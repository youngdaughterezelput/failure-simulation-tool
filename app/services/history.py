import logging
from typing import Protocol

from app.history_repository import (
    HistoryPersistenceError,
    RequestHistoryReader,
    RequestHistoryWriter,
)
from app.infrastructure.clock import Clock
from app.models import (
    HistoryQuery,
    RecordRequestCommand,
    RequestHistoryCreate,
    RequestHistoryEntry,
)


logger = logging.getLogger(__name__)


class RequestHistoryQueryService:
    def __init__(self, reader: RequestHistoryReader) -> None:
        self._reader = reader

    def list(self, query: HistoryQuery) -> tuple[RequestHistoryEntry, ...]:
        return self._reader.list(query)


class RequestHistoryRecorder(Protocol):
    def record(self, command: RecordRequestCommand,) -> RequestHistoryEntry | None: ...


class PersistentRequestHistoryRecorder:
    def __init__(self, writer: RequestHistoryWriter, clock: Clock) -> None:
        self._writer = writer
        self._clock = clock

    def record(self, command: RecordRequestCommand) -> RequestHistoryEntry:
        return self._writer.create(
            RequestHistoryCreate(
                timestamp=self._clock.now(),
                **command.model_dump(),
            )
        )


class BestEffortRequestHistoryRecorder:
    """Suppresses expected history-storage failures on the data plane"""

    def __init__(self, recorder: RequestHistoryRecorder) -> None:
        self._recorder = recorder

    def record(self, command: RecordRequestCommand,) -> RequestHistoryEntry | None:
        try:
            return self._recorder.record(command)
        except HistoryPersistenceError:
            logger.exception("Could not persist request history")
            return None
