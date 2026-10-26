"""
State-Bound Invoice Commitment and Commercial Directives Service.

Binds custom conversational requests (e.g. early settlement discounts, grace period
pauses, reminder freezes, penalty waivers) directly into PostgreSQL state and ensures
full synchronization with the background automation scheduler.
"""

from datetime import datetime, timedelta
import json
import uuid
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now, ist_now
from app.db.models import Invoice, Customer, InvoiceCommitment
from app.services.penalty_engine import sync_invoice_financials, calculate_days_overdue
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


def create_invoice_commitment(
    db: Session,
    invoice_id: str,
    customer_id: str,
    commitment_type: str,
    description: str,
    parameters: Dict[str, Any],
    hours_valid: Optional[int] = None,
    days_valid: Optional[int] = None,
) -> InvoiceCommitment:
    """
    Persists an official commercial commitment on an invoice.
    
    Args:
        db: Active SQLAlchemy database session.
        invoice_id: Target invoice identifier.
        customer_id: Recipient customer identifier.
        commitment_type: Category (e.g. EARLY_SETTLEMENT_DISCOUNT, GRACE_PERIOD_PAUSE).
        description: Human-readable summary of the commitment.
        parameters: Arbitrary structured parameters stored dynamically as JSON.
        hours_valid: Optional expiration lifetime in hours.
        days_valid: Optional expiration lifetime in days.
        
    Returns:
        InvoiceCommitment: The created database record.
    """
    commitment_id = f"COM-{uuid.uuid4().hex[:8].upper()}"
    valid_until = None
    if hours_valid is not None:
        valid_until = ist_naive_now() + timedelta(hours=hours_valid)
    elif days_valid is not None:
        valid_until = ist_naive_now() + timedelta(days=days_valid)

    commitment = InvoiceCommitment(
        commitment_id=commitment_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        commitment_type=commitment_type,
        description=description,
        parameters=json.dumps(parameters),
        status="ACTIVE",
        created_at=ist_naive_now(),
        valid_until=valid_until,
    )
    db.add(commitment)
    db.commit()
    db.refresh(commitment)
    return commitment


def expire_stale_commitments(db: Session) -> int:
    """
    Scans for expired commitments and marks them EXPIRED.
    When a PAYMENT_PROMISE expires without payment receipt, transitions invoice
    back to OVERDUE and automatically dispatches a polite follow-up notice.
    
    Returns:
        int: Number of commitments expired in this pass.
    """
    now = ist_naive_now()
    stale = (
        db.query(InvoiceCommitment)
        .filter(
            InvoiceCommitment.status == "ACTIVE",
            InvoiceCommitment.valid_until.isnot(None),
            InvoiceCommitment.valid_until < now,
        )
        .all()
    )

    for comm in stale:
        comm.status = "EXPIRED"
        inv = db.query(Invoice).filter(Invoice.invoice_id == comm.invoice_id).first()
        if inv:
            if inv.next_action_at and inv.next_action_at <= now:
                inv.next_action_at = None

            # If a payment promise expired without ledger clearance
            if comm.commitment_type == "PAYMENT_PROMISE" and inv.status == "PAYMENT_PROMISED":
                sync_invoice_financials(inv, db)
                if inv.status != "PAID":
                    inv.status = "OVERDUE"
                    inv.promised_payment_date = None

                    # Dispatch gentle follow-up notice
                    cust = inv.customer
                    if cust and cust.email:
                        p_date_str = comm.valid_until.strftime("%d %B %Y") if comm.valid_until else "earlier this week"
                        followup_sub = f"Follow-up: Payment Status Update - Invoice {inv.invoice_number}"
                        followup_body = (
                            f"Dear {cust.name},\n\n"
                            f"Our records indicate payment for Invoice {inv.invoice_number} (₹{inv.total_amount:,.2f}) "
                            f"was expected around {p_date_str}.\n\n"
                            f"If payment has already been remitted, please disregard this notice and reply with your bank UTR transaction "
                            f"reference number so we can promptly credit your ledger.\n\n"
                            f"If you require any assistance, please let us know.\n\n"
                            f"Warm regards,\nAccounts Receivable Team\nReceivIQ"
                        )
                        try:
                            EmailService.send_customer_email(
                                db=db,
                                customer_id=cust.customer_id,
                                invoice_id=inv.invoice_id,
                                subject=followup_sub,
                                message=followup_body,
                                comm_type="PROMISE_EXPIRED_FOLLOWUP",
                                direction="OUTGOING",
                            )
                        except Exception as mail_err:
                            logger.error("Failed to send promise expiration follow-up email: %s", mail_err)

    if stale:
        db.commit()
        logger.info("Automation cycle expired %d stale invoice commitments.", len(stale))
    return len(stale)



def has_active_hold_or_pause(db: Session, invoice_id: str) -> bool:
    """
    Checks if an invoice has an active grace period, dispute hold, or active discount.
    Used by the scheduler to ensure it never sends conflicting reminders.
    """
    now = ist_naive_now()
    active_comm = (
        db.query(InvoiceCommitment)
        .filter(
            InvoiceCommitment.invoice_id == invoice_id,
            InvoiceCommitment.status == "ACTIVE",
            (InvoiceCommitment.valid_until.is_(None) | (InvoiceCommitment.valid_until > now)),
        )
        .first()
    )
    return active_comm is not None


def tool_apply_settlement_discount(
    db: Session,
    discount_percent: float = 0.1,
    hours_valid: int = 24,
    min_amount: Optional[float] = None,
    custom_message: Optional[str] = None,
    resolution_mode: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Applies an early settlement discount across unsettled invoices matching optional balance threshold.
    Guarantees conflict detection: if target accounts already have active commitments and resolution_mode
    is not set, it pauses execution, registers a PendingAction, and presents options to Revise, Stack, or Cancel.
    """
    unsettled = (
        db.query(Invoice)
        .join(Customer)
        .filter(Invoice.status.in_(["PENDING", "OVERDUE"]))
        .all()
    )

    if not unsettled:
        return {
            "status": "NO_UNSETTLED_ACCOUNTS",
            "message": "There are currently no customers with unsettled or overdue invoices.",
            "total_sent": 0,
            "dispatches": [],
        }

    # 1. Identify qualifying accounts matching threshold
    qualifying = []
    for inv in unsettled:
        sync_invoice_financials(inv, db)
        if min_amount is not None and inv.total_amount < float(min_amount):
            continue
        qualifying.append(inv)

    if not qualifying:
        threshold_text = f" with balance >= ₹{min_amount:,.2f}" if min_amount else ""
        return {
            "status": "NO_MATCHING_ACCOUNTS",
            "message": f"No unsettled accounts found{threshold_text}.",
            "total_sent": 0,
            "dispatches": [],
        }

    # 2. Check for active commitment conflicts across qualifying accounts
    now = ist_naive_now()
    active_conflicts = []
    for inv in qualifying:
        existing_active = (
            db.query(InvoiceCommitment)
            .filter(
                InvoiceCommitment.invoice_id == inv.invoice_id,
                InvoiceCommitment.commitment_type == "EARLY_SETTLEMENT_DISCOUNT",
                InvoiceCommitment.status == "ACTIVE",
                (InvoiceCommitment.valid_until.is_(None) | (InvoiceCommitment.valid_until > now)),
            )
            .all()
        )
        for ea in existing_active:
            try:
                ea_params = json.loads(ea.parameters) if ea.parameters else {}
            except Exception:
                ea_params = {}
            active_conflicts.append({
                "commitment_id": ea.commitment_id,
                "invoice_id": inv.invoice_id,
                "invoice_number": inv.invoice_number,
                "customer": inv.customer.company_name if inv.customer else "Unknown",
                "customer_email": inv.customer.email if inv.customer else "",
                "existing_discount_percent": float(ea_params.get("discount_percent", 0.0)),
                "existing_discount_amount": float(ea_params.get("discount_amount", 0.0)),
                "total_amount": inv.total_amount,
                "valid_until": ea.valid_until.strftime("%d %b %Y, %I:%M %p") if ea.valid_until else "24 Hours",
            })

    # 3. CONFLICT GATE: If active commitments exist and user has not confirmed resolution mode
    if active_conflicts and resolution_mode is None:
        if session_id:
            from app.services.action_state_machine import create_pending_action
            create_pending_action(
                db=db,
                session_id=session_id,
                tool_name="send_bulk_settlement_offer",
                description=f"Resolve commitment conflict for {discount_percent}% settlement offer on {len(active_conflicts)} accounts",
                parameters={"discount_percent": discount_percent, "hours_valid": hours_valid, "min_amount": min_amount, "custom_message": custom_message, "target_invoices": [c["invoice_id"] for c in active_conflicts], "existing_conflicts": active_conflicts},
                target_invoices=[c["invoice_id"] for c in active_conflicts],
                expires_in_minutes=15,
            )

        return {
            "status": "CONFLICT_ACTIVE_COMMITMENTS_DETECTED",
            "requires_user_decision": True,
            "requested_discount_percent": discount_percent,
            "min_amount": min_amount,
            "hours_valid": hours_valid,
            "active_conflicts": active_conflicts,
            "options": [
                f"1. Revise & Upgrade: Supersede earlier concession with {discount_percent}% (customer email references revision).",
                f"2. Stack Concession: Add {discount_percent}% on top of existing concession.",
                f"3. Cancel: Keep existing agreements active (zero emails sent).",
            ],
            "summary": f"Found {len(active_conflicts)} accounts with existing active settlement agreements. Awaiting decision.",
        }

    # 4. Execute Settlement Dispatches (Clean run or confirmed resolution mode)
    deadline = now + timedelta(hours=hours_valid)
    dispatches = []
    effective_pct = discount_percent

    # Pre-open pooled SMTP connection to deliver all customer notices in seconds without connection churn
    smtp_session = None
    from app.core.config import settings
    if settings.email_provider == "smtp" and settings.smtp_user and settings.smtp_password:
        try:
            import smtplib
            smtp_session = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            smtp_session.starttls()
            smtp_session.login(settings.smtp_user, settings.smtp_password)
        except Exception as smtp_conn_err:
            logger.warning("Could not pre-open shared SMTP session for bulk discount: %s", smtp_conn_err)
            smtp_session = None

    try:
        for inv in qualifying:
            # Check existing active commitments for this invoice
            existing_active = (
                db.query(InvoiceCommitment)
                .filter(
                    InvoiceCommitment.invoice_id == inv.invoice_id,
                    InvoiceCommitment.commitment_type == "EARLY_SETTLEMENT_DISCOUNT",
                    InvoiceCommitment.status == "ACTIVE",
                )
                .all()
            )

            prior_pct = 0.0
            for ea in existing_active:
                try:
                    ea_params = json.loads(ea.parameters) if ea.parameters else {}
                    prior_pct = max(prior_pct, float(ea_params.get("discount_percent", 0.0)))
                except Exception:
                    pass

            if resolution_mode == "STACK" and prior_pct > 0:
                effective_pct = round(prior_pct + discount_percent, 2)
            else:
                effective_pct = discount_percent

            # Mark all prior active commitments as SUPERSEDED
            for ea in existing_active:
                ea.status = "SUPERSEDED"

            discount_amount = round(inv.total_amount * (effective_pct / 100.0), 2)
            settlement_amount = round(inv.total_amount - discount_amount, 2)

            if resolution_mode == "STACK":
                comm_desc = f"{effective_pct}% Stacked Settlement Offer ({prior_pct}% + {discount_percent}%)"
            elif prior_pct > 0 and effective_pct < prior_pct:
                comm_desc = f"{effective_pct}% Revised Settlement Offer (Adjusted from {prior_pct}%)"
            elif prior_pct > 0:
                comm_desc = f"{effective_pct}% Revised Settlement Offer (Upgraded from {prior_pct}%)"
            else:
                comm_desc = f"{effective_pct}% Early Settlement Offer (Valid {hours_valid}h)"

            comm = create_invoice_commitment(
                db=db,
                invoice_id=inv.invoice_id,
                customer_id=inv.customer_id,
                commitment_type="EARLY_SETTLEMENT_DISCOUNT",
                description=comm_desc,
                parameters={
                    "discount_percent": effective_pct,
                    "base_discount_percent": discount_percent,
                    "prior_discount_percent": prior_pct,
                    "discount_amount": discount_amount,
                    "net_settlement_amount": settlement_amount,
                    "hours_valid": hours_valid,
                    "min_amount_threshold": min_amount,
                    "resolution_mode": resolution_mode or "INITIAL",
                },
                hours_valid=hours_valid,
            )

            comm_id = comm.commitment_id
            customer_company = inv.customer.company_name if inv.customer else "Valued Client"
            customer_person = inv.customer.name if inv.customer else "Client"
            customer_email = inv.customer.email if inv.customer else ""

            inv.next_action_at = deadline

            # AI-Powered Contextual Email Synthesis
            from app.services.ai_email_drafter import draft_settlement_email_with_ai
            email_draft = draft_settlement_email_with_ai(
                customer_person=customer_person,
                customer_company=customer_company,
                invoice_number=inv.invoice_number,
                original_amount=inv.total_amount,
                effective_pct=effective_pct,
                discount_amount=discount_amount,
                settlement_amount=settlement_amount,
                hours_valid=hours_valid,
                commitment_id=comm_id,
                prior_pct=prior_pct,
                resolution_mode=resolution_mode,
                custom_instructions=custom_message,
            )
            subject = email_draft["subject"]
            body = email_draft["body"]

            send_res = EmailService.send_customer_email(
                db=db,
                customer_id=inv.customer_id,
                invoice_id=inv.invoice_id,
                subject=subject,
                message=body,
                comm_type="SETTLEMENT_OFFER",
                direction="OUTGOING",
                discount_percent=effective_pct,
                discount_amount=discount_amount,
                settlement_amount=settlement_amount,
                hours_valid=hours_valid,
                smtp_server=smtp_session,
            )

            dispatches.append({
                "commitment_id": comm_id,
                "customer": customer_company,
                "invoice_number": inv.invoice_number,
                "original_amount": inv.total_amount,
                "discount_amount": discount_amount,
                "settlement_amount": settlement_amount,
                "recipient": customer_email,
                "delivery_status": send_res.get("status", "SENT"),
            })
    finally:
        if smtp_session:
            try:
                smtp_session.quit()
            except Exception:
                pass

    db.commit()

    threshold_text = f" with balance >= ₹{min_amount:,.2f}" if min_amount else ""
    action_label = "revised" if resolution_mode == "REVISE" else ("stacked" if resolution_mode == "STACK" else "registered")
    return {
        "status": "SUCCESS",
        "total_sent": len(dispatches),
        "discount_percent": effective_pct,
        "hours_valid": hours_valid,
        "min_amount": min_amount,
        "dispatches": dispatches,
        "summary": (
            f"Successfully {action_label} and dispatched {effective_pct}% settlement agreements to "
            f"{len(dispatches)} accounts{threshold_text}. Tracked in database with {hours_valid}-hour automated expiry."
        ),
    }


# Re-export grace period and revocation tools from dedicated modular service
from app.services.grace_period_tools import tool_grant_grace_period, tool_revoke_commitment
