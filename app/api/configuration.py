from fastapi import APIRouter, Query, Request, Response

from app.models import ConfigurationDocument, ConfigurationImportResult
from app.services import ConfigurationService


router = APIRouter(prefix="/api/configuration", tags=["configuration"])


def get_configuration_service(request: Request) -> ConfigurationService:
    return request.app.state.configuration_service


@router.get("/export", response_model=ConfigurationDocument)
async def export_configuration(
    request: Request,
    response: Response,
) -> ConfigurationDocument:
    response.headers["Content-Disposition"] = (
        'attachment; filename="failure-simulation-config-v1.json"'
    )
    return get_configuration_service(request).export()


@router.post("/import", response_model=ConfigurationImportResult)
async def import_configuration(
    document: ConfigurationDocument,
    request: Request,
    dry_run: bool = Query(default=False),
) -> ConfigurationImportResult:
    return get_configuration_service(request).import_document(
        document,
        dry_run=dry_run,
    )
