"""Medicine names from the State Register (ГРЛС) and the guidelines, to spot drugs in AI text.

The register contains names, registration numbers and dates only — no indications or
contraindications — so it is used to recognise a medicine and show its registration.
"""
import json
import re
from pathlib import Path

from app.judge.text import is_dictionary_word, lemma, words

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GRLS_PATH = BASE_DIR / "knowledge" / "grls" / "Svedeniya_GRLS_127_UTF_8.json"
FIELDS = {
    "6ae16349-4a5c-481e-bb88-734da123bd9a": "number",
    "ea196ca5-df83-4c39-8729-5508cad2bc64": "registered",
    "60a8f917-0695-43ad-aa92-ae484fdb9368": "valid_until",
    "ef746010-cee3-407f-a6be-7cb1e448b134": "name",
}
# Drugs are marked in guideline texts: «вальпроевой кислоты**», «#хлорпромазина».
GUIDELINE_DRUG_RE = re.compile(r"#?([А-Яа-яЁё][а-яё-]{3,})(?:\*\*|\s*\*\*)|#([А-Яа-яЁё][а-яё-]{3,})")


def base_name(trade_name: str) -> str:
    cleaned = re.sub(r"[®™\"«»()]", " ", trade_name.lower().replace("ё", "е"))
    first = cleaned.split()[0] if cleaned.split() else ""
    return first.split("-")[0]


class MedicineIndex:
    def __init__(self, records: list[dict], guideline_texts: list[str]):
        self.records: dict[str, list[dict]] = {}
        for record in records:
            name = base_name(record.get("name", ""))
            if len(name) >= 4:
                self.records.setdefault(name, []).append(record)
        guideline_drugs = set()
        for text in guideline_texts:
            for match in GUIDELINE_DRUG_RE.finditer(text):
                word = (match.group(1) or match.group(2)).lower().replace("ё", "е")
                guideline_drugs.update({word, lemma(word)})
        # A register name that is an ordinary word («вода», «магний») counts only if guidelines use it as a drug.
        self.names = {n for n in self.records if not is_dictionary_word(n) or n in guideline_drugs} | guideline_drugs

    @classmethod
    def load(cls, guideline_texts: list[str], path: Path = GRLS_PATH) -> "MedicineIndex":
        data = json.loads(path.read_text(encoding="utf-8"))["data"]["records"]
        records = [{FIELDS[v["attributeUid"]]: v["value"] for v in r["attributeValues"] if v["attributeUid"] in FIELDS}
                   for r in data]
        return cls(records, guideline_texts)

    def find(self, text: str) -> list[str]:
        """Medicine names mentioned in the text, as written."""
        found = []
        for word in words(text):
            base = word.split("-")[0]
            if base in self.names or lemma(base) in self.names:
                if word not in found:
                    found.append(word)
        return found

    def registration(self, name: str) -> list[dict]:
        base = base_name(name)
        return self.records.get(base) or self.records.get(lemma(base), [])

    def same_medicine(self, mentioned: str, prescribed: list[str]) -> bool:
        target = {base_name(mentioned), lemma(base_name(mentioned))}
        return any({base_name(p), lemma(base_name(p))} & target for p in prescribed)
