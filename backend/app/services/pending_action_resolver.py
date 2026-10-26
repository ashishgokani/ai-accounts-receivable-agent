"""
Pending Action Conversational Turn Resolver.

Provides robust, conversational resolution of multi-turn pending actions for the
Autonomous Accounts Receivable Agent. Handles:
1. Valid option selections (Option 1: Revise, Option 2: Stack, Option 3: Cancel).
2. Out-of-range option inputs (e.g. '4', '5', '0') without killing the pending action.
3. User mistake/correction statements (e.g. 'no i have by mistake selected wrong option').
4. Resurrecting recently superseded/cancelled actions if user expresses an accidental input.
5. Inquiries and questions about pending actions without premature action cancellation.
"""

from datetime import timedelta
import json
import logging
import re
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.models import PendingAction
from app.services.action_state_machine import (
    get_active_pending_action,
    execute_pending_action,
    cancel_pending_action,
    is_affirmative_intent,
    is_cancellation_intent,
)

logger = logging.getLogger(__name__)


def is_correction_or_reselect_intent(message: str) -> bool:
    """
    Evaluates whether the user indicates they made a mistake, selected the wrong option,
    or wishes to re-select an option from the previous decision.
    """
    clean = message.lower().strip()
    clean = re.sub(r"^[!.,?#]+", "", clean).strip()

    correction_signals = [
        "mistake", "wrong option", "selected wrong", "wrong choice", "typo",
        "misclick", "let me choose", "choose again", "re-select", "reselect",
        "change option", "change my option", "change choice", "i meant",
        "actually option", "actually 1", "actually 2", "actually 3",
        "actually revise", "actually stack", "wait", "my mistake",
    ]
    return any(sig in clean for sig in correction_signals)


def extract_invalid_option_number(message: str) -> Optional[int]:
    """
    Checks if the user typed an invalid option number like '4', '5', 'option 4', '0'.
    """
    clean = message.lower().strip()
    clean = re.sub(r"^[!.,?#]+", "", clean).strip()
    match = re.match(r"^(?:option\s*)?([0-9]+)$", clean)
    if match:
        num = int(match.group(1))
        if num not in (1, 2, 3):
            return num
    return None


def extract_option_choice(message: str) -> Optional[str]:
    """
    Extracts an explicit option choice (Option 1: Revise, Option 2: Stack, Option 3: Cancel).
    Guarantees percentage specifications (e.g. '1%', '1 percent discount') are NOT falsely matched as option 1.
    """
    clean = message.lower().strip()
    clean = re.sub(r"^[!.,?#]+", "", clean).strip()

    is_pure_1 = bool(re.match(r"^(?:option\s*)?1$", clean))
    has_opt1 = is_pure_1 or bool(re.search(r"\b(option\s*1|revise|upgrade)\b", clean))

    is_pure_2 = bool(re.match(r"^(?:option\s*)?2$", clean))
    has_opt2 = is_pure_2 or bool(re.search(r"\b(option\s*2|stack|add\s*on\s*top)\b", clean))

    is_pure_3 = bool(re.match(r"^(?:option\s*)?3$", clean))
    has_opt3 = is_pure_3 or bool(re.search(r"\b(option\s*3|cancel|keep\s*existing)\b", clean))

    if has_opt1 and not has_opt2 and not has_opt3:
        return "REVISE"
    if has_opt2 and not has_opt1 and not has_opt3:
        return "STACK"
    if has_opt3 and not has_opt1 and not has_opt2:
        return "CANCEL"
    return None


def format_invalid_option_reply(pending_action: PendingAction, chosen_number: int) -> str:
    """Formats a helpful response when an unrecognized option number is submitted."""
    params = json.loads(pending_action.parameters) if isinstance(pending_action.parameters, str) else (pending_action.parameters or {})
    disc = params.get("discount_percent", 0.1)
    return (
        f"### ⚠️ Invalid Option Selected\n\n"
        f"You selected **Option {chosen_number}**, but only **Options 1, 2, and 3** are available for this settlement agreement:\n\n"
        f"1. **Option 1 (Revise & Upgrade):** Supersede earlier concession with the new **{disc}%** discount (customer email explicitly notes the revision).\n"
        f"2. **Option 2 (Stack Concession):** Add **+{disc}%** on top of the existing concession.\n"
        f"3. **Option 3 (Cancel):** Keep current agreements active (zero emails sent).\n\n"
        f"👉 **Please reply with \"1\" (Revise), \"2\" (Stack), or \"3\" (Cancel).**"
    )


def format_reselect_options_reply(pending_action: PendingAction) -> str:
    """Formats an encouraging re-selection response when user indicates they made a mistake."""
    params = json.loads(pending_action.parameters) if isinstance(pending_action.parameters, str) else (pending_action.parameters or {})
    disc = params.get("discount_percent", 0.1)
    return (
        f"### 🔄 Let's Re-evaluate Your Selection\n\n"
        f"No problem at all! Your request for the **{disc}% early settlement discount** is on hold awaiting your choice:\n\n"
        f"1. **Option 1 (Revise & Upgrade):** Supersede earlier concession with the new **{disc}%** discount (customer email explicitly notes the revision).\n"
        f"2. **Option 2 (Stack Concession):** Add **+{disc}%** on top of the existing concession.\n"
        f"3. **Option 3 (Cancel):** Keep current agreements active (zero emails sent).\n\n"
        f"👉 **Which option would you like to proceed with? Reply \"1\", \"2\", or \"3\".**"
    )


def get_recent_pending_action(db: Session, session_id: str, within_minutes: int = 15) -> Optional[PendingAction]:
    """
    Retrieves the most recent PendingAction in the session within the last N minutes,
    regardless of status, allowing recovery if user made an accidental input.
    """
    cutoff = ist_naive_now() - timedelta(minutes=within_minutes)
    return (
        db.query(PendingAction)
        .filter(
            PendingAction.session_id == session_id,
            PendingAction.created_at >= cutoff,
        )
        .order_by(PendingAction.created_at.desc())
        .first()
    )


def resolve_pending_action_turn(
    db: Session,
    session_id: str,
    message: str,
) -> Optional[Dict[str, Any]]:
    """
    Resolves a conversational turn against the PendingAction state machine.
    
    Returns:
        Optional[Dict[str, Any]]: If handled, returns a dict with 'reply', 'reasoning',
        'actions_taken', 'tool_calls', and 'execution_result'. If unhandled, returns None.
    """
    active_pending = get_active_pending_action(db, session_id)

    # --- Case 1: Active Pending Action Exists ---
    if active_pending:
        # 1A. Invalid numeric option (e.g. '4', '5', 'option 4')
        invalid_opt = extract_invalid_option_number(message)
        if invalid_opt is not None:
            return {
                "handled": True,
                "reply": format_invalid_option_reply(active_pending, invalid_opt),
                "reasoning": f"User entered option {invalid_opt}, but only options 1, 2, or 3 are valid. Prompted for clarification while keeping pending action active.",
                "actions_taken": ["Invalid option prompted; pending action kept active."],
                "tool_calls": [],
            }

        # 1B. Direct option selection (e.g. '1', '2', '3', 'revise', 'stack', 'cancel')
        chosen_opt = extract_option_choice(message)
        if chosen_opt == "REVISE":
            res = execute_pending_action(db, active_pending, session_id, user_message=message)
            return {
                "handled": True,
                "reply": res["summary_markdown"],
                "reasoning": f"Administrator selected Option 1 (Revise & Upgrade): {active_pending.description}.",
                "actions_taken": [f"Executed: {active_pending.description}"],
                "tool_calls": [active_pending.tool_name],
            }
        elif chosen_opt == "STACK":
            res = execute_pending_action(db, active_pending, session_id, user_message=message)
            return {
                "handled": True,
                "reply": res["summary_markdown"],
                "reasoning": f"Administrator selected Option 2 (Stack Concession): {active_pending.description}.",
                "actions_taken": [f"Executed: {active_pending.description}"],
                "tool_calls": [active_pending.tool_name],
            }
        elif chosen_opt == "CANCEL":
            res = cancel_pending_action(db, active_pending)
            return {
                "handled": True,
                "reply": res["summary_markdown"],
                "reasoning": "Administrator selected Option 3 (Cancel). No actions dispatched.",
                "actions_taken": ["Pending action cancelled."],
                "tool_calls": [],
            }

        # 1C. User indicates mistake or re-selection without explicit choice
        if is_correction_or_reselect_intent(message):
            return {
                "handled": True,
                "reply": format_reselect_options_reply(active_pending),
                "reasoning": "User expressed correction or mistake. Re-displayed valid choices without state mutation.",
                "actions_taken": ["Re-displayed options for user correction."],
                "tool_calls": [],
            }

        # 1C. Affirmative confirmation
        if is_affirmative_intent(message):
            res = execute_pending_action(db, active_pending, session_id, user_message=message)
            return {
                "handled": True,
                "reply": res["summary_markdown"],
                "reasoning": f"Confirmed by administrator. Executed state-bound action: {active_pending.description}.",
                "actions_taken": [f"Executed: {active_pending.description}"],
                "tool_calls": [active_pending.tool_name],
            }

        # 1D. Cancellation
        if is_cancellation_intent(message):
            res = cancel_pending_action(db, active_pending)
            return {
                "handled": True,
                "reply": res["summary_markdown"],
                "reasoning": "Administrator explicitly cancelled pending action. No state was mutated.",
                "actions_taken": ["Pending action cancelled."],
                "tool_calls": [],
            }

        # 1E. Inquiry / Question vs New Command
        clean_msg = message.lower().strip()
        is_question = any(q in clean_msg for q in ["what", "why", "how", "who", "which", "explain", "tell me", "mean", "?"])
        if not is_question:
            active_pending.status = "SUPERSEDED"
            db.commit()

        return None

    # --- Case 2: No Active Pending Action Currently ---
    # 2A. User expresses a mistake or wants to re-select after accidental cancellation or supersede
    if is_correction_or_reselect_intent(message):
        recent = get_recent_pending_action(db, session_id, within_minutes=15)
        if recent:
            recent.status = "PENDING_CONFIRMATION"
            recent.expires_at = ist_naive_now() + timedelta(minutes=15)
            db.commit()

            chosen = extract_option_choice(message)
            if chosen == "REVISE":
                res = execute_pending_action(db, recent, session_id, user_message="revise")
                return {
                    "handled": True,
                    "reply": res["summary_markdown"],
                    "reasoning": f"Re-activated and executed revision: {recent.description}.",
                    "actions_taken": [f"Executed: {recent.description}"],
                    "tool_calls": [recent.tool_name],
                }
            elif chosen == "STACK":
                res = execute_pending_action(db, recent, session_id, user_message="stack")
                return {
                    "handled": True,
                    "reply": res["summary_markdown"],
                    "reasoning": f"Re-activated and executed stacking: {recent.description}.",
                    "actions_taken": [f"Executed: {recent.description}"],
                    "tool_calls": [recent.tool_name],
                }
            elif chosen == "CANCEL":
                res = cancel_pending_action(db, recent)
                return {
                    "handled": True,
                    "reply": res["summary_markdown"],
                    "reasoning": "Re-activated and confirmed cancellation.",
                    "actions_taken": ["Pending action cancelled."],
                    "tool_calls": [],
                }
            else:
                return {
                    "handled": True,
                    "reply": format_reselect_options_reply(recent),
                    "reasoning": "Re-activated recent pending action and presented choices following user mistake report.",
                    "actions_taken": ["Restored pending action for option re-selection."],
                    "tool_calls": [],
                }

    # 2B. Isolated affirmative with no pending action
    if is_affirmative_intent(message):
        clean_msg = message.lower().strip()
        clean_msg = re.sub(r"^[!.,?#]+", "", clean_msg).strip()
        words = clean_msg.split()

        # If this message has directives or multiple words (e.g. "please send...", "send email..."),
        # it is an operational instruction, NEVER an isolated affirmation. Pass straight to LLM!
        is_bare_affirmative = clean_msg in (
            "yes", "yep", "yeah", "yup", "sure", "ok", "okay", "confirm", "proceed",
            "approved", "go ahead", "do it", "send it", "please proceed", "please do so",
        )
        if not is_bare_affirmative and len(words) > 2:
            return None

        from app.db.models import ChatMessage
        last_ai_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "ai")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if last_ai_msg and last_ai_msg.content:
            ai_text = last_ai_msg.content.strip().lower()
            is_prompting_action = (
                "?" in ai_text
                or any(phrase in ai_text for phrase in [
                    "would you like", "should i", "shall i", "do you want me to",
                    "proceed with", "ready to proceed", "confirm if", "confirm to",
                    "reply yes", "say yes", "let me know if you would like",
                ])
            )
            if is_prompting_action:
                # Conversational turn: Pass to LLM so it executes the confirmed proposal
                return None

        return {
            "handled": True,
            "reply": (
                "I received your confirmation, but there is currently no active action awaiting approval in this thread.\n\n"
                "Please specify what you would like me to do (e.g. *'Show overdue invoices'* or *'Apply 0.1% settlement discount'*)."
            ),
            "reasoning": "Affirmative intent detected with no active PendingAction in PostgreSQL. Prompted clarification.",
            "actions_taken": [],
            "tool_calls": [],
        }

    # 2C. Isolated cancellation with no pending action
    if is_cancellation_intent(message):
        from app.db.models import ChatMessage
        last_ai_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "ai")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if last_ai_msg and last_ai_msg.content:
            ai_text = last_ai_msg.content.strip().lower()
            is_prompting_action = (
                "?" in ai_text
                or any(phrase in ai_text for phrase in [
                    "would you like", "should i", "shall i", "do you want me to",
                    "proceed with", "ready to proceed", "confirm if", "confirm to",
                ])
            )
            if is_prompting_action:
                # Conversational turn: Pass to LLM so it responds politely to user cancellation
                return None

        return {
            "handled": True,
            "reply": "Understood. No actions were pending confirmation, and no changes have been made to your accounts receivable records.",
            "reasoning": "Cancellation intent received with no pending action active. Confirmed clean state.",
            "actions_taken": [],
            "tool_calls": [],
        }

    return None
