"""Contract between the AI draft (Qwen) and the judge."""
from typing import Literal

from pydantic import BaseModel, Field


class Complaint(BaseModel):
    date: str | None = None
    text: str = Field(min_length=1)


class Patient(BaseModel):
    """Same field names as the AI context in app/api.py, plus the complaint texts."""
    age: int | None = None
    sex: str | None = None  # «Ж» / «М»
    diagnosisCode: str | None = None
    diagnosisTitle: str | None = None
    currentMedications: list[str] = []
    allergies: str | None = None
    pregnancyStatus: Literal["unknown", "no", "pregnant", "lactation"] | None = None
    medicationRestrictions: dict[str, bool] = {}
    complaints: list[Complaint] = []


class Symptom(BaseModel):
    term: str = Field(min_length=1)
    quote: str = ""
    date: str | None = None


class Draft(BaseModel):
    """What Qwen returns for the «разбор жалоб» task."""
    symptoms: list[Symptom] = []
    possible_match: str | None = None
    to_check: list[str] = []


class JudgeRequest(BaseModel):
    patient: Patient
    draft: Draft
