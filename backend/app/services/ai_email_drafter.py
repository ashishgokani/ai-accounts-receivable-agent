"""
AI-Powered Email Drafting Engine.

Synthesizes context-aware, professionally tailored B2B customer emails
using AWS Bedrock Nova Pro / Claude, with an intelligent fail-closed deterministic fallback.
Dynamically crafts payment reminders, early settlement offers, concessions,
and payment confirmations as clean, natural plain text without artificial HTML/CSS clutter.
Guarantees authentic greetings, structured remittance details, and zero placeholders.
"""

import json
import logging
import re
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.currency import format_inr

logger = logging.getLogger(__name__)

SIGN_OFF_TEXT = "Warm regards,\nAccounts Receivable Team"


def resolve_salutation(customer_name: Optional[str], company_name: Optional[str]) -> str:
    """
    Constructs an authentic professional salutation without generic placeholders.

    Args:
        customer_name: Contact person's name if known.
        company_name: Organization or corporate client name.

    Returns:
        str: Clean salutation header (e.g. 'Dear John Doe,' or 'Dear Acme Corp Accounts Team,').
    """
    clean_name = (customer_name or "").strip()
    clean_comp = (company_name or "").strip()

    # Discard placeholder-like or generic customer names
    generic_names = {"valued client", "valued customer", "customer", "client", "unknown", "n/a", "none"}
    if clean_name and clean_name.lower() not in generic_names and not clean_name.startswith("["):
        return f"Dear {clean_name},"
    elif clean_comp and clean_comp.lower() not in generic_names and not clean_comp.startswith("["):
        return f"Dear {clean_comp} Accounts Team,"
    return "Hello Customer,"


def format_bank_transfer_block(bank_details: Optional[Dict[str, str]], invoice_number: Optional[str] = None) -> str:
    """
    Formats banking and remittance details as clean, readable text bullet points.

    Args:
        bank_details: Dictionary containing bank configuration fields.
        invoice_number: Optional invoice identifier for the remittance reference line.

    Returns:
        str: Formatted plain text bank remittance block.
    """
    if not bank_details:
        return ""

    ref_line = (
        f"Please quote Invoice {invoice_number} or your bank UTR upon payment."
        if invoice_number
        else bank_details.get("payment_instructions", "Please share UTR reference upon remittance.")
    )

    lines = [
        "Bank Remittance Details (NEFT / RTGS / IMPS):",
        f"• Beneficiary Name: {bank_details.get('beneficiary_name', 'Accounts Receivable Management')}",
        f"• Bank Name: {bank_details.get('bank_name', 'Corporate Banking')}",
        f"• Account Number: {bank_details.get('account_number', '')}",
        f"• IFSC Code: {bank_details.get('ifsc_code', '')}",
        f"• Payment Reference: {ref_line}",
    ]
    return "\n".join(lines)


def draft_reminder_email_with_ai(
    db: Session,
    invoice_id: str,
    reminder_level: int = 1,
    tone: str = "polite",
    custom_instructions: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Drafts a context-aware payment reminder email tailored by AI with live database figures.

    Args:
        db: Active SQLAlchemy database session.
        invoice_id: Unique identifier of the invoice.
        reminder_level: 1 (courtesy), 2 (second notice with late fees), 3 (urgent final notice).
        tone: Desired communication tone ('polite', 'firm', 'urgent').
        custom_instructions: Optional directives from management.

    Returns:
        Dict[str, Any]: Dictionary containing invoice_id, recipient, subject, and clean body text.
    """
    from app.db.models import Invoice
    from app.services.penalty_engine import calculate_days_overdue, sync_invoice_financials
    from app.services.settings_service import get_bank_details_dict

    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        return {"error": f"Invoice {invoice_id} not found."}

    sync_invoice_financials(inv, db)
    days = calculate_days_overdue(inv.due_date)
    cust = inv.customer
    bank_info = get_bank_details_dict(db)

    cust_name = cust.name if cust else "Valued Client"
    comp_name = cust.company_name if cust else "Corporate Debtor"
    salutation = resolve_salutation(cust_name, comp_name)
    bank_block = format_bank_transfer_block(bank_info, inv.invoice_number)

    # 1. Attempt AI Generation via Amazon Nova Pro / Bedrock
    if not settings.use_mock_bedrock_fallback:
        try:
            from app.services.bedrock_service import BedrockGateway
            gateway = BedrockGateway()
            if gateway.client:
                system_prompt = (
                    "You are an executive accounts receivable communications specialist for an enterprise corporation. "
                    "Draft a natural, authentic, and legally accurate B2B customer email. "
                    "Output strictly valid JSON with keys 'subject' and 'body'. "
                    "CRITICAL RULES: Output pure plain text ONLY. Absolutely NO HTML tags, NO CSS, NO markdown headings (#), "
                    "and NO bracketed placeholders like [Name] or [Date]. "
                    f"Start the body with '{salutation}' and conclude with '{SIGN_OFF_TEXT}'."
                )

                user_prompt = (
                    f"Draft a level {reminder_level} payment notice for the following debtor:\n\n"
                    f"CUSTOMER INFORMATION:\n"
                    f"• Contact Person: {cust_name}\n"
                    f"• Company Name: {comp_name}\n\n"
                    f"INVOICE & FINANCIAL DETAILS:\n"
                    f"• Invoice Number: {inv.invoice_number}\n"
                    f"• Original Due Date: {inv.due_date.strftime('%d %B %Y')}\n"
                    f"• Days Overdue: {days} days\n"
                    f"• Original Principal: {format_inr(inv.amount)}\n"
                    f"• Accrued Late Fee / Interest: {format_inr(inv.penalty_amount)}\n"
                    f"• Total Balance Outstanding: {format_inr(inv.total_amount)}\n"
                    f"• Reminder Level: {reminder_level} (Tone: {tone})\n"
                    f"• Manager Directive: {custom_instructions or 'None'}\n\n"
                    f"REQUIRED REMITTANCE INSTRUCTIONS:\n"
                    f"{bank_block}\n\n"
                    f"Draft the email body integrating the financial facts and remittance details seamlessly."
                )

                ai_res = gateway.converse(
                    messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                    system_prompt=system_prompt,
                )
                raw_text = ai_res.get("text", "")
                json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if "subject" in parsed and "body" in parsed:
                        clean_body = parsed["body"].strip()
                        # Ensure proper salutation and sign-off
                        if not clean_body.startswith("Dear ") and not clean_body.startswith("Hello "):
                            clean_body = f"{salutation}\n\n{clean_body}"
                        if "Accounts Receivable" not in clean_body:
                            clean_body = f"{clean_body}\n\n{SIGN_OFF_TEXT}"
                        return {
                            "invoice_id": inv.invoice_id,
                            "recipient": cust.email if cust else "client@domain.com",
                            "subject": parsed["subject"].strip(),
                            "body": clean_body,
                            "reminder_level": reminder_level,
                            "tone": tone,
                        }
        except Exception as exc:
            logger.warning("Bedrock reminder email generation failed (%s). Using deterministic plain-text generator.", exc)

    # 2. Deterministic Context-Aware Plain-Text Engine (Zero CSS, Clean Text)
    if reminder_level == 1:
        subject = f"Friendly Payment Reminder: Invoice {inv.invoice_number} - {comp_name}"
        body = (
            f"{salutation}\n\n"
            f"We hope this note finds you well.\n\n"
            f"This is a gentle courtesy reminder regarding Invoice {inv.invoice_number} for {format_inr(inv.amount)}, "
            f"which reached its scheduled maturity date on {inv.due_date.strftime('%d %B %Y')} ({days} days ago).\n\n"
            f"If remittance has already been scheduled or completed, please accept our sincere thanks and reply with your bank UTR "
            f"or transaction reference so we may promptly update your ledger.\n\n"
            f"{bank_block}\n\n"
            f"{custom_instructions + '\n\n' if custom_instructions else ''}"
            f"{SIGN_OFF_TEXT}"
        )
    elif reminder_level == 2:
        subject = f"Second Notice: Overdue Payment for Invoice {inv.invoice_number} - {comp_name}"
        body = (
            f"{salutation}\n\n"
            f"We are following up regarding outstanding Invoice {inv.invoice_number} for {comp_name}, "
            f"which is currently {days} days overdue.\n\n"
            f"Financial Summary:\n"
            f"• Original Principal: {format_inr(inv.amount)}\n"
            f"• Accrued Late Penalty: {format_inr(inv.penalty_amount)}\n"
            f"• Total Outstanding Amount: {format_inr(inv.total_amount)}\n\n"
            f"Please arrange remittance at your earliest convenience to prevent further late fee accumulation "
            f"and maintain an uninterrupted credit facility.\n\n"
            f"{bank_block}\n\n"
            f"{custom_instructions + '\n\n' if custom_instructions else ''}"
            f"{SIGN_OFF_TEXT}"
        )
    else:
        subject = f"URGENT: Final Payment Demand Before Formal Escalation - Invoice {inv.invoice_number}"
        body = (
            f"{salutation}\n\n"
            f"Despite previous notices, Invoice {inv.invoice_number} for {comp_name} remains unpaid and is now {days} days past due.\n\n"
            f"Financial Summary:\n"
            f"• Outstanding Balance: {format_inr(inv.total_amount)} (including late fee of {format_inr(inv.penalty_amount)})\n\n"
            f"Please remit this balance immediately within 48 hours to avoid credit line suspension and escalation "
            f"to legal debt recovery proceedings.\n\n"
            f"{bank_block}\n\n"
            f"{custom_instructions + '\n\n' if custom_instructions else ''}"
            f"{SIGN_OFF_TEXT}"
        )

    return {
        "invoice_id": inv.invoice_id,
        "recipient": cust.email if cust else "client@domain.com",
        "subject": subject,
        "body": body,
        "reminder_level": reminder_level,
        "tone": tone,
    }


def draft_settlement_email_with_ai(
    customer_person: str,
    customer_company: str,
    invoice_number: str,
    original_amount: float,
    effective_pct: float,
    discount_amount: float,
    settlement_amount: float,
    hours_valid: int,
    commitment_id: str,
    prior_pct: float = 0.0,
    resolution_mode: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    bank_details: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Drafts an executive customer email for early settlement discounts using AI.
    Renders pure clean plain text with complete financial figures and banking instructions.
    """
    is_stacked = resolution_mode == "STACK"
    is_reduction = not is_stacked and prior_pct > 0 and effective_pct < prior_pct
    is_upgrade = not is_stacked and prior_pct > 0 and effective_pct > prior_pct
    salutation = resolve_salutation(customer_person, customer_company)
    bank_block = format_bank_transfer_block(bank_details, invoice_number)

    # 1. Attempt AI generation via Bedrock
    if not settings.use_mock_bedrock_fallback:
        try:
            from app.services.bedrock_service import BedrockGateway
            gateway = BedrockGateway()
            if gateway.client:
                prompt = (
                    f"You are an executive accounts receivable communications specialist for an enterprise corporation.\n"
                    f"Draft a formal, polite, and legally accurate customer settlement notice in clean plain text.\n\n"
                    f"COMMERCIAL CONTEXT:\n"
                    f"• Customer Contact: {customer_person}\n"
                    f"• Company: {customer_company}\n"
                    f"• Invoice Number: {invoice_number}\n"
                    f"• Original Balance: {format_inr(original_amount)}\n"
                    f"• New Discount: {effective_pct}% (Concession: -{format_inr(discount_amount)})\n"
                    f"• Net Settlement Amount Due: {format_inr(settlement_amount)}\n"
                    f"• Offer Validity Window: {hours_valid} Hours\n"
                    f"• Agreement Reference: {commitment_id}\n"
                    f"• Prior Concession on Record: {prior_pct}%\n"
                    f"• Custom Manager Directive: {custom_instructions or 'None'}\n\n"
                    f"CRITICAL COMPLIANCE RULES:\n"
                )
                if is_reduction:
                    prompt += (
                        f"1. PREVIOUS CONCESSION RETRACTED: The previous offer of {prior_pct}% has been cancelled/removed. "
                        f"The new discount is {effective_pct}%. You MUST explicitly state that the earlier {prior_pct}% offer "
                        f"was retracted/removed due to an administrative review. Include a sincere apology for any confusion or inconvenience.\n"
                        f"2. NEVER call a lower discount an 'upgrade'! It is a revised correction.\n"
                    )
                elif is_upgrade:
                    prompt += (
                        f"1. UPGRADED CONCESSION: State that the earlier {prior_pct}% concession has been upgraded to {effective_pct}%.\n"
                    )
                elif is_stacked:
                    prompt += (
                        f"1. STACKED CONCESSION: State that an additional concession has been stacked on top of the earlier discount, providing a total of {effective_pct}%.\n"
                    )
                else:
                    prompt += "1. Standard early settlement incentive notice.\n"

                prompt += (
                    f"Start with '{salutation}' and end with '{SIGN_OFF_TEXT}'.\n"
                    f"Output strictly valid JSON with keys 'subject' and 'body'. Absolutely NO markdown headings, NO HTML, and NO bracketed placeholders."
                )

                response = gateway.converse(
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    system_prompt="You are an enterprise credit control communications engine. Output valid JSON only.",
                )
                text = response.get("text", "")
                json_match = re.search(r"\{.*\}", text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if "subject" in parsed and "body" in parsed:
                        clean_body = parsed["body"].strip()
                        if bank_block and "Beneficiary" not in clean_body:
                            clean_body = f"{clean_body}\n\n{bank_block}"
                        return {"subject": parsed["subject"].strip(), "body": clean_body}
        except Exception as exc:
            logger.warning("Bedrock AI email generation encountered an issue (%s). Using deterministic template.", exc)

    # 2. Deterministic Context-Aware Plain-Text Fallback
    bank_section = f"\n\n{bank_block}" if bank_block else ""
    if is_reduction:
        subject = f"Important Correction: Revised {effective_pct}% Settlement Terms for Invoice {invoice_number}"
        body = (
            f"{salutation}\n\n"
            f"We are writing to provide an important update regarding outstanding invoice {invoice_number} for {customer_company}.\n\n"
            f"Please be advised that following an administrative audit of our commercial settlement schedule, the previous "
            f"{prior_pct}% concession notice has been formally retracted and removed. We sincerely apologize for any confusion "
            f"or inconvenience this revision may cause your team.\n\n"
            f"Our Accounts Department has officially authorized a revised {effective_pct}% early settlement discount if payment is remitted "
            f"within the next {hours_valid} hours of this notice:\n\n"
            f"• Original Outstanding Balance: {format_inr(original_amount)}\n"
            f"• Revised Concession ({effective_pct}%): -{format_inr(discount_amount)}\n"
            f"• Net Settlement Amount Due: {format_inr(settlement_amount)}\n"
            f"• Concession Validity: Next {hours_valid} Hours\n"
            f"• Official Agreement Reference: {commitment_id}\n\n"
            f"{custom_instructions or 'Please process payment via NEFT/RTGS and reply with the payment transaction reference to claim this revised concession.'}"
            f"{bank_section}\n\n"
            f"{SIGN_OFF_TEXT}"
        )
    elif is_upgrade:
        subject = f"Urgent Notice: Upgraded {effective_pct}% Early Settlement Incentive on Invoice {invoice_number}"
        body = (
            f"{salutation}\n\n"
            f"We are reaching out with an upgraded commercial offer regarding outstanding invoice {invoice_number} for {customer_company}.\n\n"
            f"In revision to our earlier notice (which offered a {prior_pct}% concession), our Accounts Department has officially authorized "
            f"an upgraded {effective_pct}% early settlement discount if payment is remitted within the next {hours_valid} hours:\n\n"
            f"• Original Outstanding Balance: {format_inr(original_amount)}\n"
            f"• Upgraded Concession ({effective_pct}%): -{format_inr(discount_amount)}\n"
            f"• Net Settlement Amount Due: {format_inr(settlement_amount)}\n"
            f"• Concession Validity: Next {hours_valid} Hours\n"
            f"• Official Agreement Reference: {commitment_id}\n\n"
            f"{custom_instructions or 'Please process payment via NEFT/RTGS and reply with payment transaction reference to claim this concession.'}"
            f"{bank_section}\n\n"
            f"{SIGN_OFF_TEXT}"
        )
    elif is_stacked:
        subject = f"Notice: Stacked {effective_pct}% Early Settlement Concession on Invoice {invoice_number}"
        body = (
            f"{salutation}\n\n"
            f"We are pleased to inform you that our Accounts Department has approved an additional settlement concession for invoice {invoice_number} ({customer_company}).\n\n"
            f"In addition to our previously authorized {prior_pct}% concession, an extra discount has been authorized, bringing your total "
            f"combined settlement discount to {effective_pct}% if remitted within the next {hours_valid} hours:\n\n"
            f"• Original Outstanding Balance: {format_inr(original_amount)}\n"
            f"• Total Stacked Concession ({effective_pct}%): -{format_inr(discount_amount)}\n"
            f"• Net Settlement Amount Due: {format_inr(settlement_amount)}\n"
            f"• Concession Validity: Next {hours_valid} Hours\n"
            f"• Official Agreement Reference: {commitment_id}\n\n"
            f"{custom_instructions or 'Please process remittance via NEFT/RTGS and reply with payment reference to claim this combined concession.'}"
            f"{bank_section}\n\n"
            f"{SIGN_OFF_TEXT}"
        )
    else:
        subject = f"Urgent Notice: {effective_pct}% Early Settlement Incentive on Invoice {invoice_number}"
        body = (
            f"{salutation}\n\n"
            f"We are reaching out regarding outstanding invoice {invoice_number} for {customer_company}.\n\n"
            f"Our Accounts Department has officially authorized an immediate {effective_pct}% early settlement discount "
            f"if your payment is remitted within the next {hours_valid} hours of this notice:\n\n"
            f"• Original Outstanding Balance: {format_inr(original_amount)}\n"
            f"• Concession Discount ({effective_pct}%): -{format_inr(discount_amount)}\n"
            f"• Net Settlement Amount Due: {format_inr(settlement_amount)}\n"
            f"• Concession Expiry: Next {hours_valid} Hours\n"
            f"• Official Agreement Reference: {commitment_id}\n\n"
            f"{custom_instructions or 'Please process remittance via NEFT/RTGS and reply with payment transaction reference to claim this concession.'}"
            f"{bank_section}\n\n"
            f"{SIGN_OFF_TEXT}"
        )

    return {"subject": subject, "body": body}


def draft_payment_confirmation_email(
    customer_name: Optional[str],
    company_name: Optional[str],
    invoice_number: str,
    amount_received: float,
    payment_method: str,
    reference_number: str,
) -> Dict[str, str]:
    """
    Drafts a clean, professional payment receipt confirmation email.
    Explicitly omits banking collection details since payment has already been settled.

    Args:
        customer_name: Contact person name.
        company_name: Company name.
        invoice_number: Settled invoice number.
        amount_received: Settled amount.
        payment_method: Payment rail (NEFT, RTGS, UPI, etc.).
        reference_number: Bank UTR or reference transaction code.

    Returns:
        Dict[str, str]: {'subject': str, 'body': str}
    """
    salutation = resolve_salutation(customer_name, company_name)
    subject = f"Payment Received Confirmation - Invoice {invoice_number}"
    body = (
        f"{salutation}\n\n"
        f"Thank you for your prompt remittance. We are pleased to confirm that payment has been successfully credited "
        f"against Invoice {invoice_number}.\n\n"
        f"Settlement Details:\n"
        f"• Amount Credited: {format_inr(amount_received)}\n"
        f"• Payment Method: {payment_method}\n"
        f"• Reference / UTR Number: {reference_number}\n\n"
        f"Your account balance for this invoice has been fully cleared in our accounts ledger, "
        f"and all further collection follow-ups have been cancelled.\n\n"
        f"Thank you for your valued business partnership.\n\n"
        f"{SIGN_OFF_TEXT}"
    )
    return {"subject": subject, "body": body}
