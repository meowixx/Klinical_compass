from __future__ import annotations

import re
from functools import lru_cache

WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.I)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
SPACE_RE = re.compile(r"[ \t]+")
STOP_WORDS = {
    "без", "более", "быть", "для", "его", "или", "как", "которые", "может",
    "она", "они", "при", "также", "что", "это", "этот", "пациент", "пациента",
}


def normalize(value: str) -> str:
    return SPACE_RE.sub(" ", value.casefold().replace("ё", "е")).strip()


@lru_cache(maxsize=1)
def _morph():
    try:
        import pymorphy3
        return pymorphy3.MorphAnalyzer()
    except (ImportError, OSError):
        return None


def tokens(value: str) -> list[str]:
    words = [word for word in WORD_RE.findall(normalize(value)) if len(word) > 2 and word not in STOP_WORDS]
    morph = _morph()
    return [morph.parse(word)[0].normal_form if morph else word for word in words]


def split_sentences(value: str) -> list[str]:
    return [SPACE_RE.sub(" ", item).strip() for item in SENTENCE_RE.split(value) if item.strip()]
