import logging
from datetime import UTC, datetime
from uuid import UUID

from app.history_repository import RequestHistoryRepository
from app.models import (
    DecisionReason,
    RequestHistoryCreate,
    RequestHistoryEntry,
    RequestOutcome,
)


logger = logging.getLogger(__name__)


class RequestHistoryService:
    def __init__(self, repository: RequestHistoryRepository) -> None:
        self._repository = repository

    def list(self, *, limit: int) -> tuple[RequestHistoryEntry, ...]:
        return self._repository.list(limit=limit)

    def record(
        self,
        *,
        method: str,
        path: str,
        outcome: RequestOutcome,
        decision_reason: DecisionReason,
        status_code: int,
        duration_ms: int,
        rule_id: UUID | None = None,
    ) -> RequestHistoryEntry:
        return self._repository.create(
            RequestHistoryCreate(
                timestamp=datetime.now(UTC),
                method=method,
                path=path,
                outcome=outcome,
                decision_reason=decision_reason,
                status_code=status_code,
                rule_id=rule_id,
                duration_ms=duration_ms,
            )
        )

    def record_safely(
        self,
        *,
        method: str,
        path: str,
        outcome: RequestOutcome,
        decision_reason: DecisionReason,
        status_code: int,
        duration_ms: int,
        rule_id: UUID | None = None,
    ) -> RequestHistoryEntry | None:
        try:
            return self.record(
                method=method,
                path=path,
                outcome=outcome,
                decision_reason=decision_reason,
                status_code=status_code,
                duration_ms=duration_ms,
                rule_id=rule_id,
            )
        except Exception:
            logger.exception("Could not persist request history")
            return None
