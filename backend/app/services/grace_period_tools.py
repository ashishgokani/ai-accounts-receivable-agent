"""
Grace Period and Commercial Agreement Revocation Tools.

Provides specialized tools to grant payment extensions, pause automated
collection sequences, and revoke commercial agreements when terms are violated.
"""

from datetime import timedelta
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.models import Invoice, InvoiceCommitment
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


def tool_grant_grace_period(
    db: Session,
    invoice_id: str,
    days: int,
    reason: str = "Managerial extension requested in chat",
) -> Dict[str, Any]:
    """
    Grants a formal payment extension and freezes automated collection reminders.
    Mutates invoice next_action_at and records an active InvoiceCommitment.
    """
    from app.services.commitments_service import create_invoice_commitment

    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice {invoice_id} not found."}

    deadline = ist_naive_now() + timedelta(days=days)
    comm = create_invoice_commitment(
        db=db,
        invoice_id=inv.invoice_id,
        customer_id=inv.customer_id,
        commitment_type="GRACE_PERIOD_PAUSE",
        description=f"Payment Grace Period of {days} days granted ({reason})",
        parameters={"days": days, "reason": reason, "paused_until": deadline.isoformat()},
        days_valid=days,
    )

    inv.next_action_at = deadline
    db.commit()

    # Dispatch notification email
    subject = f"Notice: Payment Extension Granted - Invoice {inv.invoice_number}"
    body = (
        f"Dear {inv.customer.name},\n\n"
        f"We have registered your request regarding invoice {inv.invoice_number}.\n\n"
        f"A payment grace period of {days} days has been officially authorized. "
        f"All automated collection notices for your account have been frozen until {deadline.strftime('%d %B %Y')}.\n\n"
        f"Agreement Reference: {comm.commitment_id}\n\n"
        f"Warm regards,\nAccounts Receivable Team\nReceivIQ"
    )
    EmailService.send_customer_email(
        db=db,
        customer_id=inv.customer_id,
        invoice_id=inv.invoice_id,
        subject=subject,
        message=body,
        comm_type="GRACE_PERIOD_NOTICE",
        direction="OUTGOING",
    )

    return {
        "status": "SUCCESS",
        "commitment_id": comm.commitment_id,
        "invoice_number": inv.invoice_number,
        "days_granted": days,
        "frozen_until": deadline.isoformat(),
        "message": f"Extension of {days} days recorded. Reminders paused until {deadline.strftime('%d %B %Y')}.",
    }


def tool_revoke_commitment(
    db: Session,
    invoice_id: Optional[str] = None,
    commitment_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Revokes an active agreement (e.g. cancels a discount offer or terminates an extension).
    Marks the database record REVOKED, restores invoice parameters, and notifies debtors.
    """
    query = db.query(InvoiceCommitment).filter(InvoiceCommitment.status == "ACTIVE")
    if invoice_id:
        query = query.filter(InvoiceCommitment.invoice_id == invoice_id)
    if commitment_type:
        query = query.filter(InvoiceCommitment.commitment_type == commitment_type)

    active_commitments = query.all()
    if not active_commitments:
        return {
            "status": "NO_ACTIVE_COMMITMENTS",
            "message": "No active commercial agreements or discounts match your criteria to revoke.",
        }

    now = ist_naive_now()
    revoked_count = 0

    for comm in active_commitments:
        comm.status = "REVOKED"
        comm.revoked_at = now

        # Restore invoice
        inv = db.query(Invoice).filter(Invoice.invoice_id == comm.invoice_id).first()
        if inv:
            inv.next_action_at = None
            # Dispatch revocation notification
            subject = f"Notice: Agreement Revocation - Invoice {inv.invoice_number}"
            body = (
                f"Dear {inv.customer.name},\n\n"
                f"Please be advised that the prior arrangement ({comm.description}) for invoice {inv.invoice_number} "
                f"has been officially revoked by Accounts Receivable Management.\n\n"
                f"Outstanding balance of ₹{inv.total_amount:,.2f} is now due as per original contractual terms.\n\n"
                f"Warm regards,\nAccounts Receivable Team\nReceivIQ"
            )
            EmailService.send_customer_email(
                db=db,
                customer_id=inv.customer_id,
                invoice_id=inv.invoice_id,
                subject=subject,
                message=body,
                comm_type="AGREEMENT_REVOCATION",
                direction="OUTGOING",
            )
        revoked_count += 1

    db.commit()
    return {
        "status": "SUCCESS",
        "revoked_count": revoked_count,
        "message": f"Successfully revoked {revoked_count} active agreements and restored contractual terms.",
    }
