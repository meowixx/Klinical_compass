from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_judge.config import CORPUS_PATH
from ai_judge.red_flags import detect_red_flags
from ai_judge.retrieval import HybridRetriever

HERE = Path(__file__).resolve().parent


def main() -> int:
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    retriever = HybridRetriever(CORPUS_PATH)
    retrieval_hits = 0
    expected_flags = found_flags = 0
    details = []
    for case in cases:
        results = retriever.search(case["query"], limit=5)
        retrieval_ok = any(item["docId"] == case["docId"] for item in results)
        retrieval_hits += retrieval_ok
        detected = {item["code"] for item in detect_red_flags(case["redFlagText"])}
        expected = set(case["expectedFlags"])
        expected_flags += len(expected)
        found_flags += len(expected & detected)
        details.append({"id": case["id"], "retrieval": retrieval_ok, "missingFlags": sorted(expected - detected)})
    report = {
        "caseCount": len(cases),
        "retrievalRecallAt5": round(retrieval_hits / len(cases), 3),
        "redFlagRecall": round(found_flags / expected_flags, 3) if expected_flags else 1.0,
        "details": details,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["retrievalRecallAt5"] >= 0.9 and report["redFlagRecall"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
