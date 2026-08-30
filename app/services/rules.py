from uuid import UUID

from app.models import FailureRule, RuleCreate, RuleFromTemplateCreate
from app.project_repository import ProjectRepository
from app.repository import RuleRepository
from app.templates import FailureTemplateCatalog


class RuleService:
    """Application service for rule management use cases."""

    def __init__(
        self,
        repository: RuleRepository,
        template_catalog: FailureTemplateCatalog,
        project_repository: ProjectRepository,
    ) -> None:
        self._repository = repository
        self._template_catalog = template_catalog
        self._project_repository = project_repository

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
            )
        )

    def update(self, rule_id: UUID, data: RuleCreate) -> FailureRule | None:
        self._validate_project(data.project_id)
        return self._repository.update(rule_id, data)

    def set_enabled(self, rule_id: UUID, *, enabled: bool) -> FailureRule | None:
        return self._repository.set_enabled(rule_id, enabled=enabled)

    def delete(self, rule_id: UUID) -> bool:
        return self._repository.delete(rule_id)

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
