import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from pydantic import BaseModel

from app.models import FailureRule, Project


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    project_id TEXT REFERENCES projects(id) ON DELETE RESTRICT,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS rules_project_id_idx ON rules(project_id);

CREATE TABLE IF NOT EXISTS request_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('simulated', 'proxied')),
    status_code INTEGER NOT NULL,
    rule_id TEXT,
    duration_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS request_history_timestamp_idx
    ON request_history(timestamp DESC);
"""


class SQLiteDatabase:
    """Owns SQLite initialization and short-lived transactional connections."""

    def __init__(
        self,
        path: str,
        *,
        seed_projects: Sequence[Project] = (),
        seed_rules: Sequence[FailureRule] = (),
    ) -> None:
        self._path = path
        self._seed_projects = tuple(seed_projects)
        self._seed_rules = tuple(seed_rules)
        self._initialized = False
        self._lock = RLock()
        self._is_memory = path == ":memory:"
        self._connection_target = (
            f"file:failure_simulator_{id(self)}?mode=memory&cache=shared"
            if self._is_memory
            else path
        )
        self._memory_keeper: sqlite3.Connection | None = None

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._initialize()
        connection = self._open_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            if not self._is_memory:
                Path(self._path).expanduser().parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
            connection = self._open_connection()
            if self._is_memory:
                self._memory_keeper = connection
            try:
                connection.executescript(SCHEMA)
                connection.execute("BEGIN IMMEDIATE")
                seeded = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'initial_seed'"
                ).fetchone()
                if seeded is None:
                    self._insert_seeds(connection)
                    connection.execute(
                        "INSERT INTO metadata (key, value) VALUES (?, ?)",
                        ("initial_seed", "1"),
                    )
                connection.commit()
            finally:
                if not self._is_memory:
                    connection.close()
            self._initialized = True

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._connection_target,
            timeout=10,
            uri=self._is_memory,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _insert_seeds(self, connection: sqlite3.Connection) -> None:
        connection.executemany(
            "INSERT INTO projects (id, payload) VALUES (?, ?)",
            [
                (str(project.id), self.serialize(project))
                for project in self._seed_projects
            ],
        )
        connection.executemany(
            "INSERT INTO rules (id, project_id, payload) VALUES (?, ?, ?)",
            [
                (
                    str(rule.id),
                    str(rule.project_id) if rule.project_id else None,
                    self.serialize(rule),
                )
                for rule in self._seed_rules
            ],
        )

    @staticmethod
    def serialize(model: BaseModel) -> str:
        return json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
