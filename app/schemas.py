from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    login: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=128)


class UserRoleUpdate(BaseModel):
    role: str = Field(pattern="^(doctor|patient)$")


class AdminUserCreate(BaseModel):
    login: str = Field(min_length=3, max_length=80, pattern="^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(doctor|patient)$")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    specialty: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=160)
    patientAge: int | None = Field(default=None, ge=18, le=120)
    patientSex: str | None = Field(default=None, pattern="^[ЖМ]$")
    diagnosisCode: str | None = Field(default=None, max_length=20)
    doctorId: str | None = None

    @field_validator("email", "phone", mode="before")
    @classmethod
    def empty_contact_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class AccountContactUpdate(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=10, max_length=32)


class AdminUserProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    specialty: str = Field(min_length=2, max_length=120)
    organization: str = Field(min_length=2, max_length=160)


class PatientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    age: int = Field(ge=18, le=120)
    sex: str = Field(pattern="^[ЖМ]$")
    code: str = Field(min_length=2, max_length=20)


class AlertUpdate(BaseModel):
    status: str = Field(pattern="^(new|working|closed)$")
    comment: str = Field(default="", max_length=4000)
    action: str = Field(default="", max_length=1000)


class TaskCreate(BaseModel):
    patientId: str
    title: str = Field(min_length=2, max_length=255)
    dueAt: datetime


class TaskUpdate(BaseModel):
    status: str = Field(pattern="^(new|working|done|cancelled)$")


class AssignmentCreate(BaseModel):
    template: str | None = Field(default=None, min_length=2, max_length=80)
    versionId: str | None = None
    dueAt: datetime
    purpose: str = Field(default="Наблюдение за состоянием", min_length=2, max_length=255)
    scheduleType: str = Field(default="once", pattern="^(once|daily|weekly|interval)$")
    intervalDays: int | None = Field(default=None, ge=1, le=365)
    scheduledTime: str | None = Field(default=None, pattern="^([01]\\d|2[0-3]):[0-5]\\d$")
    timezone: str = Field(default="Europe/Moscow", min_length=3, max_length=80)
    endAt: datetime | None = None
    reminderAfterMinutes: int | None = Field(default=None, ge=15, le=10080)


class AiRequest(BaseModel):
    patientId: str
    kind: str = Field(min_length=2, max_length=40)


class MedicationReviewUpdate(BaseModel):
    diagnosisConfirmed: bool = False
    firstTwoLinesRefractory: bool = False
    contraindicationsReviewed: bool = False
    restrictions: str = Field(default="", max_length=2000)
    confirmed: bool = False


class AiUpdate(BaseModel):
    text: str = Field(min_length=1)
    status: str = Field(pattern="^(draft|accepted|rejected)$")
    confirmed: bool = False


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    notifications: bool
    reminders: bool


class CheckinCreate(BaseModel):
    anxiety: float | None = Field(default=None, ge=0, le=10)
    mood: float | None = Field(default=None, ge=0, le=10)
    sleepMinutes: int | None = Field(default=None, ge=0, le=1440)
    sleepQuality: str | None = None
    functioning: str | None = None
    newSymptoms: str | None = Field(default=None, max_length=2000)
    requestedContact: bool = False


class QuestionnaireOptionInput(BaseModel):
    value: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=240)
    score: float | None = None


class QuestionnaireQuestionInput(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=2, max_length=1000)
    type: str = Field(pattern="^(single|multiple|number|text)$")
    required: bool = True
    options: list[QuestionnaireOptionInput] = Field(default_factory=list)
    min: float | None = None
    max: float | None = None


class QuestionnaireTemplateCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern="^[A-Za-zА-Яа-я0-9._-]+$")
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="Авторский", min_length=2, max_length=80)
    sourceUrl: str = Field(default="", max_length=500)
    kind: str = Field(default="custom", pattern="^(custom|validated|diary)$")
    version: str = Field(default="1.0", min_length=1, max_length=60)
    instructions: str = Field(default="", max_length=4000)
    questions: list[QuestionnaireQuestionInput] = Field(min_length=1, max_length=100)
    scoring: dict[str, Any] = Field(default_factory=dict)
    alertRules: list[dict[str, Any]] = Field(default_factory=list)
    requiresClinicalApproval: bool = False


class QuestionnaireVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=60)
    instructions: str = Field(default="", max_length=4000)
    questions: list[QuestionnaireQuestionInput] = Field(min_length=1, max_length=100)
    scoring: dict[str, Any] = Field(default_factory=dict)
    alertRules: list[dict[str, Any]] = Field(default_factory=list)
    requiresClinicalApproval: bool = False


class QuestionnairePublish(BaseModel):
    confirmed: bool


class QuestionnaireApproval(BaseModel):
    confirmed: bool


class LegalDocumentCreate(BaseModel):
    kind: str = Field(pattern="^(privacy|personal_data_consent|health_data_consent|max_communications)$")
    version: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=20, max_length=50000)
    requiresReconsent: bool = True
    publish: bool = False


class MaxLinkCreate(BaseModel):
    expiresInMinutes: int = Field(default=1440, ge=5, le=1440)


class ScheduleSettingsUpdate(BaseModel):
    organization: str = Field(min_length=2, max_length=160)
    mode: str = Field(pattern="^(internal|external)$")
    externalUrl: str = Field(default="", max_length=500)


class AppointmentInvitationCreate(BaseModel):
    proposedAt: datetime | None = None
    message: str = Field(default="Врач приглашает вас на приём.", min_length=3, max_length=1000)


class PatientMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
