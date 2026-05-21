"""Orchestration: features → OpenTSLM → RAG queries → backend synthesize."""
from __future__ import annotations
import statistics
from typing import Any

from sleep_pipeline.rag.retrieve import Chunk, PaperRetriever
from sleep_pipeline.backends import get_backend
from sleep_pipeline.backends.base import Tone


ALWAYS_ON_QUERIES = [
    "sleep hygiene best practices adults",
    "deep sleep REM proportions adults healthy",
]


def derive_queries(features: dict[str, Any]) -> list[str]:
    """Pick literature queries from feature signals. Deterministic; capped at 6 unique."""
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

    for q in ALWAYS_ON_QUERIES:
        queries.append(q)

    # dedupe, preserve order, cap at 6
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


def gather_chunks(
    retriever: PaperRetriever, queries: list[str], k: int = 6
) -> tuple[list[Chunk], list[str]]:
    """Run each query, dedupe by (paper, page), return (chunks, query_log).

    Letting load errors (missing index, bad metadata) bubble — the caller
    surfaces those to the user. Per-query failures after load succeeded are
    suppressed so one bad query doesn't kill the request.
    """
    seen: set[tuple[str, int]] = set()
    out: list[Chunk] = []
    for i, q in enumerate(queries):
        try:
            results = retriever.retrieve(q, k=k)
        except Exception:
            if i == 0:
                raise  # first query exposes load-time issues
            continue
        for c in results:
            key = (c.paper_title, c.page)
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out, queries


_backend_cache: dict[str, Any] = {}


def _get_backend_cached(name: str):
    if name not in _backend_cache:
        _backend_cache[name] = get_backend(name)
    return _backend_cache[name]


def synthesize_advice(
    backend_name: str,
    features: dict,
    opentslm: dict | None,
    chunks: list[Chunk],
    tone: Tone = "clinical",
) -> dict:
    backend = _get_backend_cached(backend_name)
    return backend.synthesize(features=features, opentslm=opentslm, chunks=chunks, tone=tone)
