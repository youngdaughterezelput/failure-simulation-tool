import sqlite3
from collections.abc import Sequence
from threading import RLock
from typing import Protocol

from app.database import SQLiteDatabase
from app.models import (
    DecisionReason,
    HistoryQuery,
    RequestHistoryCreate,
    RequestHistoryEntry,
    RequestOutcome,
)


class HistoryPersistenceError(RuntimeError):
    """Raised when the history store cannot complete an operation."""


class RequestHistoryReader(Protocol):
    def list(self, query: HistoryQuery) -> tuple[RequestHistoryEntry, ...]: ...


class RequestHistoryWriter(Protocol):
    def create(self, data: RequestHistoryCreate) -> RequestHistoryEntry: ...


class RequestHistoryRepository(RequestHistoryReader, RequestHistoryWriter, Protocol):
    pass


class InMemoryRequestHistoryRepository:
    def __init__(self, entries: Sequence[RequestHistoryEntry] = ()) -> None:
        self._entries = sorted(entries, key=lambda entry: entry.id)
        self._next_id = max((entry.id for entry in entries), default=0) + 1
        self._lock = RLock()

    def list(self, query: HistoryQuery) -> tuple[RequestHistoryEntry, ...]:
        with self._lock:
            candidates = (
                entry
                for entry in reversed(self._entries)
                if query.before_id is None or entry.id < query.before_id
            )
            result: list[RequestHistoryEntry] = []
            for entry in candidates:
                result.append(entry)
                if len(result) == query.limit:
                    break
            return tuple(result)

    def create(self, data: RequestHistoryCreate) -> RequestHistoryEntry:
        with self._lock:
            entry = RequestHistoryEntry(id=self._next_id, **data.model_dump())
            self._next_id += 1
            self._entries.append(entry)
            return entry


class SQLiteRequestHistoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list(self, query: HistoryQuery) -> tuple[RequestHistoryEntry, ...]:
        try:
            with self._database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT id, timestamp, method, path, outcome, decision_reason,
                           status_code, rule_id, duration_ms
                    FROM request_history
                    WHERE (? IS NULL OR id < ?)
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (query.before_id, query.before_id, query.limit),
                ).fetchall()
        except sqlite3.Error as error:
            raise HistoryPersistenceError(
                "Could not read request history"
            ) from error
        return tuple(self._deserialize(row) for row in rows)

    def create(self, data: RequestHistoryCreate) -> RequestHistoryEntry:
        try:
            with self._database.connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO request_history (
                        timestamp, method, path, outcome, decision_reason,
                        status_code, rule_id, duration_ms
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
        except sqlite3.Error as error:
            raise HistoryPersistenceError(
                "Could not persist request history"
            ) from error
        return RequestHistoryEntry(id=cursor.lastrowid, **data.model_dump())

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> RequestHistoryEntry:
        return RequestHistoryEntry(
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
