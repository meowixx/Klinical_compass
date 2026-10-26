from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.max_bot import send_main_menu
from app.models import LegalDocumentVersion, MaxUserBinding, QuestionnaireAssignment


def test_doctor_dashboard_contains_explainable_queue(tmp_path, monkeypatch):
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"login": "Persent", "password": "Admin321"})
        assert login.status_code == 200
        dashboard = client.get("/api/v1/doctor/dashboard")
        assert dashboard.status_code == 200
        data = dashboard.json()
        assert data["doctorQueue"]
        anna = next(item for item in data["doctorQueue"] if item["patientId"] == "p1")
        assert anna["adherence"] == {"planned": 14, "confirmed": 10, "missed": 2, "different": 0, "noData": 2}
        assert anna["source"] == "patient_self_report"
        assert anna["recommendedAction"]


def test_missing_data_is_not_green():
    with TestClient(app) as client:
        client.post("/api/v1/auth/login", json={"login": "Persent", "password": "Admin321"})
        queue = client.get("/api/v1/doctor/dashboard").json()["doctorQueue"]
        stale = next(item for item in queue if item["patientId"] == "p4")
        assert stale["status"] == "gray"
        assert "Нет ответов" in stale["reason"]


def test_patient_dashboard_contains_only_linked_patient():
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"login": "Doctor", "password": "Admin241"})
        assert login.status_code == 200
        response = client.get("/api/v1/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert [patient["id"] for patient in data["patients"]] == ["p1"]
        assert data["doctorQueue"] == []
        assert data["audit"] == []


def test_red_alert_requires_documented_action_to_close():
    with TestClient(app) as client:
        client.post("/api/v1/auth/login", json={"login": "Persent", "password": "Admin321"})
        response = client.patch("/api/v1/alerts/a1", json={"status": "closed", "comment": "", "action": ""})
        assert response.status_code == 422


def test_login_accepts_email_and_phone():
    with TestClient(app) as client:
        by_email = client.post("/api/v1/auth/login", json={"login": "doctor@clinical-compass.local", "password": "Admin321"})
        assert by_email.status_code == 200
        assert by_email.json()["user"]["role"] == "doctor"

        by_phone = client.post("/api/v1/auth/login", json={"login": "8 (999) 000-00-03", "password": "Admin241"})
        assert by_phone.status_code == 200
        assert by_phone.json()["user"]["role"] == "patient"


def test_max_legal_documents_are_published_on_startup():
    with TestClient(app):
        with SessionLocal() as db:
            rows = db.scalars(
                select(LegalDocumentVersion).where(LegalDocumentVersion.is_active.is_(True))
            ).all()
            assert {row.kind for row in rows} == {
                "privacy",
                "personal_data_consent",
                "health_data_consent",
                "max_communications",
            }


def test_daily_checkin_is_assigned_and_max_menu_has_profile(monkeypatch):
    sent = []
    monkeypatch.setattr("app.max_bot.send_message", lambda user_id, text, rows=None: sent.append((user_id, text, rows)))
    with TestClient(app):
        with SessionLocal() as db:
            assignment = db.scalar(
                select(QuestionnaireAssignment).where(
                    QuestionnaireAssignment.patient_id == "p1",
                    QuestionnaireAssignment.version_id == "version-daily-checkin-1",
                    QuestionnaireAssignment.status == "assigned",
                )
            )
            assert assignment is not None
            binding = db.scalar(select(MaxUserBinding).where(MaxUserBinding.patient_id == "p1"))
            if not binding:
                binding = MaxUserBinding(patient_id="p1", max_user_id="max-test", status="active")
                db.add(binding)
                db.flush()
            send_main_menu(db, binding)
    payloads = [button["payload"] for row in sent[-1][2] for button in row]
    assert "profile:show" in payloads
    assert "state:message" in payloads


def test_doctor_can_send_and_read_max_messages(monkeypatch):
    delivered = []
    monkeypatch.setattr("app.integration_api.send_message", lambda user_id, text, rows=None: delivered.append((user_id, text)))
    with TestClient(app) as client:
        with SessionLocal() as db:
            binding = db.scalar(select(MaxUserBinding).where(MaxUserBinding.patient_id == "p1"))
            if not binding:
                binding = MaxUserBinding(patient_id="p1", max_user_id="max-test", status="active")
                db.add(binding)
            binding.status = "active"
            db.flush()
            from app.models import MaxConsent
            for document in db.scalars(select(LegalDocumentVersion).where(LegalDocumentVersion.is_active.is_(True))):
                db.add(MaxConsent(binding_id=binding.id, legal_document_id=document.id))
            db.commit()
        assert client.post("/api/v1/auth/login", json={"login": "Persent", "password": "Admin321"}).status_code == 200
        sent = client.post("/api/v1/messages/p1", json={"text": "Как вы себя чувствуете сегодня?"})
        assert sent.status_code == 201
        thread = client.get("/api/v1/messages/p1")
        assert thread.status_code == 200
        assert thread.json()[-1]["text"] == "Как вы себя чувствуете сегодня?"
        assert delivered and delivered[-1][0] == "max-test"


def test_admin_can_assign_doctor_or_patient_role():
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"login": "Admin", "password": "AdminAIMPY"})
        assert login.status_code == 200
        users = client.get("/api/v1/admin/users")
        assert users.status_code == 200
        assert {item["role"] for item in users.json()} >= {"admin", "doctor", "patient"}

        changed = client.patch("/api/v1/admin/users/patient-demo/role", json={"role": "doctor"})
        assert changed.status_code == 200
        assert changed.json()["role"] == "doctor"
        restored = client.patch("/api/v1/admin/users/patient-demo/role", json={"role": "patient"})
        assert restored.status_code == 200


def test_doctor_changes_contacts_but_admin_controls_professional_profile():
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"login": "Persent", "password": "Admin321"}).status_code == 200
        original = client.get("/api/v1/account").json()
        changed_contact = client.patch("/api/v1/account/contact", json={"email": "doctor.updated@example.com", "phone": "+7 999 111-22-33"})
        assert changed_contact.status_code == 200
        assert changed_contact.json()["email"] == "doctor.updated@example.com"

        doctor_settings = client.patch("/api/v1/settings", json={"name": "Чужое имя", "specialty": "Другая специальность", "organization": "Другая организация", "notifications": True, "reminders": True})
        assert doctor_settings.status_code == 204
        assert client.get("/api/v1/dashboard").json()["settings"]["name"] == original["name"]

        client.patch("/api/v1/account/contact", json={"email": original["email"], "phone": original["phone"]})
        client.post("/api/v1/auth/login", json={"login": "Admin", "password": "AdminAIMPY"})
        changed_profile = client.patch("/api/v1/admin/users/doctor-demo/profile", json={"name": "Елена Тестовая", "specialty": "Врач-тестировщик", "organization": "Тестовая клиника"})
        assert changed_profile.status_code == 200
        assert changed_profile.json()["name"] == "Елена Тестовая"
        restored_profile = client.patch("/api/v1/admin/users/doctor-demo/profile", json={"name": original["name"], "specialty": original["specialty"], "organization": original["organization"]})
        assert restored_profile.status_code == 200
