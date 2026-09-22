from collections.abc import Sequence
from typing import Protocol

from app.database import SQLiteDatabase
from app.models import (
    DecisionReason,
    RequestHistoryCreate,
    RequestHistoryEntry,
    RequestOutcome,
)


class RequestHistoryRepository(Protocol):
    def list(self, *, limit: int) -> tuple[RequestHistoryEntry, ...]: ...

    def create(self, data: RequestHistoryCreate) -> RequestHistoryEntry: ...


class InMemoryRequestHistoryRepository:
    def __init__(self, entries: Sequence[RequestHistoryEntry] = ()) -> None:
        self._entries = list(entries)
        self._next_id = max((entry.id for entry in entries), default=0) + 1

    def list(self, *, limit: int) -> tuple[RequestHistoryEntry, ...]:
        return tuple(reversed(self._entries[-limit:]))

    def create(self, data: RequestHistoryCreate) -> RequestHistoryEntry:
        entry = RequestHistoryEntry(id=self._next_id, **data.model_dump())
        self._next_id += 1
        self._entries.append(entry)
        return entry


class SQLiteRequestHistoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list(self, *, limit: int) -> tuple[RequestHistoryEntry, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, timestamp, method, path, outcome, decision_reason,
                       status_code, rule_id, duration_ms
                FROM request_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(
            RequestHistoryEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                method=row["method"],
                path=row["path"],
                outcome=RequestOutcome(row["outcome"]),
                decision_reason=(
                    DecisionReason(row["decision_reason"])
                    if row["decision_reason"]
                    else (
                        DecisionReason.ALWAYS
                        if row["outcome"] == RequestOutcome.SIMULATED
                        else DecisionReason.NO_MATCHING_RULE
                    )
                ),
                status_code=row["status_code"],
                rule_id=row["rule_id"],
                duration_ms=row["duration_ms"],
            )
            for row in rows
        )

    def create(self, data: RequestHistoryCreate) -> RequestHistoryEntry:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO request_history (
                    timestamp, method, path, outcome, decision_reason, status_code,
                    rule_id, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.timestamp.isoformat(),
                    data.method,
                    data.path,
                    data.outcome.value,
                    data.decision_reason.value,
                    data.status_code,
                    str(data.rule_id) if data.rule_id else None,
                    data.duration_ms,
                ),
            )
        return RequestHistoryEntry(id=cursor.lastrowid, **data.model_dump())
