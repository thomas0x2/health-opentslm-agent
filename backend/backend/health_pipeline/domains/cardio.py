"""Cardiovascular conditioning domain: resting-HR & HRV trends, weekly Z2
exposure, autonomic-balance signals."""
from __future__ import annotations
import math
from datetime import datetime

import numpy as np
import pandas as pd

from health_pipeline.config import MAX_HR_DEFAULT
from health_pipeline.domains.base import Domain
from health_pipeline.schemas import AdviceResponseBase


PERSONA = (
    "You are a cardiovascular conditioning coach who returns structured json "
    "advice for a single user, grounded in (a) deterministic daily and weekly "
    "cardio metrics from their wearable, (b) an optional time-series narrative "
    "of resting-HR and HRV trajectories (may be null), and (c) excerpts from "
    "peer-reviewed cardio-conditioning papers."
)

ADVICE_CATEGORIES = (
    "aerobic_volume", "intensity", "vitals_trend", "recovery", "medical_flag"
)
SCORE_FIELDS = ("cardio_fitness_score", "autonomic_balance_score")
ALWAYS_ON_QUERIES = (
    "zone 2 training cardiovascular adaptation",
    "resting heart rate trend health outcomes",
)

ZONE2_LOW_FRAC = 0.60
ZONE2_HIGH_FRAC = 0.70


def _window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if start is None:
        start = df.index[0]
    if end is None:
        end = df.index[-1]
    return df.loc[start:end]


def _trend(xs: list[float]) -> dict[str, float | None]:
    if len(xs) < 3:
        return {"slope": None, "t_stat": None}
    x = np.arange(len(xs), dtype=float)
    y = np.array(xs, dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom == 0:
        return {"slope": 0.0, "t_stat": None}
    slope = float(((x - x_mean) * (y - y_mean)).sum() / denom)
    intercept = y_mean - slope * x_mean
    resid = y - (slope * x + intercept)
    n = len(xs)
    if n > 2:
        s_err = float(np.sqrt((resid ** 2).sum() / (n - 2)))
        se = s_err / math.sqrt(denom)
        t_stat = slope / se if se > 0 else None
    else:
        t_stat = None
    return {"slope": round(slope, 4), "t_stat": round(t_stat, 3) if t_stat is not None else None}


def extract(df: pd.DataFrame, start: datetime | None = None, end: datetime | None = None) -> dict:
    win = _window(df, start, end)
    max_hr = float(MAX_HR_DEFAULT)
    z2_low = ZONE2_LOW_FRAC * max_hr
    z2_high = ZONE2_HIGH_FRAC * max_hr

    daily = []
    grouped = win.groupby(win.index.date)
    for date, g in grouped:
        rhr_series = g.get("resting_hr_bpm")
        rhr_series = rhr_series.dropna() if rhr_series is not None else pd.Series(dtype=float)
        hrv_series = g.get("hrv_rmssd_ms")
        hrv_series = hrv_series.dropna() if hrv_series is not None else pd.Series(dtype=float)
        hr_series = g.get("heart_rate_bpm")
        hr_series = hr_series.dropna() if hr_series is not None else pd.Series(dtype=float)

        # Each row is one second of data (1 Hz CSV), so counting in-zone rows == in-zone seconds.
        in_zone2 = ((hr_series >= z2_low) & (hr_series <= z2_high)).sum() if not hr_series.empty else 0
        max_hr_observed = float(hr_series.max()) if not hr_series.empty else None

        daily.append({
            "date": str(date),
            "mean_rhr": round(float(rhr_series.mean()), 1) if not rhr_series.empty else None,
            "mean_hrv": round(float(hrv_series.mean()), 1) if not hrv_series.empty else None,
            "max_hr_observed": max_hr_observed,
            "minutes_in_zone2": round(int(in_zone2) / 60.0, 1),
        })

    rhr_vals = [d["mean_rhr"] for d in daily if d["mean_rhr"] is not None]
    hrv_vals = [d["mean_hrv"] for d in daily if d["mean_hrv"] is not None]
    z2_total = round(sum(d["minutes_in_zone2"] for d in daily), 1)

    rhr_mean = float(np.mean(rhr_vals)) if rhr_vals else None
    hrv_mean = float(np.mean(hrv_vals)) if hrv_vals else None

    # Linear blend: lower RHR better (anchor 60 bpm), higher HRV better (anchor 50 ms),
    # weekly Z2 vs 150 min benchmark. Each component clipped to [0, 1].
    def _score():
        comps = []
        if rhr_mean is not None:
            comps.append(max(0.0, min(1.0, (90 - rhr_mean) / 30.0)))
        if hrv_mean is not None:
            comps.append(max(0.0, min(1.0, hrv_mean / 70.0)))
        comps.append(max(0.0, min(1.0, z2_total / 150.0)))
        return int(round(100 * sum(comps) / len(comps))) if comps else None

    cardio_score = _score()
    rhr_trend = _trend(rhr_vals) if rhr_vals else {"slope": None, "t_stat": None}
    hrv_trend = _trend(hrv_vals) if hrv_vals else {"slope": None, "t_stat": None}

    week = {
        "rhr_mean": round(rhr_mean, 1) if rhr_mean is not None else None,
        "hrv_mean": round(hrv_mean, 1) if hrv_mean is not None else None,
        "zone2_minutes_total": z2_total,
        "rhr_trend": rhr_trend,
        "hrv_trend": hrv_trend,
        "cardio_fitness_score_0_100": cardio_score,
        "days_observed": len(daily),
        "max_hr_assumed": max_hr,
    }

    caveats: list[str] = []
    if len(daily) < 7:
        caveats.append("data_window_short_for_trend")
    if rhr_mean is None:
        caveats.append("no_resting_hr_logged")

    return {"daily": daily, "week": week, "data_caveats": caveats}


def derive_queries(features: dict) -> list[str]:
    week = features.get("week") or {}
    queries: list[str] = []

    rhr_mean = week.get("rhr_mean")
    if rhr_mean is not None and rhr_mean > 75:
        queries.append("elevated resting heart rate cardiovascular risk")

    hrv_mean = week.get("hrv_mean")
    if hrv_mean is not None and hrv_mean < 30:
        queries.append("low HRV chronic stress overtraining")

    z2 = week.get("zone2_minutes_total") or 0
    if z2 < 90:
        queries.append("aerobic exercise volume weekly guidelines")

    rt = (week.get("rhr_trend") or {}).get("slope")
    rt_t = (week.get("rhr_trend") or {}).get("t_stat")
    if rt is not None and rt_t is not None and rt > 0.5 and rt_t > 2:
        queries.append("rising resting heart rate detraining illness")

    queries.extend(ALWAYS_ON_QUERIES)

    seen, out = set(), []
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
        if len(out) >= 6:
            break
    return out


def narrate(df: pd.DataFrame, features: dict) -> dict:
    """Caption the week's continuous heart-rate signal via OpenTSLM M4.

    M4 needs ~256 samples — week-level daily aggregates (7 points) are too
    short — so we feed the full continuous heart_rate_bpm series resampled
    down to 256 buckets.
    """
    from health_pipeline.config import OPENTSLM_ENABLED
    if not OPENTSLM_ENABLED:
        return {"summary": None, "error": "OPENTSLM_ENABLED=0", "summaries": []}
    try:
        from health_pipeline.opentslm_runner import _resample_to_target, caption_series
        hr = df.get("heart_rate_bpm")
        if hr is None or hr.dropna().empty:
            return {"summary": None, "error": "no heart_rate_bpm in window", "summaries": []}
        series = _resample_to_target(hr.dropna())
        res = caption_series(series, channel_label="heart_rate_bpm (week, 256 buckets)")
        return {
            "summaries": [{
                "scope": "week",
                "channel": res.get("channel"),
                "summary": res["summary"],
                "error": res["error"],
            }],
            "error": res["error"],
        }
    except Exception as e:
        return {"summary": None, "error": f"narrate failed: {e}", "summaries": []}


def flag_rules(features: dict) -> list[dict]:
    out: list[dict] = []
    week = features.get("week") or {}
    rt = (week.get("rhr_trend") or {})
    if rt.get("slope") is not None and rt.get("t_stat") is not None and rt["slope"] > 1.0 and rt["t_stat"] > 2.0:
        out.append({
            "signal": "rhr_trend.slope",
            "value": float(rt["slope"]),
            "threshold": 1.0,
            "severity": "medium",
            "candidate_flag": "rising_resting_hr",
            "context": "week",
        })
    rhr_mean = week.get("rhr_mean")
    if rhr_mean is not None and rhr_mean > 90:
        out.append({
            "signal": "rhr_mean",
            "value": float(rhr_mean),
            "threshold": 90,
            "severity": "medium",
            "candidate_flag": "resting_tachycardia",
            "context": "week",
        })
    return out


DOMAIN = Domain(
    name="cardio",
    title="Cardiovascular conditioning",
    description="Resting HR, HRV trends, weekly aerobic Z2 volume, autonomic balance.",
    persona=PERSONA,
    advice_categories=ADVICE_CATEGORIES,
    score_fields=SCORE_FIELDS,
    response_model=AdviceResponseBase,
    always_on_queries=ALWAYS_ON_QUERIES,
    extract=extract,
    derive_queries=derive_queries,
    narrate=narrate,
    flag_rules=flag_rules,
    hard_rules_extra=(
        "cardio_fitness_score (0-100) is your read of weekly Z2 exposure + RHR + HRV; "
        "autonomic_balance_score (0-100) reflects HRV trend stability.",
    ),
)
