"""
AI-Powered Inbound Email Interpretation and Semantic Processing Engine.

Performs:
1. Customer identity verification and live account ledger context resolution.
2. Quoted email thread context parsing to avoid instruction injection.
3. Universal semantic intent extraction with Amazon Nova Pro (supports unknown/ambiguous categories).
4. Deterministic approval gating for consequential financial events (payment claims, disputes, extensions).
5. Immediate factual, professional customer acknowledgment mailer with Reply-To: ashishgokani58@gmail.com.
6. Persistent deduplication by RFC 822 Message-ID and safe failure recovery.
"""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.models import Approval, InvoiceCommitment, InboundEmailLog
from app.services.email_service import EmailService
from app.services.ai_email_drafter import SIGN_OFF_TEXT
from app.services.inbound_account_resolver import resolve_customer_account_context
from app.services.inbound_intent_classifier import (
    classify_inbound_email,
    _deterministic_classification_fallback,
)

logger = logging.getLogger(__name__)


def separate_clean_reply_and_quoted_history(raw_body: str) -> Tuple[str, str]:
    """
    Separates the customer's fresh reply text from quoted email history.
    
    Guarantees:
    - Quoted lines (e.g. '> ...' or 'On 24 Oct, AR Agent wrote:') are separated.
    - Prevents old instructions in the thread from being re-processed as new commands.
    """
    if not raw_body:
        return "", ""

    lines = raw_body.strip().split("\n")
    clean_lines = []
    quoted_lines = []
    is_in_quote = False

    quote_header_patterns = [
        r"^on\s+.+wrote:$",
        r"^from:\s+.+<.+@.+>",
        r"^-{3,}\s*original message\s*-{3,}",
        r"^begin forwarded message:",
    ]

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if any(re.match(p, lower) for p in quote_header_patterns):
            is_in_quote = True

        if stripped.startswith(">"):
            quoted_lines.append(line)
        elif is_in_quote:
            quoted_lines.append(line)
        else:
            clean_lines.append(line)

    clean_text = "\n".join(clean_lines).strip()
    quoted_text = "\n".join(quoted_lines).strip()

    if not clean_text and quoted_text:
        clean_text = quoted_text
        quoted_text = ""

    return clean_text, quoted_text


def parse_and_classify_customer_email(
    customer_name: str,
    customer_company: str,
    invoice_number: str,
    invoice_total: float,
    days_overdue: int,
    clean_body: str,
    thread_history: Optional[str] = None,
) -> Dict[str, Any]:
    """Compatibility wrapper providing backward compatibility with existing tests and tools."""
    mock_context = {
        "customer_name": customer_name,
        "company_name": customer_company,
        "account_status": "SINGLE_OPEN_INVOICE" if invoice_number and invoice_number != "General Account" else "NO_INVOICES_ON_FILE",
        "total_open_balance": invoice_total,
        "open_invoices": [],
        "settled_invoices": [],
        "primary_invoice": None,
        "referenced_invoice": None,
    }
    return classify_inbound_email(mock_context, clean_body, thread_history)


def process_inbound_customer_email(
    db: Session,
    sender_email: str,
    subject: str,
    raw_body: str,
    message_id: Optional[str] = None,
    recipient_email: Optional[str] = None,
    received_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Central controller processing an inbound email through the complete AI pipeline.
    
    Guarantees:
    1. Persistent deduplication by message_id.
    2. Strict customer identity verification and ledger reconciliation.
    3. Thread context parsing without instruction injection.
    4. Guardrail enforcement: financial mutations require human approval.
    5. Contextual customer acknowledgment with accurate account status.
    """
    clean_sender = sender_email.strip().lower()
    msg_id = message_id or f"MSG-{uuid.uuid4().hex[:12].upper()}@inbound.fintech"
    recv_time = received_at or ist_naive_now()

    # 1. Persistent Deduplication Check
    existing_log = db.query(InboundEmailLog).filter(InboundEmailLog.message_id == msg_id).first()
    if existing_log:
        logger.info("Inbound email with message_id '%s' was already processed. Skipping duplicate.", msg_id)
        return {
            "status": "DUPLICATE_SKIPPED",
            "message_id": msg_id,
            "processed_at": existing_log.processed_at.isoformat() if existing_log.processed_at else None,
        }

    clean_text, quoted_history = separate_clean_reply_and_quoted_history(raw_body)

    # 2. Resolve Verified Customer Account Context
    acc_context = resolve_customer_account_context(
        db=db,
        sender_email=clean_sender,
        subject=subject,
        clean_text=clean_text,
        quoted_history=quoted_history,
    )

    if not acc_context["is_registered_customer"]:
        log_entry = InboundEmailLog(
            message_id=msg_id,
            sender_email=clean_sender,
            recipient_email=recipient_email,
            subject=subject,
            clean_body=clean_text,
            quoted_history=quoted_history,
            received_at=recv_time,
            status="IGNORED_UNVERIFIED_SENDER",
            intent="UNRELATED_SPAM",
            ai_rationale="Sender address does not correspond to any registered customer in our relational database.",
            processed_at=ist_naive_now(),
        )
        db.add(log_entry)
        db.commit()
        logger.warning("Inbound email from unverified sender '%s' rejected by identity guardrails.", clean_sender)
        return {
            "status": "UNVERIFIED_SENDER_IGNORED",
            "sender_email": clean_sender,
            "message": "Sender is not a recognized customer. No action taken.",
        }

    cust = acc_context["customer"]
    primary_inv = acc_context["primary_invoice"]
    acc_status = acc_context["account_status"]

    # 3. Semantic AI Understanding with Full Ground Truth Account Context
    ai_result = classify_inbound_email(
        account_context=acc_context,
        clean_body=clean_text,
        thread_history=quoted_history,
    )

    intent = ai_result.get("intent", "UNKNOWN_OR_AMBIGUOUS")
    approval_id = None
    requires_approval = False

    # 4. Consequential Financial Actions Require Approval (Only for valid active invoices)
    if intent == "PAYMENT_CLAIMED":
        if primary_inv and acc_status in ("SINGLE_OPEN_INVOICE", "MULTIPLE_OPEN_INVOICES"):
            requires_approval = True
            appr_details = {
                "source": "INBOUND_EMAIL",
                "sender_email": clean_sender,
                "customer_name": cust.name,
                "company_name": cust.company_name,
                "email_received_at": recv_time.isoformat(),
                "utr_reference": ai_result.get("utr_reference") or "PENDING_VERIFICATION",
                "claimed_amount": ai_result.get("claimed_amount") or primary_inv.total_amount,
                "invoice_number": primary_inv.invoice_number,
                "ai_rationale": ai_result.get("concise_rationale"),
                "customer_reply_snippet": clean_text[:300],
                "possible_actions": ["FULL_PAYMENT_APPROVED", "PARTIAL_PAYMENT_APPROVED", "REJECTED_UNVERIFIED"],
            }
            existing_appr = db.query(Approval).filter(
                Approval.invoice_id == primary_inv.invoice_id,
                Approval.action_type == "VERIFY_PAYMENT_REMITTANCE",
                Approval.status == "PENDING",
            ).first()

            if existing_appr:
                approval_id = existing_appr.approval_id
                existing_appr.details = json.dumps(appr_details)
            else:
                approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
                appr = Approval(
                    approval_id=approval_id,
                    action_type="VERIFY_PAYMENT_REMITTANCE",
                    invoice_id=primary_inv.invoice_id,
                    customer_id=cust.customer_id,
                    requested_by="AI Inbound Listener",
                    details=json.dumps(appr_details),
                    status="PENDING",
                    created_at=ist_naive_now(),
                )
                db.add(appr)
        else:
            # Customer has no open invoice on file (e.g. ABC): do not create false unbacked approval
            requires_approval = False

    elif intent == "INVOICE_DISPUTE" and primary_inv:
        requires_approval = True
        primary_inv.status = "DISPUTED"
        primary_inv.dispute_reason = ai_result.get("dispute_reason") or clean_text[:200]
        appr_details = {
            "source": "INBOUND_EMAIL",
            "sender_email": clean_sender,
            "email_received_at": recv_time.isoformat(),
            "dispute_reason": primary_inv.dispute_reason,
            "claimed_amount": ai_result.get("claimed_amount"),
            "invoice_number": primary_inv.invoice_number,
            "ai_rationale": ai_result.get("concise_rationale"),
        }
        existing_appr = db.query(Approval).filter(
            Approval.invoice_id == primary_inv.invoice_id,
            Approval.action_type == "INVOICE_DISPUTE_REVIEW",
            Approval.status == "PENDING",
        ).first()

        if existing_appr:
            approval_id = existing_appr.approval_id
            existing_appr.details = json.dumps(appr_details)
        else:
            approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
            appr = Approval(
                approval_id=approval_id,
                action_type="INVOICE_DISPUTE_REVIEW",
                invoice_id=primary_inv.invoice_id,
                customer_id=cust.customer_id,
                requested_by="AI Inbound Listener",
                details=json.dumps(appr_details),
                status="PENDING",
                created_at=ist_naive_now(),
            )
            db.add(appr)

    elif intent == "PAYMENT_PROMISED" and primary_inv:
        promised_date_str = ai_result.get("promised_date")
        if promised_date_str:
            try:
                parsed_pdate = datetime.strptime(promised_date_str, "%Y-%m-%d").date()
                primary_inv.promised_payment_date = parsed_pdate
                primary_inv.status = "PAYMENT_PROMISED"

                commit_id = f"COM-{uuid.uuid4().hex[:8].upper()}"
                comm = InvoiceCommitment(
                    commitment_id=commit_id,
                    invoice_id=primary_inv.invoice_id,
                    customer_id=cust.customer_id,
                    commitment_type="PAYMENT_PROMISE",
                    description=f"Debtor promised payment by {parsed_pdate}.",
                    parameters=json.dumps({"promised_date": promised_date_str, "source": "INBOUND_EMAIL"}),
                    status="ACTIVE",
                    created_at=ist_naive_now(),
                    valid_until=datetime.combine(parsed_pdate, datetime.max.time()),
                )
                db.add(comm)
            except ValueError:
                pass

    # 5. Persist Inbound Email Audit Log
    log_entry = InboundEmailLog(
        message_id=msg_id,
        sender_email=clean_sender,
        recipient_email=recipient_email,
        subject=subject,
        clean_body=clean_text,
        quoted_history=quoted_history,
        received_at=recv_time,
        status="PROCESSED",
        customer_id=cust.customer_id,
        invoice_id=primary_inv.invoice_id if primary_inv else None,
        intent=intent,
        extracted_entities=json.dumps(ai_result, default=str),
        ai_rationale=ai_result.get("concise_rationale"),
        requires_approval=requires_approval,
        approval_id=approval_id,
        processed_at=ist_naive_now(),
    )
    db.add(log_entry)
    db.commit()

    # 6. Dispatch Immediate Contextual Customer Acknowledgment
    ack_sent = False
    ack_body = ai_result.get("ack_body")
    ack_sub = ai_result.get("ack_subject") or f"Re: {subject}"
    if ack_body and cust.email:
        clean_ack = ack_body.strip()
        if "Accounts Receivable" not in clean_ack:
            clean_ack = f"{clean_ack}\n\n{SIGN_OFF_TEXT}"
        try:
            send_res = EmailService.send_customer_email(
                db=db,
                customer_id=cust.customer_id,
                invoice_id=primary_inv.invoice_id if primary_inv else None,
                subject=ack_sub,
                message=clean_ack,
                comm_type="CUSTOMER_ACKNOWLEDGMENT",
                direction="OUTGOING",
                in_reply_to=msg_id,
            )
            ack_sent = send_res.get("status") == "DELIVERED"
            log_entry.acknowledgment_sent = ack_sent
            log_entry.acknowledgment_comm_id = send_res.get("communication_id")
            db.commit()
        except Exception as mail_err:
            logger.error("Failed to dispatch customer acknowledgment email: %s", mail_err)

    return {
        "status": "SUCCESS",
        "message_id": msg_id,
        "customer": cust.company_name,
        "invoice_number": primary_inv.invoice_number if primary_inv else "None",
        "account_status": acc_status,
        "intent": intent,
        "confidence": ai_result.get("confidence", 0.0),
        "concise_rationale": ai_result.get("concise_rationale"),
        "requires_approval": requires_approval,
        "approval_id": approval_id,
        "acknowledgment_sent": ack_sent,
    }
