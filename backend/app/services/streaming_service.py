"""
Real-Time Agent Streaming and Thought Engine.

Provides Server-Sent Events (SSE) streaming for interactive agent turns.
Streams live chain-of-thought reasoning, intermediate tool execution statuses,
boundary validation guardrails, and token-by-token visual Markdown responses to the frontend.
Integrates with TurnManager for background execution and multi-session tab persistence.
"""

from datetime import datetime
import json
import re
import time
import uuid
import logging
from typing import AsyncGenerator, Dict, Any, Optional, Generator, Callable
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import ist_start_of_day, ist_naive_now
from app.core.guardrails import validate_agent_capability
from app.db.models import ChatSession, ChatMessage, AgentAction, PendingAction
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
from app.services.tool_dispatcher import dispatch_tool_call
from app.services.agent_response_formatter import (
    format_deterministic_tool_fallback,
    is_greeting,
    is_reminder_intent,
    is_user_inquiry,
)
from app.services.turn_manager import agent_turn_manager

logger = logging.getLogger(__name__)


def sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """Encodes an event payload into standard SSE wire format."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, default=str)}\n\n"


def compute_credits(db: Session, session_id: Optional[str] = None) -> Dict[str, int]:
    """
    Computes remaining prompt allowance checking BOTH session limit and daily limit.
    Enforces whichever is lower to prevent excessive token context accumulation.
    """
    today_start = ist_start_of_day()
    daily_used = (
        db.query(ChatMessage)
        .filter(ChatMessage.role == "user", ChatMessage.created_at >= today_start)
        .count()
    )
    daily_credits_left = max(0, settings.chat_daily_credits - daily_used)

    session_used = 0
    if session_id:
        session_used = (
            db.query(ChatMessage)
            .filter(ChatMessage.role == "user", ChatMessage.session_id == session_id)
            .count()
        )
    session_credits_left = max(0, settings.chat_session_credits - session_used)
    effective_credits_left = min(daily_credits_left, session_credits_left)

    return {
        "daily_credits": settings.chat_daily_credits,
        "session_credits": settings.chat_session_credits,
        "daily_credits_left": daily_credits_left,
        "session_credits_left": session_credits_left,
        "credits_left": effective_credits_left,
    }


def execute_agent_turn_pipeline(
    db: Session,
    message: str,
    session_id: str,
    on_event: Callable[[str, Dict[str, Any]], None],
) -> None:
    """
    Autonomous pipeline executing the complete multi-turn agent ReAct loop.
    Emits granular progress events to the TurnState and guarantees transactional
    persistence of both user and AI messages in PostgreSQL.
    """
    start_time = time.perf_counter()

    # 1. Resolve or create ChatSession in PostgreSQL with smart title
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

    on_event("session_info", {
        "session_id": session_id,
        "session_title": chat_session.title,
    })

    # 2. Persist user turn in PostgreSQL if not already saved
    existing_user_msg = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.role == "user", ChatMessage.content == message)
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if not existing_user_msg:
        user_msg = ChatMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            session_id=session_id,
            role="user",
            content=message,
            created_at=ist_naive_now(),
        )
        db.add(user_msg)
        chat_session.updated_at = ist_naive_now()
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
        execution_seconds = round(time.perf_counter() - start_time, 2)
        on_event("thought", {"chunk": "Operational check: AI Agent is disabled in Admin Settings.\n"})
        on_event("status", {"message": "AI Agent is currently paused in Admin Settings."})
        on_event("content", {"chunk": paused_msg})
        ai_msg = ChatMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            session_id=session_id,
            role="ai",
            content=paused_msg,
            reasoning="AI Agent paused via Admin Settings. Operational actions suppressed.",
            execution_seconds=execution_seconds,
            actions_taken=json.dumps([]),
            tool_calls="[]",
            created_at=ist_naive_now(),
        )
        db.add(ai_msg)
        chat_session.updated_at = ist_naive_now()
        db.commit()
        credit_info = compute_credits(db, session_id)
        on_event("done", {
            "execution_seconds": execution_seconds,
            "actions_taken": [],
            "session_id": session_id,
            "session_title": chat_session.title,
            **credit_info,
        })
        return

    # 3. System Boundary Guardrail: Enforce capabilities, legal limits, and human safety
    is_capable, refusal_text = validate_agent_capability(message)
    if not is_capable:
        execution_seconds = round(time.perf_counter() - start_time, 2)
        on_event("thought", {"chunk": "Evaluating request against ethical boundaries, physical limitations, and accounting compliance...\n"})
        on_event("status", {"message": "Capabilities boundary check: Out-of-scope request detected."})
        on_event("content", {"chunk": refusal_text})

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

        credit_info = compute_credits(db, session_id)
        on_event("done", {
            "execution_seconds": execution_seconds,
            "actions_taken": ["Capability guardrail triggered."],
            "session_id": session_id,
            "session_title": chat_session.title,
            **credit_info,
        })
        return

    # 4. Multi-Turn Pending Action Resolution & Conversational State Machine
    resolved_turn = resolve_pending_action_turn(db, session_id, message)
    if resolved_turn and resolved_turn.get("handled"):
        execution_seconds = round(time.perf_counter() - start_time, 2)
        on_event("thought", {"chunk": f"{resolved_turn.get('reasoning', 'Action resolved.')}\n"})
        for word in resolved_turn["reply"].split(" "):
            on_event("content", {"chunk": word + " "})
            time.sleep(0.01)

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

        credit_info = compute_credits(db, session_id)
        on_event("done", {
            "execution_seconds": execution_seconds,
            "actions_taken": resolved_turn.get("actions_taken", []),
            "session_id": session_id,
            "session_title": chat_session.title,
            **credit_info,
        })
        return

    # 5. Retrieve prior turns with schema-compliant Bedrock validation
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

    if is_greeting(message):
        initial_thought = "Greeting received. Preparing executive introduction and accounts receivable operational capabilities overview."
        status_msg = "Connecting with Accounts Receivable Intelligence Assistant..."
    elif is_user_inquiry(message):
        initial_thought = (
            f"Analyzing informational inquiry: \"{message[:60]}...\"\n"
            f"Consulting accounts receivable operating guidelines and ledger policies."
        )
        status_msg = "Synthesizing credit policy and operational guidance..."
    else:
        initial_thought = (
            f"Analyzing administrator instruction: \"{message[:60]}...\"\n"
            f"Verifying corporate accounts receivable guidelines, credit terms, and live database state."
        )
        status_msg = "Evaluating credit policy and selecting operational tools..."

    on_event("thought", {"chunk": initial_thought + "\n"})

    # 6. Invoke Bedrock Converse (Turn 1: Natural tool selection without forced hallucination)
    on_event("status", {"message": status_msg})
    initial_tool_choice = {"auto": {}}
    ai_response = bedrock_gateway.converse(
        messages=formatted_messages,
        system_prompt=SYSTEM_PROMPT,
        tool_choice=initial_tool_choice,
    )

    tool_calls = ai_response.get("tool_calls", [])
    model_reasoning = ai_response.get("reasoning", "")
    actions_taken = []
    raw_tool_outputs = []
    final_text = ai_response.get("text", "")

    if model_reasoning:
        on_event("thought", {"chunk": f"\nPolicy Evaluation: {model_reasoning}\n"})

    # 7. Execute tools with live status events and multi-turn ReAct
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
            on_event("status", {"message": f"Executing system action: {t_name.replace('_', ' ').title()}..."})

            t_output, summary_msg = dispatch_tool_call(db, t_name, t_input, session_id=session_id)
            actions_taken.append(summary_msg)
            on_event("thought", {"chunk": f"{summary_msg}\n"})
            iter_outputs.append((tc, t_output))
            raw_tool_outputs.append((tc, t_output))

            # Register single-intent PendingAction if user intended to review overdue accounts / send reminders
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

        # ReAct feedback pass to formulate synthesized response
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
                    on_event("thought", {"chunk": f"{next_ai['reasoning']}\n"})
                    model_reasoning = f"{model_reasoning}\n{next_ai['reasoning']}".strip() if model_reasoning else next_ai["reasoning"]
            except Exception as exc:
                logger.warning("Streaming ReAct converse turn %d encountered an error: %s", iteration, exc)
                break
        else:
            break

    # 8. Guaranteed Rich Markdown Fallback if brief or robotic
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

    if not final_text:
        final_text = ai_response.get("text") or "Operation evaluated and synchronized with accounts receivable records."

    # Eliminate any LLM bracketed placeholders from chat presentation
    final_text = re.sub(r"\[(?:Your\s+)?(?:Company\s+Name|Business\s+Name|Organization)\]", "ReceivIQ", final_text, flags=re.IGNORECASE)
    final_text = re.sub(r"\[(?:Your\s+)?(?:Name|Sender(?:\s+Name)?|User)\]", "Accounts Receivable Team", final_text, flags=re.IGNORECASE)
    final_text = re.sub(r"\[(?:Your\s+)?(?:Title|Position|Role)\]", "ReceivIQ Credit Team", final_text, flags=re.IGNORECASE)

    # 9. Stream the final response with natural token cadence
    if len(final_text) > 800 or "|" in final_text:
        # Stream markdown tables line-by-line for fast, responsive rendering
        lines = final_text.split("\n")
        for line in lines:
            on_event("content", {"chunk": line + "\n"})
            time.sleep(0.003)
    else:
        words = final_text.split(" ")
        for i in range(0, len(words), 4):
            chunk = " ".join(words[i : i + 4]) + (" " if i + 4 < len(words) else "")
            on_event("content", {"chunk": chunk})
            time.sleep(0.01)

    execution_seconds = round(time.perf_counter() - start_time, 2)

    # 10. Persist AI message in PostgreSQL
    all_executed_tool_calls = [tc for tc, _ in raw_tool_outputs]
    ai_msg = ChatMessage(
        message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
        session_id=session_id,
        role="ai",
        content=final_text,
        reasoning=model_reasoning or "Synthesized database records into structured presentation.",
        execution_seconds=execution_seconds,
        actions_taken=json.dumps(actions_taken),
        tool_calls=json.dumps(all_executed_tool_calls),
        created_at=ist_naive_now(),
    )
    db.add(ai_msg)
    chat_session.updated_at = ist_naive_now()
    db.commit()

    credit_info = compute_credits(db, session_id)
    on_event("done", {
        "execution_seconds": execution_seconds,
        "actions_taken": actions_taken,
        "session_id": session_id,
        "session_title": chat_session.title,
        **credit_info,
    })


def stream_agent_turn(
    db: Session, message: str, session_id: Optional[str] = None
) -> Generator[str, None, None]:
    """
    Generator SSE streaming runner for FastAPI StreamingResponse.
    Delegates to agent_turn_manager to ensure server-side background execution
    and client reconnection resilience.
    """
    if not session_id:
        session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"

    return agent_turn_manager.stream_events(
        session_id=session_id,
        message=message,
        run_pipeline_fn=execute_agent_turn_pipeline,
    )
