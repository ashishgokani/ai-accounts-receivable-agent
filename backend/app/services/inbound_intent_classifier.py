"""
Semantic Intent Classifier and Contextual AI Reply Generator.

Uses Amazon Nova Pro to interpret inbound emails within their verified commercial context:
- Deeply aware of real customer account status (NO_INVOICES_ON_FILE, ALL_INVOICES_SETTLED,
  SINGLE_OPEN_INVOICE, MULTIPLE_OPEN_INVOICES).
- Enforces strict factual accuracy: never promises unbacked receipts or assumes fictional invoices.
- Generates tailored, professional plain-text responses without placeholders.
- Provides robust deterministic fallbacks if LLM reasoning is offline.
"""

import json
import logging
import re
from datetime import timedelta
from typing import Dict, Any, Optional

from app.core.config import settings
from app.core.timezone import ist_today
from app.core.currency import format_inr
from app.services.bedrock_service import BedrockGateway
from app.services.ai_email_drafter import resolve_salutation, SIGN_OFF_TEXT

logger = logging.getLogger(__name__)

OFFICIAL_BANK_DETAILS = (
    "Bank Name: HDFC Bank\n"
    "Account Name: Fintech Enterprise AR Collections Ltd\n"
    "Account Number: 50200012345678\n"
    "IFSC Code: HDFC0001234\n"
    "Branch: Mumbai Corporate Banking Branch"
)


def classify_inbound_email(
    account_context: Dict[str, Any],
    clean_body: str,
    thread_history: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Classifies customer intent and drafts a factual, logically sound response.
    
    Args:
        account_context: Commercial snapshot from inbound_account_resolver.
        clean_body: Customer's fresh reply body.
        thread_history: Prior email thread history.
        
    Returns:
        Dict[str, Any]: Structured intent, entities, rationale, and acknowledgment text.
    """
    today_str = ist_today().isoformat()
    cust_name = account_context.get("customer_name", "Valued Customer")
    comp_name = account_context.get("company_name", "Corporate Debtor")
    acc_status = account_context.get("account_status", "NO_INVOICES_ON_FILE")
    total_bal = account_context.get("total_open_balance", 0.0)

    open_invs = account_context.get("open_invoices", [])
    open_inv_summary = (
        ", ".join([f"{i.invoice_number} ({format_inr(i.total_amount)}, {i.status})" for i in open_invs])
        if open_invs
        else "None"
    )

    settled_invs = account_context.get("settled_invoices", [])
    settled_summary = (
        ", ".join([i.invoice_number for i in settled_invs])
        if settled_invs
        else "None"
    )

    ref_inv = account_context.get("referenced_invoice")
    ref_inv_str = ref_inv.invoice_number if ref_inv else "None detected in text"

    prompt = (
        f"You are the autonomous communications reasoning engine for an enterprise Accounts Receivable department.\n"
        f"Analyze this customer email reply and draft an accurate, professional plain-text response.\n\n"
        f"VERIFIED COMMERCIAL ACCOUNT CONTEXT (GROUND TRUTH FROM RELATIONAL DATABASE):\n"
        f"• Customer: {cust_name} ({comp_name})\n"
        f"• Account Status: {acc_status}\n"
        f"  (Status meanings: NO_INVOICES_ON_FILE = zero invoices recorded; ALL_INVOICES_SETTLED = all past invoices paid; "
        f"SINGLE_OPEN_INVOICE / MULTIPLE_OPEN_INVOICES = active unpaid invoices exist)\n"
        f"• Total Current Open Balance: {format_inr(total_bal)}\n"
        f"• Open Invoices: {open_inv_summary}\n"
        f"• Settled Invoices: {settled_summary}\n"
        f"• Referenced Invoice: {ref_inv_str}\n"
        f"• Today's Date (IST): {today_str}\n\n"
        f"CUSTOMER'S NEW EMAIL TEXT:\n"
        f"\"\"\"{clean_body}\"\"\"\n\n"
        f"LOGICAL RESPONSE RULES (STRICT FACTUAL COMPLIANCE):\n"
        f"1. IF CUSTOMER SAYS PAYMENT DONE / TRANSFERRED (PAYMENT_CLAIMED):\n"
        f"   - When account_status == 'NO_INVOICES_ON_FILE': State clearly that our records show NO open or historical invoices on file for their account. "
        f"Do NOT assume an invoice exists. Do NOT promise an unbacked receipt. Politely request invoice number/order details, UTR/reference, amount, and date so finance can locate and allocate funds.\n"
        f"   - When account_status == 'ALL_INVOICES_SETTLED': Note that previous invoices are already fully settled (balance ₹0.00). Inquire if this transfer is an advance deposit or for a new upcoming order.\n"
        f"   - When open invoices exist: Reference the specific invoice number and amount. Acknowledge the UTR if provided, or politely request the UTR/bank receipt if missing to speed up reconciliation. State treasury is verifying with the bank before receipt issuance.\n\n"
        f"2. IF CUSTOMER PROMISES PAYMENT (PAYMENT_PROMISED): Extract promised date. If open invoices exist, confirm reminders are paused until then. If balance is ₹0, clarify account is already clear.\n"
        f"3. IF INVOICE DISPUTE (INVOICE_DISPUTE): Acknowledge dispute, confirm late fees and reminders are frozen while management investigates.\n"
        f"4. IF EXTENSION REQUEST (EXTENSION_REQUEST): Note request is submitted to credit management for commercial review.\n"
        f"5. IF GENERAL INQUIRY / BANK REMITTANCE DETAILS (GENERAL_INQUIRY):\n"
        f"   Provide bank remittance coordinates:\n{OFFICIAL_BANK_DETAILS}\n"
        f"6. IF UNKNOWN_OR_AMBIGUOUS: Politely request clarification in context of their current balance.\n\n"
        f"TONE & STYLE: Professional, concise, courteous plain text. Proper greeting ('Dear {cust_name},') and sign-off ('Warm regards,\\nAccounts Receivable Team'). Zero placeholders.\n\n"
        f"OUTPUT STRICTLY VALID JSON ONLY:\n"
        f"{{\n"
        f'  "intent": "PAYMENT_CLAIMED" | "PAYMENT_PROMISED" | "INVOICE_DISPUTE" | "EXTENSION_REQUEST" | "GENERAL_INQUIRY" | "UNKNOWN_OR_AMBIGUOUS" | "UNRELATED_SPAM",\n'
        f'  "confidence": 0.95,\n'
        f'  "promised_date": "YYYY-MM-DD" or null,\n'
        f'  "utr_reference": "..." or null,\n'
        f'  "claimed_amount": 0.0 or null,\n'
        f'  "dispute_reason": "..." or null,\n'
        f'  "customer_sentiment": "COOPERATIVE" | "DISTRESSED" | "HOSTILE" | "FORMAL" | "UNCERTAIN",\n'
        f'  "concise_rationale": "1-2 sentences explaining classification based on account status.",\n'
        f'  "ack_subject": "...",\n'
        f'  "ack_body": "..."\n'
        f"}}"
    )

    if not settings.use_mock_bedrock_fallback:
        try:
            gateway = BedrockGateway()
            if gateway.client:
                res = gateway.converse(
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    system_prompt="You are an enterprise credit control reasoning engine. Output valid JSON strictly.",
                )
                raw_text = res.get("text", "")
                json_match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if "intent" in parsed and "ack_body" in parsed:
                        return parsed
        except Exception as exc:
            logger.warning("Bedrock semantic classification failed: %s. Using deterministic fallback.", exc)

    return _deterministic_classification_fallback(account_context, clean_body)


def _deterministic_classification_fallback(
    account_context: Dict[str, Any],
    clean_body: str,
) -> Dict[str, Any]:
    """Generates factually validated fallback responses based on account state."""
    cust_name = account_context.get("customer_name", "Valued Customer")
    acc_status = account_context.get("account_status", "NO_INVOICES_ON_FILE")
    total_bal = account_context.get("total_open_balance", 0.0)
    primary_inv = account_context.get("primary_invoice")
    salutation = resolve_salutation(cust_name, None)
    lower = clean_body.lower()

    # 1. Payment Claimed
    if any(k in lower for k in [
        "paid", "payment", "transferred", "remitted", "neft", "utr", "rtgs", "deposited",
        "payment done", "done payment", "payment made", "payment sent"
    ]):
        utr_match = re.search(r"(?:utr|ref|neft|rtgs|reference|transaction\s*id)[\s:/-]*(?:is|no|num|number)?[\s:/-]*([a-zA-Z0-9]{5,})", lower)
        utr_val = utr_match.group(1).upper() if utr_match else None

        if acc_status == "NO_INVOICES_ON_FILE":
            return {
                "intent": "PAYMENT_CLAIMED",
                "confidence": 0.90,
                "promised_date": None,
                "utr_reference": utr_val,
                "claimed_amount": None,
                "dispute_reason": None,
                "customer_sentiment": "COOPERATIVE",
                "concise_rationale": "Customer claims payment, but customer currently has zero invoices on file.",
                "ack_subject": "Payment Notice Received: Account Details Clarification Required",
                "ack_body": (
                    f"{salutation}\n\n"
                    f"Thank you for contacting Accounts Receivable regarding your recent payment.\n\n"
                    f"Upon reviewing our accounts ledger, we currently do not find any active or outstanding invoices recorded under your account.\n\n"
                    f"To assist us in locating and correctly allocating your funds, could you please provide:\n"
                    f"1. The invoice number or sales order number this payment pertains to,\n"
                    f"2. The bank transaction reference (UTR / NEFT / IMPS),\n"
                    f"3. The exact amount transferred and the date of remittance.\n\n"
                    f"Once received, our finance team will match the credit and update your account records promptly.\n\n"
                    f"{SIGN_OFF_TEXT}"
                ),
            }
        elif acc_status == "ALL_INVOICES_SETTLED":
            return {
                "intent": "PAYMENT_CLAIMED",
                "confidence": 0.90,
                "promised_date": None,
                "utr_reference": utr_val,
                "claimed_amount": None,
                "dispute_reason": None,
                "customer_sentiment": "COOPERATIVE",
                "concise_rationale": "Customer claims payment, but all historical invoices are already settled (balance ₹0).",
                "ack_subject": "Payment Notification: Account Ledger Status Update",
                "ack_body": (
                    f"{salutation}\n\n"
                    f"Thank you for reaching out to us. We have checked your account ledger and note that all previous invoices are already fully settled in full, and your current outstanding balance is ₹0.00.\n\n"
                    f"If this transfer represents an advance payment or pertains to a new order, please share the order or purchase details so we can credit your balance accurately.\n\n"
                    f"{SIGN_OFF_TEXT}"
                ),
            }
        else:
            inv_num = primary_inv.invoice_number if primary_inv else "Outstanding Account"
            utr_text = f" (Reference: {utr_val})" if utr_val else ""
            missing_utr_note = "If you have not already shared the bank UTR or remittance receipt, please reply with those details to help expedite verification." if not utr_val else ""
            return {
                "intent": "PAYMENT_CLAIMED",
                "confidence": 0.95,
                "promised_date": None,
                "utr_reference": utr_val or "PENDING_VERIFICATION",
                "claimed_amount": primary_inv.total_amount if primary_inv else total_bal,
                "dispute_reason": None,
                "customer_sentiment": "COOPERATIVE",
                "concise_rationale": f"Customer claims payment for Invoice {inv_num}.",
                "ack_subject": f"Payment Verification in Progress: Invoice {inv_num}",
                "ack_body": (
                    f"{salutation}\n\n"
                    f"Thank you for notifying us of your payment regarding Invoice {inv_num}{utr_text}.\n\n"
                    f"Our treasury department is currently reconciling the credit against our bank statement. {missing_utr_note}\n\n"
                    f"Once verified, we will issue your official payment receipt and an updated account statement.\n\n"
                    f"{SIGN_OFF_TEXT}"
                ),
            }

    # 2. Payment Promised
    if any(k in lower for k in ["promise", "will pay", "pay next", "friday", "monday", "tomorrow", "days"]):
        days_match = re.search(r"(\d+)\s*days?", lower)
        days_add = int(days_match.group(1)) if days_match else 3
        p_date = (ist_today() + timedelta(days=days_add)).isoformat()
        inv_num = primary_inv.invoice_number if primary_inv else "Account"
        return {
            "intent": "PAYMENT_PROMISED",
            "confidence": 0.88,
            "promised_date": p_date,
            "utr_reference": None,
            "claimed_amount": None,
            "dispute_reason": None,
            "customer_sentiment": "COOPERATIVE",
            "concise_rationale": f"Customer committed to remit payment by {p_date}.",
            "ack_subject": f"Payment Schedule Noted: {inv_num}",
            "ack_body": (
                f"{salutation}\n\n"
                f"Thank you for the update. We have noted your commitment to release payment by {p_date} for {inv_num}.\n\n"
                f"Automated collection reminder notices have been placed on hold until then.\n\n"
                f"{SIGN_OFF_TEXT}"
            ),
        }

    # 3. Invoice Dispute
    if any(k in lower for k in ["dispute", "incorrect", "wrong amount", "overcharge", "damaged", "po discrepancy"]):
        inv_num = primary_inv.invoice_number if primary_inv else "Account"
        return {
            "intent": "INVOICE_DISPUTE",
            "confidence": 0.90,
            "promised_date": None,
            "utr_reference": None,
            "claimed_amount": None,
            "dispute_reason": clean_body[:200],
            "customer_sentiment": "HOSTILE",
            "concise_rationale": "Customer submitted a commercial or billing dispute.",
            "ack_subject": f"Dispute Notice Logged: {inv_num}",
            "ack_body": (
                f"{salutation}\n\n"
                f"We have registered your inquiry regarding {inv_num}. Late fee accruals and collection notices have been paused while billing management investigates your query.\n\n"
                f"An accounts manager will reach out shortly with an update.\n\n"
                f"{SIGN_OFF_TEXT}"
            ),
        }

    # 4. Bank Details Request
    if any(k in lower for k in ["bank", "account details", "where to pay", "remittance info", "ifsc"]):
        return {
            "intent": "GENERAL_INQUIRY",
            "confidence": 0.95,
            "promised_date": None,
            "utr_reference": None,
            "claimed_amount": None,
            "dispute_reason": None,
            "customer_sentiment": "COOPERATIVE",
            "concise_rationale": "Customer requested bank remittance details.",
            "ack_subject": "Remittance Bank Account Details: Accounts Receivable",
            "ack_body": (
                f"{salutation}\n\n"
                f"Please find our official bank remittance coordinates below:\n\n"
                f"{OFFICIAL_BANK_DETAILS}\n\n"
                f"Kindly reference your invoice number when initiating the transfer and reply with the UTR number once remitted.\n\n"
                f"{SIGN_OFF_TEXT}"
            ),
        }

    # Default Ambiguous
    return {
        "intent": "UNKNOWN_OR_AMBIGUOUS",
        "confidence": 0.40,
        "promised_date": None,
        "utr_reference": None,
        "claimed_amount": None,
        "dispute_reason": None,
        "customer_sentiment": "UNCERTAIN",
        "concise_rationale": "Customer message does not specify invoice or concrete payment status.",
        "ack_subject": "Accounts Receivable: Inquiry Acknowledged",
        "ack_body": (
            f"{salutation}\n\n"
            f"Thank you for contacting Accounts Receivable. Could you please specify your invoice number or share additional details regarding your inquiry so our team can assist you?\n\n"
            f"{SIGN_OFF_TEXT}"
        ),
    }
