"""
Automated Integration and Regression Tests for Custom Communications & Conversational Confirmations.

Verifies:
1. 'please send happy diwali email to only "ABC" customer' is NOT misclassified as an affirmative confirmation.
2. 'please send happy diwali greetings email to only "ABC" customer' is passed directly to the reasoning engine.
3. Affirmative confirmation ('yes') following an assistant proposal question is passed to the LLM.
4. tool_send_custom_communication with status='ACTIVE' matches all active customers directly.
5. tool_send_custom_communication with company_name='ABC' targets only the matching customer.
"""

import uuid
import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Customer, ChatSession, ChatMessage
from app.services.action_state_machine import is_affirmative_intent
from app.services.pending_action_resolver import resolve_pending_action_turn
from app.services.communication_tools import tool_send_custom_communication
from app.services.orchestrator import AgentOrchestrator


def test_please_send_greetings_not_misclassified_as_confirmation():
    """Verifies that 'please send...' instruction prompts are never treated as confirmation replies."""
    prompt1 = 'please send happy diwali email to only "ABC" customer'
    prompt2 = 'please send happy diwali greetings email to only "ABC" customer'

    assert is_affirmative_intent(prompt1) is False
    assert is_affirmative_intent(prompt2) is False

    db: Session = SessionLocal()
    session_id = f"TEST-SES-{uuid.uuid4().hex[:6].upper()}"
    try:
        # Create session
        chat_sess = ChatSession(session_id=session_id, title="Test Greetings")
        db.add(chat_sess)
        db.commit()

        # Must not be intercepted as isolated confirmation
        resolved = resolve_pending_action_turn(db, session_id, prompt1)
        assert resolved is None

        resolved2 = resolve_pending_action_turn(db, session_id, prompt2)
        assert resolved2 is None
    finally:
        db.close()


def test_conversational_confirmation_after_assistant_question():
    """Verifies that replying 'yes' after the assistant asks a question is not intercepted with a canned error."""
    db: Session = SessionLocal()
    session_id = f"TEST-SES-{uuid.uuid4().hex[:6].upper()}"
    try:
        chat_sess = ChatSession(session_id=session_id, title="Test Conversational Confirm")
        db.add(chat_sess)
        db.commit()

        # Simulate assistant asking a confirmation question
        ai_msg = ChatMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            session_id=session_id,
            role="ai",
            content="There are 49 active customers in the database. Would you like to proceed with sending the Diwali greetings to all active customers?",
        )
        db.add(ai_msg)
        db.commit()

        # User replies 'yes'
        resolved = resolve_pending_action_turn(db, session_id, "yes")
        # Must return None so Bedrock / LLM receives the affirmative confirmation in conversation context
        assert resolved is None
    finally:
        db.close()


def test_custom_communication_broadcast_active_customers():
    """Verifies that tool_send_custom_communication with status='ACTIVE' matches active customers."""
    from unittest.mock import patch
    db: Session = SessionLocal()
    try:
        with patch("app.services.communication_tools.EmailService.send_customer_email", return_value={"status": "SENT"}):
            res = tool_send_custom_communication(
                db=db,
                subject="Important Announcement from ReceivIQ",
                message_body="Dear {customer_name}, An update for {company_name}.",
                target_criteria={"status": "ACTIVE"},
                comm_type="announcement",
            )
            assert res["status"] == "SUCCESS"
            assert res["total_dispatched"] > 0
            assert len(res["dispatches"]) == res["total_dispatched"]
            first_dispatch = res["dispatches"][0]
            assert "customer" in first_dispatch
            assert "recipient" in first_dispatch
    finally:
        db.close()


def test_custom_communication_targets_specific_customer():
    """Verifies that tool_send_custom_communication with company_name targets only that customer."""
    from unittest.mock import patch
    db: Session = SessionLocal()
    try:
        cust = db.query(Customer).filter(Customer.status == "ACTIVE").first()
        assert cust is not None

        with patch("app.services.communication_tools.EmailService.send_customer_email", return_value={"status": "SENT"}):
            res = tool_send_custom_communication(
                db=db,
                subject="Special Message",
                message_body="Dear {customer_name}, Greetings to {company_name}!",
                target_criteria={"company_name": cust.company_name},
                comm_type="custom_communication",
            )
            assert res["status"] == "SUCCESS"
            assert res["total_dispatched"] >= 1
            for d in res["dispatches"]:
                assert cust.company_name.lower() in d["customer"].lower()
    finally:
        db.close()


def test_drafted_reminder_emails_create_pending_action_and_execute_on_confirm():
    """
    Verifies that when reminder emails are drafted in a chat session, a PendingAction
    is automatically created, and replying 'okay sent it' immediately executes real email dispatch.
    """
    from unittest.mock import patch
    from app.db.models import Invoice, PendingAction
    from app.services.action_state_machine import get_active_pending_action

    db: Session = SessionLocal()
    session_id = f"TEST-SES-{uuid.uuid4().hex[:6].upper()}"
    try:
        # Create session
        chat_sess = ChatSession(session_id=session_id, title="Test Draft Confirmation")
        db.add(chat_sess)
        db.commit()

        inv = db.query(Invoice).filter(Invoice.status.in_(["PENDING", "OVERDUE"])).first()
        assert inv is not None, "Need at least one invoice for testing"

        # Mock Converse so Bedrock issues a draft_reminder_email tool call
        fake_ai_call = {
            "text": "I have drafted the reminder email for your review.",
            "tool_calls": [
                {
                    "tool_use_id": "call_draft_1",
                    "name": "draft_reminder_email",
                    "input": {"invoice_id": inv.invoice_id, "reminder_level": 1},
                }
            ],
            "raw_message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "call_draft_1",
                            "name": "draft_reminder_email",
                            "input": {"invoice_id": inv.invoice_id, "reminder_level": 1},
                        }
                    }
                ],
            },
        }

        with patch("app.services.orchestrator.bedrock_gateway.converse", side_effect=[
            fake_ai_call,
            {"text": "Here is the draft email. Would you like me to send it?", "tool_calls": [], "raw_message": None},
        ]):
            resp1 = AgentOrchestrator.process_chat(db, f"Draft reminder for {inv.invoice_id}", session_id=session_id)
            assert "draft" in resp1["reply"].lower() or "reminder" in resp1["reply"].lower()

        # Verify PendingAction was automatically registered in PostgreSQL
        pending = get_active_pending_action(db, session_id)
        assert pending is not None, "PendingAction should be registered for drafted emails"
        assert pending.status == "PENDING_CONFIRMATION"
        assert inv.invoice_id in pending.target_invoices

        # Now simulate user confirming with 'okay sent it'
        with patch("app.services.email_service.EmailService.send_customer_email", return_value={"status": "DELIVERED"}) as mock_send:
            resp2 = AgentOrchestrator.process_chat(db, "okay sent it", session_id=session_id)
            assert "dispatched" in resp2["reply"].lower() or "successfully" in resp2["reply"].lower()
            assert mock_send.called

        # PendingAction status must be EXECUTED
        db.refresh(pending)
        assert pending.status == "EXECUTED"
    finally:
        db.close()
