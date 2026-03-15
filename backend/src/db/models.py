import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ExtractFrNfrRequest(BaseModel):
    requirement: str
    requirement_type: Literal["requirement", "SRS", "PRD"] = "requirement"


class GenerateFromSessionRequest(BaseModel):
    pass


class GenerateRequest(BaseModel):
    requirement: str
    requirement_type: Literal["requirement", "SRS", "PRD"] = "requirement"


class GenerateResponse(BaseModel):
    id: uuid.UUID
    status: str


class ValidationResult(BaseModel):
    coverage_score: float
    missing_areas: list[str]
    feedback: str
    is_sufficient: bool


class SessionResponse(BaseModel):
    id: uuid.UUID
    requirement: str | None = None
    requirement_type: str | None = None
    status: str | None = None
    fr_nfr: dict[str, Any] | None = None
    testcases: list[Any] | None = None
    validation: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
