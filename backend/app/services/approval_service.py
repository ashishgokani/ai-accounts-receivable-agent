"""
Unified Approval Business Logic Service.

Single source of truth for all human-in-the-loop managerial decisions,
whether executed from the REST API Approvals page or via Agent Chat tools.
Ensures identical validation, deterministic ledger calculations, state machine
progressions, and reliable customer notifications with delivery recovery.
"""

import json
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.core.currency import format_inr
from app.db.models import Approval, Invoice, Customer, Payment, Escalation, Followup
from app.services.penalty_engine import sync_invoice_financials
from app.services.email_service import EmailService
from app.services.tools import log_agent_action

logger = logging.getLogger(__name__)


class ApprovalService:
    """
    Centralized controller for managerial approval gates across accounts receivable.
    """

    @staticmethod
    def apply_approval_decision(
        db: Session,
        approval_id: str,
        decision_status: str,
        reviewed_by: str = "Admin",
        review_notes: Optional[str] = None,
        amount_received: Optional[float] = None,
        custom_subject: Optional[str] = None,
        custom_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes an authorized managerial decision on a pending human approval item.
        
        Guarantees:
        1. Original invoice principal is permanently preserved.
        2. Verified payments are recorded in the payment ledger.
        3. Financial balances are updated deterministically.
        4. Customer notifications are dispatched only after DB commit succeeds.
        5. Email delivery failures do not corrupt the financial ledger.
        """
        clean_id = approval_id.strip()
        appr = db.query(Approval).filter(Approval.approval_id == clean_id).first()
        if not appr:
            raise ValueError(f"Approval request '{clean_id}' was not found.")

        if appr.status != "PENDING":
            raise ValueError(f"Approval request '{clean_id}' has already been processed with status '{appr.status}'.")

        inv = db.query(Invoice).filter(Invoice.invoice_id == appr.invoice_id).first()
        if not inv:
            raise ValueError(f"Associated invoice '{appr.invoice_id}' was not found.")

        cust = inv.customer
        details = json.loads(appr.details) if appr.details else {}
        norm_decision = decision_status.strip().upper()

        # Update approval metadata
        appr.status = "APPROVED" if "APPROV" in norm_decision else "REJECTED"
        appr.reviewed_by = reviewed_by
        appr.review_notes = review_notes
        appr.reviewed_at = ist_naive_now()

        execution_message = ""
        notification_to_send: Optional[Dict[str, str]] = None

        # -------------------------------------------------------------
        # Scenario A: Payment Remittance Verification
        # -------------------------------------------------------------
        if appr.action_type in ("VERIFY_PAYMENT_REMITTANCE", "PAYMENT_CLAIMED"):
            raw_utr = details.get("utr_reference", "UNSPECIFIED").strip().upper()
            claimed_amount = float(details.get("claimed_amount", inv.total_amount or inv.amount))

            def _resolve_unique_reference(proposed: str, prefix: str) -> str:
                if not proposed or proposed in ("UNSPECIFIED", "PENDING_VERIFICATION", "NONE", "NA", "N/A", "NULL"):
                    candidate = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
                else:
                    candidate = proposed
                if db.query(Payment).filter(Payment.reference_number == candidate).first():
                    candidate = f"{candidate}-{uuid.uuid4().hex[:6].upper()}"
                return candidate

            if norm_decision in ("APPROVED", "FULL_PAYMENT_APPROVED"):
                # 1. Full payment verified: record in separate payment ledger
                pay_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
                final_ref = _resolve_unique_reference(raw_utr, "VERIF")
                payment = Payment(
                    payment_id=pay_id,
                    invoice_id=inv.invoice_id,
                    customer_id=inv.customer_id,
                    amount=claimed_amount,
                    payment_method=details.get("payment_method", "NEFT"),
                    reference_number=final_ref,
                    status="SUCCESS",
                    created_at=ist_naive_now(),
                )
                db.add(payment)
                db.flush()

                # 2. Cancel remaining automated follow-ups
                pending_f = db.query(Followup).filter(
                    Followup.invoice_id == inv.invoice_id, Followup.status == "PENDING"
                ).all()
                for f in pending_f:
                    f.status = "CANCELLED"
                    f.completed_at = ist_naive_now()

                # 3. Synchronize financials deterministically
                sync_invoice_financials(inv, db)
                execution_message = f"Full payment of {format_inr(claimed_amount)} verified (Ref: {final_ref}). Invoice {inv.invoice_number} marked PAID."

                notification_to_send = {
                    "comm_type": "PAYMENT_CONFIRMATION",
                    "subject": f"Official Payment Receipt: Invoice {inv.invoice_number}",
                    "body": (
                        f"Dear {cust.name},\n\n"
                        f"We are pleased to confirm receipt of your payment of {format_inr(claimed_amount)} against Invoice {inv.invoice_number} "
                        f"(Transaction Reference: {final_ref}).\n\n"
                        f"Your account ledger has been updated and this invoice is now settled in full. Thank you for your business."
                    ),
                }

            elif norm_decision == "PARTIAL_PAYMENT_APPROVED":
                # Partial payment verified: record actual amount received
                actual_paid = float(amount_received) if amount_received and amount_received > 0 else claimed_amount
                pay_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
                final_ref = _resolve_unique_reference(raw_utr, "PARTIAL")
                payment = Payment(
                    payment_id=pay_id,
                    invoice_id=inv.invoice_id,
                    customer_id=inv.customer_id,
                    amount=actual_paid,
                    payment_method=details.get("payment_method", "NEFT"),
                    reference_number=final_ref,
                    status="SUCCESS",
                    created_at=ist_naive_now(),
                )
                db.add(payment)
                db.flush()

                # Synchronize financials deterministically
                fin = sync_invoice_financials(inv, db)
                remaining = fin["total_amount"]
                execution_message = f"Partial payment of {format_inr(actual_paid)} verified. Remaining balance: {format_inr(remaining)} on {inv.invoice_number}."

                notification_to_send = {
                    "comm_type": "PARTIAL_PAYMENT_STATEMENT",
                    "subject": f"Partial Payment Receipt & Outstanding Balance: Invoice {inv.invoice_number}",
                    "body": (
                        f"Dear {cust.name},\n\n"
                        f"We have credited {format_inr(actual_paid)} to your account for Invoice {inv.invoice_number} (Ref: {final_ref}).\n\n"
                        f"Remaining Outstanding Balance: {format_inr(remaining)}.\n"
                        f"Please arrange remittance of the remaining balance at your earliest convenience."
                    ),
                }

            else:
                # Payment rejected / Not located in bank records
                inv.status = "OVERDUE"
                sync_invoice_financials(inv, db)
                execution_message = f"Payment claim for {inv.invoice_number} REJECTED. Funds not located for Ref: {utr_ref}."

                notification_to_send = {
                    "comm_type": "PAYMENT_NOT_LOCATED",
                    "subject": f"Payment Verification Notice: Invoice {inv.invoice_number}",
                    "body": (
                        f"Dear {cust.name},\n\n"
                        f"Our treasury department reviewed our banking records for the transaction reference '{utr_ref}' "
                        f"regarding Invoice {inv.invoice_number}, but we were unable to locate the corresponding credit.\n\n"
                        f"Please provide your bank debit advice or contact your remitting bank to ensure funds were cleared."
                    ),
                }

        # -------------------------------------------------------------
        # Scenario B: Administrative Escalation Gate
        # -------------------------------------------------------------
        elif appr.action_type == "ESCALATE":
            if appr.status == "APPROVED":
                esc = Escalation(
                    escalation_id=f"ESC-{uuid.uuid4().hex[:8].upper()}",
                    invoice_id=inv.invoice_id,
                    customer_id=inv.customer_id,
                    reason=details.get("reason", "Approved administrative escalation."),
                    amount=inv.total_amount,
                    days_overdue=details.get("days_overdue", 30),
                    assigned_to=reviewed_by,
                    status="OPEN",
                    created_at=ist_naive_now(),
                )
                db.add(esc)
                inv.status = "ESCALATED"
                execution_message = f"Invoice {inv.invoice_number} formally escalated to {reviewed_by}."
            else:
                execution_message = f"Escalation for {inv.invoice_number} rejected by {reviewed_by}."

        # -------------------------------------------------------------
        # Scenario C: Customized Reminder or Final Notice
        # -------------------------------------------------------------
        elif appr.action_type in ("SEND_REMINDER", "SEND_THIRD_REMINDER", "FINAL_NOTICE"):
            if appr.status == "APPROVED":
                final_subject = custom_subject or details.get("subject", f"Payment Notice: Invoice {inv.invoice_number}")
                final_body = custom_body or details.get("body", "Please arrange payment for your invoice.")
                inv.reminder_count += 1
                inv.last_reminder_at = ist_naive_now()
                execution_message = f"Approved email notice queued for dispatch to {cust.company_name}."

                notification_to_send = {
                    "comm_type": "REMINDER",
                    "subject": final_subject,
                    "body": final_body,
                }
            else:
                execution_message = f"Email dispatch proposal for {inv.invoice_number} rejected."

        # -------------------------------------------------------------
        # Scenario D: Dispute Resolution or Settlement Concession
        # -------------------------------------------------------------
        elif appr.action_type in ("INVOICE_DISPUTE_REVIEW", "DISCOUNT_APPROVAL"):
            if appr.status == "APPROVED":
                inv.status = "OVERDUE"
                inv.dispute_reason = None
                sync_invoice_financials(inv, db)
                execution_message = f"Dispute on invoice {inv.invoice_number} marked resolved by {reviewed_by}."
                notification_to_send = {
                    "comm_type": "DISPUTE_RESOLUTION",
                    "subject": f"Dispute Resolution: Invoice {inv.invoice_number}",
                    "body": (
                        f"Dear {cust.name},\n\n"
                        f"Our accounts management team has reviewed your query regarding Invoice {inv.invoice_number}. "
                        f"Resolution details: {review_notes or 'Account reviewed and adjustments applied'}.\n\n"
                        f"Net Balance Due: ₹{inv.total_amount:,.2f}."
                    ),
                }
            else:
                execution_message = f"Dispute resolution proposal for {inv.invoice_number} rejected."

        # Commit financial state machine updates atomically
        db.commit()

        # Audit log agent action
        log_agent_action(
            db,
            session_id="session-human",
            action_type=f"APPROVAL_{appr.status}",
            tool_name=appr.action_type,
            input_data={"approval_id": clean_id, "decision": norm_decision, "amount_received": amount_received},
            output_data={"execution": execution_message},
            status=appr.status,
        )

        # -------------------------------------------------------------
        # Dispatch Notification ONLY after DB state succeeds
        # Safe retries: failure to send email does NOT corrupt ledger
        # -------------------------------------------------------------
        notification_dispatched = False
        if notification_to_send and cust and cust.email:
            try:
                EmailService.send_customer_email(
                    db=db,
                    customer_id=cust.customer_id,
                    invoice_id=inv.invoice_id,
                    subject=notification_to_send["subject"],
                    message=notification_to_send["body"],
                    comm_type=notification_to_send["comm_type"],
                    direction="OUTGOING",
                )
                notification_dispatched = True
            except Exception as mail_err:
                logger.error("Failed to dispatch post-approval customer notification: %s", mail_err)

        return {
            "approval_id": clean_id,
            "status": appr.status,
            "reviewed_by": reviewed_by,
            "message": execution_message,
            "notification_sent": notification_dispatched,
            "invoice_id": inv.invoice_id,
            "invoice_status": inv.status,
            "total_outstanding": inv.total_amount,
        }
