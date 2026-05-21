"""FAISS-backed paper retrieval used by the agent."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass
class Chunk:
    paper_title: str
    page: int
    text: str
    score: float


class PaperRetriever:
    """Loads the FAISS index + metadata once; .retrieve() is thread-safe."""

    def __init__(self, index_dir: Path):
        self.index_dir = Path(index_dir)
        self._lock = Lock()
        self._index = None
        self._meta: list[dict] | None = None
        self._encoder = None
        self._loaded = False
        self._load_error: str | None = None

    def _ensure_loaded(self):
        if self._loaded or self._load_error:
            return
        with self._lock:
            if self._loaded or self._load_error:
                return
            try:
                idx_path = self.index_dir / "papers.faiss"
                meta_path = self.index_dir / "papers.meta.json"
                if not idx_path.exists() or not meta_path.exists():
                    raise FileNotFoundError(
                        f"Index not found in {self.index_dir}. "
                        "Run: python -m scripts.ingest_papers --papers-dir papers/ --out indexes/"
                    )
                import faiss
                from sentence_transformers import SentenceTransformer
                from sleep_pipeline.config import EMBEDDING_MODEL

                self._index = faiss.read_index(str(idx_path))
                self._meta = json.loads(meta_path.read_text())
                self._encoder = SentenceTransformer(EMBEDDING_MODEL)
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
        emb = self._encoder.encode([query], normalize_embeddings=True).astype("float32")
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
