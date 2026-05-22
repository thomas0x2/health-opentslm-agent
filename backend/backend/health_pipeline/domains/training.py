"""Training load & recovery domain: daily load proxies + HRV/RHR-based recovery."""
from __future__ import annotations
import statistics
from datetime import datetime

import numpy as np
import pandas as pd

from health_pipeline.domains.base import Domain
from health_pipeline.schemas import AdviceResponseBase


PERSONA = (
    "You are a sport-science coach who returns structured json training & "
    "recovery advice, grounded in (a) deterministic daily load and recovery "
    "metrics, (b) an optional time-series narrative of load-vs-recovery "
    "coupling, and (c) excerpts from sport-science papers."
)

ADVICE_CATEGORIES = (
    "load_balance", "deload", "intensity", "recovery", "fueling_link", "medical_flag"
)
SCORE_FIELDS = ("load_score", "recovery_score")
ALWAYS_ON_QUERIES = (
    "acute chronic workload ratio injury risk",
    "HRV-guided training adaptation",
)


def _window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if start is None:
        start = df.index[0]
    if end is None:
        end = df.index[-1]
    return df.loc[start:end]


def _last_nonnull(s: pd.Series) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _first_nonnull(s: pd.Series) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    return float(s.iloc[0])


def extract(df: pd.DataFrame, start: datetime | None = None, end: datetime | None = None) -> dict:
    win = _window(df, start, end)
    daily = []
    for date, g in win.groupby(win.index.date):
        steps = _last_nonnull(g.get("steps_today", pd.Series(dtype=float)))
        kcal = _last_nonnull(g.get("calories_today", pd.Series(dtype=float)))
        sleep_score = _last_nonnull(g.get("sleep_score", pd.Series(dtype=float)))
        morning_hrv = _first_nonnull(g.get("hrv_rmssd_ms", pd.Series(dtype=float)))
        morning_rhr = _first_nonnull(g.get("resting_hr_bpm", pd.Series(dtype=float)))

        # Load index: blend of steps and calories, clipped. Hackathon-grade TRIMP proxy.
        load = 0.0
        if steps is not None:
            load += min(steps / 1000.0, 20.0)
        if kcal is not None:
            load += min(kcal / 100.0, 30.0)

        daily.append({
            "date": str(date),
            "steps": steps,
            "active_kcal": kcal,
            "sleep_score": sleep_score,
            "morning_hrv": morning_hrv,
            "morning_rhr": morning_rhr,
            "load_index": round(load, 1),
        })

    loads = [d["load_index"] for d in daily if d["load_index"] is not None]
    n = len(loads)

    # ACWR: acute = last 3 days mean, chronic = full window mean.
    acwr = None
    acwr_reliable = True
    if n >= 3:
        acute = float(np.mean(loads[-3:]))
        chronic = float(np.mean(loads))
        if chronic > 0:
            acwr = round(acute / chronic, 2)
        if n < 7:
            acwr_reliable = False

    # Monotony: sd / mean (Foster) — high values flag uniform load.
    monotony = None
    if n >= 3 and statistics.mean(loads) > 0:
        monotony = round(statistics.pstdev(loads) / statistics.mean(loads), 2)

    sleep_scores = [d["sleep_score"] for d in daily if d["sleep_score"] is not None]
    hrv_vals = [d["morning_hrv"] for d in daily if d["morning_hrv"] is not None]

    # Recovery score: HRV anchored 50 ms, sleep anchored 80 (good).
    comps = []
    if hrv_vals:
        comps.append(max(0.0, min(1.0, float(np.mean(hrv_vals)) / 70.0)))
    if sleep_scores:
        comps.append(max(0.0, min(1.0, float(np.mean(sleep_scores)) / 100.0)))
    recovery_score = int(round(100 * sum(comps) / len(comps))) if comps else None

    # Load score: 70 = "balanced" (ACWR ≈ 1.0); decreases as ACWR drifts away.
    load_score = None
    if acwr is not None:
        load_score = int(round(100 * max(0.0, 1 - abs(acwr - 1.0) / 0.7)))

    week = {
        "load_total": round(sum(loads), 1),
        "load_mean": round(float(np.mean(loads)), 1) if loads else None,
        "acwr": acwr,
        "acwr_reliable": acwr_reliable,
        "monotony": monotony,
        "recovery_score_0_100": recovery_score,
        "load_score_0_100": load_score,
        "days_observed": n,
    }

    caveats: list[str] = []
    if n < 7:
        caveats.append("data_window_short_for_acwr")
    if not sleep_scores:
        caveats.append("no_sleep_score_logged")
    if not hrv_vals:
        caveats.append("no_morning_hrv_logged")

    return {"daily": daily, "week": week, "data_caveats": caveats}


def derive_queries(features: dict) -> list[str]:
    week = features.get("week") or {}
    queries: list[str] = []

    acwr = week.get("acwr")
    if acwr is not None and acwr > 1.3:
        queries.append("training spike injury risk acute chronic")
    if acwr is not None and acwr < 0.8:
        queries.append("undertraining detraining cardiorespiratory loss")

    monotony = week.get("monotony")
    if monotony is not None and monotony > 1.5:
        queries.append("training monotony overreaching prevention")

    rec = week.get("recovery_score_0_100")
    if rec is not None and rec < 60:
        queries.append("sleep recovery athletic performance")

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
    """Caption the week's continuous step signal via OpenTSLM M4.

    `steps_today` is cumulative within each day; resampling its raw 1 Hz
    trace to 256 buckets captures load shape across the week (sleep periods
    flat, daytime accumulating). M4 needs >= 32 samples so we use 256.
    """
    from health_pipeline.config import OPENTSLM_ENABLED
    if not OPENTSLM_ENABLED:
        return {"summary": None, "error": "OPENTSLM_ENABLED=0", "summaries": []}
    try:
        from health_pipeline.opentslm_runner import _resample_to_target, caption_series
        steps = df.get("steps_today")
        if steps is None or steps.dropna().empty:
            return {"summary": None, "error": "no steps_today in window", "summaries": []}
        series = _resample_to_target(steps.dropna())
        res = caption_series(series, channel_label="steps_today (week, 256 buckets)")
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
    acwr = week.get("acwr")
    if acwr is not None and acwr > 1.5 and week.get("acwr_reliable"):
        out.append({
            "signal": "acwr",
            "value": float(acwr),
            "threshold": 1.5,
            "severity": "medium",
            "candidate_flag": "training_spike_injury_risk",
            "context": "week",
        })
    rec = week.get("recovery_score_0_100")
    if rec is not None and rec < 40:
        out.append({
            "signal": "recovery_score_0_100",
            "value": int(rec),
            "threshold": 40,
            "severity": "low",
            "candidate_flag": "low_recovery_state",
            "context": "week",
        })
    return out


DOMAIN = Domain(
    name="training",
    title="Training load & recovery",
    description="Daily load proxies, ACWR, recovery markers, monotony, deload signals.",
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
        "load_score (0-100) peaks at 100 when ACWR is near 1.0; recovery_score (0-100) "
        "blends HRV and sleep-score means.",
    ),
)
