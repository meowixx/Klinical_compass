import json

from ai_judge.corpus import build_corpus
from ai_judge.judge import quote_similarity
from ai_judge.red_flags import detect_red_flags
from ai_judge.text import normalize, tokens


def test_text_normalization_and_tokens():
    assert normalize("  Ёлка   И ТРЕВОГА ") == "елка и тревога"
    assert "тревога" in tokens("Сильная тревога")


def test_red_flags_include_phq9_and_phrase():
    assert detect_red_flags("Я хочу умереть")[0]["code"] == "suicide"
    assert detect_red_flags("нет жалоб", phq9_item9=1)[0]["urgency"] == "emergency"


def test_quote_similarity_detects_exact_and_fake():
    source = "Пациенту рекомендуется регулярное наблюдение лечащего врача."
    assert quote_similarity(source, source) == 100
    assert quote_similarity("Назначить выдуманный препарат", source) < 70


def test_corpus_builder_removes_references(tmp_path):
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text(json.dumps([{
        "doc_id": "1", "doc_title": "КР", "section": "Лечение", "page": 5,
        "paragraph_id": "p5", "url": "https://example.test", "detected_drugs": [],
        "content": "2. Лечение\nРекомендуется наблюдение врача. " * 8 + "\nСписок литературы\nФиктивный источник",
    }], ensure_ascii=False), encoding="utf-8")
    rows = build_corpus(source, target)
    assert rows and all("Фиктивный" not in row["text"] for row in rows)
    assert rows[0]["sectionType"] == "treatment"
