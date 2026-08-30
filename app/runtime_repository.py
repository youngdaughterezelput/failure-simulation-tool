from typing import Protocol
from uuid import UUID

from app.database import SQLiteDatabase
from app.models import RuleRuntimeState


class RuleRuntimeRepository(Protocol):
    def get(self, rule_id: UUID) -> RuleRuntimeState: ...

    def save(self, state: RuleRuntimeState) -> RuleRuntimeState: ...

    def reset(self, rule_id: UUID) -> RuleRuntimeState: ...

    def delete(self, rule_id: UUID) -> None: ...


class InMemoryRuleRuntimeRepository:
    def __init__(self) -> None:
        self._states: dict[UUID, RuleRuntimeState] = {}

    def get(self, rule_id: UUID) -> RuleRuntimeState:
        return self._states.get(rule_id, RuleRuntimeState(rule_id=rule_id))

    def save(self, state: RuleRuntimeState) -> RuleRuntimeState:
        self._states[state.rule_id] = state
        return state

    def reset(self, rule_id: UUID) -> RuleRuntimeState:
        self._states.pop(rule_id, None)
        return RuleRuntimeState(rule_id=rule_id)

    def delete(self, rule_id: UUID) -> None:
        self._states.pop(rule_id, None)


class SQLiteRuleRuntimeRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get(self, rule_id: UUID) -> RuleRuntimeState:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT matched_count, simulated_count, last_triggered_at
                FROM rule_runtime_state
                WHERE rule_id = ?
                """,
                (str(rule_id),),
            ).fetchone()
        if row is None:
            return RuleRuntimeState(rule_id=rule_id)
        return RuleRuntimeState(
            rule_id=rule_id,
            matched_count=row["matched_count"],
            simulated_count=row["simulated_count"],
            last_triggered_at=row["last_triggered_at"],
        )

    def save(self, state: RuleRuntimeState) -> RuleRuntimeState:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO rule_runtime_state (
                    rule_id, matched_count, simulated_count, last_triggered_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    matched_count = excluded.matched_count,
                    simulated_count = excluded.simulated_count,
                    last_triggered_at = excluded.last_triggered_at
                """,
                (
                    str(state.rule_id),
                    state.matched_count,
                    state.simulated_count,
                    (
                        state.last_triggered_at.isoformat()
                        if state.last_triggered_at
                        else None
                    ),
                ),
            )
        return state

    def reset(self, rule_id: UUID) -> RuleRuntimeState:
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM rule_runtime_state WHERE rule_id = ?",
                (str(rule_id),),
            )
        return RuleRuntimeState(rule_id=rule_id)

    def delete(self, rule_id: UUID) -> None:
        self.reset(rule_id)
