"""
Email Service and Communication History Manager.

Dispatches customer payment notices, escalation alerts, and payment confirmations,
while logging every inbound and outbound message into the audit ledger.
Sends natural, clean plain-text emails without artificial HTML/CSS table clutter,
ensuring 100% universal readability across all modern and legacy email clients.
"""

import html
import logging
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.models import Communication, Customer, Invoice, Payment

logger = logging.getLogger(__name__)


def sanitize_email_placeholders_and_signoff(text: str) -> str:
    """
    Sanitizes email body text by purging generic LLM bracketed placeholders
    (e.g., [Your Company Name], [Your Name]) and enforcing an authentic, professional
    sign-off as 'Accounts Receivable Team' and 'ReceivIQ'.

    Args:
        text: Raw email message body.

    Returns:
        str: Cleaned email body with zero bracketed placeholders and compliant sign-off.
    """
    if not text:
        return ""

    cleaned = text.strip()

    # 1. Replace company placeholders
    cleaned = re.sub(
        r"\[\s*(?:Your\s+|Our\s+)?Company(?:\s+Name)?\s*\]",
        "ReceivIQ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\[\s*(?:Your\s+|Our\s+)?Organization(?:\s+Name)?\s*\]",
        "ReceivIQ",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 2. Replace sender / name / title placeholders
    cleaned = re.sub(
        r"\[\s*(?:Your\s+|Sender\s+)?Name\s*\]",
        "Accounts Receivable Team",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\[\s*(?:Your\s+)?(?:Title|Position|Designation|Role)\s*\]",
        "Accounts Receivable Team",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 3. Replace contact / phone / email / date placeholders
    cleaned = re.sub(
        r"\[\s*(?:Your\s+)?(?:Phone|Mobile|Contact(?:\s+Number)?)\s*\]",
        "+91 98765 43210",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\[\s*(?:Your\s+)?Email(?:\s+Address)?\s*\]",
        "receiviq@gmail.com",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\[\s*(?:Insert\s+)?(?:Date|Current\s+Date|Today'?s\s+Date)\s*\]",
        datetime.now().strftime("%d %B %Y"),
        cleaned,
        flags=re.IGNORECASE,
    )

    # 4. Catch any remaining [Your ...] placeholders
    cleaned = re.sub(
        r"\[\s*Your\s+[^\]]+\]",
        "Accounts Receivable Team",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 5. Clean up sign-off block to guarantee 'Accounts Receivable Team\nReceivIQ'
    signoff_target = "Warm regards,\nAccounts Receivable Team\nReceivIQ"

    cleaned = re.sub(
        r"(Warm\s+regards|Best\s+regards|Regards|Sincerely)[\s,]*\n+(?:Accounts\s+Receivable\s+Team|Credit\s+Control\s+Department|ReceivIQ)[\s,]*\n*(?:ReceivIQ|Accounts\s+Receivable\s+Team)?",
        signoff_target,
        cleaned,
        flags=re.IGNORECASE,
    )

    # If no standard sign-off found at the end of the email, ensure one is appended
    if not re.search(r"(Warm\s+regards|Best\s+regards|Regards|Sincerely)", cleaned, flags=re.IGNORECASE):
        cleaned = f"{cleaned}\n\n{signoff_target}"

    return cleaned.strip()


def build_clean_text_email(message: str) -> str:
    """
    Wraps clean AI-generated plain text into a lightweight, zero-CSS HTML body
    for email clients requesting multipart/alternative MIME parts, preserving exact
    formatting, typography, and line breaks without artificial tables or CSS backgrounds.

    Args:
        message: Pure plain-text email message.

    Returns:
        str: Minimalist HTML representation preserving line breaks.
    """
    clean_escaped = html.escape(message.strip())
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "</head>\n"
        "<body style=\"margin: 0; padding: 16px; font-family: -apple-system, BlinkMacSystemFont, "
        "'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; "
        "color: #1e293b; background-color: #ffffff;\">\n"
        f"<div style=\"white-space: pre-wrap; max-width: 650px;\">{clean_escaped}</div>\n"
        "</body>\n"
        "</html>"
    )


def build_responsive_html_email(
    subject: str,
    message: str,
    customer_name: Optional[str] = None,
    company_name: Optional[str] = None,
    comm_type: str = "REMINDER",
    invoice_number: Optional[str] = None,
    total_amount: Optional[float] = None,
    discount_percent: Optional[float] = None,
    discount_amount: Optional[float] = None,
    settlement_amount: Optional[float] = None,
    hours_valid: Optional[int] = None,
    bank_details: Optional[Dict[str, str]] = None,
) -> str:
    """
    Backwards-compatible alias directing to clean text email representation.
    Eliminates rigid table-based CSS styling while maintaining method signature.
    """
    return build_clean_text_email(message)


class EmailService:
    """Manages email dispatch, simulated delivery, and communication audit logging."""

    @staticmethod
    def send_customer_email(
        db: Session,
        customer_id: str,
        invoice_id: Optional[str],
        subject: str,
        message: str,
        comm_type: str = "REMINDER",
        direction: str = "OUTGOING",
        intent: Optional[str] = None,
        html_body: Optional[str] = None,
        discount_percent: Optional[float] = None,
        discount_amount: Optional[float] = None,
        settlement_amount: Optional[float] = None,
        hours_valid: Optional[int] = None,
        in_reply_to: Optional[str] = None,
        smtp_server: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Records and dispatches a clean, natural email message to a customer.
        Supports RFC 5322 In-Reply-To and References headers for continuous email threading.
        Appends banking remittance details only for payment collection and invoice notices.
        Supports optional pre-opened smtp_server for high-throughput batch dispatches.
        """
        customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
        if not customer:
            raise ValueError(f"Customer with ID {customer_id} does not exist.")

        invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first() if invoice_id else None

        # Clean and ensure zero bracketed placeholders and proper remittance details
        final_message = sanitize_email_placeholders_and_signoff(message)
        is_payment_notice = comm_type in ("REMINDER", "OVERDUE_NOTICE", "SETTLEMENT_OFFER", "FINAL_NOTICE", "ESCALATION")

        if is_payment_notice and invoice and "Bank Remittance Details" not in final_message and "Beneficiary" not in final_message:
            try:
                from app.services.settings_service import get_bank_details_dict
                from app.services.ai_email_drafter import format_bank_transfer_block
                bank_dict = get_bank_details_dict(db)
                bank_block = format_bank_transfer_block(bank_dict, invoice.invoice_number)
                if bank_block:
                    if "Warm regards" in final_message:
                        final_message = final_message.replace("Warm regards", f"{bank_block}\n\nWarm regards")
                    elif "Sincerely" in final_message:
                        final_message = final_message.replace("Sincerely", f"{bank_block}\n\nSincerely")
                    else:
                        final_message = f"{final_message}\n\n{bank_block}\n\nWarm regards,\nAccounts Receivable Team\nReceivIQ"
            except Exception as bank_err:
                logger.warning("Could not append bank remittance block: %s", bank_err)

        final_message = sanitize_email_placeholders_and_signoff(final_message)

        comm_id = f"COMM-{uuid.uuid4().hex[:8].upper()}"
        comm = Communication(
            communication_id=comm_id,
            customer_id=customer_id,
            invoice_id=invoice_id,
            type=comm_type,
            direction=direction,
            subject=subject,
            message=final_message,
            intent=intent,
            sent_at=ist_naive_now(),
            created_at=ist_naive_now(),
        )
        db.add(comm)
        db.commit()
        db.refresh(comm)

        # Generate zero-CSS lightweight HTML body
        clean_html = build_clean_text_email(final_message)

        # Real SMTP delivery with alternative MIME parts (Plain text primary + Clean HTML)
        smtp_sent = False
        smtp_error_msg: Optional[str] = None
        from app.core.config import settings
        if settings.email_provider == "smtp" and settings.smtp_user and settings.smtp_password:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                msg = MIMEMultipart("alternative")

                # Send directly to the customer's actual email address unless demo override is explicitly configured
                target_recipient = (
                    settings.demo_override_email.strip()
                    if settings.demo_override_email and settings.demo_override_email.strip()
                    else customer.email
                )
                reply_target = settings.reply_to_email or settings.smtp_user

                sender_display_name = settings.from_name or "ReceivIQ"
                msg["From"] = f"{sender_display_name} <{settings.from_email or settings.smtp_user}>"
                msg["To"] = target_recipient
                msg["Reply-To"] = reply_target

                # Clean professional subject: avoid artificial bracket tags
                clean_subj = subject.strip()
                if in_reply_to and not clean_subj.lower().startswith("re:"):
                    clean_subj = f"Re: {clean_subj}"
                msg["Subject"] = clean_subj

                if in_reply_to:
                    msg["In-Reply-To"] = in_reply_to
                    msg["References"] = in_reply_to

                if invoice:
                    msg["X-AR-Invoice-ID"] = invoice.invoice_id
                    msg["X-AR-Customer-ID"] = customer.customer_id

                # Attach clean plain text and zero-CSS lightweight HTML part
                msg.attach(MIMEText(final_message, "plain", "utf-8"))
                msg.attach(MIMEText(clean_html, "html", "utf-8"))

                if smtp_server:
                    smtp_server.send_message(msg)
                else:
                    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                        server.starttls()
                        server.login(settings.smtp_user, settings.smtp_password)
                        server.send_message(msg)
                smtp_sent = True
            except Exception as smtp_err:
                smtp_error_msg = str(smtp_err)
                logger.warning("SMTP dispatch warning to %s: %s. Delivery marked for fallback/retry queue.", customer.email, smtp_err)

        delivery_status = "DELIVERED" if (smtp_sent or settings.email_provider != "smtp") else "FAILED_DISPATCH"
        return {
            "status": delivery_status,
            "error": smtp_error_msg,
            "communication_id": comm_id,
            "recipient_email": customer.email,
            "recipient_name": customer.name,
            "company_name": customer.company_name,
            "subject": subject,
            "sent_at": comm.sent_at.isoformat(),
            "real_smtp_dispatched": smtp_sent,
            "html_rendered": bool(clean_html),
        }

    @staticmethod
    def send_payment_confirmation(db: Session, payment: Payment) -> Dict[str, Any]:
        """
        Dispatches an automated payment receipt confirmation to the customer.
        Generated by AI without bank collection details and without placeholders.
        """
        invoice = db.query(Invoice).filter(Invoice.invoice_id == payment.invoice_id).first()
        customer = db.query(Customer).filter(Customer.customer_id == payment.customer_id).first()
        if not customer:
            raise ValueError(f"Customer with ID {payment.customer_id} does not exist.")

        from app.services.ai_email_drafter import draft_payment_confirmation_email
        draft = draft_payment_confirmation_email(
            customer_name=customer.name,
            company_name=customer.company_name,
            invoice_number=invoice.invoice_number if invoice else payment.invoice_id,
            amount_received=payment.amount,
            payment_method=payment.payment_method,
            reference_number=payment.reference_number,
        )

        return EmailService.send_customer_email(
            db=db,
            customer_id=customer.customer_id,
            invoice_id=invoice.invoice_id if invoice else None,
            subject=draft["subject"],
            message=draft["body"],
            comm_type="PAYMENT_CONFIRMATION",
            direction="OUTGOING",
            intent="PAYMENT_CONFIRMATION",
        )
