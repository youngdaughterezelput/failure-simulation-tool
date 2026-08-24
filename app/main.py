from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.api.rules import router as rules_router
from app.config import Settings
from app.core.matcher import find_matching_rule
from app.core.proxy import proxy_request
from app.core.response import build_simulated_response
from app.repository import InMemoryRuleRepository, seed_rules


PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def create_app(
    *,
    settings: Settings | None = None,
    repository: InMemoryRuleRepository | None = None,
    proxy_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    resolved_repository = repository or InMemoryRuleRepository(seed_rules())
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
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.repository = resolved_repository
    application.state.proxy_client = proxy_client
    application.include_router(rules_router)

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.api_route("/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def simulate_or_proxy(request: Request, path: str) -> Response:
        del path  # Routing consumes the path; matching uses the canonical request URL.
        rule = find_matching_rule(
            application.state.repository.list(),
            method=request.method,
            path=request.url.path,
        )
        if rule is not None:
            return await build_simulated_response(rule.response)
        try:
            return await proxy_request(
                request,
                target_api_url=application.state.settings.target_api_url,
                client=application.state.proxy_client,
            )
        except httpx.RequestError as error:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "upstream request failed",
                    "detail": str(error),
                },
            )
    return application


app = create_app()
