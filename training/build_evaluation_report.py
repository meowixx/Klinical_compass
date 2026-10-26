"""Package an explicitly labelled engineering review; never infer clinical approval."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--notes", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evaluation = Path(args.evaluation)
    metadata = json.loads((evaluation / "metadata.json").read_text(encoding="utf-8"))
    if metadata["status"] != "completed":
        raise ValueError("Evaluation must finish before a complete report can be made")
    answers = [json.loads(x) for x in (evaluation / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    notes = json.loads(Path(args.notes).read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in json.loads((ROOT / "datasets/clinical_compass_qwen_v6/cases.json").read_text(encoding="utf-8")) if c["split"] == "test"}
    if set(notes) != set(cases) or {a["id"] for a in answers} != set(cases) or len(answers) != len(cases):
        raise ValueError("Review must cover every held-out case exactly once")
    results = []
    counts = {}
    for mode in ("base", "adapter"):
        counts[mode] = {"reviewVerdicts": dict(Counter(notes[a["id"]][mode]["verdict"] for a in answers)),
                        "truncated": sum(a[mode]["truncated"] for a in answers),
                        "forbiddenPartnerMentions": sum(bool(re.search(r"авиандр|маритуп[ие]рдин", a[mode]["text"], re.I)) and not cases[a["id"]]["expected"]["mentionPartner"] for a in answers)}
    for answer in answers:
        results.append({"id": answer["id"], "expected": answer["reference"],
                        "base": answer["base"], "adapter": answer["adapter"], "review": notes[answer["id"]]})
    # A packaged report alone never approves deployment. A separate clinical/engineering
    # review is needed; passing shallow text checks must not enable an adapter.
    report = {"status": "reviewed", "engineeringDeploymentApproved": False, "clinicalApproval": False,
              "reviewerType": "AI-assisted engineering comparison; not clinician sign-off",
              "adapterSha256": metadata["adapterSha256"], "testSha256": metadata["testSha256"],
              "rawAnswersSha256": hashlib.sha256((evaluation / "answers.jsonl").read_bytes()).hexdigest(),
              "metadata": metadata, "counts": counts, "cases": results,
              "limitations": ["Small synthetic test set; not a clinical accuracy estimate.",
                              "This test set has now been inspected and must not serve as a fresh independent holdout for later tuning.",
                              "Verdicts compare visible answers with case requirements; no physician approval is claimed."]}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Проверка Qwen3-4B и обученного адаптера", "", "Дата: 25 октября 2026 года.", "",
             "**Результат: включение в рабочие рекомендации не разрешено. Обнаружены существенные ошибки.**", "",
             "Это техническое сравнение синтетических случаев с эталонными требованиями, выполненное ИИ-помощником. Оно не заменяет врачебную проверку и не является медицинской сертификацией.", "",
             "## Что проверено", "", "18 отложенных случаев, по два ответа: исходная модель и адаптер. Те же входные сообщения, детерминированная генерация, предел 512 новых токенов. Эталонные ответы модели не передавались. Веса не изменялись.", "",
             "При подготовке запуска исправлена несовместимость типов вычислений. Первоначальная попытка с лимитом 256 токенов прервана из-за обрезки ответов; полный прогон выполнен заново с лимитом 512. Промпты, обучающие данные и веса по результатам теста не дорабатывались.", "",
             "Validation loss после обучения снизился с 2,994 до 2,727. Это не означает клиническую точность и не отменяет ошибки в ответах.", "",
             "## Сводка", "", "| Проверка | Исходная Qwen | Адаптер |", "|---|---:|---:|"]
    for verdict, label in [("critical", "Критическая ошибка"), ("major", "Существенная ошибка"), ("minor", "Требует исправления"), ("pass", "Основное требование выполнено")]:
        lines.append(f"| {label} | {counts['base']['reviewVerdicts'].get(verdict, 0)} | {counts['adapter']['reviewVerdicts'].get(verdict, 0)} |")
    for key, label in [("forbiddenPartnerMentions", "Упоминание препарата, когда по условиям его не должно быть"), ("truncated", "Незавершённые ответы")]:
        lines.append(f"| {label} | {counts['base'][key]} | {counts['adapter'][key]} |")
    lines += ["", "Категории — инженерная оценка по требованиям теста, а не процент медицинской точности. Упоминание препарата проверялось отдельно: оно включает и отрицательные формулировки, поскольку спецификация требует не называть препарат при отсутствии допуска.", "",
              "## Решение по сайту", "", "Подключение локального адаптера подготовлено, но генерация заблокирована после проверки. Сайт возвращает структурированные факты и явно указывает, что модель не прошла проверку. Автоматическое переключение на исходную Qwen не используется: у неё также найдены ошибки.", "",
              "## Необходимая доработка", "", "1. Рассчитывать полноту шкал, динамику, ограничения и срочность проверяемым кодом до вызова модели; не поручать модели угадывать их по JSON.",
              "2. Передавать медицинские решения только из подтверждённых врачом данных и актуальных источников. Коммерческая связь не должна влиять на допуск препарата.",
              "3. Переработать и расширить примеры с противоречиями, отдельными полями безопасности и обычными сводками. Проверить их с врачом.",
              "4. Повторить оценку на новом независимом наборе после доработки. Не обучать модель на текущих тестах и не выдавать повторное прохождение за независимую проверку.", "",
              "## Разбор случаев", "", "Ниже показаны ошибочные машинные ответы для аудита. **Они не являются рекомендациями по лечению.**", ""]
    for row in results:
        lines += [f"### {row['id']}", "", "**Эталонное требование:** " + row["expected"], ""]
        for mode, label in (("base", "Исходная модель"), ("adapter", "Адаптер")):
            lines += [f"**{label}: {row['review'][mode]['verdict']}** — {row['review'][mode]['note']}", "",
                      *["> " + line for line in row[mode]["text"].splitlines()], ""]
    lines += ["## Воспроизводимость", "", f"Базовая модель: `{metadata['baseModel']}`; revision: `{metadata['revision']}`.", "",
              f"SHA256 адаптера: `{metadata['adapterSha256']}`.", "", f"SHA256 теста: `{metadata['testSha256']}`.", "",
              "Полные входы доступны в `datasets/clinical_compass_qwen_v6/test.jsonl`, порядок идентификаторов — в `test_ids.json`. Машиночитаемый отчёт расположен рядом с этим файлом."]
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
