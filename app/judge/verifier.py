"""The judge: checks each item of the AI draft against the patient's words and the guidelines.

No language model is involved: references and quotes come from the found guideline
fragments, so the judge cannot invent a source. It marks, removes and explains; it does not
rewrite. A retry with the feedback is up to the caller.
"""
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.ai_service import rejected_output
from app.judge.grls import MedicineIndex
from app.judge.knowledge import Knowledge
from app.judge.schemas import JudgeRequest, Patient
from app.judge.text import clauses, normalize

SYMPTOM_SECTIONS = ("clinical_picture", "diagnosis", "overview", "terms")
NO_MEDICATION = {"status": "not_configured"}  # complaint analysis never proposes a medicine


@dataclass
class Thresholds:
    quote_exact: float = 90      # rapidfuzz partial_ratio: the quote is in the diary
    quote_close: float = 75      # close enough to accept with a warning
    nli_entails: float = 0.5     # the term follows from the patient's words
    nli_contradicts: float = 0.5
    guideline: float = 0.1       # reranker relevance: symptoms of the guideline scored 0.07–0.99, others ≤ 0.05
    discard_share: float = 0.5   # more rejected symptoms than this → the whole draft is unreliable


@dataclass
class Judge:
    knowledge: Knowledge
    nli: object
    medicines: MedicineIndex
    thresholds: Thresholds = field(default_factory=Thresholds)

    # ------------------------------------------------------------------ public

    def verify(self, request: JudgeRequest) -> dict:
        patient, draft = request.patient, request.draft
        own_docs = self.knowledge.documents_for(patient.diagnosisCode)
        symptoms = [self._symptom(s.term, s.quote, s.date, patient, own_docs) for s in draft.symptoms]
        accepted_quotes = [s["quote"] for s in symptoms if s["verdict"] != "rejected" and s["quote"]]
        rejected = [s for s in symptoms if s["verdict"] == "rejected"]
        result = {
            "status": "ok",
            "diagnosis": {"code": patient.diagnosisCode, "title": patient.diagnosisTitle,
                          "guidelines": [self._document(d) for d in own_docs]},
            "symptoms": symptoms,
            "possible_match": self._possible_match(draft.possible_match, own_docs),
            "to_check": [self._to_check(item, patient) for item in draft.to_check],
            "uncovered": self._uncovered(patient, accepted_quotes),
            "attention": self._attention(patient, own_docs),
        }
        if symptoms and len(rejected) / len(symptoms) > self.thresholds.discard_share:
            result["status"] = "discard"
        result["feedback_for_model"] = self._feedback(result)
        result["source_ids"] = sorted({ref["chunk_id"] for ref in self._references(result)})
        return result

    # ------------------------------------------------------------------ symptoms

    def _symptom(self, term: str, quote: str, date: str | None, patient: Patient, own_docs: list[str]) -> dict:
        t = self.thresholds
        item = {"term": term, "quote": quote, "date": date, "verdict": "supported", "reasons": [], "checks": {}}

        clause, quote_score = self._find_quote(quote, patient)
        item["checks"]["quote"] = {"score": round(quote_score), "diary_text": clause}
        if not quote.strip():
            return self._reject(item, "нет цитаты из дневника")
        if quote_score < t.quote_close:
            return self._reject(item, "этих слов нет в дневнике пациента")
        if quote_score < t.quote_exact:
            self._warn(item, "цитата передана неточно")

        problem = self._forbidden(term)
        if problem:
            return self._reject(item, problem)

        # The quote is already confirmed in the diary. This wording separated paraphrases from
        # over-interpretations best on Russian diary slang.
        nli = self.nli.scores(f"Пациент пишет: «{quote}».", f"У пациента есть {term}.")
        item["checks"]["nli"] = {k: round(v, 3) for k, v in nli.items()}
        if nli.get("contradiction", 0) >= t.nli_contradicts:
            return self._reject(item, "термин противоречит словам пациента")
        if nli.get("entailment", 0) < t.nli_entails:
            self._warn(item, "термин не следует из слов пациента напрямую — возможно перетолкование")

        item["guideline"] = self._guideline(term, own_docs, item)
        return item

    def _find_quote(self, quote: str, patient: Patient) -> tuple[str | None, float]:
        """Best diary clause for the quote and how well the quote matches the diary text."""
        target = normalize(quote)
        if not target:
            return None, 0.0
        best_clause, best_score = None, 0.0
        for complaint in patient.complaints:
            score = fuzz.partial_ratio(target, normalize(complaint.text))
            if score > best_score:
                best_score = score
                candidates = clauses(complaint.text) or [complaint.text]
                best_clause = max(candidates, key=lambda c: fuzz.partial_ratio(target, normalize(c)))
        return best_clause, best_score

    def _guideline(self, term: str, own_docs: list[str], item: dict) -> dict:
        threshold = self.thresholds.guideline
        if own_docs:
            hits = self.knowledge.search(term, own_docs, SYMPTOM_SECTIONS)
            if hits and hits[0].score >= threshold:
                return {"found": True, "in_patient_guideline": True, "reference": hits[0].reference()}
        others = [d for d in self.knowledge.documents if d not in own_docs]
        hits = self.knowledge.search(term, others, SYMPTOM_SECTIONS)
        if hits and hits[0].score >= threshold:
            reference = hits[0].reference()
            self._warn(item, f"в КР по диагнозу пациента не найдено; есть в КР «{reference['doc_title']}»"
                       if own_docs else f"найдено в КР «{reference['doc_title']}»")
            return {"found": True, "in_patient_guideline": False, "reference": reference}
        self._warn(item, "в базе КР не найдено")
        return {"found": False, "in_patient_guideline": False, "reference": None}

    # ------------------------------------------------------------------ other draft parts

    def _possible_match(self, text: str | None, own_docs: list[str]) -> dict | None:
        if not text:
            return None
        item = {"text": text, "verdict": "supported", "reasons": []}
        problem = self._forbidden(text)
        if problem:
            return self._reject(item, problem)
        hits = self.knowledge.search(text, None, ("overview", "clinical_picture"), top=1)
        if not hits or hits[0].score < self.thresholds.guideline:
            item["guideline"] = None
            return self._warn(item, "в базе КР не найдено")
        reference = hits[0].reference()
        item["guideline"] = reference
        if own_docs and reference["doc_id"] not in own_docs:
            self._warn(item, f"отличается от установленного диагноза — ближе к КР «{reference['doc_title']}»")
        return item

    def _to_check(self, text: str, patient: Patient) -> dict:
        item = {"text": text, "verdict": "supported", "reasons": []}
        problem = self._forbidden(text)
        return self._reject(item, problem) if problem else item

    def _forbidden(self, text: str) -> str | None:
        """Doses, prescriptions and any medicine name: the complaint analysis must not suggest therapy."""
        reason = rejected_output(text, NO_MEDICATION)
        if reason:
            return reason
        medicines = self.medicines.find(text)
        return f"упомянут препарат ({', '.join(medicines)}) — разбор жалоб не предлагает лечение" if medicines else None

    def _uncovered(self, patient: Patient, quotes: list[str]) -> list[dict]:
        normalized_quotes = [normalize(q) for q in quotes]
        missing = []
        for complaint in patient.complaints:
            for clause in clauses(complaint.text):
                text = normalize(clause)
                covered = any(fuzz.partial_ratio(q, text) >= 80 or fuzz.partial_ratio(text, q) >= 80
                              for q in normalized_quotes if q)
                if not covered:
                    missing.append({"date": complaint.date, "text": clause})
        return missing

    def _attention(self, patient: Patient, own_docs: list[str]) -> list[dict]:
        """«Проверьте перед решением»: shown always, from the patient card and the guidelines."""
        notes = []
        female = (patient.sex or "").upper() in ("Ж", "F")
        if patient.diagnosisCode and not own_docs:
            notes.append({"kind": "no_guideline", "text": f"Для диагноза {patient.diagnosisCode} нет КР в базе"})
        if female and (patient.age is None or 15 <= patient.age <= 50) and patient.pregnancyStatus in (None, "unknown"):
            notes.append({"kind": "pregnancy", "text": "Статус беременности/лактации не указан"})
        if patient.pregnancyStatus in ("pregnant", "lactation"):
            label = "Беременность" if patient.pregnancyStatus == "pregnant" else "Лактация"
            notes.append(self._with_guideline("pregnancy", f"{label}: учитывайте ограничения терапии",
                                              "беременность лактация грудное вскармливание", own_docs))
        if not (patient.allergies or "").strip():
            notes.append({"kind": "allergies", "text": "Аллергоанамнез не заполнен"})
        for restriction, active in patient.medicationRestrictions.items():
            if active:
                notes.append({"kind": "restriction", "text": f"Ограничение, указанное врачом: {restriction}"})
        if patient.age is not None and patient.age < 18:
            notes.append({"kind": "age", "text": "Пациенту меньше 18 лет: проверьте, распространяется ли КР на этот возраст"})
        if patient.age is not None and patient.age >= 65:
            notes.append(self._with_guideline("age", "Пожилой возраст: учитывайте особенности терапии",
                                              "пациенты пожилого возраста особенности терапии", own_docs))
        return notes

    def _with_guideline(self, kind: str, text: str, query: str, own_docs: list[str]) -> dict:
        note = {"kind": kind, "text": text}
        hits = self.knowledge.search(query, own_docs or None, None, top=1) if own_docs else []
        if hits and hits[0].score >= self.thresholds.guideline:
            note["guideline"] = hits[0].reference()
        return note

    # ------------------------------------------------------------------ helpers

    def _document(self, doc_id: str) -> dict:
        doc = self.knowledge.documents[doc_id]
        return {"doc_id": doc_id, "title": doc["title"], "url": doc["view_url"]}

    @staticmethod
    def _reject(item: dict, reason: str) -> dict:
        item["verdict"] = "rejected"
        item["reasons"].append(reason)
        return item

    @staticmethod
    def _warn(item: dict, reason: str) -> dict:
        if item["verdict"] == "supported":
            item["verdict"] = "warning"
        item["reasons"].append(reason)
        return item

    @staticmethod
    def _references(result: dict) -> list[dict]:
        refs = [s["guideline"]["reference"] for s in result["symptoms"] if s.get("guideline", {}).get("reference")]
        if result["possible_match"] and result["possible_match"].get("guideline"):
            refs.append(result["possible_match"]["guideline"])
        refs += [n["guideline"] for n in result["attention"] if n.get("guideline")]
        return refs

    @staticmethod
    def _feedback(result: dict) -> list[str]:
        """Messages for one retry of the model; only problems the model can fix."""
        messages = []
        for s in result["symptoms"]:
            if s["verdict"] == "rejected":
                messages.append(f"Симптом «{s['term']}» (цитата «{s['quote']}»): {'; '.join(s['reasons'])}. Исправь или удали.")
            elif any("перетолкование" in r or "неточно" in r for r in s["reasons"]):
                messages.append(f"Симптом «{s['term']}»: проверь, что он прямо следует из слов «{s['quote']}», и цитируй дословно.")
        for part in [result["possible_match"]] + result["to_check"]:
            if part and part["verdict"] == "rejected":
                messages.append(f"«{part['text']}»: {'; '.join(part['reasons'])}. Удали.")
        if result["uncovered"]:
            missed = "; ".join(f"«{u['text']}»" for u in result["uncovered"][:5])
            messages.append(f"Не разобраны слова пациента: {missed}.")
        return messages
