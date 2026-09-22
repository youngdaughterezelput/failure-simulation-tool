from datetime import UTC, datetime
from time import perf_counter_ns
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class MonotonicClock(Protocol):
    def now_ns(self) -> int: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemMonotonicClock:
    def now_ns(self) -> int:
        return perf_counter_ns()


def elapsed_milliseconds(*, started_ns: int, finished_ns: int) -> int:
    return max(0, finished_ns - started_ns) // 1_000_000
