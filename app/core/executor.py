from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.decision import RuleDecisionEngine
from app.core.matcher import find_matching_rule
from app.core.proxy import proxy_request
from app.core.response import build_simulated_response
from app.models import DecisionReason, RequestOutcome
from app.repository import RuleRepository


@dataclass(frozen=True, slots=True)
class RequestExecutionResult:
    response: Response
    outcome: RequestOutcome
    decision_reason: DecisionReason
    rule_id: UUID | None


class RequestExecutor:
    """Executes one data-plane request and describes its observable result."""

    def __init__(
        self,
        repository: RuleRepository,
        decision_engine: RuleDecisionEngine,
        target_api_url: str,
    ) -> None:
        self._repository = repository
        self._decision_engine = decision_engine
        self._target_api_url = target_api_url

    async def execute(
        self,
        request: Request,
        proxy_client: httpx.AsyncClient,
    ) -> RequestExecutionResult:
        rule = find_matching_rule(
            self._repository.list(),
            method=request.method,
            path=request.url.path,
        )
        if rule is not None:
            decision = self._decision_engine.decide(rule)
            if decision.simulate:
                return RequestExecutionResult(
                    response=await build_simulated_response(rule.response),
                    outcome=RequestOutcome.SIMULATED,
                    decision_reason=decision.reason,
                    rule_id=rule.id,
                )
            matched_rule_id = rule.id
            decision_reason = decision.reason
        else:
            matched_rule_id = None
            decision_reason = DecisionReason.NO_MATCHING_RULE

        try:
            response = await proxy_request(
                request,
                target_api_url=self._target_api_url,
                client=proxy_client,
            )
        except httpx.RequestError as error:
            response = JSONResponse(
                status_code=502,
                content={
                    "error": "upstream request failed",
                    "detail": str(error),
                },
            )
        return RequestExecutionResult(
            response=response,
            outcome=RequestOutcome.PROXIED,
            decision_reason=decision_reason,
            rule_id=matched_rule_id,
        )
