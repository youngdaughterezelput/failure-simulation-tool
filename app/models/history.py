from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class RequestHistoryEntry(RequestHistoryCreate):
    id: int
