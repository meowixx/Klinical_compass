import hashlib
import json
import os
import secrets
import ssl
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppointmentInvitation,
    ClinicalAlert,
    DailyCheckin,
    LegalDocumentVersion,
    MaxConsent,
    MaxLinkCode,
    MaxProcessedUpdate,
    MaxUserBinding,
    PatientMessage,
    PatientProfile,
    QuestionnaireAssignment,
    QuestionnaireResponse,
    QuestionnaireVersion,
    User,
)
from app.questionnaires import calculate_score, json_load, matched_alerts, validate_answers

MAX_API_BASE = "https://platform-api2.max.ru"
MAX_TOKEN_PATH = Path(os.getenv("MAX_TOKEN_PATH", Path(__file__).resolve().parent.parent / "BotMax" / "MaxAPI.txt"))
MAX_CERT_DIR = Path(__file__).resolve().parent / "certs"


def max_ssl_context() -> ssl.SSLContext:
    """Use standard trust plus the official Russian Ministry CA required by MAX."""
    context = ssl.create_default_context()
    for certificate in (
        MAX_CERT_DIR / "russian_trusted_root_ca.pem",
        MAX_CERT_DIR / "russian_trusted_sub_ca.pem",
    ):
        if not certificate.is_file():
            raise RuntimeError(f"Не найден сертификат MAX: {certificate.name}")
        context.load_verify_locations(cafile=str(certificate))
    return context


def read_max_token() -> str:
    """Read the MAX token only from the user-designated local file."""
    if not MAX_TOKEN_PATH.is_file():
        raise RuntimeError(f"Файл токена MAX не найден: {MAX_TOKEN_PATH}")
    lines = [line.strip() for line in MAX_TOKEN_PATH.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise RuntimeError("Файл токена MAX пуст")
    value = lines[0].split("=", 1)[1].strip() if "=" in lines[0] else lines[0]
    if not value:
        raise RuntimeError("В файле MAX не найден API-ключ")
    return value


def max_api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    token = read_max_token()
    with httpx.Client(timeout=timeout, verify=max_ssl_context()) as client:
        response = client.request(
            method,
            f"{MAX_API_BASE}{path}",
            params=params,
            json=body,
            headers={"Authorization": token, "Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"MAX API вернул ошибку HTTP {response.status_code}")
    return response.json() if response.content else {}


def keyboard(rows: list[list[dict[str, str]]]) -> list[dict[str, Any]]:
    return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]


def callback_button(text: str, payload: str) -> dict[str, str]:
    return {"type": "callback", "text": text, "payload": payload}


def link_button(text: str, url: str) -> dict[str, str]:
    return {"type": "link", "text": text, "url": url}


def send_message(max_user_id: str, text: str, rows: list[list[dict[str, str]]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"text": text[:4000], "notify": True}
    if rows:
        body["attachments"] = keyboard(rows)
    return max_api_request("POST", "/messages", params={"user_id": max_user_id}, body=body)


def send_long_message(max_user_id: str, text: str, rows: list[list[dict[str, str]]] | None = None) -> None:
    """Send every part of a long legal text; attach actions only to the final part."""
    remaining = text.strip()
    parts: list[str] = []
    while len(remaining) > 3800:
        split_at = remaining.rfind("\n", 0, 3800)
        if split_at < 1800:
            split_at = 3800
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    parts.append(remaining)
    for index, part in enumerate(parts):
        prefix = f"Часть {index + 1} из {len(parts)}\n\n" if len(parts) > 1 else ""
        send_message(max_user_id, prefix + part, rows if index == len(parts) - 1 else None)


def answer_callback(callback_id: str, notification: str) -> None:
    max_api_request("POST", "/answers", params={"callback_id": callback_id}, body={"notification": notification[:200]})


def hash_link_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def link_code_candidates(text: str) -> list[str]:
    code = text.strip()
    return [code] if code else []


def create_link_code(db: Session, patient_id: str, created_by_user_id: str, expires_in_minutes: int) -> str:
    now = datetime.utcnow()
    for previous in db.scalars(
        select(MaxLinkCode).where(
            MaxLinkCode.patient_id == patient_id,
            MaxLinkCode.used_at.is_(None),
            MaxLinkCode.expires_at > now,
        )
    ):
        previous.used_at = now
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    code = "".join(secrets.choice(alphabet) for _ in range(12))
    db.add(
        MaxLinkCode(
            patient_id=patient_id,
            code_hash=hash_link_code(code),
            expires_at=now + timedelta(minutes=expires_in_minutes),
            created_by_user_id=created_by_user_id,
        )
    )
    return code


def active_legal_documents(db: Session) -> list[LegalDocumentVersion]:
    return db.scalars(
        select(LegalDocumentVersion)
        .where(LegalDocumentVersion.is_active.is_(True))
        .order_by(LegalDocumentVersion.kind, LegalDocumentVersion.published_at)
    ).all()


def pending_legal_document(db: Session, binding: MaxUserBinding) -> LegalDocumentVersion | None:
    accepted = set(
        db.scalars(
            select(MaxConsent.legal_document_id).where(MaxConsent.binding_id == binding.id, MaxConsent.revoked_at.is_(None))
        ).all()
    )
    for document in active_legal_documents(db):
        if document.id in accepted:
            continue
        if not document.requires_reconsent:
            prior = db.scalar(
                select(MaxConsent)
                .join(LegalDocumentVersion, MaxConsent.legal_document_id == LegalDocumentVersion.id)
                .where(
                    MaxConsent.binding_id == binding.id,
                    MaxConsent.revoked_at.is_(None),
                    LegalDocumentVersion.kind == document.kind,
                )
            )
            if prior:
                continue
        return document
    return None


def request_next_consent(db: Session, binding: MaxUserBinding) -> None:
    if not active_legal_documents(db):
        # Repair installations created before legal document versioning was added.
        # Import locally to keep application startup dependencies one-way.
        from app.seed import seed_legal_documents

        seed_legal_documents(db)
        db.flush()
    if not active_legal_documents(db):
        binding.status = "pending_legal_setup"
        binding.updated_at = datetime.utcnow()
        send_message(
            binding.max_user_id,
            "Не удалось подготовить согласия. Повторите попытку позже или обратитесь в клинику.",
        )
        return
    document = pending_legal_document(db, binding)
    if not document:
        binding.status = "active"
        binding.updated_at = datetime.utcnow()
        send_main_menu(db, binding, "Согласия приняты. Теперь можно отвечать на вопросы врача.")
        return
    binding.status = "pending_consent"
    binding.updated_at = datetime.utcnow()
    text = f"{document.title}\n\n{document.content}\n\nВерсия: {document.version}"
    send_long_message(
        binding.max_user_id,
        text,
        [[callback_button("Принимаю", f"consent:accept:{document.id}")], [callback_button("Не принимаю", f"consent:decline:{document.id}")]],
    )


def send_main_menu(db: Session, binding: MaxUserBinding, prefix: str = "") -> None:
    assignments = db.scalars(
        select(QuestionnaireAssignment)
        .where(QuestionnaireAssignment.patient_id == binding.patient_id, QuestionnaireAssignment.status == "assigned")
        .order_by(QuestionnaireAssignment.due_at)
    ).all()
    rows: list[list[dict[str, str]]] = []
    for item in assignments[:8]:
        rows.append([callback_button(f"Опрос: {item.template}", f"assignment:start:{item.id}")])
    rows.append([callback_button("Мой профиль", "profile:show")])
    rows.append([callback_button("Написать лечащему врачу", "state:message")])
    text = (prefix + "\n\n" if prefix else "") + (
        "Выберите назначенный опрос или передайте лечащему врачу сообщение о своём состоянии. "
        "Медицинская карточка, история и результаты доступны только на сайте."
    )
    send_message(binding.max_user_id, text, rows)


def question_prompt(question: dict[str, Any], assignment_id: str, index: int, total: int) -> tuple[str, list[list[dict[str, str]]] | None]:
    text = f"Вопрос {index + 1} из {total}\n\n{question.get('text', 'Вопрос')}"
    options = question.get("options", [])
    if question.get("type") == "single" and options:
        return text, [[callback_button(option.get("label", option.get("value", "Ответ")), f"answer:{assignment_id}:{index}:{option_index}")] for option_index, option in enumerate(options)]
    if question.get("type") == "multiple":
        labels = ", ".join(option.get("label", option.get("value", "")) for option in options)
        return text + f"\n\nНапишите один или несколько вариантов через запятую: {labels}", None
    if question.get("type") == "number":
        minimum = question.get("min")
        maximum = question.get("max")
        if isinstance(minimum, int) and isinstance(maximum, int) and maximum - minimum <= 10:
            buttons = [
                callback_button(str(value), f"number:{assignment_id}:{index}:{value}")
                for value in range(minimum, maximum + 1)
            ]
            rows = [buttons[position:position + 4] for position in range(0, len(buttons), 4)]
            return text + f"\n\nВыберите оценку от {minimum} до {maximum}.", rows
        limits = ""
        if question.get("min") is not None or question.get("max") is not None:
            limits = f" Допустимый диапазон: {question.get('min', '—')}–{question.get('max', '—')}."
        return text + "\n\nОтправьте число." + limits, None
    return text + "\n\nОтправьте ответ сообщением.", None


def send_current_question(db: Session, binding: MaxUserBinding) -> None:
    assignment = db.get(QuestionnaireAssignment, binding.active_assignment_id)
    if not assignment or assignment.patient_id != binding.patient_id or not assignment.version_id:
        binding.active_assignment_id = None
        binding.active_question_index = 0
        binding.active_answers_json = "{}"
        send_main_menu(db, binding, "Назначение больше недоступно.")
        return
    version = db.get(QuestionnaireVersion, assignment.version_id)
    questions = json_load(version.questions_json if version else "[]", [])
    if not version or binding.active_question_index >= len(questions):
        complete_assignment(db, binding, assignment, version)
        return
    text, rows = question_prompt(questions[binding.active_question_index], assignment.id, binding.active_question_index, len(questions))
    send_message(binding.max_user_id, text, rows)


def next_due_at(assignment: QuestionnaireAssignment) -> datetime | None:
    days = 1 if assignment.schedule_type == "daily" else 7 if assignment.schedule_type == "weekly" else assignment.interval_days if assignment.schedule_type == "interval" else None
    if not days or days < 1:
        return None
    step = timedelta(days=days)
    due = assignment.due_at + step
    now = datetime.utcnow()
    if due <= now:
        due += step * ((now - due) // step + 1)
    return due


def complete_assignment(db: Session, binding: MaxUserBinding, assignment: QuestionnaireAssignment, version: QuestionnaireVersion | None) -> None:
    if not version:
        raise HTTPException(status_code=422, detail="Версия опросника не найдена")
    answers = json_load(binding.active_answers_json, {})
    validate_answers(version, answers, complete=True)
    score = calculate_score(version, answers)
    previous = db.scalar(
        select(QuestionnaireResponse)
        .where(QuestionnaireResponse.patient_id == assignment.patient_id, QuestionnaireResponse.version_id == version.id)
        .order_by(QuestionnaireResponse.completed_at.desc())
    )
    response = QuestionnaireResponse(
        patient_id=assignment.patient_id,
        template=assignment.template,
        source_version=version.version,
        completed_at=datetime.utcnow(),
        score=round(score) if score is not None else None,
        previous_score=previous.score if previous else None,
        status="completed",
        assignment_id=assignment.id,
        version_id=version.id,
        answers_json=json.dumps(answers, ensure_ascii=False),
        source_event_id=f"max:{binding.id}:{assignment.id}:{datetime.utcnow().isoformat()}",
    )
    db.add(response)
    patient = db.get(PatientProfile, assignment.patient_id)
    if version.id == "version-daily-checkin-1":
        sleep_hours = answers.get("sleep")
        db.add(
            DailyCheckin(
                patient_id=assignment.patient_id,
                reported_at=response.completed_at,
                anxiety=float(answers["anxiety"]) if answers.get("anxiety") is not None else None,
                mood=float(answers["wellbeing"]) if answers.get("wellbeing") is not None else None,
                sleep_minutes=round(float(sleep_hours) * 60) if sleep_hours is not None else None,
                new_symptoms=str(answers.get("changes") or "")[:2000] or None,
                requested_contact=answers.get("contact") == "yes",
                source="max_bot",
                completeness=1.0,
            )
        )
    if patient:
        patient.last_contact = response.completed_at
        for alert_data in matched_alerts(version, answers, score):
            db.add(
                ClinicalAlert(
                    patient_id=patient.id,
                    responsible_doctor_id=patient.doctor_id,
                    level=alert_data["level"],
                    reason=alert_data["reason"],
                    source=f"Ответы MAX, опросник «{assignment.template}», {response.completed_at:%d.%m.%Y %H:%M}. Требует оценки лечащим врачом.",
                )
            )
    following = next_due_at(assignment)
    if following and (not assignment.end_at or following <= assignment.end_at):
        assignment.due_at = following
        assignment.status = "assigned"
        assignment.last_sent_at = None
        assignment.reminder_sent_at = None
    else:
        assignment.status = "completed"
    binding.active_assignment_id = None
    binding.active_question_index = 0
    binding.active_answers_json = "{}"
    binding.updated_at = datetime.utcnow()
    db.flush()
    send_main_menu(db, binding, "Ответы сохранены и переданы лечащему врачу.")


def record_answer(db: Session, binding: MaxUserBinding, raw_value: Any) -> None:
    assignment = db.get(QuestionnaireAssignment, binding.active_assignment_id)
    version = db.get(QuestionnaireVersion, assignment.version_id) if assignment and assignment.version_id else None
    questions = json_load(version.questions_json if version else "[]", [])
    if not assignment or not version or binding.active_question_index >= len(questions):
        send_current_question(db, binding)
        return
    question = questions[binding.active_question_index]
    value: Any = raw_value
    if question.get("type") == "number":
        try:
            value = float(str(raw_value).replace(",", "."))
            if value.is_integer():
                value = int(value)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Отправьте число") from error
    elif question.get("type") == "multiple" and isinstance(raw_value, str):
        labels = {option.get("label", "").lower(): option.get("value") for option in question.get("options", [])}
        values = []
        for part in (item.strip().lower() for item in raw_value.split(",")):
            values.append(labels.get(part, part))
        value = values
    answers = json_load(binding.active_answers_json, {})
    answers[question["id"]] = value
    validate_answers(version, answers, complete=False)
    binding.active_answers_json = json.dumps(answers, ensure_ascii=False)
    binding.active_question_index += 1
    binding.updated_at = datetime.utcnow()
    db.flush()
    send_current_question(db, binding)


def update_identity(update: dict[str, Any]) -> tuple[str | None, str | None]:
    message = update.get("message") or {}
    user = update.get("user") or update.get("callback", {}).get("user") or message.get("sender") or {}
    recipient = message.get("recipient") or {}
    user_id = user.get("user_id") or user.get("id") or update.get("user_id")
    chat_id = recipient.get("chat_id") or update.get("chat_id")
    return (str(user_id) if user_id is not None else None, str(chat_id) if chat_id is not None else None)


def update_key(update: dict[str, Any]) -> str:
    message = update.get("message") or {}
    body = message.get("body") or {}
    callback = update.get("callback") or {}
    seed = "|".join(
        str(value)
        for value in (
            update.get("update_type"),
            update.get("timestamp"),
            body.get("mid") or body.get("message_id") or message.get("message_id"),
            callback.get("callback_id"),
            callback.get("payload"),
        )
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def bind_by_code(db: Session, max_user_id: str, chat_id: str | None, text: str) -> MaxUserBinding | None:
    candidates = link_code_candidates(text)
    hashes = [hash_link_code(code) for code in candidates]
    if not hashes:
        return None
    link = db.scalar(
        select(MaxLinkCode).where(
            MaxLinkCode.code_hash.in_(hashes),
            MaxLinkCode.used_at.is_(None),
            MaxLinkCode.expires_at >= datetime.utcnow(),
        )
    )
    if not link:
        return None
    existing_patient = db.scalar(select(MaxUserBinding).where(MaxUserBinding.patient_id == link.patient_id))
    existing_max = db.scalar(select(MaxUserBinding).where(MaxUserBinding.max_user_id == max_user_id))
    if existing_max and existing_max.patient_id != link.patient_id:
        raise HTTPException(status_code=409, detail="Аккаунт MAX уже привязан к другому пациенту")
    binding = existing_patient or existing_max
    if binding:
        binding.max_user_id = max_user_id
        binding.chat_id = chat_id
        binding.status = "pending_consent"
        binding.updated_at = datetime.utcnow()
    else:
        binding = MaxUserBinding(patient_id=link.patient_id, max_user_id=max_user_id, chat_id=chat_id)
        db.add(binding)
        db.flush()
    link.used_at = datetime.utcnow()
    return binding


def handle_callback(db: Session, binding: MaxUserBinding, callback: dict[str, Any]) -> None:
    payload = callback.get("payload", "")
    callback_id = str(callback.get("callback_id") or "")
    if payload.startswith("consent:accept:"):
        document_id = payload.rsplit(":", 1)[-1]
        document = db.get(LegalDocumentVersion, document_id)
        if document and document.is_active and not db.scalar(
            select(MaxConsent).where(MaxConsent.binding_id == binding.id, MaxConsent.legal_document_id == document.id)
        ):
            db.add(MaxConsent(binding_id=binding.id, legal_document_id=document.id, source_event_id=callback_id or None))
            db.flush()
        if callback_id:
            answer_callback(callback_id, "Согласие сохранено")
        request_next_consent(db, binding)
        return
    if payload.startswith("consent:decline:"):
        binding.status = "consent_declined"
        binding.updated_at = datetime.utcnow()
        if callback_id:
            answer_callback(callback_id, "Отказ сохранён")
        send_message(binding.max_user_id, "Согласие не принято. Сбор ответов в MAX остановлен. Для возобновления обратитесь в клинику.")
        return
    if binding.status in {"stopped", "consent_declined"}:
        send_message(binding.max_user_id, "Сбор ответов остановлен. Для повторного подключения получите новый код на сайте.")
        return
    if not active_legal_documents(db) or pending_legal_document(db, binding):
        request_next_consent(db, binding)
        return
    if payload == "profile:show":
        patient = db.get(PatientProfile, binding.patient_id)
        if not patient:
            send_message(binding.max_user_id, "Профиль пациента не найден. Обратитесь в клинику.")
            return
        account = db.get(User, patient.user_id) if patient.user_id else None
        doctor = db.get(User, patient.doctor_id)
        phone = account.phone if account and account.phone else "не указан"
        doctor_name = doctor.name if doctor else "не назначен"
        if callback_id:
            answer_callback(callback_id, "Профиль открыт")
        send_message(
            binding.max_user_id,
            "Профиль подключён\n\n"
            f"Пациент: {patient.display_name}\n"
            f"Номер карты: {patient.card}\n"
            f"Телефон: {phone}\n"
            f"Лечащий врач: {doctor_name}",
            [[callback_button("Вернуться в меню", "menu:show")]],
        )
        return
    if payload == "menu:show":
        if callback_id:
            answer_callback(callback_id, "Главное меню")
        send_main_menu(db, binding)
        return
    if payload.startswith("assignment:start:"):
        assignment_id = payload.rsplit(":", 1)[-1]
        assignment = db.get(QuestionnaireAssignment, assignment_id)
        if not assignment or assignment.patient_id != binding.patient_id or assignment.status != "assigned" or not assignment.version_id:
            send_main_menu(db, binding, "Назначение недоступно.")
            return
        binding.active_assignment_id = assignment.id
        binding.active_question_index = 0
        binding.active_answers_json = "{}"
        binding.updated_at = datetime.utcnow()
        if callback_id:
            answer_callback(callback_id, "Опрос начат")
        send_current_question(db, binding)
        return
    if payload.startswith("answer:"):
        _, assignment_id, index_text, option_text = payload.split(":", 3)
        if binding.active_assignment_id != assignment_id or binding.active_question_index != int(index_text):
            send_current_question(db, binding)
            return
        assignment = db.get(QuestionnaireAssignment, assignment_id)
        version = db.get(QuestionnaireVersion, assignment.version_id) if assignment and assignment.version_id else None
        questions = json_load(version.questions_json if version else "[]", [])
        question = questions[binding.active_question_index]
        options = question.get("options", [])
        option_index = int(option_text)
        if option_index < 0 or option_index >= len(options):
            raise HTTPException(status_code=422, detail="Вариант ответа не найден")
        if callback_id:
            answer_callback(callback_id, "Ответ сохранён")
        record_answer(db, binding, options[option_index].get("value"))
        return
    if payload.startswith("number:"):
        _, assignment_id, index_text, value_text = payload.split(":", 3)
        if binding.active_assignment_id != assignment_id or binding.active_question_index != int(index_text):
            send_current_question(db, binding)
            return
        if callback_id:
            answer_callback(callback_id, "Ответ сохранён")
        record_answer(db, binding, value_text)
        return
    if payload == "state:message":
        binding.active_assignment_id = None
        binding.active_question_index = 0
        binding.active_answers_json = json.dumps({"_mode": "state_message"})
        if callback_id:
            answer_callback(callback_id, "Можно отправить сообщение")
        send_message(binding.max_user_id, "Напишите, что изменилось в вашем состоянии. Сообщение будет доступно вашему лечащему врачу на сайте.")
        return
    if payload.startswith("appointment:"):
        _, invitation_id, decision = payload.split(":", 2)
        invitation = db.get(AppointmentInvitation, invitation_id)
        if invitation and invitation.patient_id == binding.patient_id and decision in {"confirmed", "reschedule", "declined"}:
            invitation.status = decision
            invitation.responded_at = datetime.utcnow()
            if callback_id:
                answer_callback(callback_id, "Ответ передан врачу")
            send_main_menu(db, binding, "Ответ по приглашению передан врачу.")


def handle_message(db: Session, binding: MaxUserBinding, text: str) -> None:
    if binding.status in {"stopped", "consent_declined"}:
        send_message(binding.max_user_id, "Сбор ответов остановлен. Для повторного подключения получите новый код на сайте.")
        return
    if not active_legal_documents(db) or pending_legal_document(db, binding):
        request_next_consent(db, binding)
        return
    if binding.active_assignment_id:
        record_answer(db, binding, text)
        return
    state = json_load(binding.active_answers_json, {})
    if state.get("_mode") == "state_message":
        patient = db.get(PatientProfile, binding.patient_id)
        if patient:
            db.add(
                PatientMessage(
                    patient_id=patient.id,
                    doctor_id=patient.doctor_id,
                    sender_role="patient",
                    text=text[:4000],
                    source="max",
                    delivered_at=datetime.utcnow(),
                )
            )
        item = DailyCheckin(
            patient_id=binding.patient_id,
            reported_at=datetime.utcnow(),
            new_symptoms=text[:2000],
            source="max_bot",
            completeness=0.2,
        )
        db.add(item)
        if patient:
            patient.last_contact = item.reported_at
            db.add(
                ClinicalAlert(
                    patient_id=patient.id,
                    responsible_doctor_id=patient.doctor_id,
                    level="yellow",
                    reason="Новое сообщение пациента о состоянии",
                    source=f"Сообщение через MAX от {item.reported_at:%d.%m.%Y %H:%M}. Требует просмотра лечащим врачом.",
                )
            )
        binding.active_answers_json = "{}"
        binding.updated_at = datetime.utcnow()
        db.flush()
        send_main_menu(db, binding, "Сообщение сохранено и передано лечащему врачу.")
        return
    send_main_menu(db, binding)


def process_update(db: Session, update: dict[str, Any]) -> dict[str, str]:
    key = update_key(update)
    if db.get(MaxProcessedUpdate, key):
        return {"status": "duplicate"}
    db.add(MaxProcessedUpdate(id=key, update_type=str(update.get("update_type", "unknown"))))
    max_user_id, chat_id = update_identity(update)
    if not max_user_id:
        db.commit()
        return {"status": "ignored"}
    binding = db.scalar(select(MaxUserBinding).where(MaxUserBinding.max_user_id == max_user_id))
    update_type = update.get("update_type")
    if update_type in {"bot_stopped", "dialog_removed"} and binding:
        binding.status = "stopped"
        binding.updated_at = datetime.utcnow()
        db.commit()
        return {"status": "stopped"}
    if update_type == "bot_started" and not binding:
        send_message(
            max_user_id,
            "Здравствуйте! Чтобы воспользоваться сервисом, вы должны быть зарегистрированы в клинике.\n\n"
            "Введите уникальный код, который вам выдали, или авторизуйтесь на сайте с помощью полученных логина и пароля.",
        )
        db.commit()
        return {"status": "awaiting_link"}
    if update_type == "message_created":
        body = (update.get("message") or {}).get("body") or {}
        text = str(body.get("text") or "").strip()
        if not binding:
            if text.casefold() in {"старт", "start", "/start", "начать"}:
                send_message(
                    max_user_id,
                    "Здравствуйте! Получите одноразовый код в профиле пациента на сайте и отправьте его сюда. "
                    "Код состоит из 12 символов и действует 24 часа.",
                )
                db.commit()
                return {"status": "awaiting_link"}
            binding = bind_by_code(db, max_user_id, chat_id, text)
            if not binding:
                if not 8 <= len(link_code_candidates(text)[0] if link_code_candidates(text) else "") <= 20:
                    send_message(max_user_id, "Отправьте 12-значный код из вкладки «Профиль» на сайте.")
                else:
                    send_message(max_user_id, "Код не найден или истёк. Получите новый код в профиле пациента на сайте.")
                db.commit()
                return {"status": "invalid_link"}
            request_next_consent(db, binding)
        else:
            binding.chat_id = chat_id or binding.chat_id
            try:
                with db.begin_nested():
                    handle_message(db, binding, text)
            except HTTPException as error:
                send_message(binding.max_user_id, str(error.detail))
    elif update_type == "message_callback" and binding:
        try:
            with db.begin_nested():
                handle_callback(db, binding, update.get("callback") or {})
        except (HTTPException, ValueError, IndexError) as error:
            send_message(binding.max_user_id, str(error.detail) if isinstance(error, HTTPException) else "Эта кнопка больше недоступна. Откройте меню и выберите опрос заново.")
    db.commit()
    return {"status": "processed"}


def send_appointment_invitation(db: Session, invitation: AppointmentInvitation) -> bool:
    binding = db.scalar(select(MaxUserBinding).where(MaxUserBinding.patient_id == invitation.patient_id, MaxUserBinding.status == "active"))
    if not binding:
        return False
    rows = [
        [callback_button("Подтвердить", f"appointment:{invitation.id}:confirmed")],
        [callback_button("Нужно другое время", f"appointment:{invitation.id}:reschedule")],
        [callback_button("Не смогу прийти", f"appointment:{invitation.id}:declined")],
    ]
    if invitation.schedule_mode == "external" and invitation.external_reference:
        rows.insert(0, [link_button("Открыть расписание клиники", invitation.external_reference)])
    when = invitation.proposed_at.strftime("%d.%m.%Y %H:%M") if invitation.proposed_at else "время согласует клиника"
    send_message(binding.max_user_id, f"{invitation.message}\n\nПредлагаемое время: {when}", rows)
    return True


def verify_webhook_secret(received: str | None) -> None:
    configured = os.getenv("MAX_WEBHOOK_SECRET", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Секрет webhook MAX не настроен")
    if not secrets.compare_digest(received or "", configured):
        raise HTTPException(status_code=401, detail="Некорректный секрет webhook")
