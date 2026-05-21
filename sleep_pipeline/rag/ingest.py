"""PDF → chunks → embeddings → FAISS index.

Idempotent: rebuilds the index from scratch each run. Intended for a small
corpus (< 200 papers) — exact search with IndexFlatIP is the right choice here.
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


def _extract_chunks(pdf_path: Path) -> list[Chunk]:
    from pypdf import PdfReader  # local import to keep `import sleep_pipeline.rag` cheap

    reader = PdfReader(str(pdf_path))
    paper_title = pdf_path.stem
    chunks: list[Chunk] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        sentences = _split_sentences(text)
        chunks.extend(_pack_chunks(sentences, paper_title, page_idx, str(pdf_path), len(chunks)))
    return chunks


def build_index(papers_dir: Path, out_dir: Path) -> dict:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer

    from sleep_pipeline.config import EMBEDDING_MODEL

    papers_dir = Path(papers_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(papers_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found under {papers_dir}")

    all_chunks: list[Chunk] = []
    for pdf in pdfs:
        print(f"  parsing {pdf.name}")
        all_chunks.extend(_extract_chunks(pdf))
    if not all_chunks:
        raise RuntimeError("PDF parsing produced zero chunks (check file contents)")
    print(f"  total chunks: {len(all_chunks)}")

    model = SentenceTransformer(EMBEDDING_MODEL)
    texts = [c.text for c in all_chunks]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True).astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss.write_index(index, str(out_dir / "papers.faiss"))
    (out_dir / "papers.meta.json").write_text(
        json.dumps([asdict(c) for c in all_chunks], indent=2)
    )

    return {
        "papers": len(pdfs),
        "chunks": len(all_chunks),
        "dim": int(dim),
        "index_path": str(out_dir / "papers.faiss"),
        "meta_path": str(out_dir / "papers.meta.json"),
    }
