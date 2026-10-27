import json
import httpx
import pytest
from app import ai_service as ai


def test_model_markdown_is_converted_to_plain_clinical_text():
    text = ai.plain_text_response("**Изменения:**\n- Проверить данные\n\n\n## Ограничения")
    assert text == "Изменения:\n• Проверить данные\n\nОграничения"


def test_medication_consultation_uses_clear_localized_status():
    from app.api import format_medication_consultation
    text = format_medication_consultation({
        "status": "not_indicated",
        "details": "Диагноз пациента не соответствует показаниям карточки.",
        "disclosure": "Препарат представлен партнёром проекта.",
    })
    assert "Не соответствует настроенным показаниям" in text
    assert "not_indicated" not in text
    assert "**" not in text
    assert "лекарственное предложение для указанного диагноза не сформировано" in text


def test_runtime_uses_local_authenticated_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "BASE_DIR", tmp_path)
    profile = tmp_path / "runtime.json"
    monkeypatch.setattr(ai, "RUNTIME_PROFILE", profile)
    (tmp_path / ".run").mkdir()
    (tmp_path / ".run/ai-adapter.token").write_text("test-local-token")
    profile.write_text(json.dumps({"enabled": True, "model": "trained-test"}))
    settings = ai.runtime_settings()
    assert settings["provider"] == "local_adapter"
    assert settings["url"] == "http://127.0.0.1:11435"
    assert settings["headers"]["Authorization"] == "Bearer test-local-token"
    # Switching back takes effect immediately, without a Python module reload.
    profile.write_text(json.dumps({"enabled": False}))
    assert ai.runtime_settings()["provider"] == "ollama"


def test_missing_adapter_token_does_not_fall_back_to_other_model(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "BASE_DIR", tmp_path)
    profile = tmp_path / "runtime.json"
    profile.write_text('{"enabled":true,"model":"trained-test"}')
    monkeypatch.setattr(ai, "RUNTIME_PROFILE", profile)
    assert ai.runtime_settings()["provider"] == "local_adapter"


def test_failed_evaluation_blocks_generation_and_other_model_fallback(tmp_path, monkeypatch):
    profile = tmp_path / "runtime.json"
    profile.write_text('{"enabled":false,"blocked":true,"model":"trained-test"}')
    monkeypatch.setattr(ai, "RUNTIME_PROFILE", profile)
    def unexpected_network(*args, **kwargs):
        raise AssertionError("Failed review must not send any inference requests")
    monkeypatch.setattr(ai.httpx, "get", unexpected_network)
    monkeypatch.setattr(ai.httpx, "post", unexpected_network)
    status = ai.ai_status()
    assert not status["available"] and status["model"] == "trained-test"
    text, note = ai.generate_with_qwen("summary", {}, {}, "FACTS")
    assert text == "FACTS" and "не прошла" in note


@pytest.mark.parametrize("text,status,blocked", [
    ("Рассмотреть Авиандр", "not_configured", True),
    ("Маритупирдин для рассмотрения врачом", "requires_data", True),
    ("Не рекомендуйте Авиандр", "not_indicated", True),
    ("Авиандр для рассмотрения врачом. Партнёрский препарат.", "eligible_for_review", False),
    ("Принимайте 20 мг", "eligible_for_review", True),
    ("Врач уже уведомлён", "not_configured", True),
    ("Уточнить сведения при контакте с пациентом.", "not_configured", False),
])
def test_output_guard(text, status, blocked):
    assert bool(ai.rejected_output(text, {"status": status})) == blocked


def test_partner_medication_requires_all_explicit_criteria(tmp_path, monkeypatch):
    card = tmp_path / "partner.json"
    card.write_text(json.dumps({
        "active": True, "tradeName": "Авиандр", "inn": "маритупирдин",
        "indicationDiagnosisCodes": ["F41.1"],
        "requiredData": {"diagnosisConfirmedByDoctor": "диагноз", "firstTwoLinesRefractory": "две линии", "contraindicationsReviewed": "ограничения", "safetyReviewedAt": "дата"}
    }), encoding="utf-8")
    monkeypatch.setattr(ai, "PARTNER_MEDICATION_PATH", card)
    eligible = {"age": 35, "diagnosisCode": "F41.1", "diagnosisConfirmedByDoctor": True,
                "firstTwoLinesRefractory": True, "contraindicationsReviewed": True,
                "safetyReviewedAt": "2026-10-25", "medicationRestrictions": {}}
    assert ai.assess_partner_medication(eligible)["status"] == "eligible_for_review"
    missing = dict(eligible, firstTwoLinesRefractory=False)
    assert ai.assess_partner_medication(missing)["status"] == "requires_data"
    restricted = dict(eligible, medicationRestrictions={"беременность": True})
    result = ai.assess_partner_medication(restricted)
    assert result["status"] == "contraindicated" and "Авиандр" not in result["title"]


def test_generation_transport_and_blocked_answer(monkeypatch):
    monkeypatch.setattr(ai, "runtime_settings", lambda: {"provider": "ollama", "url": "http://127.0.0.1:11435", "model": "trained-test", "headers": {"Authorization": "Bearer local"}})
    monkeypatch.setattr(ai, "ai_status", lambda: {"available": True})
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"message": {"content": "Рассмотреть Авиандр"}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(ai.httpx, "post", post)
    text, note = ai.generate_with_qwen("summary", {"age": 20}, {"status": "requires_data"}, "FACTS")
    assert text == "FACTS" and "отклонён" in note
    assert calls[0][1]["headers"] == {"Authorization": "Bearer local"}
    assert calls[0][1]["json"]["model"] == "trained-test"


def test_model_failure_returns_explicit_fallback(monkeypatch):
    monkeypatch.setattr(ai, "runtime_settings", lambda: {"provider": "ollama", "url": "http://127.0.0.1:11435", "model": "trained-test", "headers": {}})
    monkeypatch.setattr(ai, "ai_status", lambda: {"available": True})
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(ai.httpx, "post", fail)
    text, note = ai.generate_with_qwen("summary", {}, {}, "FACTS")
    assert text == "FACTS" and "недоступен" in note


def test_missing_measurements_are_not_converted_to_zero_in_fallback(monkeypatch):
    from datetime import date, datetime
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app import api
    db = Mock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [
            SimpleNamespace(reported_at=datetime(2026, 10, 25), anxiety=None, mood=5, sleep_minutes=None),
            SimpleNamespace(reported_at=datetime(2026, 10, 24), anxiety=7, mood=5, sleep_minutes=420),
        ]), SimpleNamespace(all=lambda: []),
    ]
    db.scalar.return_value = None
    monkeypatch.setattr(api, "adherence_counts", lambda *args: {"confirmed": 0, "planned": 0, "missed": 0, "noData": 0})
    monkeypatch.setattr(api, "assess_partner_medication", lambda *args: {})
    monkeypatch.setattr(api, "generate_with_qwen", lambda kind, context, assessment, fallback: (fallback, "rules"))
    patient = SimpleNamespace(id="synthetic", birth_date=date(1990, 1, 1), sex="female", diagnosis_code=None, diagnosis_title=None)
    text, *_ = api.generate_ai_text(db, patient, "summary")
    assert "Нет пар заполненных показателей" in text
    assert "-7" not in text


def test_medication_review_requires_confirmation_and_patient_cannot_edit():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.seed import normalize_existing_labels
    from app.database import SessionLocal
    with TestClient(app) as client:
        url = "/api/v1/patients/p2/medication-review"
        assert client.get(url).status_code == 401
        client.post("/api/v1/auth/login", json={"login": "Persent", "password": "Admin321"})
        assert client.get(url).json()["contraindicationsReviewed"] is False
        review = {"diagnosisConfirmed": True, "firstTwoLinesRefractory": True,
                  "contraindicationsReviewed": True, "restrictions": "breastfeeding"}
        assert client.put(url, json=review).status_code == 422
        response = client.put(url, json={**review, "confirmed": True})
        assert response.status_code == 200
        assert response.json()["reviewedAt"]
        with SessionLocal() as db:
            normalize_existing_labels(db)
            db.commit()
        assert client.get(url).json()["restrictions"] == "breastfeeding"
        client.post("/api/v1/auth/login", json={"login": "Doctor", "password": "Admin241"})
        assert client.get(url).status_code == 403
        assert client.put(url, json={**review, "confirmed": True}).status_code == 403
