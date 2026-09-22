from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.models import HistoryQuery, RequestHistoryEntry
from app.services import RequestHistoryQueryService


router = APIRouter(prefix="/api/history", tags=["request history"])


def get_history_query_service(request: Request) -> RequestHistoryQueryService:
    return request.app.state.history_query_service


@router.get("", response_model=list[RequestHistoryEntry])
def list_request_history(
    service: Annotated[
        RequestHistoryQueryService,
        Depends(get_history_query_service),
    ],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    before_id: Annotated[int | None, Query(ge=1)] = None,
) -> tuple[RequestHistoryEntry, ...]:
    return service.list(HistoryQuery(limit=limit, before_id=before_id))
