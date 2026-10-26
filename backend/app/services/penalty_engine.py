"""
Deterministic Financial Calculations and Penalty Engine.

Implements mathematical and date-based business rules in pure Python.
The AI Agent NEVER performs financial arithmetic directly, guaranteeing 100%
numerical reliability and zero hallucinations.
"""

from datetime import date
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.timezone import ist_today
from app.db.models import Invoice


def calculate_days_overdue(due_date: date, as_of: date = None) -> int:
    """
    Calculates exact elapsed calendar days past the invoice due date in IST.
    
    Args:
        due_date: Contractual payment deadline.
        as_of: Reference date (defaults to current date in IST).
        
    Returns:
        int: Number of days overdue (returns 0 if not yet due).
    """
    if as_of is None:
        as_of = ist_today()
    delta = (as_of - due_date).days
    return max(0, delta)


def compute_penalty(
    base_amount: float,
    days_overdue: int,
    rate_percent: float = settings.penalty_rate_percent,
    cycle_days: int = settings.penalty_days_cycle,
    grace_period_days: int = 14,
) -> float:
    """
    Computes accrued late interest penalty deterministically on principal only.
    
    Formula:
        Penalty = base_amount * (rate_percent / 100) * floor(days_overdue / cycle_days)
        Calculated strictly on the principal balance to avoid compounding interest.
        If days_overdue < grace_period_days, penalty is 0.0.
        
    Args:
        base_amount: Principal invoice amount in Rupees.
        days_overdue: Elapsed calendar days past due date.
        rate_percent: Penalty interest percentage per cycle (configured per risk tier).
        cycle_days: Duration of one billing cycle (default 30 days).
        grace_period_days: Grace period before penalties start accruing.
        
    Returns:
        float: Calculated penalty amount rounded to 2 decimal places.
    """
    if days_overdue <= 0 or days_overdue < grace_period_days:
        return 0.0

    # Number of full cycles past grace period (minimum 1 cycle once grace period exceeded)
    cycles = max(1, days_overdue // cycle_days)
    penalty = base_amount * (rate_percent / 100.0) * cycles
    return round(penalty, 2)


def sync_invoice_financials(invoice: Invoice, db: Session) -> Dict[str, Any]:
    """
    Synchronizes invoice aging, applies deterministic risk-tiered penalty calculations,
    and updates database records atomically.
    
    Args:
        invoice: Target Invoice model instance.
        db: Active SQLAlchemy database session.
        
    Returns:
        Dict[str, Any]: Dictionary containing updated financial metrics.
    """
    days = calculate_days_overdue(invoice.due_date)

    # 1. Deterministically query total verified payments from the payment ledger
    from app.db.models import Payment
    verified_payments = (
        db.query(Payment)
        .filter(Payment.invoice_id == invoice.invoice_id, Payment.status == "SUCCESS")
        .all()
    )
    total_paid = sum(p.amount for p in verified_payments)

    # 2. Preserve original invoiced principal; calculate net remaining balance
    remaining_principal = max(0.0, round(invoice.amount - total_paid, 2))

    if remaining_principal <= 0.01:
        # Paid in full
        invoice.status = "PAID"
        invoice.penalty_amount = 0.0
        invoice.total_amount = 0.0
    elif invoice.status in ("OVERDUE", "DISPUTED", "PARTIALLY_PAID") and days > 0:
        risk_level = invoice.customer.risk_level if invoice.customer else "Low"
        try:
            from app.services.settings_service import get_risk_penalty_rule
            rule = get_risk_penalty_rule(db, risk_level)
            rate_percent = rule.penalty_rate_percent
            grace_period = rule.grace_period_days
        except Exception:
            rate_percent = settings.penalty_rate_percent
            grace_period = 14

        # Penalties accrue strictly on the unpaid balance, not on paid principal
        penalty = compute_penalty(
            base_amount=remaining_principal,
            days_overdue=days,
            rate_percent=rate_percent,
            grace_period_days=grace_period,
        )
        invoice.penalty_amount = penalty
        invoice.total_amount = round(remaining_principal + penalty, 2)
        if invoice.status not in ("DISPUTED", "PAYMENT_PROMISED"):
            invoice.status = "OVERDUE"
    else:
        # Pending or non-overdue with remaining balance
        invoice.penalty_amount = 0.0
        invoice.total_amount = remaining_principal
        if total_paid > 0 and invoice.status not in ("DISPUTED", "PAYMENT_PROMISED"):
            invoice.status = "PARTIALLY_PAID"

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return {
        "invoice_id": invoice.invoice_id,
        "original_amount": invoice.amount,
        "total_paid": total_paid,
        "remaining_principal": remaining_principal,
        "days_overdue": days,
        "penalty_amount": invoice.penalty_amount,
        "total_amount": invoice.total_amount,
        "status": invoice.status,
    }



def determine_recommended_action(invoice: Invoice, db: Optional[Session] = None) -> Tuple[str, str]:
    """
    Evaluates risk-tiered business policy rules to determine the exact next workflow action.
    
    Args:
        invoice: Invoice model instance.
        db: Optional database session to load admin reminder settings.
        
    Returns:
        Tuple[str, str]: (Action Code, Explanation Reason).
    """
    if invoice.status == "PAID":
        return "NO_ACTION", "Invoice has already been settled in full."

    # Load configured reminder rules for customer risk tier
    risk_level = invoice.customer.risk_level if invoice.customer else "Low"
    auto_reminders = True
    first_days = 1
    interval_days = 5
    max_reminders = settings.max_reminders_before_escalation
    pause_dispute = True

    if db:
        try:
            from app.services.settings_service import get_risk_reminder_rule
            rule = get_risk_reminder_rule(db, risk_level)
            auto_reminders = rule.auto_reminders_enabled
            first_days = rule.first_reminder_days
            interval_days = rule.reminder_interval_days
            max_reminders = rule.max_reminders_before_escalation
            pause_dispute = rule.pause_on_dispute
        except Exception:
            pass

    if invoice.status == "DISPUTED":
        if pause_dispute:
            return "PAUSE_REMINDERS", f"Invoice is in dispute: '{invoice.dispute_reason}'. Reminders paused per settings."

    if invoice.status == "PAYMENT_PROMISED":
        return "MONITOR_PROMISE", f"Customer committed to pay by {invoice.promised_payment_date}."

    if not auto_reminders:
        return "NO_ACTION", f"Automatic collection reminders disabled for {risk_level} Risk tier in Admin Settings."

    days = calculate_days_overdue(invoice.due_date)

    if days == 0:
        return "NO_ACTION", "Invoice is not yet overdue."

    if days < first_days and invoice.reminder_count == 0:
        return "NO_ACTION", f"Invoice is {days} days past due; first reminder configured after {first_days} days."

    # Escalation check
    if days >= settings.escalation_overdue_days_threshold or invoice.reminder_count >= max_reminders:
        return "ESCALATE", f"Invoice is {days} days overdue with {invoice.reminder_count} reminders sent. Maximum allowed reminders ({max_reminders}) reached."

    # Check interval since last reminder
    if invoice.reminder_count > 0 and invoice.last_reminder_at:
        from app.core.timezone import ist_naive_now
        elapsed_days = (ist_naive_now() - invoice.last_reminder_at).days
        if elapsed_days < interval_days:
            return "WAITING_INTERVAL", f"Next reminder scheduled in {interval_days - elapsed_days} days."

    # Subsequent reminder
    if invoice.reminder_count >= 1:
        return "SECOND_REMINDER", f"Invoice is {days} days overdue with {invoice.reminder_count} previous reminder(s). Next reminder required."

    # Initial reminder
    if invoice.reminder_count == 0:
        return "FIRST_REMINDER", f"Invoice is {days} days overdue with 0 reminders sent. Initial notice required."

    return "FOLLOW_UP", f"Follow-up required. Days overdue: {days}, Reminders sent: {invoice.reminder_count}."
