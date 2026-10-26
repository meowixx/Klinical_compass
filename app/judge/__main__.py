"""Command line for the judge.

    python -m app.judge build-index                  # after scripts/build_guidelines.py
    python -m app.judge check examples/judge/01_depression.json [--json]
    python -m app.judge search "снижение энергии" --icd F33
"""
import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog="python -m app.judge", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build-index", help="Посчитать векторы фрагментов КР")
    check = commands.add_parser("check", help="Проверить черновик ИИ из JSON-файла")
    check.add_argument("files", nargs="+", type=Path)
    check.add_argument("--json", action="store_true", help="Вывести полный результат в JSON")
    search = commands.add_parser("search", help="Поиск по КР")
    search.add_argument("query")
    search.add_argument("--icd", help="Код МКБ пациента: искать только в его КР")
    search.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    started = time.time()
    if args.command == "build-index":
        from app.judge.knowledge import Knowledge
        from app.judge.models import Embedder

        count = Knowledge.build_index(Embedder())
        print(f"Индекс построен: {count} фрагментов, {time.time() - started:.0f} с")
        return 0

    from app.judge import JudgeRequest, get_judge, render_text

    judge = get_judge()
    print(f"[модели загружены за {time.time() - started:.0f} с]", file=sys.stderr)
    if args.command == "search":
        docs = judge.knowledge.documents_for(args.icd) if args.icd else None
        for hit in judge.knowledge.search(args.query, docs, top=args.top):
            ref = hit.reference()
            print(f"{ref['score']:.3f}  {ref['chunk_id']}  разд. {ref['section']} {ref['section_title']}  стр. {ref['page']}")
            print(f"       {' '.join(ref['text'].split())[:200]}")
        return 0

    for path in args.files:
        started = time.time()
        request = JudgeRequest.model_validate_json(path.read_text(encoding="utf-8"))
        result = judge.verify(request)
        print(f"===== {path.name} ({time.time() - started:.1f} с) =====")
        print(json.dumps(result, ensure_ascii=False, indent=1) if args.json else render_text(result))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
