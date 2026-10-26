# Судья: проверка разбора жалоб по КР Минздрава

Судья проверяет черновик ИИ (разбор жалоб пациента) без языковой модели:

1. цитата пациента действительно есть в дневнике (rapidfuzz);
2. медицинский термин следует из слов пациента (NLI, mDeBERTa);
3. термин есть в клинических рекомендациях — сначала в КР по диагнозу пациента, затем в остальных (bge-m3 + BM25 → bge-reranker-v2-m3);
4. в тексте нет препаратов, доз и назначений (реестр ГРЛС, маркеры препаратов в КР);
5. блок «Проверьте перед решением»: беременность, аллергии, ограничения врача, возраст.

Ссылки и цитаты берутся из найденных фрагментов КР — судья не может их выдумать. Код: `app/judge/`.

## Установка

```bash
pip install -r requirements.txt -r requirements-judge.txt
# только CPU (меньше по размеру): pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
```

При первом запуске скачиваются модели (~5 ГБ): `BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3`,
`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`. Для работы без интернета: `HF_HUB_OFFLINE=1`.
Видеокарта NVIDIA используется автоматически, если установлен torch с CUDA.

## Запуск

```bash
python -m app.judge check examples/judge/01_depression_mixed.json      # текст для врача
python -m app.judge check examples/judge/01_depression_mixed.json --json
python -m app.judge search "мышечное напряжение" --icd F41.1           # поиск по КР
python scripts/eval_judge.py -v                                         # примеры против ожидаемого
python -m pytest tests/test_judge.py                                    # тесты логики без моделей
```

## Формат входа

```json
{
  "patient": {
    "age": 32, "sex": "Ж", "diagnosisCode": "F33.1", "diagnosisTitle": "…",
    "currentMedications": ["Эсциталопрам"], "allergies": null,
    "pregnancyStatus": "unknown | no | pregnant | lactation | null",
    "medicationRestrictions": {"удлинение QT": true},
    "complaints": [{"date": "2026-10-20", "text": "башка болит, утром встать не могу"}]
  },
  "draft": {
    "symptoms": [{"term": "снижение энергии", "quote": "утром встать не могу", "date": "2026-10-20"}],
    "possible_match": "ухудшение депрессивного эпизода",
    "to_check": ["как давно болит голова"]
  }
}
```

`draft` — то, что должна вернуть Qwen (задача «разбор жалоб»). Из кода:

```python
from app.judge import JudgeRequest, get_judge, render_text
result = get_judge().verify(JudgeRequest.model_validate(data))
result["status"]              # ok | discard (отклонено больше половины симптомов)
result["feedback_for_model"]  # замечания для одной повторной попытки Qwen
text = render_text(result)    # текст для врача
```

## База КР

10 КР из папки A15, скачанных из API Минздрава (`GetClinrec`) и нарезанных по разделам и тезисам
(рекомендация + УУР/УДД + комментарий): `knowledge/guidelines/chunks.json`, 2428 фрагментов.
Номера страниц сопоставлены с PDF. Пересборка после обновления КР:

```bash
python scripts/build_guidelines.py --pdf-dir путь/к/A15     # скачать и нарезать
python -m app.judge build-index                             # векторы bge-m3 (~30 мин на CPU)
```

## Пороги

Подобраны на примерах из `examples/judge/` (`Thresholds` в `app/judge/verifier.py`):

- найдено в КР — оценка reranker ≥ 0.1: симптомы из КР пациента получили 0.07–0.99, чужие ≤ 0.05;
- термин следует из цитаты — NLI entailment ≥ 0.5: 13/16 верных пар выше, 0/7 ловушек выше.
  NLI почти не выдаёт «противоречие», поэтому она только предупреждает (⚠️), а не отклоняет.
