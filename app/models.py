from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now() -> datetime:
    return datetime.utcnow()


def gen_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    login: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(1), nullable=False)
    card: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    diagnosis_code: Mapped[str] = mapped_column(String(20), nullable=False)
    diagnosis_title: Mapped[str] = mapped_column(String(255), nullable=False)
    diagnosis_status: Mapped[str] = mapped_column(String(30), default="preliminary", nullable=False)
    first_two_lines_refractory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contraindications_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    medication_restrictions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    complaint: Mapped[str] = mapped_column(Text, default="", nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#dce6f8", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_contact: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)

    user: Mapped[User | None] = relationship("User", foreign_keys=[user_id])
    doctor: Mapped[User] = relationship("User", foreign_keys=[doctor_id])
    checkins: Mapped[list["DailyCheckin"]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    prescriptions: Mapped[list["Prescription"]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class CareRelationship(Base):
    __tablename__ = "care_relationships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    __table_args__ = (UniqueConstraint("doctor_id", "patient_id", name="uq_doctor_patient"),)


class DailyCheckin(Base):
    __tablename__ = "daily_checkins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True, nullable=False)
    anxiety: Mapped[float | None] = mapped_column(Float, nullable=True)
    mood: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_quality: Mapped[str | None] = mapped_column(String(30), nullable=True)
    functioning: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="patient_self_report", nullable=False)
    completeness: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    patient: Mapped[PatientProfile] = relationship(back_populates="checkins")


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    medication_name: Mapped[str] = mapped_column(String(160), nullable=False)
    medication_form: Mapped[str] = mapped_column(String(100), default="Назначение", nullable=False)
    regimen: Mapped[str] = mapped_column(String(255), nullable=False)
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    patient: Mapped[PatientProfile] = relationship(back_populates="prescriptions")
    intakes: Mapped[list["TherapyIntake"]] = relationship(back_populates="prescription", cascade="all, delete-orphan")
    events: Mapped[list["AdverseEvent"]] = relationship(back_populates="prescription", cascade="all, delete-orphan")


class TherapyIntake(Base):
    __tablename__ = "therapy_intakes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    prescription_id: Mapped[str] = mapped_column(ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # taken, missed, different, unknown, no_data
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prescription: Mapped[Prescription] = relationship(back_populates="intakes")


class AdverseEvent(Base):
    __tablename__ = "adverse_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    prescription_id: Mapped[str | None] = mapped_column(ForeignKey("prescriptions.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ongoing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    impact: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="needs_review", nullable=False)
    prescription: Mapped[Prescription | None] = relationship(back_populates="events")


class QuestionnaireResponse(Base):
    __tablename__ = "questionnaire_responses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    template: Mapped[str] = mapped_column(String(80), nullable=False)
    source_version: Mapped[str] = mapped_column(String(120), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    assignment_id: Mapped[str | None] = mapped_column(ForeignKey("questionnaire_assignments.id", ondelete="SET NULL"), index=True, nullable=True)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("questionnaire_versions.id", ondelete="SET NULL"), index=True, nullable=True)
    answers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)


class QuestionnaireAssignment(Base):
    __tablename__ = "questionnaire_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    template: Mapped[str] = mapped_column(String(80), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="assigned", nullable=False)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("questionnaire_versions.id", ondelete="SET NULL"), index=True, nullable=True)
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    purpose: Mapped[str] = mapped_column(String(255), default="Наблюдение за состоянием", nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), default="once", nullable=False)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Moscow", nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_after_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_channel: Mapped[str] = mapped_column(String(20), default="max", nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuestionnaireTemplate(Base):
    __tablename__ = "questionnaire_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="Авторский", nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="custom", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    versions: Mapped[list["QuestionnaireVersion"]] = relationship(back_populates="template", cascade="all, delete-orphan")


class QuestionnaireVersion(Base):
    __tablename__ = "questionnaire_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    template_id: Mapped[str] = mapped_column(ForeignKey("questionnaire_templates.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    questions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    scoring_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    alert_rules_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    requires_clinical_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    template: Mapped[QuestionnaireTemplate] = relationship(back_populates="versions")
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_questionnaire_template_version"),)


class ClinicalAlert(Base):
    __tablename__ = "clinical_alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    level: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    responsible_doctor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)


class ClinicalTask(Base):
    __tablename__ = "clinical_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)


class PatientMessage(Base):
    __tablename__ = "patient_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    sender_role: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="site", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NextContact(Base):
    __tablename__ = "next_contacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), default="Повторная консультация", nullable=False)


class AiRecommendation(Base):
    __tablename__ = "ai_recommendations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    risks: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    source_ids: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)


class ClinicalDocument(Base):
    __tablename__ = "clinical_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    organization: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    published: Mapped[date] = mapped_column(Date, nullable=False)
    checked: Mapped[date] = mapped_column(Date, nullable=False)
    code: Mapped[str] = mapped_column(String(40), default="—", nullable=False)
    medication: Mapped[str] = mapped_column(String(120), default="—", nullable=False)
    url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now, index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)


class DoctorSettings(Base):
    __tablename__ = "doctor_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    specialty: Mapped[str] = mapped_column(String(120), nullable=False)
    organization: Mapped[str] = mapped_column(String(160), nullable=False)
    notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminders: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LegalDocumentVersion(Base):
    __tablename__ = "legal_document_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    kind: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    requires_reconsent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("kind", "version", name="uq_legal_kind_version"),)


class MaxUserBinding(Base):
    __tablename__ = "max_user_bindings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    max_user_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    chat_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_consent", nullable=False)
    active_assignment_id: Mapped[str | None] = mapped_column(ForeignKey("questionnaire_assignments.id", ondelete="SET NULL"), nullable=True)
    active_question_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_answers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class MaxLinkCode(Base):
    __tablename__ = "max_link_codes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class MaxConsent(Base):
    __tablename__ = "max_consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    binding_id: Mapped[str] = mapped_column(ForeignKey("max_user_bindings.id", ondelete="CASCADE"), index=True, nullable=False)
    legal_document_id: Mapped[str] = mapped_column(ForeignKey("legal_document_versions.id", ondelete="RESTRICT"), index=True, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("binding_id", "legal_document_id", name="uq_binding_legal_document"),)


class MaxProcessedUpdate(Base):
    __tablename__ = "max_processed_updates"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    update_type: Mapped[str] = mapped_column(String(60), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ScheduleSettings(Base):
    __tablename__ = "schedule_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    organization: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)
    external_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AppointmentInvitation(Base):
    __tablename__ = "appointment_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True, nullable=False)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="Врач приглашает вас на приём.", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="invited", nullable=False)
    schedule_mode: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)
    external_reference: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
