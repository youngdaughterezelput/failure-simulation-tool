from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models import FailureRule, RuleCreate
from app.repository import InMemoryRuleRepository


router = APIRouter(prefix="/api/rules", tags=["rules"])


def get_repository(request: Request) -> InMemoryRuleRepository:
    return request.app.state.repository


def rule_not_found(rule_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Rule {rule_id} was not found",
    )


@router.get("", response_model=list[FailureRule])
async def list_rules(request: Request) -> tuple[FailureRule, ...]:
    return get_repository(request).list()


@router.post("", response_model=FailureRule, status_code=status.HTTP_201_CREATED)
async def create_rule(data: RuleCreate, request: Request) -> FailureRule:
    return get_repository(request).create(data)


@router.put("/{rule_id}", response_model=FailureRule)
async def update_rule(
    rule_id: UUID,
    data: RuleCreate,
    request: Request,
) -> FailureRule:
    rule = get_repository(request).update(rule_id, data)
    if rule is None:
        raise rule_not_found(rule_id)
    return rule


@router.post("/{rule_id}/enable", response_model=FailureRule)
async def enable_rule(rule_id: UUID, request: Request) -> FailureRule:
    rule = get_repository(request).set_enabled(rule_id, enabled=True)
    if rule is None:
        raise rule_not_found(rule_id)
    return rule


@router.post("/{rule_id}/disable", response_model=FailureRule)
async def disable_rule(rule_id: UUID, request: Request) -> FailureRule:
    rule = get_repository(request).set_enabled(rule_id, enabled=False)
    if rule is None:
        raise rule_not_found(rule_id)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: UUID, request: Request) -> Response:
    if not get_repository(request).delete(rule_id):
        raise rule_not_found(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
