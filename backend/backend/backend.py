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
CSV_PATH = HERE / "week_health_data.csv"
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
print(f"Loading {CSV_PATH} ...")
_df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])
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


VIZ_TYPES = ["single_value", "line", "bar", "scatter", "area", "stacked_bar", "heatmap"]

AGENT_SYSTEM_PROMPT = """You are a health dashboard widget builder. Generate ONLY valid JSON — no markdown fences, no prose.

AVAILABLE HEALTH DATA (array of daily records, field types & units):
  date: string ("YYYY-MM-DD")
  heart_rate_mean: number (bpm) — average heart rate for the day
  heart_rate_min: number (bpm) — lowest heart rate
  heart_rate_max: number (bpm) — highest heart rate
  resting_hr: number|null (bpm) — morning resting heart rate (one reading per day, may be null)
  hrv_ms: number|null (ms) — heart rate variability RMSSD (one reading per day, may be null)
  spo2_mean: number (%) — average blood oxygen saturation
  sleep_score: number|null (0-100) — sleep quality score (may be null)
  steps_total: number — total steps for the day
  calories_total: number|null — total calories burned (may be null)
  workout_minutes: number — total workout minutes for the day
  weight_kg: number|null — body weight in kg (may be null)
  bp_systolic: number|null — systolic blood pressure (may be null)
  bp_diastolic: number|null — diastolic blood pressure (may be null)

RULES:
- Filter out null values before computing.
- Handle empty arrays gracefully (return reasonable defaults like 0 or null).
- computeFn must be a JS function body string: the body of a function(records) { ... }.
- The function receives an array of HealthRecord objects and must return a ComputeResult.

COMPUTE RESULT TYPES:

single_value: { kind: "single_value", value: number, unit: string, label: string, trend?: "up"|"down"|"flat", trendValue?: number }
  Use for: single KPI metrics (e.g. average HRV, total steps, best sleep score).

series: { kind: "series", series: Array<{ x: string|number, y: number, label?: string }>, xLabel?: string, yLabel?: string, unit?: string }
  Use for: trends over time, comparisons, distributions. Each entry in series has x (the label/date/category) and y (the value).

VIZ TYPE GUIDE:
- single_value: big number display — best for single metrics (avg HR, total steps, best sleep)
- line: line chart — best for trends over time (HRV by day, resting HR trend)
- bar: bar chart — best for comparing values across days (steps per day)
- scatter: scatter plot — best for correlation (HRV vs sleep score, steps vs calories)
- area: area chart — best for cumulative or range data
- stacked_bar: stacked bars — best for composition
- heatmap: grid of colored cells — best for week-at-a-glance patterns

WIDGET JSON SCHEMA (respond with EXACTLY this shape):
{
  "title": "string (≤5 words, concise)",
  "description": "string (1 sentence explaining the metric)",
  "vizType": "single_value | line | bar | scatter | area | stacked_bar | heatmap",
  "computeFn": "string (JS function body, see rules above)"
}

RETURN ONLY THE JSON OBJECT. No explanation, no markdown fences."""


def _get_sample_records() -> list[dict]:
    """Build 2 sample HealthRecords for computeFn validation."""
    dates = sorted(set(_df.index.normalize()))[:2]
    records = []
    for day in dates:
        end_ts = day + timedelta(days=1)
        sub = _df.loc[day:end_ts - timedelta(seconds=1)]
        if sub.empty:
            continue
        rhr = sub["resting_hr_bpm"].dropna() if "resting_hr_bpm" in sub.columns else pd.Series(dtype=float)
        hrv = sub["hrv_rmssd_ms"].dropna() if "hrv_rmssd_ms" in sub.columns else pd.Series(dtype=float)
        cal = sub["calories_today"].dropna() if "calories_today" in sub.columns else pd.Series(dtype=float)
        weight = sub["weight_kg"].dropna()
        sleep_sc = sub["sleep_score"].dropna()
        bp_s = sub["bp_systolic"].dropna()
        bp_d = sub["bp_diastolic"].dropna()
        records.append({
            "date": day.strftime("%Y-%m-%d"),
            "heart_rate_mean": round(float(sub["heart_rate_bpm"].mean()), 1),
            "heart_rate_min": int(sub["heart_rate_bpm"].min()),
            "heart_rate_max": int(sub["heart_rate_bpm"].max()),
            "resting_hr": float(rhr.iloc[0]) if len(rhr) else None,
            "hrv_ms": float(hrv.iloc[0]) if len(hrv) else None,
            "spo2_mean": round(float(sub["spo2_pct"].mean()), 2),
            "sleep_score": float(sleep_sc.iloc[0]) if len(sleep_sc) else None,
            "steps_total": int(sub["steps_today"].max()),
            "calories_total": round(float(cal.iloc[0]), 1) if len(cal) else None,
            "workout_minutes": round(int(sub["workout_flag"].sum()) / 60, 1),
            "weight_kg": float(weight.iloc[0]) if len(weight) else None,
            "bp_systolic": int(bp_s.iloc[0]) if len(bp_s) else None,
            "bp_diastolic": int(bp_d.iloc[0]) if len(bp_d) else None,
        })
    return records


def _validate_fn_in_node(compute_fn: str, sample_records: list[dict]) -> tuple[bool, str | None, dict | None]:
    """Run computeFn in Node.js against sample data. Returns (ok, error_msg, result)."""
    # Escape computeFn for safe embedding in a Node one-liner.
    # Use JSON string to pass computeFn + records into Node.
    payload = _json.dumps({"fn": compute_fn, "records": sample_records[:2]})
    script = f"""
const {{fn, records}} = JSON.parse({_json.dumps(payload)});
try {{
  const f = new Function('records', fn);
  const result = f(records);
  if (!result || typeof result !== 'object' || !result.kind) {{
    throw new Error('Result must be an object with a "kind" field');
  }}
  if (result.kind !== 'single_value' && result.kind !== 'series') {{
    throw new Error('kind must be "single_value" or "series"');
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
    dates = sorted(set(_df.index.normalize()))
    records = []
    for day in dates:
        end_ts = day + timedelta(days=1)
        sub = _df.loc[day:end_ts - timedelta(seconds=1)]
        if sub.empty:
            continue
        rhr = sub["resting_hr_bpm"].dropna() if "resting_hr_bpm" in sub.columns else pd.Series(dtype=float)
        hrv = sub["hrv_rmssd_ms"].dropna() if "hrv_rmssd_ms" in sub.columns else pd.Series(dtype=float)
        cal = sub["calories_today"].dropna() if "calories_today" in sub.columns else pd.Series(dtype=float)
        weight = sub["weight_kg"].dropna()
        sleep_sc = sub["sleep_score"].dropna()
        bp_s = sub["bp_systolic"].dropna()
        bp_d = sub["bp_diastolic"].dropna()
        records.append({
            "date": day.strftime("%Y-%m-%d"),
            "heart_rate_mean": round(float(sub["heart_rate_bpm"].mean()), 1),
            "heart_rate_min": int(sub["heart_rate_bpm"].min()),
            "heart_rate_max": int(sub["heart_rate_bpm"].max()),
            "resting_hr": float(rhr.iloc[0]) if len(rhr) else None,
            "hrv_ms": float(hrv.iloc[0]) if len(hrv) else None,
            "spo2_mean": round(float(sub["spo2_pct"].mean()), 2),
            "sleep_score": float(sleep_sc.iloc[0]) if len(sleep_sc) else None,
            "steps_total": int(sub["steps_today"].max()),
            "calories_total": round(float(cal.iloc[0]), 1) if len(cal) else None,
            "workout_minutes": round(int(sub["workout_flag"].sum()) / 60, 1),
            "weight_kg": float(weight.iloc[0]) if len(weight) else None,
            "bp_systolic": int(bp_s.iloc[0]) if len(bp_s) else None,
            "bp_diastolic": int(bp_d.iloc[0]) if len(bp_d) else None,
        })
    return jsonify({"records": records})


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
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            temperature=0.3 if attempt == 0 else 0.5,
        )
        raw = resp.choices[0].message.content or ""
        raw = _strip_markdown_fences(raw)

        # Step 1 — JSON parse
        try:
            widget = _json.loads(raw)
        except _json.JSONDecodeError as e:
            last_error = f"Invalid JSON: {e}"
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
            if attempt < max_retries:
                messages.append({
                    "role": "user",
                    "content": f"Invalid vizType '{widget['vizType']}'. Must be one of: {VIZ_TYPES}.",
                })
                continue
            break

        # Step 4 — computeFn runtime check (Node.js)
        fn_ok, fn_err, fn_result = _validate_fn_in_node(widget["computeFn"], sample_records)
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
