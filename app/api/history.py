from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.models import RequestHistoryEntry
from app.services import RequestHistoryService


router = APIRouter(prefix="/api/history", tags=["request history"])


def get_history_service(request: Request) -> RequestHistoryService:
    return request.app.state.history_service


@router.get("", response_model=list[RequestHistoryEntry])
async def list_request_history(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> tuple[RequestHistoryEntry, ...]:
    return get_history_service(request).list(limit=limit)
