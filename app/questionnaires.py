import json
import math
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuestionnaireTemplate, QuestionnaireVersion


def json_load(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def serialize_version(version: QuestionnaireVersion, include_questions: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": version.id,
        "templateId": version.template_id,
        "version": version.version,
        "instructions": version.instructions,
        "status": version.status,
        "requiresClinicalApproval": version.requires_clinical_approval,
        "approvedByUserId": version.approved_by_user_id,
        "createdAt": version.created_at.isoformat(),
        "publishedAt": version.published_at.isoformat() if version.published_at else None,
    }
    if include_questions:
        result.update(
            questions=json_load(version.questions_json, []),
            scoring=json_load(version.scoring_json, {}),
            alertRules=json_load(version.alert_rules_json, []),
        )
    return result


def serialize_template(template: QuestionnaireTemplate, include_versions: bool = True) -> dict[str, Any]:
    versions = sorted(template.versions, key=lambda item: (item.created_at, item.version), reverse=True)
    result: dict[str, Any] = {
        "id": template.id,
        "code": template.code,
        "title": template.title,
        "description": template.description,
        "category": template.category,
        "sourceUrl": template.source_url,
        "kind": template.kind,
        "status": template.status,
        "createdAt": template.created_at.isoformat(),
        "updatedAt": template.updated_at.isoformat(),
        "publishedVersion": next((serialize_version(row) for row in versions if row.status == "published"), None),
    }
    if include_versions:
        result["versions"] = [serialize_version(row) for row in versions]
    return result


def published_version_or_404(db: Session, version_id: str) -> QuestionnaireVersion:
    version = db.get(QuestionnaireVersion, version_id)
    if not version or version.status != "published":
        raise HTTPException(status_code=404, detail="Опубликованная версия опросника не найдена")
    return version


def validate_answers(version: QuestionnaireVersion, answers: dict[str, Any], complete: bool = True) -> None:
    questions = json_load(version.questions_json, [])
    for question in questions:
        key = question.get("id")
        if not key:
            continue
        value = answers.get(key)
        if complete and question.get("required", True) and (value is None or value == "" or value == []):
            raise HTTPException(status_code=422, detail=f"Нет ответа на обязательный вопрос: {question.get('text', key)}")
        if value is None:
            continue
        kind = question.get("type")
        options = [option.get("value") for option in question.get("options", [])]
        if kind == "single" and value not in options:
            raise HTTPException(status_code=422, detail=f"Недопустимый ответ на вопрос {key}")
        if kind == "multiple" and (not isinstance(value, list) or any(item not in options for item in value)):
            raise HTTPException(status_code=422, detail=f"Недопустимый ответ на вопрос {key}")
        if kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise HTTPException(status_code=422, detail=f"Ответ на вопрос {key} должен быть числом")
            if question.get("min") is not None and value < question["min"]:
                raise HTTPException(status_code=422, detail=f"Ответ на вопрос {key} меньше допустимого")
            if question.get("max") is not None and value > question["max"]:
                raise HTTPException(status_code=422, detail=f"Ответ на вопрос {key} больше допустимого")
        if kind == "text" and (not isinstance(value, str) or len(value) > 4000):
            raise HTTPException(status_code=422, detail=f"Недопустимый текстовый ответ на вопрос {key}")


def calculate_score(version: QuestionnaireVersion, answers: dict[str, Any]) -> float | None:
    if json_load(version.scoring_json, {}).get("mode") != "sum":
        return None
    questions = json_load(version.questions_json, [])
    total = 0.0
    scored = False
    for question in questions:
        value = answers.get(question.get("id"))
        if value is None:
            continue
        if question.get("type") == "number":
            total += float(value)
            scored = True
            continue
        option_scores = {option.get("value"): option.get("score") for option in question.get("options", [])}
        selected = value if isinstance(value, list) else [value]
        for selected_value in selected:
            score = option_scores.get(selected_value)
            if score is not None:
                total += float(score)
                scored = True
    return total if scored else None


def matched_alerts(version: QuestionnaireVersion, answers: dict[str, Any], score: float | None) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for rule in json_load(version.alert_rules_json, []):
        actual = score if rule.get("field") == "totalScore" else answers.get(rule.get("questionId"))
        expected = rule.get("value")
        operator = rule.get("operator", "eq")
        matched = False
        if actual is not None:
            if operator == "eq":
                matched = actual == expected
            elif operator == "gte" and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
                matched = actual >= expected
            elif operator == "lte" and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
                matched = actual <= expected
            elif operator == "contains":
                matched = expected in actual if isinstance(actual, (list, str)) else False
        if matched:
            matches.append({"level": rule.get("level", "yellow"), "reason": rule.get("reason", "Ответ требует внимания врача")})
    return matches


def list_published_templates(db: Session) -> list[QuestionnaireTemplate]:
    return db.scalars(
        select(QuestionnaireTemplate).where(QuestionnaireTemplate.status == "published").order_by(QuestionnaireTemplate.title)
    ).all()


def touch(template: QuestionnaireTemplate) -> None:
    template.updated_at = datetime.utcnow()
