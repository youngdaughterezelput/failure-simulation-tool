from uuid import UUID

from app.models import (
    FailureRule,
    RuleCreate,
    RuleFromTemplateCreate,
    RuleRuntimeState,
)
from app.project_repository import ProjectRepository
from app.repository import RuleRepository
from app.runtime_repository import RuleRuntimeRepository
from app.templates import FailureTemplateCatalog


class RuleService:
    """Application service for rule management use cases."""

    def __init__(
        self,
        repository: RuleRepository,
        template_catalog: FailureTemplateCatalog,
        project_repository: ProjectRepository,
        runtime_repository: RuleRuntimeRepository,
    ) -> None:
        self._repository = repository
        self._template_catalog = template_catalog
        self._project_repository = project_repository
        self._runtime_repository = runtime_repository

    def list(self) -> tuple[FailureRule, ...]:
        return self._repository.list()

    def create(self, data: RuleCreate) -> FailureRule:
        self._validate_project(data.project_id)
        return self._repository.create(data)

    def create_from_template(
        self, template_id: str, data: RuleFromTemplateCreate,) -> FailureRule | None:
        template = self._template_catalog.get(template_id)
        if template is None:
            return None
        self._validate_project(data.project_id)
        return self._repository.create(
            RuleCreate(
                name=data.name or template.name,
                enabled=data.enabled,
                project_id=data.project_id,
                match=data.match,
                response=template.response,
                behavior=data.behavior,
            )
        )

    def update(self, rule_id: UUID, data: RuleCreate) -> FailureRule | None:
        self._validate_project(data.project_id)
        return self._repository.update(rule_id, data)

    def set_enabled(self, rule_id: UUID, *, enabled: bool) -> FailureRule | None:
        return self._repository.set_enabled(rule_id, enabled=enabled)

    def delete(self, rule_id: UUID) -> bool:
        deleted = self._repository.delete(rule_id)
        if deleted:
            self._runtime_repository.delete(rule_id)
        return deleted

    def list_states(self) -> tuple[RuleRuntimeState, ...]:
        return tuple(
            self._runtime_repository.get(rule.id)
            for rule in self._repository.list()
        )

    def reset_state(self, rule_id: UUID) -> RuleRuntimeState | None:
        if self._repository.get(rule_id) is None:
            return None
        return self._runtime_repository.reset(rule_id)

    def _validate_project(self, project_id: UUID | None) -> None:
        if (
            project_id is not None
            and self._project_repository.get(project_id) is None
        ):
            raise ProjectNotFoundError(project_id)


class ProjectNotFoundError(ValueError):
    def __init__(self, project_id: UUID) -> None:
        self.project_id = project_id
        super().__init__(f"Project {project_id} was not found")
