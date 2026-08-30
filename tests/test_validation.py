import math

import pytest
from pydantic import ValidationError

from app.models import RequestMatch, SimulatedResponse
from app.models.rule import MAX_BODY_BYTES, MAX_DELAY_MS, MAX_HEADER_BYTES


@pytest.mark.parametrize("status", [199, 600, True, "503"])
def test_rejects_invalid_or_non_integer_status(status: object) -> None:
    with pytest.raises(ValidationError):
        SimulatedResponse(status=status)  # type: ignore[arg-type]


@pytest.mark.parametrize("delay_ms", [-1, MAX_DELAY_MS + 1, True, "10"])
def test_rejects_invalid_or_non_integer_delay(delay_ms: object) -> None:
    with pytest.raises(ValidationError):
        SimulatedResponse(status=503, delay_ms=delay_ms)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({"bad header": "value"}, "invalid HTTP header name"),
        ({"content-length": "10"}, "managed by the HTTP server"),
        ({"x-test": "safe\r\ninjected: yes"}, "invalid HTTP header value"),
        ({"X-Test": "one", "x-test": "two"}, "duplicate HTTP header name"),
        ({"x-test": "snowman: ☃"}, "latin-1"),
    ],
)
def test_rejects_unsafe_response_headers(
    headers: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        SimulatedResponse(status=503, headers=headers)


def test_normalizes_header_names_for_consistent_matching() -> None:
    response = SimulatedResponse(status=503, headers={"Retry-After": "30"})

    assert response.headers == {"retry-after": "30"}


def test_rejects_headers_over_total_size_limit() -> None:
    with pytest.raises(ValidationError, match="headers must not exceed"):
        SimulatedResponse(
            status=503,
            headers={"x-large": "x" * MAX_HEADER_BYTES},
        )


@pytest.mark.parametrize("status", [204, 205, 304])
def test_rejects_body_for_bodyless_status(status: int) -> None:
    with pytest.raises(ValidationError, match="cannot have a response body"):
        SimulatedResponse(status=status, body={"unexpected": True})


@pytest.mark.parametrize("body", [math.nan, math.inf, -math.inf])
def test_rejects_non_json_numbers(body: float) -> None:
    with pytest.raises(ValidationError, match="body must be valid JSON"):
        SimulatedResponse(status=500, body=body)


def test_rejects_body_over_size_limit() -> None:
    with pytest.raises(ValidationError, match="body must not exceed"):
        SimulatedResponse(status=500, body="x" * (MAX_BODY_BYTES + 1))


@pytest.mark.parametrize(
    "path",
    ["/", "/health", "/api/rules", "/api/rules/example", "/static/app.js"],
)
def test_rejects_paths_reserved_by_the_simulator(path: str) -> None:
    with pytest.raises(ValidationError, match="path is reserved"):
        RequestMatch(method="GET", path=path)
