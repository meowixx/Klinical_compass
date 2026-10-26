from __future__ import annotations

import json
from typing import Any

from .config import manifest
from .ollama import request

SCHEMA = {
    "type": "object",
    "properties": {
        "chiefComplaint": {"type": "string"},
        "symptoms": {"type": "array", "items": {"type": "string"}},
        "duration": {"type": ["string", "null"]},
        "severity": {"type": ["string", "null"]},
        "redFlagPhrases": {"type": "array", "items": {"type": "string"}},
        "missingQuestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["chiefComplaint", "symptoms", "duration", "severity", "redFlagPhrases", "missingQuestions"],
}


def _valid(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and all(key in payload for key in SCHEMA["required"])
        and isinstance(payload["chiefComplaint"], str)
        and all(isinstance(payload[key], list) for key in ("symptoms", "redFlagPhrases", "missingQuestions"))
    )


def extract_complaints(text: str) -> dict[str, Any]:
    prompt = (
        "Извлеки только факты из текста пациента. Не ставь диагноз и не назначай лечение. "
        "Не додумывай отсутствующие данные. Верни JSON по заданной схеме.\n\nТекст пациента:\n" + text
    )
    payload = {
        "model": manifest()["ollama"]["complaintExtractor"],
        "messages": [{"role": "user", "content": prompt}],
        "format": SCHEMA,
        "stream": False,
        "options": {"temperature": 0.1, "seed": 42},
    }
    for _ in range(2):
        response = request("/api/chat", payload)
        try:
            parsed = json.loads(response["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
        if _valid(parsed):
            return parsed
        payload["messages"].append({"role": "assistant", "content": response.get("message", {}).get("content", "")})
        payload["messages"].append({"role": "user", "content": "Исправь ответ: верни строго объект указанной JSON-схемы."})
    return {
        "chiefComplaint": text.strip()[:500], "symptoms": [], "duration": None, "severity": None,
        "redFlagPhrases": [], "missingQuestions": ["Структурирование моделью недоступно; уточните жалобы вручную."],
    }
