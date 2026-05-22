"""Sleep quality & consistency domain — wraps the existing sleep feature
extractor, OpenTSLM night narrator, and sleep-specific query heuristics
behind the generic Domain abstraction."""
from __future__ import annotations
import statistics
from datetime import datetime

import pandas as pd

from health_pipeline.domains.base import Domain
from health_pipeline.schemas import AdviceResponseBase
from health_pipeline.features import extract as _extract_features
from health_pipeline.opentslm_runner import summarize_night


PERSONA = (
    "You are a sleep-science assistant that returns structured json advice for a "
    "single user, grounded in (a) deterministic per-night and weekly metrics from "
    "their wearable, (b) an optional time-series narrative describing the night's "
    "physiology (may be null), and (c) excerpts from peer-reviewed sleep papers."
)

ADVICE_CATEGORIES = (
    "consistency", "duration", "hygiene", "environment", "recovery", "medical_flag"
)
SCORE_FIELDS = ("consistency_score", "quality_score")
ALWAYS_ON_QUERIES = (
    "sleep hygiene best practices adults",
    "deep sleep REM proportions adults healthy",
)


def extract(df: pd.DataFrame, start: datetime | None = None, end: datetime | None = None) -> dict:
    feats = _extract_features(start=start, end=end, df=df)
    # Surface caveat hint when window is short for week-level stats
    if feats.get("nights") and len(feats["nights"]) < 5:
        feats.setdefault("data_caveats", []).append("data_window_short_for_consistency")
    return feats


def derive_queries(features: dict) -> list[str]:
    week = features.get("week") or {}
    nights = features.get("nights") or []
    queries: list[str] = []

    cs = week.get("consistency_score_0_100")
    if cs is not None and cs < 70:
        queries.append("irregular bedtime cardiovascular metabolic risk")

    sd = week.get("bedtime_sd_minutes")
    if sd is not None and sd > 60:
        queries.append("sleep regularity index health outcomes")

    sjl = week.get("social_jet_lag_minutes")
    if sjl is not None and sjl > 60:
        queries.append("social jet lag weekend catch-up sleep")

    short_nights = sum(1 for n in nights if (n.get("tst_minutes") or 0) < 420)
    if short_nights >= 3:
        queries.append("short sleep duration adults consequences")

    dips = [n.get("hr_dip_pct") for n in nights if n.get("hr_dip_pct") is not None]
    if dips and statistics.median(dips) < 0.10:
        queries.append("nocturnal heart rate dip recovery autonomic")

    if any((n.get("spo2_desat_seconds") or 0) > 300 for n in nights):
        queries.append("nocturnal SpO2 desaturation sleep apnea screening")

    trend = (week.get("morning_hrv_trend") or {}).get("slope")
    t_stat = (week.get("morning_hrv_trend") or {}).get("t_stat")
    if trend is not None and t_stat is not None and trend < 0 and t_stat < -2.0:
        queries.append("declining HRV recovery overtraining stress")

    queries.extend(ALWAYS_ON_QUERIES)

    seen = set()
    out = []
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
        if len(out) >= 6:
            break
    return out


def narrate(df: pd.DataFrame, features: dict) -> dict:
    """Caption the most recent night's HR with OpenTSLM M4.

    Captioning every night would be ~14 s × N nights on CPU. We pick the most
    recent night as the representative sample. Returns the shape expected by
    the engine (`{summaries: [...], error}`) so older consumers still parse it.
    """
    nights = features.get("nights", []) or []
    if not nights:
        return {"summaries": [], "error": "no nights detected"}
    target = nights[-1]
    res = summarize_night(df, target["bedtime"], target["wake_time"])
    return {
        "summaries": [{
            "bedtime": target["bedtime"],
            "channel": res.get("channel"),
            "summary": res["summary"],
            "error": res["error"],
        }],
        "error": res["error"],
        "scope": "most_recent_night_only",
    }


def flag_rules(features: dict) -> list[dict]:
    """Deterministic medical-flag triggers used by the triage aggregator."""
    flags: list[dict] = []
    for night in features.get("nights", []):
        desat = night.get("spo2_desat_seconds") or 0
        if desat > 600:
            flags.append({
                "signal": "spo2_desat_seconds",
                "value": int(desat),
                "threshold": 600,
                "severity": "medium",
                "candidate_flag": "suspected_apnea",
                "context": night.get("bedtime"),
            })
        dip = night.get("hr_dip_pct")
        if dip is not None and dip < 0.05:
            flags.append({
                "signal": "hr_dip_pct",
                "value": float(dip),
                "threshold": 0.05,
                "severity": "low",
                "candidate_flag": "blunted_nocturnal_hr_dip",
                "context": night.get("bedtime"),
            })
    week = features.get("week") or {}
    sd = week.get("bedtime_sd_minutes")
    if sd is not None and sd > 120:
        flags.append({
            "signal": "bedtime_sd_minutes",
            "value": float(sd),
            "threshold": 120,
            "severity": "low",
            "candidate_flag": "severe_circadian_irregularity",
            "context": "week",
        })
    return flags


DOMAIN = Domain(
    name="sleep",
    title="Sleep quality & consistency",
    description="Sleep stages, duration, regularity, and recovery markers from wearable data.",
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
        "consistency_score (0-100) reflects bedtime regularity; quality_score (0-100) is your overall read of the week.",
        "Summary is at most 3 sentences.",
    ),
)
