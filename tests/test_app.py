import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture
def upstream_requests() -> list[httpx.Request]:
    return []


@pytest.fixture
async def proxy_client(upstream_requests: list[httpx.Request],) -> AsyncIterator[httpx.AsyncClient]:
    async def handle_upstream(request: httpx.Request) -> httpx.Response:
        upstream_requests.append(request)
        return httpx.Response(
            status_code=201,
            json={
                "source": "upstream",
                "path": request.url.path,
                "query": request.url.query.decode(),
                "body": json.loads(request.content),
            },
            headers=[
                ("x-upstream", "yes"),
                ("set-cookie", "first=one; Path=/"),
                ("set-cookie", "second=two; Path=/"),
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_upstream))
    yield client
    await client.aclose()


@pytest.fixture
def app(proxy_client: httpx.AsyncClient):
    return create_app(
        settings=Settings(target_api_url="https://upstream.example/base"),
        proxy_client=proxy_client,
    )


@pytest.mark.asyncio
async def test_matching_request_returns_simulated_response_without_upstream_call(
    app, upstream_requests: list[httpx.Request],) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://simulator.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 503
    assert response.json() == {"error": "service unavailable"}
    assert upstream_requests == []


@pytest.mark.asyncio
async def test_unmatched_request_is_forwarded_to_the_target_api(
    app, upstream_requests: list[httpx.Request],) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://simulator.test",
    ) as client:
        response = await client.post(
            "/orders?state=new&state=paid",
            json={"order_id": 42},
            headers={"x-correlation-id": "test-123"},
        )

    assert response.status_code == 201
    assert response.headers["x-upstream"] == "yes"
    assert response.headers.get_list("set-cookie") == [
        "first=one; Path=/",
        "second=two; Path=/",
    ]
    assert response.json() == {
        "source": "upstream",
        "path": "/base/orders",
        "query": "state=new&state=paid",
        "body": {"order_id": 42},
    }
    assert len(upstream_requests) == 1
    assert upstream_requests[0].method == "POST"
    assert upstream_requests[0].headers["x-correlation-id"] == "test-123"


@pytest.mark.asyncio
async def test_health_endpoint_is_handled_locally(
    app,
    upstream_requests: list[httpx.Request],
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://simulator.test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert upstream_requests == []


@pytest.mark.asyncio
async def test_application_lifespan_manages_the_default_proxy_client() -> None:
    application = create_app(
        settings=Settings(target_api_url="http://localhost:9000")
    )
    assert application.state.proxy_client is None
    async with application.router.lifespan_context(application):
        managed_client = application.state.proxy_client
        assert not managed_client.is_closed

    assert managed_client.is_closed
