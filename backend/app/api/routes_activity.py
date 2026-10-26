"""
Agent Activity Audit and Activity Log Endpoints.

Provides paginated audit trail queries with multi-faceted search, status,
tool action type, and date filtering for human governance and audit compliance.
"""

from datetime import datetime
import json
import math
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import AgentAction
from app.schemas.schemas import AgentActionResponse, PaginatedActivityResponse

router = APIRouter(prefix="/api/agent", tags=["Agent Activity"])


@router.get("/activity", response_model=PaginatedActivityResponse)
def get_agent_activity(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    session_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search term across action type, tool name, inputs, and outputs"),
    status: Optional[str] = Query(None, description="Filter by status: SUCCESS, PENDING_APPROVAL, ERROR, etc."),
    action_type: Optional[str] = Query(None, description="Filter by action type or tool name"),
    start_date: Optional[str] = Query(None, description="Filter from start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter to end date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Retrieves paginated audit trail with multi-faceted search, status, type, and date filtering."""
    query = db.query(AgentAction)

    if session_id:
        query = query.filter(AgentAction.session_id == session_id)

    if status and status.upper() != "ALL":
        query = query.filter(AgentAction.status == status.upper())

    if action_type and action_type.upper() != "ALL":
        query = query.filter(
            (AgentAction.action_type.ilike(f"%{action_type}%")) |
            (AgentAction.tool_name.ilike(f"%{action_type}%"))
        )

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (AgentAction.action_type.ilike(term)) |
            (AgentAction.tool_name.ilike(term)) |
            (AgentAction.input_data.ilike(term)) |
            (AgentAction.output_data.ilike(term))
        )

    if start_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(AgentAction.created_at >= s_date)
        except ValueError:
            pass

    if end_date:
        try:
            e_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(AgentAction.created_at <= e_date)
        except ValueError:
            pass

    total_count = query.count()
    total_pages = max(1, math.ceil(total_count / page_size))
    offset = (page - 1) * page_size

    actions = query.order_by(AgentAction.created_at.desc()).offset(offset).limit(page_size).all()

    formatted = []
    for a in actions:
        formatted.append(
            AgentActionResponse(
                action_id=a.action_id,
                session_id=a.session_id,
                action_type=a.action_type,
                tool_name=a.tool_name,
                input_data=json.loads(a.input_data) if a.input_data else None,
                output_data=json.loads(a.output_data) if a.output_data else None,
                status=a.status,
                created_at=a.created_at,
            )
        )

    return PaginatedActivityResponse(
        items=formatted,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
