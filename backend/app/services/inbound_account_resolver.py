"""
Inbound Email Account Context Resolver.

Inspects the relational database to construct an accurate, verified commercial snapshot
for the inbound sender:
- Validates whether sender is a registered customer.
- Partitions customer invoices into active open invoices vs fully settled invoices.
- Identifies any specific invoice numbers referenced in email headers or text.
- Determines the exact factual account status (NO_INVOICES_ON_FILE, ALL_INVOICES_SETTLED,
  SINGLE_OPEN_INVOICE, MULTIPLE_OPEN_INVOICES).
- Prevents LLM hallucinations regarding fictional invoices or unbacked payment receipts.
"""

import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.timezone import ist_today
from app.db.models import Customer, Invoice, Communication, InvoiceCommitment


def resolve_customer_account_context(
    db: Session,
    sender_email: str,
    subject: str = "",
    clean_text: str = "",
    quoted_history: str = "",
) -> Dict[str, Any]:
    """
    Constructs an exhaustive commercial and invoice ledger snapshot for an incoming email sender.
    
    Args:
        db: Active SQLAlchemy database session.
        sender_email: Sender email address extracted from RFC 822 envelope.
        subject: Email subject line.
        clean_text: Customer's fresh reply body (without quoted history).
        quoted_history: Historical email thread text.
        
    Returns:
        Dict[str, Any]: Comprehensive account state, invoice balances, and active commitments.
    """
    clean_sender = sender_email.strip().lower()
    cust = db.query(Customer).filter(Customer.email.ilike(clean_sender)).first()

    if not cust:
        return {
            "is_registered_customer": False,
            "customer_id": None,
            "customer_name": "Unregistered Sender",
            "company_name": "Unknown Entity",
            "account_status": "UNREGISTERED_SENDER",
            "total_open_balance": 0.0,
            "open_invoices": [],
            "settled_invoices": [],
            "primary_invoice": None,
            "referenced_invoice": None,
            "active_commitments": [],
            "recent_communications": [],
        }

    # 1. Fetch all customer invoices sorted by due date
    all_invoices = (
        db.query(Invoice)
        .filter(Invoice.customer_id == cust.customer_id)
        .order_by(Invoice.due_date.asc())
        .all()
    )

    open_invoices: List[Invoice] = []
    settled_invoices: List[Invoice] = []

    for inv in all_invoices:
        if inv.status in ("PAID", "SETTLED") or (inv.total_amount <= 0.01 and inv.status != "DISPUTED"):
            settled_invoices.append(inv)
        else:
            open_invoices.append(inv)

    total_open_balance = sum(float(inv.total_amount or 0.0) for inv in open_invoices)

    # 2. Extract referenced invoice numbers from text (e.g., INV-1002, INV-TEST-EA2286)
    combined_text = f"{subject} {clean_text} {quoted_history}"
    inv_matches = re.findall(r"(INV-[\w-]+)", combined_text, re.IGNORECASE)

    referenced_invoice: Optional[Invoice] = None
    if inv_matches:
        for match_num in inv_matches:
            found = next(
                (inv for inv in all_invoices if inv.invoice_number.lower() == match_num.lower() or inv.invoice_id.lower() == match_num.lower()),
                None,
            )
            if found:
                referenced_invoice = found
                break

    # 3. Select primary representative invoice
    primary_invoice: Optional[Invoice] = None
    if referenced_invoice:
        primary_invoice = referenced_invoice
    elif open_invoices:
        # Default to oldest overdue or due open invoice
        primary_invoice = open_invoices[0]
    elif settled_invoices:
        primary_invoice = settled_invoices[-1]

    # 4. Determine rigorous factual account status
    if not all_invoices:
        account_status = "NO_INVOICES_ON_FILE"
    elif not open_invoices:
        account_status = "ALL_INVOICES_SETTLED"
    elif len(open_invoices) == 1:
        account_status = "SINGLE_OPEN_INVOICE"
    else:
        account_status = "MULTIPLE_OPEN_INVOICES"

    # 5. Retrieve active commitments and recent communications
    commitments = (
        db.query(InvoiceCommitment)
        .filter(InvoiceCommitment.customer_id == cust.customer_id, InvoiceCommitment.status == "ACTIVE")
        .all()
    )
    active_commitments = [
        {
            "commitment_id": c.commitment_id,
            "invoice_id": c.invoice_id,
            "type": c.commitment_type,
            "description": c.description,
            "valid_until": c.valid_until.isoformat() if c.valid_until else None,
        }
        for c in commitments
    ]

    comms = (
        db.query(Communication)
        .filter(Communication.customer_id == cust.customer_id)
        .order_by(Communication.sent_at.desc())
        .limit(3)
        .all()
    )
    recent_comms = [
        {
            "type": c.type,
            "subject": c.subject,
            "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        }
        for c in comms
    ]

    return {
        "is_registered_customer": True,
        "customer": cust,
        "customer_id": cust.customer_id,
        "customer_name": cust.name or "Valued Customer",
        "company_name": cust.company_name or cust.name or "Valued Client",
        "account_status": account_status,
        "total_open_balance": total_open_balance,
        "open_invoices": open_invoices,
        "settled_invoices": settled_invoices,
        "primary_invoice": primary_invoice,
        "referenced_invoice": referenced_invoice,
        "active_commitments": active_commitments,
        "recent_communications": recent_comms,
    }
