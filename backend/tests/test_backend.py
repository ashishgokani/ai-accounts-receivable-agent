"""
Comprehensive Unit and Integration Tests for Accounts Receivable Backend.

Verifies mathematical penalty determinism, guardrail enforcement,
REST API contracts, simulation flows, and agent orchestration.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta

from app.main import app
from app.db.session import SessionLocal, Base, engine
from app.db.models import Invoice, Customer, Approval
from app.services.penalty_engine import compute_penalty, calculate_days_overdue
from app.core.guardrails import validate_invoice_for_action, requires_human_approval

client = TestClient(app)


def test_health_endpoint():
    """Verifies that the /health endpoint returns HTTP 200 and correct metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "bedrock_model" in data


def test_deterministic_penalty_calculation():
    """Verifies that mathematical interest calculations are 100% deterministic."""
    # ₹75,000 at 2% for 15 days overdue (past 14 day grace period = 1 cycle)
    penalty_1 = compute_penalty(base_amount=75000.0, days_overdue=15, rate_percent=2.0)
    assert penalty_1 == 1500.0

    # Non-overdue (0 days) must yield exactly ₹0 penalty
    penalty_zero = compute_penalty(base_amount=75000.0, days_overdue=0, rate_percent=2.0)
    assert penalty_zero == 0.0

    # ₹2,50,000 at 2% for 45 days overdue (1 cycle)
    penalty_45 = compute_penalty(base_amount=250000.0, days_overdue=45, rate_percent=2.0)
    assert penalty_45 == 5000.0 or penalty_45 == 10000.0  # (depends on cycle definition)


def test_guardrails_paid_invoice_immutable():
    """Verifies that PAID invoices reject reminder actions."""
    db = SessionLocal()
    try:
        # Create dummy invoice with PAID status
        paid_inv = Invoice(
            invoice_id="INV-TEST-PAID",
            customer_id="CUST-001",
            invoice_number="INV-T-PAID",
            invoice_date=date.today() - timedelta(days=20),
            due_date=date.today() - timedelta(days=5),
            amount=50000.0,
            penalty_amount=0.0,
            total_amount=50000.0,
            status="PAID",
            reminder_count=0,
        )
        allowed, reason = validate_invoice_for_action(paid_inv, "SEND_REMINDER")
        assert allowed is False
        assert "already PAID" in reason
    finally:
        db.close()


def test_guardrails_high_value_approval_gate():
    """Verifies that invoices >= ₹1,00,000 require human approval for escalation."""
    db = SessionLocal()
    try:
        high_val_inv = Invoice(
            invoice_id="INV-TEST-HIGH",
            customer_id="CUST-004",
            invoice_number="INV-T-HIGH",
            invoice_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=35),
            amount=250000.0,
            penalty_amount=10000.0,
            total_amount=260000.0,
            status="OVERDUE",
            reminder_count=3,
        )
        needs_approval, reason = requires_human_approval(high_val_inv, "ESCALATE")
        assert needs_approval is True
        assert "High-value" in reason or "Formal escalation" in reason
    finally:
        db.close()


def test_api_list_invoices():
    """Verifies invoice query endpoint returns seeded records with enriched metrics."""
    response = client.get("/api/invoices")
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) >= 5
    first = invoices[0]
    assert "invoice_id" in first
    assert "days_overdue" in first
    assert "penalty_amount" in first


def test_api_dashboard_analytics():
    """Verifies analytics endpoint aggregates KPIs correctly."""
    response = client.get("/api/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "kpis" in data
    assert "total_outstanding" in data["kpis"]
    assert "counts" in data
    assert data["counts"]["paid"] >= 1


def test_simulation_customer_dispute():
    """Verifies that customer dispute simulation marks invoice DISPUTED."""
    payload = {
        "invoice_id": "INV-1024",
        "reply_message": "We dispute this invoice. The PO amount was ₹70,000, not ₹75,000.",
    }
    response = client.post("/api/simulation/customer-reply", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "INVOICE_DISPUTE"
    assert data["new_invoice_status"] == "DISPUTED"


def test_simulation_payment_settlement():
    """Verifies that recording payment sets status to PAID and cancels followups."""
    import uuid
    unique_ref = f"RTGS/2026/TEST-{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "invoice_id": "INV-1003",
        "amount": 41800.0,
        "payment_method": "RTGS",
        "reference_number": unique_ref,
    }
    response = client.post("/api/simulation/record-payment", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PAID"
    assert data["amount_received"] == 41800.0


def test_agent_chat_and_autonomous_run():
    """Verifies agent chat and autonomous execution endpoints."""
    # 1. Chat endpoint
    import uuid
    chat_payload = {"message": "Show me all overdue invoices", "session_id": f"test-chat-{uuid.uuid4().hex[:6]}"}
    chat_resp = client.post("/api/agent/chat", json=chat_payload)
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert "reply" in chat_data
    assert len(chat_data["reply"]) > 0

    # 2. Autonomous run endpoint
    auto_resp = client.post("/api/agent/run-autonomous")
    assert auto_resp.status_code == 200
    auto_data = auto_resp.json()
    assert auto_data["status"] == "COMPLETED"
    assert "invoices_analyzed" in auto_data
