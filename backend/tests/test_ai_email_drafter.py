"""
AI-Powered Email Drafter Regression Suite.

Verifies:
1. Concession reduction (e.g. 0.5% -> 0.1%): Retracts previous discount and issues apology.
2. Concession upgrade (e.g. 0.1% -> 0.5%): References upgraded discount offer.
3. Concession stacking: Details combined multi-concession totals.
4. Managerial custom instructions incorporation into customer email body.
"""

from app.services.ai_email_drafter import (
    draft_settlement_email_with_ai,
    draft_reminder_email_with_ai,
    draft_payment_confirmation_email,
    resolve_salutation,
    SIGN_OFF_TEXT,
)
from app.services.email_service import build_clean_text_email
from app.db.session import SessionLocal


def test_draft_settlement_email_reduction_with_apology():
    """Concession reduction (0.5% to 0.1%) MUST retract previous offer and include an apology."""
    res = draft_settlement_email_with_ai(
        customer_person="Priya Deshmukh",
        customer_company="Pinnacle Healthcare",
        invoice_number="INV-2026-1008",
        original_amount=211500.0,
        effective_pct=0.1,
        discount_amount=211.50,
        settlement_amount=211288.50,
        hours_valid=24,
        commitment_id="COM-TEST1234",
        prior_pct=0.5,
        resolution_mode="REVISE",
        custom_instructions=None,
    )
    body = res["body"]
    subject = res["subject"]

    # Must NOT call 0.1% an upgrade over 0.5%
    assert "upgraded 0.1%" not in body.lower()
    assert "upgraded" not in subject.lower()

    # Must acknowledge that 0.5% was retracted/removed
    assert "0.5%" in body
    assert "retracted" in body.lower() or "removed" in body.lower()

    # Must include sincere apology
    assert "apologize" in body.lower() or "apologies" in body.lower()

    # Must specify the new 0.1% terms
    assert "0.1%" in body
    assert "₹2,11,288.50" in body


def test_draft_settlement_email_upgrade():
    """Concession increase (0.1% to 0.5%) MUST indicate an upgraded concession."""
    res = draft_settlement_email_with_ai(
        customer_person="Sarah Connor",
        customer_company="Helios Retail Corp",
        invoice_number="INV-2026-1004",
        original_amount=255000.0,
        effective_pct=0.5,
        discount_amount=1275.0,
        settlement_amount=253725.0,
        hours_valid=24,
        commitment_id="COM-TEST5678",
        prior_pct=0.1,
        resolution_mode="REVISE",
        custom_instructions=None,
    )
    body = res["body"]
    subject = res["subject"]

    assert "upgraded" in subject.lower() or "upgraded" in body.lower()
    assert "0.5%" in body
    assert "0.1%" in body


def test_draft_settlement_email_stack():
    """Stacked concession MUST reflect combined multi-concession totals."""
    res = draft_settlement_email_with_ai(
        customer_person="Sarah Connor",
        customer_company="Helios Retail Corp",
        invoice_number="INV-2026-1004",
        original_amount=255000.0,
        effective_pct=0.6,
        discount_amount=1530.0,
        settlement_amount=253470.0,
        hours_valid=24,
        commitment_id="COM-TEST9999",
        prior_pct=0.1,
        resolution_mode="STACK",
        custom_instructions=None,
    )
    body = res["body"]
    assert "stacked" in body.lower() or "combined" in body.lower() or "additional" in body.lower()
    assert "0.6%" in body


def test_draft_settlement_email_incorporates_custom_instructions():
    """Manager custom instructions must be embedded into the email copy."""
    custom_msg = "Please note our finance desk closes at 4:30 PM IST for clearance."
    res = draft_settlement_email_with_ai(
        customer_person="Priya Deshmukh",
        customer_company="Pinnacle Healthcare",
        invoice_number="INV-2026-1008",
        original_amount=211500.0,
        effective_pct=0.1,
        discount_amount=211.50,
        settlement_amount=211288.50,
        hours_valid=24,
        commitment_id="COM-TEST1234",
        prior_pct=0.5,
        resolution_mode="REVISE",
        custom_instructions=custom_msg,
    )
    assert custom_msg in res["body"]


def test_resolve_salutation_and_sign_off():
    """Verifies that salutations format properly and sign-off is standard."""
    assert resolve_salutation("Alice Smith", "Apex Technologies") == "Dear Alice Smith,"
    assert resolve_salutation("", "Apex Technologies") == "Dear Apex Technologies Accounts Team,"
    assert resolve_salutation(None, None) == "Hello Customer,"
    assert "Accounts Receivable Team" in SIGN_OFF_TEXT


def test_draft_reminder_email_includes_bank_and_no_placeholders():
    """Verifies that payment reminder emails include banking details and zero placeholders."""
    from app.db.models import Invoice
    db = SessionLocal()
    try:
        inv = db.query(Invoice).first()
        assert inv is not None
        res = draft_reminder_email_with_ai(db, invoice_id=inv.invoice_id, reminder_level=1)
        assert "error" not in res
        body = res["body"]

        # Must include banking remittance instructions for payment collection
        assert "Bank Remittance Details" in body or "Bank Name" in body
        assert "IFSC Code" in body or "Account Number" in body

        # Must end with standard sign-off
        assert "Accounts Receivable Team" in body

        # Must NOT contain bracketed placeholders
        assert "[Customer Name]" not in body
        assert "[Invoice Number]" not in body
        assert "[Due Date]" not in body
        assert "[Amount]" not in body
    finally:
        db.close()


def test_draft_payment_confirmation_omits_bank_and_has_no_placeholders():
    """Payment receipt confirmations must acknowledge payment and omit bank collection details."""
    res = draft_payment_confirmation_email(
        customer_name="Vikram Patel",
        company_name="Apex Global Technologies",
        invoice_number="INV-2026-1001",
        amount_received=95000.0,
        payment_method="NEFT",
        reference_number="NEFT/2026/889104",
    )
    body = res["body"]

    # Salutation & Confirmation details
    assert "Dear Vikram Patel," in body
    assert "₹95,000.00" in body
    assert "NEFT/2026/889104" in body
    assert "INV-2026-1001" in body

    # Must NOT include remittance/bank collection details (as payment is already received)
    assert "Bank Remittance Details" not in body

    # Sign-off & zero placeholders
    assert "Accounts Receivable Team" in body
    assert "[" not in body and "]" not in body


def test_build_clean_text_email_zero_css_tables():
    """Verifies that the HTML alternative part has zero heavy CSS tables or dark backgrounds."""
    sample_text = "Dear Customer,\n\nPlease remit payment.\n\nWarm regards,\nAccounts Receivable Team"
    clean_html = build_clean_text_email(sample_text)

    # Must NOT contain table-based dark backgrounds or complex CSS layout
    assert "#0b0f19" not in clean_html
    assert "<table" not in clean_html
    assert "linear-gradient" not in clean_html
    assert "white-space: pre-wrap" in clean_html
    assert "Dear Customer," in clean_html
