"""
Human-in-the-Loop Approval Endpoints.

Allows administrators to review, approve, or reject high-risk autonomous proposals
such as large-value escalations, legal notices, and disputed debt actions.
"""

from datetime import datetime
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.session import get_db
from app.db.models import Approval, Invoice, Escalation
from app.schemas.schemas import ApprovalResponse, ApprovalDecision
from app.services.email_service import EmailService
from app.services.tools import log_agent_action

router = APIRouter(prefix="/api/approvals", tags=["Human Approvals"])


@router.get("", response_model=List[ApprovalResponse])
def list_approvals(db: Session = Depends(get_db)):
    """Retrieves all pending human-in-the-loop approval requests."""
    approvals = db.query(Approval).filter(Approval.status == "PENDING").all()
    results = []

    for a in approvals:
        inv = db.query(Invoice).filter(Invoice.invoice_id == a.invoice_id).first()
        results.append(
            ApprovalResponse(
                approval_id=a.approval_id,
                action_type=a.action_type,
                invoice_id=a.invoice_id,
                customer_id=a.customer_id,
                company_name=inv.customer.company_name if inv and inv.customer else "Unknown",
                requested_by=a.requested_by,
                details=json.loads(a.details) if a.details else {},
                status=a.status,
                reviewed_by=a.reviewed_by,
                review_notes=a.review_notes,
                created_at=a.created_at,
                reviewed_at=a.reviewed_at,
            )
        )
    return results


@router.post("/{approval_id}/decision")
def review_approval(approval_id: str, decision: ApprovalDecision, db: Session = Depends(get_db)):
    """
    Records administrative sign-off, partial payment credit, or rejection for a pending proposal.
    Executes centralized, deterministic business logic via ApprovalService.
    """
    from app.services.approval_service import ApprovalService

    try:
        result = ApprovalService.apply_approval_decision(
            db=db,
            approval_id=approval_id,
            decision_status=decision.status,
            reviewed_by=decision.reviewed_by,
            review_notes=decision.review_notes,
            amount_received=decision.amount_received,
            custom_subject=decision.custom_subject,
            custom_body=decision.custom_body,
        )
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process approval decision: {str(exc)}")

