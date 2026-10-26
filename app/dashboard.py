from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AdverseEvent, AiRecommendation, AuditEvent, ClinicalAlert, ClinicalDocument,
    ClinicalTask, DailyCheckin, DoctorSettings, NextContact, PatientProfile,
    Prescription, QuestionnaireAssignment, QuestionnaireResponse, TherapyIntake, User,
)

DEMO_NOW = datetime(2026, 10, 16, 12, 0)


def iso(value: date | datetime | None) -> str:
    return value.isoformat() if value else ""


def age_on(born: date, today: date = date(2026, 10, 16)) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def adherence_counts(db: Session, patient_id: str) -> dict[str, int]:
    rows = db.scalars(
        select(TherapyIntake)
        .join(Prescription)
        .where(Prescription.patient_id == patient_id)
        .order_by(TherapyIntake.scheduled_at.desc())
        .limit(14)
    ).all()
    return {
        "planned": len(rows),
        "confirmed": sum(row.status == "taken" for row in rows),
        "missed": sum(row.status == "missed" for row in rows),
        "different": sum(row.status == "different" for row in rows),
        "noData": sum(row.status in {"unknown", "no_data"} for row in rows),
    }


def patient_risk(db: Session, patient: PatientProfile) -> tuple[str, str]:
    alerts = db.scalars(
        select(ClinicalAlert).where(ClinicalAlert.patient_id == patient.id, ClinicalAlert.status != "closed")
    ).all()
    stale_days = max(0, (datetime.utcnow().date() - patient.last_contact.date()).days)
    if any(alert.level == "red" for alert in alerts):
        return "red", next(alert.reason for alert in alerts if alert.level == "red")
    if stale_days >= 3:
        return "gray", f"Нет ответов {stale_days} дн."
    if alerts:
        return "yellow", alerts[0].reason
    return "green", "Актуальные данные, активных сигналов нет"


def serialize_patient(db: Session, patient: PatientProfile) -> dict:
    checkins = db.scalars(
        select(DailyCheckin).where(DailyCheckin.patient_id == patient.id).order_by(DailyCheckin.reported_at)
    ).all()
    prescriptions = db.scalars(select(Prescription).where(Prescription.patient_id == patient.id)).all()
    questionnaires = db.scalars(
        select(QuestionnaireResponse)
        .where(QuestionnaireResponse.patient_id == patient.id)
        .order_by(QuestionnaireResponse.completed_at.desc())
    ).all()
    risk, _ = patient_risk(db, patient)
    counts = adherence_counts(db, patient.id)
    adherence = round(counts["confirmed"] / counts["planned"] * 100) if counts["planned"] else 0
    doctor_name = patient.doctor.name if patient.doctor else "Врач"
    return {
        "id": patient.id,
        "name": patient.display_name,
        "age": age_on(patient.birth_date),
        "sex": patient.sex,
        "card": patient.card,
        "doctor": doctor_name,
        "status": patient.status,
        "risk": "yellow" if risk == "gray" else risk,
        "diagnosis": {"code": patient.diagnosis_code, "title": patient.diagnosis_title},
        "diagnosisStatus": patient.diagnosis_status,
        "lastContact": iso(patient.last_contact),
        "adherence": adherence,
        "complaint": patient.complaint,
        "color": patient.color,
        "dynamics": [
            {
                "date": item.reported_at.date().isoformat(),
                "anxiety": item.anxiety if item.anxiety is not None else 0,
                "mood": item.mood if item.mood is not None else 0,
                "sleep": round((item.sleep_minutes or 0) / 60, 1),
                "wellbeing": round(((item.mood or 0) + (10 - (item.anxiety or 0))) / 2, 1),
                "adherence": adherence,
            }
            for item in checkins
        ],
        "questionnaires": [
            {
                "id": item.id,
                "template": item.template,
                "date": item.completed_at.date().isoformat(),
                "score": item.score if item.score is not None else 0,
                "previous": item.previous_score if item.previous_score is not None else 0,
                "description": f"{item.source_version}. Результат не является диагнозом.",
            }
            for item in questionnaires
        ],
        "prescriptions": [
            {
                "id": rx.id,
                "medication": {"id": f"med-{rx.id}", "name": rx.medication_name, "form": rx.medication_form},
                "regimen": rx.regimen,
                "start": iso(rx.started_on),
                "end": iso(rx.ended_on),
                "adherence": adherence,
                "intakes": [
                    {"date": row.scheduled_at.date().isoformat(), "taken": row.status == "taken"}
                    for row in sorted(rx.intakes, key=lambda row: row.scheduled_at)
                ],
                "events": [
                    {
                        "id": event.id,
                        "date": event.started_at.date().isoformat(),
                        "description": event.description,
                        "status": "Требует проверки врача" if event.review_status == "needs_review" else "Проверено",
                    }
                    for event in rx.events
                ],
                "status": "Наблюдение" if rx.status == "active" else rx.status,
            }
            for rx in prescriptions
        ],
    }


def queue_item(db: Session, patient: PatientProfile) -> dict:
    risk, reason = patient_risk(db, patient)
    checkins = db.scalars(
        select(DailyCheckin).where(DailyCheckin.patient_id == patient.id).order_by(DailyCheckin.reported_at.desc()).limit(2)
    ).all()
    latest = checkins[0] if checkins else None
    previous = checkins[1] if len(checkins) > 1 else None
    changes: list[str] = []
    if latest and previous:
        anxiety_delta = round((latest.anxiety or 0) - (previous.anxiety or 0), 1)
        sleep_delta = round(((latest.sleep_minutes or 0) - (previous.sleep_minutes or 0)) / 60, 1)
        if abs(anxiety_delta) >= 0.5:
            changes.append(f"тревога {anxiety_delta:+g}")
        if abs(sleep_delta) >= 0.5:
            changes.append(f"сон {sleep_delta:+g} ч")
    event = db.scalar(
        select(AdverseEvent).where(AdverseEvent.patient_id == patient.id).order_by(AdverseEvent.started_at.desc())
    )
    counts = adherence_counts(db, patient.id)
    overdue = db.scalars(
        select(ClinicalTask).where(
            ClinicalTask.patient_id == patient.id,
            ClinicalTask.due_at < datetime.utcnow(),
            ClinicalTask.status.in_(["new", "working"]),
        )
    ).all()
    contact = db.scalar(select(NextContact).where(NextContact.patient_id == patient.id))
    if risk == "red":
        action = "Оценить сигнал и зафиксировать действие"
    elif risk == "gray":
        action = "Связаться с пациентом и уточнить состояние"
    elif overdue:
        action = f"Закрыть просроченные действия: {len(overdue)}"
    else:
        action = "Продолжить наблюдение по плану"
    doctor_name = patient.doctor.name if patient.doctor else "Врач"
    return {
        "patientId": patient.id,
        "patientName": patient.display_name,
        "status": risk,
        "reason": reason,
        "changeSummary": ", ".join(changes) if changes else "Значимых изменений по последним ответам нет",
        "tolerability": event.description if event else "Новых сообщений нет",
        "adherence": counts,
        "lastResponseAt": iso(patient.last_contact),
        "overdueActions": len(overdue),
        "nextContactAt": iso(contact.scheduled_at) if contact else None,
        "nextContactKind": contact.kind if contact else "Не назначен",
        "recommendedAction": action,
        "responsibleDoctor": doctor_name,
        "source": latest.source if latest else "нет данных",
        "measuredAt": iso(latest.reported_at) if latest else None,
    }


def build_dashboard(db: Session, doctor_id: str | None = None) -> dict:
    patient_query = select(PatientProfile).order_by(PatientProfile.id)
    if doctor_id:
        patient_query = patient_query.where(PatientProfile.doctor_id == doctor_id)
    patients = db.scalars(patient_query).all()
    patient_ids = [patient.id for patient in patients]
    alerts_query = select(ClinicalAlert).order_by(ClinicalAlert.created_at.desc())
    tasks_query = select(ClinicalTask).order_by(ClinicalTask.due_at)
    assignments_query = select(QuestionnaireAssignment).order_by(QuestionnaireAssignment.due_at)
    recommendations_query = select(AiRecommendation).order_by(AiRecommendation.created_at.desc())
    if doctor_id:
        alerts_query = alerts_query.where(ClinicalAlert.patient_id.in_(patient_ids))
        tasks_query = tasks_query.where(ClinicalTask.patient_id.in_(patient_ids))
        assignments_query = assignments_query.where(QuestionnaireAssignment.patient_id.in_(patient_ids))
        recommendations_query = recommendations_query.where(AiRecommendation.patient_id.in_(patient_ids))
    alerts = db.scalars(alerts_query).all()
    tasks = db.scalars(tasks_query).all()
    assignments = db.scalars(assignments_query).all()
    recommendations = db.scalars(recommendations_query).all()
    documents = db.scalars(select(ClinicalDocument).order_by(ClinicalDocument.title)).all()
    audit_query = select(AuditEvent)
    if doctor_id:
        visible_ids = [doctor_id, *patient_ids, *[row.id for row in alerts], *[row.id for row in tasks], *[row.id for row in assignments], *[row.id for row in recommendations]]
        audit_query = audit_query.where(AuditEvent.entity_id.in_(visible_ids))
    audits = db.scalars(audit_query.order_by(AuditEvent.timestamp.desc()).limit(100)).all()
    settings = db.scalar(select(DoctorSettings).where(DoctorSettings.user_id == doctor_id)) if doctor_id else None
    if not doctor_id:
        settings = db.scalar(select(DoctorSettings).where(DoctorSettings.user_id == "doctor-demo"))
    doctor = db.get(User, doctor_id) if doctor_id else (db.get(User, settings.user_id) if settings else None)
    return {
        "patients": [serialize_patient(db, patient) for patient in patients],
        "doctorQueue": [queue_item(db, patient) for patient in patients],
        "alerts": [
            {
                "id": row.id,
                "patientId": row.patient_id,
                "level": row.level,
                "reason": row.reason,
                "source": row.source,
                "createdAt": iso(row.created_at),
                "deliveredAt": iso(row.delivered_at),
                "status": row.status,
                "comment": row.comment,
                "action": row.action,
                **({"reviewedAt": iso(row.reviewed_at)} if row.reviewed_at else {}),
            }
            for row in alerts
        ],
        "tasks": [
            {"id": row.id, "patientId": row.patient_id, "title": row.title, "dueAt": iso(row.due_at), "status": row.status}
            for row in tasks
        ],
        "assignments": [
            {
                "id": row.id,
                "patientId": row.patient_id,
                "template": row.template,
                "assignedAt": iso(row.assigned_at),
                "dueAt": iso(row.due_at),
                "status": row.status,
            }
            for row in assignments
        ],
        "recommendations": [
            {
                "id": row.id,
                "patientId": row.patient_id,
                "kind": row.kind,
                "text": row.text,
                "data": row.data,
                "risks": row.risks,
                "limitations": row.limitations,
                "sourceIds": [x for x in row.source_ids.split(",") if x],
                "createdAt": iso(row.created_at),
                "status": row.status,
            }
            for row in recommendations
        ],
        "documents": [
            {
                "id": row.id,
                "title": row.title,
                "category": row.category,
                "organization": row.organization,
                "version": row.version,
                "published": iso(row.published),
                "checked": iso(row.checked),
                "code": row.code,
                "medication": row.medication,
                "url": row.url,
                "text": row.text,
            }
            for row in documents
        ],
        "audit": [
            {"id": row.id, "timestamp": iso(row.timestamp), "actor": row.actor, "action": row.action, "entityId": row.entity_id}
            for row in audits
        ],
        "settings": {
            "name": doctor.name if doctor else "Врач",
            "specialty": settings.specialty if settings else "Не указана",
            "organization": settings.organization if settings else "Не указана",
            "notifications": settings.notifications if settings else True,
            "reminders": settings.reminders if settings else True,
        },
    }
