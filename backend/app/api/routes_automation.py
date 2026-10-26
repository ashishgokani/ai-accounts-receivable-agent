"""
Automation Pipeline and Scheduler API Endpoints.

Provides live observability into the autonomous accounts receivable background worker,
including next scheduled actions with estimated times and historical email dispatches.
"""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import (
    AutomationStatusResponse,
    AutomationPipelineItem,
    AutomationHistoryItem,
    AutonomousRunResponse,
)
from app.services.scheduler import automation_scheduler

router = APIRouter(prefix="/api/automation", tags=["Automation Pipeline"])


@router.get("/status", response_model=AutomationStatusResponse)
def get_automation_status():
    """Returns background worker running state, execution interval, and next execution time."""
    return automation_scheduler.get_status()


@router.get("/pipeline", response_model=List[AutomationPipelineItem])
def get_automation_pipeline(db: Session = Depends(get_db)):
    """
    Returns upcoming automated tasks the system will execute next,
    along with estimated target timestamps and prioritization.
    """
    return automation_scheduler.get_upcoming_pipeline(db)


@router.get("/history", response_model=List[AutomationHistoryItem])
def get_automation_history(db: Session = Depends(get_db)):
    """
    Returns real auditable history of previous automated actions and sent emails.
    """
    return automation_scheduler.get_execution_history(db)


@router.post("/run-now", response_model=AutonomousRunResponse)
def trigger_automation_now(db: Session = Depends(get_db)):
    """Immediately triggers an autonomous monitoring cycle."""
    result = automation_scheduler.trigger_cycle_now(db)
    return AutonomousRunResponse(
        status=result["status"],
        invoices_analyzed=result["invoices_analyzed"],
        actions_executed=result["actions_executed"],
        approvals_pending=result["approvals_pending"],
        summary=result["summary"],
        action_logs=result["action_logs"],
    )
