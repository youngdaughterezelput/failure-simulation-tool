from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models import Project, ProjectCreate
from app.services import ProjectDeleteResult, ProjectService


router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_project_service(request: Request) -> ProjectService:
    return request.app.state.project_service


def project_not_found(project_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Project {project_id} was not found",
    )


@router.get("", response_model=list[Project])
async def list_projects(request: Request) -> tuple[Project, ...]:
    return get_project_service(request).list()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, request: Request) -> Project:
    return get_project_service(request).create(data)


@router.put("/{project_id}", response_model=Project)
async def update_project(
    project_id: UUID,
    data: ProjectCreate,
    request: Request,
) -> Project:
    project = get_project_service(request).update(project_id, data)
    if project is None:
        raise project_not_found(project_id)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, request: Request) -> Response:
    result = get_project_service(request).delete(project_id)
    if result is ProjectDeleteResult.NOT_FOUND:
        raise project_not_found(project_id)
    if result is ProjectDeleteResult.IN_USE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project {project_id} still contains rules",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
