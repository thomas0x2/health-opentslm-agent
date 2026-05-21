"""CLI: build the FAISS index from PDFs in --papers-dir."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest PDFs into FAISS index for RAG.")
    parser.add_argument("--papers-dir", type=Path, default=Path("papers"))
    parser.add_argument("--out", type=Path, default=Path("indexes"))
    args = parser.parse_args()

    from sleep_pipeline.rag.ingest import build_index

    stats = build_index(args.papers_dir, args.out)
    print(f"Indexed {stats['papers']} papers, {stats['chunks']} chunks (dim={stats['dim']}).")
    print(f"  -> {stats['index_path']}")
    print(f"  -> {stats['meta_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
