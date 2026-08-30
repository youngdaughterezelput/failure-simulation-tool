from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.history import router as history_router
from app.api.projects import router as projects_router
from app.api.rules import router as rules_router
from app.api.templates import router as templates_router
from app.config import Settings
from app.constants import CONTROL_PREFIX
from app.core.decision import RuleDecisionEngine
from app.core.matcher import find_matching_rule
from app.core.proxy import proxy_request
from app.core.response import build_simulated_response
from app.database import SQLiteDatabase
from app.history_repository import (
    InMemoryRequestHistoryRepository,
    RequestHistoryRepository,
    SQLiteRequestHistoryRepository,
)
from app.models import DecisionReason, RequestOutcome
from app.project_repository import (
    InMemoryProjectRepository,
    ProjectRepository,
    SQLiteProjectRepository,
    seed_projects,
)
from app.repository import (
    InMemoryRuleRepository,
    RuleRepository,
    SQLiteRuleRepository,
    seed_rules,
)
from app.runtime_repository import (
    InMemoryRuleRuntimeRepository,
    RuleRuntimeRepository,
    SQLiteRuleRuntimeRepository,
)
from app.services import ProjectService, RequestHistoryService, RuleService
from app.templates import FailureTemplateCatalog


PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
WEB_DIRECTORY = Path(__file__).parent / "web"


def create_app(
    *,
    settings: Settings | None = None,
    repository: RuleRepository | None = None,
    project_repository: ProjectRepository | None = None,
    history_repository: RequestHistoryRepository | None = None,
    runtime_repository: RuleRuntimeRepository | None = None,
    template_catalog: FailureTemplateCatalog | None = None,
    proxy_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    if (
        repository is None
        and project_repository is None
        and history_repository is None
        and runtime_repository is None
    ):
        database = SQLiteDatabase(
            resolved_settings.database_path,
            seed_projects=seed_projects(),
            seed_rules=seed_rules(),
        )
        resolved_repository: RuleRepository = SQLiteRuleRepository(database)
        resolved_project_repository: ProjectRepository = (
            SQLiteProjectRepository(database)
        )
        resolved_history_repository: RequestHistoryRepository = (
            SQLiteRequestHistoryRepository(database)
        )
        resolved_runtime_repository: RuleRuntimeRepository = (
            SQLiteRuleRuntimeRepository(database)
        )
    else:
        resolved_repository = repository or InMemoryRuleRepository(seed_rules())
        resolved_project_repository = (
            project_repository or InMemoryProjectRepository(seed_projects())
        )
        resolved_history_repository = (
            history_repository or InMemoryRequestHistoryRepository()
        )
        resolved_runtime_repository = (
            runtime_repository or InMemoryRuleRuntimeRepository()
        )
    resolved_template_catalog = (
        template_catalog or FailureTemplateCatalog.predefined()
    )
    owns_proxy_client = proxy_client is None

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if application.state.proxy_client is None:
            application.state.proxy_client = httpx.AsyncClient(
                timeout=resolved_settings.upstream_timeout_seconds,
                follow_redirects=False,
            )
        yield
        if owns_proxy_client:
            await application.state.proxy_client.aclose()

    application = FastAPI(
        title="Failure Simulation Tool",
        version="0.4.0",
        description=(
            "Inject validated HTTP responses into matching requests, or proxy "
            "unmatched traffic to the configured target API."
        ),
        docs_url=f"{CONTROL_PREFIX}/docs",
        redoc_url=f"{CONTROL_PREFIX}/redoc",
        openapi_url=f"{CONTROL_PREFIX}/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.repository = resolved_repository
    application.state.project_repository = resolved_project_repository
    application.state.template_catalog = resolved_template_catalog
    application.state.rule_service = RuleService(
        resolved_repository,
        resolved_template_catalog,
        resolved_project_repository,
        resolved_runtime_repository,
    )
    application.state.project_service = ProjectService(
        resolved_project_repository,
        resolved_repository,
    )
    application.state.history_service = RequestHistoryService(
        resolved_history_repository
    )
    application.state.decision_engine = RuleDecisionEngine(
        resolved_runtime_repository
    )
    application.state.proxy_client = proxy_client
    application.include_router(projects_router, prefix=CONTROL_PREFIX)
    application.include_router(rules_router, prefix=CONTROL_PREFIX)
    application.include_router(templates_router, prefix=CONTROL_PREFIX)
    application.include_router(history_router, prefix=CONTROL_PREFIX)
    application.mount(
        f"{CONTROL_PREFIX}/static",
        StaticFiles(directory=WEB_DIRECTORY / "static"),
        name="static",
    )

    @application.get(CONTROL_PREFIX, include_in_schema=False)
    @application.get(f"{CONTROL_PREFIX}/ui", include_in_schema=False)
    async def web_ui() -> FileResponse:
        return FileResponse(WEB_DIRECTORY / "index.html")

    @application.get(f"{CONTROL_PREFIX}/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.api_route(
        "/{path:path}",
        methods=PROXY_METHODS,
        include_in_schema=False,
    )
    async def simulate_or_proxy(request: Request, path: str) -> Response:
        del path  # Routing consumes the path; matching uses the canonical request URL.
        started_at = perf_counter()
        rule = find_matching_rule(
            application.state.repository.list(),
            method=request.method,
            path=request.url.path,
        )
        if rule is not None:
            decision = application.state.decision_engine.decide(rule)
            if decision.simulate:
                response = await build_simulated_response(rule.response)
                application.state.history_service.record_safely(
                    method=request.method,
                    path=request.url.path,
                    outcome=RequestOutcome.SIMULATED,
                    decision_reason=decision.reason,
                    status_code=response.status_code,
                    rule_id=rule.id,
                    duration_ms=int((perf_counter() - started_at) * 1000),
                )
                return response
            matched_rule_id = rule.id
            decision_reason = decision.reason
        else:
            matched_rule_id = None
            decision_reason = DecisionReason.NO_MATCHING_RULE
        try:
            response = await proxy_request(
                request,
                target_api_url=application.state.settings.target_api_url,
                client=application.state.proxy_client,
            )
        except httpx.RequestError as error:
            response = JSONResponse(
                status_code=502,
                content={
                    "error": "upstream request failed",
                    "detail": str(error),
                },
            )
        application.state.history_service.record_safely(
            method=request.method,
            path=request.url.path,
            outcome=RequestOutcome.PROXIED,
            decision_reason=decision_reason,
            status_code=response.status_code,
            rule_id=matched_rule_id,
            duration_ms=int((perf_counter() - started_at) * 1000),
        )
        return response
    return application


app = create_app()
