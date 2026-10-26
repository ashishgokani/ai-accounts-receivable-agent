"""
Invoice Management API Endpoints.

Handles querying invoices with computed overdue aging and penalties,
creating new invoices, modifying invoice parameters, and manually triggering reminders.
"""

from datetime import datetime
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.session import get_db
from app.db.models import Invoice, Customer, AgentAction
from app.schemas.schemas import InvoiceResponse, InvoiceCreate, InvoiceUpdate
from app.services.penalty_engine import calculate_days_overdue, sync_invoice_financials
from app.services.tools import tool_draft_reminder_email, tool_send_email

router = APIRouter(prefix="/api/invoices", tags=["Invoices"])


def _format_invoice_response(inv: Invoice, db: Session) -> InvoiceResponse:
    """Helper formatting an Invoice model into a fully populated InvoiceResponse."""
    sync_invoice_financials(inv, db)
    days = calculate_days_overdue(inv.due_date)
    risk = inv.customer.risk_level if inv.customer and inv.customer.risk_level else "Medium"
    from app.services.settings_service import get_risk_penalty_rule
    rule = get_risk_penalty_rule(db, risk)
    return InvoiceResponse(
        invoice_id=inv.invoice_id,
        customer_id=inv.customer_id,
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        amount=inv.amount,
        penalty_amount=inv.penalty_amount,
        total_amount=inv.total_amount,
        status=inv.status,
        reminder_count=inv.reminder_count,
        last_reminder_at=inv.last_reminder_at,
        next_action_at=inv.next_action_at,
        dispute_reason=inv.dispute_reason,
        promised_payment_date=inv.promised_payment_date,
        customer_name=inv.customer.name if inv.customer else None,
        company_name=inv.customer.company_name if inv.customer else None,
        risk_level=risk,
        penalty_rate_percent=rule.penalty_rate_percent,
        days_overdue=days,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
    )


@router.get("", response_model=List[InvoiceResponse])
def list_invoices(
    status: Optional[str] = Query(None, description="Filter by status: Paid, Pending, Overdue, Disputed"),
    search: Optional[str] = Query(None, description="Search by invoice number or company name"),
    db: Session = Depends(get_db),
):
    """Retrieves all invoices enriched with live calculated overdue days and penalty amounts."""
    query = db.query(Invoice).join(Customer)

    if status and status.upper() != "ALL":
        query = query.filter(Invoice.status == status.upper())

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Invoice.invoice_id.ilike(pattern))
            | (Invoice.invoice_number.ilike(pattern))
            | (Customer.company_name.ilike(pattern))
        )

    invoices = query.order_by(Invoice.due_date.asc()).all()
    return [_format_invoice_response(inv, db) for inv in invoices]


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
    """Retrieves a single invoice record with complete billing context."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")
    return _format_invoice_response(inv, db)


@router.post("", response_model=InvoiceResponse, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    """
    Creates a new receivable invoice with deterministic initial validation.
    """
    # 1. Validate customer existence
    cust = db.query(Customer).filter(Customer.customer_id == payload.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail=f"Customer {payload.customer_id} does not exist.")

    # 2. Check invoice number uniqueness
    existing_num = db.query(Invoice).filter(Invoice.invoice_number == payload.invoice_number).first()
    if existing_num:
        raise HTTPException(status_code=400, detail=f"Invoice number '{payload.invoice_number}' already exists.")

    # 3. Create invoice ID
    count = db.query(Invoice).count()
    invoice_id = f"INV-{count + 1010}"

    new_inv = Invoice(
        invoice_id=invoice_id,
        customer_id=payload.customer_id,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        amount=payload.amount,
        penalty_amount=0.0,
        total_amount=payload.amount,
        status="PENDING",
        reminder_count=0,
        created_at=ist_naive_now(),
        updated_at=ist_naive_now(),
    )
    db.add(new_inv)
    db.commit()
    db.refresh(new_inv)

    # 4. Log audit trace
    action_log = AgentAction(
        action_id=f"ACT-{uuid.uuid4().hex[:6].upper()}",
        session_id="system-audit",
        action_type="INVOICE_CREATED",
        tool_name="create_invoice",
        input_data=f'{{"invoice_id": "{invoice_id}", "amount": {payload.amount}}}',
        output_data='{"status": "SUCCESS"}',
        status="SUCCESS",
        created_at=ist_naive_now(),
    )
    db.add(action_log)
    db.commit()

    return _format_invoice_response(new_inv, db)


@router.put("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(invoice_id: str, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    """
    Updates editable fields on an invoice (amount, due date, status, dispute reason, promised date).
    """
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")

    update_dict = payload.model_dump(exclude_unset=True)
    for key, val in update_dict.items():
        setattr(inv, key, val)

    inv.updated_at = ist_naive_now()
    sync_invoice_financials(inv, db)
    db.commit()
    db.refresh(inv)

    return _format_invoice_response(inv, db)


@router.post("/{invoice_id}/remind")
def trigger_invoice_reminder(invoice_id: str, db: Session = Depends(get_db)):
    """Manually dispatches an appropriate payment reminder for an invoice."""
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")

    draft = tool_draft_reminder_email(db, inv.invoice_id, reminder_level=inv.reminder_count + 1)
    result = tool_send_email(
        db, inv.invoice_id, draft["subject"], draft["body"], session_id="session-manual"
    )
    return result
