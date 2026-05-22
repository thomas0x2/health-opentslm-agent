"""Nutrition & supplements domain. Wearable CSV is thin on nutrition signals;
the domain explicitly flags missing data and limits claims to what's
observable (weight trend, calorie consistency)."""
from __future__ import annotations
import math
from datetime import datetime

import numpy as np
import pandas as pd

from health_pipeline.domains.base import Domain
from health_pipeline.schemas import AdviceResponseBase


PERSONA = (
    "You are an evidence-based nutrition assistant who returns structured json "
    "guidance for a single user, grounded in (a) the user's daily calorie and "
    "weight data (sparse), and (b) excerpts from peer-reviewed nutrition papers. "
    "When data is missing, say so plainly and avoid claims you can't support."
)

ADVICE_CATEGORIES = (
    "macronutrients", "hydration", "timing", "supplements", "weight_management", "medical_flag"
)
SCORE_FIELDS = ("nutrition_adherence_score",)
ALWAYS_ON_QUERIES = (
    "protein intake muscle recovery adults",
    "evidence-based supplements healthy adults",
)


def _window(df, start, end):
    if start is None: start = df.index[0]
    if end is None:   end = df.index[-1]
    return df.loc[start:end]


def _trend(xs: list[float]) -> dict:
    if len(xs) < 3:
        return {"slope": None, "t_stat": None}
    x = np.arange(len(xs), dtype=float)
    y = np.array(xs, dtype=float)
    x_mean = x.mean(); y_mean = y.mean()
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
    daily = []
    for date, g in win.groupby(win.index.date):
        cal_series = g.get("calories_today")
        cal_series = cal_series.dropna() if cal_series is not None else pd.Series(dtype=float)
        # `calories_today` is cumulative across day → take final reading.
        kcal = float(cal_series.iloc[-1]) if not cal_series.empty else None

        weight_series = g.get("weight_kg")
        weight_series = weight_series.dropna() if weight_series is not None else pd.Series(dtype=float)
        weight = float(weight_series.iloc[0]) if not weight_series.empty else None

        daily.append({
            "date": str(date),
            "calories": round(kcal, 0) if kcal is not None else None,
            "weight_kg": round(weight, 2) if weight is not None else None,
        })

    cals = [d["calories"] for d in daily if d["calories"] is not None]
    weights = [d["weight_kg"] for d in daily if d["weight_kg"] is not None]

    cal_mean = float(np.mean(cals)) if cals else None
    cal_sd = float(np.std(cals, ddof=0)) if len(cals) >= 2 else None
    cal_cv = (cal_sd / cal_mean) if cal_mean and cal_sd is not None else None
    weight_trend = _trend(weights) if len(weights) >= 3 else {"slope": None, "t_stat": None}

    # Adherence score: penalty for high calorie CV (variability). Without targets,
    # consistency is the only thing we can legitimately score.
    adherence = None
    if cal_cv is not None:
        adherence = int(round(100 * max(0.0, 1 - cal_cv / 0.30)))

    week = {
        "calorie_mean": round(cal_mean, 0) if cal_mean is not None else None,
        "calorie_sd": round(cal_sd, 1) if cal_sd is not None else None,
        "calorie_cv": round(cal_cv, 3) if cal_cv is not None else None,
        "weight_trend": weight_trend,
        "nutrition_adherence_score_0_100": adherence,
        "days_with_calorie_log": len(cals),
        "days_with_weight_log": len(weights),
    }

    caveats: list[str] = []
    if len(cals) < 5:
        caveats.append("calorie_data_sparse")
    caveats.append("no_protein_log")  # CSV has no macro breakdown
    caveats.append("no_hydration_log")
    if not weights:
        caveats.append("no_weight_log")
    return {"daily": daily, "week": week, "data_caveats": caveats}


def derive_queries(features: dict) -> list[str]:
    week = features.get("week") or {}
    queries: list[str] = []

    cv = week.get("calorie_cv")
    if cv is not None and cv > 0.30:
        queries.append("calorie intake variability appetite regulation")

    slope = (week.get("weight_trend") or {}).get("slope")
    if slope is not None:
        if slope < -0.10:
            queries.append("unintentional weight loss screening primary care")
        if slope > 0.10:
            queries.append("rapid weight gain lifestyle intervention")

    queries.append("meal timing circadian metabolism")
    queries.append("creatine monohydrate evidence healthy adults")
    queries.append("omega-3 supplementation cardiovascular outcomes")
    queries.append("vitamin D deficiency evidence supplementation")
    queries.append("hydration adults daily requirements")

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


def flag_rules(features: dict) -> list[dict]:
    out: list[dict] = []
    week = features.get("week") or {}
    slope = (week.get("weight_trend") or {}).get("slope")
    t_stat = (week.get("weight_trend") or {}).get("t_stat")
    if slope is not None and t_stat is not None and slope < -0.20 and t_stat < -2.0:
        out.append({
            "signal": "weight_trend.slope",
            "value": float(slope),
            "threshold": -0.20,
            "severity": "medium",
            "candidate_flag": "unintentional_weight_loss",
            "context": "week",
        })
    return out


DOMAIN = Domain(
    name="nutrition",
    title="Nutrition & supplements",
    description="Calorie consistency, weight trend, and evidence-based supplement guidance.",
    persona=PERSONA,
    advice_categories=ADVICE_CATEGORIES,
    score_fields=SCORE_FIELDS,
    response_model=AdviceResponseBase,
    always_on_queries=ALWAYS_ON_QUERIES,
    extract=extract,
    derive_queries=derive_queries,
    narrate=None,  # calorie/weight signals too coarse for time-series narration
    flag_rules=flag_rules,
    hard_rules_extra=(
        "Do NOT recommend protein, hydration, or macro targets unless the user data "
        "supports it. If a relevant signal is missing (see data_caveats), say so.",
        "nutrition_adherence_score (0-100) reflects calorie-intake consistency only.",
    ),
)
