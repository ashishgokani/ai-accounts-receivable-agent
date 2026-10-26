"""
Operational Master Data Management and Automation Tools for the AI Agent.

Enables the autonomous agent to:
1. Update customer master profiles (name, email, phone, address, credit risk score/level).
2. Update invoice terms (due date, amounts with penalty recalculation, notes, dispute flags).
3. Trigger autonomous collection cycles on-demand.
4. Review pending human-in-the-loop approvals.
5. Provide portfolio-wide financial analytics and agent audit trails.

Enforces GAAP/IFRS financial immutability and PostgreSQL audit logging.
"""

from datetime import datetime, date
import json
import logging
from typing import Dict, Any, Optional, List
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.timezone import ist_naive_now, ist_today
from app.db.models import (
    Customer,
    Invoice,
    Approval,
    Escalation,
    Payment,
    AgentAction,
    Followup,
)
from app.services.penalty_engine import sync_invoice_financials, calculate_days_overdue
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


def tool_update_customer_profile(
    db: Session,
    customer_id: str,
    name: Optional[str] = None,
    company_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    risk_level: Optional[str] = None,
    risk_score: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Updates a customer's corporate profile, contact coordinates, or credit risk rating.
    """
    clean_id = customer_id.strip()
    cust = (
        db.query(Customer)
        .filter(
            (Customer.customer_id == clean_id)
            | (Customer.company_name.ilike(f"%{clean_id}%"))
            | (Customer.name.ilike(f"%{clean_id}%"))
            | (Customer.email.ilike(f"%{clean_id}%"))
        )
        .first()
    )
    if not cust:
        return {"error": f"Customer '{clean_id}' was not found in the database."}

    changes: List[str] = []

    # Validate email uniqueness if changing
    if email and email.strip().lower() != cust.email.lower():
        existing = db.query(Customer).filter(Customer.email == email.strip()).first()
        if existing and existing.customer_id != cust.customer_id:
            return {"error": f"Email '{email}' is already registered to another customer ({existing.company_name})."}
        changes.append(f"email: '{cust.email}' -> '{email.strip()}'")
        cust.email = email.strip()

    if name and name.strip() != cust.name:
        changes.append(f"contact name: '{cust.name}' -> '{name.strip()}'")
        cust.name = name.strip()

    if company_name and company_name.strip() != cust.company_name:
        changes.append(f"company: '{cust.company_name}' -> '{company_name.strip()}'")
        cust.company_name = company_name.strip()

    if phone is not None and phone.strip() != (cust.phone or ""):
        changes.append(f"phone: '{cust.phone}' -> '{phone.strip()}'")
        cust.phone = phone.strip()

    if address is not None and address.strip() != (cust.address or ""):
        changes.append(f"address: '{cust.address}' -> '{address.strip()}'")
        cust.address = address.strip()

    # Risk level and score adjustments
    if risk_level:
        valid_risk = risk_level.capitalize()
        if valid_risk not in ("Low", "Medium", "High"):
            return {"error": f"Invalid risk level '{risk_level}'. Must be 'Low', 'Medium', or 'High'."}
        if valid_risk != cust.risk_level:
            changes.append(f"risk level: '{cust.risk_level}' -> '{valid_risk}'")
            cust.risk_level = valid_risk
        # Auto-align risk score if not explicitly passed
        if risk_score is None:
            default_scores = {"Low": 20, "Medium": 50, "High": 85}
            expected_score = default_scores.get(valid_risk, cust.risk_score)
            if cust.risk_score != expected_score:
                cust.risk_score = expected_score
                changes.append(f"risk score: adjusted to {cust.risk_score}")

    if risk_score is not None:
        clamped_score = max(0, min(100, int(risk_score)))
        changes.append(f"risk score: {cust.risk_score} -> {clamped_score}")
        cust.risk_score = clamped_score

    if not changes:
        return {
            "status": "NO_CHANGES",
            "customer_id": cust.customer_id,
            "company_name": cust.company_name,
            "message": f"No modifications were necessary. Customer '{cust.company_name}' already matches provided values.",
        }

    cust.updated_at = ist_naive_now()
    db.commit()
    db.refresh(cust)

    return {
        "status": "SUCCESS",
        "customer_id": cust.customer_id,
        "company_name": cust.company_name,
        "name": cust.name,
        "email": cust.email,
        "phone": cust.phone,
        "address": cust.address,
        "risk_level": cust.risk_level,
        "risk_score": cust.risk_score,
        "changes_applied": changes,
        "message": f"Successfully updated customer '{cust.company_name}' ({cust.customer_id}): {', '.join(changes)}.",
    }


def tool_update_invoice_data(
    db: Session,
    invoice_id: str,
    due_date: Optional[str] = None,
    amount: Optional[float] = None,
    status: Optional[str] = None,
    dispute_reason: Optional[str] = None,
    promised_payment_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Updates invoice parameters, contractual dates, and dispute status with penalty syncing.
    STRICT FINANCIAL GUARDRAIL: PAID invoices are immutable under GAAP/IFRS standards.
    """
    clean_id = invoice_id.strip().upper()
    inv = (
        db.query(Invoice)
        .filter((Invoice.invoice_id == clean_id) | (Invoice.invoice_number.ilike(clean_id)))
        .first()
    )
    if not inv:
        return {"error": f"Invoice '{clean_id}' was not found in the database."}

    # Financial Immutability Guardrail
    if inv.status == "PAID":
        return {
            "error": f"Invoice '{inv.invoice_number}' is marked PAID and is legally immutable. Settled invoices cannot be altered.",
            "blocked_by_guardrail": True,
        }

    changes: List[str] = []

    # Amount modification
    if amount is not None and amount > 0:
        if round(amount, 2) != round(inv.amount, 2):
            changes.append(f"principal: ₹{inv.amount:,.2f} -> ₹{amount:,.2f}")
            inv.amount = round(amount, 2)

    # Due Date modification
    if due_date:
        try:
            parsed_date = datetime.strptime(due_date.strip(), "%Y-%m-%d").date()
            if parsed_date != inv.due_date:
                changes.append(f"due date: {inv.due_date} -> {parsed_date}")
                inv.due_date = parsed_date
        except ValueError:
            return {"error": f"Invalid due_date format '{due_date}'. Expected YYYY-MM-DD."}

    # Status modification
    if status:
        valid_statuses = ("PENDING", "OVERDUE", "DISPUTED", "PAYMENT_PROMISED", "ESCALATED", "PAID")
        norm_status = status.strip().upper()
        if norm_status not in valid_statuses:
            return {"error": f"Invalid invoice status '{status}'. Must be one of: {', '.join(valid_statuses)}."}
        if norm_status != inv.status:
            changes.append(f"status: {inv.status} -> {norm_status}")
            inv.status = norm_status

    if dispute_reason is not None:
        changes.append(f"dispute note updated")
        inv.dispute_reason = dispute_reason.strip() if dispute_reason else None

    if promised_payment_date is not None:
        try:
            if promised_payment_date.strip():
                prom_date = datetime.strptime(promised_payment_date.strip(), "%Y-%m-%d").date()
                changes.append(f"promised payment date: {prom_date}")
                inv.promised_payment_date = prom_date
            else:
                inv.promised_payment_date = None
        except ValueError:
            return {"error": f"Invalid promised_payment_date format '{promised_payment_date}'. Expected YYYY-MM-DD."}

    if not changes:
        return {
            "status": "NO_CHANGES",
            "invoice_number": inv.invoice_number,
            "message": f"No modifications required for invoice {inv.invoice_number}.",
        }

    # Recalculate deterministic penalties & overdue aging
    sync_invoice_financials(inv, db)
    inv.updated_at = ist_naive_now()
    db.commit()
    db.refresh(inv)

    return {
        "status": "SUCCESS",
        "invoice_id": inv.invoice_id,
        "invoice_number": inv.invoice_number,
        "amount": inv.amount,
        "penalty_amount": inv.penalty_amount,
        "total_amount": inv.total_amount,
        "due_date": str(inv.due_date),
        "invoice_status": inv.status,
        "changes_applied": changes,
        "message": f"Successfully updated invoice {inv.invoice_number} ({', '.join(changes)}).",
    }


def tool_trigger_automation_cycle(db: Session) -> Dict[str, Any]:
    """
    Executes an autonomous monitoring and collection cycle on-demand.
    """
    from app.services.scheduler import automation_scheduler
    result = automation_scheduler.trigger_cycle_now(db)
    return {
        "status": "SUCCESS",
        "invoices_analyzed": result.get("invoices_analyzed", 0),
        "actions_executed": result.get("actions_executed", 0),
        "approvals_pending": result.get("approvals_pending", 0),
        "summary": result.get("summary", "Autonomous collection cycle completed."),
        "action_logs": result.get("action_logs", []),
    }


def tool_get_pending_approvals(db: Session) -> Dict[str, Any]:
    """
    Retrieves human-in-the-loop actions waiting for manager sign-off.
    """
    approvals = db.query(Approval).filter(Approval.status == "PENDING").all()
    items = []
    for a in approvals:
        inv = db.query(Invoice).filter(Invoice.invoice_id == a.invoice_id).first()
        items.append({
            "approval_id": a.approval_id,
            "action_type": a.action_type,
            "invoice_id": a.invoice_id,
            "invoice_number": inv.invoice_number if inv else "N/A",
            "customer_company": inv.customer.company_name if inv and inv.customer else "Unknown",
            "total_amount": inv.total_amount if inv else 0.0,
            "requested_by": a.requested_by,
            "details": json.loads(a.details) if a.details else {},
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "N/A",
        })

    return {
        "total_pending": len(items),
        "approvals": items,
        "message": f"Found {len(items)} pending human approval request(s)." if items else "No pending approvals at this time.",
    }


def tool_review_approval_decision(
    db: Session,
    approval_id: str,
    decision: str,
    notes: Optional[str] = None,
    reviewed_by: str = "AR Manager",
    amount_received: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Approves, partially credits, or rejects a pending human-in-the-loop action request.
    Routes strictly through centralized ApprovalService for unified financial safety.
    """
    from app.services.approval_service import ApprovalService

    try:
        res = ApprovalService.apply_approval_decision(
            db=db,
            approval_id=approval_id,
            decision_status=decision,
            reviewed_by=reviewed_by,
            review_notes=notes,
            amount_received=amount_received,
        )
        return {
            "status": "SUCCESS",
            "approval_id": res["approval_id"],
            "decision": res["status"],
            "message": res["message"],
            "notification_sent": res.get("notification_sent", False),
        }
    except ValueError as val_err:
        return {"error": str(val_err)}
    except Exception as exc:
        return {"error": f"Failed to execute approval decision: {str(exc)}"}



def tool_get_financial_portfolio_summary(db: Session) -> Dict[str, Any]:
    """
    Computes real-time financial portfolio KPIs, collection rate, and debt health.
    """
    invoices = db.query(Invoice).all()

    total_invoiced = 0.0
    total_outstanding = 0.0
    total_overdue = 0.0
    total_penalties = 0.0
    paid_count = 0
    overdue_count = 0
    disputed_count = 0

    for inv in invoices:
        sync_invoice_financials(inv, db)
        days = calculate_days_overdue(inv.due_date)
        total_invoiced += inv.amount

        if inv.status == "PAID":
            paid_count += 1
        else:
            total_outstanding += inv.total_amount
            total_penalties += inv.penalty_amount
            if inv.status == "OVERDUE" or days > 0:
                overdue_count += 1
                total_overdue += inv.total_amount
            if inv.status == "DISPUTED":
                disputed_count += 1

    settled_payments = db.query(func.sum(Payment.amount)).filter(Payment.status == "SUCCESS").scalar() or 0.0
    collection_rate = round((settled_payments / total_invoiced * 100), 1) if total_invoiced > 0 else 0.0

    total_customers_count = db.query(Customer).count()
    active_customers_count = db.query(Customer).filter(Customer.status == "ACTIVE").count()
    high_risk_customers_count = db.query(Customer).filter(Customer.status == "ACTIVE", Customer.risk_level == "High").count()

    return {
        "total_customers": total_customers_count,
        "active_customers": active_customers_count,
        "high_risk_customers": high_risk_customers_count,
        "total_invoices": len(invoices),
        "total_invoiced_amount": total_invoiced,
        "total_outstanding_amount": total_outstanding,
        "total_overdue_amount": total_overdue,
        "total_penalties_accrued": total_penalties,
        "collection_efficiency_rate": f"{collection_rate}%",
        "paid_invoices_count": paid_count,
        "overdue_invoices_count": overdue_count,
        "disputed_invoices_count": disputed_count,
        "active_escalations": db.query(Escalation).filter(Escalation.status == "OPEN").count(),
        "pending_approvals": db.query(Approval).filter(Approval.status == "PENDING").count(),
    }


def tool_get_agent_audit_logs(db: Session, limit: int = 10) -> Dict[str, Any]:
    """
    Retrieves recent auditable agent decisions, tool invocations, and ledger executions.
    """
    safe_limit = max(1, min(50, limit))
    actions = db.query(AgentAction).order_by(AgentAction.created_at.desc()).limit(safe_limit).all()
    results = []
    for a in actions:
        results.append({
            "action_id": a.action_id,
            "action_type": a.action_type,
            "tool_name": a.tool_name or "N/A",
            "status": a.status,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "N/A",
        })

    return {
        "total_retrieved": len(results),
        "logs": results,
    }
