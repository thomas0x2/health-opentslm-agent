"""CLI: build per-domain FAISS indexes from markdown corpora.

Examples:
  python -m scripts.ingest_papers --domain sleep
  python -m scripts.ingest_papers --all
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest markdown papers into per-domain FAISS indexes.")
    parser.add_argument("--domain", type=str, help="Build index for a single domain (e.g. sleep, cardio).")
    parser.add_argument("--all", action="store_true", help="Build indexes for every domain with a papers/<name>/ directory.")
    parser.add_argument("--papers-root", type=Path, default=None, help="Override papers root (defaults to <repo>/papers).")
    parser.add_argument("--out", type=Path, default=None, help="Override output dir (defaults to <repo>/indexes).")
    args = parser.parse_args()

    from health_pipeline.config import PAPERS_DIR, INDEX_DIR, papers_dir_for
    from health_pipeline.rag.ingest import build_index

    papers_root = args.papers_root or PAPERS_DIR
    out_dir = args.out or INDEX_DIR

    if not args.domain and not args.all:
        parser.error("Provide --domain <name> or --all")

    if args.all:
        names = sorted(p.name for p in papers_root.iterdir() if p.is_dir() and not p.name.startswith("."))
    else:
        names = [args.domain]

    if not names:
        print(f"No domain subdirectories found under {papers_root}.")
        return 1

    overall_ok = True
    for name in names:
        pdir = papers_dir_for(name) if papers_root == PAPERS_DIR else (papers_root / name)
        print(f"\n=== Ingesting domain '{name}' from {pdir} ===")
        try:
            stats = build_index(name, pdir, out_dir)
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
            overall_ok = False
            continue
        print(f"  -> {stats['papers']} papers, {stats['chunks']} chunks (dim={stats['dim']})")
        print(f"  -> {stats['index_path']}")
        print(f"  -> {stats['meta_path']}")
    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())
