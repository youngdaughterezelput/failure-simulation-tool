from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.project import Project
from app.models.rule import FailureRule


CONFIGURATION_KIND = "failure-simulation-configuration"
CONFIGURATION_SCHEMA_VERSION = 1
MAX_CONFIGURATION_ITEMS = 10_000


class ConfigurationDocument(BaseModel):
    """Portable, versioned representation of user-managed configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["failure-simulation-configuration"]
    schema_version: Literal[1]
    projects: tuple[Project, ...] = Field(max_length=MAX_CONFIGURATION_ITEMS)
    rules: tuple[FailureRule, ...] = Field(max_length=MAX_CONFIGURATION_ITEMS)

    @model_validator(mode="after")
    def validate_graph(self) -> "ConfigurationDocument":
        project_ids = [project.id for project in self.projects]
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("project ids must be unique")

        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule ids must be unique")

        known_project_ids = set(project_ids)
        unknown_project_ids = {
            rule.project_id
            for rule in self.rules
            if rule.project_id is not None
            and rule.project_id not in known_project_ids
        }
        if unknown_project_ids:
            formatted = ", ".join(
                str(project_id)
                for project_id in sorted(unknown_project_ids, key=str)
            )
            raise ValueError(f"rules reference unknown project ids: {formatted}")
        return self


class ConfigurationImportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    projects_imported: int = Field(ge=0)
    rules_imported: int = Field(ge=0)
    runtime_states_reset: int = Field(ge=0)
    dry_run: bool
