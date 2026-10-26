"""
Autonomous Agent Orchestrator and ReAct Execution Engine.

Implements the multi-step reasoning loop (Understand -> Plan -> Tool Call ->
Guardrail Validation -> Backend Execution -> Observation -> Decision)
for both interactive administrator chat and autonomous batch runs.
"""

from datetime import datetime, date, timedelta
import uuid
import json
import re
import time
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import ist_naive_now
from app.core.guardrails import validate_agent_capability
from app.db.models import Invoice, Customer, AgentAction, Approval, ChatSession, ChatMessage, PendingAction
from app.services.agent_prompts import SYSTEM_PROMPT, generate_smart_title
from app.services.bedrock_service import bedrock_gateway, build_validated_bedrock_history
from app.services.action_state_machine import (
    get_active_pending_action,
    is_affirmative_intent,
    is_cancellation_intent,
    create_pending_action,
    execute_pending_action,
    cancel_pending_action,
)
from app.services.pending_action_resolver import resolve_pending_action_turn
from app.services.penalty_engine import (
    calculate_days_overdue,
    sync_invoice_financials,
    determine_recommended_action,
)
from app.services.tools import (
    tool_draft_reminder_email,
    tool_send_email,
    tool_create_escalation,
    log_agent_action,
)
from app.services.tool_dispatcher import dispatch_tool_call
from app.services.agent_response_formatter import (
    format_deterministic_tool_fallback,
    is_greeting,
    is_reminder_intent,
    is_user_inquiry,
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates tool execution, Bedrock LLM reasoning, and guardrail verification."""

    @staticmethod
    def process_chat(db: Session, message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes an interactive agent reasoning turn for natural-language administrator prompts.
        Loads previous turn history up to configured limits, measures execution latency,
        extracts chain-of-thought reasoning, and persists conversation turns in PostgreSQL.
        """
        start_time = time.perf_counter()

        if not session_id:
            session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"

        # 1. Resolve or create ChatSession in PostgreSQL with smart AI title
        chat_session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        smart_title = generate_smart_title(message)

        if not chat_session:
            chat_session = ChatSession(
                session_id=session_id,
                title=smart_title,
                created_at=ist_naive_now(),
                updated_at=ist_naive_now(),
            )
            db.add(chat_session)
            db.commit()
        elif chat_session.title in ("New Conversation", "Untitled"):
            chat_session.title = smart_title
            db.commit()

        # 2. Persist user turn in PostgreSQL
        user_msg = ChatMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            session_id=session_id,
            role="user",
            content=message,
            created_at=ist_naive_now(),
        )
        db.add(user_msg)
        db.commit()

        # Check if AI Agent operations are paused in Admin Settings
        from app.services.settings_service import is_agent_enabled
        if not is_agent_enabled(db):
            paused_msg = (
                "The AI Agent is currently paused by the administrator in Admin Settings. "
                "Autonomous reasoning and conversational database mutations are temporarily disabled.\n\n"
                "You can still inspect invoices, customer records, and approvals manually in the platform, "
                "or re-enable the Agent anytime from the Admin Settings page."
            )
            ai_msg = ChatMessage(
                message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
                session_id=session_id,
                role="ai",
                content=paused_msg,
                reasoning="AI Agent paused via Admin Settings. Operational actions suppressed.",
                execution_seconds=0.01,
                actions_taken=json.dumps([]),
                tool_calls="[]",
                created_at=ist_naive_now(),
            )
            db.add(ai_msg)
            chat_session.updated_at = ist_naive_now()
            db.commit()
            return {
                "reply": paused_msg,
                "session_id": session_id,
                "session_title": chat_session.title,
                "reasoning": "AI Agent paused in Admin Settings.",
                "execution_seconds": 0.01,
                "tool_calls": [],
                "actions_taken": [],
            }

        # 3. System Boundary Guardrail: Enforce capabilities, legal limits, and human safety
        is_capable, refusal_text = validate_agent_capability(message)
        if not is_capable:
            execution_seconds = round(time.perf_counter() - start_time, 2)
            ai_msg = ChatMessage(
                message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
                session_id=session_id,
                role="ai",
                content=refusal_text,
                reasoning="Request violates autonomous capabilities boundary, accounting compliance, or ethical policies.",
                execution_seconds=execution_seconds,
                actions_taken=json.dumps(["Capability guardrail triggered. Safe refusal dispatched."]),
                tool_calls="[]",
                created_at=ist_naive_now(),
            )
            db.add(ai_msg)
            chat_session.updated_at = ist_naive_now()
            db.commit()

            return {
                "reply": refusal_text,
                "session_id": session_id,
                "session_title": chat_session.title,
                "reasoning": ai_msg.reasoning,
                "execution_seconds": execution_seconds,
                "tool_calls": [],
                "actions_taken": ["Capability guardrail triggered."],
            }

        # 4. Multi-Turn Pending Action Resolution & Conversational State Machine
        resolved_turn = resolve_pending_action_turn(db, session_id, message)
        if resolved_turn and resolved_turn.get("handled"):
            execution_seconds = round(time.perf_counter() - start_time, 2)
            ai_msg = ChatMessage(
                message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
                session_id=session_id,
                role="ai",
                content=resolved_turn["reply"],
                reasoning=resolved_turn.get("reasoning", "Resolved state-bound action."),
                execution_seconds=execution_seconds,
                actions_taken=json.dumps(resolved_turn.get("actions_taken", [])),
                tool_calls=json.dumps([{
                    "name": t, "parameters": {}
                } for t in resolved_turn.get("tool_calls", [])]),
                created_at=ist_naive_now(),
            )
            db.add(ai_msg)
            chat_session.updated_at = ist_naive_now()
            db.commit()

            return {
                "reply": resolved_turn["reply"],
                "session_id": session_id,
                "session_title": chat_session.title,
                "reasoning": ai_msg.reasoning,
                "execution_seconds": execution_seconds,
                "tool_calls": resolved_turn.get("tool_calls", []),
                "actions_taken": resolved_turn.get("actions_taken", []),
            }

        # 6. Retrieve prior turns with schema-compliant Bedrock validation
        past_msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        formatted_messages = build_validated_bedrock_history(
            past_msgs=past_msgs,
            max_turns=settings.chat_max_history_turns,
            active_pending_action=None,
        )

        # 7. Invoke Bedrock AI Gateway (Turn 1: Natural tool calling without forced hallucination)
        initial_tool_choice = {"auto": {}}
        ai_response = bedrock_gateway.converse(
            messages=formatted_messages,
            system_prompt=SYSTEM_PROMPT,
            tool_choice=initial_tool_choice,
        )

        tool_calls = ai_response.get("tool_calls", [])
        actions_taken = []
        final_text = ai_response.get("text", "")
        reasoning = ai_response.get("reasoning", "")
        raw_tool_outputs = []

        # 8. Multi-Turn ReAct Tool Execution Loop (supports up to 2 iterations)
        current_ai = ai_response
        current_tools = tool_calls
        feedback_messages = list(formatted_messages)

        iteration = 0
        while current_tools and iteration < 2:
            iteration += 1
            iter_outputs = []
            for tc in current_tools:
                t_name = tc.get("name")
                t_input = tc.get("input", {})
                t_output, summary_msg = dispatch_tool_call(db, t_name, t_input, session_id=session_id)
                actions_taken.append(summary_msg)
                iter_outputs.append((tc, t_output))
                raw_tool_outputs.append((tc, t_output))

                # If user intended to review overdue accounts / dispatch reminders, create single-intent PendingAction
                if t_name == "get_overdue_invoices" and is_reminder_intent(message) and not is_user_inquiry(message):
                    invs = t_output.get("invoices", [])
                    if invs:
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

            # Register PendingAction if agent drafted reminder emails awaiting user confirmation
            drafted_ids = [
                tc.get("input", {}).get("invoice_id")
                for tc in current_tools
                if tc.get("name") == "draft_reminder_email" and tc.get("input", {}).get("invoice_id")
            ]
            if drafted_ids:
                create_pending_action(
                    db=db,
                    session_id=session_id,
                    tool_name="send_reminders",
                    description=f"Dispatch payment reminders to {len(drafted_ids)} accounts ({', '.join(drafted_ids)})",
                    parameters={"invoice_ids": drafted_ids},
                    target_invoices=drafted_ids,
                    expires_in_minutes=15,
                )

            # Build ReAct feedback
            if current_ai.get("raw_message"):
                try:
                    tool_results = [
                        {
                            "toolUseId": tc.get("tool_use_id", f"call_{i}"),
                            "content": [{"json": output}],
                            "status": "success",
                        }
                        for i, (tc, output) in enumerate(iter_outputs)
                    ]
                    feedback_messages.append(current_ai["raw_message"])
                    feedback_messages.append({
                        "role": "user",
                        "content": [{"toolResult": tr} for tr in tool_results],
                    })

                    next_ai = bedrock_gateway.converse(
                        messages=feedback_messages,
                        system_prompt=SYSTEM_PROMPT,
                    )
                    current_ai = next_ai
                    current_tools = next_ai.get("tool_calls", [])
                    if next_ai.get("text"):
                        final_text = next_ai["text"]
                    if next_ai.get("reasoning"):
                        reasoning = f"{reasoning}\n{next_ai['reasoning']}".strip() if reasoning else next_ai["reasoning"]
                except Exception as exc:
                    logger.warning("ReAct converse turn %d encountered an error: %s", iteration, exc)
                    break
            else:
                break

        # 8b. Proactive Action Interceptor: If LLM tutorializes or claims it cannot modify DB, query PostgreSQL directly
        refusal_keywords = [
            "can't directly modify",
            "cannot directly modify",
            "guide you through the process",
            "use the update_customer_profile tool",
            "use the record_payment tool",
            "here’s how you can update",
            "here's how you can update",
        ]
        if not raw_tool_outputs and any(kw in final_text.lower() for kw in refusal_keywords):
            from app.services.tools_crud import tool_list_customers
            from app.db.models import Invoice

            words = re.findall(r'[a-zA-Z0-9_\-]+', message)
            stop_words = {
                "update", "data", "and", "mark", "payment", "as", "paid", "record",
                "for", "the", "customer", "invoice", "please", "can", "you", "to",
                "all", "in", "of", "a", "an", "is", "this", "that", "set"
            }
            candidate_terms = [w for w in words if w.lower() not in stop_words and len(w) > 2]
            target_term = candidate_terms[0] if candidate_terms else message.strip()

            cust_lookup = tool_list_customers(db, search=target_term)
            matched_custs = cust_lookup.get("customers", [])

            if matched_custs:
                c = matched_custs[0]
                invs = db.query(Invoice).filter(Invoice.customer_id == c["customer_id"]).all()
                unpaid_invs = [inv for inv in invs if inv.status not in ["PAID", "CANCELLED"]]

                if unpaid_invs:
                    inv_list_str = ", ".join([f"`{inv.invoice_id}` (₹{inv.total_amount:,.2f})" for inv in unpaid_invs])
                    first_inv = unpaid_invs[0]
                    final_text = (
                        f"I inspected the database and located customer **{c['contact_name']}** (**{c['company_name']}**, `{c['customer_id']}`).\n\n"
                        f"- **Current Email:** `{c['email']}`\n"
                        f"- **Current Phone:** `{c['phone']}`\n"
                        f"- **Total Outstanding:** ₹{c['outstanding_balance']:,.2f}\n"
                        f"- **Unpaid Invoices:** {inv_list_str}\n\n"
                        f"**Next Steps:**\n"
                        f"1. What specific customer fields would you like me to update (e.g. email, phone, risk level)?\n"
                        f"2. Would you like me to record the full payment of ₹{first_inv.total_amount:,.2f} for invoice `{first_inv.invoice_id}` to mark it **PAID** now?"
                    )
                else:
                    final_text = (
                        f"I located customer **{c['contact_name']}** (**{c['company_name']}**, `{c['customer_id']}`).\n\n"
                        f"- **Current Email:** `{c['email']}`\n"
                        f"- **Current Phone:** `{c['phone']}`\n"
                        f"- **Outstanding Balance:** ₹0.00 (All invoices settled)\n\n"
                        f"What specific customer profile data would you like me to update?"
                    )
            else:
                final_text = (
                    f"I searched our customer database for **\"{target_term}\"** but found no matching customer records.\n\n"
                    f"- Would you like me to onboard **{target_term}** as a new debtor using `create_customer`?\n"
                    f"- Or would you like to search under a different registered company name or Customer ID?"
                )

        # 9. Guaranteed Rich Markdown Formatter (when AI response is minimal or robotic)
        if not final_text or final_text.startswith("I have completed the requested operations"):
            for tc, output in raw_tool_outputs:
                t_name = tc.get("name")
                formatted_fallback = format_deterministic_tool_fallback(
                    tool_name=t_name,
                    output=output,
                    user_message=message,
                    session_id=session_id,
                    db=db,
                )
                if formatted_fallback:
                    final_text = formatted_fallback
                    break

        # Ensure single-intent confirmation question is present if a PendingAction was registered
        if is_reminder_intent(message) and not is_user_inquiry(message):
            for tc, output in raw_tool_outputs:
                if tc.get("name") == "get_overdue_invoices":
                    invs = output.get("invoices", [])
                    if invs and "reply **'yes'**" not in final_text.lower() and "reply 'yes'" not in final_text.lower():
                        final_text += f"\n\n**Action Confirmation:** Would you like me to dispatch payment reminders to these {len(invs)} accounts now? Reply **'Yes'** to execute or **'No'** to cancel."
                    break

        # Eliminate any LLM bracketed placeholders from chat presentation
        if final_text:
            final_text = re.sub(r"\[(?:Your\s+)?(?:Company\s+Name|Business\s+Name|Organization)\]", "ReceivIQ", final_text, flags=re.IGNORECASE)
            final_text = re.sub(r"\[(?:Your\s+)?(?:Name|Sender(?:\s+Name)?|User)\]", "Accounts Receivable Team", final_text, flags=re.IGNORECASE)
            final_text = re.sub(r"\[(?:Your\s+)?(?:Title|Position|Role)\]", "ReceivIQ Credit Team", final_text, flags=re.IGNORECASE)

        execution_seconds = round(time.perf_counter() - start_time, 2)
        if not reasoning:
            reasoning = "Evaluated administrator instruction against enterprise credit rules. Synced database state and synthesized structured visual presentation."

        # 10. Persist AI message in PostgreSQL
        all_executed_tool_calls = [tc for tc, _ in raw_tool_outputs]
        ai_msg = ChatMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            session_id=session_id,
            role="ai",
            content=final_text,
            reasoning=reasoning,
            execution_seconds=execution_seconds,
            actions_taken=json.dumps(actions_taken),
            tool_calls=json.dumps(all_executed_tool_calls),
            created_at=ist_naive_now(),
        )
        db.add(ai_msg)
        chat_session.updated_at = ist_naive_now()
        db.commit()

        return {
            "reply": final_text,
            "session_id": session_id,
            "session_title": chat_session.title,
            "reasoning": reasoning,
            "execution_seconds": execution_seconds,
            "tool_calls": all_executed_tool_calls,
            "actions_taken": actions_taken,
        }

    @staticmethod
    def run_autonomous_workflow(db: Session, session_id: str = "session-auto") -> Dict[str, Any]:
        """
        Executes Mode A: Autonomous periodic collection batch run ("Run Agent Now").
        Scans all pending and overdue invoices, evaluates deterministic business rules,
        dispatches reminders, and creates human approval items for high-value cases.
        Delegated to autonomous_workflow_engine.py for modularity and maintainability.
        """
        from app.services.autonomous_workflow_engine import execute_autonomous_collection_cycle
        return execute_autonomous_collection_cycle(db, session_id=session_id)

