"""
Backend CRUD Tools for the AI Agent.

Enables the autonomous agent to create customers, remove customers with strict
balance verification, generate new invoices, and update invoice parameters.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
import uuid
from sqlalchemy.orm import Session

from app.core.timezone import ist_today, ist_naive_now
from app.core.currency import format_inr
from app.db.models import Customer, Invoice, AgentAction
from app.services.penalty_engine import sync_invoice_financials, calculate_days_overdue
from app.services.email_service import EmailService


def tool_create_customer(
    db: Session,
    name: str,
    company_name: str,
    email: str,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    risk_level: str = "Low",
    risk_score: Optional[int] = None,
) -> Dict[str, Any]:
    """Onboards a new corporate debtor record into the database."""
    # Check if email is in use
    existing = db.query(Customer).filter(Customer.email == email).first()
    if existing:
        return {"error": f"Customer with email {email} already exists ({existing.customer_id})."}

    total_count = db.query(Customer).count()
    customer_id = f"CUST-{total_count + 101:03d}"
    risk_scores = {"Low": 20, "Medium": 50, "High": 85}
    final_score = risk_score if risk_score is not None else risk_scores.get(risk_level, 25)

    cust = Customer(
        customer_id=customer_id,
        name=name,
        company_name=company_name,
        email=email,
        phone=phone,
        address=address,
        risk_score=final_score,
        risk_level=risk_level,
        status="ACTIVE",
        created_at=ist_naive_now(),
        updated_at=ist_naive_now(),
    )
    db.add(cust)
    db.commit()

    return {
        "status": "SUCCESS",
        "customer_id": customer_id,
        "company_name": company_name,
        "email": email,
        "risk_level": risk_level,
        "risk_score": final_score,
        "message": f"Successfully onboarded customer {company_name} ({customer_id}).",
    }


def tool_list_customers(
    db: Session,
    status: str = "ACTIVE",
    risk_level: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Retrieves the corporate customer directory with aggregate statistics and risk stratification.
    Answers general queries like 'How many customers are there?' or 'List all customers'.
    """
    all_total = db.query(Customer).count()
    active_total = db.query(Customer).filter(Customer.status == "ACTIVE").count()
    archived_total = db.query(Customer).filter(Customer.status == "ARCHIVED").count()

    query = db.query(Customer)
    if status and status.upper() != "ALL":
        query = query.filter(Customer.status == status.upper())

    if risk_level and risk_level.upper() != "ALL":
        query = query.filter(Customer.risk_level.ilike(risk_level))

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(pattern))
            | (Customer.company_name.ilike(pattern))
            | (Customer.email.ilike(pattern))
            | (Customer.customer_id.ilike(pattern))
        )

    matched_customers = query.order_by(Customer.company_name.asc()).limit(limit).all()

    low_risk = db.query(Customer).filter(Customer.status == "ACTIVE", Customer.risk_level == "Low").count()
    med_risk = db.query(Customer).filter(Customer.status == "ACTIVE", Customer.risk_level == "Medium").count()
    high_risk = db.query(Customer).filter(Customer.status == "ACTIVE", Customer.risk_level == "High").count()

    customer_items = []
    for c in matched_customers:
        invoices = db.query(Invoice).filter(Invoice.customer_id == c.customer_id).all()
        outstanding = sum(inv.total_amount or inv.amount for inv in invoices if inv.status not in ["PAID", "CANCELLED"])
        overdue_count = sum(1 for inv in invoices if inv.status == "OVERDUE")

        customer_items.append({
            "customer_id": c.customer_id,
            "company_name": c.company_name,
            "contact_name": c.name,
            "email": c.email,
            "phone": c.phone or "N/A",
            "risk_level": c.risk_level,
            "risk_score": c.risk_score or 25,
            "status": c.status,
            "total_invoices": len(invoices),
            "overdue_invoices": overdue_count,
            "outstanding_balance": round(outstanding, 2),
        })

    return {
        "total_customers": all_total,
        "active_customers": active_total,
        "archived_customers": archived_total,
        "risk_breakdown": {
            "low_risk": low_risk,
            "medium_risk": med_risk,
            "high_risk": high_risk,
        },
        "returned_count": len(customer_items),
        "customers": customer_items,
    }


def tool_remove_customer(db: Session, customer_id: str) -> Dict[str, Any]:
    """
    Archives a customer.
    STRICT GUARDRAIL: Rejected if the customer has any pending or overdue invoices.
    """
    cust = (
        db.query(Customer)
        .filter((Customer.customer_id == customer_id) | (Customer.company_name.ilike(f"%{customer_id}%")))
        .first()
    )
    if not cust:
        return {"error": f"Customer '{customer_id}' not found."}

    # Verify no unsettled balances
    unsettled = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == cust.customer_id,
            Invoice.status.in_(["PENDING", "OVERDUE", "PAYMENT_PROMISED", "DISPUTED"]),
        )
        .all()
    )
    if unsettled:
        inv_nums = ", ".join(i.invoice_number for i in unsettled)
        return {
            "error": (
                f"Customer '{cust.company_name}' CANNOT be removed because they have "
                f"{len(unsettled)} unsettled invoices ({inv_nums}). "
                f"Outstanding balances must be fully resolved before archiving."
            ),
            "blocked_by_guardrail": True,
        }

    cust.status = "ARCHIVED"
    cust.updated_at = ist_naive_now()
    db.commit()

    return {
        "status": "SUCCESS",
        "customer_id": cust.customer_id,
        "company_name": cust.company_name,
        "message": f"Customer '{cust.company_name}' moved to Removed / Archived Section.",
    }


def tool_create_invoice(
    db: Session,
    customer_id: str,
    invoice_number: str,
    amount: float,
    due_date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a new receivable invoice in the database."""
    cust = (
        db.query(Customer)
        .filter((Customer.customer_id == customer_id) | (Customer.company_name.ilike(f"%{customer_id}%")))
        .first()
    )
    if not cust:
        return {"error": f"Customer '{customer_id}' not found."}

    existing_inv = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
    if existing_inv:
        return {"error": f"Invoice number '{invoice_number}' already exists."}

    # Parse due date
    if due_date_str:
        try:
            parsed_due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            parsed_due = ist_today() + timedelta(days=30)
    else:
        parsed_due = ist_today() + timedelta(days=30)

    count = db.query(Invoice).count()
    invoice_id = f"INV-{count + 1010}"

    inv = Invoice(
        invoice_id=invoice_id,
        customer_id=cust.customer_id,
        invoice_number=invoice_number,
        invoice_date=ist_today(),
        due_date=parsed_due,
        amount=amount,
        penalty_amount=0.0,
        total_amount=amount,
        status="PENDING",
        reminder_count=0,
        created_at=ist_naive_now(),
        updated_at=ist_naive_now(),
    )
    db.add(inv)
    db.commit()

    return {
        "status": "SUCCESS",
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "customer": cust.company_name,
        "amount": amount,
        "due_date": str(parsed_due),
        "message": f"Invoice {invoice_number} ({invoice_id}) for {format_inr(amount)} created successfully.",
    }


def tool_send_bulk_settlement_offer(
    db: Session,
    discount_percent: float = 0.1,
    hours_valid: int = 24,
    min_amount: Optional[float] = None,
    custom_message: Optional[str] = None,
    resolution_mode: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dispatches early settlement discount notices to customers matching optional minimum balance criteria.
    Atomically binds agreements into the official database commitment ledger.
    """
    from app.services.commitments_service import tool_apply_settlement_discount
    return tool_apply_settlement_discount(
        db=db,
        discount_percent=discount_percent,
        hours_valid=hours_valid,
        min_amount=min_amount,
        custom_message=custom_message,
        resolution_mode=resolution_mode,
        session_id=session_id,
    )


# ==================== UNIVERSAL AGENT COMMUNICATION ENGINE ====================
# Extracted into dedicated communication_tools module for modularity and maintainability
from app.services.communication_tools import tool_send_custom_communication

