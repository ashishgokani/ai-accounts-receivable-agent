"""
Autonomous AR Batch Workflow and Periodic Collection Execution Engine.

Executes Mode A: Autonomous periodic collection batch runs ("Run Agent Now").
Scans all pending and overdue invoices, evaluates AI collection strategy decisions,
dispatches reminders, and creates human approval items for high-value cases.
"""

from datetime import datetime, timedelta
import logging
import uuid
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models import Invoice, Customer, AgentAction
from app.services.penalty_engine import sync_invoice_financials
from app.services.tools import (
    tool_draft_reminder_email,
    tool_send_email,
    tool_create_escalation,
    log_agent_action,
)

logger = logging.getLogger(__name__)


def execute_autonomous_collection_cycle(db: Session, session_id: str = "session-auto") -> Dict[str, Any]:
    """
    Executes Mode A: Autonomous periodic collection batch run ("Run Agent Now").
    Scans all pending and overdue invoices, evaluates deterministic business rules,
    dispatches reminders, and creates human approval items for high-value cases.

    Args:
        db: Active SQLAlchemy database session.
        session_id: Session identifier for audit logging.

    Returns:
        Dict[str, Any]: Structured execution summary and action log items.
    """
    session_id = session_id or f"AUTO-{uuid.uuid4().hex[:6].upper()}"

    from app.services.settings_service import is_automation_enabled, is_agent_enabled
    if not is_automation_enabled(db):
        logger.info("Autonomous AR workflow skipped: automation is disabled in Admin Settings.")
        return {
            "status": "DISABLED",
            "invoices_analyzed": 0,
            "actions_executed": 0,
            "approvals_pending": 0,
            "summary": "Autonomous collection cycles are disabled in Admin Settings.",
            "action_logs": [],
        }
    if not is_agent_enabled(db):
        logger.info("Autonomous AR workflow skipped: AI agent is disabled in Admin Settings.")
        return {
            "status": "DISABLED",
            "invoices_analyzed": 0,
            "actions_executed": 0,
            "approvals_pending": 0,
            "summary": "AI Agent operations are paused in Admin Settings.",
            "action_logs": [],
        }

    from app.services.ai_collection_decision_agent import evaluate_invoice_collection_decision

    all_invoices = db.query(Invoice).filter(Invoice.status.in_(["PENDING", "OVERDUE", "PARTIALLY_PAID"])).all()

    invoices_analyzed = len(all_invoices)
    actions_executed = 0
    approvals_pending = 0
    action_logs = []

    for inv in all_invoices:
        fin = sync_invoice_financials(inv, db)
        days = fin["days_overdue"]

        if days <= 0 or fin["remaining_principal"] <= 0.01:
            continue

        # Step: AI Collection Decision Agent evaluates debtor context & applies safety guardrails
        decision = evaluate_invoice_collection_decision(db, inv)
        rec_action = decision["action"]

        if rec_action == "DEFER":
            continue

        if decision["requires_approval"]:
            # High-value overdue or concession routed to Human Approval
            res = tool_create_escalation(
                db,
                inv.invoice_id,
                decision.get("ai_rationale") or f"Exceeded risk threshold ({days} days overdue). Human review required.",
            )
            if not res.get("already_pending"):
                approvals_pending += 1
            action_logs.append({
                "invoice_id": inv.invoice_id,
                "customer": inv.customer.company_name if inv.customer else "Unknown",
                "action": "APPROVAL_ALREADY_PENDING" if res.get("already_pending") else "APPROVAL_QUEUED",
                "status": "PENDING_APPROVAL",
                "amount": inv.total_amount,
                "ai_rationale": decision.get("ai_rationale"),
            })

        elif rec_action == "FIRST_REMINDER":
            draft = tool_draft_reminder_email(db, inv.invoice_id, reminder_level=1)
            res = tool_send_email(db, inv.invoice_id, draft["subject"], draft["body"], session_id=session_id)
            if res.get("status") == "PENDING_APPROVAL":
                if not res.get("already_pending"):
                    approvals_pending += 1
            else:
                actions_executed += 1
            action_logs.append({
                "invoice_id": inv.invoice_id,
                "customer": inv.customer.company_name if inv.customer else "Unknown",
                "action": "FIRST_REMINDER",
                "status": res.get("status"),
                "amount": inv.total_amount,
                "ai_rationale": decision.get("ai_rationale"),
            })

        elif rec_action == "SECOND_REMINDER":
            draft = tool_draft_reminder_email(db, inv.invoice_id, reminder_level=2)
            res = tool_send_email(db, inv.invoice_id, draft["subject"], draft["body"], session_id=session_id)
            if res.get("status") == "PENDING_APPROVAL":
                if not res.get("already_pending"):
                    approvals_pending += 1
            else:
                actions_executed += 1
            action_logs.append({
                "invoice_id": inv.invoice_id,
                "customer": inv.customer.company_name if inv.customer else "Unknown",
                "action": "SECOND_REMINDER",
                "status": res.get("status"),
                "amount": inv.total_amount,
                "penalty": inv.penalty_amount,
                "ai_rationale": decision.get("ai_rationale"),
            })

        elif rec_action in ("ESCALATE", "ESCALATE_TO_ADMIN"):
            res = tool_create_escalation(
                db,
                inv.invoice_id,
                decision.get("ai_rationale") or f"Exceeded overdue threshold: {days} days overdue with {inv.reminder_count} reminders sent.",
            )
            if not res.get("already_pending"):
                approvals_pending += 1
            action_logs.append({
                "invoice_id": inv.invoice_id,
                "customer": inv.customer.company_name if inv.customer else "Unknown",
                "action": "APPROVAL_ALREADY_PENDING" if res.get("already_pending") else "ESCALATION_QUEUED",
                "status": "PENDING_APPROVAL",
                "amount": inv.total_amount,
                "ai_rationale": decision.get("ai_rationale"),
            })

    summary = (
        f"Autonomous run completed. Analyzed {invoices_analyzed} accounts: "
        f"{actions_executed} automated actions executed, {approvals_pending} new cases queued for Human Approval."
    )

    log_agent_action(
        db,
        session_id,
        "AUTONOMOUS_BATCH_COMPLETED",
        "run_autonomous_workflow",
        {"invoices_analyzed": invoices_analyzed},
        {"actions_executed": actions_executed, "approvals_pending": approvals_pending},
        status="SUCCESS",
    )

    return {
        "status": "COMPLETED",
        "invoices_analyzed": invoices_analyzed,
        "actions_executed": actions_executed,
        "approvals_pending": approvals_pending,
        "summary": summary,
        "action_logs": action_logs,
    }
