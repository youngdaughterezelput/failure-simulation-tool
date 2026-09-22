from datetime import UTC, datetime

import httpx
import pytest

from app.config import Settings
from app.history_repository import InMemoryRequestHistoryRepository
from app.main import create_app
from app.models import (
    DecisionReason,
    HistoryQuery,
    RecordRequestCommand,
    RequestHistoryCreate,
    RequestHistoryEntry,
    RequestOutcome,
)
from app.repository import InMemoryRuleRepository, seed_rules
from app.services import PersistentRequestHistoryRecorder, RequestHistoryQueryService


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


class ScriptedMonotonicClock:
    def __init__(self, *values: int) -> None:
        self._values = iter(values)

    def now_ns(self) -> int:
        return next(self._values)


def test_recorder_uses_injected_clock_and_query_uses_stable_cursor() -> None:
    repository = InMemoryRequestHistoryRepository()
    recorder = PersistentRequestHistoryRecorder(
        repository,
        FixedClock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC)),
    )
    command = RecordRequestCommand(
        method="get",
        path="/orders",
        outcome=RequestOutcome.PROXIED,
        decision_reason=DecisionReason.NO_MATCHING_RULE,
        status_code=200,
        duration_ms=12,
    )
    first = recorder.record(command)
    second = recorder.record(command)
    third = recorder.record(command)
    query_service = RequestHistoryQueryService(repository)

    assert first.timestamp == datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    assert first.method == "GET"
    assert [entry.id for entry in query_service.list(HistoryQuery(limit=2))] == [
        third.id,
        second.id,
    ]
    assert [
        entry.id
        for entry in query_service.list(
            HistoryQuery(limit=2, before_id=second.id)
        )
    ] == [first.id]


@pytest.mark.asyncio
async def test_data_plane_history_uses_injected_clocks() -> None:
    upstream = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    )
    fixed_time = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    application = create_app(
        settings=Settings(target_api_url="https://upstream.example"),
        repository=InMemoryRuleRepository(seed_rules()),
        proxy_client=upstream,
        clock=FixedClock(fixed_time),
        monotonic_clock=ScriptedMonotonicClock(1_000_000, 4_500_000),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://simulator.test",
    ) as client:
        response = await client.get("/api/users")
        history = await client.get("/_simulator/api/history")

    assert response.status_code == 503
    entry = history.json()[0]
    assert entry["timestamp"] == "2026-09-22T12:00:00Z"
    assert entry["duration_ms"] == 3
    await upstream.aclose()


def test_in_memory_repository_normalizes_seed_order() -> None:
    timestamp = datetime(2026, 9, 22, tzinfo=UTC)
    data = RequestHistoryCreate(
        timestamp=timestamp,
        method="GET",
        path="/",
        outcome=RequestOutcome.PROXIED,
        decision_reason=DecisionReason.NO_MATCHING_RULE,
        status_code=200,
        duration_ms=0,
    )
    repository = InMemoryRequestHistoryRepository(
        (
            RequestHistoryEntry(id=2, **data.model_dump()),
            RequestHistoryEntry(id=1, **data.model_dump()),
        )
    )

    assert [entry.id for entry in repository.list(HistoryQuery(limit=10))] == [2, 1]
