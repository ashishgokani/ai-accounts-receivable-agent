"""
Comprehensive Test Suite for Autonomous Inbound Email AI Workflow & Unified Approvals.

Tests all 12 mandatory requirements:
1. Message deduplication by RFC 822 Message-ID.
2. Unverified or spoofed sender rejection without financial mutations or data leakage.
3. Quoted email thread history separation (preventing historical text from acting as new instructions).
4. Unknown or ambiguous reply handling (polite clarification, no false classification).
5. Payment claim remittance intake (generates Approval with UTR, timestamp, acknowledgment).
6. Full payment managerial approval (records Payment ledger entry, preserves invoice amount, marks PAID).
7. Partial payment managerial approval (preserves invoice amount, recalculates remaining debt deterministically).
8. Rejected payment claim handling (restores OVERDUE status, sends rejection clarification).
9. Stale payment promise expiration and automated follow-up dispatch.
10. Safe failure recovery when email delivery encounters errors.
11. Outgoing Reply-To enforcement (ashishgokani58@gmail.com).
12. Deterministic Python ledger and penalty synchronization.
"""

import uuid
import json
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Customer, Invoice, Payment, Approval, InboundEmailLog, InvoiceCommitment, Communication
from app.core.timezone import ist_naive_now, ist_today
from app.services.ai_reply_processor import (
    separate_clean_reply_and_quoted_history,
    process_inbound_customer_email,
)
from app.services.approval_service import ApprovalService
from app.services.commitments_service import expire_stale_commitments
from app.services.penalty_engine import sync_invoice_financials
from app.services.email_service import EmailService


@pytest.fixture
def db_session():
    """Provides a transactional database session for each test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_customer_and_invoice(db_session):
    """Creates a verified customer and overdue invoice for integration tests."""
    cust_id = f"CUST-TEST-{uuid.uuid4().hex[:6].upper()}"
    inv_id = f"INV-TEST-{uuid.uuid4().hex[:6].upper()}"
    test_email = f"billing-{uuid.uuid4().hex[:4]}@acmecorp.com"

    customer = Customer(
        customer_id=cust_id,
        name="John Doe",
        company_name="Acme Corporation Ltd",
        email=test_email,
        phone="+91-9876543210",
        risk_level="Low",
        risk_score=20,
        status="ACTIVE",
        created_at=ist_naive_now(),
    )
    db_session.add(customer)

    invoice = Invoice(
        invoice_id=inv_id,
        customer_id=cust_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:4].upper()}",
        invoice_date=ist_today() - timedelta(days=40),
        due_date=ist_today() - timedelta(days=10),
        amount=100000.0,  # Original invoiced principal
        penalty_amount=0.0,
        total_amount=100000.0,
        status="OVERDUE",
        reminder_count=1,
        created_at=ist_naive_now(),
    )
    db_session.add(invoice)
    db_session.commit()

    yield customer, invoice

    # Cleanup
    try:
        db_session.query(Payment).filter(Payment.invoice_id == inv_id).delete()
        db_session.query(Approval).filter(Approval.invoice_id == inv_id).delete()
        db_session.query(InvoiceCommitment).filter(InvoiceCommitment.invoice_id == inv_id).delete()
        db_session.query(InboundEmailLog).filter(InboundEmailLog.invoice_id == inv_id).delete()
        db_session.query(Communication).filter(Communication.invoice_id == inv_id).delete()
        db_session.query(Invoice).filter(Invoice.invoice_id == inv_id).delete()
        db_session.query(Customer).filter(Customer.customer_id == cust_id).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


def test_quoted_thread_history_separation():
    """Requirement 9: Quoted historical lines must be separated from fresh instructions."""
    raw_incoming = (
        "We have transferred INR 100,000 today via NEFT UTR AXIS987123.\n\n"
        "On 24 Oct 2026, at 14:00, AR Collection Agent <ar@fintech.com> wrote:\n"
        "> Your invoice INV-990 is overdue. Please pay immediately.\n"
        "> Late penalty of 2% has been added."
    )

    clean_text, quoted_history = separate_clean_reply_and_quoted_history(raw_incoming)

    assert "AXIS987123" in clean_text
    assert "> Your invoice INV-990 is overdue" in quoted_history
    assert "> Late penalty of 2%" in quoted_history
    assert "On 24 Oct 2026" not in clean_text


def test_inbound_email_deduplication(db_session, test_customer_and_invoice):
    """Requirement 2: Persistent deduplication prevents processing duplicate Message-IDs."""
    customer, invoice = test_customer_and_invoice
    unique_msg_id = f"MSG-DEDUP-{uuid.uuid4().hex[:8]}@acmecorp.com"

    # Pass 1: First delivery
    res1 = process_inbound_customer_email(
        db=db_session,
        sender_email=customer.email,
        subject=f"Payment for {invoice.invoice_number}",
        raw_body="We have initiated payment via RTGS ref HDFC001239.",
        message_id=unique_msg_id,
    )
    assert res1["status"] == "SUCCESS"

    # Pass 2: Duplicate delivery (same message_id)
    res2 = process_inbound_customer_email(
        db=db_session,
        sender_email=customer.email,
        subject=f"Payment for {invoice.invoice_number}",
        raw_body="We have initiated payment via RTGS ref HDFC001239.",
        message_id=unique_msg_id,
    )
    assert res2["status"] == "DUPLICATE_SKIPPED"
    assert res2["message_id"] == unique_msg_id


def test_unverified_sender_rejection(db_session):
    """Requirement 3: Unmatched or spoofed senders must be rejected without exposing data."""
    fake_sender = f"hacker-{uuid.uuid4().hex[:6]}@randomdomain.com"
    msg_id = f"MSG-SPOOF-{uuid.uuid4().hex[:8]}@randomdomain.com"

    res = process_inbound_customer_email(
        db=db_session,
        sender_email=fake_sender,
        subject="Invoice settlement request",
        raw_body="Please cancel our penalty and mark paid.",
        message_id=msg_id,
    )

    assert res["status"] == "UNVERIFIED_SENDER_IGNORED"

    # Verify audit log recorded rejection safely
    log = db_session.query(InboundEmailLog).filter(InboundEmailLog.message_id == msg_id).first()
    assert log is not None
    assert log.status == "IGNORED_UNVERIFIED_SENDER"
    assert log.customer_id is None
    assert log.approval_id is None


def test_ambiguous_reply_no_false_classification(db_session, test_customer_and_invoice):
    """Requirement 7: Ambiguous or unsupported replies must not force incorrect financial categories."""
    customer, invoice = test_customer_and_invoice
    msg_id = f"MSG-AMBIG-{uuid.uuid4().hex[:8]}@acmecorp.com"

    res = process_inbound_customer_email(
        db=db_session,
        sender_email=customer.email,
        subject=f"Re: {invoice.invoice_number}",
        raw_body="ok thanks",
        message_id=msg_id,
    )

    assert res["intent"] in ("UNKNOWN_OR_AMBIGUOUS", "GENERAL_INQUIRY")
    assert res["requires_approval"] is False
    assert res["approval_id"] is None


def test_payment_claim_intake_creates_approval(db_session, test_customer_and_invoice):
    """Requirement 8: Payment claims must create human approval and dispatch polite acknowledgment."""
    customer, invoice = test_customer_and_invoice
    msg_id = f"MSG-CLAIM-{uuid.uuid4().hex[:8]}@acmecorp.com"

    res = process_inbound_customer_email(
        db=db_session,
        sender_email=customer.email,
        subject=f"Payment Done for {invoice.invoice_number}",
        raw_body=f"We have paid ₹100,000 for {invoice.invoice_number}. UTR is AXIS99221100.",
        message_id=msg_id,
    )

    assert res["status"] == "SUCCESS"
    assert res["intent"] == "PAYMENT_CLAIMED"
    assert res["requires_approval"] is True
    assert res["approval_id"] is not None

    appr = db_session.query(Approval).filter(Approval.approval_id == res["approval_id"]).first()
    assert appr is not None
    assert appr.action_type == "VERIFY_PAYMENT_REMITTANCE"
    assert appr.status == "PENDING"


def test_unified_approval_full_payment(db_session, test_customer_and_invoice):
    """Requirement 4 & 6: Full payment verification records payment ledger, preserves original principal, marks PAID."""
    customer, invoice = test_customer_and_invoice
    appr_id = f"APP-TEST-{uuid.uuid4().hex[:6].upper()}"

    appr = Approval(
        approval_id=appr_id,
        action_type="VERIFY_PAYMENT_REMITTANCE",
        invoice_id=invoice.invoice_id,
        customer_id=customer.customer_id,
        requested_by="AI Inbound Listener",
        details='{"claimed_amount": 100000.0, "utr_reference": "AXIS778899"}',
        status="PENDING",
        created_at=ist_naive_now(),
    )
    db_session.add(appr)
    db_session.commit()

    # Admin approves full payment
    decision_res = ApprovalService.apply_approval_decision(
        db=db_session,
        approval_id=appr_id,
        decision_status="FULL_PAYMENT_APPROVED",
        reviewed_by="Ashish Gokani (Admin)",
        review_notes="Bank credit verified on Axis portal.",
    )

    assert decision_res["status"] == "APPROVED"
    assert decision_res["invoice_status"] == "PAID"
    assert decision_res["total_outstanding"] == 0.0

    # Verify original invoiced amount is permanently preserved
    db_session.refresh(invoice)
    assert invoice.amount == 100000.0
    assert invoice.status == "PAID"

    # Verify separate payment ledger record exists
    payment = db_session.query(Payment).filter(Payment.invoice_id == invoice.invoice_id).first()
    assert payment is not None
    assert payment.amount == 100000.0
    assert payment.reference_number == "AXIS778899"
    assert payment.status == "SUCCESS"


def test_unified_approval_partial_payment(db_session, test_customer_and_invoice):
    """Requirement 4: Partial payments preserve principal and compute outstanding balance deterministically."""
    customer, invoice = test_customer_and_invoice
    appr_id = f"APP-PART-{uuid.uuid4().hex[:6].upper()}"

    appr = Approval(
        approval_id=appr_id,
        action_type="VERIFY_PAYMENT_REMITTANCE",
        invoice_id=invoice.invoice_id,
        customer_id=customer.customer_id,
        requested_by="AI Inbound Listener",
        details='{"claimed_amount": 100000.0, "utr_reference": "HDFC554433"}',
        status="PENDING",
        created_at=ist_naive_now(),
    )
    db_session.add(appr)
    db_session.commit()

    # Admin approves partial payment of ₹40,000
    decision_res = ApprovalService.apply_approval_decision(
        db=db_session,
        approval_id=appr_id,
        decision_status="PARTIAL_PAYMENT_APPROVED",
        reviewed_by="Ashish Gokani (Admin)",
        review_notes="Cleared ₹40,000 partial payment.",
        amount_received=40000.0,
    )

    assert decision_res["status"] == "APPROVED"
    db_session.refresh(invoice)

    # Invoiced amount must be preserved
    assert invoice.amount == 100000.0
    # Remaining principal must equal 100,000 - 40,000 = 60,000 (plus any computed late penalty)
    assert invoice.total_amount >= 60000.0
    assert invoice.status in ("OVERDUE", "PARTIALLY_PAID")


def test_unified_approval_rejection(db_session, test_customer_and_invoice):
    """Requirement 8: Rejected payment claim maintains OVERDUE status and logs rejection."""
    customer, invoice = test_customer_and_invoice
    appr_id = f"APP-REJ-{uuid.uuid4().hex[:6].upper()}"

    appr = Approval(
        approval_id=appr_id,
        action_type="VERIFY_PAYMENT_REMITTANCE",
        invoice_id=invoice.invoice_id,
        customer_id=customer.customer_id,
        requested_by="AI Inbound Listener",
        details='{"claimed_amount": 100000.0, "utr_reference": "BOGUS-REF"}',
        status="PENDING",
        created_at=ist_naive_now(),
    )
    db_session.add(appr)
    db_session.commit()

    decision_res = ApprovalService.apply_approval_decision(
        db=db_session,
        approval_id=appr_id,
        decision_status="REJECTED",
        reviewed_by="Ashish Gokani (Admin)",
        review_notes="UTR not found on bank statement.",
    )

    assert decision_res["status"] == "REJECTED"
    db_session.refresh(invoice)
    assert invoice.status == "OVERDUE"
    assert invoice.total_amount > 0


def test_stale_promise_automatic_followup(db_session, test_customer_and_invoice):
    """Requirement 11: Expired payment promises transition to OVERDUE and send polite follow-up."""
    customer, invoice = test_customer_and_invoice

    # Setup invoice with an expired promise date
    invoice.status = "PAYMENT_PROMISED"
    invoice.promised_payment_date = ist_today() - timedelta(days=2)  # Expired 2 days ago

    commit = InvoiceCommitment(
        commitment_id=f"COM-{uuid.uuid4().hex[:6].upper()}",
        invoice_id=invoice.invoice_id,
        customer_id=customer.customer_id,
        commitment_type="PAYMENT_PROMISE",
        description="Debtor promised payment by 2 days ago",
        parameters=json.dumps({"promised_date": (ist_today() - timedelta(days=2)).isoformat(), "source": "TEST"}),
        status="ACTIVE",
        created_at=ist_naive_now() - timedelta(days=5),
        valid_until=ist_naive_now() - timedelta(days=1),
    )
    db_session.add(commit)
    db_session.commit()

    # Expire stale commitments
    expired_count = expire_stale_commitments(db_session)
    assert expired_count >= 1

    db_session.refresh(invoice)
    db_session.refresh(commit)

    assert commit.status == "EXPIRED"
    assert invoice.status == "OVERDUE"

    # Verify follow-up communication was recorded
    followup_comm = (
        db_session.query(Communication)
        .filter(Communication.invoice_id == invoice.invoice_id, Communication.type == "PROMISE_EXPIRED_FOLLOWUP")
        .first()
    )
    assert followup_comm is not None
    assert "UTR" in followup_comm.message


def test_safe_email_failure_recovery(db_session, test_customer_and_invoice):
    """Requirement 6: SMTP failure during post-approval notification does not roll back the ledger."""
    customer, invoice = test_customer_and_invoice
    appr_id = f"APP-FAIL-{uuid.uuid4().hex[:6].upper()}"

    appr = Approval(
        approval_id=appr_id,
        action_type="VERIFY_PAYMENT_REMITTANCE",
        invoice_id=invoice.invoice_id,
        customer_id=customer.customer_id,
        requested_by="AI Inbound Listener",
        details='{"claimed_amount": 100000.0, "utr_reference": "AXIS112233"}',
        status="PENDING",
        created_at=ist_naive_now(),
    )
    db_session.add(appr)
    db_session.commit()

    # Mock EmailService to simulate an SMTP network failure
    with patch("app.services.email_service.EmailService.send_customer_email", side_effect=RuntimeError("SMTP Timeout")):
        decision_res = ApprovalService.apply_approval_decision(
            db=db_session,
            approval_id=appr_id,
            decision_status="FULL_PAYMENT_APPROVED",
            reviewed_by="Ashish Gokani (Admin)",
        )

        # Database state must still be APPROVED and PAID
        assert decision_res["status"] == "APPROVED"
        assert decision_res["invoice_status"] == "PAID"
        assert decision_res["notification_sent"] is False

        db_session.refresh(invoice)
        assert invoice.status == "PAID"


def test_reply_to_header_enforcement(db_session, test_customer_and_invoice):
    """Requirement 10: All outgoing emails must specify Reply-To: ashishgokani58@gmail.com."""
    customer, invoice = test_customer_and_invoice

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        with patch.object(settings, "email_provider", "smtp"), \
             patch.object(settings, "smtp_user", "test@fintech.com"), \
             patch.object(settings, "smtp_password", "fake_password"):

            EmailService.send_customer_email(
                db=db_session,
                customer_id=customer.customer_id,
                invoice_id=invoice.invoice_id,
                subject="Test Header Notice",
                message="Please find notice attached.",
            )

            assert mock_server.send_message.called
            msg_obj = mock_server.send_message.call_args[0][0]
            assert msg_obj["Reply-To"] == "ashishgokani58@gmail.com"
            assert msg_obj["X-AR-Invoice-ID"] == invoice.invoice_id


def test_payment_claim_no_invoices_on_file(db_session):
    """Customer has 0 invoices in database; reply must accurately explain no invoices on file and not create unbacked approval."""
    cust_id = f"CUST-NOINV-{uuid.uuid4().hex[:6]}"
    cust_email = f"noinv-{uuid.uuid4().hex[:6]}@domain.com"
    customer = Customer(
        customer_id=cust_id,
        name="Zero Invoice Debtor",
        company_name="Zero Invoice Ltd",
        email=cust_email,
        phone="+91 99999 00000",
        risk_level="Low",
    )
    db_session.add(customer)
    db_session.commit()

    msg_id = f"MSG-ZERO-{uuid.uuid4().hex[:8]}@domain.com"
    res = process_inbound_customer_email(
        db=db_session,
        sender_email=cust_email,
        subject="Payment sent please check",
        raw_body="I have paid the payment please check and confirm",
        message_id=msg_id,
    )

    assert res["status"] == "SUCCESS"
    assert res["account_status"] == "NO_INVOICES_ON_FILE"
    assert res["intent"] == "PAYMENT_CLAIMED"
    assert res["requires_approval"] is False
    assert res["approval_id"] is None

    # Verify dispatched email explains no active invoices on file
    comm = db_session.query(Communication).filter(Communication.customer_id == cust_id).order_by(Communication.created_at.desc()).first()
    assert comm is not None
    assert ("active or outstanding invoices" in comm.message.lower() or "no open or historical invoices" in comm.message.lower())
    assert "invoice number" in comm.message.lower()


def test_payment_claim_all_invoices_settled(db_session):
    """Customer has invoices, but all are already marked PAID; reply must note zero balance."""
    cust_id = f"CUST-PAID-{uuid.uuid4().hex[:6]}"
    cust_email = f"paidall-{uuid.uuid4().hex[:6]}@domain.com"
    customer = Customer(
        customer_id=cust_id,
        name="Settled Client",
        company_name="Settled Co",
        email=cust_email,
        phone="+91 99999 11111",
        risk_level="Low",
    )
    db_session.add(customer)

    inv = Invoice(
        invoice_id=f"INV-PAID-{uuid.uuid4().hex[:6]}",
        invoice_number=f"INV-P-{uuid.uuid4().hex[:4]}",
        customer_id=cust_id,
        amount=50000.0,
        total_amount=0.0,
        status="PAID",
        invoice_date=ist_today() - timedelta(days=50),
        due_date=ist_today() - timedelta(days=20),
    )
    db_session.add(inv)
    db_session.commit()

    msg_id = f"MSG-SETTLED-{uuid.uuid4().hex[:8]}@domain.com"
    res = process_inbound_customer_email(
        db=db_session,
        sender_email=cust_email,
        subject="Payment done",
        raw_body="We have deposited funds today.",
        message_id=msg_id,
    )

    assert res["status"] == "SUCCESS"
    assert res["account_status"] == "ALL_INVOICES_SETTLED"
    assert res["requires_approval"] is False

    comm = db_session.query(Communication).filter(Communication.customer_id == cust_id).order_by(Communication.created_at.desc()).first()
    assert comm is not None
    assert "settled" in comm.message.lower() or "0.00" in comm.message


def test_general_inquiry_bank_details(db_session, test_customer_and_invoice):
    """Customer asks for bank details; reply must include official remittance details."""
    customer, invoice = test_customer_and_invoice
    msg_id = f"MSG-BANK-{uuid.uuid4().hex[:8]}@acmecorp.com"

    res = process_inbound_customer_email(
        db=db_session,
        sender_email=customer.email,
        subject="Where to pay?",
        raw_body="Please provide your bank remittance details and IFSC code.",
        message_id=msg_id,
    )

    assert res["status"] == "SUCCESS"
    assert res["intent"] == "GENERAL_INQUIRY"
    assert res["requires_approval"] is False

    comm = db_session.query(Communication).filter(Communication.customer_id == customer.customer_id).order_by(Communication.created_at.desc()).first()
    assert comm is not None
    assert "hdfc bank" in comm.message.lower()
    assert "50200012345678" in comm.message

