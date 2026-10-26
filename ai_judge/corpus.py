from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .config import CORPUS_PATH, SOURCE_CORPUS
from .text import split_sentences

REFERENCE_HEADING = re.compile(r"^(?:список\s+литературы|литература|references)\b", re.I)
HEADING = re.compile(r"^(?:\d+(?:\.\d+){0,3}\.?\s+|приложение\s+[а-яa-z0-9]+\b)(.{3,180})$", re.I)
LEVEL = re.compile(r"уровень\s+(?:убедительности\s+рекомендаций|достоверности\s+доказательств)\s*[–-]\s*([ABC12345])", re.I)
RECOMMENDATION = re.compile(r"\b(?:рекомендуется|рекомендовано|не\s+рекомендуется|следует)\b", re.I)


def _section_type(section: str) -> str:
    value = section.casefold()
    for key, label in (
        ("диагност", "diagnostics"), ("лечен", "treatment"), ("реабил", "rehabilitation"),
        ("профилакт", "prevention"), ("организац", "care_organization"),
    ):
        if key in value:
            return label
    return "other"


def _pack(sentences: Iterable[str], minimum: int = 420, maximum: int = 1150) -> list[str]:
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and len(current) + len(sentence) + 1 > maximum:
            chunks.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
        if len(current) >= minimum and (RECOMMENDATION.search(current) or len(current) >= maximum * 0.8):
            chunks.append(current)
            current = ""
    if current:
        if chunks and len(current) < 160:
            chunks[-1] = f"{chunks[-1]} {current}"
        else:
            chunks.append(current)
    return chunks


def build_corpus(source: Path = SOURCE_CORPUS, target: Path = CORPUS_PATH) -> list[dict[str, Any]]:
    rows = json.loads(source.read_text(encoding="utf-8"))
    documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        documents[row["doc_id"]].append(row)

    result: list[dict[str, Any]] = []
    for doc_id, doc_rows in sorted(documents.items()):
        stopped = False
        last_page = max(int(item.get("page") or 0) for item in doc_rows)
        for row in sorted(doc_rows, key=lambda item: (int(item.get("page") or 0), item.get("paragraph_id", ""))):
            if stopped:
                continue
            lines = [line.strip() for line in row["content"].splitlines() if line.strip()]
            kept: list[str] = []
            section = row.get("section") or "Без раздела"
            for line in lines:
                if REFERENCE_HEADING.match(line):
                    # The table of contents also names this section. Stop only near the
                    # end of the document, where the actual bibliography begins.
                    if int(row.get("page") or 0) >= last_page * 0.55:
                        stopped = True
                        break
                    continue
                heading = HEADING.match(line)
                if heading and len(line) < 190:
                    section = line
                    continue
                if line.casefold() not in {"оглавление", "содержание"}:
                    kept.append(line)
            for local_index, content in enumerate(_pack(split_sentences("\n".join(kept)))):
                if len(content) < 80:
                    continue
                levels = LEVEL.findall(content)
                result.append({
                    "chunkId": f"{row['paragraph_id']}_c{local_index}",
                    "docId": doc_id,
                    "docTitle": row["doc_title"],
                    "section": section,
                    "sectionType": _section_type(f"{row.get('section', '')} {section}"),
                    "page": row["page"],
                    "url": row["url"],
                    "text": content,
                    "drugs": sorted(set(row.get("detected_drugs") or [])),
                    "evidenceLevels": sorted(set(levels)),
                    "isRecommendation": bool(RECOMMENDATION.search(content)),
                })
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
