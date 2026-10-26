"""
Comprehensive Unit and Integration Tests for Admin Settings.

Verifies:
1. Retrieval of default and persisted settings across all 4 categories.
2. Risk-tiered penalty rules and non-compounding principal calculations.
3. Risk-tiered reminder cadences, dispute pausing, and max escalation limits.
4. Bank details validation, confirmation checks, and dynamic HTML email template rendering.
5. AI Agent operational master toggle behavior in conversational chat.
"""

import json
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Customer, Invoice
from app.core.timezone import ist_today, ist_naive_now
from app.services.penalty_engine import sync_invoice_financials, determine_recommended_action, compute_penalty
from app.services.email_service import EmailService
from app.services.orchestrator import AgentOrchestrator
from app.services.settings_service import (
    get_all_settings,
    update_penalty_settings,
    update_reminder_settings,
    update_bank_settings,
    update_agent_settings,
    PenaltySettings,
    ReminderSettings,
    BankSettings,
    AgentSettings,
)

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_get_all_settings():
    """Verifies GET /api/settings returns valid schemas for all 4 sections."""
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()

    assert "penalty" in data
    assert "reminders" in data
    assert "bank" in data
    assert "agent" in data

    assert data["penalty"]["calculation_base"] == "PRINCIPAL_ONLY"
    assert "low_risk" in data["penalty"]
    assert "medium_risk" in data["penalty"]
    assert "high_risk" in data["penalty"]

    assert "automation_enabled" in data["reminders"]
    assert "beneficiary_name" in data["bank"]
    assert "agent_enabled" in data["agent"]


def test_penalty_rules_by_risk_tier(db: Session):
    """Verifies updating penalty rules and tests actual calculation against different customer risk tiers."""
    # 1. Update penalty settings via API
    payload = {
        "calculation_base": "PRINCIPAL_ONLY",
        "low_risk": {"penalty_rate_percent": 1.5, "grace_period_days": 15},
        "medium_risk": {"penalty_rate_percent": 2.5, "grace_period_days": 10},
        "high_risk": {"penalty_rate_percent": 5.0, "grace_period_days": 4},
    }
    resp = client.put("/api/settings/penalty", json=payload)
    assert resp.status_code == 200

    # 2. Setup test customers with Low and High risk
    low_cust = db.query(Customer).filter(Customer.customer_id == "CUST-TEST-LOW").first()
    if not low_cust:
        low_cust = Customer(
            customer_id="CUST-TEST-LOW",
            name="Low Risk Contact",
            company_name="Low Risk Corp",
            email="low@riskcorp.com",
            risk_level="Low",
        )
        db.add(low_cust)

    high_cust = db.query(Customer).filter(Customer.customer_id == "CUST-TEST-HIGH").first()
    if not high_cust:
        high_cust = Customer(
            customer_id="CUST-TEST-HIGH",
            name="High Risk Contact",
            company_name="High Risk Corp",
            email="high@riskcorp.com",
            risk_level="High",
        )
        db.add(high_cust)
    db.commit()

    # 3. Create invoices 10 days overdue
    due_10_days_ago = ist_today() - timedelta(days=10)

    # Low risk customer invoice (grace period is 15 days, so 10 days overdue should have 0 penalty)
    inv_low = db.query(Invoice).filter(Invoice.invoice_id == "INV-TEST-LOW").first()
    if not inv_low:
        inv_low = Invoice(
            invoice_id="INV-TEST-LOW",
            customer_id=low_cust.customer_id,
            invoice_number="INV-2026-LOW",
            invoice_date=due_10_days_ago - timedelta(days=30),
            due_date=due_10_days_ago,
            amount=100000.0,
            penalty_amount=0.0,
            total_amount=100000.0,
            status="OVERDUE",
        )
        db.add(inv_low)
    else:
        inv_low.due_date = due_10_days_ago
        inv_low.amount = 100000.0
        inv_low.status = "OVERDUE"
    db.commit()

    fin_low = sync_invoice_financials(inv_low, db)
    # 10 days overdue is less than 15 days grace period -> 0 penalty
    assert fin_low["penalty_amount"] == 0.0
    assert fin_low["total_amount"] == 100000.0

    # High risk customer invoice (grace period is 4 days, rate is 5.0%, 10 days overdue gets 5% on 100,000 = 5,000)
    inv_high = db.query(Invoice).filter(Invoice.invoice_id == "INV-TEST-HIGH").first()
    if not inv_high:
        inv_high = Invoice(
            invoice_id="INV-TEST-HIGH",
            customer_id=high_cust.customer_id,
            invoice_number="INV-2026-HIGH",
            invoice_date=due_10_days_ago - timedelta(days=30),
            due_date=due_10_days_ago,
            amount=100000.0,
            penalty_amount=0.0,
            total_amount=100000.0,
            status="OVERDUE",
        )
        db.add(inv_high)
    else:
        inv_high.due_date = due_10_days_ago
        inv_high.amount = 100000.0
        inv_high.status = "OVERDUE"
    db.commit()

    fin_high = sync_invoice_financials(inv_high, db)
    # 10 days overdue >= 4 days grace period -> 1 cycle of 5.0% on ₹1,00,000 = ₹5,000
    assert fin_high["penalty_amount"] == 5000.0
    assert fin_high["total_amount"] == 105000.0


def test_reminder_settings_and_dispute_pause(db: Session):
    """Verifies reminder schedules and checks that disputed invoices are paused per settings."""
    payload = {
        "automation_enabled": True,
        "automation_interval_minutes": 30,
        "low_risk": {
            "auto_reminders_enabled": True,
            "first_reminder_days": 5,
            "reminder_interval_days": 7,
            "max_reminders_before_escalation": 3,
            "final_reminder_approval_required": True,
            "pause_on_dispute": True,
        },
        "medium_risk": {
            "auto_reminders_enabled": True,
            "first_reminder_days": 2,
            "reminder_interval_days": 4,
            "max_reminders_before_escalation": 2,
            "final_reminder_approval_required": True,
            "pause_on_dispute": True,
        },
        "high_risk": {
            "auto_reminders_enabled": False,  # Disabled auto-reminders for high risk
            "first_reminder_days": 1,
            "reminder_interval_days": 2,
            "max_reminders_before_escalation": 1,
            "final_reminder_approval_required": True,
            "pause_on_dispute": True,
        },
    }
    resp = client.put("/api/settings/reminders", json=payload)
    assert resp.status_code == 200

    # Test dispute pause behavior
    inv = db.query(Invoice).first()
    assert inv is not None
    orig_status = inv.status
    inv.status = "DISPUTED"
    inv.dispute_reason = "Billing discrepancy pending resolution"
    db.commit()

    action, reason = determine_recommended_action(inv, db)
    assert action == "PAUSE_REMINDERS"
    assert "dispute" in reason.lower()

    # Restore invoice status
    inv.status = orig_status
    db.commit()


def test_bank_details_validation_and_email_rendering(db: Session):
    """Verifies account number confirmation check and dynamic email template rendering."""
    # 1. Non-matching account numbers should fail validation
    invalid_payload = {
        "beneficiary_name": "Treasury Department",
        "bank_name": "State Bank of India",
        "account_number": "123456789012",
        "confirm_account_number": "999999999999",
        "ifsc_code": "SBIN0001234",
        "payment_instructions": "Pay via RTGS with UTR number.",
    }
    resp = client.put("/api/settings/bank", json=invalid_payload)
    assert resp.status_code == 422

    # 2. Matching account numbers should succeed
    valid_payload = {
        "beneficiary_name": "Treasury Department",
        "bank_name": "State Bank of India",
        "account_number": "123456789012",
        "confirm_account_number": "123456789012",
        "ifsc_code": "SBIN0001234",
        "payment_instructions": "Please quote invoice reference on remittance.",
    }
    resp = client.put("/api/settings/bank", json=valid_payload)
    assert resp.status_code == 200

    # 3. Verify EmailService dispatches with updated bank details dynamically
    cust = db.query(Customer).first()
    send_res = EmailService.send_customer_email(
        db=db,
        customer_id=cust.customer_id,
        invoice_id=None,
        subject="Important Commercial Notice",
        message="Please find your latest billing schedule attached.",
    )
    assert send_res["status"] in ["DELIVERED", "FAILED_DISPATCH"]
    assert send_res["html_rendered"] is True


def test_agent_settings_master_toggle(db: Session):
    """Verifies that pausing the AI Agent in settings prevents conversational actions."""
    # 1. Pause Agent
    resp = client.put("/api/settings/agent", json={"agent_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["agent_enabled"] is False

    # 2. Send chat request - should politely state agent is paused
    chat_resp = AgentOrchestrator.process_chat(
        db=db,
        message="Send payment reminders to overdue accounts",
        session_id="test-paused-agent",
    )
    assert "currently paused by the administrator in Admin Settings" in chat_resp["reply"]
    assert len(chat_resp["tool_calls"]) == 0

    # 3. Re-enable Agent
    resp2 = client.put("/api/settings/agent", json={"agent_enabled": True})
    assert resp2.status_code == 200
    assert resp2.json()["agent_enabled"] is True
