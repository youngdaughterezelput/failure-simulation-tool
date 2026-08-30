from enum import StrEnum
from uuid import UUID

from app.models import Project, ProjectCreate
from app.project_repository import ProjectRepository
from app.repository import RuleRepository


class ProjectDeleteResult(StrEnum):
    DELETED = "deleted"
    NOT_FOUND = "not_found"
    IN_USE = "in_use"


class ProjectService:
    def __init__(
        self, repository: ProjectRepository, rule_repository: RuleRepository,) -> None:
        self._repository = repository
        self._rule_repository = rule_repository

    def list(self) -> tuple[Project, ...]:
        return self._repository.list()

    def create(self, data: ProjectCreate) -> Project:
        return self._repository.create(data)

    def update(
        self, project_id: UUID, data: ProjectCreate,) -> Project | None:
        return self._repository.update(project_id, data)

    def delete(self, project_id: UUID) -> ProjectDeleteResult:
        if self._repository.get(project_id) is None:
            return ProjectDeleteResult.NOT_FOUND
        if self._rule_repository.count_for_project(project_id):
            return ProjectDeleteResult.IN_USE
        self._repository.delete(project_id)
        return ProjectDeleteResult.DELETED
