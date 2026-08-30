import json
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.database import SQLiteDatabase
from app.models import Project, ProjectCreate


DEFAULT_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")


class ProjectRepository(Protocol):
    def list(self) -> tuple[Project, ...]: ...

    def get(self, project_id: UUID) -> Project | None: ...

    def create(self, data: ProjectCreate) -> Project: ...

    def update(self, project_id: UUID, data: ProjectCreate) -> Project | None: ...

    def delete(self, project_id: UUID) -> bool: ...


class InMemoryProjectRepository:
    def __init__(self, projects: Sequence[Project] = ()) -> None:
        self._projects = list(projects)

    def list(self) -> tuple[Project, ...]:
        return tuple(self._projects)

    def get(self, project_id: UUID) -> Project | None:
        return next(
            (project for project in self._projects if project.id == project_id),
            None,
        )

    def create(self, data: ProjectCreate) -> Project:
        project = Project(**data.model_dump())
        self._projects.append(project)
        return project

    def update(self, project_id: UUID, data: ProjectCreate) -> Project | None:
        index = self._find_index(project_id)
        if index is None:
            return None
        project = Project(id=project_id, **data.model_dump())
        self._projects[index] = project
        return project

    def delete(self, project_id: UUID) -> bool:
        index = self._find_index(project_id)
        if index is None:
            return False
        del self._projects[index]
        return True

    def _find_index(self, project_id: UUID) -> int | None:
        return next(
            (
                index
                for index, project in enumerate(self._projects)
                if project.id == project_id
            ),
            None,
        )


class SQLiteProjectRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list(self) -> tuple[Project, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM projects ORDER BY sequence"
            ).fetchall()
        return tuple(self._deserialize(row["payload"]) for row in rows)

    def get(self, project_id: UUID) -> Project | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM projects WHERE id = ?",
                (str(project_id),),
            ).fetchone()
        return self._deserialize(row["payload"]) if row else None

    def create(self, data: ProjectCreate) -> Project:
        project = Project(**data.model_dump())
        with self._database.connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, payload) VALUES (?, ?)",
                (str(project.id), self._database.serialize(project)),
            )
        return project

    def update(self, project_id: UUID, data: ProjectCreate) -> Project | None:
        project = Project(id=project_id, **data.model_dump())
        with self._database.connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET payload = ? WHERE id = ?",
                (self._database.serialize(project), str(project_id)),
            )
        return project if cursor.rowcount else None

    def delete(self, project_id: UUID) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (str(project_id),),
            )
        return bool(cursor.rowcount)

    @staticmethod
    def _deserialize(payload: str) -> Project:
        return Project.model_validate(json.loads(payload))


def seed_projects() -> tuple[Project, ...]:
    return (
        Project(
            id=DEFAULT_PROJECT_ID,
            name="Default project",
            description="Default failure simulation scenarios",
        ),
    )
