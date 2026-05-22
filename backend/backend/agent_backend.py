"""Dedicated health coach agent backend.

Run this next to the existing backend.py:
  .venv\\Scripts\\python.exe agent_backend.py

It serves only the frontend Agent page on port 5001, so Dashboard/Builder can
keep using backend.py on port 5000.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

HERE = Path(__file__).parent
DATA_DIR = HERE / "new_data" / "person_sleep_issues"
DAILY_CSV = DATA_DIR / "person_sleep_issues_daily.csv"
SECONDLY_CSV = DATA_DIR / "person_sleep_issues_secondly.csv"

load_dotenv(HERE / ".env")
os.environ["OPENTSLM_ENABLED"] = os.getenv("AGENT_OPENTSLM_ENABLED", "1")
os.environ.setdefault("RAG_OPTIONAL", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

app = Flask(__name__)
CORS(app)


def _opt_float(v: Any) -> float | None:
    return None if v is None or pd.isna(v) else float(v)


def _opt_int(v: Any) -> int | None:
    return None if v is None or pd.isna(v) else int(v)


def parse_ts(raw: str | None, default: datetime) -> datetime:
    if not raw:
        return default
    return pd.to_datetime(raw).to_pydatetime()


def load_agent_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    sec = pd.read_csv(SECONDLY_CSV, parse_dates=["timestamp"]).set_index("timestamp").sort_index()
    daily = pd.read_csv(DAILY_CSV, parse_dates=["date"]).set_index("date").sort_index()

    df = sec.copy()
    for col in (
        "resting_hr_bpm",
        "hrv_rmssd_ms",
        "sleep_score",
        "weight_kg",
        "bp_systolic",
        "bp_diastolic",
    ):
        df[col] = pd.NA
        if col in daily.columns:
            for day, val in daily[col].dropna().items():
                ts = pd.Timestamp(day)
                if ts in df.index:
                    df.at[ts, col] = val
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df, daily


_df, _daily = load_agent_frame()

from health_pipeline.config import DOMAINS_ENABLED, OPENTSLM_ENABLED  # noqa: E402
from health_pipeline.domains import DOMAIN_REGISTRY  # noqa: E402
from health_pipeline import engine  # noqa: E402
from health_pipeline.opentslm_runner import warmup as opentslm_warmup  # noqa: E402

if OPENTSLM_ENABLED:
    opentslm_warmup()


def serialize_domain(domain):
    return {
        "name": domain.name,
        "title": domain.title,
        "description": domain.description,
        "advice_categories": list(domain.advice_categories),
        "score_fields": list(domain.score_fields),
        "accepts_cross_domain_evidence": domain.accepts_cross_domain_evidence,
    }


def fallback_advice(domain: str, error: str | None = None) -> dict:
    latest_day = _daily.index[-1].strftime("%Y-%m-%d")
    r = _daily.iloc[-1]
    summary = (
        f"I analyzed your latest available health data through the {domain} agent. "
        f"The newest daily record is {latest_day}."
    )
    if domain == "sleep":
        summary = (
            f"Your latest sleep record is {latest_day}: sleep score "
            f"{_opt_float(r.get('sleep_score'))}, total sleep {_opt_float(r.get('sleep_minutes'))} minutes, "
            f"and minimum SpO2 {_opt_float(r.get('min_spo2_pct'))}%."
        )
    elif domain == "training":
        summary = (
            f"Your latest training load on {latest_day}: {_opt_float(r.get('workout_minutes'))} workout minutes, "
            f"{_opt_int(r.get('steps_total'))} steps, and resting HR {_opt_float(r.get('resting_hr_bpm'))} bpm."
        )
    elif domain == "nutrition":
        summary = (
            f"Your latest nutrition proxy data on {latest_day}: {_opt_float(r.get('calories_total'))} kcal, "
            f"{_opt_int(r.get('steps_total'))} steps, and weight {_opt_float(r.get('weight_kg'))} kg."
        )
    elif domain == "cardio":
        summary = (
            f"Your latest cardio markers on {latest_day}: resting HR {_opt_float(r.get('resting_hr_bpm'))} bpm, "
            f"HRV {_opt_float(r.get('hrv_rmssd_ms'))} ms, and minimum SpO2 {_opt_float(r.get('min_spo2_pct'))}%."
        )
    elif domain == "triage":
        summary = (
            f"Latest triage scan used {latest_day}. If you have chest pain, fainting, severe shortness of breath, "
            "or concerning symptoms, discuss with a clinician promptly."
        )

    caveats = ["local_fallback_response"]
    if error:
        caveats.append(error[:240])

    return {
        "domain": domain,
        "agent_backend": "local-fallback",
        "features": {},
        "narration": None,
        "queries": [],
        "retrieved_papers": [],
        "advice": {
            "summary": summary,
            "advice": [{
                "category": "recovery",
                "headline": "Review the latest trend",
                "rationale": "The dedicated agent backend is available and can read the local wearable dataset.",
                "actionable_step": "Use the domain tabs to run sleep, cardio, training, nutrition, or triage analysis.",
                "citations": [],
                "applies_to": latest_day,
            }],
            "scores": {},
            "red_flags": [],
            "medical_disclaimer": "This is informational and does not replace medical advice.",
            "caveats": caveats,
        },
        "latency_ms": {"total": 0},
        "window": {"start": _df.index[0].isoformat(), "end": _df.index[-1].isoformat()},
    }


@app.get("/ping")
def ping():
    return jsonify({
        "status": "ok",
        "backend": "agent",
        "opentslm_enabled": OPENTSLM_ENABLED,
        "rows": len(_df),
    })


@app.get("/api/agents")
def list_agents():
    return jsonify([
        serialize_domain(d)
        for d in DOMAIN_REGISTRY.values()
        if d.name in DOMAINS_ENABLED
    ])


@app.get("/api/agents/<domain>")
def run_agent(domain: str):
    if domain not in DOMAIN_REGISTRY or domain not in DOMAINS_ENABLED:
        return jsonify({"error": f"Unknown agent domain: {domain}"}), 404

    start = parse_ts(request.args.get("start"), _df.index[0].to_pydatetime())
    end = parse_ts(request.args.get("end"), _df.index[-1].to_pydatetime())
    tone = request.args.get("tone", "coach")
    include_opentslm = request.args.get("include_opentslm", "1") in ("1", "true", "yes")

    try:
        t0 = datetime.utcnow()
        out = engine.run(
            domain_name=domain,
            df=_df,
            start=start,
            end=end,
            tone=tone if tone in ("clinical", "coach") else "coach",
            include_opentslm=include_opentslm,
        )
        out["window"] = {"start": start.isoformat(), "end": end.isoformat()}
        out["latency_ms"]["total"] = int((datetime.utcnow() - t0).total_seconds() * 1000)
        return jsonify(out)
    except Exception as e:
        return jsonify(fallback_advice(domain, str(e)))


if __name__ == "__main__":
    port = int(os.environ.get("AGENT_PORT", "5001"))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=False, use_reloader=False)
