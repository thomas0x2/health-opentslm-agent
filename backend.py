"""Flask backend exposing the simulated health data to a frontend.

Endpoints:
  GET /ping                          -> liveness check
  GET /api/status                    -> dataset metadata
  GET /api/latest                    -> most recent reading (relative to ?now=ISO or server time)
  GET /api/range?start=ISO&end=ISO&columns=hr,spo2&step=N
                                     -> windowed slice, optionally downsampled
  GET /api/series/<column>?start=ISO&end=ISO&step=N
                                     -> single-column series
  GET /api/daily?day=YYYY-MM-DD      -> daily summary (steps, sleep score, weight, bp)
  GET /api/events?start=ISO&end=ISO  -> discrete events (workouts, weigh-ins, bp readings)

Run:
  pip install flask flask-cors pandas
  python backend.py
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, abort, send_from_directory
from flask_cors import CORS

HERE = Path(__file__).parent
CSV_PATH = HERE / "week_health_data.csv"

app = Flask(__name__)
CORS(app)


@app.get("/")
def index():
    return send_from_directory(HERE, "frontend.html")


@app.get("/<path:filename>")
def static_file(filename: str):
    # only serve files that actually exist next to backend.py
    p = HERE / filename
    if p.is_file():
        return send_from_directory(HERE, filename)
    abort(404, "Not found")

# ---------- data load ----------
print(f"Loading {CSV_PATH} ...")
_df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"], low_memory=False)
_df = _df.set_index("timestamp").sort_index()
print(f"Loaded {len(_df):,} rows from {_df.index[0]} to {_df.index[-1]}")

ALL_COLUMNS = list(_df.columns)
COLUMN_ALIASES = {
    "hr": "heart_rate_bpm",
    "heart_rate": "heart_rate_bpm",
    "rhr": "resting_hr_bpm",
    "resting_hr": "resting_hr_bpm",
    "hrv": "hrv_rmssd_ms",
    "spo2": "spo2_pct",
    "steps": "steps_today",
    "calories": "calories_today",
    "kcal": "calories_today",
    "weight": "weight_kg",
    "sleep": "sleep_phase",
}


def resolve_columns(raw: str | None) -> list[str]:
    if not raw:
        return ALL_COLUMNS
    out = []
    for c in raw.split(","):
        c = c.strip()
        if not c:
            continue
        c = COLUMN_ALIASES.get(c, c)
        if c not in ALL_COLUMNS:
            abort(400, f"Unknown column: {c}. Available: {ALL_COLUMNS}")
        out.append(c)
    return out


def parse_ts(s: str | None, default: datetime | None = None) -> datetime | None:
    if s is None or s == "":
        return default
    try:
        return pd.to_datetime(s).to_pydatetime()
    except Exception:
        abort(400, f"Bad timestamp: {s!r}")


def df_to_records(df: pd.DataFrame) -> list[dict]:
    out = df.reset_index().copy()
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    # convert NaN to None for valid JSON
    return out.where(pd.notna(out), None).to_dict(orient="records")


# ---------- endpoints ----------
@app.get("/ping")
def ping():
    return jsonify({
        "status": "ok",
        "server_time": datetime.utcnow().isoformat() + "Z",
        "rows": len(_df),
    })


@app.get("/api/status")
def status():
    return jsonify({
        "rows": len(_df),
        "start": _df.index[0].isoformat(),
        "end": _df.index[-1].isoformat(),
        "columns": ALL_COLUMNS,
        "aliases": COLUMN_ALIASES,
    })


@app.get("/api/latest")
def latest():
    """Most recent row at-or-before ?now=... (defaults to dataset end)."""
    now = parse_ts(request.args.get("now"), _df.index[-1].to_pydatetime())
    cols = resolve_columns(request.args.get("columns"))
    sub = _df.loc[:now, cols]
    if sub.empty:
        abort(404, "No data before that timestamp")
    row = sub.iloc[[-1]]
    return jsonify(df_to_records(row)[0])


@app.get("/api/range")
def range_query():
    """Slice between start/end. Optional ?step=N to downsample (every Nth second)."""
    start = parse_ts(request.args.get("start"), _df.index[0].to_pydatetime())
    end = parse_ts(request.args.get("end"), _df.index[-1].to_pydatetime())
    cols = resolve_columns(request.args.get("columns"))
    step = max(1, int(request.args.get("step", 1)))
    max_points = int(request.args.get("max_points", 5000))

    sub = _df.loc[start:end, cols]
    if step > 1:
        sub = sub.iloc[::step]
    if len(sub) > max_points:
        # auto-thin to stay under cap
        stride = (len(sub) // max_points) + 1
        sub = sub.iloc[::stride]

    return jsonify({
        "start": start.isoformat(),
        "end": end.isoformat(),
        "columns": cols,
        "count": len(sub),
        "data": df_to_records(sub),
    })


@app.get("/api/series/<column>")
def series(column: str):
    column = COLUMN_ALIASES.get(column, column)
    if column not in ALL_COLUMNS:
        abort(400, f"Unknown column: {column}")
    start = parse_ts(request.args.get("start"), _df.index[0].to_pydatetime())
    end = parse_ts(request.args.get("end"), _df.index[-1].to_pydatetime())
    step = max(1, int(request.args.get("step", 1)))
    drop_null = request.args.get("drop_null", "0") in ("1", "true", "yes")

    s = _df.loc[start:end, column]
    if step > 1:
        s = s.iloc[::step]
    if drop_null:
        s = s.dropna()

    return jsonify({
        "column": column,
        "count": len(s),
        "timestamps": [t.strftime("%Y-%m-%dT%H:%M:%S") for t in s.index],
        "values": [None if pd.isna(v) else v.item() if hasattr(v, "item") else v
                   for v in s.values],
    })


@app.get("/api/daily")
def daily():
    """Summary for a single day."""
    day_str = request.args.get("day")
    if not day_str:
        abort(400, "?day=YYYY-MM-DD required")
    try:
        day = pd.to_datetime(day_str).normalize()
    except Exception:
        abort(400, "Bad day")
    end = day + timedelta(days=1)
    sub = _df.loc[day:end - timedelta(seconds=1)]
    if sub.empty:
        abort(404, "Day not in dataset")

    weight = sub["weight_kg"].dropna()
    sleep_score = sub["sleep_score"].dropna()
    bp_sys = sub["bp_systolic"].dropna()
    bp_dia = sub["bp_diastolic"].dropna()
    rhr = sub["resting_hr_bpm"].dropna() if "resting_hr_bpm" in sub.columns else pd.Series(dtype=float)
    hrv = sub["hrv_rmssd_ms"].dropna() if "hrv_rmssd_ms" in sub.columns else pd.Series(dtype=float)

    return jsonify({
        "day": day.strftime("%Y-%m-%d"),
        "steps_total": int(sub["steps_today"].max()),
        "calories_total": (
            round(float(sub["calories_today"].max()), 1)
            if "calories_today" in sub.columns else None
        ),
        "heart_rate": {
            "mean": round(float(sub["heart_rate_bpm"].mean()), 1),
            "min": int(sub["heart_rate_bpm"].min()),
            "max": int(sub["heart_rate_bpm"].max()),
        },
        "resting_hr": float(rhr.iloc[0]) if len(rhr) else None,
        "hrv_rmssd_ms": float(hrv.iloc[0]) if len(hrv) else None,
        "spo2_mean": round(float(sub["spo2_pct"].mean()), 2),
        "workout_seconds": int(sub["workout_flag"].sum()),
        "sleep_score": float(sleep_score.iloc[0]) if len(sleep_score) else None,
        "weight_kg": float(weight.iloc[0]) if len(weight) else None,
        "blood_pressure": (
            f"{int(bp_sys.iloc[0])}/{int(bp_dia.iloc[0])}"
            if len(bp_sys) and len(bp_dia) else None
        ),
    })


@app.get("/api/events")
def events():
    """Discrete events in a range: workouts, weigh-ins, blood pressure readings."""
    start = parse_ts(request.args.get("start"), _df.index[0].to_pydatetime())
    end = parse_ts(request.args.get("end"), _df.index[-1].to_pydatetime())
    sub = _df.loc[start:end]

    # workout intervals: detect rising/falling edges
    flag = sub["workout_flag"].values
    workouts = []
    if len(flag):
        diff = pd.Series(flag).diff().fillna(flag[0])
        starts = sub.index[diff == 1].tolist()
        ends = sub.index[diff == -1].tolist()
        if flag[0] == 1:
            starts = [sub.index[0]] + starts
        if flag[-1] == 1:
            ends = ends + [sub.index[-1]]
        for s, e in zip(starts, ends):
            workouts.append({
                "start": s.strftime("%Y-%m-%dT%H:%M:%S"),
                "end": e.strftime("%Y-%m-%dT%H:%M:%S"),
                "duration_s": int((e - s).total_seconds()),
            })

    weigh_ins = [
        {"timestamp": t.strftime("%Y-%m-%dT%H:%M:%S"), "weight_kg": float(v)}
        for t, v in sub["weight_kg"].dropna().items()
    ]
    bp_readings = [
        {
            "timestamp": t.strftime("%Y-%m-%dT%H:%M:%S"),
            "systolic": int(sub["bp_systolic"].loc[t]),
            "diastolic": int(sub["bp_diastolic"].loc[t]),
        }
        for t in sub["bp_systolic"].dropna().index
    ]
    sleep_scores = [
        {"timestamp": t.strftime("%Y-%m-%dT%H:%M:%S"), "score": float(v)}
        for t, v in sub["sleep_score"].dropna().items()
    ]

    return jsonify({
        "workouts": workouts,
        "weigh_ins": weigh_ins,
        "blood_pressure": bp_readings,
        "sleep_scores": sleep_scores,
    })


# ---------- sleep advice pipeline ----------
from sleep_pipeline.config import AGENT_BACKEND, INDEX_DIR  # noqa: E402
from sleep_pipeline.rag.retrieve import PaperRetriever  # noqa: E402
from sleep_pipeline.opentslm_runner import warmup as opentslm_warmup, summarize_night  # noqa: E402
from sleep_pipeline.features import extract as extract_features  # noqa: E402
from sleep_pipeline.agent import derive_queries, gather_chunks, synthesize_advice  # noqa: E402

_retriever = PaperRetriever(INDEX_DIR)
opentslm_warmup()


@app.get("/api/sleep_advice")
def sleep_advice():
    t0 = datetime.utcnow()
    start = parse_ts(request.args.get("start"), _df.index[0].to_pydatetime())
    end = parse_ts(request.args.get("end"), _df.index[-1].to_pydatetime())
    tone = request.args.get("tone", "clinical")
    if tone not in ("clinical", "coach"):
        abort(400, "tone must be 'clinical' or 'coach'")
    include_opentslm = request.args.get("include_opentslm", "1") in ("1", "true", "yes")

    timings: dict[str, int] = {}

    # Phase 1: features
    t_feat = datetime.utcnow()
    feats = extract_features(start, end, df=_df)
    timings["features"] = int((datetime.utcnow() - t_feat).total_seconds() * 1000)
    if not feats["nights"]:
        abort(404, "No nights detected in window")

    caveats: list[str] = []

    # Phase 2: OpenTSLM (per night)
    t_ts = datetime.utcnow()
    opentslm_payload = {"per_night_summaries": [], "error": None}
    if include_opentslm:
        per_night = []
        first_err = None
        for night in feats["nights"]:
            res = summarize_night(_df, night["bedtime"], night["wake_time"])
            per_night.append({
                "bedtime": night["bedtime"],
                "summary": res["summary"],
                "error": res["error"],
            })
            if res["error"] and first_err is None:
                first_err = res["error"]
        opentslm_payload = {"per_night_summaries": per_night, "error": first_err}
        if first_err:
            caveats.append("opentslm_unavailable")
    else:
        caveats.append("opentslm_skipped")
    timings["opentslm"] = int((datetime.utcnow() - t_ts).total_seconds() * 1000)

    # Phase 3: RAG
    t_rag = datetime.utcnow()
    queries = derive_queries(feats)
    try:
        chunks, _ = gather_chunks(_retriever, queries, k=6)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"RAG retrieval failed: {e}"}), 503
    retrieved_payload = [
        {"paper": c.paper_title, "page": c.page, "snippet": c.text[:240], "score": round(c.score, 4)}
        for c in chunks
    ]
    timings["rag"] = int((datetime.utcnow() - t_rag).total_seconds() * 1000)

    # Phase 4: agent
    t_llm = datetime.utcnow()
    try:
        advice = synthesize_advice(
            backend_name=AGENT_BACKEND,
            features=feats,
            opentslm=opentslm_payload if include_opentslm else None,
            chunks=chunks,
            tone=tone,
        )
    except Exception as e:
        return jsonify({"error": f"agent backend ({AGENT_BACKEND}) failed: {e}"}), 503
    timings["claude"] = int((datetime.utcnow() - t_llm).total_seconds() * 1000)

    if caveats:
        advice.setdefault("caveats", [])
        for c in caveats:
            if c not in advice["caveats"]:
                advice["caveats"].append(c)

    timings["total"] = int((datetime.utcnow() - t0).total_seconds() * 1000)

    return jsonify({
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "agent_backend": AGENT_BACKEND,
        "features": feats,
        "opentslm": opentslm_payload,
        "retrieved_papers": retrieved_payload,
        "advice": advice,
        "latency_ms": timings,
    })


@app.errorhandler(400)
@app.errorhandler(404)
def _err(e):
    return jsonify({"error": str(e)}), e.code


@app.errorhandler(500)
def _err500(e):
    # Keep API responses JSON even on uncaught errors.
    return jsonify({"error": f"server error: {e}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True)
