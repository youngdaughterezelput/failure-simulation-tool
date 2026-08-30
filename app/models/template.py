from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.rule import RequestMatch, SimulatedResponse


class FailureTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    response: SimulatedResponse


class RuleFromTemplateCreate(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "Checkout dependency unavailable",
                    "enabled": True,
                    "project_id": "00000000-0000-0000-0000-000000000001",
                    "match": {"method": "POST", "path": "/api/checkout"},
                }
            ]
        },
    )

    name: str | None = Field(default=None, min_length=1)
    enabled: bool = True
    project_id: UUID | None = None
    match: RequestMatch
