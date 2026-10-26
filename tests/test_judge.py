"""Judge logic and guideline splitting, with tiny stand-ins for the three models."""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

from app.judge import JudgeRequest, Judge, render_text
from app.judge.grls import MedicineIndex
from app.judge.knowledge import Knowledge
from app.judge.text import lemmas

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_guidelines  # noqa: E402


class WordEmbedder:
    name = "test"

    def encode(self, texts, **_):
        vectors = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in lemmas(text):
                vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)


class OverlapReranker:
    def score(self, query, passages):
        words = set(lemmas(query))
        return [len(words & set(lemmas(p))) / max(len(words), 1) for p in passages]


class OverlapNLI:
    def scores(self, premise, hypothesis):
        if "суицид" in hypothesis and "суицид" not in premise:
            return {"entailment": 0.05, "neutral": 0.15, "contradiction": 0.8}
        shared = set(lemmas(premise)) & set(lemmas(hypothesis)) - {"пациент"}
        return {"entailment": 0.9, "neutral": 0.05, "contradiction": 0.05} if shared else \
               {"entailment": 0.2, "neutral": 0.7, "contradiction": 0.1}


DOCUMENTS = [
    {"doc_id": "457_3", "title": "Генерализованное тревожное расстройство", "icd": ["F41.1"], "view_url": "u1"},
    {"doc_id": "301_3", "title": "Депрессивный эпизод", "icd": ["F32", "F33"], "view_url": "u2"},
    {"doc_id": "162_3", "title": "Головная боль напряжения", "icd": ["G44.2"], "view_url": "u3"},
]


def chunk(doc_id, number, text, section_type="clinical_picture", kind="text", **extra):
    title = next(d["title"] for d in DOCUMENTS if d["doc_id"] == doc_id)
    return {"id": f"{doc_id}:{number}", "doc_id": doc_id, "doc_title": title, "section": number,
            "section_title": "Клиническая картина", "subsection": None, "section_type": section_type,
            "kind": kind, "parent_id": None, "text": text, "comment": "", "uur": None, "udd": None, "page": 5, **extra}


CHUNKS = [
    chunk("457_3", "1.6", "Основные симптомы: постоянная тревога, беспокойство, мышечное напряжение, раздражительность."),
    chunk("301_3", "1.6", "Сниженное настроение, утрата интересов, снижение энергии и повышенная утомляемость."),
    chunk("162_3", "1.6", "Головная боль сжимающего характера, двусторонняя, давящая."),
    chunk("301_3", "3.1", "Рекомендуется применение сертралина** при депрессивном эпизоде.", "treatment", "recommendation",
          uur="A", udd="1"),
]


@pytest.fixture
def judge():
    knowledge = Knowledge(DOCUMENTS, CHUNKS, WordEmbedder(), OverlapReranker())
    medicines = MedicineIndex([{"name": "СЕРТРАЛИН", "number": "ЛП-1"}, {"name": "АВИАНДР®", "number": "ЛП-2"}],
                              [c["text"] for c in CHUNKS])
    return Judge(knowledge, OverlapNLI(), medicines)


def request(symptoms, complaints, possible_match=None, to_check=(), **patient):
    base = {"age": 40, "sex": "М", "diagnosisCode": "F33.1", "allergies": "нет"}
    return JudgeRequest.model_validate({
        "patient": {**base, **patient, "complaints": [{"date": "2026-10-20", "text": t} for t in complaints]},
        "draft": {"symptoms": [{"term": t, "quote": q} for t, q in symptoms],
                  "possible_match": possible_match, "to_check": list(to_check)},
    })


def test_symptom_with_real_quote_is_linked_to_patient_guideline(judge):
    result = judge.verify(request([("снижение энергии", "утром встать не могу, нет энергии")],
                                  ["Утром встать не могу, нет энергии"]))
    symptom = result["symptoms"][0]
    assert symptom["verdict"] == "supported"
    assert symptom["guideline"]["reference"]["doc_id"] == "301_3"
    assert result["source_ids"] == ["301_3:1.6"]


def test_invented_quote_is_rejected(judge):
    result = judge.verify(request([("бессонница", "не сплю по ночам")], ["Утром встать не могу"]))
    assert result["symptoms"][0]["verdict"] == "rejected"
    assert "нет в дневнике" in result["symptoms"][0]["reasons"][0]
    assert result["feedback_for_model"]


def test_overinterpretation_is_rejected_by_nli(judge):
    result = judge.verify(request([("суицидальные мысли", "думала умру")], ["в метро накрыло, думала умру"]))
    assert result["symptoms"][0]["verdict"] == "rejected"


def test_symptom_from_another_guideline_is_a_warning(judge):
    result = judge.verify(request([("двусторонняя давящая головная боль", "голова давящая, двусторонняя боль")],
                                  ["Голова давящая, двусторонняя боль к вечеру"]))
    symptom = result["symptoms"][0]
    assert symptom["verdict"] == "warning"
    assert symptom["guideline"]["reference"]["doc_id"] == "162_3"
    assert symptom["guideline"]["in_patient_guideline"] is False


def test_medicines_and_doses_are_not_allowed(judge):
    result = judge.verify(request([], ["тревожно"], to_check=["продолжить сертралин 50 мг", "частота приступов"],
                                  possible_match="назначить Авиандр"))
    assert [t["verdict"] for t in result["to_check"]] == ["rejected", "supported"]
    assert result["possible_match"]["verdict"] == "rejected"


def test_attention_notes_for_woman_of_childbearing_age(judge):
    result = judge.verify(request([], ["тревожно"], sex="Ж", age=30, allergies=None,
                                  medicationRestrictions={"удлинение QT": True, "старое": False}))
    kinds = [n["kind"] for n in result["attention"]]
    assert kinds == ["pregnancy", "allergies", "restriction"]
    assert "удлинение QT" in result["attention"][2]["text"]


def test_mostly_invented_draft_is_discarded(judge):
    result = judge.verify(request([("тревога", "тревожно"), ("гнев", "срываюсь"), ("вина", "я виноват")], ["тревожно"]))
    assert result["status"] == "discard"


def test_uncovered_words_are_reported(judge):
    result = judge.verify(request([("снижение энергии", "утром встать не могу")],
                                  ["утром встать не могу, сердце колотится по ночам"]))
    assert [u["text"] for u in result["uncovered"]] == ["сердце колотится по ночам"]


def test_render_text_shows_marks_references_and_rejections(judge):
    result = judge.verify(request([("снижение энергии", "нет энергии"), ("бессонница", "не сплю")], ["нет энергии"],
                                  possible_match="депрессивный эпизод"))
    text = render_text(result)
    assert "✅ снижение энергии — «нет энергии»" in text
    assert "КР 301_3 «Депрессивный эпизод»" in text
    assert "Отклонено проверкой:" in text and "❌ бессонница" in text
    assert "Проверьте перед решением:" in text


def test_documents_for_matches_icd_prefixes(judge):
    assert judge.knowledge.documents_for("F33.1") == ["301_3"]
    assert judge.knowledge.documents_for("F41") == ["457_3"]
    assert judge.knowledge.documents_for("K58") == []


def test_medicine_index_ignores_ordinary_words():
    index = MedicineIndex([{"name": "ВОДА"}, {"name": "ЗОЛОФТ®"}, {"name": "МАГНИЙ"}], ["#магния сульфата**"])
    assert index.find("пью воду, принимаю Золофт и магний") == ["золофт", "магний"]


def test_guideline_split_into_theses_with_levels_and_comment():
    html = (
        "<h2>3.1 Терапия</h2><p>Вводный текст раздела.</p>"
        "<ul><li><p>Пациентам с ГТР <strong>рекомендуется</strong> применение СИОЗС [1].</p></li></ul>"
        "<p><strong>Уровень убедительности рекомендаций А (уровень достоверности доказательств – 1).</strong></p>"
        "<p><strong>Комментарий:</strong> эффект развивается за 2–4 недели.</p>"
        "<ul><li><p><strong>Рекомендовано</strong> следующее:</p></li></ul><p>- светотерапия [3]</p>"
        "<p><strong>УДД – 5, УУР – С.</strong></p>"
        "<p>- ЭСТ [4]</p>"
        "<p><strong>Уровень достоверности доказательств - 2, уровень убедительности рекомендаций - B</strong></p>"
    )
    chunks = build_guidelines.section_chunks(build_guidelines.html_blocks(html))
    kinds = [(c["kind"], c.get("uur"), c.get("udd")) for c in chunks]
    assert kinds == [("text", None, None), ("recommendation", "A", "1"), ("recommendation", "C", "5"),
                     ("recommendation", "B", "2")]
    assert chunks[1]["comment"].startswith("Комментарий")
    assert chunks[0]["subsection"] == "3.1 Терапия"
    assert chunks[3]["text"] == "Рекомендовано следующее:\n- ЭСТ [4]"
