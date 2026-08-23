from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequestMatch(BaseModel):
    model_config = ConfigDict(frozen=True)
    method: str
    path: str

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("path must start with '/'")
        return value


class SimulatedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    delay_ms: int = Field(default=0, ge=0)


class FailureRule(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = Field(min_length=1)
    enabled: bool = True
    match: RequestMatch
    response: SimulatedResponse

