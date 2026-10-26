"""
Admin Settings API Endpoints.

Provides RESTful endpoints for viewing and configuring:
1. Penalty & Financial Rules.
2. Payment Reminders & Escalation Schedules.
3. Payment & Bank Details.
4. AI Agent Master Operational Switch.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Invoice
from app.services.penalty_engine import sync_invoice_financials
from app.services.scheduler import automation_scheduler
from app.services.settings_service import (
    AllAdminSettings,
    PenaltySettings,
    ReminderSettings,
    BankSettings,
    AgentSettings,
    get_all_settings,
    update_penalty_settings,
    update_reminder_settings,
    update_bank_settings,
    update_agent_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Admin Settings"])


@router.get("", response_model=AllAdminSettings)
def read_all_settings(db: Session = Depends(get_db)):
    """
    Retrieves all 4 settings sections for the Admin Settings dashboard.
    """
    try:
        return get_all_settings(db)
    except Exception as exc:
        logger.error("Failed to load admin settings: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load system settings: {str(exc)}",
        )


@router.put("/penalty", response_model=PenaltySettings)
def save_penalty_settings(payload: PenaltySettings, db: Session = Depends(get_db)):
    """
    Updates financial penalty rates and grace periods by risk tier,
    and immediately recalculates financial standing across all unsettled invoices.
    """
    try:
        updated = update_penalty_settings(db, payload)
        # Instantly recalculate penalty amounts on all active/unsettled accounts
        unsettled = (
            db.query(Invoice)
            .filter(Invoice.status.in_(["PENDING", "OVERDUE", "DISPUTED", "PAYMENT_PROMISED"]))
            .all()
        )
        for inv in unsettled:
            sync_invoice_financials(inv, db)
        return updated
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed to update penalty settings: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update penalty rules: {str(exc)}",
        )


@router.put("/reminders", response_model=ReminderSettings)
def save_reminder_settings(payload: ReminderSettings, db: Session = Depends(get_db)):
    """
    Updates reminder schedules, intervals, and global automation toggles,
    and immediately reconfigures the background scheduler runtime and persistence.
    """
    try:
        updated = update_reminder_settings(db, payload)
        # Instantly reconfigure the running background scheduler and persist state
        automation_scheduler.reconfigure(
            new_interval_minutes=payload.automation_interval_minutes,
            enabled=payload.automation_enabled,
            db=db,
        )
        return updated
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed to update reminder settings: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update reminder rules: {str(exc)}",
        )


@router.put("/bank", response_model=BankSettings)
def save_bank_settings(payload: BankSettings, db: Session = Depends(get_db)):
    """
    Updates corporate banking remittance details with account number confirmation.
    """
    try:
        updated = update_bank_settings(db, payload)
        return updated
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed to update bank settings: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update bank details: {str(exc)}",
        )


@router.put("/agent", response_model=AgentSettings)
def save_agent_settings(payload: AgentSettings, db: Session = Depends(get_db)):
    """
    Enables or disables the AI Agent master operational switch.
    """
    try:
        updated = update_agent_settings(db, payload)
        return updated
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed to update agent settings: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update AI agent status: {str(exc)}",
        )
