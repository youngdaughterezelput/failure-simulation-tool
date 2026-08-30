from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "Payments QA",
                    "description": "Failure scenarios for the payments API",
                }
            ]
        },
    )

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)


class Project(ProjectCreate):
    id: UUID = Field(default_factory=uuid4)
