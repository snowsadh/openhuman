from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.employees.schemas import (
    CreateEmployeeRequest,
    DiscordTokenRequest,
    EmployeeResponse,
    SlackTokenRequest,
    StatusRequest,
    UpdateEmployeeRequest,
)
from app.employees.service import (
    DuplicateEmployeeTypeError,
    create_employee,
    delete_employee,
    get_employee,
    get_employee_model,
    list_employees,
    store_discord_token,
    store_slack_token,
    update_employee,
    update_status,
)
from app.memory.service import render_graph_visualization_html

router = APIRouter(
    prefix="/api/organizations/{org_id}/employees",
    tags=["employees"],
)


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee_route(
    org_id: UUID,
    data: CreateEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmployeeResponse:
    try:
        result = await create_employee(db, org_id, current_user.id, data)
    except DuplicateEmployeeTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return result


@router.get("", response_model=list[EmployeeResponse])
async def list_employees_route(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EmployeeResponse]:
    result = await list_employees(db, org_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return result


@router.get("/{emp_id}", response_model=EmployeeResponse)
async def get_employee_route(
    org_id: UUID,
    emp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmployeeResponse:
    result = await get_employee(db, org_id, emp_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return result


@router.get("/{emp_id}/knowledge-graph", response_class=HTMLResponse)
async def get_employee_knowledge_graph(
    org_id: UUID,
    emp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    employee = await get_employee_model(db, org_id, emp_id, current_user.id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )
    if not employee.cognee_dataset_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge graph dataset not found for employee",
        )

    try:
        html = await render_graph_visualization_html(
            employee.cognee_dataset_id,
            user_id=employee.cognee_user_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render knowledge graph: {exc}",
        ) from exc

    return HTMLResponse(content=html)


@router.patch("/{emp_id}", response_model=EmployeeResponse)
async def update_employee_route(
    org_id: UUID,
    emp_id: UUID,
    data: UpdateEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmployeeResponse:
    try:
        result = await update_employee(db, org_id, emp_id, current_user.id, data)
    except DuplicateEmployeeTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return result


@router.delete("/{emp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee_route(
    org_id: UUID,
    emp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = await delete_employee(db, org_id, emp_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")


@router.put("/{emp_id}/discord", response_model=EmployeeResponse)
async def set_discord_token(
    org_id: UUID,
    emp_id: UUID,
    data: DiscordTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmployeeResponse:
    """Store an encrypted Discord bot token for this employee."""
    result = await store_discord_token(db, org_id, emp_id, current_user.id, data.token)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return result


@router.put("/{emp_id}/slack", response_model=EmployeeResponse)
async def set_slack_token(
    org_id: UUID,
    emp_id: UUID,
    data: SlackTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmployeeResponse:
    """Store an encrypted Slack bot token for this employee."""
    result = await store_slack_token(db, org_id, emp_id, current_user.id, data.token)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return result


@router.put("/{emp_id}/status", response_model=EmployeeResponse)
async def set_status(
    org_id: UUID,
    emp_id: UUID,
    data: StatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmployeeResponse:
    """Activate or deactivate an employee."""
    allowed = {"active", "inactive", "suspended"}
    if data.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {sorted(allowed)}",
        )
    result = await update_status(db, org_id, emp_id, current_user.id, data.status)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return result

