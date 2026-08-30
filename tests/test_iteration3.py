from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.database import SQLiteDatabase
from app.main import create_app
from app.project_repository import seed_projects
from app.repository import (
    InMemoryRuleRepository,
    SQLiteRuleRepository,
    seed_rules,
)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    upstream = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"upstream": True})
        )
    )
    application = create_app(
        settings=Settings(target_api_url="https://upstream.example"),
        repository=InMemoryRuleRepository(seed_rules()),
        proxy_client=upstream,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://simulator.test",
    ) as application_client:
        yield application_client
    await upstream.aclose()


@pytest.mark.asyncio
async def test_project_lifecycle_and_rule_delete_constraint(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/projects",
        json={"name": "Orders", "description": "Orders QA"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    updated = await client.put(
        f"/api/projects/{project_id}",
        json={"name": "Orders API", "description": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Orders API"

    rule_response = await client.post(
        "/api/rules/from-template/gateway-timeout",
        json={
            "project_id": project_id,
            "match": {"method": "GET", "path": "/orders"},
        },
    )
    assert rule_response.status_code == 201
    assert rule_response.json()["project_id"] == project_id

    conflict = await client.delete(f"/api/projects/{project_id}")
    assert conflict.status_code == 409

    await client.delete(f"/api/rules/{rule_response.json()['id']}")
    deleted = await client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_rule_rejects_unknown_project(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/rules/from-template/not-found",
        json={
            "project_id": "00000000-0000-0000-0000-000000000099",
            "match": {"method": "GET", "path": "/missing"},
        },
    )

    assert response.status_code == 422
    assert "Project" in response.json()["detail"]


@pytest.mark.asyncio
async def test_records_simulated_and_proxied_request_history(
    client: httpx.AsyncClient,
) -> None:
    simulated = await client.get("/api/users")
    proxied = await client.get("/no-rule")

    assert simulated.status_code == 503
    assert proxied.status_code == 200

    history = await client.get("/api/history")
    assert history.status_code == 200
    entries = history.json()
    assert [entry["outcome"] for entry in entries[:2]] == [
        "proxied",
        "simulated",
    ]
    assert entries[0]["path"] == "/no-rule"
    assert entries[0]["rule_id"] is None
    assert entries[1]["path"] == "/api/users"
    assert entries[1]["rule_id"] is not None


@pytest.mark.asyncio
async def test_web_ui_and_static_assets_are_served(
    client: httpx.AsyncClient,
) -> None:
    page = await client.get("/")
    script = await client.get("/static/app.js")

    assert page.status_code == 200
    assert "Failure Simulation Tool" in page.text
    assert script.status_code == 200
    assert "class Dashboard" in script.text
    assert "runRefresh" in script.text
    assert 'cache: "no-store"' in script.text
    assert "This path is reserved by the simulator" in script.text


@pytest.mark.asyncio
async def test_sqlite_configuration_and_history_survive_restart(tmp_path) -> None:
    database_path = tmp_path / "simulator.db"
    settings = Settings(
        target_api_url="https://upstream.example",
        database_path=str(database_path),
    )
    upstream = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"upstream": True})
        )
    )

    first_app = create_app(settings=settings, proxy_client=upstream)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=first_app),
        base_url="http://simulator.test",
    ) as first_client:
        project = (
            await first_client.post(
                "/api/projects",
                json={"name": "Persistent project"},
            )
        ).json()
        rule = await first_client.post(
            "/api/rules/from-template/service-unavailable",
            json={
                "project_id": project["id"],
                "match": {"method": "GET", "path": "/persistent"},
            },
        )
        assert rule.status_code == 201
        assert (await first_client.get("/persistent")).status_code == 503

    second_app = create_app(settings=settings, proxy_client=upstream)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=second_app),
        base_url="http://simulator.test",
    ) as second_client:
        projects = await second_client.get("/api/projects")
        rules = await second_client.get("/api/rules")
        history = await second_client.get("/api/history")

    assert project["id"] in {item["id"] for item in projects.json()}
    assert "/persistent" in {item["match"]["path"] for item in rules.json()}
    assert history.json()[0]["outcome"] == "simulated"
    await upstream.aclose()


def test_sqlite_reads_legacy_rule_with_reserved_path() -> None:
    database = SQLiteDatabase(":memory:", seed_projects=seed_projects())
    legacy_payload = """{
        "id": "00000000-0000-0000-0000-000000000099",
        "name": "Legacy management rule",
        "enabled": true,
        "project_id": "00000000-0000-0000-0000-000000000001",
        "match": {"method": "GET", "path": "/api/rules/{rule_id}"},
        "response": {"status": 503, "headers": {}, "body": null, "delay_ms": 0}
    }"""
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO rules (id, project_id, payload) VALUES (?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000099",
                "00000000-0000-0000-0000-000000000001",
                legacy_payload,
            ),
        )

    rules = SQLiteRuleRepository(database).list()

    assert rules[0].match.path == "/api/rules/{rule_id}"
