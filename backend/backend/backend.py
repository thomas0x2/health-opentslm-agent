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
import os, uuid, json as _json, subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, request, abort, send_from_directory
from flask_cors import CORS
from openai import OpenAI

HERE = Path(__file__).parent
DATA_DIR = HERE / "new_data" / "person_sleep_issues"
DAILY_CSV = DATA_DIR / "person_sleep_issues_daily.csv"
SECONDLY_CSV = DATA_DIR / "person_sleep_issues_secondly.csv"
load_dotenv(HERE / ".env")

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
# New layout: daily aggregates in *_daily.csv, high-res samples in *_secondly.csv.
# For backward compatibility we expose a single seconds-indexed `_df` with the
# same columns the old endpoints used by merging daily values onto midnight of
# each day.
print(f"Loading {SECONDLY_CSV} ...")
_sec = pd.read_csv(SECONDLY_CSV, parse_dates=["timestamp"])
_sec = _sec.set_index("timestamp").sort_index()
print(f"  secondly: {len(_sec):,} rows from {_sec.index[0]} to {_sec.index[-1]}")

print(f"Loading {DAILY_CSV} ...")
_daily = pd.read_csv(DAILY_CSV, parse_dates=["date"])
_daily = _daily.set_index("date").sort_index()
print(f"  daily:    {len(_daily):,} rows from {_daily.index[0]} to {_daily.index[-1]}")

# Pre-compute per-day heart-rate min/mean/max and spo2 mean from the seconds
# data (the daily csv only has avg_heart_rate_bpm and min_spo2_pct).
_hr_by_day = _sec["heart_rate_bpm"].groupby(_sec.index.normalize()).agg(["min", "mean", "max"])
_spo2_mean_by_day = _sec["spo2_pct"].groupby(_sec.index.normalize()).mean()

# Enriched daily frame used by /api/daily and /api/health/raw.
_daily_df = _daily.copy()
_daily_df["heart_rate_min"] = _hr_by_day["min"]
_daily_df["heart_rate_mean"] = _hr_by_day["mean"].round(1)
_daily_df["heart_rate_max"] = _hr_by_day["max"]
_daily_df["spo2_mean"] = _spo2_mean_by_day.round(2)

# Build the legacy seconds-indexed frame so old endpoints keep working.
_df = _sec.copy()
# Per-day aggregates are sparse columns that only carry a value at 00:00:00 of
# the day they belong to — matches the original dataset's shape.
_daily_to_legacy = {
    "resting_hr_bpm": "resting_hr_bpm",
    "hrv_rmssd_ms": "hrv_rmssd_ms",
    "sleep_score": "sleep_score",
    "weight_kg": "weight_kg",
    "bp_systolic": "bp_systolic",
    "bp_diastolic": "bp_diastolic",
}
for src_col, dst_col in _daily_to_legacy.items():
    _df[dst_col] = pd.NA
    for day, val in _daily[src_col].dropna().items():
        ts = pd.Timestamp(day)
        if ts in _df.index:
            _df.at[ts, dst_col] = val
    _df[dst_col] = pd.to_numeric(_df[dst_col], errors="coerce")

print(f"Loaded {len(_df):,} legacy rows, columns={list(_df.columns)}")

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


def _opt_float(v):
    return None if v is None or pd.isna(v) else float(v)


def _opt_int(v):
    return None if v is None or pd.isna(v) else int(v)


@app.get("/api/daily")
def daily():
    """Summary for a single day (reads pre-aggregated daily CSV)."""
    day_str = request.args.get("day")
    if not day_str:
        abort(400, "?day=YYYY-MM-DD required")
    try:
        day = pd.to_datetime(day_str).normalize()
    except Exception:
        abort(400, "Bad day")
    if day not in _daily_df.index:
        abort(404, "Day not in dataset")
    r = _daily_df.loc[day]
    bp_s, bp_d = _opt_int(r.get("bp_systolic")), _opt_int(r.get("bp_diastolic"))

    return jsonify({
        "day": day.strftime("%Y-%m-%d"),
        "steps_total": _opt_int(r.get("steps_total")) or 0,
        "calories_total": _opt_float(r.get("calories_total")),
        "heart_rate": {
            "mean": round(float(r["heart_rate_mean"]), 1) if pd.notna(r.get("heart_rate_mean")) else None,
            "min": _opt_int(r.get("heart_rate_min")),
            "max": _opt_int(r.get("heart_rate_max")),
        },
        "resting_hr": _opt_float(r.get("resting_hr_bpm")),
        "hrv_rmssd_ms": _opt_float(r.get("hrv_rmssd_ms")),
        "spo2_mean": round(float(r["spo2_mean"]), 2) if pd.notna(r.get("spo2_mean")) else None,
        "workout_seconds": int(round(float(r.get("workout_minutes") or 0) * 60)),
        "sleep_score": _opt_float(r.get("sleep_score")),
        "sleep_minutes": _opt_float(r.get("sleep_minutes")),
        "deep_minutes": _opt_float(r.get("deep_minutes")),
        "rem_minutes": _opt_float(r.get("rem_minutes")),
        "light_minutes": _opt_float(r.get("light_minutes")),
        "min_spo2_pct": _opt_float(r.get("min_spo2_pct")),
        "weight_kg": _opt_float(r.get("weight_kg")),
        "blood_pressure": f"{bp_s}/{bp_d}" if bp_s is not None and bp_d is not None else None,
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


VIZ_TYPES = ["single_value", "line", "bar", "scatter", "area", "stacked_bar", "heatmap"]

AGENT_SYSTEM_PROMPT = """You are a health dashboard widget builder. Generate ONLY valid JSON — no markdown fences, no prose.

AVAILABLE HEALTH DATA (array of DAILY records — one row per day, already sorted by date ascending):
  date: string ("YYYY-MM-DD")
  heart_rate_mean: number|null (bpm) — average heart rate for the day
  heart_rate_min: number|null (bpm) — lowest heart rate
  heart_rate_max: number|null (bpm) — highest heart rate
  resting_hr: number|null (bpm) — morning resting heart rate (may be null)
  hrv_ms: number|null (ms) — heart rate variability RMSSD (may be null)
  spo2_mean: number|null (%) — average blood oxygen saturation
  min_spo2_pct: number|null (%) — lowest SpO2 sample of the day (often during sleep)
  sleep_score: number|null (0-100) — overall sleep quality score (may be null)
  sleep_minutes: number|null — total sleep duration in minutes (may be 0 on no-sleep days)
  deep_minutes: number|null — minutes in deep sleep
  rem_minutes: number|null — minutes in REM sleep
  light_minutes: number|null — minutes in light sleep
  steps_total: number — total steps for the day
  calories_total: number|null — total calories burned (may be null)
  workout_minutes: number — total workout minutes for the day
  weight_kg: number|null — body weight in kg (may be null)
  bp_systolic: number|null — systolic blood pressure (may be null)
  bp_diastolic: number|null — diastolic blood pressure (may be null)

CRITICAL RULES:
1. ALWAYS filter `null` and non-finite values before using a field: `records.filter(r => r.X != null && Number.isFinite(r.X))`.
2. Records are already one-per-day. Do NOT group by date or deduplicate — each row is already a distinct day.
3. For "weekly"/"7-day" type requests: use the last 7 records, e.g. `records.slice(-7)`.
4. For "monthly" requests: group by year-month: `r.date.slice(0, 7)`.
5. NEVER concatenate values — accumulate with `+=` or `reduce((a, b) => a + b, 0)`.
6. Handle empty arrays — guard with `if (filtered.length === 0) return {...defaults}`.
7. computeFn is the BODY of a `function(records) { ... }` — start with code, end with `return {...}`.
8. Return value MUST match one of the result types below. The `kind` field is REQUIRED.
9. For series results, x should be a meaningful label (date "YYYY-MM-DD", or category like "Mon"); y MUST be a finite number.

COMPUTE RESULT TYPES:

A) single_value:
   { kind: "single_value", value: number, unit: string, label: string, trend?: "up"|"down"|"flat", trendValue?: number }
   Use for: single KPIs (avg HRV, total steps, best sleep).

B) series:
   { kind: "series", series: [{ x: string|number, y: number, label?: string }], xLabel?: string, yLabel?: string, unit?: string }
   Use for: trends, comparisons, distributions, correlations.

VIZ TYPE GUIDE:
- single_value: one big number (e.g. "Average HRV this week")
- line: trend over time — DATE x-axis (e.g. "HRV trend last 7 days")
- area: cumulative/filled trend over time (e.g. "Steps over week")
- bar: discrete comparison across days/categories (e.g. "Sleep score per day")
- scatter: correlation between two NUMERIC fields — x AND y must be numbers (e.g. "HRV vs sleep score")
- stacked_bar: composition breakdown (e.g. one segment per category)
- heatmap: grid where x = row label, y = value, label = column label

WORKED EXAMPLES (study these patterns carefully):

# Example 1 — single_value (Average HRV last 7 days):
{
  "title": "Avg HRV (7d)",
  "description": "Average heart rate variability over the past week.",
  "vizType": "single_value",
  "computeFn": "const recs = records.slice(-7).filter(r => r.hrv_ms != null && Number.isFinite(r.hrv_ms)); if (recs.length === 0) return { kind: 'single_value', value: 0, unit: 'ms', label: 'No data' }; const avg = recs.reduce((s, r) => s + r.hrv_ms, 0) / recs.length; const prev = records.slice(-14, -7).filter(r => r.hrv_ms != null); const prevAvg = prev.length ? prev.reduce((s, r) => s + r.hrv_ms, 0) / prev.length : avg; return { kind: 'single_value', value: Math.round(avg * 10) / 10, unit: 'ms', label: '7-day average', trend: avg > prevAvg ? 'up' : avg < prevAvg ? 'down' : 'flat', trendValue: Math.round((avg - prevAvg) * 10) / 10 };"
}

# Example 2 — line (HRV trend last 7 days):
{
  "title": "HRV Weekly Trend",
  "description": "Heart rate variability over the past 7 days.",
  "vizType": "line",
  "computeFn": "const recs = records.slice(-7).filter(r => r.hrv_ms != null && Number.isFinite(r.hrv_ms)); return { kind: 'series', series: recs.map(r => ({ x: r.date, y: Math.round(r.hrv_ms * 10) / 10 })), xLabel: 'Date', yLabel: 'HRV', unit: 'ms' };"
}

# Example 3 — bar (Steps per day):
{
  "title": "Daily Steps",
  "description": "Total steps per day over the past week.",
  "vizType": "bar",
  "computeFn": "const recs = records.slice(-7).filter(r => Number.isFinite(r.steps_total)); return { kind: 'series', series: recs.map(r => ({ x: r.date, y: r.steps_total })), xLabel: 'Date', yLabel: 'Steps', unit: 'steps' };"
}

# Example 4 — area (Sleep score trend):
{
  "title": "Sleep Score Trend",
  "description": "Daily sleep quality score over the past 2 weeks.",
  "vizType": "area",
  "computeFn": "const recs = records.slice(-14).filter(r => r.sleep_score != null && Number.isFinite(r.sleep_score)); return { kind: 'series', series: recs.map(r => ({ x: r.date, y: Math.round(r.sleep_score) })), xLabel: 'Date', yLabel: 'Sleep score', unit: 'points' };"
}

# Example 5 — scatter (HRV vs sleep score):
{
  "title": "HRV vs Sleep Score",
  "description": "Correlation between sleep quality and recovery.",
  "vizType": "scatter",
  "computeFn": "const recs = records.filter(r => r.hrv_ms != null && r.sleep_score != null && Number.isFinite(r.hrv_ms) && Number.isFinite(r.sleep_score)); return { kind: 'series', series: recs.map(r => ({ x: r.sleep_score, y: r.hrv_ms, label: r.date })), xLabel: 'Sleep score', yLabel: 'HRV (ms)', unit: 'ms' };"
}

# Example 6 — stacked_bar (Calorie split, illustrative):
{
  "title": "Last Day Composition",
  "description": "Breakdown of the most recent day's calorie components.",
  "vizType": "stacked_bar",
  "computeFn": "const r = records[records.length - 1]; const total = (r.calories_total ?? 0); const workout = Math.round((r.workout_minutes / 60) * 400); const basal = Math.max(0, total - workout); return { kind: 'series', series: [{ x: 'Basal', y: basal, label: 'Basal' }, { x: 'Active', y: workout, label: 'Active' }], yLabel: 'kcal', unit: 'kcal' };"
}

# Example 7 — heatmap (sleep score by day-of-week × week):
{
  "title": "Sleep Heatmap",
  "description": "Sleep score by day of week across recent weeks.",
  "vizType": "heatmap",
  "computeFn": "const recs = records.filter(r => r.sleep_score != null); const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']; const cells = recs.map(r => { const d = new Date(r.date); const wk = `W${Math.floor((d.getTime() - new Date(recs[0].date).getTime()) / (7*86400000)) + 1}`; return { x: wk, y: Math.round(r.sleep_score), label: days[d.getDay()] }; }); return { kind: 'series', series: cells, xLabel: 'Week', yLabel: 'Score', unit: 'points' };"
}

WIDGET JSON SCHEMA (respond with EXACTLY this shape, no extra keys):
{
  "title": "string (≤5 words)",
  "description": "string (1 sentence)",
  "vizType": "single_value | line | bar | scatter | area | stacked_bar | heatmap",
  "computeFn": "string — JS function body"
}

RETURN ONLY THE JSON OBJECT. No explanation, no markdown fences, no commentary."""


def _build_health_records(limit: int | None = None) -> list[dict]:
    """Build HealthRecord[] from the pre-aggregated daily frame."""
    df = _daily_df if limit is None else _daily_df.tail(limit)
    records = []
    for day, r in df.iterrows():
        records.append({
            "date": day.strftime("%Y-%m-%d"),
            "heart_rate_mean": round(float(r["heart_rate_mean"]), 1) if pd.notna(r.get("heart_rate_mean")) else None,
            "heart_rate_min": _opt_int(r.get("heart_rate_min")),
            "heart_rate_max": _opt_int(r.get("heart_rate_max")),
            "resting_hr": _opt_float(r.get("resting_hr_bpm")),
            "hrv_ms": _opt_float(r.get("hrv_rmssd_ms")),
            "spo2_mean": round(float(r["spo2_mean"]), 2) if pd.notna(r.get("spo2_mean")) else None,
            "min_spo2_pct": _opt_float(r.get("min_spo2_pct")),
            "sleep_score": _opt_float(r.get("sleep_score")),
            "sleep_minutes": _opt_float(r.get("sleep_minutes")),
            "deep_minutes": _opt_float(r.get("deep_minutes")),
            "rem_minutes": _opt_float(r.get("rem_minutes")),
            "light_minutes": _opt_float(r.get("light_minutes")),
            "steps_total": _opt_int(r.get("steps_total")) or 0,
            "calories_total": _opt_float(r.get("calories_total")),
            "workout_minutes": _opt_float(r.get("workout_minutes")) or 0.0,
            "weight_kg": _opt_float(r.get("weight_kg")),
            "bp_systolic": _opt_int(r.get("bp_systolic")),
            "bp_diastolic": _opt_int(r.get("bp_diastolic")),
        })
    return records


def _get_sample_records() -> list[dict]:
    """Build sample HealthRecords for computeFn validation (last 60 days)."""
    return _build_health_records(limit=60)


def _validate_fn_in_node(compute_fn: str, sample_records: list[dict]) -> tuple[bool, str | None, dict | None]:
    """Run computeFn in Node.js against sample data. Returns (ok, error_msg, result)."""
    # Escape computeFn for safe embedding in a Node one-liner.
    # Use JSON string to pass computeFn + records into Node.
    payload = _json.dumps({"fn": compute_fn, "records": sample_records})
    script = f"""
const {{fn, records}} = JSON.parse({_json.dumps(payload)});
try {{
  const f = new Function('records', fn);
  const result = f(records);
  if (!result || typeof result !== 'object' || !result.kind) {{
    throw new Error('Result must be an object with a "kind" field');
  }}
  if (result.kind === 'single_value') {{
    if (typeof result.value !== 'number' || !Number.isFinite(result.value)) {{
      throw new Error('single_value.value must be a finite number (got ' + typeof result.value + ': ' + result.value + ')');
    }}
    if (typeof result.unit !== 'string') {{
      throw new Error('single_value.unit must be a string');
    }}
  }} else if (result.kind === 'series') {{
    if (!Array.isArray(result.series)) {{
      throw new Error('series must be an array');
    }}
    if (result.series.length === 0) {{
      throw new Error('series is empty — check your null filtering or use a larger window');
    }}
    const sample = result.series.slice(0, 5);
    for (let i = 0; i < sample.length; i++) {{
      const p = sample[i];
      if (!p || typeof p !== 'object') throw new Error('series[' + i + '] is not an object');
      if (p.x === undefined || p.x === null) throw new Error('series[' + i + '].x is missing');
      if (typeof p.y !== 'number' || !Number.isFinite(p.y)) {{
        throw new Error('series[' + i + '].y must be a finite number (got ' + typeof p.y + ': ' + JSON.stringify(p.y) + ')');
      }}
    }}
  }} else {{
    throw new Error('kind must be "single_value" or "series" (got ' + JSON.stringify(result.kind) + ')');
  }}
  console.log(JSON.stringify({{ok:true, result}}));
}} catch(e) {{
  console.log(JSON.stringify({{ok:false, error: e.message || String(e)}}));
}}
"""
    try:
        out = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, timeout=10,
            cwd=str(HERE),
        )
        raw = out.stdout.strip() or out.stderr.strip()
        if not raw:
            return False, "Node produced no output", None
        parsed = _json.loads(raw)
        if parsed.get("ok"):
            return True, None, parsed.get("result")
        return False, parsed.get("error", "Unknown runtime error"), None
    except subprocess.TimeoutExpired:
        return False, "computeFn timed out (>10s)", None
    except FileNotFoundError:
        return True, None, None  # Node not installed — skip runtime validation
    except Exception as e:
        return False, str(e), None


def _strip_markdown_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines[0].startswith("```"):
            lines.pop(0)
        if lines and lines[-1].strip() == "```":
            lines.pop()
        s = "\n".join(lines).strip()
    return s


@app.get("/api/health/raw")
def health_raw():
    """All daily summaries as HealthRecord[] — used by widget compute functions."""
    return jsonify({"records": _build_health_records()})


@app.post("/api/agent")
def agent():
    """Widget generation agent — sends prompt to DeepSeek, validates response, retries on failure."""
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt", "") or "").strip()
    if not prompt:
        abort(400, "prompt required")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        abort(500, "DEEPSEEK_API_KEY not configured")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    sample_records = _get_sample_records()
    max_retries = 3
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    last_error = None
    for attempt in range(max_retries + 1):
        print(f"[agent] attempt {attempt + 1}/{max_retries + 1}, prompt={prompt[:80]!r}")
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            temperature=0.3 if attempt == 0 else 0.5,
        )
        raw = resp.choices[0].message.content or ""
        print(f"[agent] raw response ({len(raw)} chars): {raw[:300]!r}")
        raw = _strip_markdown_fences(raw)

        # Step 1 — JSON parse
        try:
            widget = _json.loads(raw)
        except _json.JSONDecodeError as e:
            last_error = f"Invalid JSON: {e}"
            print(f"[agent] JSON parse error: {e}")
            if attempt < max_retries:
                messages.append({
                    "role": "user",
                    "content": f"Attempt {attempt + 1} failed. Your response was not valid JSON: {e}.\nReturn ONLY a valid JSON object matching the widget schema. No markdown fences, no prose.",
                })
                continue
            break

        # Step 2 — required fields
        required = ["title", "description", "vizType", "computeFn"]
        missing = [f for f in required if f not in widget or not widget[f]]
        if missing:
            last_error = f"Missing fields: {missing}"
            print(f"[agent] missing fields: {missing}")
            if attempt < max_retries:
                messages.append({
                    "role": "user",
                    "content": f"Missing required fields: {missing}. Include all of: {required}.",
                })
                continue
            break

        # Step 3 — vizType check
        if widget["vizType"] not in VIZ_TYPES:
            last_error = f"Invalid vizType '{widget['vizType']}'"
            print(f"[agent] invalid vizType: {widget['vizType']!r}")
            if attempt < max_retries:
                messages.append({
                    "role": "user",
                    "content": f"Invalid vizType '{widget['vizType']}'. Must be one of: {VIZ_TYPES}.",
                })
                continue
            break

        # Step 4 — computeFn runtime check (Node.js)
        print(f"[agent] computeFn ({len(widget['computeFn'])} chars):\n{widget['computeFn']}")
        fn_ok, fn_err, fn_result = _validate_fn_in_node(widget["computeFn"], sample_records)
        print(f"[agent] node validation: ok={fn_ok}, err={fn_err!r}, result={str(fn_result)[:200]!r}")
        if not fn_ok:
            last_error = fn_err or "Unknown computeFn error"
            if attempt < max_retries:
                sample_json = _json.dumps(sample_records[:2], indent=2)
                messages.append({
                    "role": "user",
                    "content": (
                        f"Attempt {attempt + 1} failed — computeFn runtime error: {fn_err}\n"
                        f"Your computeFn:\n```js\n{widget['computeFn']}\n```\n"
                        f"Sample data (2 records):\n```json\n{sample_json}\n```\n"
                        f"Fix the error and return the complete Widget JSON again."
                    ),
                })
                continue
            break

        # Success
        widget["id"] = str(uuid.uuid4())
        widget["createdAt"] = datetime.utcnow().isoformat() + "Z"
        reply = f"Created '{widget['title']}': {widget['description']}"
        print(f"[agent] success: {widget['title']!r} vizType={widget['vizType']!r}")
        return jsonify({"reply": reply, "widget": widget})

    # All retries exhausted or hard failure
    return jsonify({
        "reply": f"Failed to generate widget after {max_retries + 1} attempts.",
        "error": last_error,
    })


@app.errorhandler(400)
@app.errorhandler(404)
def _err(e):
    return jsonify({"error": str(e)}), e.code


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True)
