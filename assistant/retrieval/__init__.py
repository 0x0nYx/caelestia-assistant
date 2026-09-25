"""Layer 2: local retrieval over the repo's own docs and resolved issues.

When the deterministic rules (Layer 1) do not match, the assistant searches
this corpus for the closest real past resolution and returns it with a clear
banner: these are pointers, not verified diagnoses.

Everything here is offline, stdlib-only, and index-driven at runtime: the
corpus markdown is parsed only by the offline build step
(`python3 -m assistant.retrieval.build`); search reads index/bm25.json only.
"""

from pathlib import Path

RETRIEVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = RETRIEVAL_DIR / "corpus"
DEFAULT_INDEX_PATH = RETRIEVAL_DIR / "index" / "bm25.json"

__all__ = ["CORPUS_DIR", "DEFAULT_INDEX_PATH", "RETRIEVAL_DIR"]
