from __future__ import annotations

import argparse
import json
import sys

from .complaints import extract_complaints
from .config import CORPUS_PATH, EMBEDDINGS_PATH, MANIFEST_PATH, SOURCE_CORPUS, manifest, model_path
from .corpus import build_corpus
from .ollama import OllamaError, request
from .red_flags import detect_red_flags
from .retrieval import HybridRetriever, build_embeddings


def doctor() -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("manifest", MANIFEST_PATH.exists(), str(MANIFEST_PATH)))
    checks.append(("source corpus", SOURCE_CORPUS.exists(), str(SOURCE_CORPUS)))
    checks.append(("prepared corpus", CORPUS_PATH.exists(), str(CORPUS_PATH)))
    checks.append(("embeddings", EMBEDDINGS_PATH.exists(), str(EMBEDDINGS_PATH)))
    checks.extend((f"model {name}", model_path(name).exists(), str(model_path(name))) for name in ("reranker", "nli"))
    try:
        tags = request("/api/tags").get("models", [])
        installed = {item.get("name", "").split(":latest")[0] for item in tags}
        for name in manifest()["ollama"].values():
            checks.append((f"Ollama {name}", name in installed or f"{name}:latest" in installed, name))
    except OllamaError as exc:
        checks.append(("Ollama service", False, str(exc)))
    for label, passed, detail in checks:
        print(f"[{'OK' if passed else 'FAIL'}] {label}: {detail}")
    return 0 if all(item[1] for item in checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Clinical Compass AI judge")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build-corpus")
    commands.add_parser("build-index")
    commands.add_parser("doctor")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--doc-id")
    search.add_argument("--limit", type=int, default=3)
    complaints = commands.add_parser("extract-complaints")
    complaints.add_argument("text")
    flags = commands.add_parser("red-flags")
    flags.add_argument("text")
    flags.add_argument("--phq9-item9", type=int)
    args = parser.parse_args()
    if args.command in {"build-corpus", "build-index"}:
        rows = build_corpus()
        print(f"Prepared {len(rows)} chunks at {CORPUS_PATH}")
        if args.command == "build-index":
            print(f"Saved {build_embeddings()} embeddings at {EMBEDDINGS_PATH}")
        return 0
    if args.command == "doctor":
        return doctor()
    if args.command == "search":
        print(json.dumps(HybridRetriever().search(args.query, args.doc_id, args.limit), ensure_ascii=False, indent=2))
    elif args.command == "extract-complaints":
        print(json.dumps(extract_complaints(args.text), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(detect_red_flags(args.text, args.phq9_item9), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
