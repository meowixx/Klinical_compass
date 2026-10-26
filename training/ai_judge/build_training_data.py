from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "generated")
    args = parser.parse_args()
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    reviewed = [case for case in cases if case.get("clinicianReviewed")]
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "retrieval_queries.jsonl"
    target.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in reviewed), encoding="utf-8")
    print(f"Wrote {len(reviewed)} clinician-reviewed records to {target}")
    if not reviewed:
        print("No records were exported because clinicianReviewed is false for all synthetic cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
