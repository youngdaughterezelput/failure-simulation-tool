import json
from typing import Protocol

from app.database import SQLiteDatabase
from app.models import ConfigurationDocument, FailureRule, Project
from app.models.configuration import (
    CONFIGURATION_KIND,
    CONFIGURATION_SCHEMA_VERSION,
)
from app.project_repository import InMemoryProjectRepository
from app.repository import InMemoryRuleRepository
from app.runtime_repository import InMemoryRuleRuntimeRepository


class ConfigurationRepository(Protocol):
    def export(self) -> ConfigurationDocument: ...

    def replace(self, document: ConfigurationDocument) -> int: ...


class InMemoryConfigurationRepository:
    def __init__(
        self,
        project_repository: InMemoryProjectRepository,
        rule_repository: InMemoryRuleRepository,
        runtime_repository: InMemoryRuleRuntimeRepository,
    ) -> None:
        self._project_repository = project_repository
        self._rule_repository = rule_repository
        self._runtime_repository = runtime_repository

    def export(self) -> ConfigurationDocument:
        return ConfigurationDocument(
            kind=CONFIGURATION_KIND,
            schema_version=CONFIGURATION_SCHEMA_VERSION,
            projects=self._project_repository.list(),
            rules=self._rule_repository.list(),
        )

    def replace(self, document: ConfigurationDocument) -> int:
        runtime_states_reset = self._runtime_repository.clear()
        self._project_repository.replace_all(document.projects)
        self._rule_repository.replace_all(document.rules)
        return runtime_states_reset


class SQLiteConfigurationRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def export(self) -> ConfigurationDocument:
        with self._database.connect() as connection:
            connection.execute("BEGIN")
            project_rows = connection.execute(
                "SELECT payload FROM projects ORDER BY sequence"
            ).fetchall()
            rule_rows = connection.execute(
                "SELECT payload FROM rules ORDER BY sequence"
            ).fetchall()
        return ConfigurationDocument(
            kind=CONFIGURATION_KIND,
            schema_version=CONFIGURATION_SCHEMA_VERSION,
            projects=tuple(
                Project.model_validate(json.loads(row["payload"]))
                for row in project_rows
            ),
            rules=tuple(
                FailureRule.model_validate(
                    json.loads(row["payload"]),
                    context={"allow_reserved_paths": True},
                )
                for row in rule_rows
            ),
        )

    def replace(self, document: ConfigurationDocument) -> int:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            runtime_states_reset = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM rule_runtime_state"
                ).fetchone()["count"]
            )
            connection.execute("DELETE FROM rules")
            connection.execute("DELETE FROM projects")
            connection.executemany(
                "INSERT INTO projects (id, payload) VALUES (?, ?)",
                [
                    (str(project.id), self._database.serialize(project))
                    for project in document.projects
                ],
            )
            connection.executemany(
                "INSERT INTO rules (id, project_id, payload) VALUES (?, ?, ?)",
                [
                    (
                        str(rule.id),
                        str(rule.project_id) if rule.project_id else None,
                        self._database.serialize(rule),
                    )
                    for rule in document.rules
                ],
            )
        return runtime_states_reset
