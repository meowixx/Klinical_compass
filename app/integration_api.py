import json
from datetime import datetime, timedelta
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import audit, patient_or_404
from app.database import get_db
from app.max_bot import (
    MAX_TOKEN_PATH,
    pending_legal_document,
    active_legal_documents,
    callback_button,
    create_link_code,
    process_update,
    send_message,
    send_appointment_invitation,
    verify_webhook_secret,
)
from app.models import (
    AppointmentInvitation,
    LegalDocumentVersion,
    MaxConsent,
    MaxUserBinding,
    PatientMessage,
    PatientProfile,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    ScheduleSettings,
    User,
)
from app.questionnaires import serialize_template, serialize_version, touch
from app.scheduler import dispatch_due_assignments
from app.schemas import (
    AppointmentInvitationCreate,
    LegalDocumentCreate,
    MaxLinkCreate,
    PatientMessageCreate,
    QuestionnaireApproval,
    QuestionnairePublish,
    QuestionnaireTemplateCreate,
    QuestionnaireVersionCreate,
    ScheduleSettingsUpdate,
)
from app.security import current_user, require_admin, require_doctor

router = APIRouter(prefix="/api/v1")


def doctor_patient_access(user: User, patient_doctor_id: str) -> None:
    if user.role != "admin" and user.id != patient_doctor_id:
        raise HTTPException(status_code=403, detail="Пациент закреплён за другим лечащим врачом")


def serialize_message(item: PatientMessage) -> dict:
    return {
        "id": item.id,
        "patientId": item.patient_id,
        "senderRole": item.sender_role,
        "text": item.text,
        "source": item.source,
        "createdAt": item.created_at.isoformat(),
        "readAt": item.read_at.isoformat() if item.read_at else None,
        "deliveredAt": item.delivered_at.isoformat() if item.delivered_at else None,
    }


@router.get("/messages")
def message_conversations(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    query = select(PatientProfile).order_by(PatientProfile.display_name)
    if doctor.role != "admin":
        query = query.where(PatientProfile.doctor_id == doctor.id)
    result = []
    for patient in db.scalars(query):
        last = db.scalar(
            select(PatientMessage)
            .where(PatientMessage.patient_id == patient.id)
            .order_by(PatientMessage.created_at.desc())
        )
        unread = len(
            db.scalars(
                select(PatientMessage).where(
                    PatientMessage.patient_id == patient.id,
                    PatientMessage.sender_role == "patient",
                    PatientMessage.read_at.is_(None),
                )
            ).all()
        )
        binding = db.scalar(select(MaxUserBinding).where(MaxUserBinding.patient_id == patient.id))
        result.append(
            {
                "patientId": patient.id,
                "patientName": patient.display_name,
                "card": patient.card,
                "maxConnected": bool(binding and binding.status == "active"),
                "unreadCount": unread,
                "lastMessage": serialize_message(last) if last else None,
            }
        )
    return result


@router.get("/messages/{patient_id}")
def message_thread(
    patient_id: str,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    patient = patient_or_404(db, patient_id)
    doctor_patient_access(doctor, patient.doctor_id)
    rows = db.scalars(
        select(PatientMessage)
        .where(PatientMessage.patient_id == patient.id)
        .order_by(PatientMessage.created_at)
    ).all()
    now = datetime.utcnow()
    for row in rows:
        if row.sender_role == "patient" and not row.read_at:
            row.read_at = now
    db.commit()
    return [serialize_message(row) for row in rows]


@router.post("/messages/{patient_id}", status_code=201)
def reply_to_patient(
    patient_id: str,
    payload: PatientMessageCreate,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    patient = patient_or_404(db, patient_id)
    doctor_patient_access(doctor, patient.doctor_id)
    binding = db.scalar(
        select(MaxUserBinding).where(
            MaxUserBinding.patient_id == patient.id,
            MaxUserBinding.status == "active",
        )
    )
    if not binding:
        raise HTTPException(status_code=409, detail="Пациент ещё не завершил подключение MAX")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Введите текст сообщения")
    if not active_legal_documents(db) or pending_legal_document(db, binding):
        raise HTTPException(status_code=409, detail="Пациент должен принять актуальные согласия в MAX")
    send_message(
        binding.max_user_id,
        f"Сообщение лечащего врача:\n\n{text}",
        [[callback_button("Ответить врачу", "state:message")]],
    )
    item = PatientMessage(
        patient_id=patient.id,
        doctor_id=patient.doctor_id,
        sender_role="doctor",
        text=text,
        source="site",
        delivered_at=datetime.utcnow(),
    )
    db.add(item)
    audit(db, doctor.name, "Отправлено сообщение пациенту через MAX", patient.id)
    db.commit()
    db.refresh(item)
    return serialize_message(item)


@router.get("/questionnaire-library")
def questionnaire_library(user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    query = select(QuestionnaireTemplate).order_by(QuestionnaireTemplate.title)
    if user.role != "admin":
        query = query.where(QuestionnaireTemplate.status == "published")
    return [serialize_template(item) for item in db.scalars(query).unique().all()]


@router.post("/admin/questionnaire-library", status_code=201)
def create_questionnaire_template(
    payload: QuestionnaireTemplateCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    template = QuestionnaireTemplate(
        code=payload.code.strip(),
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category.strip(),
        source_url=payload.sourceUrl.strip(),
        kind=payload.kind,
        status="draft",
        created_by_user_id=admin.id,
    )
    version = QuestionnaireVersion(
        template=template,
        version=payload.version.strip(),
        instructions=payload.instructions.strip(),
        questions_json=json.dumps([item.model_dump() for item in payload.questions], ensure_ascii=False),
        scoring_json=json.dumps(payload.scoring, ensure_ascii=False),
        alert_rules_json=json.dumps(payload.alertRules, ensure_ascii=False),
        status="draft",
        requires_clinical_approval=payload.requiresClinicalApproval or payload.kind == "validated",
        created_by_user_id=admin.id,
    )
    db.add(template)
    db.add(version)
    audit(db, admin.name, f"Создан черновик опросника «{template.title}», версия {version.version}", template.id)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Код опросника уже используется") from error
    db.refresh(template)
    return serialize_template(template)


@router.post("/admin/questionnaire-library/{template_id}/versions", status_code=201)
def create_questionnaire_version(
    template_id: str,
    payload: QuestionnaireVersionCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    template = db.get(QuestionnaireTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Опросник не найден")
    version = QuestionnaireVersion(
        template_id=template.id,
        version=payload.version.strip(),
        instructions=payload.instructions.strip(),
        questions_json=json.dumps([item.model_dump() for item in payload.questions], ensure_ascii=False),
        scoring_json=json.dumps(payload.scoring, ensure_ascii=False),
        alert_rules_json=json.dumps(payload.alertRules, ensure_ascii=False),
        status="draft",
        requires_clinical_approval=payload.requiresClinicalApproval or template.kind == "validated",
        created_by_user_id=admin.id,
    )
    db.add(version)
    touch(template)
    audit(db, admin.name, f"Добавлена версия {version.version} опросника «{template.title}»", template.id)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Такая версия уже существует") from error
    return serialize_version(version)


@router.post("/questionnaire-library/versions/{version_id}/approve")
def approve_questionnaire_version(
    version_id: str,
    payload: QuestionnaireApproval,
    doctor: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if doctor.role != "doctor":
        raise HTTPException(status_code=403, detail="Клиническое утверждение доступно только врачу")
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Подтвердите клиническую проверку")
    version = db.get(QuestionnaireVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Версия не найдена")
    version.approved_by_user_id = doctor.id
    audit(db, doctor.name, f"Клинически проверена версия {version.version}", version.template_id)
    db.commit()
    return serialize_version(version)


@router.post("/admin/questionnaire-library/versions/{version_id}/publish")
def publish_questionnaire_version(
    version_id: str,
    payload: QuestionnairePublish,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Подтвердите публикацию")
    version = db.get(QuestionnaireVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Версия не найдена")
    if version.requires_clinical_approval and not version.approved_by_user_id:
        raise HTTPException(status_code=422, detail="Сначала требуется клиническое утверждение врачом")
    template = db.get(QuestionnaireTemplate, version.template_id)
    for item in template.versions:
        if item.id != version.id and item.status == "published":
            item.status = "archived"
    version.status = "published"
    version.published_at = datetime.utcnow()
    template.status = "published"
    touch(template)
    audit(db, admin.name, f"Опубликована версия {version.version} опросника «{template.title}»", template.id)
    db.commit()
    return serialize_template(template)


@router.post("/admin/questionnaire-library/versions/{version_id}/archive")
def archive_questionnaire_version(
    version_id: str,
    payload: QuestionnairePublish,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Подтвердите перенос в архив")
    version = db.get(QuestionnaireVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Версия не найдена")
    version.status = "archived"
    template = db.get(QuestionnaireTemplate, version.template_id)
    if not any(item.status == "published" for item in template.versions if item.id != version.id):
        template.status = "archived"
    touch(template)
    audit(db, admin.name, f"Версия {version.version} опросника «{template.title}» перенесена в архив", template.id)
    db.commit()
    return serialize_template(template)


@router.get("/admin/legal-documents")
def legal_documents(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(LegalDocumentVersion).order_by(LegalDocumentVersion.kind, LegalDocumentVersion.created_at.desc())).all()
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "version": row.version,
            "title": row.title,
            "content": row.content,
            "isActive": row.is_active,
            "requiresReconsent": row.requires_reconsent,
            "publishedAt": row.published_at.isoformat() if row.published_at else None,
        }
        for row in rows
    ]


@router.post("/admin/legal-documents", status_code=201)
def create_legal_document(
    payload: LegalDocumentCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = LegalDocumentVersion(
        kind=payload.kind,
        version=payload.version.strip(),
        title=payload.title.strip(),
        content=payload.content.strip(),
        requires_reconsent=payload.requiresReconsent,
        created_by_user_id=admin.id,
    )
    db.add(item)
    db.flush()
    if payload.publish:
        for previous in db.scalars(
            select(LegalDocumentVersion).where(LegalDocumentVersion.kind == item.kind, LegalDocumentVersion.id != item.id)
        ):
            previous.is_active = False
        item.is_active = True
        item.published_at = datetime.utcnow()
    audit(db, admin.name, f"Создана версия {item.version} документа «{item.title}»", item.id)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Такая версия документа уже существует") from error
    return {"id": item.id, "kind": item.kind, "version": item.version, "isActive": item.is_active}


@router.post("/admin/legal-documents/{document_id}/publish")
def publish_legal_document(
    document_id: str,
    payload: QuestionnairePublish,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Подтвердите публикацию юридического документа")
    item = db.get(LegalDocumentVersion, document_id)
    if not item:
        raise HTTPException(status_code=404, detail="Документ не найден")
    for previous in db.scalars(
        select(LegalDocumentVersion).where(LegalDocumentVersion.kind == item.kind, LegalDocumentVersion.id != item.id)
    ):
        previous.is_active = False
    item.is_active = True
    item.published_at = datetime.utcnow()
    audit(db, admin.name, f"Опубликована версия {item.version} документа «{item.title}»", item.id)
    db.commit()
    return {"id": item.id, "isActive": True, "requiresReconsent": item.requires_reconsent}


@router.post("/patients/{patient_id}/max/link-code", status_code=201)
def max_link_code(
    patient_id: str,
    payload: MaxLinkCreate,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    patient = patient_or_404(db, patient_id)
    doctor_patient_access(doctor, patient.doctor_id)
    code = create_link_code(db, patient.id, doctor.id, payload.expiresInMinutes)
    audit(db, doctor.name, "Создан одноразовый код привязки MAX", patient.id)
    db.commit()
    return {
        "code": code,
        "expiresAt": (datetime.utcnow() + timedelta(minutes=payload.expiresInMinutes)).isoformat(),
        "instruction": "Отправьте этот код боту MAX",
    }


@router.post("/account/max/link-code", status_code=201)
def own_max_link_code(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.role != "patient":
        raise HTTPException(status_code=403, detail="Код доступен только пациенту")
    patient = db.scalar(select(PatientProfile).where(PatientProfile.user_id == user.id))
    if not patient:
        raise HTTPException(status_code=404, detail="К учётной записи не привязана карточка пациента")
    code = create_link_code(db, patient.id, user.id, 1440)
    audit(db, user.name, "Пациент создал код привязки MAX", patient.id)
    db.commit()
    return {
        "code": code,
        "expiresAt": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        "instruction": "Отправьте этот код боту MAX",
    }


@router.get("/patients/{patient_id}/max/status")
def max_binding_status(
    patient_id: str,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    patient = patient_or_404(db, patient_id)
    doctor_patient_access(doctor, patient.doctor_id)
    binding = db.scalar(select(MaxUserBinding).where(MaxUserBinding.patient_id == patient.id))
    consent_count = 0
    if binding:
        consent_count = len(db.scalars(select(MaxConsent).where(MaxConsent.binding_id == binding.id, MaxConsent.revoked_at.is_(None))).all())
    return {"linked": bool(binding), "status": binding.status if binding else "not_linked", "acceptedDocuments": consent_count}


@router.get("/admin/max/status")
def max_status(_: User = Depends(require_admin)):
    return {"tokenFileConfigured": MAX_TOKEN_PATH.is_file(), "webhookSecretConfigured": bool(os.getenv("MAX_WEBHOOK_SECRET"))}


@router.post("/admin/max/dispatch")
def dispatch_max_questionnaires(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = dispatch_due_assignments(db)
    audit(db, admin.name, "Запущена отправка назначенных опросников MAX", "max-dispatch")
    db.commit()
    return result


@router.get("/admin/schedule-settings")
def get_schedule_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ScheduleSettings).order_by(ScheduleSettings.organization)).all()
    return [{"id": row.id, "organization": row.organization, "mode": row.mode, "externalUrl": row.external_url} for row in rows]


@router.put("/admin/schedule-settings")
def update_schedule_settings(
    payload: ScheduleSettingsUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(ScheduleSettings).where(ScheduleSettings.organization == payload.organization.strip()))
    if not item:
        item = ScheduleSettings(id=str(uuid4()), organization=payload.organization.strip())
        db.add(item)
    item.mode = payload.mode
    item.external_url = payload.externalUrl.strip()
    item.updated_at = datetime.utcnow()
    audit(db, admin.name, f"Обновлён режим расписания: {item.mode}", item.id)
    db.commit()
    return {"id": item.id, "organization": item.organization, "mode": item.mode, "externalUrl": item.external_url}


@router.post("/patients/{patient_id}/appointments/invite", status_code=201)
def invite_to_appointment(
    patient_id: str,
    payload: AppointmentInvitationCreate,
    doctor: User = Depends(require_doctor),
    db: Session = Depends(get_db),
):
    patient = patient_or_404(db, patient_id)
    doctor_patient_access(doctor, patient.doctor_id)
    if doctor.role == "admin":
        raise HTTPException(status_code=403, detail="Приглашение отправляет лечащий врач")
    settings = db.scalar(select(ScheduleSettings).order_by(ScheduleSettings.updated_at.desc()))
    mode = settings.mode if settings else "internal"
    item = AppointmentInvitation(
        id=str(uuid4()),
        patient_id=patient.id,
        doctor_id=doctor.id,
        proposed_at=payload.proposedAt,
        message=payload.message.strip(),
        schedule_mode=mode,
        external_reference=settings.external_url if settings and mode == "external" else "",
    )
    db.add(item)
    db.flush()
    delivered = send_appointment_invitation(db, item)
    if not delivered:
        item.status = "awaiting_max_link"
    audit(db, doctor.name, "Создано приглашение пациента на приём", patient.id)
    db.commit()
    return {
        "id": item.id,
        "patientId": item.patient_id,
        "proposedAt": item.proposed_at.isoformat() if item.proposed_at else None,
        "status": item.status,
        "scheduleMode": item.schedule_mode,
        "deliveredToMax": delivered,
    }


@router.post("/max/webhook")
def max_webhook(
    update: dict,
    x_max_bot_api_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    verify_webhook_secret(x_max_bot_api_secret)
    return process_update(db, update)
