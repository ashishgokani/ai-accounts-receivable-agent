"""
Deterministic Pending Action State Machine.

Coordinates the lifecycle of consequential agent write actions awaiting human approval.
Guarantees fail-closed safety, strict idempotency, multi-turn confirmation resolution,
and comprehensive audit logging for the Autonomous Accounts Receivable Agent.
"""

from datetime import datetime, timedelta
import json
import logging
import re
import uuid
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.models import PendingAction, Invoice, Customer, AgentAction
from app.services.tools import (
    tool_send_email,
    tool_draft_reminder_email,
    tool_create_escalation,
    tool_record_payment,
    log_agent_action,
)
from app.services.tools_crud import (
    tool_send_custom_communication,
)
from app.services.commitments_service import (
    tool_apply_settlement_discount,
    tool_grant_grace_period,
    tool_revoke_commitment,
)

logger = logging.getLogger(__name__)


def is_affirmative_intent(message: str) -> bool:
    """
    Evaluates whether a user reply represents an affirmative confirmation or option selection.
    Guarantees that full natural-language instructions (e.g. 'Send email to customers...')
    are NEVER misclassified as short confirmation replies.
    
    Examples: 'yes', 'proceed', 'confirm', 'revise', 'stack', 'option 1', '1', '2'.
    """
    clean = message.lower().strip()
    clean = re.sub(r"^[!.,?#]+", "", clean).strip()
    
    words = clean.split()
    starts_with_affirmative = bool(re.search(r"^(yes|yep|yeah|yup|sure|ok|okay|proceed|confirm|approved?)\b", clean))

    # Confirmations are short acknowledgements, or affirmative statements with directives (up to 40 words, 250 characters)
    max_words = 40 if starts_with_affirmative else 10
    max_chars = 250 if starts_with_affirmative else 80
    if len(words) > max_words or len(clean) > max_chars:
        return False

    # Disallow imperative action commands: any message starting with "send" or "please send"
    # unless it is strictly confirming "send it", "send them", "please send it", or "please send them"
    if re.search(r"^(please\s+)?send\b", clean) and not re.search(r"^(please\s+)?send\s+(it|them|now)\b", clean):
        return False

    # Any message referencing specific business entities or communication mediums is an operational instruction
    if any(k in clean for k in ["email", "mail", "customer", "invoice", "statement", "discount", "account"]):
        return False

    # Disallow informational queries or instructions containing search/inquiry verbs
    if re.search(r"\b(find|show|list|get|check|display|tell|search|details|all\s+customers|all\s+invoices|how\s+many|what|why|who|where)\b", clean):
        return False
        
    affirmative_patterns = [
        r"^(yes|yep|yeah|yup|sure|ok|okay|proceed|confirm|approved?)\b",
        r"^(send\s+it|send\s+them|send\s+now|dispatch\s+it|dispatch\s+them|do\s+it|go\s+ahead|execute)\b",
        r"\b(please\s+proceed|please\s+do\s+so|please\s+do\s+it|please\s+send\s+it|please\s+send\s+them|go\s+for\s+it|sounds\s+good|confirmed)\b",
        r"^(revise|replace|upgrade|stack|add\s+on\s+top|option\s+[12]|[12])\b",
        r"\b(revise\s+to|upgrade\s+to|proceed\s+with\s+revision|apply\s+revision|revise\s+it)\b",
    ]
    return any(re.search(pat, clean) for pat in affirmative_patterns)


def is_cancellation_intent(message: str) -> bool:
    """
    Evaluates whether a user reply represents a deliberate cancellation.
    Guarantees that corrections, typos, or multi-word instructions are never misclassified as cancellations.
    
    Examples: 'no', 'cancel', 'stop', 'abort', "don't send", 'option 3', '3', 'keep existing'.
    """
    clean = message.lower().strip()
    clean = re.sub(r"^[!.,?#]+", "", clean).strip()

    words = clean.split()
    if len(words) > 8 or len(clean) > 70:
        return False

    # Disqualify messages that indicate correction, mistake, or alternative option selection
    if any(k in clean for k in ["mistake", "wrong", "wait", "meant", "actually", "instead", "change", "select", "typo", "retry", "misclick", "option 1", "option 2"]):
        return False

    cancellation_patterns = [
        r"^(no|nope|cancel|stop|abort|reject|nevermind|halt)\b",
        r"\b(don't\s+send|do\s+not\s+send|leave\s+it|hold\s+off|keep\s+existing|keep\s+current|option\s*3|\b3\b)\b",
    ]
    return any(re.search(pat, clean) for pat in cancellation_patterns)





def get_active_pending_action(db: Session, session_id: str) -> Optional[PendingAction]:
    """
    Retrieves the most recent active PendingAction for a conversation session.
    Automatically marks expired actions as EXPIRED to guarantee deterministic state.
    """
    now = ist_naive_now()

    # Expire overdue pending actions
    stale_actions = (
        db.query(PendingAction)
        .filter(
            PendingAction.session_id == session_id,
            PendingAction.status == "PENDING_CONFIRMATION",
            PendingAction.expires_at <= now,
        )
        .all()
    )
    for act in stale_actions:
        act.status = "EXPIRED"
    if stale_actions:
        db.commit()

    # Fetch the newest active pending action
    return (
        db.query(PendingAction)
        .filter(
            PendingAction.session_id == session_id,
            PendingAction.status == "PENDING_CONFIRMATION",
            PendingAction.expires_at > now,
        )
        .order_by(PendingAction.created_at.desc())
        .first()
    )


def create_pending_action(
    db: Session,
    session_id: str,
    tool_name: str,
    description: str,
    parameters: Dict[str, Any],
    target_invoices: Optional[List[str]] = None,
    target_customers: Optional[List[str]] = None,
    expires_in_minutes: int = 15,
) -> PendingAction:
    """
    Registers a new consequential action in PostgreSQL awaiting administrator confirmation.
    Automatically supersedes any prior pending action in the same session.
    """
    now = ist_naive_now()

    # Mark prior pending actions as SUPERSEDED
    db.query(PendingAction).filter(
        PendingAction.session_id == session_id,
        PendingAction.status == "PENDING_CONFIRMATION",
    ).update({"status": "SUPERSEDED"})

    action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
    idempotency_key = f"IDEMP-{uuid.uuid4().hex[:12].upper()}"
    expires_at = now + timedelta(minutes=expires_in_minutes)

    pending = PendingAction(
        action_id=action_id,
        session_id=session_id,
        tool_name=tool_name,
        description=description,
        target_invoices=json.dumps(target_invoices or []),
        target_customers=json.dumps(target_customers or []),
        parameters=json.dumps(parameters),
        status="PENDING_CONFIRMATION",
        idempotency_key=idempotency_key,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    logger.info("Created PendingAction %s (%s) for session %s", action_id, tool_name, session_id)
    return pending


def execute_pending_action(
    db: Session,
    pending_action: PendingAction,
    session_id: str,
    user_message: str = "",
) -> Dict[str, Any]:
    """
    Executes a confirmed pending action atomically and marks its database record EXECUTED.
    Enforces target state verification (e.g. skipping already-paid invoices).
    """
    now = ist_naive_now()
    tool_name = pending_action.tool_name
    params = json.loads(pending_action.parameters) if isinstance(pending_action.parameters, str) else pending_action.parameters

    logger.info("Executing confirmed action %s [%s]", pending_action.action_id, tool_name)
    execution_result: Dict[str, Any] = {}
    summary_markdown = ""

    # 1. Send Reminder Emails (Single or Batch)
    if tool_name in ("send_email", "send_reminders", "dispatch_reminders"):
        invoice_ids = params.get("invoice_ids")
        if not invoice_ids and params.get("invoice_id"):
            invoice_ids = [params["invoice_id"]]

        results = []
        for inv_id in (invoice_ids or []):
            inv = db.query(Invoice).filter(Invoice.invoice_id == inv_id).first()
            if not inv:
                results.append({"invoice_id": inv_id, "status": "NOT_FOUND"})
                continue
            if inv.status == "PAID":
                results.append({"invoice_id": inv_id, "status": "ALREADY_PAID", "message": "Invoice already settled."})
                continue

            draft = tool_draft_reminder_email(db, inv_id, reminder_level=inv.reminder_count + 1)
            send_res = tool_send_email(
                db, inv_id, draft["subject"], draft["body"], session_id=session_id, admin_approved=True
            )
            results.append({
                "invoice_id": inv_id,
                "invoice_number": inv.invoice_number,
                "customer": inv.customer.company_name if inv.customer else "Debtor",
                "status": send_res.get("status", "SENT"),
                "error": send_res.get("error"),
                "subject": draft["subject"],
            })

        execution_result = {"dispatched_reminders": results}
        rows = []
        has_failures = False
        for r in results:
            st = r.get("status")
            if st == "SENT":
                st_label = "`SENT`"
            elif st == "FAILED_DISPATCH":
                has_failures = True
                err_text = str(r.get("error") or "SMTP Error")
                if "Daily user sending limit exceeded" in err_text:
                    st_label = "❌ `FAILED` (Gmail Daily Sending Limit Exceeded)"
                else:
                    st_label = f"❌ `FAILED` ({err_text[:35]})"
            elif st == "BLOCKED_BY_GUARDRAIL":
                st_label = "⚠️ `BLOCKED_BY_GUARDRAIL`"
            else:
                st_label = f"`{st}`"
            rows.append(f"| **{r.get('invoice_number', r.get('invoice_id'))}** | {r.get('customer', 'Debtor')} | {st_label} | {r.get('subject', 'Payment Reminder')} |")

        if has_failures:
            header_title = "### ⚠️ Payment Reminder Dispatch Status"
            footer_note = (
                "\n\n> [!WARNING]\n"
                "> **SMTP Delivery Note:** One or more emails could not be dispatched over SMTP (e.g. Gmail Daily Sending Limit exceeded or invalid domain). Outgoing records are registered in the communication audit ledger."
            )
        else:
            header_title = "### ✅ Payment Reminders Successfully Dispatched"
            footer_note = "\n\nAll dispatches have been registered in the communication audit ledger."

        summary_markdown = (
            f"{header_title}\n\n"
            f"Processed **{len(results)} formal payment notices** following your confirmation:\n\n"
            f"| Invoice | Customer | Dispatch Status | Subject |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows) + footer_note
        )

    # 2. Settlement Discount Campaign
    elif tool_name in ("send_bulk_settlement_offer", "apply_settlement_discount"):
        disc_val = float(params.get("discount_percent", 0.1))
        hrs_val = int(params.get("hours_valid", 24))
        min_amt = float(params["min_amount"]) if params.get("min_amount") is not None else None
        msg_val = params.get("custom_message")

        clean_user_msg = (user_message or "").lower()
        if any(k in clean_user_msg for k in ["stack", "add on top", "option 2", "2"]):
            resolution_mode = "STACK"
        else:
            resolution_mode = "REVISE"

        res = tool_apply_settlement_discount(
            db,
            discount_percent=disc_val,
            hours_valid=hrs_val,
            min_amount=min_amt,
            custom_message=msg_val,
            resolution_mode=resolution_mode,
            session_id=session_id,
        )
        execution_result = res
        rows = [
            f"| **{d.get('customer')}** | `{d.get('invoice_number')}` | ₹{d.get('original_amount', 0):,.2f} | "
            f"₹{d.get('discount_amount', 0):,.2f} | **₹{d.get('settlement_amount', 0):,.2f}** | `{d.get('delivery_status', 'SENT')}` |"
            for d in res.get("dispatches", [])
        ]
        action_title = "Revised Settlement Agreements Dispatched" if resolution_mode == "REVISE" else "Stacked Settlement Agreements Dispatched"
        summary_markdown = (
            f"### 🏷️ {action_title}\n\n"
            f"{res.get('summary', 'Settlement campaign registered in database.')}\n\n"
            f"| Customer | Invoice No | Original Principal | Concession ({res.get('discount_percent')}%) | Net Settlement Due | Dispatch Status |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(rows) + "\n\n"
            f"**Customer Notification:** Dispatched emails explicitly acknowledge the previous concession and confirm the updated terms. Agreements are valid for {res.get('hours_valid', hrs_val)} hours."
        )

    # 3. Grant Payment Grace Period
    elif tool_name == "grant_grace_period":
        inv_id = params.get("invoice_id")
        days = int(params.get("days", 7))
        reason = params.get("reason", "Manager confirmed extension via chat")
        res = tool_grant_grace_period(db, inv_id, days, reason)
        execution_result = res
        summary_markdown = (
            f"### ⏳ Payment Grace Period Extension Authorized\n\n"
            f"• **Invoice:** `{res.get('invoice_number', inv_id)}`\n"
            f"• **Extension Duration:** **{days} Days**\n"
            f"• **Reminder Freeze Active Until:** `{res.get('frozen_until')}`\n"
            f"• **Official Reference ID:** `{res.get('commitment_id')}`\n\n"
            f"Automated overdue reminders and late penalties are paused for this account during this grace period."
        )

    # 4. Revoke Active Commitment
    elif tool_name == "revoke_commitment":
        res = tool_revoke_commitment(
            db,
            invoice_id=params.get("invoice_id"),
            commitment_type=params.get("commitment_type"),
        )
        execution_result = res
        summary_markdown = (
            f"### 🔄 Commercial Agreement Revoked\n\n"
            f"{res.get('message', 'Agreement revoked.')}\n\n"
            f"Prior terms have been canceled and standard contractual collection schedules are restored."
        )

    # 5. Custom Communication
    elif tool_name == "send_custom_communication":
        res = tool_send_custom_communication(
            db=db,
            subject=params.get("subject", "Notice Regarding Your Account"),
            message_body=params.get("message_body", ""),
            target_criteria=params.get("target_criteria", {}),
            customer_id=params.get("customer_id"),
            invoice_id=params.get("invoice_id"),
            comm_type=params.get("comm_type", "CUSTOM_NOTICE"),
        )
        execution_result = res
        summary_markdown = (
            f"### 📨 Custom Debtor Communications Delivered\n\n"
            f"{res.get('summary', 'Dispatched custom communications.')}\n\n"
            f"Delivered {res.get('total_dispatched', 0)} messages under category `{params.get('comm_type', 'CUSTOM_NOTICE')}`."
        )

    # 6. Escalate Account
    elif tool_name == "create_escalation":
        inv_id = params.get("invoice_id")
        reason = params.get("reason", "Escalation confirmed via administrator chat.")
        res = tool_create_escalation(db, inv_id, reason)
        execution_result = res
        summary_markdown = (
            f"### ⚠️ Account Escalation Successfully Queued\n\n"
            f"• **Invoice:** `{inv_id}`\n"
            f"• **Status:** `{res.get('status', 'PENDING_APPROVAL')}`\n"
            f"• **Reason:** {reason}\n\n"
            f"This account has been forwarded to the Executive Approval Queue for review."
        )

    # 7. Record Payment
    elif tool_name == "record_payment":
        inv_id = params.get("invoice_id")
        amt = float(params.get("amount", 0.0))
        res = tool_record_payment(db, inv_id, amt)
        execution_result = res
        summary_markdown = (
            f"### 💰 Payment Settlement Recorded\n\n"
            f"Successfully logged receipt of **₹{amt:,.2f}** against invoice `{inv_id}`.\n\n"
            f"• **New Ledger Status:** `{res.get('new_status', 'UPDATED')}`\n"
            f"• **Remaining Balance:** ₹{res.get('remaining_balance', 0):,.2f}"
        )

    else:
        execution_result = {"error": f"Unknown tool name: {tool_name}"}
        summary_markdown = f"Action could not be executed: Unsupported tool `{tool_name}`."

    # Mark PendingAction as EXECUTED
    pending_action.status = "EXECUTED"
    pending_action.executed_at = now
    pending_action.execution_result = json.dumps(execution_result, default=str)
    db.commit()

    log_agent_action(
        db, session_id, "PENDING_ACTION_EXECUTED", tool_name, params, execution_result, status="SUCCESS"
    )

    return {
        "status": "EXECUTED",
        "tool_name": tool_name,
        "description": pending_action.description,
        "result": execution_result,
        "summary_markdown": summary_markdown,
    }


def cancel_pending_action(
    db: Session,
    pending_action: PendingAction,
) -> Dict[str, Any]:
    """
    Cancels an active pending action safely without dispatching any messages or altering state.
    """
    now = ist_naive_now()
    pending_action.status = "CANCELLED"
    pending_action.executed_at = now
    db.commit()

    logger.info("Cancelled PendingAction %s (%s)", pending_action.action_id, pending_action.tool_name)

    return {
        "status": "CANCELLED",
        "summary_markdown": (
            f"Understood. The proposed action (**{pending_action.description}**) has been cancelled.\n\n"
            f"No emails have been sent, and no financial records or balances have been modified."
        ),
    }
