"""Central configuration: paths, model IDs, env-var reads."""
from __future__ import annotations
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = REPO_ROOT / "papers"
INDEX_DIR = REPO_ROOT / "indexes"
HF_CACHE = REPO_ROOT / ".hf_cache"

os.environ.setdefault("HF_HOME", str(HF_CACHE))

AGENT_BACKEND = os.getenv("AGENT_BACKEND", "deepseek").lower()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")

OPENTSLM_ENABLED = os.getenv("OPENTSLM_ENABLED", "0") in ("1", "true", "yes")
OPENTSLM_CHECKPOINT = os.getenv("OPENTSLM_CHECKPOINT", "OpenTSLM/llama-3.2-1b-m4-sp")
RAG_OPTIONAL = os.getenv("RAG_OPTIONAL", "1") in ("1", "true", "yes")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

MAX_HR_DEFAULT = int(os.getenv("MAX_HR_DEFAULT", "185"))
DOMAINS_ENABLED = tuple(
    d.strip()
    for d in os.getenv("DOMAINS_ENABLED", "sleep,cardio,training,nutrition,triage").split(",")
    if d.strip()
)


def papers_dir_for(domain_name: str) -> Path:
    return PAPERS_DIR / domain_name


def index_paths_for(domain_name: str) -> tuple[Path, Path]:
    return INDEX_DIR / f"{domain_name}.faiss", INDEX_DIR / f"{domain_name}.meta.json"
