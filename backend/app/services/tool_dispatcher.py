"""
Centralized Tool Execution and Dispatch Engine.

Routes reasoning agent tool calls to their respective business services,
validates input boundaries, catches runtime anomalies, and maintains
an immutable audit log in PostgreSQL.
"""

import logging
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from app.services.tools import (
    tool_get_overdue_invoices,
    tool_get_invoice_details,
    tool_get_customer_history,
    tool_draft_reminder_email,
    tool_send_email,
    tool_update_invoice_status,
    tool_create_escalation,
    tool_record_payment,
    log_agent_action,
)
from app.services.tools_crud import (
    tool_create_customer,
    tool_list_customers,
    tool_remove_customer,
    tool_create_invoice,
    tool_send_bulk_settlement_offer,
    tool_send_custom_communication,
)
from app.services.commitments_service import (
    tool_grant_grace_period,
    tool_revoke_commitment,
)
from app.services.tools_history import (
    tool_get_communication_history,
    tool_get_invoice_commitments,
)
from app.services.tools_management import (
    tool_update_customer_profile,
    tool_update_invoice_data,
    tool_trigger_automation_cycle,
    tool_get_pending_approvals,
    tool_review_approval_decision,
    tool_get_financial_portfolio_summary,
    tool_get_agent_audit_logs,
)

logger = logging.getLogger(__name__)


def dispatch_tool_call(
    db: Session,
    tool_name: str,
    tool_input: Dict[str, Any],
    session_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Executes a single agent tool invocation against backend database services.

    Args:
        db: Active SQLAlchemy database session.
        tool_name: Registered name of the tool (e.g. 'get_overdue_invoices').
        tool_input: Dictionary of parameters passed by the reasoning model.
        session_id: Optional session identifier for audit logging.

    Returns:
        Tuple[Dict[str, Any], str]: A pair of (raw_output_data, human_readable_summary).
    """
    t_output: Dict[str, Any] = {}
    summary: str = ""

    try:
        # 1. Read & Query Tools
        if tool_name == "get_overdue_invoices":
            min_days = int(tool_input.get("min_days", 0))
            limit = int(tool_input.get("limit", 20))
            t_output = tool_get_overdue_invoices(db, min_days=min_days, limit=limit)
            count = t_output.get("total_found", len(t_output.get("invoices", [])))
            summary = f"Retrieved {count} overdue account records from database."

        elif tool_name == "get_invoice_details":
            inv_id = str(tool_input.get("invoice_id", "")).strip()
            t_output = tool_get_invoice_details(db, inv_id)
            summary = f"Loaded invoice details for {inv_id}."

        elif tool_name == "list_customers":
            status = tool_input.get("status", "ACTIVE")
            risk_level = tool_input.get("risk_level")
            search = tool_input.get("search")
            limit = int(tool_input.get("limit", 50))
            t_output = tool_list_customers(db, status=status, risk_level=risk_level, search=search, limit=limit)
            summary = f"Retrieved {t_output.get('returned_count', 0)} customer records (Total: {t_output.get('total_customers', 0)})."

        elif tool_name == "get_customer_history":
            cust_id = str(tool_input.get("customer_id", "")).strip()
            t_output = tool_get_customer_history(db, cust_id)
            summary = f"Retrieved credit history for customer {cust_id}."

        elif tool_name == "get_communication_history":
            inv_id = tool_input.get("invoice_id")
            cust_id = tool_input.get("customer_id")
            limit = int(tool_input.get("limit", 10))
            t_output = tool_get_communication_history(db, customer_id=cust_id, invoice_id=inv_id, limit=limit)
            summary = f"Retrieved {t_output.get('total_found', 0)} communication audit records."

        elif tool_name == "get_invoice_commitments":
            inv_id = tool_input.get("invoice_id")
            cust_id = tool_input.get("customer_id")
            status = tool_input.get("status")
            limit = int(tool_input.get("limit", 10))
            t_output = tool_get_invoice_commitments(db, invoice_id=inv_id, customer_id=cust_id, status=status, limit=limit)
            summary = f"Retrieved {t_output.get('total_found', 0)} invoice commitments."

        # 2. Promotional Settlements & Communication Dispatches
        elif tool_name == "send_bulk_settlement_offer":
            discount_pct = float(tool_input.get("discount_percent", 0.1))
            hours = int(tool_input.get("hours_valid", 24))
            min_amt = float(tool_input["min_amount"]) if tool_input.get("min_amount") is not None else None
            custom_msg = tool_input.get("custom_message")
            res_mode = tool_input.get("resolution_mode")
            t_output = tool_send_bulk_settlement_offer(
                db=db,
                discount_percent=discount_pct,
                hours_valid=hours,
                min_amount=min_amt,
                custom_message=custom_msg,
                resolution_mode=res_mode,
                session_id=session_id,
            )
            summary = t_output.get("summary", "Processed settlement offers.")

        elif tool_name == "send_custom_communication":
            comm_type = tool_input.get("comm_type", "CUSTOM_COMMUNICATION")
            tc = dict(tool_input.get("target_criteria") or {})
            if "company_name" in tool_input and "company_name" not in tc:
                tc["company_name"] = tool_input["company_name"]
            if "customer" in tool_input and "company_name" not in tc:
                tc["company_name"] = tool_input["customer"]
            if "status" in tool_input and "status" not in tc:
                tc["status"] = tool_input["status"]
            cust_id = tool_input.get("customer_id") or tc.get("customer_id")
            inv_id = tool_input.get("invoice_id") or tc.get("invoice_id")
            t_output = tool_send_custom_communication(
                db=db,
                subject=tool_input.get("subject", "Notice Regarding Your Account"),
                message_body=tool_input.get("message_body", ""),
                target_criteria=tc,
                customer_id=cust_id,
                invoice_id=inv_id,
                comm_type=comm_type,
            )
            summary = t_output.get("summary", "Dispatched custom customer communications.")

        elif tool_name == "draft_reminder_email":
            inv_id = str(tool_input.get("invoice_id", "")).strip()
            level = int(tool_input.get("reminder_level", 1))
            tone = str(tool_input.get("tone", "polite"))
            custom_inst = tool_input.get("custom_instructions")
            t_output = tool_draft_reminder_email(
                db=db,
                invoice_id=inv_id,
                reminder_level=level,
                tone=tone,
                custom_instructions=custom_inst,
            )
            summary = f"Drafted payment reminder email for invoice {inv_id}."

        elif tool_name == "send_email":
            inv_id = str(tool_input.get("invoice_id", "")).strip()
            subj = str(tool_input.get("subject", "Urgent: Payment Reminder Regarding Your Account")).strip()
            body = str(tool_input.get("body", "")).strip()
            recip = tool_input.get("recipient")
            t_output = tool_send_email(
                db=db,
                invoice_id=inv_id,
                subject=subj,
                body=body,
                recipient=recip,
                session_id=session_id or "session-chat",
            )
            st = t_output.get("status")
            if st == "SENT":
                summary = f"Dispatched reminder email for invoice {inv_id}."
            elif st == "PENDING_APPROVAL":
                summary = f"Reminder for invoice {inv_id} queued for Human Review: {t_output.get('message')}."
            elif st == "BLOCKED_BY_GUARDRAIL":
                summary = f"Reminder for {inv_id} blocked: {t_output.get('reason')}."
            else:
                summary = t_output.get("message") or f"Processed email dispatch for {inv_id} ({st})."

        # 3. Commercial Agreements & Commitments
        elif tool_name == "grant_grace_period":
            inv_id = str(tool_input.get("invoice_id", "")).strip()
            days = int(tool_input.get("days", 7))
            reason = tool_input.get("reason", "Extension requested in chat")
            t_output = tool_grant_grace_period(db=db, invoice_id=inv_id, days=days, reason=reason)
            summary = t_output.get("message", f"Grace period granted for {inv_id}.")

        elif tool_name == "revoke_commitment":
            inv_id = tool_input.get("invoice_id")
            comm_type = tool_input.get("commitment_type")
            t_output = tool_revoke_commitment(db=db, invoice_id=inv_id, commitment_type=comm_type)
            summary = t_output.get("message", "Commitment revoked.")

        # 4. Standard Ledger & CRM Mutations
        elif tool_name == "create_customer":
            t_output = tool_create_customer(
                db=db,
                name=tool_input.get("name", "New Contact"),
                company_name=tool_input.get("company_name", "Corporate Client"),
                email=tool_input.get("email", ""),
                phone=tool_input.get("phone"),
                address=tool_input.get("address"),
                risk_level=tool_input.get("risk_level", "Low"),
            )
            summary = t_output.get("message", "Created customer profile.")

        elif tool_name == "remove_customer":
            t_output = tool_remove_customer(db=db, customer_id=tool_input.get("customer_id"))
            summary = t_output.get("message", "Removed customer profile.")

        elif tool_name == "create_invoice":
            t_output = tool_create_invoice(
                db=db,
                customer_id=tool_input.get("customer_id"),
                invoice_number=tool_input.get("invoice_number"),
                amount=float(tool_input.get("amount", 0.0)),
                due_date_str=tool_input.get("due_date"),
            )
            summary = t_output.get("message", "Created new invoice.")

        elif tool_name == "create_escalation":
            inv_id = tool_input.get("invoice_id")
            reason = tool_input.get("reason", "Escalation requested via chat.")
            t_output = tool_create_escalation(db, inv_id, reason)
            summary = f"Escalation queued for {inv_id}: {t_output.get('status')}"

        elif tool_name == "record_payment":
            inv_id = tool_input.get("invoice_id")
            amount = float(tool_input.get("amount", 0.0))
            method = tool_input.get("payment_method", "NEFT")
            ref = tool_input.get("reference_number")
            t_output = tool_record_payment(db, inv_id, amount, payment_method=method, reference_number=ref)
            summary = f"Recorded settlement for {inv_id}."

        elif tool_name == "update_invoice_status":
            inv_id = tool_input.get("invoice_id")
            status = tool_input.get("new_status")
            notes = tool_input.get("notes")
            t_output = tool_update_invoice_status(db, inv_id, status, notes)
            summary = f"Updated invoice {inv_id} status to {status}."

        elif tool_name == "update_customer_profile":
            t_output = tool_update_customer_profile(
                db=db,
                customer_id=str(tool_input.get("customer_id", "")),
                name=tool_input.get("name"),
                company_name=tool_input.get("company_name"),
                email=tool_input.get("email"),
                phone=tool_input.get("phone"),
                address=tool_input.get("address"),
                risk_level=tool_input.get("risk_level"),
                risk_score=tool_input.get("risk_score"),
            )
            summary = t_output.get("message", "Updated customer profile.")

        elif tool_name == "update_invoice_data":
            amt_val = float(tool_input["amount"]) if tool_input.get("amount") is not None else None
            t_output = tool_update_invoice_data(
                db=db,
                invoice_id=str(tool_input.get("invoice_id", "")),
                due_date=tool_input.get("due_date"),
                amount=amt_val,
                status=tool_input.get("status"),
                dispute_reason=tool_input.get("dispute_reason"),
                promised_payment_date=tool_input.get("promised_payment_date"),
            )
            summary = t_output.get("message", "Updated invoice data.")

        elif tool_name == "trigger_automation_cycle":
            t_output = tool_trigger_automation_cycle(db=db)
            summary = t_output.get("summary", "Executed autonomous cycle.")

        elif tool_name == "get_pending_approvals":
            t_output = tool_get_pending_approvals(db=db)
            summary = t_output.get("message", "Loaded pending approvals.")

        elif tool_name == "review_approval_decision":
            t_output = tool_review_approval_decision(
                db=db,
                approval_id=str(tool_input.get("approval_id", "")),
                decision=str(tool_input.get("decision", "APPROVED")),
                notes=tool_input.get("notes"),
            )
            summary = t_output.get("message", "Processed approval decision.")

        elif tool_name == "get_financial_portfolio_summary":
            t_output = tool_get_financial_portfolio_summary(db=db)
            summary = "Computed real-time financial portfolio KPIs."

        elif tool_name == "get_agent_audit_logs":
            limit = int(tool_input.get("limit", 10))
            t_output = tool_get_agent_audit_logs(db=db, limit=limit)
            summary = f"Retrieved {t_output.get('total_retrieved', 0)} agent audit logs."

        else:
            logger.warning("Unrecognized tool name requested: %s", tool_name)
            t_output = {"error": f"Tool '{tool_name}' is not recognized by the backend."}
            summary = f"Tool '{tool_name}' not recognized."

        # 5. Log audit action in database
        status_flag = "FAILED" if "error" in t_output else "SUCCESS"
        log_agent_action(db, session_id, "CHAT_TOOL_INVOCATION", tool_name, tool_input, t_output, status=status_flag)

    except Exception as exc:
        logger.error("Error executing tool %s: %s", tool_name, exc, exc_info=True)
        t_output = {"error": f"Tool execution failed: {str(exc)}"}
        summary = f"Error executing {tool_name}."
        log_agent_action(db, session_id, "CHAT_TOOL_INVOCATION", tool_name, tool_input, t_output, status="FAILED")

    return t_output, summary
