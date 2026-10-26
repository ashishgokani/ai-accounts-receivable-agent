"""
Operational Master Data Management and Automation Tools Regression Suite.

Verifies:
1. Customer master profile updates (contact, email uniqueness, risk rating).
2. Invoice parameter updates with automated penalty recalculations.
3. Financial immutability: Settled PAID invoices cannot be modified.
4. On-demand autonomous collection pipeline execution.
5. Human-in-the-loop approval inspection and decision processing.
6. Portfolio-wide financial KPIs aggregation.
7. Agent activity audit log retrieval.
"""

from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Customer, Invoice, Approval
from app.services.tools_management import (
    tool_update_customer_profile,
    tool_update_invoice_data,
    tool_trigger_automation_cycle,
    tool_get_pending_approvals,
    tool_review_approval_decision,
    tool_get_financial_portfolio_summary,
    tool_get_agent_audit_logs,
)
from app.core.timezone import ist_today, ist_naive_now


def test_update_customer_profile():
    """Verify updating contact details, address, and credit risk rating."""
    db: Session = SessionLocal()
    try:
        cust = db.query(Customer).first()
        assert cust is not None

        # Reset customer to baseline first so changes always register
        cust.name = "Original Officer"
        cust.phone = "+91 88888 77777"
        cust.address = "Original Address"
        cust.risk_level = "Low"
        cust.risk_score = 20
        db.commit()

        res = tool_update_customer_profile(
            db,
            customer_id=cust.customer_id,
            name="Updated Contact Officer",
            phone="+91 99999 11111",
            address="Level 14, Express Towers, Nariman Point, Mumbai",
            risk_level="High",
        )
        assert res["status"] == "SUCCESS"
        assert res["name"] == "Updated Contact Officer"
        assert res["phone"] == "+91 99999 11111"
        assert res["risk_level"] == "High"
        assert res["risk_score"] == 85  # Auto-synced for High risk

        # Verify in database
        db.refresh(cust)
        assert cust.name == "Updated Contact Officer"
        assert cust.risk_level == "High"
    finally:
        db.close()


def test_update_customer_duplicate_email_rejected():
    """Verify email uniqueness guardrail prevents duplicate corporate emails."""
    db: Session = SessionLocal()
    try:
        custs = db.query(Customer).limit(2).all()
        if len(custs) >= 2:
            res = tool_update_customer_profile(
                db,
                customer_id=custs[0].customer_id,
                email=custs[1].email,  # Attempt duplicate email
            )
            assert "error" in res
            assert "already registered" in res["error"]
    finally:
        db.close()


def test_update_invoice_data_and_penalty_recalculation():
    """Verify updating invoice due date and amount triggers penalty recalculation."""
    db: Session = SessionLocal()
    try:
        # Target standard seeded invoice rather than test fixture invoices
        inv = db.query(Invoice).filter(Invoice.status != "PAID", ~Invoice.invoice_id.like("INV-TEST-%")).first()
        assert inv is not None

        new_due = (ist_today() - timedelta(days=20)).strftime("%Y-%m-%d")
        res = tool_update_invoice_data(
            db,
            invoice_id=inv.invoice_id,
            due_date=new_due,
            amount=150000.0,
            status="OVERDUE",
            dispute_reason="Under commercial review",
        )
        assert res["status"] == "SUCCESS"
        assert res["amount"] == 150000.0
        assert res["due_date"] == new_due
        assert res["penalty_amount"] > 0  # Penalties recalculate for 10 days overdue
        assert res["total_amount"] == res["amount"] + res["penalty_amount"]
    finally:
        db.close()


def test_paid_invoice_immutability_guardrail():
    """Verify GAAP/IFRS financial rule: settled PAID invoices cannot be modified."""
    import uuid
    db: Session = SessionLocal()
    try:
        cust = db.query(Customer).first()
        test_paid_id = f"INV-PAID-{uuid.uuid4().hex[:6].upper()}"
        paid_inv = Invoice(
            invoice_id=test_paid_id,
            customer_id=cust.customer_id,
            invoice_number=test_paid_id,
            invoice_date=ist_today() - timedelta(days=30),
            due_date=ist_today() - timedelta(days=10),
            amount=50000.0,
            penalty_amount=0.0,
            total_amount=50000.0,
            status="PAID",
            created_at=ist_naive_now(),
        )
        db.add(paid_inv)
        db.commit()

        res = tool_update_invoice_data(
            db,
            invoice_id=paid_inv.invoice_id,
            amount=99999.0,
        )
        assert "error" in res
        assert res.get("blocked_by_guardrail") is True
        assert "immutable" in res["error"].lower()
    finally:
        db.close()


def test_trigger_automation_cycle():
    """Verify running the autonomous collection pipeline on-demand."""
    db: Session = SessionLocal()
    try:
        res = tool_trigger_automation_cycle(db)
        assert res["status"] == "SUCCESS"
        assert "invoices_analyzed" in res
        assert "actions_executed" in res
    finally:
        db.close()


def test_pending_approvals_and_decision_review():
    """Verify inspecting and processing human approvals."""
    import uuid
    db: Session = SessionLocal()
    try:
        # Query approvals
        res = tool_get_pending_approvals(db)
        assert "total_pending" in res

        # Create temporary approval with unique ID
        inv = db.query(Invoice).first()
        test_appr_id = f"APP-TEST-{uuid.uuid4().hex[:6].upper()}"
        appr = Approval(
            approval_id=test_appr_id,
            action_type="ESCALATE",
            invoice_id=inv.invoice_id,
            customer_id=inv.customer_id,
            details='{"reason": "Test escalation"}',
            status="PENDING",
            created_at=ist_naive_now(),
        )
        db.add(appr)
        db.commit()

        # Review decision: approve
        rev_res = tool_review_approval_decision(
            db,
            approval_id=test_appr_id,
            decision="APPROVED",
            notes="Authorized by CFO in chat test",
        )
        assert rev_res["status"] == "SUCCESS"
        assert rev_res["decision"] == "APPROVED"

        db.refresh(appr)
        assert appr.status == "APPROVED"
    finally:
        db.close()


def test_financial_portfolio_summary_and_audit_logs():
    """Verify portfolio summary metrics and agent audit log retrieval."""
    db: Session = SessionLocal()
    try:
        summary = tool_get_financial_portfolio_summary(db)
        assert "total_invoiced_amount" in summary
        assert "total_outstanding_amount" in summary
        assert "collection_efficiency_rate" in summary

        logs = tool_get_agent_audit_logs(db, limit=5)
        assert "logs" in logs
        assert "total_retrieved" in logs
    finally:
        db.close()


def test_all_bedrock_tools_handled_in_dispatcher():
    """Verify that every tool registered in BEDROCK_TOOL_SPECS is dispatched without 'unrecognized' errors."""
    from app.services.bedrock_tools import BEDROCK_TOOL_SPECS
    from app.services.tool_dispatcher import dispatch_tool_call

    db: Session = SessionLocal()
    try:
        inv = db.query(Invoice).first()
        inv_id = inv.invoice_id if inv else "INV-1001"

        # 1. Directly test draft_reminder_email
        draft_out, draft_sum = dispatch_tool_call(db, "draft_reminder_email", {"invoice_id": inv_id})
        assert "error" not in draft_out or "not recognized" not in draft_out["error"]
        assert "Drafted" in draft_sum or "draft" in draft_sum.lower()

        # 2. Directly test send_email
        send_out, send_sum = dispatch_tool_call(db, "send_email", {
            "invoice_id": inv_id,
            "subject": "Test Notice",
            "body": "Test message body without placeholders.",
        })
        assert "error" not in send_out or "not recognized" not in send_out["error"]

        # 3. Verify that all 25 Bedrock tools have dispatch entries
        import inspect, re
        source = inspect.getsource(dispatch_tool_call)
        handled = set(re.findall(r'tool_name == ["\']([^"\']+)["\']', source))
        bedrock_names = set(t["toolSpec"]["name"] for t in BEDROCK_TOOL_SPECS)
        missing = bedrock_names - handled
        assert not missing, f"Tools defined in Bedrock specs but missing in dispatcher: {missing}"
    finally:
        db.close()

