from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.max_bot import active_legal_documents, callback_button, pending_legal_document, send_message
from app.models import MaxUserBinding, QuestionnaireAssignment


def dispatch_due_assignments(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Deliver due MAX questionnaires and one configured reminder without duplicates."""
    moment = now or datetime.utcnow()
    assignments = db.scalars(
        select(QuestionnaireAssignment)
        .where(
            QuestionnaireAssignment.status == "assigned",
            QuestionnaireAssignment.delivery_channel == "max",
            QuestionnaireAssignment.due_at <= moment,
        )
        .order_by(QuestionnaireAssignment.due_at)
    ).all()
    delivered = 0
    reminded = 0
    skipped = 0
    failed = 0

    for assignment in assignments:
        if assignment.end_at and assignment.end_at < moment:
            assignment.status = "expired"
            skipped += 1
            continue
        binding = db.scalar(
            select(MaxUserBinding).where(
                MaxUserBinding.patient_id == assignment.patient_id,
                MaxUserBinding.status == "active",
            )
        )
        if not binding or not active_legal_documents(db) or pending_legal_document(db, binding):
            skipped += 1
            continue
        try:
            if assignment.last_sent_at is None:
                send_message(
                    binding.max_user_id,
                    f"Врач назначил опрос «{assignment.template}».\nЦель: {assignment.purpose}",
                    [[callback_button("Начать опрос", f"assignment:start:{assignment.id}")]],
                )
                assignment.last_sent_at = moment
                assignment.reminder_sent_at = None
                delivered += 1
                continue
            if (
                assignment.reminder_after_minutes
                and assignment.reminder_sent_at is None
                and assignment.last_sent_at + timedelta(minutes=assignment.reminder_after_minutes) <= moment
            ):
                send_message(
                    binding.max_user_id,
                    f"Напоминание: ожидает опрос «{assignment.template}».",
                    [[callback_button("Ответить", f"assignment:start:{assignment.id}")]],
                )
                assignment.reminder_sent_at = moment
                reminded += 1
        except RuntimeError:
            failed += 1

    db.commit()
    return {"delivered": delivered, "reminded": reminded, "skipped": skipped, "failed": failed}
