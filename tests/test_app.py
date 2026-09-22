import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repository import InMemoryRuleRepository, seed_rules


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
                "body": json.loads(request.content) if request.content else None,
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
        repository=InMemoryRuleRepository(seed_rules()),
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
    app,upstream_requests: list[httpx.Request],) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://simulator.test",
    ) as client:
        response = await client.get("/_simulator/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert upstream_requests == []


@pytest.mark.asyncio
async def test_application_lifespan_manages_the_default_proxy_client() -> None:
    application = create_app(
        settings=Settings(target_api_url="http://localhost:9000"),
        repository=InMemoryRuleRepository(seed_rules()),
    )
    assert application.state.proxy_client is None
    async with application.router.lifespan_context(application):
        managed_client = application.state.proxy_client
        assert not managed_client.is_closed

    assert managed_client.is_closed


@pytest.mark.asyncio
async def test_rule_management_lifecycle(
    app, upstream_requests: list[httpx.Request],) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://simulator.test",
    ) as client:
        create_response = await client.post(
            "/_simulator/api/rules",
            json={
                "name": "Payments unavailable",
                "match": {"method": "get", "path": "/payments"},
                "response": {
                    "status": 500,
                    "body": {"error": "temporary failure"},
                },
            },
        )

        assert create_response.status_code == 201
        created_rule = create_response.json()
        rule_id = created_rule["id"]
        assert created_rule["match"]["method"] == "GET"
        assert created_rule["enabled"] is True

        list_response = await client.get("/_simulator/api/rules")
        assert list_response.status_code == 200
        assert rule_id in {rule["id"] for rule in list_response.json()}

        update_response = await client.put(
            f"/_simulator/api/rules/{rule_id}",
            json={
                "name": "Payments rate limited",
                "match": {"method": "GET", "path": "/payments"},
                "response": {
                    "status": 429,
                    "headers": {"retry-after": "10"},
                    "body": {"error": "rate limited"},
                    "delay_ms": 0,
                },
            },
        )
        assert update_response.status_code == 200
        assert update_response.json()["id"] == rule_id
        assert update_response.json()["name"] == "Payments rate limited"

        disable_response = await client.post(f"/_simulator/api/rules/{rule_id}/disable")
        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] is False

        proxied_response = await client.get("/payments")
        assert proxied_response.status_code == 201
        assert proxied_response.json()["source"] == "upstream"

        enable_response = await client.post(f"/_simulator/api/rules/{rule_id}/enable")
        assert enable_response.status_code == 200
        assert enable_response.json()["enabled"] is True

        simulated_response = await client.get("/payments")
        assert simulated_response.status_code == 429
        assert simulated_response.headers["retry-after"] == "10"
        assert simulated_response.json() == {"error": "rate limited"}

        delete_response = await client.delete(f"/_simulator/api/rules/{rule_id}")
        assert delete_response.status_code == 204

        rules_after_delete = (await client.get("/_simulator/api/rules")).json()
        assert rule_id not in {rule["id"] for rule in rules_after_delete}

    assert len(upstream_requests) == 1


@pytest.mark.asyncio
async def test_rule_management_returns_404_for_unknown_rule(app) -> None:
    unknown_rule_id = "00000000-0000-0000-0000-000000000000"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://simulator.test",
    ) as client:
        response = await client.post(f"/_simulator/api/rules/{unknown_rule_id}/disable")

    assert response.status_code == 404
    assert response.json() == {
        "detail": f"Rule {unknown_rule_id} was not found"
    }
