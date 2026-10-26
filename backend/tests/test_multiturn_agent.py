"""
Multi-Turn Context & State-Bound Commitment Engine Regression Suite.

Verifies the 14 critical scenarios for multi-turn Agent Chat:
1. Bedrock Converse history slicing (never starts with assistant).
2. Strict role alternation (merges consecutive identical roles).
3. Two-turn confirmation flow (listing overdue -> 'yes' executes reminders).
4. Two-turn cancellation flow (listing overdue -> 'no' cancels safely).
5. Fail-closed safety for isolated 'yes' without pending action.
6. Fail-closed safety for isolated 'no' without pending action.
7. State-bound settlement discount persistence in PostgreSQL.
8. State-bound grace period extension and invoice freeze.
9. Commitment revocation and contractual terms restoration.
10. Background scheduler reminder pause awareness.
11. Automated commitment expiry detection.
12. Capability boundary: Physical courier refusal.
13. Capability boundary: WhatsApp / Telephony refusal.
14. Capability boundary: Financial ledger deletion refusal.
"""

from datetime import datetime, date, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Invoice, Customer, ChatSession, ChatMessage, PendingAction, InvoiceCommitment
from app.core.timezone import ist_naive_now
from app.core.guardrails import validate_agent_capability
from app.services.agent_prompts import SYSTEM_PROMPT
from app.services.bedrock_service import build_validated_bedrock_history
from app.services.action_state_machine import (
    get_active_pending_action,
    create_pending_action,
    execute_pending_action,
    cancel_pending_action,
    is_affirmative_intent,
    is_cancellation_intent,
)
from app.services.commitments_service import (
    tool_apply_settlement_discount,
    tool_grant_grace_period,
    tool_revoke_commitment,
    has_active_hold_or_pause,
    expire_stale_commitments,
)
from app.services.orchestrator import AgentOrchestrator

client = TestClient(app)


# --- Scenario 1 & 2: Bedrock Converse History Validation ---

def test_history_slicing_drops_leading_assistant():
    """Scenario 1: Slicing must drop leading assistant turns to avoid Bedrock HTTP 400."""
    now = ist_naive_now()
    m1 = ChatMessage(message_id="M1", session_id="S1", role="assistant", content="Hello!", created_at=now)
    m2 = ChatMessage(message_id="M2", session_id="S1", role="user", content="Show invoices", created_at=now)
    m3 = ChatMessage(message_id="M3", session_id="S1", role="assistant", content="Here they are", created_at=now)

    history = build_validated_bedrock_history([m1, m2, m3], max_turns=10)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"][0]["text"] == "Show invoices"
    assert history[1]["role"] == "assistant"


def test_history_merges_adjacent_identical_roles():
    """Scenario 2: Consecutive identical roles must be merged into a single turn."""
    now = ist_naive_now()
    m1 = ChatMessage(message_id="M1", session_id="S1", role="user", content="Part 1", created_at=now)
    m2 = ChatMessage(message_id="M2", session_id="S1", role="user", content="Part 2", created_at=now)
    m3 = ChatMessage(message_id="M3", session_id="S1", role="assistant", content="Reply", created_at=now)

    history = build_validated_bedrock_history([m1, m2, m3], max_turns=10)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert "Part 1\n\nPart 2" in history[0]["content"][0]["text"]
    assert history[1]["role"] == "assistant"


# --- Scenario 3 & 4: Multi-Turn Confirmation & Cancellation ---

def test_multiturn_confirmation_flow():
    """Scenario 3: Listing overdue invoices followed by 'yes' executes pending action."""
    db: Session = SessionLocal()
    session_id = f"TEST-SES-{uuid.uuid4().hex[:6].upper()}"
    try:
        # Step 1: Prompt overdue invoices
        resp1 = AgentOrchestrator.process_chat(db, "Show overdue invoices", session_id=session_id)
        assert "overdue" in resp1["reply"].lower() or "invoices" in resp1["reply"].lower()

        pending = get_active_pending_action(db, session_id)
        assert pending is not None
        assert pending.status == "PENDING_CONFIRMATION"

        # Step 2: Affirmative confirmation
        resp2 = AgentOrchestrator.process_chat(db, "Yes, please proceed", session_id=session_id)
        assert "dispatched" in resp2["reply"].lower() or "reminders" in resp2["reply"].lower()

        db.refresh(pending)
        assert pending.status == "EXECUTED"
        assert pending.executed_at is not None
    finally:
        db.close()


def test_multiturn_cancellation_flow():
    """Scenario 4: Listing overdue invoices followed by 'no' cancels safely without emails."""
    db: Session = SessionLocal()
    session_id = f"TEST-SES-{uuid.uuid4().hex[:6].upper()}"
    try:
        # Step 1: Prompt overdue invoices
        AgentOrchestrator.process_chat(db, "Show overdue invoices", session_id=session_id)
        pending = get_active_pending_action(db, session_id)
        assert pending is not None
        assert pending.status == "PENDING_CONFIRMATION"

        # Step 2: Explicit cancellation
        resp = AgentOrchestrator.process_chat(db, "No, do not send", session_id=session_id)
        assert "cancelled" in resp["reply"].lower()

        db.refresh(pending)
        assert pending.status == "CANCELLED"
    finally:
        db.close()


# --- Scenario 5 & 6: Fail-Closed Ambiguous Inputs ---

def test_fail_closed_isolated_yes_without_pending():
    """Scenario 5: Isolated 'yes' without an active pending action prompts for clarification."""
    db: Session = SessionLocal()
    session_id = f"TEST-SES-{uuid.uuid4().hex[:6].upper()}"
    try:
        resp = AgentOrchestrator.process_chat(db, "yes", session_id=session_id)
        assert "no active action awaiting approval" in resp["reply"]
    finally:
        db.close()


def test_fail_closed_isolated_cancel_without_pending():
    """Scenario 6: Isolated 'cancel' without an active pending action safely acknowledges."""
    db: Session = SessionLocal()
    session_id = f"TEST-SES-{uuid.uuid4().hex[:6].upper()}"
    try:
        resp = AgentOrchestrator.process_chat(db, "cancel", session_id=session_id)
        assert "no actions were pending" in resp["reply"].lower() or "cancelled" in resp["reply"].lower()
    finally:
        db.close()


# --- Scenario 7, 8, 9: State-Bound Commercial Commitments ---

def test_state_bound_commitment_discount_creation():
    """Scenario 7: Applying settlement discount persists commitments and binds scheduler deadline."""
    db: Session = SessionLocal()
    try:
        db.query(InvoiceCommitment).filter(InvoiceCommitment.commitment_type == "EARLY_SETTLEMENT_DISCOUNT").delete()
        db.commit()
        res = tool_apply_settlement_discount(db, discount_percent=0.1, hours_valid=24)
        assert res["status"] in ("SUCCESS", "NO_UNSETTLED_ACCOUNTS")
        if res["status"] == "SUCCESS":
            assert res["total_sent"] > 0
            # Verify database record exists
            first_comm = db.query(InvoiceCommitment).filter(
                InvoiceCommitment.commitment_type == "EARLY_SETTLEMENT_DISCOUNT",
                InvoiceCommitment.status == "ACTIVE"
            ).first()
            assert first_comm is not None
            assert first_comm.valid_until is not None
    finally:
        db.close()


def test_state_bound_grace_period():
    """Scenario 8: Granting grace period creates commitment and updates invoice next_action_at."""
    db: Session = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.status.in_(["PENDING", "OVERDUE"])).first()
        if inv:
            res = tool_grant_grace_period(db, invoice_id=inv.invoice_id, days=7, reason="Testing extension")
            assert res["status"] == "SUCCESS"
            assert res["days_granted"] == 7

            db.refresh(inv)
            assert inv.next_action_at is not None

            # Verify active commitment
            comm = db.query(InvoiceCommitment).filter(
                InvoiceCommitment.invoice_id == inv.invoice_id,
                InvoiceCommitment.commitment_type == "GRACE_PERIOD_PAUSE",
                InvoiceCommitment.status == "ACTIVE"
            ).first()
            assert comm is not None
    finally:
        db.close()


def test_commitment_revocation():
    """Scenario 9: Revoking commitment restores contractual terms and resets next_action_at."""
    db: Session = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.status.in_(["PENDING", "OVERDUE"])).first()
        if inv:
            # Grant grace period first
            tool_grant_grace_period(db, invoice_id=inv.invoice_id, days=5)
            assert has_active_hold_or_pause(db, inv.invoice_id) is True

            # Revoke commitment
            res = tool_revoke_commitment(db, invoice_id=inv.invoice_id)
            assert res["status"] == "SUCCESS"
            assert has_active_hold_or_pause(db, inv.invoice_id) is False

            db.refresh(inv)
            assert inv.next_action_at is None
    finally:
        db.close()


# --- Scenario 10 & 11: Automation Scheduler Awareness & Expiry ---

def test_scheduler_pauses_reminders_on_active_commitment():
    """Scenario 10: Scheduler helper recognizes active commitments to pause reminders."""
    db: Session = SessionLocal()
    try:
        inv = db.query(Invoice).first()
        if inv:
            # When commitment active
            tool_grant_grace_period(db, invoice_id=inv.invoice_id, days=10)
            assert has_active_hold_or_pause(db, inv.invoice_id) is True

            # When revoked
            tool_revoke_commitment(db, invoice_id=inv.invoice_id)
            assert has_active_hold_or_pause(db, inv.invoice_id) is False
    finally:
        db.close()


def test_scheduler_commitment_auto_expiration():
    """Scenario 11: Stale commitments past valid_until are automatically marked EXPIRED."""
    db: Session = SessionLocal()
    try:
        inv = db.query(Invoice).first()
        if inv:
            expired_comm = InvoiceCommitment(
                commitment_id=f"COM-EXP-{uuid.uuid4().hex[:6].upper()}",
                invoice_id=inv.invoice_id,
                customer_id=inv.customer_id,
                commitment_type="EARLY_SETTLEMENT_DISCOUNT",
                description="Past Discount Offer",
                parameters="{}",
                status="ACTIVE",
                created_at=ist_naive_now() - timedelta(days=2),
                valid_until=ist_naive_now() - timedelta(hours=1),
            )
            db.add(expired_comm)
            db.commit()

            expired_count = expire_stale_commitments(db)
            assert expired_count >= 1

            db.refresh(expired_comm)
            assert expired_comm.status == "EXPIRED"
    finally:
        db.close()


# --- Scenario 12, 13, 14: System Capability Boundary Guardrails ---

def test_capability_guardrail_physical_courier():
    """Scenario 12: In-person or physical courier requests trigger polite software capability refusal."""
    is_capable, refusal = validate_agent_capability("Send a physical courier to their office to collect the check")
    assert is_capable is False
    assert "Currently, I do not have the capability to dispatch physical couriers" in refusal
    assert "Recommended Alternative" in refusal


def test_capability_guardrail_whatsapp_telephony():
    """Scenario 13: Unsupported SMS/WhatsApp requests trigger communication channel boundary refusal."""
    is_capable, refusal = validate_agent_capability("Send a WhatsApp message and call their phone immediately")
    assert is_capable is False
    assert "telephony, SMS, or WhatsApp gateway connected" in refusal
    assert "Recommended Alternative" in refusal


def test_capability_guardrail_ledger_wiping():
    """Scenario 14: Ledger destruction requests trigger GAAP/IFRS financial integrity refusal."""
    is_capable, refusal = validate_agent_capability("Delete all invoices and wipe transaction history from the database")
    assert is_capable is False
    assert "Corporate accounting standards (GAAP/IFRS) strictly prohibit deleting" in refusal
    assert "Recommended Alternative" in refusal


def test_full_send_instruction_not_misclassified_as_confirmation():
    """Scenario 15: Full imperative prompt starting with 'Send email to...' is NOT misclassified as a short confirmation."""
    prompt = (
        "Send email to only that customers whichever payment is left more than 2 lakh rupees, "
        "give 0.1 percent discount to all of that , And make sure the email should be with professional design with proper css, "
        "not simple only text, Design a professional mail and send it ,"
    )
    # 1. Affirmative intent must be strictly False
    assert is_affirmative_intent(prompt) is False

    # 2. Executing through Orchestrator must NOT return the false-positive refusal
    db: Session = SessionLocal()
    session_id = f"TEST-2LAKH-{uuid.uuid4().hex[:6].upper()}"
    try:
        resp = AgentOrchestrator.process_chat(db, prompt, session_id=session_id)
        assert "no active action awaiting approval" not in resp["reply"]
        assert any(k in resp["reply"].lower() for k in ["overdue", "discount", "settlement", "invoice", "account", "option", "concession", "agreement", "customer"])
    finally:
        db.close()


def test_inquiry_does_not_hijack_with_reminders():
    """Scenario 16: An inquiry/explanation request must NOT create PendingAction or hijack with payment reminders."""
    db: Session = SessionLocal()
    session_id = f"TEST-INQ-{uuid.uuid4().hex[:6].upper()}"
    try:
        inquiry_prompt = (
            "but why earlier i has sent 0.5 percent discount and now you have sent 0.1 percent discount, "
            "why both discount email sent with original invoice amount?"
        )
        resp = AgentOrchestrator.process_chat(db, inquiry_prompt, session_id=session_id)

        # 1. Must NOT create a PendingAction to send reminders
        pending = get_active_pending_action(db, session_id)
        assert pending is None, "Inquiry question must not register an active PendingAction!"

        # 2. Must NOT hijack with the overdue reminder dispatch confirmation
        reply = resp["reply"]
        assert "would you like me to dispatch payment reminders" not in reply.lower(), (
            "Inquiry response was hijacked by overdue reminder breakdown!"
        )

        # 3. Must address discount or invoice mechanics
        assert any(k in reply.lower() for k in ["discount", "amount", "percent", "invoice", "original", "settlement"])
    finally:
        db.close()


def test_audit_tools_query_communications_and_commitments():
    """Scenario 17: Verifies get_communication_history and get_invoice_commitments audit tools."""
    from app.services.tools_history import tool_get_communication_history, tool_get_invoice_commitments

    db: Session = SessionLocal()
    try:
        comms = tool_get_communication_history(db, limit=5)
        assert "communications" in comms
        assert "total_found" in comms
        assert isinstance(comms["communications"], list)

        commitments = tool_get_invoice_commitments(db, limit=5)
        assert "commitments" in commitments
        assert "total_found" in commitments
        assert isinstance(commitments["commitments"], list)
    finally:
        db.close()


def test_capability_guardrail_unauthorized_auto_debit():
    """Scenario 18: Direct auto-debit / bank withdrawal triggers voluntary payment boundary refusal."""
    is_capable, refusal = validate_agent_capability("Directly auto-debit their bank account for ₹50,000")
    assert is_capable is False
    assert "authority over customer bank accounts" in refusal
    assert "Recommended Alternative" in refusal


def test_capability_guardrail_arbitrary_invoice_alteration():
    """Scenario 19: Arbitrary invoice modification triggers tax compliance and immutability refusal."""
    is_capable, refusal = validate_agent_capability("Change invoice amount to ₹10 for INV-2026-1004")
    assert is_capable is False
    assert "tax compliance (GST/VAT) and audit rules" in refusal
    assert "Recommended Alternative" in refusal


def test_discount_commitment_anti_duplication_and_superseding():
    """Scenario 20: Anti-duplication conflict gate pauses when active commitments exist, and REVISE supersedes older offer."""
    from app.services.commitments_service import tool_apply_settlement_discount
    db: Session = SessionLocal()
    try:
        # Reset any pre-existing settlement commitments to isolate test
        db.query(InvoiceCommitment).filter(InvoiceCommitment.commitment_type == "EARLY_SETTLEMENT_DISCOUNT").delete()
        inv_1004 = db.query(Invoice).filter(Invoice.invoice_id == "INV-1004").first()
        if inv_1004:
            inv_1004.status = "OVERDUE"
            inv_1004.amount = 250000.0
            inv_1004.total_amount = 255000.0
        db.commit()

        # Run 1: Apply 0.1% discount with min_amount 200,000
        res1 = tool_apply_settlement_discount(db, discount_percent=0.1, hours_valid=24, min_amount=200000.0)
        assert res1["status"] == "SUCCESS"
        assert len(res1["dispatches"]) >= 1

        # Run 2: Immediately re-request 0.5% discount without resolution mode -> Conflict gate triggers (zero emails sent)
        res2 = tool_apply_settlement_discount(db, discount_percent=0.5, hours_valid=24, min_amount=200000.0)
        assert res2["status"] == "CONFLICT_ACTIVE_COMMITMENTS_DETECTED"
        assert res2["requires_user_decision"] is True
        assert len(res2["active_conflicts"]) >= 1

        # Run 3: Confirmed revision -> resolution_mode="REVISE" supersedes old 0.1% and delivers updated emails
        res3 = tool_apply_settlement_discount(
            db, discount_percent=0.5, hours_valid=24, min_amount=200000.0, resolution_mode="REVISE"
        )
        assert res3["status"] == "SUCCESS"
        for d in res3["dispatches"]:
            assert d["delivery_status"] != "SKIPPED_DUPLICATE"

        # Check DB that the old 0.1% commitments are now marked SUPERSEDED
        for d in res3["dispatches"]:
            inv_num = d["invoice_number"]
            inv = db.query(Invoice).filter(Invoice.invoice_number == inv_num).first()
            if inv:
                old_comms = db.query(InvoiceCommitment).filter(
                    InvoiceCommitment.invoice_id == inv.invoice_id,
                    InvoiceCommitment.status == "SUPERSEDED"
                ).all()
                assert len(old_comms) >= 1
    finally:
        db.close()


def test_multiturn_settlement_conflict_and_resolution_flow():
    """Scenario 21: Full multi-turn chat gate pausing for conflict and executing revision."""
    db: Session = SessionLocal()
    session_id = f"TEST-CONFLICT-{uuid.uuid4().hex[:6].upper()}"
    try:
        # Reset commitments and ensure qualifying unsettled invoice
        db.query(InvoiceCommitment).filter(InvoiceCommitment.commitment_type == "EARLY_SETTLEMENT_DISCOUNT").delete()
        inv_1004 = db.query(Invoice).filter(Invoice.invoice_id == "INV-1004").first()
        if inv_1004:
            inv_1004.status = "OVERDUE"
            inv_1004.amount = 250000.0
            inv_1004.total_amount = 255000.0
        db.commit()
        db.expire_all()

        # Step 1: Initial discount creation
        tool_apply_settlement_discount(db, discount_percent=0.1, hours_valid=24, min_amount=200000.0)

        # Step 2: In chat, user requests a new 0.5% discount on accounts > 2 lakh
        # When active commitments exist, tool returns CONFLICT_ACTIVE_COMMITMENTS_DETECTED and pending action is created
        res2 = AgentOrchestrator.process_chat(
            db,
            "Send email to only that customers whichever payment is left more than 2 lakh rupees, give 0.5 percent discount to all of that.",
            session_id=session_id
        )
        assert "conflict" in res2["reply"].lower() or "active" in res2["reply"].lower() or "option" in res2["reply"].lower()

        pending = get_active_pending_action(db, session_id)
        assert pending is not None
        assert pending.status == "PENDING_CONFIRMATION"

        # Step 2B: User types invalid option number '4'
        res2b = AgentOrchestrator.process_chat(db, "4", session_id=session_id)
        assert "invalid option" in res2b["reply"].lower() or "option 4" in res2b["reply"].lower()
        # Verify pending action is kept ACTIVE in PostgreSQL
        assert get_active_pending_action(db, session_id) is not None

        # Step 2C: User sends conversational mistake correction
        res2c = AgentOrchestrator.process_chat(db, "no i have by mistake selected wrong option", session_id=session_id)
        assert "re-evaluate" in res2c["reply"].lower() or "option" in res2c["reply"].lower()
        assert get_active_pending_action(db, session_id) is not None

        # Step 3: User replies with valid option '1' to execute revision
        res3 = AgentOrchestrator.process_chat(
            db,
            "1",
            session_id=session_id
        )
        assert "revised" in res3["reply"].lower() or "dispatched" in res3["reply"].lower() or "0.5" in res3["reply"]

        # Pending action should now be EXECUTED
        assert pending.status == "EXECUTED"
    finally:
        db.close()


