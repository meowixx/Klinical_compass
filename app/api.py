import json
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai_service import ai_status, assess_partner_medication, generate_with_qwen, load_partner_medication
from app.dashboard import adherence_counts, build_dashboard, serialize_patient
from app.database import get_db
from app.knowledge_base import verify_draft
from app.models import (
    AdverseEvent, AiRecommendation, AuditEvent, ClinicalAlert, ClinicalTask,
    DailyCheckin, DoctorSettings, PatientProfile, Prescription, QuestionnaireAssignment, QuestionnaireVersion, User,
)
from app.schemas import (
    AccountContactUpdate, AdminUserCreate, AdminUserProfileUpdate, AiRequest, AiUpdate, AlertUpdate,
    AssignmentCreate, CheckinCreate, LoginRequest, PatientCreate, SettingsUpdate,
    TaskCreate, TaskUpdate, UserRoleUpdate, MedicationReviewUpdate,
)
from app.max_bot import create_link_code
from app.security import create_session, current_user, hash_password, require_admin, require_doctor, set_session_cookie, verify_password

router = APIRouter(prefix="/api/v1")


def audit(db: Session, actor: str, action: str, entity_id: str) -> None:
    db.add(AuditEvent(id=str(uuid4()), actor=actor, action=action, entity_id=entity_id))


def patient_or_404(db: Session, patient_id: str) -> PatientProfile:
    patient = db.get(PatientProfile, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    return patient


def patient_for_clinician(db: Session, patient_id: str, user: User) -> PatientProfile:
    patient = patient_or_404(db, patient_id)
    if user.role != "admin" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Пациент закреплён за другим лечащим врачом")
    return patient


def normalize_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 10:
        digits = f"7{digits}"
    elif len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return f"+{digits}" if digits else value.strip()


def serialize_user(db: Session, user: User) -> dict[str, str | None]:
    settings = db.scalar(select(DoctorSettings).where(DoctorSettings.user_id == user.id)) if user.role == "doctor" else None
    patient = db.scalar(select(PatientProfile).where(PatientProfile.user_id == user.id)) if user.role == "patient" else None
    return {
        "id": user.id,
        "login": user.login,
        "email": user.email,
        "phone": user.phone,
        "name": user.name,
        "role": user.role,
        "specialty": settings.specialty if settings else None,
        "organization": settings.organization if settings else None,
        "patientId": patient.id if patient else None,
    }


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    identifier = payload.login.strip()
    normalized_phone = normalize_phone(identifier)
    user = db.scalar(
        select(User).where(
            or_(
                func.lower(User.login) == identifier.lower(),
                func.lower(User.email) == identifier.lower(),
                User.phone == normalized_phone,
            )
        )
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин, почта, телефон или пароль")
    set_session_cookie(response, create_session(user))
    return {"user": {"id": user.id, "name": user.name, "role": user.role}, "issuedAt": datetime.utcnow().isoformat()}


@router.get("/admin/users")
def admin_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize_user(db, user) for user in db.scalars(select(User).order_by(User.created_at)).all()]


@router.post("/admin/users", status_code=201)
def create_user(payload: AdminUserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    login = payload.login.strip()
    email = str(payload.email).strip().lower() if payload.email else None
    phone = normalize_phone(payload.phone) if payload.phone else None
    duplicate_filters = [func.lower(User.login) == login.lower()]
    if email:
        duplicate_filters.append(func.lower(User.email) == email)
    if phone:
        if len("".join(character for character in phone if character.isdigit())) != 11:
            raise HTTPException(status_code=422, detail="Укажите российский номер из 11 цифр")
        duplicate_filters.append(User.phone == phone)
    if db.scalar(select(User).where(or_(*duplicate_filters))):
        raise HTTPException(status_code=409, detail="Логин, почта или телефон уже используются")

    user = User(
        id=str(uuid4()),
        login=login,
        email=email,
        phone=phone,
        password_hash=hash_password(payload.password),
        role=payload.role,
        name=payload.name.strip(),
    )
    db.add(user)
    db.flush()
    max_link = None

    if payload.role == "doctor":
        specialty = (payload.specialty or "").strip()
        organization = (payload.organization or "").strip()
        if len(specialty) < 2 or len(organization) < 2:
            raise HTTPException(status_code=422, detail="Укажите специальность и организацию врача")
        db.add(DoctorSettings(id=str(uuid4()), user_id=user.id, specialty=specialty, organization=organization))
    else:
        if payload.patientAge is None or payload.patientSex is None or not (payload.diagnosisCode or "").strip():
            raise HTTPException(status_code=422, detail="Укажите возраст, пол и код диагноза пациента")
        doctor = db.get(User, payload.doctorId) if payload.doctorId else db.scalar(
            select(User).where(User.role == "doctor").order_by(User.created_at)
        )
        if not doctor or doctor.role != "doctor":
            raise HTTPException(status_code=422, detail="Выберите лечащего врача")
        patient = PatientProfile(
            id=str(uuid4()),
            user_id=user.id,
            doctor_id=doctor.id,
            display_name=user.name,
            birth_date=date(datetime.utcnow().year - payload.patientAge, 1, 1),
            sex=payload.patientSex,
            card=f"КК-{datetime.utcnow():%y%m%d%H%M%S}-{uuid4().hex[:4]}",
            diagnosis_code=payload.diagnosisCode.strip(),
            diagnosis_title="Требует проверки врачом",
            diagnosis_status="preliminary",
            complaint="Данные ещё не получены",
            last_contact=datetime.utcnow(),
        )
        db.add(patient)
        db.flush()
        code = create_link_code(db, patient.id, admin.id, 1440)
        max_link = {
            "code": code,
            "expiresAt": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
            "instruction": "Отправьте этот код боту MAX",
        }

    audit(db, admin.name, f"Создана учётная запись {payload.role}: {login}", user.id)
    db.commit()
    return {"account": serialize_user(db, user), "maxLink": max_link}


@router.patch("/admin/users/{user_id}/role")
def update_user_role(user_id: str, payload: UserRoleUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Учётная запись не найдена")
    if user.role == "admin" or user.id == admin.id:
        raise HTTPException(status_code=422, detail="Роль администратора нельзя изменить здесь")
    previous_role = user.role
    user.role = payload.role
    audit(db, admin.name, f"Роль пользователя {user.login}: {previous_role} → {payload.role}", user.id)
    db.commit()
    return serialize_user(db, user)


@router.patch("/admin/users/{user_id}/profile")
def update_user_profile(user_id: str, payload: AdminUserProfileUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Учётная запись не найдена")
    if user.role != "doctor":
        raise HTTPException(status_code=422, detail="Профессиональный профиль доступен только врачу")
    settings = db.scalar(select(DoctorSettings).where(DoctorSettings.user_id == user.id))
    if not settings:
        settings = DoctorSettings(
            id=str(uuid4()),
            user_id=user.id,
            specialty=payload.specialty.strip(),
            organization=payload.organization.strip(),
        )
        db.add(settings)
    user.name = payload.name.strip()
    settings.specialty = payload.specialty.strip()
    settings.organization = payload.organization.strip()
    audit(db, admin.name, f"Обновлён профиль врача {user.login}", user.id)
    db.commit()
    return serialize_user(db, user)


@router.get("/account")
def account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return serialize_user(db, user)


@router.patch("/account/contact")
def update_account_contact(payload: AccountContactUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    phone = normalize_phone(payload.phone)
    if len("".join(character for character in phone if character.isdigit())) != 11:
        raise HTTPException(status_code=422, detail="Укажите российский номер из 11 цифр")
    duplicate = db.scalar(select(User).where(User.id != user.id, or_(func.lower(User.email) == email, User.phone == phone)))
    if duplicate:
        raise HTTPException(status_code=409, detail="Почта или телефон уже привязаны к другой учётной записи")
    user.email, user.phone = email, phone
    audit(db, user.name, "Обновлены контактные данные учётной записи", user.id)
    db.commit()
    return serialize_user(db, user)


@router.post("/auth/refresh", status_code=204)
def refresh(response: Response, user: User = Depends(current_user)):
    set_session_cookie(response, create_session(user))


@router.post("/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("cc_session", path="/")


@router.get("/doctor/dashboard")
def dashboard(user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return build_dashboard(db, user.id if user.role == "doctor" else None)


@router.get("/dashboard")
def role_dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = build_dashboard(db, user.id if user.role == "doctor" else None)
    if user.role != "patient":
        return data
    patient = db.scalar(select(PatientProfile).where(PatientProfile.user_id == user.id))
    if not patient:
        raise HTTPException(status_code=404, detail="К учётной записи не привязан пациент")
    patient_id = patient.id
    data["patients"] = [row for row in data["patients"] if row["id"] == patient_id]
    data["doctorQueue"] = []
    data["alerts"] = [row for row in data["alerts"] if row["patientId"] == patient_id]
    data["tasks"] = [row for row in data["tasks"] if row["patientId"] == patient_id]
    data["assignments"] = [row for row in data["assignments"] if row["patientId"] == patient_id]
    data["recommendations"] = []
    data["audit"] = []
    return data


@router.get("/patients")
def patients(user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return build_dashboard(db, user.id if user.role == "doctor" else None)["patients"]


@router.get("/patients/{patient_id}")
def patient(patient_id: str, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return serialize_patient(db, patient_for_clinician(db, patient_id, user))


@router.post("/patients")
def add_patient(payload: PatientCreate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    doctor_id = user.id if user.role == "doctor" else "doctor-demo"
    item = PatientProfile(
        id=str(uuid4()),
        doctor_id=doctor_id,
        display_name=payload.name.strip(),
        birth_date=date(datetime.utcnow().year - payload.age, 1, 1),
        sex=payload.sex,
        card=f"КК-{datetime.utcnow():%y%m%d%H%M%S}-{uuid4().hex[:4]}",
        diagnosis_code=payload.code.strip(),
        diagnosis_title="Требует проверки врачом",
        diagnosis_status="preliminary",
        complaint="Данные ещё не получены",
        last_contact=datetime.utcnow(),
    )
    db.add(item)
    audit(db, user.name, "Добавлен пациент", item.id)
    db.commit()
    return serialize_patient(db, item)


@router.post("/patients/{patient_id}/checkins", status_code=201)
def add_checkin(patient_id: str, payload: CheckinCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    patient = patient_or_404(db, patient_id)
    if user.role == "patient" and patient.user_id != user.id:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    if user.role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Пациент закреплён за другим лечащим врачом")
    supplied = [payload.anxiety, payload.mood, payload.sleepMinutes, payload.sleepQuality, payload.functioning]
    item = DailyCheckin(
        id=str(uuid4()),
        patient_id=patient_id,
        reported_at=datetime.utcnow(),
        anxiety=payload.anxiety,
        mood=payload.mood,
        sleep_minutes=payload.sleepMinutes,
        sleep_quality=payload.sleepQuality,
        functioning=payload.functioning,
        new_symptoms=payload.newSymptoms,
        requested_contact=payload.requestedContact,
        completeness=sum(value is not None for value in supplied) / len(supplied),
    )
    patient.last_contact = item.reported_at
    db.add(item)
    if payload.requestedContact or payload.newSymptoms:
        db.add(
            ClinicalAlert(
                id=str(uuid4()),
                patient_id=patient_id,
                responsible_doctor_id=patient.doctor_id,
                level="yellow",
                reason="Пациент просит связаться" if payload.requestedContact else "Новое сообщение о возможном нежелательном явлении",
                source=f"Самоотчёт пациента от {item.reported_at:%d.%m.%Y %H:%M}. Требует оценки специалистом.",
            )
        )
    db.commit()
    return {"id": item.id, "reportedAt": item.reported_at.isoformat(), "completeness": item.completeness}


@router.get("/patients/{patient_id}/dynamics")
def dynamics(patient_id: str, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return serialize_patient(db, patient_for_clinician(db, patient_id, user))["dynamics"]


@router.get("/patients/{patient_id}/prescriptions")
def prescriptions(patient_id: str, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return serialize_patient(db, patient_for_clinician(db, patient_id, user))["prescriptions"]


@router.get("/patients/{patient_id}/questionnaires")
def questionnaires(patient_id: str, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return serialize_patient(db, patient_for_clinician(db, patient_id, user))["questionnaires"]


@router.get("/patients/{patient_id}/alerts")
def patient_alerts(patient_id: str, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    patient_for_clinician(db, patient_id, user)
    return [row for row in build_dashboard(db, user.id if user.role == "doctor" else None)["alerts"] if row["patientId"] == patient_id]


@router.get("/alerts")
def alerts(user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return build_dashboard(db, user.id if user.role == "doctor" else None)["alerts"]


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: str, payload: AlertUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    alert = db.get(ClinicalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    patient_for_clinician(db, alert.patient_id, user)
    if payload.status == "closed" and alert.level == "red" and (not payload.comment.strip() or not payload.action.strip()):
        raise HTTPException(status_code=422, detail="Для закрытия критического сигнала укажите действие и комментарий")
    alert.status, alert.comment, alert.action, alert.reviewed_at = payload.status, payload.comment.strip(), payload.action.strip(), datetime.utcnow()
    audit(db, user.name, f"Обновлён сигнал: {alert.reason}", alert.id)
    db.commit()
    return next(row for row in build_dashboard(db, user.id if user.role == "doctor" else None)["alerts"] if row["id"] == alert.id)


@router.post("/patients/{patient_id}/tasks")
def add_task(patient_id: str, payload: TaskCreate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    patient_for_clinician(db, patient_id, user)
    if payload.patientId != patient_id:
        raise HTTPException(status_code=422, detail="Пациент в адресе и теле запроса не совпадает")
    item = ClinicalTask(id=str(uuid4()), patient_id=patient_id, title=payload.title.strip(), due_at=payload.dueAt)
    db.add(item)
    audit(db, user.name, f"Создана задача: {item.title}", patient_id)
    db.commit()
    return {"id": item.id, "patientId": patient_id, "title": item.title, "dueAt": item.due_at.isoformat(), "status": item.status}


@router.patch("/tasks/{task_id}", status_code=204)
def update_task(task_id: str, payload: TaskUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    item = db.get(ClinicalTask, task_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    patient_for_clinician(db, item.patient_id, user)
    item.status = payload.status
    audit(db, user.name, f"Статус задачи «{item.title}»: {payload.status}", item.id)
    db.commit()


@router.post("/patients/{patient_id}/questionnaires")
def assign_questionnaire(patient_id: str, payload: AssignmentCreate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    patient = patient_for_clinician(db, patient_id, user)
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="Опросник назначает лечащий врач")
    version = db.get(QuestionnaireVersion, payload.versionId) if payload.versionId else None
    if payload.versionId and (not version or version.status != "published"):
        raise HTTPException(status_code=422, detail="Выберите опубликованную версию опросника")
    template_name = version.template.title if version and version.template else payload.template
    if not template_name:
        raise HTTPException(status_code=422, detail="Выберите опросник")
    if payload.scheduleType == "interval" and not payload.intervalDays:
        raise HTTPException(status_code=422, detail="Для интервального расписания укажите число дней")
    if payload.endAt and payload.endAt < payload.dueAt:
        raise HTTPException(status_code=422, detail="Дата окончания не может быть раньше первой отправки")
    item = QuestionnaireAssignment(
        id=str(uuid4()),
        patient_id=patient_id,
        doctor_id=patient.doctor_id,
        version_id=version.id if version else None,
        template=template_name,
        due_at=payload.dueAt,
        purpose=payload.purpose.strip(),
        schedule_type=payload.scheduleType,
        interval_days=payload.intervalDays,
        scheduled_time=payload.scheduledTime,
        timezone=payload.timezone,
        start_at=payload.dueAt,
        end_at=payload.endAt,
        reminder_after_minutes=payload.reminderAfterMinutes,
        delivery_channel="max",
    )
    db.add(item)
    audit(db, user.name, f"Назначен опросник «{template_name}»", patient_id)
    db.commit()
    return {
        "id": item.id,
        "patientId": patient_id,
        "template": item.template,
        "versionId": item.version_id,
        "assignedAt": item.assigned_at.isoformat(),
        "dueAt": item.due_at.isoformat(),
        "status": item.status,
    }


def patient_ai_context(db: Session, patient: PatientProfile) -> tuple[dict, list[DailyCheckin], dict, AdverseEvent | None]:
    checkins = db.scalars(
        select(DailyCheckin).where(DailyCheckin.patient_id == patient.id).order_by(DailyCheckin.reported_at.desc()).limit(2)
    ).all()
    counts = adherence_counts(db, patient.id)
    event = db.scalar(select(AdverseEvent).where(AdverseEvent.patient_id == patient.id).order_by(AdverseEvent.started_at.desc()))
    prescriptions = db.scalars(
        select(Prescription).where(Prescription.patient_id == patient.id, Prescription.status == "active")
    ).all()
    today = date.today()
    age = today.year - patient.birth_date.year - ((today.month, today.day) < (patient.birth_date.month, patient.birth_date.day))
    context = {
        "patientId": patient.id,
        "asOf": today.isoformat(),
        "scaleDirections": {"anxiety": "0..10, выше — хуже", "mood": "0..10, выше — лучше", "sleepMinutes": "минуты"},
        "age": age,
        "sex": patient.sex,
        "diagnosisCode": patient.diagnosis_code,
        "diagnosisTitle": patient.diagnosis_title,
        "diagnosisConfirmedByDoctor": getattr(patient, "diagnosis_status", "preliminary") == "confirmed",
        "treatmentHistory": {
            "firstTwoLinesRefractory": getattr(patient, "first_two_lines_refractory", False),
            "adequacyAndAdherenceReviewedByDoctor": getattr(patient, "first_two_lines_refractory", False),
        },
        "firstTwoLinesRefractory": getattr(patient, "first_two_lines_refractory", False),
        "latestCheckins": [
            {
                "reportedAt": row.reported_at.isoformat(),
                "anxiety": row.anxiety,
                "mood": row.mood,
                "sleepMinutes": row.sleep_minutes,
            }
            for row in checkins
        ],
        "adherence": counts,
        "latestAdverseEvent": event.description if event else None,
        "currentMedications": [row.medication_name for row in prescriptions],
        "allergies": None,
        "contraindicationsReviewed": getattr(patient, "contraindications_reviewed", False),
        "safetyReviewedAt": patient.safety_reviewed_at.isoformat() if getattr(patient, "safety_reviewed_at", None) else None,
        "medicationRestrictions": json.loads(getattr(patient, "medication_restrictions_json", "{}") or "{}"),
    }
    return context, checkins, counts, event


def verify_ai_text(text: str, context: dict) -> dict | None:
    """Ground the draft in the КР/ГРЛС knowledge base; a missing or broken dataset must not block the draft."""
    medication = load_partner_medication()
    aliases = [[medication.get("tradeName", ""), medication.get("inn", "")]] if medication else []
    try:
        return verify_draft(text, context, aliases)
    except (OSError, ValueError, KeyError):
        return None


def generate_ai_text(db: Session, patient: PatientProfile, kind: str) -> tuple[str, str, str, dict | None]:
    context, checkins, counts, event = patient_ai_context(db, patient)
    change = "Недостаточно последовательных записей для сравнения."
    if len(checkins) > 1:
        changes = []
        if checkins[0].anxiety is not None and checkins[1].anxiety is not None:
            changes.append(f"тревога {checkins[0].anxiety - checkins[1].anxiety:+.2f} балла")
        if checkins[0].sleep_minutes is not None and checkins[1].sleep_minutes is not None:
            changes.append(f"сон {checkins[0].sleep_minutes - checkins[1].sleep_minutes:+g} мин")
        change = "; ".join(changes) + "." if changes else "Нет пар заполненных показателей для сравнения."
    fallback = (
        f"Изменения: {change}\n"
        f"Терапия: подтверждено пациентом {counts['confirmed']} из {counts['planned']}; явные пропуски — {counts['missed']}; нет сведений — {counts['noData']}.\n"
        f"Переносимость: {event.description if event else 'новых сообщений нет'}.\n"
        f"Недостающие данные: {'есть приёмы без ответа' if counts['noData'] else 'по отметкам терапии нет'}.\n"
        f"Для проверки врачом: уточнить переносимость, фактический режим приёма и дальнейший план наблюдения."
    )
    medication = assess_partner_medication(context)
    if kind == "questions":
        fallback = (
            "1. Как изменились самочувствие, тревога и сон со времени последнего отчёта?\n"
            "2. Удалось ли соблюдать назначенный режим лечения? Были ли пропуски или трудности?\n"
            "3. Появились ли нежелательные реакции или новые жалобы?\n"
            "4. Какие изменения сильнее всего мешают повседневной жизни?"
        )
    elif kind == "sources":
        fallback = (
            "Врачу следует сверить актуальные клинические рекомендации по подтверждённому диагнозу "
            "в рубрикаторе Минздрава: https://cr.minzdrav.gov.ru/\n"
            "Инструкцию, противопоказания и взаимодействия — в ГРЛС: https://grls.rosminzdrav.ru/\n"
            "Тексты документов автоматически не загружены; соответствие конкретной редакции не подтверждено."
        )
    elif kind == "risks":
        fallback = "Факторы для проверки врачом:\n" + fallback
    elif kind == "note":
        fallback = "Черновик записи врача по самоотчётам пациента:\n" + fallback
    elif kind == "changes":
        fallback = f"Изменения по двум последним самоотчётам: {change}\nДата последней записи: {checkins[0].reported_at.isoformat() if checkins else 'нет данных'}. Данные требуют сопоставления с текущим состоянием."
    text, model_note = generate_with_qwen(kind, context, medication, fallback)
    if medication.get("status") == "eligible_for_review" and "авиандр" not in text.casefold():
        text += (
            "\n\nВозможное действие: врач может рассмотреть Авиандр (маритупирдин) после проверки "
            "актуальной инструкции и взаимодействий. Препарат партнёра; решение принимает врач."
        )
    if kind == "medication":
        text = (
            f"Формальная проверка: {medication['title']}\n"
            f"Статус: {medication['status']}\n"
            f"Результат: {medication['details']}\n"
            f"Раскрытие: {medication['disclosure']}\n\n{text}"
        )
    verification = verify_ai_text(text, context)
    check_note = (
        f" Проверка по базе знаний: ссылок на КР — {len(verification['citations'])}, препаратов в тексте — {len(verification['medications'])}."
        if verification else " Проверка по базе знаний недоступна."
    )
    data = (
        f"Самоотчёты: {len(checkins)} последних записи; источник — пациент; "
        f"последняя запись — {checkins[0].reported_at.isoformat() if checkins else 'нет данных'}. "
        f"Обработка: {model_note}.{check_note}"
    )
    return text, data, "Требует самостоятельной проверки врачом. Изменение после назначения терапии не доказывает причинную связь.", verification


def medication_review_payload(patient: PatientProfile):
    restrictions = json.loads(patient.medication_restrictions_json or "{}")
    return {
        "diagnosisConfirmed": patient.diagnosis_status == "confirmed",
        "firstTwoLinesRefractory": patient.first_two_lines_refractory,
        "contraindicationsReviewed": patient.contraindications_reviewed,
        "restrictions": "\n".join(key for key, active in restrictions.items() if active),
        "reviewedAt": patient.safety_reviewed_at.isoformat() if patient.safety_reviewed_at else None,
    }


@router.get("/patients/{patient_id}/medication-review")
def get_medication_review(patient_id: str, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return medication_review_payload(patient_for_clinician(db, patient_id, user))


@router.put("/patients/{patient_id}/medication-review")
def save_medication_review(patient_id: str, payload: MedicationReviewUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    patient = patient_for_clinician(db, patient_id, user)
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="Проверку подтверждает лечащий врач")
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Подтвердите сохранение проверки врачом")
    patient.diagnosis_status = "confirmed" if payload.diagnosisConfirmed else "preliminary"
    patient.first_two_lines_refractory = payload.firstTwoLinesRefractory
    patient.contraindications_reviewed = payload.contraindicationsReviewed
    patient.safety_reviewed_at = datetime.utcnow() if payload.contraindicationsReviewed else None
    patient.medication_restrictions_json = json.dumps(
        {line.strip(): True for line in payload.restrictions.splitlines() if line.strip()}, ensure_ascii=False)
    audit(db, user.name, "Обновлена проверка лекарственного предложения врачом", patient_id)
    db.commit()
    return medication_review_payload(patient)


@router.get("/ai/status")
def get_ai_status(_: User = Depends(require_doctor)):
    return ai_status()


@router.post("/ai/summary")
@router.post("/ai/recommendation")
def generate_ai(payload: AiRequest, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    patient = patient_for_clinician(db, payload.patientId, user)
    text, data, risks, verification = generate_ai_text(db, patient, payload.kind)
    item = AiRecommendation(
        id=str(uuid4()),
        patient_id=patient.id,
        kind=payload.kind,
        text=text,
        data=data,
        risks=risks,
        limitations="Локальный ИИ-черновик. Не является диагнозом или назначением. Медицинские и партнёрские предложения требуют проверки врачом по официальной инструкции.",
        source_ids="doc1,doc2",
        verification_json=json.dumps(verification or {}, ensure_ascii=False),
    )
    db.add(item)
    audit(db, user.name, "Сформирован структурированный ИИ-черновик", patient.id)
    db.commit()
    return {
        "id": item.id,
        "patientId": item.patient_id,
        "kind": item.kind,
        "text": item.text,
        "data": item.data,
        "risks": item.risks,
        "limitations": item.limitations,
        "sourceIds": item.source_ids.split(","),
        "verification": verification,
        "createdAt": item.created_at.isoformat(),
        "status": item.status,
    }


@router.patch("/ai/recommendations/{item_id}", status_code=204)
def update_ai(item_id: str, payload: AiUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    item = db.get(AiRecommendation, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    patient = patient_for_clinician(db, item.patient_id, user)
    if payload.status == "accepted" and not payload.confirmed:
        raise HTTPException(status_code=422, detail="Требуется подтверждение врача")
    text = payload.text.strip()
    if text != item.text:
        # The doctor may add or change a drug while editing; the check must describe the saved text.
        item.verification_json = json.dumps(verify_ai_text(text, patient_ai_context(db, patient)[0]) or {}, ensure_ascii=False)
    item.text, item.status = text, payload.status
    audit(db, user.name, f"Статус ИИ-черновика: {payload.status}", item.patient_id)
    db.commit()


@router.get("/clinical-documents")
def documents(_: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return build_dashboard(db)["documents"]


@router.get("/audit")
def audit_log(user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return build_dashboard(db, None if user.role == "admin" else user.id)["audit"]


@router.patch("/settings", status_code=204)
def save_settings(payload: SettingsUpdate, user: User = Depends(require_doctor), db: Session = Depends(get_db)):
    doctor = db.get(User, "doctor-demo" if user.role == "admin" else user.id)
    if not doctor:
        doctor = user
    settings = db.scalar(select(DoctorSettings).where(DoctorSettings.user_id == doctor.id))
    if not settings:
        settings = DoctorSettings(id=str(uuid4()), user_id=doctor.id, specialty="Не указана", organization="Не указана")
        db.add(settings)
    settings.notifications, settings.reminders = payload.notifications, payload.reminders
    audit(db, user.name, "Обновлены настройки уведомлений", doctor.id)
    db.commit()
