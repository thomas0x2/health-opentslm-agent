"""Sleep & consistency feature extraction.

All metrics derived from the wearable CSV; no ML in here. The output is consumed by
the agent layer as JSON, and also drives deterministic RAG query selection.
"""
from __future__ import annotations
from datetime import datetime, timedelta
import math
from typing import Any

import numpy as np
import pandas as pd

MIN_NIGHT_MINUTES = 180
MERGE_GAP_MINUTES = 60
DESAT_THRESHOLD = 92.0
PRE_BED_WINDOW_MIN = 30
MORNING_LOOKAHEAD_MIN = 30


def _detect_nights(df: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Group contiguous non-null sleep_phase runs into nights.

    Merges spans separated by < MERGE_GAP_MINUTES; drops spans < MIN_NIGHT_MINUTES
    so naps don't pollute the consistency stats.
    """
    flag = df["sleep_phase"].notna().astype(int)
    if flag.empty or flag.sum() == 0:
        return []
    edges = flag.diff().fillna(flag.iloc[0])
    starts = df.index[edges == 1].tolist()
    ends = df.index[edges == -1].tolist()
    if flag.iloc[0] == 1:
        starts = [df.index[0]] + starts
    if flag.iloc[-1] == 1:
        ends = ends + [df.index[-1]]

    spans = list(zip(starts, ends))
    merged: list[list[pd.Timestamp]] = []
    for s, e in spans:
        if merged and (s - merged[-1][1]).total_seconds() / 60 < MERGE_GAP_MINUTES:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    out = []
    for s, e in merged:
        if (e - s).total_seconds() / 60 >= MIN_NIGHT_MINUTES:
            out.append((s, e))
    return out


def _circular_sd_minutes(times_of_day_minutes: list[float]) -> float:
    """Circular standard deviation of times-of-day (minutes since midnight)."""
    if len(times_of_day_minutes) < 2:
        return 0.0
    angles = [2 * math.pi * t / 1440 for t in times_of_day_minutes]
    sin_mean = np.mean([math.sin(a) for a in angles])
    cos_mean = np.mean([math.cos(a) for a in angles])
    r = math.sqrt(sin_mean**2 + cos_mean**2)
    if r >= 1.0:
        return 0.0
    sd_rad = math.sqrt(-2.0 * math.log(r))
    return sd_rad * 1440 / (2 * math.pi)


def _time_of_day_minutes(ts: pd.Timestamp) -> float:
    return ts.hour * 60 + ts.minute + ts.second / 60.0


def _midpoint_minutes(bedtime: pd.Timestamp, wake: pd.Timestamp) -> float:
    """Midpoint of sleep as minutes after noon (wraps so the middle of the night
    lands around 14h-22h of "minutes after noon").
    """
    duration = (wake - bedtime).total_seconds() / 60.0
    bed_min = _time_of_day_minutes(bedtime)
    mid = (bed_min + duration / 2) % 1440
    return mid


def _lookup_morning_scalar(
    df: pd.DataFrame, wake_time: pd.Timestamp, column: str
) -> float | None:
    """Find a single morning reading at-or-just-after wake_time (within MORNING_LOOKAHEAD_MIN).

    Many wearables emit HRV / resting HR as a single reading at wake — that's the
    coverage pattern in our CSV. Look back briefly too in case the reading is
    timestamped a few seconds before the last sleep row.
    """
    if column not in df.columns:
        return None
    window_start = wake_time - timedelta(minutes=5)
    window_end = wake_time + timedelta(minutes=MORNING_LOOKAHEAD_MIN)
    s = df.loc[window_start:window_end, column].dropna()
    if s.empty:
        return None
    return float(s.iloc[0])


def per_night_features(
    df: pd.DataFrame, span_start: pd.Timestamp, span_end: pd.Timestamp
) -> dict[str, Any]:
    night = df.loc[span_start:span_end]
    tst_minutes = (span_end - span_start).total_seconds() / 60.0

    phases = night["sleep_phase"].dropna().str.lower()
    # CSV uses light/deep/REM; lowercase normalises REM.
    stage_seconds = phases.value_counts().to_dict()
    light_min = stage_seconds.get("light", 0) / 60.0
    deep_min = stage_seconds.get("deep", 0) / 60.0
    rem_min = stage_seconds.get("rem", 0) / 60.0
    total_staged = light_min + deep_min + rem_min or 1.0

    hr = night["heart_rate_bpm"].dropna()
    spo2 = night["spo2_pct"].dropna()

    pre_bed = df.loc[
        span_start - timedelta(minutes=PRE_BED_WINDOW_MIN) : span_start, "heart_rate_bpm"
    ].dropna()
    mean_hr_pre_bed = float(pre_bed.mean()) if not pre_bed.empty else None
    min_hr_sleep = float(hr.min()) if not hr.empty else None
    if mean_hr_pre_bed and min_hr_sleep is not None and mean_hr_pre_bed > 0:
        hr_dip_pct = (mean_hr_pre_bed - min_hr_sleep) / mean_hr_pre_bed
    else:
        hr_dip_pct = None

    spo2_desat_seconds = int((spo2 < DESAT_THRESHOLD).sum()) if not spo2.empty else 0

    return {
        "bedtime": span_start.isoformat(),
        "wake_time": span_end.isoformat(),
        "tst_minutes": round(tst_minutes, 1),
        "stage_distribution": {
            "light": {"minutes": round(light_min, 1), "fraction": round(light_min / total_staged, 3)},
            "deep": {"minutes": round(deep_min, 1), "fraction": round(deep_min / total_staged, 3)},
            "rem": {"minutes": round(rem_min, 1), "fraction": round(rem_min / total_staged, 3)},
        },
        "mean_hr_sleep": round(float(hr.mean()), 1) if not hr.empty else None,
        "min_hr_sleep": min_hr_sleep,
        "mean_spo2_sleep": round(float(spo2.mean()), 2) if not spo2.empty else None,
        "min_spo2_sleep": round(float(spo2.min()), 2) if not spo2.empty else None,
        "hr_dip_pct": round(hr_dip_pct, 3) if hr_dip_pct is not None else None,
        "spo2_desat_seconds": spo2_desat_seconds,
        "morning_hrv_ms": _lookup_morning_scalar(df, span_end, "hrv_rmssd_ms"),
        "morning_resting_hr": _lookup_morning_scalar(df, span_end, "resting_hr_bpm"),
    }


def _hrv_trend(nights: list[dict]) -> dict[str, float | None]:
    vals = [(i, n["morning_hrv_ms"]) for i, n in enumerate(nights) if n.get("morning_hrv_ms") is not None]
    if len(vals) < 3:
        return {"slope": None, "p_value": None}
    xs = np.array([v[0] for v in vals], dtype=float)
    ys = np.array([v[1] for v in vals], dtype=float)
    n = len(xs)
    x_mean = xs.mean()
    y_mean = ys.mean()
    denom = ((xs - x_mean) ** 2).sum()
    if denom == 0:
        return {"slope": 0.0, "p_value": None}
    slope = float(((xs - x_mean) * (ys - y_mean)).sum() / denom)
    intercept = float(y_mean - slope * x_mean)
    resid = ys - (slope * xs + intercept)
    if n > 2:
        s_err = float(np.sqrt((resid**2).sum() / (n - 2)))
        se_slope = s_err / math.sqrt(denom)
        t_stat = slope / se_slope if se_slope > 0 else None
    else:
        t_stat = None
    return {"slope": round(slope, 3), "t_stat": round(t_stat, 3) if t_stat else None}


def _chronotype(midpoint_time_of_day_minutes: float) -> str:
    """Classify chronotype from the mean sleep midpoint (time-of-day, minutes).

    Thresholds target adult sleepers whose midpoint lands between ~01:00 and 06:00.
    Early < 03:30 (210), intermediate < 04:30 (270), else late.
    """
    m = midpoint_time_of_day_minutes
    if m < 210:
        return "early"
    if m < 270:
        return "intermediate"
    return "late"


def week_consistency(nights: list[dict]) -> dict[str, Any]:
    if not nights:
        return {
            "bedtime_sd_minutes": None,
            "waketime_sd_minutes": None,
            "sleep_midpoint_mean": None,
            "sleep_midpoint_sd": None,
            "social_jet_lag_minutes": None,
            "consistency_score_0_100": None,
            "nights_meeting_7h": 0,
            "chronotype": None,
            "morning_hrv_trend": {"slope": None},
        }

    bedtimes = [pd.Timestamp(n["bedtime"]) for n in nights]
    waketimes = [pd.Timestamp(n["wake_time"]) for n in nights]
    bedtime_mins = [_time_of_day_minutes(b) for b in bedtimes]
    waketime_mins = [_time_of_day_minutes(w) for w in waketimes]
    midpoint_mins = [_midpoint_minutes(b, w) for b, w in zip(bedtimes, waketimes)]

    bedtime_sd = _circular_sd_minutes(bedtime_mins)
    waketime_sd = _circular_sd_minutes(waketime_mins)

    weekend_mids = [m for b, m in zip(bedtimes, midpoint_mins) if b.weekday() >= 5]
    weekday_mids = [m for b, m in zip(bedtimes, midpoint_mins) if b.weekday() < 5]
    if weekend_mids and weekday_mids:
        social_jet_lag = abs(np.mean(weekend_mids) - np.mean(weekday_mids))
    else:
        social_jet_lag = None

    consistency_score = round(100 * max(0.0, 1 - bedtime_sd / 90.0))

    nights_meeting_7h = sum(1 for n in nights if n["tst_minutes"] >= 420)
    midpoint_mean = float(np.mean(midpoint_mins))

    return {
        "bedtime_sd_minutes": round(bedtime_sd, 1),
        "waketime_sd_minutes": round(waketime_sd, 1),
        "sleep_midpoint_mean": round(midpoint_mean, 1),
        "sleep_midpoint_sd": round(_circular_sd_minutes(midpoint_mins), 1),
        "social_jet_lag_minutes": round(social_jet_lag, 1) if social_jet_lag is not None else None,
        "consistency_score_0_100": int(consistency_score),
        "nights_meeting_7h": nights_meeting_7h,
        "chronotype": _chronotype(midpoint_mean),
        "morning_hrv_trend": _hrv_trend(nights),
    }


def extract(
    start: datetime | None = None,
    end: datetime | None = None,
    df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Top-level entry point. df defaults to backend._df."""
    if df is None:
        from backend import _df as df  # noqa: PLC0415 — avoid circular at import time
    if start is None:
        start = df.index[0]
    if end is None:
        end = df.index[-1]
    window = df.loc[start:end]
    spans = _detect_nights(window)
    nights = [per_night_features(df, s, e) for s, e in spans]
    return {"nights": nights, "week": week_consistency(nights)}
