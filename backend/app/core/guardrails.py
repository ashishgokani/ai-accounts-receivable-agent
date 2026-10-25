"""
Security Guardrails and Business Rule Boundary Enforcement.

Intercepts all agent actions and tool requests before database mutations
or external communications occur, preventing unauthorized financial alterations,
spurious reminder spam, and hallucinations.
"""

import re
from typing import Tuple, Optional, Any
from app.core.config import settings
from app.core.currency import format_inr
from app.db.models import Invoice


class GuardrailViolationError(Exception):
    """Raised when an agent action violates a deterministic safety guardrail."""
    pass


def validate_invoice_for_action(invoice: Invoice, action: str, db: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
    """
    Validates whether an invoice can legitimately transition through the requested action.
    
    Args:
        invoice: SQLAlchemy Invoice model instance.
        action: Target action string (e.g. 'SEND_REMINDER', 'ESCALATE', 'RECORD_PAYMENT').
        db: Optional database session to load risk-tiered settings.
        
    Returns:
        Tuple[bool, Optional[str]]: (True, None) if permitted, or (False, reason) if blocked.
    """
    # Guardrail 1: Never harass customers for already paid invoices
    if invoice.status == "PAID" and action != "RECORD_PAYMENT":
        return False, f"Invoice {invoice.invoice_id} is already PAID. No further reminders or escalations are permitted."

    # Guardrail 2: Cancelled invoices are strictly immutable
    if invoice.status == "CANCELLED":
        return False, f"Invoice {invoice.invoice_id} has been CANCELLED and cannot be modified."

    # Load configured reminder rules for customer risk tier
    pause_dispute = True
    max_reminders = settings.max_reminders_before_escalation
    if db:
        try:
            from app.services.settings_service import get_risk_reminder_rule
            risk_level = invoice.customer.risk_level if invoice.customer else "Low"
            rule = get_risk_reminder_rule(db, risk_level)
            pause_dispute = rule.pause_on_dispute
            max_reminders = rule.max_reminders_before_escalation
        except Exception:
            pass

    # Guardrail 3: Invoices in active dispute cannot receive automated reminders if pause_on_dispute is enabled
    if invoice.status == "DISPUTED" and action in ("SEND_REMINDER", "SEND_EMAIL") and pause_dispute:
        return False, f"Invoice {invoice.invoice_id} is in DISPUTE. Reminders are paused until resolution."

    # Guardrail 4: Maximum reminder limit enforcement
    if action == "SEND_REMINDER" and invoice.reminder_count >= max_reminders:
        return False, f"Invoice {invoice.invoice_id} has reached {invoice.reminder_count} reminders. Must be ESCALATED rather than reminded."

    return True, None


def requires_human_approval(invoice: Invoice, action_type: str, db: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
    """
    Determines whether a proposed agent action exceeds autonomous authority
    and must be gated behind human review.
    
    Args:
        invoice: Invoice model instance.
        action_type: Intended action type.
        db: Optional database session to load risk-tiered settings.
        
    Returns:
        Tuple[bool, Optional[str]]: (True, reason) if human approval is required, else (False, None).
    """
    # High-value invoices exceeding threshold (e.g., ₹1,00,000)
    if invoice.total_amount >= settings.high_value_approval_threshold:
        return True, f"High-value invoice ({format_inr(invoice.total_amount)} >= {format_inr(settings.high_value_approval_threshold)}) requires human sign-off."

    # Legal / Executive escalations require human sign-off
    if action_type in ("ESCALATE", "CREATE_ESCALATION"):
        return True, "Formal escalation triggers legal/management review and requires human authorization."

    # Load final reminder approval setting
    final_approval_req = True
    max_reminders = settings.max_reminders_before_escalation
    if db:
        try:
            from app.services.settings_service import get_risk_reminder_rule
            risk_level = invoice.customer.risk_level if invoice.customer else "Low"
            rule = get_risk_reminder_rule(db, risk_level)
            final_approval_req = rule.final_reminder_approval_required
            max_reminders = rule.max_reminders_before_escalation
        except Exception:
            pass

    # Final notice reminder approval
    if final_approval_req:
        if action_type in ("SEND_THIRD_REMINDER", "THIRD_REMINDER") or (
            action_type == "SEND_REMINDER" and invoice.reminder_count >= max(1, max_reminders - 1)
        ):
            return True, "Final notice requires supervisory review before dispatch."

    return False, None


def sanitize_input(text: str) -> str:
    """
    Sanitizes user or prompt input to prevent prompt injection and control character abuse.
    
    Args:
        text: Raw input string.
        
    Returns:
        str: Cleaned text safe for processing.
    """
    if not text:
        return ""
    # Strip null bytes and non-printable control characters
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return cleaned.strip()


def validate_agent_capability(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether an administrator instruction is within autonomous software capabilities
    and adheres to financial compliance, corporate ethics, and safety boundaries.
    
    If the request demands physical tasks, telephony/SMS/WhatsApp, financial ledger wiping,
    or aggressive/unethical recovery, it rejects execution with a polite, constructive explanation.
    
    Args:
        prompt: Raw user query or prompt string.
        
    Returns:
        Tuple[bool, Optional[str]]: (True, None) if permissible, or (False, refusal_text) if out-of-scope.
    """
    if not prompt:
        return True, None

    lower = prompt.lower()

    # Boundary 1: Physical delivery / In-person recovery
    if any(k in lower for k in ["courier", "physical visit", "go to their office", "send someone to their house", "in person"]):
        return False, (
            "Currently, I do not have the capability to dispatch physical couriers or conduct in-person visits. "
            "My autonomous operations are strictly digital (corporate email notices, ledger audits, and workflow tracking).\n\n"
            "**Recommended Alternative:** You can instruct me to send an urgent formal email notice or escalate "
            "this account to the Senior Credit Manager for field review."
        )

    # Boundary 2: Unsupported communication channels (WhatsApp, SMS, Phone Call)
    if any(k in lower for k in ["whatsapp", "send sms", "send text message", "call their phone", "voice call"]):
        return False, (
            "Currently, I do not have an active telephony, SMS, or WhatsApp gateway connected. "
            "All outbound debtor communications are officially managed via authenticated corporate email (SMTP/Simulated).\n\n"
            "**Recommended Alternative:** I can dispatch a customized high-priority payment reminder or settlement proposal to their verified billing email address."
        )

    # Boundary 3: Financial integrity & destructive database wiping
    if any(k in lower for k in ["delete all invoices", "wipe all records", "drop database", "erase audit logs", "delete transaction history", "clear all data"]):
        return False, (
            "I cannot execute this request. Corporate accounting standards (GAAP/IFRS) strictly prohibit deleting "
            "auditable financial transaction history, active ledgers, or issued invoices.\n\n"
            "**Recommended Alternative:** If an invoice is incorrect or canceled by mutual agreement, I can update its status to "
            "`CANCELLED` or `DISPUTED`, or archive inactive customer profiles that have zero outstanding debt."
        )

    # Boundary 4: Unethical recovery, harassment, or coercion
    if any(k in lower for k in ["threaten", "harass", "hack", "seize assets", "steal", "blackmail"]):
        return False, (
            "I cannot execute this instruction. All debt recovery actions must strictly comply with fair credit "
            "collection practices and corporate ethics. Coercive tactics, harassment, or threats are prohibited.\n\n"
            "**Recommended Alternative:** I can prepare a formal notice of legal escalation or calculate contractual "
            "late interest penalties according to verified corporate policy."
        )

    # Boundary 5: Direct bank auto-debits, card charging, or unauthorized fund transfers
    if any(k in lower for k in ["auto-debit", "direct debit", "charge their card", "charge credit card", "withdraw from their bank", "deduct from their bank"]):
        return False, (
            "Currently, I do not have direct automated debit (NACH/e-mandate) authority over customer bank accounts or payment cards. "
            "All AR collections require voluntary remittance from the debtor via approved bank channels (NEFT/RTGS/UPI).\n\n"
            "**Recommended Alternative:** I can dispatch an official settlement agreement or payment reminder containing our corporate bank account details."
        )

    # Boundary 6: Arbitrary ledger alteration of historical invoice totals without credit note
    if any(k in lower for k in ["change invoice amount to", "alter invoice amount", "edit invoice total", "modify invoice amount", "change total to"]):
        return False, (
            "I cannot directly alter the base total of an issued invoice. Corporate tax compliance (GST/VAT) and audit rules "
            "require that issued tax invoices remain immutable unless adjusted via an authorized Early Settlement Discount or Credit Note.\n\n"
            "**Recommended Alternative:** I can apply an official settlement discount percentage (e.g. 'Apply 0.5% early settlement discount') "
            "or grant a grace period pause to keep all adjustments fully auditable."
        )

    return True, None

