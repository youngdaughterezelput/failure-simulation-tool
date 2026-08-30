from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models import (
    FailureRule,
    RuleCreate,
    RuleFromTemplateCreate,
    RuleRuntimeState,
)
from app.services import ProjectNotFoundError, RuleService


router = APIRouter(prefix="/api/rules", tags=["rules"])


def get_rule_service(request: Request) -> RuleService:
    return request.app.state.rule_service


def rule_not_found(rule_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Rule {rule_id} was not found",
    )


@router.get("", response_model=list[FailureRule])
async def list_rules(request: Request) -> tuple[FailureRule, ...]:
    return get_rule_service(request).list()


@router.get("/states", response_model=list[RuleRuntimeState])
async def list_rule_states(request: Request) -> tuple[RuleRuntimeState, ...]:
    return get_rule_service(request).list_states()


@router.post("", response_model=FailureRule, status_code=status.HTTP_201_CREATED)
async def create_rule(data: RuleCreate, request: Request) -> FailureRule:
    try:
        return get_rule_service(request).create(data)
    except ProjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post(
    "/from-template/{template_id}",
    response_model=FailureRule,
    status_code=status.HTTP_201_CREATED,
    summary="Create a rule from a predefined failure template",
)
async def create_rule_from_template(
    template_id: str,
    data: RuleFromTemplateCreate,
    request: Request,
) -> FailureRule:
    try:
        rule = get_rule_service(request).create_from_template(template_id, data)
    except ProjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failure template {template_id!r} was not found",
        )
    return rule


@router.put("/{rule_id}", response_model=FailureRule)
async def update_rule(
    rule_id: UUID, data: RuleCreate, request: Request,) -> FailureRule:
    try:
        rule = get_rule_service(request).update(rule_id, data)
    except ProjectNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    if rule is None:
        raise rule_not_found(rule_id)
    return rule


@router.post("/{rule_id}/enable", response_model=FailureRule)
async def enable_rule(rule_id: UUID, request: Request) -> FailureRule:
    rule = get_rule_service(request).set_enabled(rule_id, enabled=True)
    if rule is None:
        raise rule_not_found(rule_id)
    return rule


@router.post("/{rule_id}/disable", response_model=FailureRule)
async def disable_rule(rule_id: UUID, request: Request) -> FailureRule:
    rule = get_rule_service(request).set_enabled(rule_id, enabled=False)
    if rule is None:
        raise rule_not_found(rule_id)
    return rule


@router.post("/{rule_id}/reset", response_model=RuleRuntimeState)
async def reset_rule_state(
    rule_id: UUID,
    request: Request,
) -> RuleRuntimeState:
    state = get_rule_service(request).reset_state(rule_id)
    if state is None:
        raise rule_not_found(rule_id)
    return state


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: UUID, request: Request) -> Response:
    if not get_rule_service(request).delete(rule_id):
        raise rule_not_found(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
