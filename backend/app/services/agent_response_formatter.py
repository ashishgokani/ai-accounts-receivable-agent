"""
Deterministic Response and Rich Markdown Formatting Engine.

Provides polished, executive-ready Markdown presentation tables and cards
when the reasoning agent returns brief or raw data, while strictly preventing
unwanted PendingActions or hijacked reminder confirmations during inquiries.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.services.action_state_machine import create_pending_action
from app.core.currency import format_inr

logger = logging.getLogger(__name__)


def is_user_inquiry(message: str) -> bool:
    """
    Detects if the user prompt is an informational question, inquiry, or explanation request
    rather than an actionable dispatch command.

    Args:
        message: Raw user prompt string.

    Returns:
        bool: True if prompt seeks explanation or data inquiry.
    """
    clean = message.strip().lower()
    inquiry_keywords = [
        "why", "what", "how", "when", "who", "which",
        "explain", "reason", "clarify", "tell me", "details of",
        "difference", "did you", "have you", "is there", "are there",
    ]
    # Check if starts with inquiry keyword or contains question mark
    if "?" in clean:
        return True
    for kw in inquiry_keywords:
        if clean.startswith(kw) or f" {kw} " in clean:
            return True
    return False


def is_greeting(message: str) -> bool:
    """
    Detects if the user prompt is a greeting, pleasantry, or introductory remark
    (e.g., 'Hi', 'Hello', 'Good morning', 'Thanks') that requires conversational
    engagement rather than operational ledger tools.

    Args:
        message: Raw user prompt string.

    Returns:
        bool: True if prompt is a greeting or conversational pleasantry.
    """
    clean = message.strip().lower()
    clean_no_punct = re.sub(r"[^\w\s]", "", clean).strip()

    standalone_greetings = {
        "hi", "hello", "hey", "hola", "howdy", "greetings",
        "good morning", "good afternoon", "good evening", "good day",
        "morning", "evening", "thanks", "thank you", "thx", "ok",
        "okay", "k", "cool", "great", "awesome", "perfect",
        "understood", "got it", "bye", "goodbye", "who are you",
        "what are you", "what can you do", "introduce yourself", "help",
    }
    if clean_no_punct in standalone_greetings:
        return True

    greeting_starters = (
        "hi", "hello", "hey", "greetings", "good morning", "good afternoon",
        "good evening", "good day", "thanks", "thank you",
    )
    if clean_no_punct.startswith(greeting_starters):
        action_keywords = {"send", "give", "discount", "remind", "escalate", "extension", "grace", "invoice", "overdue", "pay"}
        if not any(ak in clean_no_punct for ak in action_keywords):
            return True

    return False


def is_reminder_intent(message: str) -> bool:
    """
    Determines if user prompt explicitly intended to initiate reminder dispatches.
    """
    clean = message.strip().lower()
    reminder_keywords = ["remind", "reminder", "overdue invoices", "show overdue", "list overdue", "send reminders"]
    return any(kw in clean for kw in reminder_keywords)


def format_deterministic_tool_fallback(
    tool_name: str,
    output: Dict[str, Any],
    user_message: str = "",
    session_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Optional[str]:
    """
    Formats raw tool outputs into rich executive Markdown.

    Args:
        tool_name: Name of the executed tool.
        output: Dictionary payload returned by the tool.
        user_message: User's original prompt for contextual decisioning.
        session_id: Current chat session ID.
        db: Optional database session for registering pending actions when explicitly appropriate.

    Returns:
        Optional[str]: Rich Markdown formatted text, or None if no specific formatter applies.
    """
    if "error" in output:
        return f"⚠️ **Notice:** {output['error']}"

    # 1. Overdue Invoices Formatter
    if tool_name == "get_overdue_invoices":
        invs = output.get("invoices", [])
        if not invs:
            return "Good news! There are currently no invoices matching the requested overdue threshold in the database."

        rows = [
            f"| **{inv.get('invoice_number') or inv.get('invoice_id', 'INV')}** | "
            f"{inv.get('company_name') or inv.get('customer_name', 'Client')} | "
            f"{format_inr(inv.get('amount', 0))} | {format_inr(inv.get('penalty_amount', 0))} | "
            f"{format_inr(inv.get('total_amount', 0))} | **{inv.get('days_overdue', 0)} days** | `{inv.get('status', 'OVERDUE')}` |"
            for inv in invs
        ]
        table_md = (
            f"### 📋 Overdue Invoices Breakdown\n\n"
            f"Found **{len(invs)} accounts** matching your overdue aging criteria:\n\n"
            f"| Invoice No | Customer | Principal | Late Penalty | Total Due | Days Overdue | Status |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows)
        )

        # Only create a PendingAction and prompt for confirmation if the user actually requested reminders
        user_wants_reminders = is_reminder_intent(user_message) and not is_user_inquiry(user_message)
        if user_wants_reminders and db and session_id:
            overdue_ids = [inv.get("invoice_id") for inv in invs if inv.get("invoice_id")]
            create_pending_action(
                db=db,
                session_id=session_id,
                tool_name="send_reminders",
                description=f"Dispatch payment reminders to {len(invs)} overdue accounts",
                parameters={"invoice_ids": overdue_ids},
                target_invoices=overdue_ids,
                expires_in_minutes=15,
            )
            return table_md + f"\n\n**Action Confirmation:** Would you like me to dispatch payment reminders to these {len(invs)} accounts now? Reply **'Yes'** to execute or **'No'** to cancel."

        return table_md

    # 2. Bulk Settlement Offer Formatter
    elif tool_name == "send_bulk_settlement_offer":
        if output.get("status") == "CONFLICT_ACTIVE_COMMITMENTS_DETECTED":
            conflicts = output.get("active_conflicts", [])
            req_disc = output.get("requested_discount_percent", 0.0)
            rows = [
                f"| **{c.get('customer', 'Client')}** | `{c.get('invoice_number', 'INV')}` | "
                f"{format_inr(c.get('total_amount', 0))} | `{c.get('commitment_id')}` | "
                f"{c.get('existing_discount_percent', 0)}% ({format_inr(c.get('existing_discount_amount', 0))}) | {c.get('valid_until', '24 Hours')} |"
                for c in conflicts
            ]
            conflict_table = (
                f"| Customer | Invoice No | Current Balance | Active Commitment ID | Current Concession | Expiry |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                + "\n".join(rows)
            )
            return (
                f"### ⚠️ Active Commercial Commitment Conflict Detected\n\n"
                f"Active, unexpired settlement offers already exist for **{len(conflicts)} qualifying account(s)**. "
                f"To prevent sending duplicate conflicting emails and avoid uncoordinated discounting, "
                f"**no emails have been sent and no records have been altered**.\n\n"
                f"{conflict_table}\n\n"
                f"#### ❓ How would you like to handle this **{req_disc}% discount** request?\n\n"
                f"1. **Option 1: Revise & Upgrade**\n"
                f"   - Supersedes the earlier offer with the new **{req_disc}%** discount.\n"
                f"   - The customer email will explicitly state: *\"In revision to our earlier notice... an upgraded {req_disc}% discount is authorized.\"*\n\n"
                f"2. **Option 2: Stack Concession**\n"
                f"   - Adds **+{req_disc}%** on top of the customer's existing concession.\n\n"
                f"3. **Option 3: Cancel**\n"
                f"   - Discards this request and keeps the existing agreement active. Zero emails sent.\n\n"
                f"👉 **Please reply in chat with \"Revise\" (or \"1\"), \"Stack\" (or \"2\"), or \"Cancel\" (or \"3\").**"
            )

        dispatches = output.get("dispatches", [])
        if not dispatches:
            return output.get("message", "No eligible accounts qualified for the settlement discount.")

        all_skipped = all("SKIPPED" in str(d.get("delivery_status", "")) for d in dispatches)
        any_skipped = any("SKIPPED" in str(d.get("delivery_status", "")) for d in dispatches)

        if all_skipped:
            header_title = "### ℹ️ Active Settlement Offers Already in Effect"
            header_sub = (
                f"Active **{output.get('discount_percent')}% early settlement discount offers** are already in effect for these accounts. "
                f"Duplicate customer email notices were suppressed to prevent debtor spam:"
            )
        elif any_skipped:
            header_title = "### 📧 Settlement Campaign Updated"
            header_sub = (
                f"Updated settlement offers for qualifying accounts. Dispatched new agreements where needed and "
                f"preserved existing active offers without sending duplicate emails:"
            )
        else:
            header_title = "### 📧 Early Settlement Discount Campaign Dispatched"
            header_sub = (
                f"Successfully generated and delivered **{output.get('discount_percent')}% early settlement discount offers** "
                f"to all **{len(dispatches)} customers** with unsettled balances:"
            )

        rows = [
            f"| **{d.get('customer', 'Client')}** | {d.get('invoice_number', 'INV')} | "
            f"{format_inr(d.get('original_amount', 0))} | {format_inr(d.get('discount_amount', 0))} | "
            f"**{format_inr(d.get('settlement_amount', 0))}** | `{d.get('delivery_status', 'SENT')}` |"
            for d in dispatches
        ]
        return (
            f"{header_title}\n\n"
            f"{header_sub}\n\n"
            f"| Customer | Invoice No | Original Amount | Discount ({output.get('discount_percent')}%) | Net Settlement Due | Dispatch Status |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows) + "\n\n"
            f"**Settlement Terms:** Agreements are valid for **{output.get('hours_valid', 24)} hours** and tracked in the database commitment ledger."
        )

    # 3. Grace Period Formatter
    elif tool_name == "grant_grace_period":
        return (
            f"### ⏳ Payment Grace Period Extension Authorized\n\n"
            f"• **Invoice:** `{output.get('invoice_number')}`\n"
            f"• **Extension Duration:** **{output.get('days_granted')} Days**\n"
            f"• **Reminder Freeze Active Until:** `{output.get('frozen_until')}`\n"
            f"• **Commitment Reference:** `{output.get('commitment_id')}`\n\n"
            f"Automated reminder dispatches have been paused for this account until the extension expires."
        )

    # 4. Revocation Formatter
    elif tool_name == "revoke_commitment":
        return f"### 🔄 Commercial Commitment Revoked\n\n{output.get('message', 'Active commitment has been revoked and contractual terms restored.')}"

    # 5. Communication History Formatter
    elif tool_name == "get_communication_history":
        comms = output.get("communications", [])
        if not comms:
            return "No previous communications found matching your query criteria."

        rows = [
            f"| {c.get('sent_at', '')[:19].replace('T', ' ')} | `{c.get('invoice_id') or 'N/A'}` | "
            f"`{c.get('type')}` | **{c.get('subject', '')}** |"
            for c in comms
        ]
        return (
            f"### 📬 Communication Audit Log\n\n"
            f"Found **{len(comms)} dispatched customer communications**:\n\n"
            f"| Sent Timestamp | Invoice ID | Type | Subject |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows)
        )

    # 6. Invoice Commitments Formatter
    elif tool_name == "get_invoice_commitments":
        comms = output.get("commitments", [])
        if not comms:
            return "No commercial commitments or settlement discount agreements found matching criteria."

        rows = [
            f"| `{c.get('commitment_id')}` | `{c.get('invoice_id')}` | `{c.get('commitment_type')}` | "
            f"{c.get('description')} | `{c.get('status')}` | {c.get('valid_until', 'N/A')[:19].replace('T', ' ')} |"
            for c in comms
        ]
        return (
            f"### 📑 Registered Commercial Commitments\n\n"
            f"Found **{len(comms)} commitments** in the ledger:\n\n"
            f"| Commitment ID | Invoice ID | Type | Description | Status | Valid Until |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows)
        )

    # 7. Invoice Details Formatter
    elif tool_name == "get_invoice_details":
        inv = output
        return (
            f"### 📄 Invoice Ledger Dossier: `{inv.get('invoice_number', 'INV')}`\n\n"
            f"• **Customer:** {inv.get('customer_name')} ({inv.get('customer_email')})\n"
            f"• **Principal Amount:** {format_inr(inv.get('amount', 0))}\n"
            f"• **Late Penalty Accrued:** {format_inr(inv.get('penalty_amount', 0))}\n"
            f"• **Total Outstanding Balance:** **{format_inr(inv.get('total_amount', 0))}**\n"
            f"• **Status:** `{inv.get('status')}` ({inv.get('days_overdue', 0)} days overdue)\n"
            f"• **Due Date:** `{inv.get('due_date')}`\n"
            f"• **Reminders Dispatched:** {inv.get('reminder_count', 0)}"
        )

    # 8. Customer Profile Update Formatter
    elif tool_name == "update_customer_profile":
        changes = ", ".join(output.get("changes_applied", [])) or "Profile saved"
        return (
            f"### 👤 Corporate Customer Profile Updated\n\n"
            f"• **Company:** **{output.get('company_name')}** (`{output.get('customer_id')}`)\n"
            f"• **Billing Contact:** {output.get('name')}\n"
            f"• **Email:** `{output.get('email')}`\n"
            f"• **Phone:** {output.get('phone') or 'Not specified'}\n"
            f"• **Address:** {output.get('address') or 'Not specified'}\n"
            f"• **Credit Risk:** `{output.get('risk_level')}` (Score: **{output.get('risk_score')}/100**)\n\n"
            f"**Modifications Applied:** {changes}"
        )

    # 9. Invoice Data Update Formatter
    elif tool_name == "update_invoice_data":
        changes = ", ".join(output.get("changes_applied", [])) or "Terms updated"
        return (
            f"### 📄 Invoice Ledger Terms Updated: `{output.get('invoice_number')}`\n\n"
            f"• **Principal Amount:** {format_inr(output.get('amount', 0))}\n"
            f"• **Late Penalty Accrued:** {format_inr(output.get('penalty_amount', 0))}\n"
            f"• **Net Total Balance Due:** **{format_inr(output.get('total_amount', 0))}**\n"
            f"• **Due Date:** `{output.get('due_date')}`\n"
            f"• **Status:** `{output.get('invoice_status') or output.get('status')}`\n\n"
            f"**Changes Applied:** {changes}"
        )

    # 10. Automation Cycle Formatter
    elif tool_name == "trigger_automation_cycle":
        logs = output.get("action_logs", [])
        log_rows = "\n".join(f"• {log}" for log in logs[:5]) if logs else "• All monitored accounts evaluated."
        return (
            f"### ⚡ Autonomous Collection Cycle Executed\n\n"
            f"• **Invoices Analyzed:** {output.get('invoices_analyzed', 0)}\n"
            f"• **Automated Actions Executed:** {output.get('actions_executed', 0)}\n"
            f"• **High-Value Approvals Pending:** {output.get('approvals_pending', 0)}\n\n"
            f"**Execution Log Snippet:**\n{log_rows}\n\n"
            f"{output.get('summary', '')}"
        )

    # 11. Pending Approvals Formatter
    elif tool_name == "get_pending_approvals":
        apprs = output.get("approvals", [])
        if not apprs:
            return "✅ **No Pending Approvals:** All high-value actions have been cleared."
        rows = [
            f"| `{a.get('approval_id')}` | `{a.get('action_type')}` | `{a.get('invoice_number')}` | "
            f"**{a.get('customer_company')}** | {format_inr(a.get('total_amount', 0))} | {a.get('created_at')} |"
            for a in apprs
        ]
        return (
            f"### ⏳ Pending Human-in-the-Loop Approvals ({len(apprs)})\n\n"
            f"| Approval ID | Action | Invoice No | Company | Total Balance | Requested At |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows) + "\n\n"
            f"To authorize or reject an action, type: *\"Approve {apprs[0].get('approval_id')}\"* or *\"Reject {apprs[0].get('approval_id')}\"*."
        )

    # 12. Financial Portfolio Summary Formatter
    elif tool_name == "get_financial_portfolio_summary":
        return (
            f"### 📊 Accounts Receivable Portfolio Health\n\n"
            f"• **Total Invoiced Balance:** {format_inr(output.get('total_invoiced_amount', 0))} across **{output.get('total_invoices', 0)} invoices**\n"
            f"• **Total Outstanding Balance:** **{format_inr(output.get('total_outstanding_amount', 0))}**\n"
            f"• **Total Overdue Debt:** **{format_inr(output.get('total_overdue_amount', 0))}** ({output.get('overdue_invoices_count', 0)} overdue accounts)\n"
            f"• **Late Penalties Accrued:** {format_inr(output.get('total_penalties_accrued', 0))}\n"
            f"• **Collection Efficiency Rate:** **{output.get('collection_efficiency_rate', '0.0%')}**\n"
            f"• **Active Escalations:** {output.get('active_escalations', 0)} | **Pending Approvals:** {output.get('pending_approvals', 0)}"
        )

    # 13. Agent Audit Logs Formatter
    elif tool_name == "get_agent_audit_logs":
        logs = output.get("logs", [])
        if not logs:
            return "No recent agent execution logs found."
        rows = [
            f"| {l.get('created_at')} | `{l.get('action_type')}` | `{l.get('tool_name')}` | `{l.get('status')}` |"
            for l in logs
        ]
        return (
            f"### 🛡️ Autonomous Agent Audit Trail\n\n"
            f"| Timestamp | Action Type | Tool Name | Status |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows)
        )

    return None
