"""
Interactive Simulation API Endpoints for Demonstrations and Viva Testing.

Enables simulating real-time external events such as incoming customer emails,
promising payment dates, disputes, and payment settlements.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import SimulateReplyRequest, PaymentCreate
from app.services.simulation_service import process_incoming_customer_reply
from app.services.tools import tool_record_payment

router = APIRouter(prefix="/api/simulation", tags=["Simulation & Demo"])


@router.post("/customer-reply")
def simulate_customer_reply(payload: SimulateReplyRequest, db: Session = Depends(get_db)):
    """
    Simulates receiving an inbound email from a customer regarding an invoice.
    Triggers intent classification (PAYMENT_PROMISED, DISPUTED, etc.) and executes
    downstream database transitions.
    """
    result = process_incoming_customer_reply(
        db=db,
        invoice_id=payload.invoice_id,
        reply_text=payload.reply_message,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/record-payment")
def simulate_payment_settlement(payload: PaymentCreate, db: Session = Depends(get_db)):
    """
    Simulates recording a customer payment.
    Marks invoice as PAID, resets late penalties, auto-cancels pending followups,
    and dispatches a formal payment confirmation receipt.
    """
    result = tool_record_payment(
        db=db,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        reference_number=payload.reference_number,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
