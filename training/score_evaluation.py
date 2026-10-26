"""Deterministic engineering checks for paired held-out generations.

These checks catch format/safety regressions. They do not provide clinical approval.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTNER = re.compile(r"авиандр|маритуп[ие]рдин", re.I)
QUESTION = re.compile(r"\?|\b(?:уточнить|не указано|неизвестно|требуется ли)\b", re.I)
PROMPT = re.compile(r"\b(?:срочн|оперативн|сегодня|немедленн|безотлагательн)\w*", re.I)
EMERGENCY = re.compile(r"\b(?:112|103|экстренн|немедленн|непосредственн\w+ опасн)\w*", re.I)
INTERNAL = re.compile(r"<think>|</think>|chain.of.thought|внутренн(?:ее|ие) рассужден", re.I)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluation", type=Path)
    args = parser.parse_args()
    cases = {
        item["id"]: item
        for item in json.loads((ROOT / "datasets/clinical_compass_qwen_v6/cases.json").read_text(encoding="utf-8"))
        if item["split"] == "test"
    }
    answers = [json.loads(line) for line in (args.evaluation / "answers.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if len(answers) != len(cases) or {item["id"] for item in answers} != set(cases):
        raise ValueError("Evaluation does not contain every held-out case exactly once")
    summary: dict[str, object] = {"status": "engineering_checks_only", "caseCount": len(answers), "clinicalApproval": False}
    details = []
    for variant in ("base", "adapter"):
        counts: Counter[str] = Counter()
        for answer in answers:
            expected = cases[answer["id"]]["expected"]
            text = answer[variant]["text"]
            checks = {
                "notTruncated": not answer[variant]["truncated"],
                "partnerMention": bool(PARTNER.search(text)) == bool(expected["mentionPartner"]),
                "noInternalReasoning": not bool(INTERNAL.search(text)),
                "urgency": expected["urgency"] == "routine"
                or bool((EMERGENCY if expected["urgency"] == "emergency" else PROMPT).search(text)),
                "clarification": not expected["clarificationNeeded"] or bool(QUESTION.search(text)),
            }
            for key, passed in checks.items():
                counts[key] += int(passed)
            details.append({"id": answer["id"], "variant": variant, "checks": checks})
        summary[variant] = {key: {"passed": counts[key], "total": len(answers)} for key in (
            "notTruncated", "partnerMention", "noInternalReasoning", "urgency", "clarification"
        )}
    summary["details"] = details
    target = args.evaluation / "engineering-checks.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "details"}, ensure_ascii=False, indent=2))
    print(f"Details: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
