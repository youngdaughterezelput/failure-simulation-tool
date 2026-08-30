from fastapi import APIRouter, HTTPException, Request, status

from app.models import FailureTemplate
from app.templates import FailureTemplateCatalog


router = APIRouter(prefix="/api/templates", tags=["failure templates"])


def get_template_catalog(request: Request) -> FailureTemplateCatalog:
    return request.app.state.template_catalog


@router.get(
    "", response_model=list[FailureTemplate],
    summary="List predefined HTTP failure templates",)
async def list_templates(request: Request) -> tuple[FailureTemplate, ...]:
    return get_template_catalog(request).list()


@router.get(
    "/{template_id}",
    response_model=FailureTemplate,
    summary="Get a predefined HTTP failure template",
)
async def get_template(template_id: str, request: Request) -> FailureTemplate:
    template = get_template_catalog(request).get(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failure template {template_id!r} was not found",
        )
    return template
