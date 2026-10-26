"""Grounds AI drafts in Minzdrav clinical guidelines (КР) and the state drug register (ГРЛС).

The checker never generates medical content. Every dose, contraindication or registration it
returns is a verbatim excerpt from the datasets in knowledge_database_RAG, with its source link.
"""
import json
import math
import re
from collections import Counter
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

KB_DIR = Path(__file__).resolve().parent / "knowledge_database_RAG"
GUIDELINES_PATH = KB_DIR / "clinical_guidelines_clean.json"
REGISTRY_PATH = KB_DIR / "Svedeniya_GRLS_127_UTF_8.json"
GRLS_SEARCH_URL = "https://grls.rosminzdrav.ru/GRLS.aspx"

# ICD-10 prefix -> guideline doc_id from the dataset.
DIAGNOSIS_GUIDELINES = (
    ("F41.0", "456_3"),
    ("F41.1", "457_3"),
    ("F43.1", "753_1"),
    ("F31", "675_2"),
    ("F32", "301_3"),
    ("F33", "301_3"),
)
# Class names used by the guidelines themselves, e.g. "СИОЗСН (венлафаксин, дулоксетин)".
DRUG_CLASSES = {
    "СИОЗС": ("флуоксетин", "сертралин", "пароксетин", "эсциталопрам", "циталопрам", "флувоксамин"),
    "СИОЗСН": ("венлафаксин", "дулоксетин"),
    "ТЦА": ("амитриптилин", "имипрамин", "кломипрамин"),
}
STOPWORDS = {
    "этот", "также", "может", "могут", "более", "менее", "после", "перед", "через", "только", "если",
    "или", "для", "при", "как", "что", "чтобы", "его", "ее", "их", "она", "они", "оно", "был", "была",
    "были", "быть", "есть", "нет", "все", "всех", "так", "уже", "еще", "между", "около", "который",
    "которые", "которых", "либо", "пациент", "пациента", "пациенту", "пациентов", "врач", "врача",
    "врачу", "данных", "данные", "случае", "случаях", "рекомендуется", "рекомендовано", "уровень",
}
CONTRA_STRONG = re.compile(r"противопоказ|не долж(?:ен|на|ны) назнача|не следует назнача|не применя|запрещ", re.I)
CONTRA_PATTERN = re.compile(
    CONTRA_STRONG.pattern + r"|не рекомендуется|с осторожностью|необходимо учитывать|повышает риск|"
    r"повышенн\w+ риск|риск развития|удлинени\w+ интервала|синдром\w* отмены|передозиров|взаимодейств",
    re.I,
)
# INN endings; used to keep ordinary words that are also register trade names out of the drug list.
INN_ENDINGS = ("ин", "ам", "ол", "ид", "он", "ат", "ен", "ил", "ан", "ум", "ар", "оз", "ит")
NON_DRUG_WORDS = {"помощь", "потенциал", "кислота", "натрия", "калия", "кальция", "магния", "витамин", "глицин"}
DOSE_PATTERN = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[–-]\s*\d+(?:[.,]\d+)?)?\s*(?:мг|мкг|г|ммоль)(?:\s*/\s*(?:сут|кг|л)\w*)?", re.I)
LEVEL_PATTERN = re.compile(r"Уровень убедительности рекомендаций\s*[–-]\s*([ABC])", re.I)
WORD_PATTERN = re.compile(r"[а-яёa-z]+", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
REFERENCE_PATTERN = re.compile(r"\s*\[[\d,\s–-]+\]")
TRADE_SUFFIXES = ("а", "у", "ом", "е", "ы", "ой")


def normalize(text: str) -> str:
    return text.casefold().replace("ё", "е")


def word_stems(text: str) -> list[str]:
    return [word[:6] for word in WORD_PATTERN.findall(normalize(text)) if len(word) > 3 and word not in STOPWORDS]


def drug_stem(name: str) -> str:
    return name[:-1] if name[-1] in "аяйоеиьы" else name


def clean_quote(text: str, limit: int = 520) -> str:
    text = REFERENCE_PATTERN.sub("", text.replace("**", ""))
    text = re.sub(r"\s+", " ", text).strip(" •−-–,;")
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()]


def parse_date(value: str | None) -> date | None:
    try:
        return datetime.strptime(value or "", "%d.%m.%Y").date()
    except ValueError:
        return None


@lru_cache(maxsize=1)
def guidelines() -> list[dict[str, Any]]:
    rows = json.loads(GUIDELINES_PATH.read_text(encoding="utf-8"))
    for row in rows:
        row["stems"] = Counter(word_stems(row["content"]))
        row["length"] = sum(row["stems"].values()) or 1
        row["normalized"] = normalize(row["content"])
    return rows


@lru_cache(maxsize=1)
def registry() -> list[dict[str, str]]:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    names = {attribute["uid"]: attribute["techName"] for attribute in raw["classifier"]["attributes"]}
    records = []
    for record in raw["data"]["records"]:
        values = {names[item["attributeUid"]]: item["value"] for item in record["attributeValues"] if item["attributeUid"] in names}
        trade_name = values.get("TradeName", "").strip()
        if trade_name:
            values["normalized"] = normalize(re.sub(r"[®™]", "", trade_name)).strip()
            records.append(values)
    return records


@lru_cache(maxsize=1)
def registry_single_names() -> frozenset[str]:
    return frozenset(record["normalized"] for record in registry() if re.fullmatch(r"[а-я]{5,}", record["normalized"]))


@lru_cache(maxsize=1)
def guideline_vocabulary() -> Counter:
    """How many paragraphs use each word; ordinary words are frequent, drug names are not marked as such."""
    return Counter(word for row in guidelines() for word in set(WORD_PATTERN.findall(row["normalized"])))


def base_form(word: str, known: set[str] | frozenset[str]) -> str:
    return next((word[: -len(suffix)] for suffix in TRADE_SUFFIXES if word.endswith(suffix) and word[: -len(suffix)] in known), word)


@lru_cache(maxsize=1)
def drug_lexicon() -> frozenset[str]:
    """INNs named in the guidelines: ЖНВЛП (**) and off-label (#) markers, detected drugs, generic register names."""
    names = registry_single_names()
    vocabulary = guideline_vocabulary()
    known: set[str] = set()
    marked: set[str] = set()
    for row in guidelines():
        known.update(normalize(name) for name in row["detected_drugs"])
        for match in re.finditer(r"(?:^|[\s(#,;:−–-])#?\s*([а-я]{6,})\s*\*\*|#\s*([а-я]{6,})", row["normalized"]):
            marked.add(match.group(1) or match.group(2))
        for word in set(WORD_PATTERN.findall(row["normalized"])):
            if len(word) >= 7 and word in names and word.endswith(INN_ENDINGS):
                known.add(word)
    for word in marked:
        base = base_form(word, names | known)
        if base not in names and base not in known:
            base = next((word[: -len(s)] for s in TRADE_SUFFIXES if word.endswith(s) and word[: -len(s)].endswith(INN_ENDINGS)), word)
        # A PDF line break can split a name ("флу оксетин**"); keep only forms confirmed elsewhere.
        if base in names or base in known or (vocabulary[word] >= 2 and len(base) >= 7 and base.endswith(INN_ENDINGS)):
            known.add(base)
    canonical = {base_form(word, known) for word in known}
    return frozenset(
        word for word in canonical
        if word not in NON_DRUG_WORDS and not word.startswith("кислот") and not word.endswith(("ая", "ой", "ую", "ые", "ых", "ого"))
    )


def stem_pattern(name: str) -> str:
    # Russian transliterations of one INN differ in unstressed и/е ("маритупирдин" / "маритупердин").
    return "".join("[ие]" if char in "ие" else re.escape(char) for char in drug_stem(name))


def drug_regex(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![а-я])(#\s*)?{stem_pattern(name)}[а-я]{{0,4}}(?![а-я])")


def guideline_for_diagnosis(code: str | None) -> str | None:
    code = (code or "").upper()
    return next((doc_id for prefix, doc_id in DIAGNOSIS_GUIDELINES if code.startswith(prefix)), None)


def search_guidelines(query: str, doc_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """BM25 over guideline paragraphs; the patient's own guideline is ranked first on ties."""
    rows = guidelines()
    terms = set(word_stems(query))
    if not terms:
        return []
    average = sum(row["length"] for row in rows) / len(rows)
    frequency = {term: sum(1 for row in rows if term in row["stems"]) for term in terms}
    scored = []
    for row in rows:
        score = 0.0
        for term in terms:
            count = row["stems"].get(term, 0)
            if count:
                idf = math.log(1 + (len(rows) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += idf * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * row["length"] / average))
        if score:
            scored.append((score * (1.3 if doc_id and row["doc_id"] == doc_id else 1.0), row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:limit]]


def citation(row: dict[str, Any], quote: str) -> dict[str, Any]:
    level = LEVEL_PATTERN.search(row["content"])
    return {
        "docId": row["doc_id"],
        "title": row["doc_title"],
        "page": row["page"],
        "url": row["url"],
        "quote": clean_quote(quote),
        "recommendationLevel": level.group(1).upper() if level else None,
    }


def is_quotable(sentence: str) -> bool:
    """Skip table-of-contents lines, headings and quality-criteria checklist items."""
    return len(sentence) >= 60 and not re.match(r"\s*(?:\d+(?:\.\d+)*\.?\s|Выполнено|Приложение)", sentence)


def sentence_match(row: dict[str, Any], terms: set[str]) -> tuple[float, str]:
    """Best-overlapping quotable sentence of a paragraph and the share of terms it covers."""
    best, best_overlap = "", 0.0
    for sentence in split_sentences(row["content"]):
        if not is_quotable(sentence):
            continue
        overlap = len(terms & set(word_stems(sentence))) / (len(terms) or 1)
        if overlap > best_overlap or (overlap == best_overlap and best and "рекоменд" in sentence and "рекоменд" not in best):
            best, best_overlap = sentence, overlap
    return best_overlap, best


def find_drugs(text: str, extra_names: list[str] | None = None) -> list[str]:
    """Drug names mentioned in a draft: guideline INNs, register trade names and configured names."""
    normalized = normalize(text)
    found: dict[int, str] = {}
    for name in sorted({*drug_lexicon(), *(normalize(n) for n in extra_names or [] if n)}, key=len, reverse=True):
        match = drug_regex(name).search(normalized)
        if match and not any(start <= match.start() < start + len(other) for start, other in found.items()):
            found[match.start()] = name
    single_names = registry_single_names()
    vocabulary = guideline_vocabulary()
    for match in re.finditer(r"(?<![А-Яа-яЁё])([А-ЯЁ][А-Яа-яЁё]{4,})(?:®)?", text):
        word = normalize(match.group(1))
        # Ordinary words used across the guidelines ("Помощь") are register trade names too; skip them.
        if vocabulary[word] >= 3 or word in NON_DRUG_WORDS:
            continue
        for candidate in (word, *(word[: -len(suffix)] for suffix in TRADE_SUFFIXES if word.endswith(suffix))):
            if candidate in single_names and match.start() not in found and candidate not in found.values():
                found[match.start()] = candidate
                break
    return [found[position] for position in sorted(found)]


def registry_entries(names: list[str], limit: int = 5) -> dict[str, Any]:
    patterns = [re.compile(rf"(?<![а-я]){stem_pattern(name)}[а-я]{{0,4}}(?![а-я])") for name in names]
    today = date.today()
    entries = []
    for record in registry():
        if not any(pattern.search(record["normalized"]) for pattern in patterns):
            continue
        valid_until = parse_date(record.get("RegistrationEndDate"))
        active = valid_until is None or valid_until >= today
        entries.append({
            "tradeName": record["TradeName"],
            "registrationNumber": record.get("RegistrationCertificateNumber", ""),
            "registeredAt": record.get("RegistrationCertificateDate", ""),
            "validUntil": record.get("RegistrationEndDate") if valid_until else "бессрочно",
            "active": active,
        })
    entries.sort(key=lambda entry: (not entry["active"], entry["tradeName"]))
    active_count = sum(entry["active"] for entry in entries)
    return {
        "status": "active" if active_count else ("expired" if entries else "not_found"),
        "activeCount": active_count,
        "totalCount": len(entries),
        "entries": entries[:limit],
        "searchUrl": GRLS_SEARCH_URL,
    }


def drug_class(name: str) -> str | None:
    return next((label for label, members in DRUG_CLASSES.items() if name in members), None)


ABBREVIATION_LEGEND = re.compile(r"(?:[А-ЯA-Z]{2,}\s*[–-]\s*[а-я][^,;]*[,;.]\s*){2,}")


def guideline_excerpts(names: list[str], pattern: re.Pattern[str], doc_id: str | None, limit: int) -> list[dict[str, Any]]:
    """Sentences mentioning the drug (or its class) that match pattern, own guideline first."""
    drugs = [drug_regex(name) for name in names]
    label = next((drug_class(name) for name in names if drug_class(name)), None)
    class_pattern = re.compile(rf"(?<![А-Яа-я]){label}(?![А-Яа-я])") if label else None
    results: list[tuple[int, int, dict[str, Any]]] = []
    seen = set()
    for row in sorted(guidelines(), key=lambda row: (row["doc_id"] != doc_id, row["doc_id"], row["page"])):
        if not any(drug.search(row["normalized"]) for drug in drugs) and not (class_pattern and class_pattern.search(row["content"])):
            continue
        sentences = split_sentences(row["content"])
        for index, sentence in enumerate(sentences):
            lowered = normalize(sentence)
            by_name = next((match for drug in drugs if (match := drug.search(lowered))), None)
            by_class = class_pattern and class_pattern.search(sentence)
            if not (by_name or by_class) or not pattern.search(sentence):
                continue
            if "Выполнено" in sentence or "Да/Нет" in sentence or ABBREVIATION_LEGEND.search(sentence):
                continue
            # A sentence cut by a PDF line break does not start with a capital letter; keep its beginning.
            starts_mid = not re.match(r"[А-ЯЁ«(]", sentence.lstrip("•−–- #"))
            quote = sentence
            if index and (len(sentence) < 80 or starts_mid):
                previous = sentences[index - 1]
                previous = previous if len(previous) <= 200 else "…" + previous[-200:].split(" ", 1)[-1]
                quote = f"{previous} {sentence}"
            key = clean_quote(quote)
            if key in seen:
                continue
            seen.add(key)
            item = citation(row, quote)
            item["offLabel"] = bool(by_name and by_name.group(1))
            item["appliesTo"] = names[0] if by_name else f"класс {label}"
            strength = 0 if CONTRA_STRONG.search(sentence) or pattern is DOSE_PATTERN else 1
            results.append((strength, 0 if by_name else 1, item))
    results.sort(key=lambda entry: entry[:2])
    return [entry[2] for entry in results[:limit]]


def patient_conflicts(names: list[str], context: dict[str, Any]) -> list[str]:
    """Clash of a drug with this patient's data: duplicate therapy, doctor's restrictions, age."""
    conflicts = []
    drugs = [drug_regex(name) for name in names]
    label = next((drug_class(name) for name in names if drug_class(name)), None)
    same_class = [drug_regex(member) for member in DRUG_CLASSES.get(label, ())]
    for medication in context.get("currentMedications") or []:
        current = normalize(str(medication))
        if any(drug.search(current) for drug in drugs):
            conflicts.append(f"Препарат уже есть в активных назначениях: {medication}.")
        elif any(member.search(current) for member in same_class):
            conflicts.append(f"В активных назначениях уже есть препарат класса {label}: {medication}.")
    for restriction, active in (context.get("medicationRestrictions") or {}).items():
        text = normalize(str(restriction))
        if active and (any(drug.search(text) for drug in drugs) or (label and normalize(label) in text)):
            conflicts.append(f"Врач указал ограничение: «{restriction}».")
    age = context.get("age")
    if isinstance(age, int) and age < 18:
        conflicts.append("Пациенту меньше 18 лет: клинические рекомендации в базе составлены для взрослых.")
    return conflicts


PATIENT_DATA = re.compile(r"\d|самоотч|отчет|отметк|жалоб|жалует|сообща|по данным|при[её]м\w* (?:препарат|лекарств)")


def check_statements(text: str, doc_id: str | None) -> list[dict[str, Any]]:
    """Mark each draft sentence as backed by a guideline sentence, patient data, or unverified."""
    results = []
    for sentence in split_sentences(text):
        shown = sentence.strip(" -•*")
        # Section labels of the draft format ("Что проверить врачу:") are not claims.
        stripped = re.sub(r"^[А-ЯЁ][А-Яа-яЁё ]{2,40}:\s*", "", shown)
        terms = set(word_stems(stripped))
        if len(stripped) >= 12 and PATIENT_DATA.search(normalize(stripped)):
            results.append({"text": shown, "status": "patient_data"})
            continue
        if len(stripped) < 25 or len(terms) < 3:
            continue
        best_row, best_quote, best_score = None, "", 0.0
        for row in search_guidelines(stripped, doc_id, limit=8):
            overlap, quote = sentence_match(row, terms)
            score = overlap + (0.1 if row["doc_id"] == doc_id else 0.0)
            if quote and overlap >= 0.5 and len(terms & set(word_stems(quote))) >= 3 and score > best_score:
                best_row, best_quote, best_score = row, quote, score
        if best_row:
            results.append({"text": shown, "status": "supported", "citation": citation(best_row, best_quote)})
        else:
            results.append({"text": shown, "status": "unverified"})
    return results


def group_drugs(found: list[str], aliases: list[list[str]]) -> list[list[str]]:
    """Merge a trade name with its INN ("Авиандр" + "маритупирдин") into one entry, keeping text order."""
    groups: list[list[str]] = []
    for name in found:
        alias = next((group for group in aliases if any(drug_regex(name).fullmatch(normalize(item)) for item in group)), None)
        names = [normalize(item) for item in alias] if alias else [name]
        if not any(set(names) & set(existing) for existing in groups):
            groups.append(names)
    return groups


def display_name(names: list[str]) -> str:
    return names[0].capitalize() + (f" ({', '.join(names[1:])})" if len(names) > 1 else "")


def verify_draft(text: str, context: dict[str, Any], drug_aliases: list[list[str]] | None = None) -> dict[str, Any]:
    """Child check run on every AI draft before a clinician sees it.

    drug_aliases lists names of one product, e.g. the partner card's trade name and INN.
    """
    aliases = [[item for item in group if item] for group in drug_aliases or [] if any(group)]
    doc_id = guideline_for_diagnosis(context.get("diagnosisCode"))
    own = next((row for row in guidelines() if row["doc_id"] == doc_id), None)
    query_terms = set(word_stems(text))
    citations = []
    for row in search_guidelines(text, doc_id, limit=12):
        _, quote = sentence_match(row, query_terms)
        if quote and len(citations) < 3:
            citations.append(citation(row, quote))
    medications = []
    for names in group_drugs(find_drugs(text, [item for group in aliases for item in group]), aliases):
        medications.append({
            "name": display_name(names),
            "drugClass": next((drug_class(name) for name in names if drug_class(name)), None),
            "registry": registry_entries(names),
            "dosing": guideline_excerpts(names, DOSE_PATTERN, doc_id, limit=3),
            "contraindications": guideline_excerpts(names, CONTRA_PATTERN, doc_id, limit=5),
            "patientConflicts": patient_conflicts(names, context),
            "instructionCheckRequired": True,
        })
    statements = check_statements(text, doc_id)
    warnings = []
    if not doc_id:
        warnings.append("Для кода диагноза пациента нет клинических рекомендаций в базе; ссылки подобраны по тексту черновика.")
    for medication in medications:
        if medication["registry"]["status"] == "not_found":
            warnings.append(f"{medication['name']}: не найден в ГРЛС. Не назначать без проверки регистрации.")
        elif medication["registry"]["status"] == "expired":
            warnings.append(f"{medication['name']}: все найденные регистрационные удостоверения истекли.")
        if not medication["dosing"]:
            warnings.append(f"{medication['name']}: доза в клинических рекомендациях базы не найдена; сверить с инструкцией ГРЛС.")
        off_label = sorted({item["title"] for item in medication["dosing"] if item["offLabel"]})
        if off_label:
            warnings.append(
                f"{medication['name']}: в «{'», «'.join(off_label)}» отмечен знаком # — применение вне инструкции при этом показании."
            )
        warnings.extend(f"{medication['name']}: {conflict}" for conflict in medication["patientConflicts"])
    unverified = sum(item["status"] == "unverified" for item in statements)
    if unverified:
        warnings.append(f"Утверждений без подтверждения в КР: {unverified}. Их нужно проверить вручную.")
    return {
        "checkedAt": datetime.utcnow().isoformat(),
        "guideline": {"docId": own["doc_id"], "title": own["doc_title"], "url": own["url"].split("#", 1)[0]} if own else None,
        "citations": citations,
        "statements": statements,
        "medications": medications,
        "warnings": warnings,
        "limitations": (
            "Проверка сопоставляет текст с базой КР и выгрузкой ГРЛС по совпадению слов и не оценивает клиническую правильность. "
            "Выгрузка ГРЛС содержит только регистрационные данные: дозировки, формы выпуска и противопоказания из инструкции "
            "врач сверяет на сайте ГРЛС по номеру удостоверения."
        ),
    }
