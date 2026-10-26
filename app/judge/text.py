import re
from functools import lru_cache

import pymorphy3

WORD_RE = re.compile(r"[а-яёa-z0-9]+(?:-[а-яёa-z0-9]+)*", re.I)
STOPWORDS = {
    "и", "в", "во", "на", "с", "со", "по", "для", "к", "ко", "от", "до", "из", "о", "об", "у", "за", "при",
    "а", "но", "или", "что", "как", "это", "то", "же", "ли", "бы", "так", "также", "его", "её", "их",
    "который", "этот", "тот", "быть", "мочь", "весь", "свой", "такой", "один", "он", "она", "они",
}

_morph = pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=200_000)
def lemma(word: str) -> str:
    return _morph.parse(word)[0].normal_form.replace("ё", "е")


def is_dictionary_word(word: str) -> bool:
    return _morph.word_is_known(word)


def words(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in WORD_RE.findall(text)]


def lemmas(text: str) -> list[str]:
    return [lemma(w) for w in words(text) if w not in STOPWORDS]


def normalize(text: str) -> str:
    """Comparable form of a quote: lower case, ё→е, punctuation dropped, single spaces."""
    return " ".join(words(text))


def clauses(text: str) -> list[str]:
    """Sentences and comma-separated parts of a diary entry; tiny parts stick to the previous one."""
    parts: list[str] = []
    for sentence in re.split(r"[.!?;\n]+", text):
        for piece in re.split(r",\s*", sentence):
            piece = piece.strip()
            if not piece:
                continue
            if parts and len(words(piece)) < 3:
                parts[-1] = f"{parts[-1]}, {piece}"
            else:
                parts.append(piece)
    return [p for p in parts if len(words(p)) >= 2]
