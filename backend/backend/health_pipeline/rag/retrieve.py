"""FAISS-backed paper retrieval. One PaperRetriever instance per domain;
the SentenceTransformer encoder is a module-level singleton shared across
all retrievers to avoid loading the embedding model multiple times."""
from __future__ import annotations
import json
from dataclasses import dataclass
from threading import Lock

from health_pipeline.config import index_paths_for


@dataclass
class Chunk:
    paper_title: str
    page: int
    text: str
    score: float


_encoder = None
_encoder_lock = Lock()


def _get_encoder():
    global _encoder
    if _encoder is not None:
        return _encoder
    with _encoder_lock:
        if _encoder is not None:
            return _encoder
        from sentence_transformers import SentenceTransformer

        from health_pipeline.config import EMBEDDING_MODEL
        _encoder = SentenceTransformer(EMBEDDING_MODEL)
        return _encoder


class PaperRetriever:
    """Loads <name>.faiss + <name>.meta.json from INDEX_DIR. Thread-safe."""

    def __init__(self, domain_name: str):
        self.domain_name = domain_name
        self._lock = Lock()
        self._index = None
        self._meta: list[dict] | None = None
        self._loaded = False
        self._load_error: str | None = None

    def _ensure_loaded(self):
        if self._loaded or self._load_error:
            return
        with self._lock:
            if self._loaded or self._load_error:
                return
            try:
                idx_path, meta_path = index_paths_for(self.domain_name)
                if not idx_path.exists() or not meta_path.exists():
                    raise FileNotFoundError(
                        f"Index for '{self.domain_name}' not found at {idx_path}. "
                        f"Run: python -m scripts.ingest_papers --domain {self.domain_name}"
                    )
                import faiss

                self._index = faiss.read_index(str(idx_path))
                self._meta = json.loads(meta_path.read_text())
                _get_encoder()  # warm shared encoder
                self._loaded = True
            except Exception as e:
                self._load_error = str(e)
                raise

    @property
    def ready(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def retrieve(self, query: str, k: int = 6) -> list[Chunk]:
        self._ensure_loaded()
        emb = _get_encoder().encode([query], normalize_embeddings=True).astype("float32")
        scores, ids = self._index.search(emb, k)
        out: list[Chunk] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0 or idx >= len(self._meta):
                continue
            m = self._meta[idx]
            out.append(
                Chunk(
                    paper_title=m["paper_title"],
                    page=m["page"],
                    text=m["text"],
                    score=float(score),
                )
            )
        return out
