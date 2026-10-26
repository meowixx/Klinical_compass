import json
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AdverseEvent, CareRelationship, ClinicalAlert, ClinicalDocument, ClinicalTask,
    DailyCheckin, DoctorSettings, NextContact, PatientProfile, Prescription,
    LegalDocumentVersion, QuestionnaireAssignment, QuestionnaireResponse,
    QuestionnaireTemplate, QuestionnaireVersion, TherapyIntake, User,
)
from app.security import hash_password

DEMO_NOW = datetime(2026, 10, 16, 12, 0)


def seed_questionnaire_library(db: Session) -> None:
    if not db.get(User, "admin-demo"):
        return
    if not db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == "DAILY-CHECKIN")):
        template = QuestionnaireTemplate(
            id="template-daily-checkin",
            code="DAILY-CHECKIN",
            title="Ежедневный дневник состояния",
            description="Короткий авторский дневник для наблюдения между визитами.",
            category="Дневник",
            kind="diary",
            status="published",
            created_by_user_id="admin-demo",
        )
        questions = [
            {"id": "wellbeing", "text": "Как вы оцениваете общее самочувствие сегодня?", "type": "number", "required": True, "options": [], "min": 0, "max": 10},
            {"id": "anxiety", "text": "Насколько выражена тревога сейчас?", "type": "number", "required": True, "options": [], "min": 0, "max": 10},
            {"id": "sleep", "text": "Сколько часов вы спали?", "type": "number", "required": True, "options": [], "min": 0, "max": 24},
            {"id": "changes", "text": "Что изменилось в состоянии?", "type": "text", "required": False, "options": [], "min": None, "max": None},
            {
                "id": "contact",
                "text": "Нужно ли, чтобы лечащий врач связался с вами?",
                "type": "single",
                "required": True,
                "options": [
                    {"value": "no", "label": "Нет", "score": 0},
                    {"value": "yes", "label": "Да", "score": 0},
                ],
                "min": None,
                "max": None,
            },
        ]
        version = QuestionnaireVersion(
            id="version-daily-checkin-1",
            template=template,
            version="1.0",
            instructions="Отвечайте исходя из своего состояния сегодня.",
            questions_json=json.dumps(questions, ensure_ascii=False),
            scoring_json="{}",
            alert_rules_json=json.dumps(
                [
                    {"questionId": "contact", "operator": "eq", "value": "yes", "level": "yellow", "reason": "Пациент просит связаться"},
                    {"questionId": "anxiety", "operator": "gte", "value": 8, "level": "yellow", "reason": "Высокая самооценка тревоги в дневнике"},
                ],
                ensure_ascii=False,
            ),
            status="published",
            created_by_user_id="admin-demo",
            published_at=datetime.utcnow(),
        )
        db.add_all([template, version])
    placeholders = [
        ("HADS", "HADS", "Тревога и депрессивные симптомы", "https://clinica.samsmu.ru/wp-content/uploads/2025/08/hads.pdf"),
        ("BECK", "Шкала депрессии Бека", "Депрессивные симптомы", "https://mgppu.ru/resources/files/fkc_metod/2.4.3%20Шкала%20депрессии%20Бека.pdf"),
    ]
    for code, title, description, source_url in placeholders:
        if not db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == code)):
            db.add(
                QuestionnaireTemplate(
                    code=code,
                    title=title,
                    description=f"{description}. Требуется заполнить вопросы, проверить версию и получить клиническое утверждение.",
                    category="Клиническая шкала",
                    source_url=source_url,
                    kind="validated",
                    status="draft",
                    created_by_user_id="admin-demo",
                )
            )


def seed_daily_assignments(db: Session) -> None:
    db.flush()
    version = db.get(QuestionnaireVersion, "version-daily-checkin-1")
    if not version:
        return
    for patient in db.scalars(select(PatientProfile).where(PatientProfile.user_id.is_not(None))):
        existing = db.scalar(
            select(QuestionnaireAssignment).where(
                QuestionnaireAssignment.patient_id == patient.id,
                QuestionnaireAssignment.version_id == version.id,
            )
        )
        if existing:
            continue
        db.add(
            QuestionnaireAssignment(
                patient_id=patient.id,
                template="Ежедневный дневник состояния",
                due_at=datetime.utcnow(),
                version_id=version.id,
                doctor_id=patient.doctor_id,
                purpose="Ежедневная оценка самочувствия между визитами",
                schedule_type="daily",
                scheduled_time="09:00",
                start_at=datetime.utcnow(),
                reminder_after_minutes=240,
                delivery_channel="max",
            )
        )


DEFAULT_LEGAL_DOCUMENTS = [
    (
        "privacy",
        "Политика обработки персональных данных",
        "Медицинская организация, выдавшая учётную запись, обрабатывает данные для идентификации пациента, работы сервиса, направления опросников и наблюдения лечащим врачом. В системе могут храниться идентификаторы учётной записи и MAX, контактные данные, ответы на опросники и сообщения о самочувствии. Медицинская карточка и история наблюдения через MAX не выдаются. Отозвать согласие и получить сведения об обработке можно через клинику.",
    ),
    (
        "personal_data_consent",
        "Согласие на обработку персональных данных",
        "Я даю медицинской организации, выдавшей мне учётную запись, согласие на сбор, запись, систематизацию, хранение, уточнение и использование моих идентификационных и контактных данных, идентификатора MAX, ответов на опросники и обращений. Обработка выполняется для подключения к сервису, связи со мной и передачи моих ответов лечащему врачу. Согласие действует до отзыва либо окончания установленного срока хранения. Отзыв можно направить через клинику.",
    ),
    (
        "health_data_consent",
        "Согласие на обработку сведений о здоровье",
        "Я даю согласие на обработку сообщённых мной сведений о самочувствии и здоровье для дистанционного наблюдения и оценки лечащим врачом. Ответы доступны уполномоченным сотрудникам клиники. Бот не ставит диагноз, не назначает лечение и не заменяет экстренную медицинскую помощь.",
    ),
    (
        "max_communications",
        "Согласие на взаимодействие через MAX",
        "Я согласен получать в MAX назначенные врачом опросники, напоминания и приглашения на приём, а также передавать через бот ответы и сообщения о самочувствии. Карточка пациента, история наблюдения и медицинские документы доступны только в защищённом кабинете сайта и не отправляются ботом MAX.",
    ),
]


def seed_legal_documents(db: Session) -> None:
    """Ensure that a fresh/local installation can complete MAX onboarding.

    Administrator-published active versions are preserved. Older placeholder drafts
    remain in the audit trail and can still be replaced through the admin API.
    """
    if not db.get(User, "admin-demo"):
        return
    published_at = datetime.utcnow()
    for kind, title, content in DEFAULT_LEGAL_DOCUMENTS:
        active = db.scalar(
            select(LegalDocumentVersion).where(
                LegalDocumentVersion.kind == kind,
                LegalDocumentVersion.is_active.is_(True),
            )
        )
        if active:
            continue
        existing = db.scalar(
            select(LegalDocumentVersion).where(
                LegalDocumentVersion.kind == kind,
                LegalDocumentVersion.version == "1.0",
            )
        )
        if existing:
            existing.title = title
            existing.content = content
            existing.is_active = True
            existing.requires_reconsent = True
            existing.published_at = existing.published_at or published_at
        else:
            db.add(
                LegalDocumentVersion(
                    kind=kind,
                    version="1.0",
                    title=title,
                    content=content,
                    is_active=True,
                    requires_reconsent=True,
                    created_by_user_id="admin-demo",
                    published_at=published_at,
                )
            )


def normalize_existing_labels(db: Session) -> None:
    """Update labels created by older local seed versions without touching user data."""
    replacements = {
        "Клиника «Гармония» · демо": "Клиника «Гармония»",
        "Тестовый сценарий сниженного настроения": "Сниженное настроение",
        "Тестовый сценарий тревожной симптоматики": "Тревожная симптоматика",
        "Демонстрационная терапия": "Назначенная терапия",
        "Учебная схема, два приёма в день": "Два приёма в день",
        "Русская исследовательская версия · демо": "Русская исследовательская версия",
        "Демо 1.0": "1.0",
        "Демонстрационная карточка. Врач проверяет актуальный официальный источник.": "Справочная карточка. Врач проверяет актуальный официальный источник.",
        "Учебный пример поиска инструкции.": "Карточка поиска инструкции.",
    }
    for settings in db.scalars(select(DoctorSettings)):
        settings.organization = replacements.get(settings.organization, settings.organization)
    for patient in db.scalars(select(PatientProfile)):
        patient.diagnosis_title = replacements.get(patient.diagnosis_title, patient.diagnosis_title)
    for prescription in db.scalars(select(Prescription)):
        prescription.medication_name = replacements.get(prescription.medication_name, prescription.medication_name)
        prescription.regimen = replacements.get(prescription.regimen, prescription.regimen)
    for response in db.scalars(select(QuestionnaireResponse)):
        response.source_version = replacements.get(response.source_version, response.source_version)
    for document in db.scalars(select(ClinicalDocument)):
        document.version = replacements.get(document.version, document.version)
        document.text = replacements.get(document.text, document.text)


def seed_database(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(User)):
        contacts = {
            "admin-demo": ("admin@clinical-compass.local", "+79990000001"),
            "doctor-demo": ("doctor@clinical-compass.local", "+79990000002"),
            "patient-demo": ("patient@clinical-compass.local", "+79990000003"),
        }
        for user_id, (email, phone) in contacts.items():
            user = db.get(User, user_id)
            if user:
                user.email = user.email or email
                user.phone = user.phone or phone
        normalize_existing_labels(db)
        for alert in db.scalars(select(ClinicalAlert).where(ClinicalAlert.responsible_doctor_id.is_(None))):
            patient = db.get(PatientProfile, alert.patient_id)
            if patient:
                alert.responsible_doctor_id = patient.doctor_id
        seed_questionnaire_library(db)
        seed_daily_assignments(db)
        seed_legal_documents(db)
        db.commit()
        return

    doctor = User(
        id="doctor-demo",
        login="Persent",
        email="doctor@clinical-compass.local",
        phone="+79990000002",
        password_hash=hash_password("Admin321"),
        role="doctor",
        name="Елена Смирнова",
    )
    admin = User(
        id="admin-demo",
        login="Admin",
        email="admin@clinical-compass.local",
        phone="+79990000001",
        password_hash=hash_password("AdminAIMPY"),
        role="admin",
        name="Администратор",
    )
    patient_user = User(
        id="patient-demo",
        login="Doctor",
        email="patient@clinical-compass.local",
        phone="+79990000003",
        password_hash=hash_password("Admin241"),
        role="patient",
        name="Анна К.",
    )

    # 1. Сначала добавляем и фиксируем пользователей
    db.add_all([doctor, admin, patient_user])
    db.flush()

    # 2. Только после этого добавляем настройки врача, которые ссылаются на doctor.id
    db.add(
        DoctorSettings(
            id="settings-demo",
            user_id=doctor.id,
            specialty="Врач-невролог",
            organization="Клиника «Гармония»",
        )
    )
    db.flush()

    patient_specs = [
        ("p1", "Анна К.", date(1992, 4, 8), "Ж", "F32.0", "Сниженное настроение", "#e6d6d0", 0, True),
        ("p2", "Михаил С.", date(1974, 2, 14), "М", "F41.1", "Тревожная симптоматика", "#d7e6e8", 1, False),
        ("p3", "Ольга Н.", date(1985, 9, 3), "Ж", "F32.0", "Сниженное настроение", "#ede1d2", 4, False),
        ("p4", "Сергей П.", date(1966, 7, 21), "М", "F41.1", "Тревожная симптоматика", "#dbe2ef", 8, False),
    ]
    for index, (pid, name, born, sex, code, title, color, stale_days, critical) in enumerate(patient_specs, start=1):
        patient = PatientProfile(
            id=pid,
            user_id="patient-demo" if pid == "p1" else None,
            doctor_id=doctor.id,
            display_name=name,
            birth_date=born,
            sex=sex,
            card=f"КК-2026-{index:03d}",
            diagnosis_code=code,
            diagnosis_title=title,
            diagnosis_status="confirmed" if index % 2 else "preliminary",
            complaint="Усиление тревоги, прерывистый сон и снижение активности." if critical else "Колебания настроения и тревоги в течение дня.",
            color=color,
            last_contact=DEMO_NOW - timedelta(days=stale_days),
        )
        db.add(patient)
        db.flush()

        db.add(CareRelationship(id=str(uuid4()), doctor_id=doctor.id, patient_id=pid))
        for day in range(7):
            when = DEMO_NOW - timedelta(days=6 - day + stale_days)
            db.add(
                DailyCheckin(
                    id=str(uuid4()),
                    patient_id=pid,
                    reported_at=when,
                    anxiety=min(10, 5 + (day * 0.55 if critical else (index % 2) - day * 0.12)),
                    mood=max(0, 6 - (day * 0.45 if critical else index * 0.15)),
                    sleep_minutes=300 + day * 12 if critical else 420 + day * 5,
                    sleep_quality="частично" if critical else "хорошо",
                    functioning="сильно" if critical else "немного",
                    new_symptoms="Дневная сонливость" if critical and day == 6 else None,
                    source="patient_self_report",
                    completeness=1.0,
                )
            )
        prescription = Prescription(
            id=f"rx{index}",
            patient_id=pid,
            medication_name="Назначенная терапия",
            regimen="Два приёма в день",
            started_on=date(2026, 9, 16),
            ended_on=date(2026, 11, 16),
        )
        db.add(prescription)
        db.flush()

        statuses = (["taken"] * 10 + ["missed"] * 2 + ["no_data"] * 2) if critical else (["taken"] * 13 + ["no_data"])
        for dose, status in enumerate(statuses):
            scheduled = DEMO_NOW - timedelta(hours=(13 - dose) * 12)
            db.add(
                TherapyIntake(
                    id=str(uuid4()),
                    prescription_id=prescription.id,
                    scheduled_at=scheduled,
                    status=status,
                    reason="забыл" if status == "missed" else None,
                    reported_at=scheduled + timedelta(minutes=15) if status != "no_data" else None,
                )
            )
        db.add(
            QuestionnaireResponse(
                id=str(uuid4()),
                patient_id=pid,
                template="GAD-7",
                source_version="Русская исследовательская версия",
                completed_at=DEMO_NOW - timedelta(days=1 + stale_days),
                score=17 if critical else 8,
                previous_score=10 if critical else 9,
            )
        )

    db.add_all(
        [
            AdverseEvent(
                id="ae1",
                patient_id="p1",
                prescription_id="rx1",
                description="Сообщение пациента о дневной сонливости",
                started_at=DEMO_NOW - timedelta(days=2),
                ongoing=True,
                impact="мешает обычным делам",
                review_status="needs_review",
            ),
            ClinicalAlert(
                id="a1",
                patient_id="p1",
                responsible_doctor_id=doctor.id,
                level="red",
                reason="Ухудшение самочувствия и пропуски терапии",
                source="Дневник: тревога выросла, сон сократился. Два явных пропуска, по двум приёмам нет данных.",
                created_at=DEMO_NOW - timedelta(hours=22),
                delivered_at=DEMO_NOW - timedelta(hours=21, minutes=59),
            ),
            ClinicalAlert(
                id="a2",
                patient_id="p3",
                responsible_doctor_id=doctor.id,
                level="yellow",
                reason="Нет ответов четыре дня",
                source="Последний самоотчёт пациента получен 12 октября.",
                created_at=DEMO_NOW - timedelta(days=1),
                delivered_at=DEMO_NOW - timedelta(days=1),
            ),
            ClinicalTask(
                id="t1",
                patient_id="p1",
                title="Проверить переносимость и фактический режим приёма",
                due_at=DEMO_NOW + timedelta(hours=3),
            ),
            ClinicalTask(
                id="t2",
                patient_id="p3",
                title="Связаться с пациентом: нет актуальных данных",
                due_at=DEMO_NOW - timedelta(days=1),
                status="working",
            ),
            NextContact(id="nc1", patient_id="p1", scheduled_at=DEMO_NOW + timedelta(hours=3),
                        kind="Повторная консультация"),
            NextContact(id="nc2", patient_id="p2", scheduled_at=DEMO_NOW + timedelta(days=3),
                        kind="Проверка состояния"),
            QuestionnaireAssignment(
                id="qa1",
                patient_id="p3",
                template="PHQ-9",
                assigned_at=DEMO_NOW - timedelta(days=2),
                due_at=DEMO_NOW - timedelta(days=1),
            ),
            ClinicalDocument(
                id="doc1",
                title="Тревожная симптоматика: наблюдение",
                category="Клинические рекомендации",
                organization="Каталог Минздрава России",
                version="1.0",
                published=date(2026, 9, 1),
                checked=date(2026, 10, 16),
                code="F41.1",
                text="Справочная карточка. Врач проверяет актуальный официальный источник.",
                url="https://cr.minzdrav.gov.ru/",
            ),
            ClinicalDocument(
                id="doc2",
                title="ГРЛС: проверка инструкции препарата",
                category="Инструкции ГРЛС",
                organization="Государственный реестр лекарственных средств",
                version="1.0",
                published=date(2026, 9, 1),
                checked=date(2026, 10, 16),
                text="Карточка поиска инструкции.",
                url="https://grls.rosminzdrav.ru/",
            ),
        ]
    )
    seed_questionnaire_library(db)
    seed_daily_assignments(db)
    seed_legal_documents(db)
    db.commit()
