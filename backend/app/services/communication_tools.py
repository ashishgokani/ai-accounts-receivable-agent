"""
Universal Communication Tools for Autonomous Accounts Receivable Operations.

Dispatches tailored communications to either a single debtor or a filtered cohort
(e.g., all active customers for greetings/announcements, overdue debtors, high risk accounts).
Supports pooled SMTP sessions for ultra-fast bulk dispatches.
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.currency import format_inr
from app.db.models import Customer, Invoice
from app.services.penalty_engine import sync_invoice_financials, calculate_days_overdue
from app.services.email_service import EmailService, sanitize_email_placeholders_and_signoff

logger = logging.getLogger(__name__)


def _render_comm_template(
    template: str,
    customer_name: str,
    company_name: str,
    invoice_number: str = "N/A",
    amount_str: str = "₹0",
    penalty_str: str = "₹0",
    total_str: str = "₹0",
    due_date_str: str = "N/A",
    days_overdue_str: str = "0",
) -> str:
    """Safely renders customer communication template variables and purges placeholders."""
    rendered = (
        template.replace("{customer_name}", customer_name)
        .replace("{company_name}", company_name)
        .replace("{invoice_number}", invoice_number)
        .replace("{amount}", amount_str)
        .replace("{penalty_amount}", penalty_str)
        .replace("{total_amount}", total_str)
        .replace("{due_date}", due_date_str)
        .replace("{days_overdue}", days_overdue_str)
    )
    return sanitize_email_placeholders_and_signoff(rendered)


def tool_send_custom_communication(
    db: Session,
    subject: str,
    message_body: str,
    target_criteria: Optional[Dict[str, Any]] = None,
    customer_id: Optional[str] = None,
    invoice_id: Optional[str] = None,
    comm_type: str = "CUSTOM_COMMUNICATION",
) -> Dict[str, Any]:
    """
    Universal Communication Primitive.
    Dispatches tailored communications to either a single debtor or a filtered cohort
    (e.g., all active customers for festival greetings, or debtors with overdue invoices).
    
    Supports template variables:
    {customer_name}, {company_name}, {invoice_number}, {amount}, {penalty_amount},
    {total_amount}, {due_date}, {days_overdue}.
    """
    target_criteria = target_criteria or {}
    dispatches = []

    # Communication routing: customer-level (e.g. general communications, announcements, greetings, notices)
    # vs. invoice-level (collection notices tied to specific invoices or overdue aging thresholds)
    is_invoice_level = bool(
        invoice_id
        or target_criteria.get("invoice_id")
        or target_criteria.get("min_days_overdue") is not None
        or target_criteria.get("min_days") is not None
        or target_criteria.get("min_balance") is not None
        or target_criteria.get("min_amount") is not None
        or target_criteria.get("has_pending_balance") is True
    )
    is_customer_level = not is_invoice_level

    # Pre-open pooled SMTP connection to deliver all customer notices in seconds without connection churn
    smtp_session = None
    from app.core.config import settings
    if settings.email_provider == "smtp" and settings.smtp_user and settings.smtp_password:
        try:
            import smtplib
            smtp_session = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            smtp_session.starttls()
            smtp_session.login(settings.smtp_user, settings.smtp_password)
        except Exception as smtp_conn_err:
            logger.warning("Could not pre-open shared SMTP session for custom communication: %s", smtp_conn_err)
            smtp_session = None

    try:
        if is_customer_level:
            cust_query = db.query(Customer)
            if customer_id:
                cust_query = cust_query.filter(Customer.customer_id == customer_id)
            elif target_criteria.get("customer_id"):
                cust_query = cust_query.filter(Customer.customer_id == target_criteria["customer_id"])
            elif target_criteria.get("company_name"):
                comp = str(target_criteria["company_name"]).strip()
                exact = cust_query.filter(Customer.company_name.ilike(comp)).all()
                if exact:
                    cust_query = cust_query.filter(Customer.company_name.ilike(comp))
                else:
                    cust_query = cust_query.filter(Customer.company_name.ilike(f"%{comp}%"))

            status_filter = target_criteria.get("status")
            if status_filter:
                if isinstance(status_filter, list):
                    st_list = [s.upper() for s in status_filter if s.upper() != "ALL"]
                    if st_list:
                        cust_query = cust_query.filter(Customer.status.in_(st_list))
                elif status_filter.upper() != "ALL":
                    cust_query = cust_query.filter(Customer.status == status_filter.upper())
            else:
                cust_query = cust_query.filter(Customer.status == "ACTIVE")

            if target_criteria.get("risk_level"):
                cust_query = cust_query.filter(Customer.risk_level == target_criteria["risk_level"])

            target_customers = cust_query.all()
            for cust in target_customers:
                c_name = cust.name or cust.company_name
                rend_subj = _render_comm_template(subject, c_name, cust.company_name)
                rend_body = _render_comm_template(message_body, c_name, cust.company_name)

                send_res = EmailService.send_customer_email(
                    db=db,
                    customer_id=cust.customer_id,
                    invoice_id=None,
                    subject=rend_subj,
                    message=rend_body,
                    comm_type=comm_type,
                    direction="OUTGOING",
                    smtp_server=smtp_session,
                )

                dispatches.append({
                    "customer": cust.company_name,
                    "invoice_number": "N/A",
                    "total_amount": 0.0,
                    "days_overdue": 0,
                    "recipient": cust.email,
                    "delivery_status": send_res.get("status", "SENT"),
                })
        else:
            # Invoice-level target resolution
            query = db.query(Invoice).join(Customer)
            if invoice_id:
                query = query.filter(Invoice.invoice_id == invoice_id)
            elif customer_id:
                query = query.filter(Invoice.customer_id == customer_id)
            else:
                if target_criteria.get("invoice_id"):
                    query = query.filter(Invoice.invoice_id == target_criteria["invoice_id"])
                elif target_criteria.get("customer_id"):
                    query = query.filter(Invoice.customer_id == target_criteria["customer_id"])
                elif target_criteria.get("company_name"):
                    query = query.filter(Customer.company_name.ilike(f"%{target_criteria['company_name']}%"))

                status_filter = target_criteria.get("status")
                if status_filter:
                    if isinstance(status_filter, list):
                        cust_st = [s.upper() for s in status_filter if s.upper() in ("ACTIVE", "ARCHIVED")]
                        if cust_st:
                            query = query.filter(Customer.status.in_(cust_st))
                        inv_st = [s.upper() for s in status_filter if s.upper() not in ("ACTIVE", "ARCHIVED", "ALL")]
                        if inv_st:
                            query = query.filter(Invoice.status.in_(inv_st))
                    else:
                        st_upper = status_filter.upper()
                        if st_upper in ("ACTIVE", "ARCHIVED"):
                            query = query.filter(Customer.status == st_upper)
                        elif st_upper != "ALL":
                            query = query.filter(Invoice.status == status_filter)
                elif target_criteria.get("has_pending_balance", True):
                    query = query.filter(Invoice.status.in_(["PENDING", "OVERDUE"]))

                if target_criteria.get("risk_level"):
                    query = query.filter(Customer.risk_level == target_criteria["risk_level"])

            target_invoices = query.all()

            # If no invoices match but a customer_id was specified
            if not target_invoices and (customer_id or target_criteria.get("customer_id")):
                c_id = customer_id or target_criteria.get("customer_id")
                cust = db.query(Customer).filter(Customer.customer_id == c_id).first()
                if cust:
                    c_name = cust.name or cust.company_name
                    rend_subj = _render_comm_template(subject, c_name, cust.company_name)
                    rend_body = _render_comm_template(message_body, c_name, cust.company_name)
                    send_res = EmailService.send_customer_email(
                        db=db,
                        customer_id=cust.customer_id,
                        invoice_id=None,
                        subject=rend_subj,
                        message=rend_body,
                        comm_type=comm_type,
                        direction="OUTGOING",
                        smtp_server=smtp_session,
                    )
                    dispatches.append({
                        "customer": cust.company_name,
                        "invoice_number": "N/A",
                        "recipient": cust.email,
                        "delivery_status": send_res.get("status", "SENT"),
                    })

            seen_customer_recipients = set()
            is_broadcast = comm_type.lower() in ("festival_greeting", "announcement", "offer", "greeting", "custom_communication") and not target_criteria.get("invoice_id")

            for inv in target_invoices:
                if is_broadcast and inv.customer_id in seen_customer_recipients:
                    continue

                sync_invoice_financials(inv, db)
                days = calculate_days_overdue(inv.due_date)

                min_days = target_criteria.get("min_days_overdue") or target_criteria.get("min_days")
                if min_days is not None and days < int(min_days):
                    continue

                min_amt = target_criteria.get("min_amount") or target_criteria.get("min_balance")
                if min_amt is not None and inv.total_amount < float(min_amt):
                    continue

                c_name = inv.customer.name or inv.customer.company_name
                rend_subj = _render_comm_template(
                    subject, c_name, inv.customer.company_name,
                    invoice_number=inv.invoice_number,
                    amount_str=format_inr(inv.amount),
                    penalty_str=format_inr(inv.penalty_amount),
                    total_str=format_inr(inv.total_amount),
                    due_date_str=inv.due_date.strftime("%d %B %Y"),
                    days_overdue_str=str(days),
                )
                rend_body = _render_comm_template(
                    message_body, c_name, inv.customer.company_name,
                    invoice_number=inv.invoice_number,
                    amount_str=format_inr(inv.amount),
                    penalty_str=format_inr(inv.penalty_amount),
                    total_str=format_inr(inv.total_amount),
                    due_date_str=inv.due_date.strftime("%d %B %Y"),
                    days_overdue_str=str(days),
                )

                send_res = EmailService.send_customer_email(
                    db=db,
                    customer_id=inv.customer_id,
                    invoice_id=inv.invoice_id,
                    subject=rend_subj,
                    message=rend_body,
                    comm_type=comm_type,
                    direction="OUTGOING",
                    smtp_server=smtp_session,
                )

                seen_customer_recipients.add(inv.customer_id)
                dispatches.append({
                    "customer": inv.customer.company_name,
                    "invoice_number": inv.invoice_number,
                    "total_amount": inv.total_amount,
                    "days_overdue": days,
                    "recipient": inv.customer.email,
                    "delivery_status": send_res.get("status", "SENT"),
                })
    finally:
        if smtp_session:
            try:
                smtp_session.quit()
            except Exception:
                pass

    return {
        "status": "SUCCESS" if dispatches else "NO_RECIPIENTS_MATCHED",
        "total_dispatched": len(dispatches),
        "comm_type": comm_type,
        "subject": subject,
        "dispatches": dispatches,
        "summary": f"Dispatched {len(dispatches)} communications ({comm_type}) to matching recipients.",
    }
