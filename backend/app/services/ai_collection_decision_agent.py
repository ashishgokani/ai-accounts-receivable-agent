"""
AI Collection Decision Agent.

Analyzes debtor context using Amazon Nova Pro before autonomous collection actions:
- Evaluates customer risk rating, overdue days, payment history, and commercial commitments.
- Recommends the optimal next collection action, communication tone, or settlement review.
- Strictly validates AI recommendations against enterprise financial guardrails on the backend.
- Consequential financial concessions (penalties, discounts, waivers) ALWAYS require human approval.
- Preserves deterministic Python execution fallback when LLM is unavailable.
"""

import json
import logging
import re
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import ist_naive_now, ist_today
from app.db.models import Invoice, Customer, Communication, InvoiceCommitment, Approval
from app.services.penalty_engine import calculate_days_overdue, determine_recommended_action
from app.services.bedrock_service import BedrockGateway
from app.services.commitments_service import has_active_hold_or_pause

logger = logging.getLogger(__name__)


def build_collection_context(db: Session, invoice: Invoice) -> Dict[str, Any]:
    """
    Assembles debtor profile, historical communications, and commitments for AI analysis.
    
    Args:
        db: SQLAlchemy database session.
        invoice: Invoice model instance.
        
    Returns:
        Dict[str, Any]: Consolidated debtor contextual snapshot.
    """
    cust = invoice.customer
    days_overdue = calculate_days_overdue(invoice.due_date)

    # 1. Recent communications sent to debtor (last 3 notices)
    comms = (
        db.query(Communication)
        .filter(Communication.customer_id == invoice.customer_id)
        .order_by(Communication.sent_at.desc())
        .limit(3)
        .all()
    )
    comm_history = [
        {
            "type": c.type,
            "subject": c.subject,
            "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        }
        for c in comms
    ]

    # 2. Active commercial commitments (payment promises, disputes, holds)
    commitments = (
        db.query(InvoiceCommitment)
        .filter(
            InvoiceCommitment.invoice_id == invoice.invoice_id,
            InvoiceCommitment.status == "ACTIVE",
        )
        .all()
    )
    active_commitments = [
        {
            "type": c.commitment_type,
            "description": c.description,
            "valid_until": c.valid_until.isoformat() if c.valid_until else None,
        }
        for c in commitments
    ]

    return {
        "invoice_id": invoice.invoice_id,
        "invoice_number": invoice.invoice_number,
        "original_amount": invoice.amount,
        "total_outstanding": invoice.total_amount,
        "penalty_amount": invoice.penalty_amount,
        "days_overdue": days_overdue,
        "reminder_count": invoice.reminder_count,
        "last_reminder_at": invoice.last_reminder_at.isoformat() if invoice.last_reminder_at else None,
        "status": invoice.status,
        "customer_name": cust.name if cust else "Valued Client",
        "company_name": cust.company_name if cust else "Corporate Debtor",
        "risk_level": cust.risk_level if cust else "Low",
        "payment_terms_days": getattr(cust, "payment_terms_days", 30) if cust else 30,
        "credit_limit": getattr(cust, "credit_limit", 100000.0) if cust else 100000.0,
        "recent_communications": comm_history,
        "active_commitments": active_commitments,
    }


def analyze_collection_strategy_with_ai(
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Queries Amazon Nova Pro to evaluate debtor context and recommend collection strategy.
    
    Args:
        context: Consolidated debtor snapshot.
        
    Returns:
        Dict[str, Any]: Structured AI recommendation (action, tone, rationale, concession).
    """
    if settings.use_mock_bedrock_fallback:
        return _deterministic_strategy_fallback(context)

    prompt = (
        f"You are the autonomous credit management and debt recovery reasoning agent for an enterprise.\n"
        f"Analyze this debtor account context and recommend the optimal collection strategy:\n\n"
        f"DEBTOR CONTEXT:\n"
        f"• Customer: {context['customer_name']} ({context['company_name']})\n"
        f"• Risk Rating: {context['risk_level']}\n"
        f"• Invoice: {context['invoice_number']} | Outstanding: ₹{context['total_outstanding']:,.2f}\n"
        f"• Overdue: {context['days_overdue']} days | Previous Reminders: {context['reminder_count']}\n"
        f"• Active Commitments: {json.dumps(context['active_commitments'])}\n"
        f"• Communications History: {json.dumps(context['recent_communications'])}\n\n"
        f"DECISION RULES:\n"
        f"1. If customer has an active payment promise or freeze, recommend HOLD_FOR_PROMISE.\n"
        f"2. If overdue < 7 days and 0 reminders sent, recommend FIRST_REMINDER (POLITE).\n"
        f"3. If overdue 7-20 days and 1 reminder sent, recommend SECOND_REMINDER (FIRM).\n"
        f"4. If overdue >= 25 days or reminder_count >= 3 or high balance, recommend ESCALATE_TO_ADMIN.\n"
        f"5. All financial concessions (discounts, waivers, payment plans) MUST require human managerial approval.\n\n"
        f"OUTPUT STRICTLY VALID JSON ONLY:\n"
        f"{{\n"
        f'  "recommended_action": "FIRST_REMINDER" | "SECOND_REMINDER" | "ESCALATE_TO_ADMIN" | "HOLD_FOR_PROMISE" | "OFFER_PAYMENT_PLAN",\n'
        f'  "tone": "POLITE" | "FIRM" | "URGENT",\n'
        f'  "confidence": 0.95,\n'
        f'  "concise_rationale": "1-2 sentence justification for this recommendation.",\n'
        f'  "propose_concession": false,\n'
        f'  "concession_details": null\n'
        f"}}"
    )

    try:
        gateway = BedrockGateway()
        if gateway.client:
            res = gateway.converse(
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                system_prompt="You are an enterprise AI collections reasoning agent. Output valid JSON strictly.",
            )
            raw_text = res.get("text", "")
            json_match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                # Validate expected keys
                if "recommended_action" in parsed and "concise_rationale" in parsed:
                    return parsed
    except Exception as exc:
        logger.warning("Bedrock collection strategy reasoning failed: %s. Falling back to deterministic rules.", exc)

    return _deterministic_strategy_fallback(context)


def _deterministic_strategy_fallback(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic rule-based fallback when AI engine is offline.
    """
    days = context["days_overdue"]
    count = context["reminder_count"]
    risk = context["risk_level"]

    if context.get("active_commitments"):
        return {
            "recommended_action": "HOLD_FOR_PROMISE",
            "tone": "POLITE",
            "confidence": 0.99,
            "concise_rationale": "Active commercial commitment or payment promise in effect.",
            "propose_concession": False,
            "concession_details": None,
        }

    if days <= 0:
        return {
            "recommended_action": "NO_ACTION",
            "tone": "POLITE",
            "confidence": 1.0,
            "concise_rationale": "Invoice is not currently overdue.",
            "propose_concession": False,
            "concession_details": None,
        }

    if days >= settings.escalation_overdue_days_threshold or count >= settings.max_reminders_before_escalation:
        return {
            "recommended_action": "ESCALATE_TO_ADMIN",
            "tone": "URGENT",
            "confidence": 0.92,
            "concise_rationale": f"Account is {days} days overdue with {count} previous notices. Senior review required.",
            "propose_concession": False,
            "concession_details": None,
        }

    if count == 0:
        return {
            "recommended_action": "FIRST_REMINDER",
            "tone": "POLITE",
            "confidence": 0.95,
            "concise_rationale": f"Initial courtesy reminder for {risk} Risk account.",
            "propose_concession": False,
            "concession_details": None,
        }

    return {
        "recommended_action": "SECOND_REMINDER",
        "tone": "FIRM",
        "confidence": 0.90,
        "concise_rationale": f"Follow-up reminder with late fee notice ({count} previous reminders dispatched).",
        "propose_concession": False,
        "concession_details": None,
    }


def evaluate_invoice_collection_decision(db: Session, invoice: Invoice) -> Dict[str, Any]:
    """
    Executes the AI Decision Agent step for an overdue invoice:
    1. Gathers complete debtor context.
    2. Runs Amazon Nova Pro semantic analysis.
    3. Enforces deterministic backend safety guardrails (approvals for concessions/escalations).
    
    Args:
        db: SQLAlchemy database session.
        invoice: Invoice model instance.
        
    Returns:
        Dict[str, Any]: Final validated action plan ready for execution.
    """
    # 1. Check if invoice is paused due to commercial agreement
    if has_active_hold_or_pause(db, invoice.invoice_id) or invoice.status == "PAYMENT_PROMISED":
        return {
            "action": "DEFER",
            "reason": "Active commercial hold or payment promise protects account from collection notices.",
            "requires_approval": False,
            "ai_rationale": "Commercial commitment is active in PostgreSQL.",
            "tone": "POLITE",
        }

    # 2. Gather debtor context and query Amazon Nova Pro
    context = build_collection_context(db, invoice)
    ai_rec = analyze_collection_strategy_with_ai(context)

    raw_action = ai_rec.get("recommended_action", "NO_ACTION").upper()
    rationale = ai_rec.get("concise_rationale", "Standard credit policy review.")
    tone = ai_rec.get("tone", "POLITE")
    propose_concession = ai_rec.get("propose_concession", False)

    # 3. Apply Backend Guardrail Verification
    requires_approval = False
    final_action = raw_action
    approval_type = None
    approval_details: Optional[Dict[str, Any]] = None

    # Guardrail 1: Any financial concession (discount, waiver, custom plan) MUST go to Human Approval
    if propose_concession:
        requires_approval = True
        final_action = "APPROVAL_REQUIRED"
        approval_type = "DISCOUNT_APPROVAL"
        approval_details = {
            "source": "AI_COLLECTION_AGENT",
            "invoice_number": invoice.invoice_number,
            "concession_proposal": ai_rec.get("concession_details"),
            "ai_rationale": rationale,
        }

    # Guardrail 2: Escalations or High-Value overdues require Human Approval
    elif raw_action in ("ESCALATE", "ESCALATE_TO_ADMIN") or (
        invoice.total_amount >= settings.high_value_approval_threshold and invoice.reminder_count >= 1
    ):
        requires_approval = True
        final_action = "ESCALATE"
        approval_type = "ESCALATE"
        approval_details = {
            "source": "AI_COLLECTION_AGENT",
            "invoice_number": invoice.invoice_number,
            "days_overdue": context["days_overdue"],
            "amount": invoice.total_amount,
            "ai_rationale": rationale,
        }

    elif raw_action == "HOLD_FOR_PROMISE":
        final_action = "DEFER"

    return {
        "action": final_action,
        "tone": tone,
        "requires_approval": requires_approval,
        "approval_type": approval_type,
        "approval_details": approval_details,
        "ai_rationale": rationale,
        "confidence": ai_rec.get("confidence", 0.9),
        "days_overdue": context["days_overdue"],
    }
