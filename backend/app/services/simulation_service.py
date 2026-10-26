"""
Customer Reply Interpretation and Simulation Engine.

Classifies incoming customer messages into standard Accounts Receivable intents
(PAYMENT_PROMISED, PAYMENT_COMPLETED, INVOICE_DISPUTE, EXTENSION_REQUEST, GENERAL_QUERY)
and triggers downstream database state changes and follow-ups.
"""

from datetime import datetime, date, timedelta
import re
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.core.timezone import ist_today, ist_naive_now

from app.db.models import Invoice, Customer, Followup, Communication, Approval
from app.services.email_service import EmailService
from app.services.tools import log_agent_action


def classify_customer_intent(message_text: str) -> Dict[str, Any]:
    """
    Classifies semantic intent from inbound customer emails.
    
    Args:
        message_text: The incoming email text.
        
    Returns:
        Dict[str, Any]: Extracted intent, confidence score, and extracted entities.
    """
    text_lower = message_text.lower()

    # Dispute Intent Detection
    if any(k in text_lower for k in ["dispute", "incorrect", "wrong amount", "purchase order", "po was for", "overcharge", "disagree"]):
        # Extract claimed amount if present
        amount_match = re.search(r"₹?\s*([\d,]+)", message_text)
        claimed = amount_match.group(1).replace(",", "") if amount_match else None
        return {
            "intent": "INVOICE_DISPUTE",
            "confidence": 0.95,
            "requires_escalation": True,
            "claimed_amount": float(claimed) if claimed and claimed.isdigit() else None,
            "reason": message_text,
        }

    # Payment Promised Intent
    if any(k in text_lower for k in ["process", "will pay", "pay next", "friday", "monday", "tomorrow", "next week", "arrange payment"]):
        return {
            "intent": "PAYMENT_PROMISED",
            "confidence": 0.92,
            "requires_escalation": False,
            "promised_date": (date.today() + timedelta(days=7)).isoformat(),
        }

    # Already Paid Intent
    if any(k in text_lower for k in ["already paid", "payment made", "settled yesterday", "remitted", "transferred"]):
        ref_match = re.search(r"(ref|utr|neft|rtgs)[\s/:]*([a-zA-Z0-9]+)", text_lower)
        return {
            "intent": "PAYMENT_COMPLETED",
            "confidence": 0.90,
            "requires_escalation": False,
            "reference_number": ref_match.group(2).upper() if ref_match else "UNSPECIFIED",
        }

    # General extension request
    if any(k in text_lower for k in ["extension", "more time", "cash flow", "financial difficulty", "delay"]):
        return {
            "intent": "EXTENSION_REQUEST",
            "confidence": 0.88,
            "requires_escalation": False,
            "requested_days": 14,
        }

    return {
        "intent": "GENERAL_QUERY",
        "confidence": 0.75,
        "requires_escalation": False,
    }


def process_incoming_customer_reply(
    db: Session, invoice_id: str, reply_text: str, session_id: str = "session-sim"
) -> Dict[str, Any]:
    """
    Simulates receiving an inbound email from a customer regarding an invoice.
    Routes strictly through centralized AI Reply Processor with Amazon Nova Pro,
    generating contextual immediate acknowledgment and human approvals where appropriate.
    """
    clean_id = invoice_id.strip()
    inv = db.query(Invoice).filter((Invoice.invoice_id == clean_id) | (Invoice.invoice_number.ilike(clean_id))).first()
    if not inv:
        return {"error": f"Invoice '{invoice_id}' not found."}

    cust = inv.customer
    if not cust:
        return {"error": f"Customer associated with invoice '{invoice_id}' not found."}

    import uuid
    from app.core.config import settings
    from app.services.ai_reply_processor import process_inbound_customer_email

    sim_msg_id = f"SIM-{uuid.uuid4().hex[:10].upper()}@simulator.fintech"
    res = process_inbound_customer_email(
        db=db,
        sender_email=cust.email,
        subject=f"Re: Payment Notice: Invoice {inv.invoice_number}",
        raw_body=reply_text,
        message_id=sim_msg_id,
        recipient_email=settings.reply_to_email or "ashishgokani58@gmail.com",
    )

    db.refresh(inv)

    return {
        "invoice_id": inv.invoice_id,
        "invoice_number": inv.invoice_number,
        "customer": cust.company_name,
        "intent": res.get("intent"),
        "confidence": res.get("confidence", 0.0),
        "new_invoice_status": inv.status,
        "action_taken": res.get("concise_rationale"),
        "requires_approval": res.get("requires_approval", False),
        "approval_id": res.get("approval_id"),
        "acknowledgment_sent": res.get("acknowledgment_sent", False),
        "message_id": sim_msg_id,
    }

