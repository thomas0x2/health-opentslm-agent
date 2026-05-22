"""Alert-doctor / triage domain. Runs as its own domain (own RAG, own feature
extraction) AND aggregates evidence from the other domains via the engine's
cross-domain pre-pass. Output schema is TriageResponse (flags + severity)."""
from __future__ import annotations
from datetime import datetime

import pandas as pd

from health_pipeline.domains.base import Domain
from health_pipeline.schemas import TriageResponse


PERSONA = (
    "You are a cautious triage assistant for a single user. You return structured "
    "json flags for issues that warrant clinician follow-up, grounded in (a) "
    "deterministic signals from the user's wearable, (b) evidence harvested from "
    "other recommendation domains, and (c) excerpts from clinical guidelines. "
    "You do NOT diagnose, you do NOT prescribe, and every non-'none' flag includes "
    "the phrase 'discuss with a clinician'."
)

ADVICE_CATEGORIES = (
    "suspected_apnea", "arrhythmia_pattern", "cardiovascular_risk",
    "metabolic", "dysautonomia", "other"
)
SCORE_FIELDS = ()  # triage uses overall_severity at top level
ALWAYS_ON_QUERIES = (
    "sleep apnea screening primary care",
    "resting tachycardia evaluation adult",
)


def _window(df, start, end):
    if start is None: start = df.index[0]
    if end is None:   end = df.index[-1]
    return df.loc[start:end]


def extract(df: pd.DataFrame, start: datetime | None = None, end: datetime | None = None) -> dict:
    win = _window(df, start, end)

    spo2 = win.get("spo2_pct", pd.Series(dtype=float)).dropna()
    rhr = win.get("resting_hr_bpm", pd.Series(dtype=float)).dropna()
    hrv = win.get("hrv_rmssd_ms", pd.Series(dtype=float)).dropna()

    spo2_desat_total = int((spo2 < 92).sum()) if not spo2.empty else 0
    min_spo2 = float(spo2.min()) if not spo2.empty else None

    rhr_max = float(rhr.max()) if not rhr.empty else None
    rhr_mean = float(rhr.mean()) if not rhr.empty else None
    rhr_z_max = None
    if len(rhr) >= 3 and rhr.std() > 0:
        rhr_z_max = float(((rhr - rhr.mean()) / rhr.std()).max())

    hrv_min = float(hrv.min()) if not hrv.empty else None
    hrv_median = float(hrv.median()) if not hrv.empty else None
    hrv_drop_pct = None
    if hrv_min is not None and hrv_median and hrv_median > 0:
        hrv_drop_pct = round(1 - hrv_min / hrv_median, 3)

    caveats: list[str] = []
    if min_spo2 is None:
        caveats.append("no_spo2_data")
    if rhr_mean is None:
        caveats.append("no_resting_hr_data")
    caveats.append("no_blood_pressure_data")  # CSV does not include BP

    return {
        "spo2_desat_seconds_total": spo2_desat_total,
        "min_spo2_observed": round(min_spo2, 1) if min_spo2 is not None else None,
        "rhr_max": round(rhr_max, 1) if rhr_max is not None else None,
        "rhr_mean": round(rhr_mean, 1) if rhr_mean is not None else None,
        "rhr_z_max": round(rhr_z_max, 2) if rhr_z_max is not None else None,
        "hrv_min": round(hrv_min, 1) if hrv_min is not None else None,
        "hrv_drop_pct_vs_median": hrv_drop_pct,
        "data_caveats": caveats,
        # cross_domain_evidence injected by engine when accepts_cross_domain_evidence=True
    }


def derive_queries(features: dict) -> list[str]:
    queries: list[str] = []

    if (features.get("spo2_desat_seconds_total") or 0) > 600 or (features.get("min_spo2_observed") or 100) < 90:
        queries.append("nocturnal hypoxemia sleep apnea screening")

    if (features.get("rhr_max") or 0) > 100:
        queries.append("resting tachycardia adult evaluation")

    if (features.get("hrv_drop_pct_vs_median") or 0) > 0.4:
        queries.append("autonomic dysfunction HRV adults")

    # Promote queries from cross-domain evidence (each item already carries a
    # candidate_flag hint — use it to drive retrieval).
    for ev in features.get("cross_domain_evidence", []) or []:
        cf = ev.get("candidate_flag")
        if cf == "suspected_apnea":
            queries.append("sleep apnea diagnostic criteria primary care")
        elif cf == "rising_resting_hr":
            queries.append("elevated resting heart rate cardiovascular evaluation")
        elif cf == "training_spike_injury_risk":
            queries.append("overtraining syndrome diagnosis recovery")
        elif cf == "unintentional_weight_loss":
            queries.append("unintentional weight loss workup differential")

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


DOMAIN = Domain(
    name="triage",
    title="Alert doctor (triage)",
    description="Cross-domain screening pass; surfaces signals that warrant clinician follow-up.",
    persona=PERSONA,
    advice_categories=ADVICE_CATEGORIES,
    score_fields=SCORE_FIELDS,
    response_model=TriageResponse,
    always_on_queries=ALWAYS_ON_QUERIES,
    extract=extract,
    derive_queries=derive_queries,
    narrate=None,  # high-stakes, skip narrative model
    flag_rules=None,
    accepts_cross_domain_evidence=True,
    hard_rules_extra=(
        "Each flag's `severity` MUST be one of: none, low, medium, high.",
        "Each flag's `urgency` MUST be one of: routine, prompt, urgent.",
        "Every non-'none' flag MUST include the literal phrase 'discuss with a clinician' "
        "in either its `recommended_action` or `summary`.",
        "When `cross_domain_evidence` items exist in the input, build at least one flag "
        "per distinct `candidate_flag` value found there, and copy the supporting "
        "`{source, signal, value, threshold}` into the flag's `evidence` list.",
        "`overall_severity` (0-100): your weighted estimate based on flag count and severity.",
        "`escalation_recommended` MUST be true if any flag has severity 'high' or urgency 'urgent'.",
    ),
)
