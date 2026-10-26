from __future__ import annotations

from dataclasses import asdict, dataclass

from .text import normalize, tokens


@dataclass(frozen=True)
class RedFlag:
    code: str
    label: str
    urgency: str


RULES = {
    "suicide": ("Суицидальный риск", "emergency", ("хочу умереть", "покончить с собой", "суицид", "нет смысла жить")),
    "psychosis": ("Признаки психоза", "urgent", ("голоса приказывают", "слышу голоса", "за мной следят", "бред")),
    "mania": ("Возможная мания", "urgent", ("не сплю несколько суток", "не нужна потребность во сне", "мысли скачут")),
    "violence": ("Риск насилия", "emergency", ("хочу убить", "причинить вред", "напасть на")),
    "delirium": ("Нарушение сознания", "emergency", ("спутанность сознания", "не узнает близких", "дезориентация")),
}


def detect_red_flags(text: str, phq9_item9: int | None = None) -> list[dict[str, str]]:
    value = normalize(text)
    term_set = set(tokens(text))
    found: list[RedFlag] = []
    for code, (label, urgency, phrases) in RULES.items():
        hit = any(normalize(phrase) in value for phrase in phrases)
        if not hit:
            hit = any(len(set(tokens(phrase)) & term_set) >= max(2, len(set(tokens(phrase))) - 1) for phrase in phrases)
        if hit:
            found.append(RedFlag(code, label, urgency))
    if phq9_item9 is not None and phq9_item9 > 0 and not any(item.code == "suicide" for item in found):
        found.append(RedFlag("suicide", "Положительный ответ на пункт 9 PHQ-9", "emergency"))
    return [asdict(item) for item in found]
