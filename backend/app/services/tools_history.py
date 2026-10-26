"""
Communication History and Invoice Commitment Audit Tools.

Provides read-only query utilities for the Autonomous Accounts Receivable Agent
to inspect past sent emails, customer notices, commercial commitments,
early settlement discount offers, and payment extensions.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import Communication, InvoiceCommitment, Invoice, Customer

logger = logging.getLogger(__name__)


def tool_get_communication_history(
    db: Session,
    customer_id: Optional[str] = None,
    invoice_id: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Retrieves chronological dispatch records for customer emails and notices.

    Args:
        db: Active SQLAlchemy database session.
        customer_id: Optional customer identifier to filter dispatches.
        invoice_id: Optional invoice identifier to filter dispatches.
        limit: Maximum number of recent communications to return (default: 10, max: 50).

    Returns:
        Dict[str, Any]: Dictionary containing total count and list of communication records.
    """
    try:
        # 1. Cap limit to prevent large payloads
        bounded_limit = min(max(1, limit), 50)

        # 2. Build base query ordered by most recent dispatches first
        query = db.query(Communication).order_by(desc(Communication.sent_at))

        # 3. Apply optional invoice filter
        if invoice_id:
            clean_inv = invoice_id.strip().upper()
            # Support both INV-1004 and INV-2026-1004 matching
            query = query.filter(
                (Communication.invoice_id == clean_inv) |
                (Communication.invoice_id.ilike(f"%{clean_inv}%"))
            )

        # 4. Apply optional customer filter
        if customer_id:
            query = query.filter(Communication.customer_id == customer_id.strip())

        records = query.limit(bounded_limit).all()

        # 5. Serialize into agent-friendly JSON structures
        results: List[Dict[str, Any]] = []
        for r in records:
            results.append({
                "communication_id": r.communication_id,
                "invoice_id": r.invoice_id,
                "customer_id": r.customer_id,
                "customer_name": r.customer.company_name if r.customer else None,
                "type": r.type,
                "direction": r.direction,
                "subject": r.subject,
                "message_snippet": (r.message[:200] + "...") if len(r.message) > 200 else r.message,
                "intent": r.intent,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            })

        return {
            "total_found": len(results),
            "filters": {"invoice_id": invoice_id, "customer_id": customer_id},
            "communications": results,
        }
    except Exception as exc:
        logger.error("Failed to query communication history: %s", exc, exc_info=True)
        return {"error": f"Failed to retrieve communication history: {str(exc)}", "total_found": 0, "communications": []}


def tool_get_invoice_commitments(
    db: Session,
    invoice_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Retrieves active or past commercial commitments (discounts, grace periods, promises).

    Args:
        db: Active SQLAlchemy database session.
        invoice_id: Optional invoice identifier to filter records.
        customer_id: Optional customer identifier to filter records.
        status: Optional commitment status (ACTIVE, EXPIRED, REVOKED, FULFILLED).
        limit: Maximum number of commitments to return (default: 10).

    Returns:
        Dict[str, Any]: Dictionary containing total count and list of commitment details.
    """
    try:
        bounded_limit = min(max(1, limit), 50)
        query = db.query(InvoiceCommitment).order_by(desc(InvoiceCommitment.created_at))

        # 1. Apply optional filters
        if invoice_id:
            clean_inv = invoice_id.strip().upper()
            query = query.filter(
                (InvoiceCommitment.invoice_id == clean_inv) |
                (InvoiceCommitment.invoice_id.ilike(f"%{clean_inv}%"))
            )

        if customer_id:
            query = query.filter(InvoiceCommitment.customer_id == customer_id.strip())

        if status:
            query = query.filter(InvoiceCommitment.status == status.strip().upper())

        records = query.limit(bounded_limit).all()

        # 2. Serialize into friendly JSON
        results: List[Dict[str, Any]] = []
        for c in records:
            results.append({
                "commitment_id": c.commitment_id,
                "invoice_id": c.invoice_id,
                "customer_id": c.customer_id,
                "commitment_type": c.commitment_type,
                "description": c.description,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "valid_until": c.valid_until.isoformat() if c.valid_until else None,
            })

        return {
            "total_found": len(results),
            "filters": {"invoice_id": invoice_id, "customer_id": customer_id, "status": status},
            "commitments": results,
        }
    except Exception as exc:
        logger.error("Failed to query invoice commitments: %s", exc, exc_info=True)
        return {"error": f"Failed to retrieve commitments: {str(exc)}", "total_found": 0, "commitments": []}
