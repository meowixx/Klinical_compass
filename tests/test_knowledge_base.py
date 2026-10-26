from fastapi.testclient import TestClient

from app import knowledge_base as kb

GAD_CONTEXT = {"diagnosisCode": "F41.1", "diagnosisTitle": "Генерализованное тревожное расстройство", "age": 34}
VENLAFAXINE_DRAFT = (
    "Изменения: тревога +1.50 балла. "
    "Возможное действие: врач может рассмотреть назначение венлафаксина после оценки артериального давления."
)


def medication(result, name):
    return next(item for item in result["medications"] if item["name"].startswith(name))


def test_lexicon_contains_guideline_drugs_but_not_ordinary_words():
    lexicon = kb.drug_lexicon()
    assert {"венлафаксин", "сертралин", "эсциталопрам", "кветиапин"} <= lexicon
    assert not {"помощь", "потенциал", "кислоты"} & lexicon
    assert kb.find_drugs("Помощь врача и потенциал терапии обсуждены с пациентом.") == []


def test_drug_is_checked_against_register_guideline_doses_and_contraindications():
    context = {**GAD_CONTEXT, "medicationRestrictions": {"венлафаксин: неконтролируемая гипертензия": True}}
    result = kb.verify_draft(VENLAFAXINE_DRAFT, context)
    drug = medication(result, "Венлафаксин")
    assert drug["drugClass"] == "СИОЗСН"
    assert drug["registry"]["status"] == "active"
    assert all(entry["registrationNumber"] for entry in drug["registry"]["entries"])
    assert any("75-225 мг/сут" in item["quote"] and "#page=" in item["url"] for item in drug["dosing"])
    assert any("артериальной гипертензии" in item["quote"] for item in drug["contraindications"])
    assert drug["patientConflicts"] == ["Врач указал ограничение: «венлафаксин: неконтролируемая гипертензия»."]
    assert any("вне инструкции" in warning for warning in result["warnings"])
    assert result["guideline"]["docId"] == "457_3"


def test_trade_name_and_inn_of_partner_drug_form_one_entry():
    draft = "Возможное действие: врач может рассмотреть Авиандр (маритупирдин) после проверки инструкции."
    result = kb.verify_draft(draft, GAD_CONTEXT, [["Авиандр", "маритупирдин"]])
    assert [item["name"] for item in result["medications"]] == ["Авиандр (маритупирдин)"]
    drug = result["medications"][0]
    assert [entry["registrationNumber"] for entry in drug["registry"]["entries"]] == ["ЛП-№(002445)-(РГ-RU)"]
    # The guideline spells the INN "маритупердин"; the dose must still be found.
    assert any("40 мг/сут" in item["quote"] for item in drug["dosing"])


def test_drug_missing_from_register_is_flagged():
    result = kb.verify_draft("Врач может рассмотреть Несуществин.", GAD_CONTEXT, [["Несуществин"]])
    drug = medication(result, "Несуществин")
    assert drug["registry"]["status"] == "not_found"
    assert any("не найден в ГРЛС" in warning for warning in result["warnings"])


def test_duplicate_therapy_and_minor_age_are_patient_conflicts():
    context = {**GAD_CONTEXT, "age": 16, "currentMedications": ["Эсциталопрам 10 мг"]}
    drug = medication(kb.verify_draft("Рассмотреть сертралин.", context), "Сертралин")
    assert "В активных назначениях уже есть препарат класса СИОЗС: Эсциталопрам 10 мг." in drug["patientConflicts"]
    assert any("меньше 18 лет" in conflict for conflict in drug["patientConflicts"])


def test_statements_are_classified():
    result = kb.verify_draft(VENLAFAXINE_DRAFT, GAD_CONTEXT)
    statuses = {item["text"]: item["status"] for item in result["statements"]}
    assert statuses["Изменения: тревога +1.50 балла."] == "patient_data"
    supported = next(item for item in result["statements"] if "венлафаксина" in item["text"])
    assert supported["status"] == "supported"
    assert supported["citation"]["url"].startswith("https://cr.minzdrav.gov.ru/view-cr/")


def test_api_stores_verification_and_rechecks_doctor_edits(monkeypatch):
    from app import api
    monkeypatch.setattr(api, "generate_with_qwen", lambda kind, context, assessment, fallback: (VENLAFAXINE_DRAFT, "test"))
    with TestClient(app_instance()) as client:
        client.post("/api/v1/auth/login", json={"login": "Persent", "password": "Admin321"})
        created = client.post("/api/v1/ai/summary", json={"patientId": "p2", "kind": "summary"}).json()
        names = [item["name"] for item in created["verification"]["medications"]]
        assert "Венлафаксин" in names
        edited = "Возможное действие: врач может рассмотреть кветиапин."
        assert client.patch(f"/api/v1/ai/recommendations/{created['id']}", json={"text": edited, "status": "draft"}).status_code == 204
        stored = next(item for item in client.get("/api/v1/doctor/dashboard").json()["recommendations"] if item["id"] == created["id"])
        assert [item["name"] for item in stored["verification"]["medications"]] == ["Кветиапин"]


def app_instance():
    from app.main import app
    return app
