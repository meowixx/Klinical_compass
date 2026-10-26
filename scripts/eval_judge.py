"""Runs the judge on examples/judge/*.json and compares with the «expected» block of each file.

    python scripts/eval_judge.py                 # all examples
    python scripts/eval_judge.py examples/judge/03_panic_traps.json -v
"""
import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.judge import JudgeRequest, get_judge  # noqa: E402


def compare(result: dict, expected: dict) -> list[tuple[str, bool, str]]:
    """(check, passed, details) for every expectation in the file."""
    checks = []
    symptoms = {s["term"]: s for s in result["symptoms"]}
    for term, allowed in expected.get("symptoms", {}).items():
        s = symptoms.get(term)
        got = s["verdict"] if s else "нет в результате"
        checks.append((f"вердикт «{term}»", got in allowed, f"{got}; ожидалось {'/'.join(allowed)}"
                       + (f"; причины: {'; '.join(s['reasons'])}" if s and s["reasons"] else "")))
    for term, doc_id in expected.get("guideline_doc", {}).items():
        ref = ((symptoms.get(term) or {}).get("guideline") or {}).get("reference")
        got = ref["doc_id"] if ref else "не найдено"
        detail = f"{got} (оценка {ref['score']}, разд. {ref['section']})" if ref else got
        checks.append((f"КР для «{term}»", got == doc_id, f"{detail}; ожидалось {doc_id}"))
    for text in expected.get("to_check_rejected", []):
        item = next((t for t in result["to_check"] if t["text"] == text), None)
        checks.append((f"отклонено «{text}»", bool(item and item["verdict"] == "rejected"), item["verdict"] if item else "нет"))
    kinds = {n["kind"] for n in result["attention"]}
    for kind in expected.get("attention", []):
        checks.append((f"«Проверьте»: {kind}", kind in kinds, ", ".join(sorted(kinds)) or "пусто"))
    if "status" in expected:
        checks.append(("статус", result["status"] == expected["status"], f"{result['status']}; ожидалось {expected['status']}"))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("-v", "--verbose", action="store_true", help="Показывать и пройденные проверки")
    args = parser.parse_args()
    files = args.files or sorted((BASE_DIR / "examples" / "judge").glob("*.json"))

    started = time.time()
    judge = get_judge()
    print(f"Модели загружены за {time.time() - started:.0f} с\n")
    passed = total = 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        started = time.time()
        result = judge.verify(JudgeRequest.model_validate(data))
        checks = compare(result, data.get("expected", {}))
        ok = sum(c[1] for c in checks)
        passed, total = passed + ok, total + len(checks)
        print(f"{'✅' if ok == len(checks) else '❌'} {path.name}: {ok}/{len(checks)} ({time.time() - started:.1f} с)")
        for name, success, details in checks:
            if args.verbose or not success:
                print(f"    {'✓' if success else '✗'} {name}: {details}")
    print(f"\nИтого: {passed}/{total} проверок пройдено")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
