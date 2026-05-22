"""Orchestrator: turns a (domain_name, dataframe, window, tone) request into
a validated structured response by routing through the domain's extract →
optional narrate → derive_queries → RAG → LLM backend pipeline.

For the triage domain (accepts_cross_domain_evidence=True), pre-runs each
non-triage domain's `extract` + `flag_rules` and injects the harvested
evidence list into the triage features under `cross_domain_evidence`."""
from __future__ import annotations
from datetime import datetime
from typing import Any

import pandas as pd

from health_pipeline.config import AGENT_BACKEND, RAG_OPTIONAL
from health_pipeline.backends import get_backend
from health_pipeline.backends.base import Tone
from health_pipeline.rag.retrieve import Chunk, PaperRetriever
from health_pipeline.domains import DOMAIN_REGISTRY
from health_pipeline.domains.base import Domain


_retriever_cache: dict[str, PaperRetriever] = {}
_backend_cache: dict[str, Any] = {}


def get_retriever(domain_name: str) -> PaperRetriever:
    if domain_name not in _retriever_cache:
        _retriever_cache[domain_name] = PaperRetriever(domain_name)
    return _retriever_cache[domain_name]


def _get_backend(name: str):
    if name not in _backend_cache:
        _backend_cache[name] = get_backend(name)
    return _backend_cache[name]


def gather_chunks(retriever: PaperRetriever, queries: list[str], k: int = 6) -> list[Chunk]:
    """Run each query, dedupe by (paper_title, page), preserve first-seen order."""
    seen: set[tuple[str, int]] = set()
    out: list[Chunk] = []
    for i, q in enumerate(queries):
        try:
            results = retriever.retrieve(q, k=k)
        except Exception:
            if RAG_OPTIONAL:
                continue
            if i == 0:
                raise  # surface load-time issues to the caller
            continue
        for c in results:
            key = (c.paper_title, c.page)
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


def _collect_cross_domain_evidence(
    df: pd.DataFrame, start: datetime, end: datetime
) -> list[dict]:
    """Run each non-triage domain's extract + flag_rules and bundle the hits."""
    evidence: list[dict] = []
    for name, dom in DOMAIN_REGISTRY.items():
        if dom.accepts_cross_domain_evidence:
            continue
        try:
            feats = dom.extract(df=df, start=start, end=end)
        except Exception as e:
            evidence.append({
                "source": name, "signal": "extract_failed",
                "value": str(e)[:200], "threshold": "",
                "severity": "low", "candidate_flag": "extract_failed",
            })
            continue
        if dom.flag_rules is None:
            continue
        try:
            for flag in dom.flag_rules(feats):
                evidence.append({"source": name, **flag})
        except Exception as e:
            evidence.append({
                "source": name, "signal": "flag_rules_failed",
                "value": str(e)[:200], "threshold": "",
                "severity": "low", "candidate_flag": "flag_rules_failed",
            })
    return evidence


def run(
    domain_name: str,
    df: pd.DataFrame,
    start: datetime,
    end: datetime,
    tone: Tone = "clinical",
    include_opentslm: bool = True,
) -> dict:
    if domain_name not in DOMAIN_REGISTRY:
        raise ValueError(f"Unknown domain: {domain_name!r}")
    domain: Domain = DOMAIN_REGISTRY[domain_name]

    timings: dict[str, int] = {}
    caveats: list[str] = []

    # 1. Features
    t = datetime.utcnow()
    features = domain.extract(df=df, start=start, end=end)
    timings["features"] = int((datetime.utcnow() - t).total_seconds() * 1000)
    if isinstance(features, dict) and features.get("data_caveats"):
        caveats.extend(features.pop("data_caveats"))

    # 1b. Cross-domain pre-pass (triage only)
    if domain.accepts_cross_domain_evidence:
        t = datetime.utcnow()
        features["cross_domain_evidence"] = _collect_cross_domain_evidence(df, start, end)
        timings["cross_domain"] = int((datetime.utcnow() - t).total_seconds() * 1000)

    # 2. Narrate (optional)
    narration = None
    t = datetime.utcnow()
    if include_opentslm and domain.narrate is not None:
        try:
            narration = domain.narrate(df, features)
        except Exception as e:
            narration = {"summary": None, "error": f"narrate raised: {e}"}
        if narration and narration.get("error"):
            caveats.append(f"{domain.name}_narrate_unavailable")
    elif not include_opentslm and domain.narrate is not None:
        caveats.append(f"{domain.name}_narrate_skipped")
    timings["narrate"] = int((datetime.utcnow() - t).total_seconds() * 1000)

    # 3. RAG
    t = datetime.utcnow()
    retriever = get_retriever(domain.name)
    queries = domain.derive_queries(features)
    chunks = gather_chunks(retriever, queries, k=6)
    if RAG_OPTIONAL and not chunks:
        caveats.append(f"{domain.name}_rag_unavailable")
    timings["rag"] = int((datetime.utcnow() - t).total_seconds() * 1000)

    # 4. LLM
    t = datetime.utcnow()
    backend = _get_backend(AGENT_BACKEND)
    advice = backend.synthesize(
        domain=domain,
        features=features,
        narration=narration,
        chunks=chunks,
        tone=tone,
    )
    timings["llm"] = int((datetime.utcnow() - t).total_seconds() * 1000)

    # Append engine-level caveats without duplicating ones the model already returned.
    existing_caveats = advice.get("caveats", [])
    for c in caveats:
        if c not in existing_caveats:
            existing_caveats.append(c)
    advice["caveats"] = existing_caveats

    return {
        "domain": domain.name,
        "agent_backend": AGENT_BACKEND,
        "features": features,
        "narration": narration,
        "queries": queries,
        "retrieved_papers": [
            {"paper": c.paper_title, "page": c.page, "snippet": c.text[:240], "score": round(c.score, 4)}
            for c in chunks
        ],
        "advice": advice,
        "latency_ms": timings,
    }


def warmup_retrievers(domain_names: list[str] | None = None) -> dict[str, str]:
    """Eager-load each domain's FAISS index. Returns {domain: error_msg_or_'ok'}."""
    out: dict[str, str] = {}
    names = domain_names or list(DOMAIN_REGISTRY.keys())
    for n in names:
        try:
            get_retriever(n)._ensure_loaded()
            out[n] = "ok"
        except Exception as e:
            out[n] = f"error: {e}"
    return out
