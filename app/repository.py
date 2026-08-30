import json
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.database import SQLiteDatabase
from app.models import FailureRule, RequestMatch, RuleCreate, SimulatedResponse
from app.project_repository import DEFAULT_PROJECT_ID


class RuleRepository(Protocol):
    def list(self) -> tuple[FailureRule, ...]: ...

    def get(self, rule_id: UUID) -> FailureRule | None: ...

    def create(self, data: RuleCreate) -> FailureRule: ...

    def update(self, rule_id: UUID, data: RuleCreate) -> FailureRule | None: ...

    def set_enabled(
        self,
        rule_id: UUID,
        *,
        enabled: bool,
    ) -> FailureRule | None: ...

    def delete(self, rule_id: UUID) -> bool: ...

    def count_for_project(self, project_id: UUID) -> int: ...


class InMemoryRuleRepository:
    def __init__(self, rules: Sequence[FailureRule] = ()) -> None:
        self._rules = list(rules)

    def list(self) -> tuple[FailureRule, ...]:
        return tuple(self._rules)

    def get(self, rule_id: UUID) -> FailureRule | None:
        return next((rule for rule in self._rules if rule.id == rule_id), None)

    def create(self, data: RuleCreate) -> FailureRule:
        rule = FailureRule(**data.model_dump())
        self._rules.append(rule)
        return rule

    def update(self, rule_id: UUID, data: RuleCreate) -> FailureRule | None:
        index = self._find_index(rule_id)
        if index is None:
            return None

        rule = FailureRule(id=rule_id, **data.model_dump())
        self._rules[index] = rule
        return rule

    def set_enabled(self, rule_id: UUID, *, enabled: bool) -> FailureRule | None:
        index = self._find_index(rule_id)
        if index is None:
            return None

        rule = self._rules[index].model_copy(update={"enabled": enabled})
        self._rules[index] = rule
        return rule

    def delete(self, rule_id: UUID) -> bool:
        index = self._find_index(rule_id)
        if index is None:
            return False

        del self._rules[index]
        return True

    def count_for_project(self, project_id: UUID) -> int:
        return sum(rule.project_id == project_id for rule in self._rules)

    def _find_index(self, rule_id: UUID) -> int | None:
        return next(
            (index for index, rule in enumerate(self._rules) if rule.id == rule_id),
            None,
        )


class SQLiteRuleRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list(self) -> tuple[FailureRule, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM rules ORDER BY sequence"
            ).fetchall()
        return tuple(self._deserialize(row["payload"]) for row in rows)

    def get(self, rule_id: UUID) -> FailureRule | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM rules WHERE id = ?",
                (str(rule_id),),
            ).fetchone()
        return self._deserialize(row["payload"]) if row else None

    def create(self, data: RuleCreate) -> FailureRule:
        rule = FailureRule(**data.model_dump())
        with self._database.connect() as connection:
            connection.execute(
                "INSERT INTO rules (id, project_id, payload) VALUES (?, ?, ?)",
                (
                    str(rule.id),
                    str(rule.project_id) if rule.project_id else None,
                    self._database.serialize(rule),
                ),
            )
        return rule

    def update(self, rule_id: UUID, data: RuleCreate) -> FailureRule | None:
        rule = FailureRule(id=rule_id, **data.model_dump())
        with self._database.connect() as connection:
            cursor = connection.execute(
                "UPDATE rules SET project_id = ?, payload = ? WHERE id = ?",
                (
                    str(rule.project_id) if rule.project_id else None,
                    self._database.serialize(rule),
                    str(rule_id),
                ),
            )
        return rule if cursor.rowcount else None

    def set_enabled(self, rule_id: UUID, *, enabled: bool) -> FailureRule | None:
        current = self.get(rule_id)
        if current is None:
            return None
        rule = current.model_copy(update={"enabled": enabled})
        with self._database.connect() as connection:
            cursor = connection.execute(
                "UPDATE rules SET payload = ? WHERE id = ?",
                (self._database.serialize(rule), str(rule_id)),
            )
        return rule if cursor.rowcount else None

    def delete(self, rule_id: UUID) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM rules WHERE id = ?",
                (str(rule_id),),
            )
        return bool(cursor.rowcount)

    def count_for_project(self, project_id: UUID) -> int:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM rules WHERE project_id = ?",
                (str(project_id),),
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def _deserialize(payload: str) -> FailureRule:
        return FailureRule.model_validate(
            json.loads(payload),
            context={"allow_reserved_paths": True},
        )


def seed_rules() -> tuple[FailureRule, ...]:
    return (
        FailureRule(
            name="Users service unavailable",
            project_id=DEFAULT_PROJECT_ID,
            match=RequestMatch(method="GET", path="/api/users"),
            response=SimulatedResponse(
                status=503,
                headers={"content-type": "application/json"},
                body={"error": "service unavailable"},
            ),
        ),
    )
