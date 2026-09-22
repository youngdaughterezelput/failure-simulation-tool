import sqlite3
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest

from app.config import Settings
from app.configuration_repository import SQLiteConfigurationRepository
from app.database import SQLiteDatabase
from app.main import create_app
from app.models import (
    ConfigurationDocument,
    FailureRule,
    Project,
    RequestMatch,
    RuleRuntimeState,
    SimulatedResponse,
)
from app.project_repository import (
    DEFAULT_PROJECT_ID,
    InMemoryProjectRepository,
    seed_projects,
)
from app.repository import InMemoryRuleRepository, seed_rules
from app.runtime_repository import InMemoryRuleRuntimeRepository


@pytest.fixture
async def configuration_client() -> AsyncIterator[
    tuple[httpx.AsyncClient, InMemoryRuleRuntimeRepository]
]:
    runtime_repository = InMemoryRuleRuntimeRepository()
    upstream = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"upstream": True})
        )
    )
    application = create_app(
        settings=Settings(target_api_url="https://upstream.example"),
        repository=InMemoryRuleRepository(seed_rules()),
        project_repository=InMemoryProjectRepository(seed_projects()),
        runtime_repository=runtime_repository,
        proxy_client=upstream,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://simulator.test",
    ) as client:
        yield client, runtime_repository
    await upstream.aclose()


@pytest.mark.asyncio
async def test_export_returns_versioned_download(
    configuration_client: tuple[
        httpx.AsyncClient,
        InMemoryRuleRuntimeRepository,
    ],
) -> None:
    client, _ = configuration_client

    response = await client.get("/_simulator/api/configuration/export")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="failure-simulation-config-v1.json"'
    )
    document = response.json()
    assert document["kind"] == "failure-simulation-configuration"
    assert document["schema_version"] == 1
    assert [project["id"] for project in document["projects"]] == [
        "00000000-0000-0000-0000-000000000001"
    ]
    assert document["rules"][0]["match"] == {
        "method": "GET",
        "path": "/api/users",
    }
    assert "target_api_url" not in document
    assert "runtime_states" not in document
    assert "history" not in document


@pytest.mark.asyncio
async def test_dry_run_does_not_change_configuration_and_import_replaces_it(
    configuration_client: tuple[
        httpx.AsyncClient,
        InMemoryRuleRuntimeRepository,
    ],
) -> None:
    client, runtime_repository = configuration_client
    original = (
        await client.get("/_simulator/api/configuration/export")
    ).json()
    rule_id = UUID(original["rules"][0]["id"])
    runtime_repository.save(
        RuleRuntimeState(
            rule_id=rule_id,
            matched_count=3,
            simulated_count=2,
        )
    )
    replacement = {
        "kind": "failure-simulation-configuration",
        "schema_version": 1,
        "projects": [
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "name": "Imported project",
                "description": "Portable scenarios",
            }
        ],
        "rules": [
            {
                "id": "00000000-0000-0000-0000-000000000020",
                "name": "Imported failure",
                "enabled": True,
                "project_id": "00000000-0000-0000-0000-000000000010",
                "match": {"method": "post", "path": "/imported"},
                "response": {
                    "status": 429,
                    "headers": {"Retry-After": "30"},
                    "body": {"error": "rate limited"},
                    "delay_ms": 10,
                },
                "behavior": {
                    "probability": 0.5,
                    "skip_matches": 1,
                    "max_simulations": 4,
                    "seed": 42,
                },
            }
        ],
    }

    dry_run = await client.post(
        "/_simulator/api/configuration/import?dry_run=true",
        json=replacement,
    )
    after_dry_run = await client.get(
        "/_simulator/api/configuration/export"
    )
    imported = await client.post(
        "/_simulator/api/configuration/import",
        json=replacement,
    )
    exported = await client.get("/_simulator/api/configuration/export")
    states = await client.get("/_simulator/api/rules/states")

    assert dry_run.status_code == 200
    assert dry_run.json() == {
        "projects_imported": 1,
        "rules_imported": 1,
        "runtime_states_reset": 0,
        "dry_run": True,
    }
    assert after_dry_run.json() == original
    assert imported.json()["runtime_states_reset"] == 1
    assert exported.json()["projects"] == replacement["projects"]
    assert exported.json()["rules"][0]["match"]["method"] == "POST"
    assert exported.json()["rules"][0]["response"]["headers"] == {
        "retry-after": "30"
    }
    assert states.json()[0]["matched_count"] == 0
    assert states.json()[0]["simulated_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document["rules"][0].update(
            {"project_id": "00000000-0000-0000-0000-000000000099"}
        ),
        lambda document: document["projects"].append(
            document["projects"][0].copy()
        ),
        lambda document: document["rules"][0]["match"].update(
            {"path": "/_simulator/api/rules"}
        ),
        lambda document: document.update({"schema_version": 2}),
        lambda document: document.pop("kind"),
        lambda document: document.update({"unexpected": True}),
    ],
)
async def test_import_rejects_invalid_documents_without_changing_configuration(
    configuration_client: tuple[
        httpx.AsyncClient,
        InMemoryRuleRuntimeRepository,
    ],
    mutate,
) -> None:
    client, _ = configuration_client
    original = (
        await client.get("/_simulator/api/configuration/export")
    ).json()
    invalid = {
        **original,
        "projects": [project.copy() for project in original["projects"]],
        "rules": [
            {
                **rule,
                "match": rule["match"].copy(),
            }
            for rule in original["rules"]
        ],
    }
    mutate(invalid)

    response = await client.post(
        "/_simulator/api/configuration/import",
        json=invalid,
    )
    current = await client.get("/_simulator/api/configuration/export")

    assert response.status_code == 422
    assert current.json() == original


@pytest.mark.asyncio
async def test_sqlite_import_is_persistent_and_preserves_history(tmp_path) -> None:
    database_path = tmp_path / "configuration.db"
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
    ) as client:
        assert (await client.get("/api/users")).status_code == 503
        document = (
            await client.get("/_simulator/api/configuration/export")
        ).json()
        imported = await client.post(
            "/_simulator/api/configuration/import",
            json=document,
        )
        history = await client.get("/_simulator/api/history")
        states = await client.get("/_simulator/api/rules/states")

    second_app = create_app(settings=settings, proxy_client=upstream)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=second_app),
        base_url="http://simulator.test",
    ) as client:
        after_restart = await client.get(
            "/_simulator/api/configuration/export"
        )

    assert imported.json()["runtime_states_reset"] == 1
    assert len(history.json()) == 1
    assert states.json()[0]["matched_count"] == 0
    assert after_restart.json() == document
    await upstream.aclose()


def test_sqlite_import_rolls_back_the_complete_document_on_write_error(
    tmp_path,
) -> None:
    database = SQLiteDatabase(
        str(tmp_path / "atomic.db"),
        seed_projects=seed_projects(),
        seed_rules=seed_rules(),
    )
    repository = SQLiteConfigurationRepository(database)
    original = repository.export()
    rejected_rule_id = UUID("00000000-0000-0000-0000-000000000099")
    replacement = ConfigurationDocument(
        kind="failure-simulation-configuration",
        schema_version=1,
        projects=(
            Project(id=DEFAULT_PROJECT_ID, name="Replacement project"),
        ),
        rules=(
            FailureRule(
                id=rejected_rule_id,
                name="Rejected rule",
                project_id=DEFAULT_PROJECT_ID,
                match=RequestMatch(method="GET", path="/rejected"),
                response=SimulatedResponse(status=500),
            ),
        ),
    )
    with database.connect() as connection:
        connection.execute(
            f"""
            CREATE TRIGGER reject_imported_rule
            BEFORE INSERT ON rules
            WHEN NEW.id = '{rejected_rule_id}'
            BEGIN
                SELECT RAISE(ABORT, 'rejected by test');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="rejected by test"):
        repository.replace(replacement)

    assert repository.export() == original
