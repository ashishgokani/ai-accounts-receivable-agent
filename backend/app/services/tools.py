"""
Executable Backend Tools Registry for the AI Agent.

Provides strictly validated, deterministic business functions callable by the
Intelligent Orchestrator via function/tool calling. The LLM can never write
directly to the database or send unvalidated emails.
"""

from datetime import datetime, date, timedelta
import uuid
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.timezone import ist_naive_now, ist_now
from app.core.currency import format_inr

from app.db.models import (
    Customer,
    Invoice,
    Payment,
    Followup,
    Escalation,
    AgentAction,
    Approval,
)
from app.services.penalty_engine import (
    calculate_days_overdue,
    sync_invoice_financials,
)
from app.services.email_service import EmailService
from app.core.guardrails import (
    validate_invoice_for_action,
    requires_human_approval,
)
from app.services.tools_history import (
    tool_get_communication_history,
    tool_get_invoice_commitments,
)


def log_agent_action(
    db: Session,
    session_id: str,
    action_type: str,
    tool_name: str,
    input_data: Dict[str, Any],
    output_data: Dict[str, Any],
    status: str = "SUCCESS",
) -> AgentAction:
    """Logs an auditable record of the agent's intermediate tool invocation."""
    action = AgentAction(
        action_id=f"ACT-{uuid.uuid4().hex[:8].upper()}",
        session_id=session_id or "session-web",
        action_type=action_type,
        tool_name=tool_name,
        input_data=json.dumps(input_data, default=str),
        output_data=json.dumps(output_data, default=str),
        status=status,
        created_at=ist_naive_now(),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


# ==================== TOOL 1: GET OVERDUE INVOICES ====================
def tool_get_overdue_invoices(db: Session, min_days: int = 0, limit: int = 20) -> Dict[str, Any]:
    """Retrieves all unpaid invoices currently exceeding their contractual due date."""
    invoices = (
        db.query(Invoice)
        .filter(Invoice.status.in_(["OVERDUE", "PENDING"]))
        .all()
    )

    results = []
    for inv in invoices:
        sync_invoice_financials(inv, db)
        days = calculate_days_overdue(inv.due_date)
        if days >= min_days:
            results.append({
                "invoice_id": inv.invoice_id,
                "invoice_number": inv.invoice_number or inv.invoice_id,
                "customer_id": inv.customer_id,
                "company_name": inv.customer.company_name if inv.customer else "Unknown",
                "customer_name": inv.customer.name if inv.customer else "Contact",
                "amount": inv.amount,
                "penalty_amount": inv.penalty_amount,
                "total_amount": inv.total_amount,
                "due_date": inv.due_date.isoformat(),
                "days_overdue": days,
                "reminder_count": inv.reminder_count,
                "status": inv.status,
            })

    results.sort(key=lambda x: x["days_overdue"], reverse=True)
    return {"total_found": len(results), "invoices": results[:limit]}


# ==================== TOOL 2: GET INVOICE DETAILS ====================
def tool_get_invoice_details(db: Session, invoice_id: str) -> Dict[str, Any]:
    """Retrieves detailed record for a specific invoice including customer information."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice with ID {invoice_id} not found."}

    sync_invoice_financials(inv, db)
    days = calculate_days_overdue(inv.due_date)

    return {
        "invoice_id": inv.invoice_id,
        "customer_id": inv.customer_id,
        "company_name": inv.customer.company_name if inv.customer else "Unknown",
        "customer_email": inv.customer.email if inv.customer else "",
        "amount": inv.amount,
        "penalty_amount": inv.penalty_amount,
        "total_amount": inv.total_amount,
        "due_date": inv.due_date.isoformat(),
        "days_overdue": days,
        "reminder_count": inv.reminder_count,
        "status": inv.status,
        "last_reminder_at": inv.last_reminder_at.isoformat() if inv.last_reminder_at else None,
        "dispute_reason": inv.dispute_reason,
        "promised_payment_date": inv.promised_payment_date.isoformat() if inv.promised_payment_date else None,
    }


# ==================== TOOL 3: GET CUSTOMER DETAILS & HISTORY ====================
def tool_get_customer_history(db: Session, customer_id: str) -> Dict[str, Any]:
    """Retrieves customer background, historical payment track record, and risk profile."""
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not cust:
        # Search by company name, contact person name, or email if ID not exact
        cust = db.query(Customer).filter(
            (Customer.company_name.ilike(f"%{customer_id}%"))
            | (Customer.name.ilike(f"%{customer_id}%"))
            | (Customer.email.ilike(f"%{customer_id}%"))
        ).first()

    if not cust:
        return {"error": f"Customer '{customer_id}' not found in records."}

    all_invoices = db.query(Invoice).filter(Invoice.customer_id == cust.customer_id).all()
    total_invoices = len(all_invoices)
    paid_invoices = sum(1 for i in all_invoices if i.status == "PAID")
    overdue_invoices = sum(1 for i in all_invoices if i.status == "OVERDUE")
    disputed_invoices = sum(1 for i in all_invoices if i.status == "DISPUTED")

    return {
        "customer_id": cust.customer_id,
        "company_name": cust.company_name,
        "contact_name": cust.name,
        "email": cust.email,
        "phone": cust.phone,
        "risk_score": cust.risk_score,
        "risk_level": cust.risk_level,
        "total_invoices": total_invoices,
        "paid_invoices": paid_invoices,
        "overdue_invoices": overdue_invoices,
        "disputed_invoices": disputed_invoices,
        "payment_reliability": f"{(paid_invoices / total_invoices * 100):.1f}%" if total_invoices > 0 else "N/A",
    }


# ==================== TOOL 4: DRAFT REMINDER EMAIL ====================
def tool_draft_reminder_email(
    db: Session,
    invoice_id: str,
    reminder_level: int = 1,
    tone: str = "polite",
    custom_instructions: Optional[str] = None,
) -> Dict[str, Any]:
    """Constructs an AI-generated, authentic customer email draft with live database numbers and remittance details."""
    from app.services.ai_email_drafter import draft_reminder_email_with_ai
    return draft_reminder_email_with_ai(
        db=db,
        invoice_id=invoice_id,
        reminder_level=reminder_level,
        tone=tone,
        custom_instructions=custom_instructions,
    )


# ==================== TOOL 5: SEND EMAIL (GUARDRAIL PROTECTED) ====================
def tool_send_email(
    db: Session,
    invoice_id: str,
    subject: str,
    body: str,
    recipient: Optional[str] = None,
    session_id: str = "session-web",
    admin_approved: bool = False,
) -> Dict[str, Any]:
    """Dispatches validated email, updates reminder counters, and verifies safety guardrails."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice {invoice_id} does not exist."}

    # Verify action against guardrails
    allowed, reason = validate_invoice_for_action(inv, "SEND_REMINDER")
    if not allowed:
        return {"status": "BLOCKED_BY_GUARDRAIL", "reason": reason}

    # Check if human approval is required (high-value or 3rd reminder)
    action_type = "SEND_THIRD_REMINDER" if inv.reminder_count >= 2 else "SEND_REMINDER"
    requires_approval, approval_reason = requires_human_approval(inv, action_type)

    if requires_approval and not admin_approved:
        # Prevent creating multiple duplicate pending approvals for the same invoice and action
        existing_appr = db.query(Approval).filter(
            Approval.invoice_id == inv.invoice_id,
            Approval.action_type == action_type,
            Approval.status == "PENDING",
        ).first()

        if existing_appr:
            return {
                "status": "PENDING_APPROVAL",
                "approval_id": existing_appr.approval_id,
                "reason": approval_reason,
                "message": f"Approval request for {action_type} on invoice {invoice_id} is already pending admin review (Approval ID: {existing_appr.approval_id}). Duplicate request suppressed.",
                "already_pending": True,
            }

        approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
        appr = Approval(
            approval_id=approval_id,
            action_type=action_type,
            invoice_id=inv.invoice_id,
            customer_id=inv.customer_id,
            requested_by="AI Agent",
            details=json.dumps({"subject": subject, "body": body, "amount": inv.total_amount}),
            status="PENDING",
            created_at=ist_naive_now(),
        )
        db.add(appr)
        db.commit()

        log_agent_action(
            db, session_id, "SEND_EMAIL_PENDING_APPROVAL", "send_email",
            {"invoice_id": invoice_id, "subject": subject},
            {"status": "PENDING_APPROVAL", "approval_id": approval_id, "reason": approval_reason},
            status="PENDING_APPROVAL",
        )

        return {
            "status": "PENDING_APPROVAL",
            "approval_id": approval_id,
            "message": f"Action paused for Human Review: {approval_reason}",
        }

    # Deliver email and record communication
    result = EmailService.send_customer_email(
        db=db,
        customer_id=inv.customer_id,
        invoice_id=inv.invoice_id,
        subject=subject,
        message=body,
        comm_type="REMINDER",
        direction="OUTGOING",
    )

    if result.get("status") == "FAILED_DISPATCH":
        log_agent_action(
            db, session_id, "EMAIL_DISPATCH_FAILED", "send_email",
            {"invoice_id": invoice_id, "subject": subject},
            result,
            status="FAILED",
        )
        return {
            "status": "FAILED_DISPATCH",
            "invoice_id": inv.invoice_id,
            "error": result.get("error") or "SMTP provider failed to dispatch email.",
            "delivery_details": result,
        }

    # Increment reminder counter and update timestamp on successful dispatch
    inv.reminder_count += 1
    inv.last_reminder_at = ist_naive_now()
    inv.next_action_at = ist_naive_now() + timedelta(days=7)
    db.commit()

    log_agent_action(
        db, session_id, "EMAIL_DISPATCHED", "send_email",
        {"invoice_id": invoice_id, "subject": subject},
        result,
        status="SUCCESS",
    )

    return {
        "status": "SENT",
        "invoice_id": inv.invoice_id,
        "reminder_count": inv.reminder_count,
        "delivery_details": result,
    }


# ==================== TOOL 6: UPDATE INVOICE STATUS ====================
def tool_update_invoice_status(
    db: Session, invoice_id: str, new_status: str, notes: Optional[str] = None
) -> Dict[str, Any]:
    """Updates invoice workflow status with validity checks."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice {invoice_id} not found."}

    valid_statuses = ["PENDING", "PAID", "OVERDUE", "PAYMENT_PROMISED", "DISPUTED", "ESCALATED", "CANCELLED"]
    if new_status.upper() not in valid_statuses:
        return {"error": f"Invalid status '{new_status}'. Allowed: {valid_statuses}"}

    old_status = inv.status
    inv.status = new_status.upper()
    if notes:
        inv.dispute_reason = notes
    db.commit()

    return {
        "status": "UPDATED",
        "invoice_id": inv.invoice_id,
        "old_status": old_status,
        "new_status": inv.status,
    }


# ==================== TOOL 7: CREATE FOLLOW-UP ====================
def tool_create_followup(
    db: Session, invoice_id: str, action_type: str, scheduled_days: int = 7
) -> Dict[str, Any]:
    """Schedules a future automated follow-up check."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice {invoice_id} not found."}

    followup = Followup(
        followup_id=f"FOL-{uuid.uuid4().hex[:8].upper()}",
        invoice_id=inv.invoice_id,
        customer_id=inv.customer_id,
        action_type=action_type,
        scheduled_at=ist_naive_now() + timedelta(days=scheduled_days),
        status="PENDING",
        created_at=ist_naive_now(),
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)

    return {
        "status": "SCHEDULED",
        "followup_id": followup.followup_id,
        "scheduled_for": followup.scheduled_at.isoformat(),
        "action_type": action_type,
    }


# ==================== TOOL 8: CREATE ESCALATION ====================
def tool_create_escalation(
    db: Session, invoice_id: str, reason: str, assigned_to: str = "Ashish Gokani (Admin)"
) -> Dict[str, Any]:
    """Escalates severely overdue account to human management for legal or credit freeze action."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice {invoice_id} not found."}

    sync_invoice_financials(inv, db)
    days = calculate_days_overdue(inv.due_date)

    # Escalations ALWAYS require human approval gate.
    # Check if an escalation approval is ALREADY pending for this invoice to prevent duplicates
    existing_appr = db.query(Approval).filter(
        Approval.invoice_id == inv.invoice_id,
        Approval.action_type == "ESCALATE",
        Approval.status == "PENDING",
    ).first()

    if existing_appr:
        return {
            "status": "PENDING_APPROVAL",
            "approval_id": existing_appr.approval_id,
            "invoice_id": invoice_id,
            "message": f"Escalation for invoice {invoice_id} is already pending manager approval (Approval ID: {existing_appr.approval_id}). Duplicate request suppressed.",
            "already_pending": True,
        }

    approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
    appr = Approval(
        approval_id=approval_id,
        action_type="ESCALATE",
        invoice_id=inv.invoice_id,
        customer_id=inv.customer_id,
        requested_by="AI Agent",
        details=json.dumps({
            "reason": reason,
            "days_overdue": days,
            "amount": inv.total_amount,
            "assigned_to": assigned_to,
        }),
        status="PENDING",
        created_at=ist_naive_now(),
    )
    db.add(appr)
    db.commit()

    return {
        "status": "PENDING_APPROVAL",
        "approval_id": approval_id,
        "invoice_id": inv.invoice_id,
        "message": f"Escalation request queued for human administrator approval (Amount: {format_inr(inv.total_amount)}, Days Overdue: {days}).",
    }


# ==================== TOOL 9: RECORD PAYMENT ====================
def tool_record_payment(
    db: Session,
    invoice_id: str,
    amount: float,
    payment_method: str = "NEFT",
    reference_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Records payment settlement, marks invoice PAID, auto-cancels pending followups, and sends receipt."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice {invoice_id} not found."}

    if not reference_number:
        reference_number = f"REF/{ist_now().year}/{uuid.uuid4().hex[:6].upper()}"

    # 1. Create Payment record
    pay = Payment(
        payment_id=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        invoice_id=inv.invoice_id,
        customer_id=inv.customer_id,
        amount=amount,
        payment_date=ist_naive_now(),
        payment_method=payment_method,
        reference_number=reference_number,
        status="SUCCESS",
        created_at=ist_naive_now(),
    )
    db.add(pay)

    # 2. Update Invoice to PAID and zero out penalties
    inv.status = "PAID"
    inv.penalty_amount = 0.0
    inv.total_amount = inv.amount

    # 3. Automatically cancel all pending follow-ups for this invoice
    pending_followups = db.query(Followup).filter(
        Followup.invoice_id == inv.invoice_id,
        Followup.status == "PENDING"
    ).all()
    for fol in pending_followups:
        fol.status = "CANCELLED"
        fol.completed_at = ist_naive_now()

    db.commit()

    # 4. Dispatch Payment Confirmation Email
    confirmation = EmailService.send_payment_confirmation(db, pay)

    return {
        "status": "PAID",
        "payment_id": pay.payment_id,
        "invoice_id": inv.invoice_id,
        "amount_received": amount,
        "followups_cancelled": len(pending_followups),
        "confirmation_email": confirmation,
    }
