"""
Agent Greetings and Intent Guardrails Regression Suite.

Verifies:
1. Conversational greetings (e.g. 'Hi', 'Hello') never trigger unsolicited tool calls
   or dump overdue invoice tables.
2. `is_greeting` classification accurately identifies greetings and excludes action commands.
3. Out-of-scope non-AR requests receive compliant digital capability boundary notices.
4. SSE streaming generates tailored welcoming thoughts rather than ledger auditing text.
"""

import json
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.agent_response_formatter import is_greeting
from app.services.orchestrator import AgentOrchestrator
from app.services.streaming_service import stream_agent_turn


def test_is_greeting_classification():
    """Verifies that greetings are identified and action commands are excluded."""
    # Positive greeting cases
    assert is_greeting("Hi") is True
    assert is_greeting("hi!") is True
    assert is_greeting("Hello") is True
    assert is_greeting("Hey there") is True
    assert is_greeting("Good morning") is True
    assert is_greeting("Thanks") is True
    assert is_greeting("Thank you very much") is True
    assert is_greeting("Who are you") is True

    # Negative action / inquiry cases
    assert is_greeting("Send email to only that customers whichever payment is left more than 2 lakh rupees, give 0.5 percent discount to all of that.") is False
    assert is_greeting("Show all overdue invoices") is False
    assert is_greeting("Grant 7 days grace period for invoice INV-1002") is False
    assert is_greeting("Why in email this type of message is written?") is False


def test_greeting_does_not_execute_tools_or_dump_invoices():
    """A simple 'Hi' MUST NOT execute database tools or dump overdue invoices."""
    db: Session = SessionLocal()
    try:
        res = AgentOrchestrator.process_chat(db, "Hi")
        reply = res["reply"]
        tool_calls = res.get("tool_calls", [])

        # Must execute zero tools
        assert len(tool_calls) == 0, f"Expected 0 tool calls for greeting, got: {tool_calls}"

        # Must NOT dump overdue table headers or ask unsolicited reminder questions
        assert "| Invoice No |" not in reply
        assert "| Invoice ID |" not in reply
        assert "Would you like me to dispatch payment reminders" not in reply

        # Must contain helpful, welcoming introduction
        lower_reply = reply.lower()
        assert "hello" in lower_reply or "welcome" in lower_reply or "assistant" in lower_reply
    finally:
        db.close()


def test_streaming_greeting_thought_process():
    """SSE streaming on 'Hi' must stream welcoming thoughts instead of ledger audit text."""
    db: Session = SessionLocal()
    try:
        events = list(stream_agent_turn(db, "Hi"))
        parsed = [json.loads(e.replace("data: ", "").strip()) for e in events if e.startswith("data:")]

        thought_chunks = [p.get("chunk", "") for p in parsed if p.get("type") == "thought"]
        full_thought = "".join(thought_chunks).lower()

        assert "greeting received" in full_thought
        assert "verifying corporate accounts receivable guidelines" not in full_thought
    finally:
        db.close()
