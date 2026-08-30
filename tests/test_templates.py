from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repository import InMemoryRuleRepository, seed_rules


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    proxy_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"source": "upstream"})
        )
    )
    application = create_app(
        settings=Settings(target_api_url="https://upstream.example"),
        repository=InMemoryRuleRepository(seed_rules()),
        proxy_client=proxy_client,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://simulator.test",
    ) as application_client:
        yield application_client
    await proxy_client.aclose()


@pytest.mark.asyncio
async def test_lists_and_gets_predefined_failure_templates(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/templates")

    assert response.status_code == 200
    template_ids = {template["id"] for template in response.json()}
    assert {
        "bad-request",
        "too-many-requests",
        "internal-server-error",
        "service-unavailable",
        "gateway-timeout",
    } <= template_ids

    service_unavailable = await client.get(
        "/api/templates/service-unavailable"
    )
    assert service_unavailable.status_code == 200
    assert service_unavailable.json()["response"] == {
        "status": 503,
        "headers": {
            "content-type": "application/json",
            "retry-after": "30",
        },
        "body": {"error": "service unavailable"},
        "delay_ms": 0,
    }


@pytest.mark.asyncio
async def test_creates_and_uses_rule_from_template(
    client: httpx.AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/rules/from-template/too-many-requests",
        json={
            "name": "Checkout is rate limited",
            "match": {"method": "post", "path": "/checkout"},
        },
    )

    assert create_response.status_code == 201
    rule = create_response.json()
    assert rule["name"] == "Checkout is rate limited"
    assert rule["match"]["method"] == "POST"
    assert rule["response"]["status"] == 429

    simulated_response = await client.post("/checkout")
    assert simulated_response.status_code == 429
    assert simulated_response.headers["retry-after"] == "30"
    assert simulated_response.json() == {"error": "too many requests"}


@pytest.mark.asyncio
async def test_returns_404_for_unknown_template(
    client: httpx.AsyncClient,
) -> None:
    get_response = await client.get("/api/templates/does-not-exist")
    create_response = await client.post(
        "/api/rules/from-template/does-not-exist",
        json={"match": {"method": "GET", "path": "/example"}},
    )

    assert get_response.status_code == 404
    assert create_response.status_code == 404


@pytest.mark.asyncio
async def test_management_api_returns_422_for_unsafe_response(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/rules",
        json={
            "name": "Unsafe response",
            "match": {"method": "GET", "path": "/unsafe"},
            "response": {
                "status": 503,
                "headers": {"content-length": "999"},
            },
        },
    )

    assert response.status_code == 422
    assert "managed by the HTTP server" in response.text


@pytest.mark.asyncio
async def test_openapi_contains_management_examples(
    client: httpx.AsyncClient,
) -> None:
    schema = (await client.get("/openapi.json")).json()

    assert schema["components"]["schemas"]["RuleCreate"]["examples"]
    assert schema["components"]["schemas"]["RuleFromTemplateCreate"][
        "examples"
    ]
