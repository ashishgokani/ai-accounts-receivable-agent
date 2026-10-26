"""
Analytics and Dashboard KPI Aggregation Endpoints.

Computes real-time financial rollups, overdue portfolio aging,
and autonomous agent operational metrics directly from relational records.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.db.models import Invoice, Payment, Escalation, Followup, Approval, AgentAction
from app.services.penalty_engine import calculate_days_overdue, sync_invoice_financials

router = APIRouter(prefix="/api/analytics", tags=["Analytics & KPIs"])


@router.get("/dashboard")
def get_dashboard_metrics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Calculates consolidated financial and agent activity metrics for the Dashboard."""
    invoices = db.query(Invoice).all()

    total_invoiced_amount = 0.0
    total_outstanding_amount = 0.0
    total_overdue_amount = 0.0
    total_penalties_accrued = 0.0

    count_total = len(invoices)
    count_paid = 0
    count_pending = 0
    count_overdue = 0
    count_disputed = 0
    count_promised = 0
    count_escalated = 0

    overdue_days_sum = 0
    overdue_count_for_avg = 0

    for inv in invoices:
        sync_invoice_financials(inv, db)
        days = calculate_days_overdue(inv.due_date)
        total_invoiced_amount += inv.amount

        if inv.status == "PAID":
            count_paid += 1
        else:
            total_outstanding_amount += inv.total_amount
            total_penalties_accrued += inv.penalty_amount

            if inv.status == "OVERDUE" or days > 0:
                count_overdue += 1
                total_overdue_amount += inv.total_amount
                overdue_days_sum += days
                overdue_count_for_avg += 1

            if inv.status == "DISPUTED":
                count_disputed += 1
            elif inv.status == "PAYMENT_PROMISED":
                count_promised += 1
            elif inv.status == "ESCALATED":
                count_escalated += 1
            elif inv.status == "PENDING":
                count_pending += 1

    # Total settled payments
    payments_sum = (
        db.query(func.sum(Payment.amount))
        .filter(Payment.status == "SUCCESS")
        .scalar()
        or 0.0
    )

    # Collection rate calculation
    collection_rate = (
        round((payments_sum / total_invoiced_amount * 100), 1)
        if total_invoiced_amount > 0
        else 0.0
    )

    avg_days_overdue = (
        round(overdue_days_sum / overdue_count_for_avg, 1)
        if overdue_count_for_avg > 0
        else 0
    )

    # Approvals and Escalations
    pending_approvals = db.query(Approval).filter(Approval.status == "PENDING").count()
    active_escalations = db.query(Escalation).filter(Escalation.status == "OPEN").count()
    active_followups = db.query(Followup).filter(Followup.status == "PENDING").count()

    # Recent activity items
    recent_actions = (
        db.query(AgentAction)
        .order_by(AgentAction.created_at.desc())
        .limit(6)
        .all()
    )

    feed = []
    for a in recent_actions:
        feed.append({
            "id": a.action_id,
            "title": a.tool_name or a.action_type,
            "detail": a.action_type.replace("_", " ").title(),
            "time": a.created_at.strftime("%H:%M:%S"),
            "status": a.status,
        })

    return {
        "kpis": {
            "total_invoices_count": count_total,
            "total_outstanding": round(total_outstanding_amount, 2),
            "total_overdue": round(total_overdue_amount, 2),
            "total_collected": round(payments_sum, 2),
            "penalties_accrued": round(total_penalties_accrued, 2),
            "collection_rate_percent": collection_rate,
            "avg_days_overdue": avg_days_overdue,
        },
        "counts": {
            "paid": count_paid,
            "pending": count_pending,
            "overdue": count_overdue,
            "disputed": count_disputed,
            "promised": count_promised,
            "escalated": count_escalated,
            "pending_approvals": pending_approvals,
            "active_escalations": active_escalations,
            "active_followups": active_followups,
        },
        "recent_activities": feed,
    }
