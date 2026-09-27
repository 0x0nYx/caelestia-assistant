"""CLI for the retrieval layer: search the offline corpus index.

Usage:
    python3 -m assistant.retrieval.cli search "query text" [-k N] [--json] [--index PATH]
    python3 -m assistant.retrieval.cli stats [--index PATH]

Reads only the prebuilt JSON index; fully offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import DEFAULT_INDEX_PATH
from .search import Searcher


def _format_results(results: List[dict]) -> str:
    if not results:
        return "No corpus document matched. The honest answer is: nothing in the local docs/issues fits."
    lines: List[str] = []
    for i, hit in enumerate(results, start=1):
        lines.append(f"[{i}] {hit['doc_id']} — {hit['title']}  (score {hit['score']})")
        lines.append(f"    source: {hit['source']}")
        lines.append(f"    snippet: {hit['snippet']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m assistant.retrieval.cli",
        description="Offline BM25 search over the caelestia docs/resolved-issues corpus.",
    )
    parser.add_argument("--index", default=str(DEFAULT_INDEX_PATH), help="path to bm25.json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    search_cmd = sub.add_parser("search", help="rank corpus docs for a query")
    search_cmd.add_argument("query", help="query text")
    search_cmd.add_argument("-k", type=int, default=5, help="max results (default 5)")
    search_cmd.add_argument("--json", action="store_true", help="emit JSON instead of text")

    sub.add_parser("stats", help="print index statistics")

    # exponential-build 4.1: the disk-backed bounded-memory index
    di = sub.add_parser("disk-index", help="index a folder tree under a RAM "
                                           "ceiling (external merge sort, "
                                           "measured footprint)")
    di.add_argument("root", help="the folder tree to index")
    di.add_argument("--out", required=True, help="output index directory")
    di.add_argument("--ceiling", type=float, default=16,
                    help="RAM ceiling in MB for index structures (default 16)")
    di.add_argument("--max-files", type=int, default=20000)

    ds = sub.add_parser("disk-search", help="search a disk index "
                                            "(metadata-only in RAM)")
    ds.add_argument("query", help="query text")
    ds.add_argument("-k", type=int, default=5)
    ds.add_argument("--json", action="store_true")
    ds.add_argument("--index-dir", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "disk-index":
        from . import diskindex
        report = diskindex.build_disk_index(args.root, args.out,
                                            ram_ceiling_mb=args.ceiling,
                                            max_files=args.max_files)
        fp = report["footprint"]
        print(f"disk index: {report['n_docs']} docs, {report['n_terms']} "
              f"terms, {fp['runs_spilled']} run(s) spilled")
        print(f"footprint (measured): budget {fp['run_budget_chars']} chars "
              f"({fp['ram_ceiling_mb']} MB ceiling); budget respected: "
              f"{fp['budget_respected_by_construction']}")
        if fp.get("hwm_growth_kb") is not None:
            print(f"process peak RSS growth (VmHWM): {fp['hwm_growth_kb']} kB "
                  f"(within ceiling: {fp['hwm_growth_within_ceiling']})")
        print(fp.get("note", ""))
        return 0
    if args.cmd == "disk-search":
        from . import diskindex
        searcher = diskindex.DiskSearcher(args.index_dir)
        results = searcher.search(args.query, k=args.k)
        if args.json:
            print(json.dumps({"query": args.query, "results": results},
                             ensure_ascii=False, indent=2))
        else:
            if not results:
                print("no match (honest empty answer)")
            for i, hit in enumerate(results, start=1):
                print(f"[{i}] {hit['path']}  (score {hit['score']})")
        return 0

    if not Path(args.index).is_file():
        print(f"error: index not found at {index_path}; run python3 -m assistant.retrieval.build", file=sys.stderr)
        return 2

    searcher = Searcher.from_file(index_path)

    if args.cmd == "stats":
        terms = len(searcher.df)
        tokens = sum(doc.get("dl", 0) for doc in searcher.docs)
        print(f"index: {index_path}")
        print(f"docs: {searcher.n_docs}, unique terms: {terms}, tokens: {tokens}, avgdl: {searcher.avgdl:.1f}")
        print(f"params: k1={searcher.k1}, b={searcher.b}")
        for doc in searcher.docs:
            print(f"  {doc['id']:16s} {doc.get('title', '')}")
        return 0

    results = searcher.search(args.query, k=args.k)
    if args.json:
        print(json.dumps({"query": args.query, "results": results}, ensure_ascii=False, indent=2))
    else:
        print(_format_results(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
