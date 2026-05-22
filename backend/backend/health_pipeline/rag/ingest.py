"""Markdown → chunks → embeddings → FAISS index.

Idempotent: rebuilds the index from scratch each run. Intended for a small
corpus (< 200 papers) — exact search with IndexFlatIP is the right choice here.

Pages: each `## ` (H2) section in the markdown is treated as a "page" so chunks
retain a usable citation. Content before the first H2 lands on page 1.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

CHUNK_CHARS = 800
CHUNK_OVERLAP = 150


@dataclass
class Chunk:
    chunk_id: str
    paper_title: str
    page: int
    text: str
    source_path: str


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _pack_chunks(sentences: list[str], paper_title: str, page: int, source: str, start_idx: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf = ""
    for sent in sentences:
        if len(buf) + len(sent) + 1 <= CHUNK_CHARS:
            buf = f"{buf} {sent}".strip() if buf else sent
        else:
            if buf:
                chunks.append(
                    Chunk(
                        chunk_id=f"{paper_title}__p{page}__c{start_idx + len(chunks)}",
                        paper_title=paper_title,
                        page=page,
                        text=buf,
                        source_path=source,
                    )
                )
            if len(sent) > CHUNK_CHARS:
                for i in range(0, len(sent), CHUNK_CHARS - CHUNK_OVERLAP):
                    chunk_text = sent[i : i + CHUNK_CHARS]
                    chunks.append(
                        Chunk(
                            chunk_id=f"{paper_title}__p{page}__c{start_idx + len(chunks)}",
                            paper_title=paper_title,
                            page=page,
                            text=chunk_text,
                            source_path=source,
                        )
                    )
                buf = ""
            else:
                tail = buf[-CHUNK_OVERLAP:] if buf else ""
                buf = f"{tail} {sent}".strip()
    if buf:
        chunks.append(
            Chunk(
                chunk_id=f"{paper_title}__p{page}__c{start_idx + len(chunks)}",
                paper_title=paper_title,
                page=page,
                text=buf,
                source_path=source,
            )
        )
    return chunks


def _split_markdown_sections(text: str) -> list[str]:
    """Split a markdown doc on H2 (`## `) boundaries. Preamble before the first
    H2 becomes section 1."""
    parts = re.split(r"(?m)^##\s", text)
    return [p.strip() for p in parts if p.strip()]


def _extract_chunks(md_path: Path) -> list[Chunk]:
    raw = md_path.read_text(encoding="utf-8")
    paper_title = md_path.stem
    chunks: list[Chunk] = []
    for page_idx, section in enumerate(_split_markdown_sections(raw), start=1):
        text = re.sub(r"\s+", " ", section).strip()
        if not text:
            continue
        sentences = _split_sentences(text)
        chunks.extend(_pack_chunks(sentences, paper_title, page_idx, str(md_path), len(chunks)))
    return chunks


def build_index(domain_name: str, papers_dir: Path, out_dir: Path) -> dict:
    """Build `<domain_name>.faiss` + `<domain_name>.meta.json` under `out_dir`
    from all `*.md` files in `papers_dir`."""
    import faiss
    from sentence_transformers import SentenceTransformer

    from health_pipeline.config import EMBEDDING_MODEL

    papers_dir = Path(papers_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mds = sorted(papers_dir.glob("*.md"))
    if not mds:
        raise FileNotFoundError(f"No markdown files found under {papers_dir}")

    all_chunks: list[Chunk] = []
    for md in mds:
        print(f"  parsing {md.name}")
        all_chunks.extend(_extract_chunks(md))
    if not all_chunks:
        raise RuntimeError("Markdown parsing produced zero chunks (check file contents)")
    print(f"  total chunks: {len(all_chunks)}")

    model = SentenceTransformer(EMBEDDING_MODEL)
    texts = [c.text for c in all_chunks]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True).astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    idx_path = out_dir / f"{domain_name}.faiss"
    meta_path = out_dir / f"{domain_name}.meta.json"
    faiss.write_index(index, str(idx_path))
    meta_path.write_text(json.dumps([asdict(c) for c in all_chunks], indent=2))

    return {
        "domain": domain_name,
        "papers": len(mds),
        "chunks": len(all_chunks),
        "dim": int(dim),
        "index_path": str(idx_path),
        "meta_path": str(meta_path),
    }
