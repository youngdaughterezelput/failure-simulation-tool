from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.behavior import DecisionReason


class RequestOutcome(StrEnum):
    SIMULATED = "simulated"
    PROXIED = "proxied"


class RequestHistoryCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    method: str = Field(min_length=1)
    path: str = Field(min_length=1)
    outcome: RequestOutcome
    decision_reason: DecisionReason
    status_code: int = Field(ge=100, le=599)
    rule_id: UUID | None = None
    duration_ms: int = Field(ge=0)

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()


class RequestHistoryEntry(RequestHistoryCreate):
    id: int


class RecordRequestCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: str = Field(min_length=1)
    path: str = Field(min_length=1)
    outcome: RequestOutcome
    decision_reason: DecisionReason
    status_code: int = Field(ge=100, le=599)
    rule_id: UUID | None = None
    duration_ms: int = Field(ge=0)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()


class HistoryQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit: int = Field(default=100, ge=1, le=500)
    before_id: int | None = Field(default=None, ge=1)
