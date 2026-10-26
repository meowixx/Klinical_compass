import json
import os
import re
from pathlib import Path
from typing import Any

import httpx


BASE_DIR = Path(__file__).resolve().parent.parent
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
PARTNER_MEDICATION_PATH = Path(
    os.getenv("PARTNER_MEDICATION_PATH", BASE_DIR / "config" / "partner_medication.json")
)
RUNTIME_PROFILE = BASE_DIR / "config" / "ai_runtime.local.json"


def runtime_settings() -> dict[str, Any]:
    """Read on each request so switching the local adapter requires no API restart."""
    if RUNTIME_PROFILE.exists():
        try:
            profile = json.loads(RUNTIME_PROFILE.read_text(encoding="utf-8"))
            if profile.get("blocked") is True:
                return {"provider": "local_adapter", "model": profile["model"], "blocked": True,
                        "url": "http://127.0.0.1:11435", "headers": {}}
            if profile.get("enabled") is True:
                token = (BASE_DIR / ".run" / "ai-adapter.token").read_text(encoding="ascii").strip()
                return {"provider": "local_adapter", "model": profile["model"],
                        "url": "http://127.0.0.1:11435", "headers": {"Authorization": "Bearer " + token}}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {"provider": "local_adapter", "model": "clinical-compass-qwen3-4b-v6",
                    "url": "http://127.0.0.1:11435", "headers": {}}
    return {"provider": "ollama", "model": OLLAMA_MODEL, "url": OLLAMA_URL, "headers": {}}


TASKS = {
    "summary": "Подготовь краткое резюме динамики пациента для лечащего врача.",
    "changes": "Перечисли клинически значимые изменения показателей без постановки диагноза.",
    "risks": "Перечисли факторы, которые врачу следует проверить в первую очередь.",
    "sources": "Сформулируй, какие официальные источники и сведения нужно проверить врачу.",
    "medication": "Объясни результат формальной проверки карточки препарата. Не меняй статус допуска.",
    "note": "Подготовь черновик записи врача по доступным структурированным данным.",
    "questions": "Составь короткий список вопросов пациенту для следующего контакта.",
}


def ai_status() -> dict[str, Any]:
    runtime = runtime_settings()
    if runtime.get("blocked"):
        return {"provider": runtime["provider"], "model": runtime["model"], "available": False,
                "message": "Дообученная модель не прошла проверку безопасности; используются проверяемые правила"}
    try:
        response = httpx.get(f"{runtime['url']}/api/tags", headers=runtime["headers"], timeout=2.5)
        response.raise_for_status()
        models = [str(item.get("name", "")) for item in response.json().get("models", [])]
        installed = any(name == runtime["model"] or name.startswith(f"{runtime['model']}:") for name in models)
        return {
            "provider": runtime["provider"],
            "model": runtime["model"],
            "available": installed,
            "message": "Дообученная локальная модель готова" if installed and runtime["provider"] == "local_adapter" else ("Локальная модель готова" if installed else f"Модель {runtime['model']} не загружена"),
        }
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return {
            "provider": runtime["provider"],
            "model": runtime["model"],
            "available": False,
            "message": "Локальная модель недоступна; используются проверяемые правила",
        }


def load_partner_medication() -> dict[str, Any] | None:
    if not PARTNER_MEDICATION_PATH.exists():
        return None
    try:
        value = json.loads(PARTNER_MEDICATION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) and value.get("active") else None


def assess_partner_medication(patient_context: dict[str, Any]) -> dict[str, Any]:
    medication = load_partner_medication()
    if not medication:
        return {
            "status": "not_configured",
            "title": "Карточка препарата партнёра не настроена",
            "details": "До загрузки официальной инструкции препарат не включается в рекомендации.",
            "disclosure": "Коммерческое влияние на клинический расчёт отключено.",
        }

    diagnosis_code = str(patient_context.get("diagnosisCode", "")).upper()
    allowed_codes = [str(value).upper() for value in medication.get("indicationDiagnosisCodes", [])]
    indication_matches = any(diagnosis_code.startswith(code) for code in allowed_codes)
    restrictions = patient_context.get("medicationRestrictions") or {}
    active_restrictions = [str(label) for label, active in restrictions.items() if active]
    missing = [
        str(label)
        for field, label in medication.get("requiredData", {}).items()
        if patient_context.get(field) in (None, "", [], {})
        or (isinstance(patient_context.get(field), bool) and not patient_context.get(field))
    ]

    age = patient_context.get("age")
    if age is None:
        missing.append("возраст")
    if age is not None and age <= 18:
        status = "contraindicated"
        details = "Возраст не соответствует настроенным условиям инструкции."
    elif active_restrictions:
        status = "contraindicated"
        details = "Выявлены ограничения: " + ", ".join(active_restrictions) + ". Препарат не предлагается."
    elif not indication_matches:
        status = "not_indicated"
        details = "Диагноз пациента не соответствует настроенным показаниям карточки."
    elif missing:
        status = "requires_data"
        details = "Показание совпадает, но недостаточно данных: " + ", ".join(missing) + "."
    else:
        status = "eligible_for_review"
        details = "Формальные критерии совпали. Врач должен проверить инструкцию, взаимодействия и обследования."

    return {
        "status": status,
        "title": (f"{medication.get('tradeName', 'Препарат')} / {medication.get('inn', 'МНН не указано')}"
                  if status == "eligible_for_review" else "Лекарственное предложение не сформировано"),
        "details": details,
        "registrationNumber": medication.get("registrationNumber", "Не указан"),
        "sourceUrl": medication.get("sourceUrl", ""),
        "disclosure": medication.get(
            "disclosure",
            "Производитель или поставщик препарата является партнёром платформы.",
        ),
    }


def generate_with_qwen(
    kind: str,
    patient_context: dict[str, Any],
    medication_assessment: dict[str, Any],
    fallback: str,
) -> tuple[str, str]:
    runtime = runtime_settings()
    status = ai_status()
    if not status["available"]:
        return fallback, status["message"]

    system = (
        "Ты локальный помощник лечащего врача. Пиши по-русски, кратко и проверяемо. "
        "Не ставь диагноз, не назначай лечение и дозировки, не предлагай изменить терапию, не утверждай причинную связь. "
        "Не добавляй фактов, которых нет во входных данных. "
        "Статус формальной проверки препарата изменять запрещено. "
        "Препарат партнёра упоминай только если его карточка передана во входных данных, "
        "всегда раскрывай партнёрскую связь и оставляй решение врачу."
    )
    if runtime["provider"] == "local_adapter":
        if medication_assessment.get("status") == "eligible_for_review":
            system = (BASE_DIR / "datasets/clinical_compass_qwen_v6/system_prompt.txt").read_text(encoding="utf-8")
        else:
            system += "\nЛекарственное предложение для этого запроса не разрешено. Не называй никаких препаратов, даже в отрицаниях. Выполни только выбранную задачу по данным пациента."
        system += "\nЕсли передан partnerMedicationAssessment, лекарственное предложение возможно только при status=eligible_for_review. Этот статус не заменяет клиническую оценку."
    system += "\nНе более 150 слов. adherence — число приёмов лекарства, не дней. Отсутствие ответа не является подтверждённым приёмом. Учитывай дату записей: старые данные не описывают состояние сегодня."
    prompt = {
        "task": TASKS.get(kind, TASKS["summary"]),
        "patientData": patient_context,
        "partnerMedicationAssessment": medication_assessment if medication_assessment.get("status") == "eligible_for_review" else {"status": medication_assessment.get("status"), "details": medication_assessment.get("details")},
        "requiredFormat": ("От трёх до пяти коротких вопросов пациенту, без ответов и лекарственных предложений." if kind == "questions" else "Короткие разделы: Изменения; Что проверить врачу; Возможное действие; Ограничения."),
    }
    try:
        response = httpx.post(
            f"{runtime['url']}/api/chat",
            headers=runtime["headers"],
            json={
                "model": runtime["model"],
                "stream": False,
                "think": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 700},
            },
            timeout=120,
        )
        response.raise_for_status()
        message = response.json().get("message", {})
        content = str(message.get("content", "")).strip()
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if "</think>" in content:
            content = content.split("</think>", 1)[1].strip()
        if not content and message.get("thinking"):
            return fallback, "Qwen не вернул итоговый текст; использован структурированный расчёт"
        reason = rejected_output(content, medication_assessment)
        if reason:
            return fallback, f"Ответ модели отклонён ({reason}); использован структурированный расчёт"
        if medication_assessment.get("status") == "eligible_for_review" and not re.search(r"авиандр|маритуп[ие]рдин", content, re.I):
            content += "\n\nВозможное действие: врач может рассмотреть Авиандр (маритупирдин) после проверки актуальной инструкции и взаимодействий. Препарат партнёра; окончательное решение принимает врач."
        return (content or fallback), f"Локальная модель {runtime['model']}"
    except (httpx.HTTPError, ValueError, TypeError):
        return fallback, "Qwen временно недоступен; использован структурированный расчёт"


def rejected_output(content: str, assessment: dict[str, Any]) -> str | None:
    """Conservative technical guard; it is not a clinical correctness classifier."""
    lowered = content.casefold().replace("ё", "е")
    if not content:
        return "пустой ответ"
    if re.search(r"авиандр|маритуп[ие]рдин", lowered) and assessment.get("status") != "eligible_for_review":
        return "нет допуска к лекарственному предложению"
    if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:мг|mg|мкг)\b|назначаю|принимайте|увеличьте доз|уменьшите доз|отмените препарат", lowered):
        return "назначение или дозировка"
    if re.search(r"врач (?:уже )?уведомлен|запись (?:уже )?создана|пациент (?:уже )?записан|уведомление (?:уже )?отправлено", lowered):
        return "неподтвержденное действие системы"
    return None
