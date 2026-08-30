import sqlite3
from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.database import SQLiteDatabase
from app.history_repository import SQLiteRequestHistoryRepository
from app.main import create_app
from app.models import DecisionReason
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
        "/_simulator/api/projects",
        json={"name": "Orders", "description": "Orders QA"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    updated = await client.put(
        f"/_simulator/api/projects/{project_id}",
        json={"name": "Orders API", "description": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Orders API"

    rule_response = await client.post(
        "/_simulator/api/rules/from-template/gateway-timeout",
        json={
            "project_id": project_id,
            "match": {"method": "GET", "path": "/orders"},
        },
    )
    assert rule_response.status_code == 201
    assert rule_response.json()["project_id"] == project_id

    conflict = await client.delete(f"/_simulator/api/projects/{project_id}")
    assert conflict.status_code == 409

    await client.delete(f"/_simulator/api/rules/{rule_response.json()['id']}")
    deleted = await client.delete(f"/_simulator/api/projects/{project_id}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_rule_rejects_unknown_project(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/_simulator/api/rules/from-template/not-found",
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

    history = await client.get("/_simulator/api/history")
    assert history.status_code == 200
    entries = history.json()
    assert [entry["outcome"] for entry in entries[:2]] == [
        "proxied",
        "simulated",
    ]
    assert entries[0]["path"] == "/no-rule"
    assert entries[0]["rule_id"] is None
    assert entries[0]["decision_reason"] == "no_matching_rule"
    assert entries[1]["path"] == "/api/users"
    assert entries[1]["rule_id"] is not None
    assert entries[1]["decision_reason"] == "always"


@pytest.mark.asyncio
async def test_web_ui_and_static_assets_are_served(
    client: httpx.AsyncClient,
) -> None:
    page = await client.get("/_simulator/ui")
    script = await client.get("/_simulator/static/app.js")

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
                "/_simulator/api/projects",
                json={"name": "Persistent project"},
            )
        ).json()
        rule = await first_client.post(
            "/_simulator/api/rules/from-template/service-unavailable",
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
        projects = await second_client.get("/_simulator/api/projects")
        rules = await second_client.get("/_simulator/api/rules")
        history = await second_client.get("/_simulator/api/history")
        states = await second_client.get("/_simulator/api/rules/states")

    assert project["id"] in {item["id"] for item in projects.json()}
    assert "/persistent" in {item["match"]["path"] for item in rules.json()}
    assert history.json()[0]["outcome"] == "simulated"
    persistent_state = next(
        item for item in states.json() if item["rule_id"] == rule.json()["id"]
    )
    assert persistent_state["matched_count"] == 1
    assert persistent_state["simulated_count"] == 1
    await upstream.aclose()


@pytest.mark.asyncio
async def test_upstream_path_that_matches_old_management_path_can_be_simulated(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/_simulator/api/rules/from-template/unauthorized",
        json={"match": {"method": "GET", "path": "/api/rules"}},
    )
    assert created.status_code == 201

    simulated = await client.get("/api/rules")
    management = await client.get("/_simulator/api/rules")

    assert simulated.status_code == 401
    assert management.status_code == 200


@pytest.mark.asyncio
async def test_count_behavior_and_reset_through_management_api(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/_simulator/api/rules/from-template/service-unavailable",
        json={
            "match": {"method": "GET", "path": "/limited"},
            "behavior": {"skip_matches": 1, "max_simulations": 2},
        },
    )
    rule_id = created.json()["id"]

    statuses = [(await client.get("/limited")).status_code for _ in range(4)]
    assert statuses == [200, 503, 503, 200]

    states = (await client.get("/_simulator/api/rules/states")).json()
    state = next(item for item in states if item["rule_id"] == rule_id)
    assert state["matched_count"] == 4
    assert state["simulated_count"] == 2

    history = (await client.get("/_simulator/api/history?limit=4")).json()
    assert [item["decision_reason"] for item in history] == [
        "count_exhausted",
        "always",
        "always",
        "skip_match",
    ]

    reset = await client.post(f"/_simulator/api/rules/{rule_id}/reset")
    assert reset.status_code == 200
    assert reset.json()["matched_count"] == 0
    assert reset.json()["simulated_count"] == 0


def test_sqlite_reads_legacy_rule_with_reserved_path() -> None:
    database = SQLiteDatabase(":memory:", seed_projects=seed_projects())
    legacy_payload = """{
        "id": "00000000-0000-0000-0000-000000000099",
        "name": "Legacy management rule",
        "enabled": true,
        "project_id": "00000000-0000-0000-0000-000000000001",
        "match": {"method": "GET", "path": "/_simulator/api/rules/{rule_id}"},
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

    assert rules[0].match.path == "/_simulator/api/rules/{rule_id}"


def test_sqlite_migrates_legacy_history_schema(tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                outcome TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                rule_id TEXT,
                duration_ms INTEGER NOT NULL
            );
            INSERT INTO request_history (
                timestamp, method, path, outcome, status_code, rule_id,
                duration_ms
            ) VALUES (
                '2026-08-30T10:00:00+00:00', 'GET', '/legacy', 'proxied',
                200, NULL, 3
            );
            """
        )

    database = SQLiteDatabase(str(database_path))
    history = SQLiteRequestHistoryRepository(database).list(limit=10)

    assert history[0].decision_reason is DecisionReason.NO_MATCHING_RULE
    with database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(request_history)"
            ).fetchall()
        }
    assert "decision_reason" in columns
