"""
Customer Management API Endpoints.

Provides directory search, payment reliability metrics, complete customer dossiers,
and secure lifecycle management (creation, soft-delete archiving with balance protection,
and account restoration).
"""

from typing import List, Optional
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.session import get_db
from app.db.models import Customer, Invoice, AgentAction
from app.schemas.schemas import CustomerResponse, CustomerCreate, CustomerUpdate

router = APIRouter(prefix="/api/customers", tags=["Customers"])


@router.get("", response_model=List[CustomerResponse])
def list_customers(
    status: Optional[str] = Query("ACTIVE", description="Filter by status: ACTIVE, ARCHIVED, or ALL"),
    risk: Optional[str] = Query(None, description="Filter by risk level: Low, Medium, High"),
    search: Optional[str] = Query(None, description="Search by name, company, or email"),
    db: Session = Depends(get_db),
):
    """Retrieves list of customers filtered by status, risk category, or search keyword."""
    query = db.query(Customer)

    if status and status.upper() != "ALL":
        query = query.filter(Customer.status == status.upper())

    if risk and risk.upper() != "ALL":
        query = query.filter(Customer.risk_level == risk.capitalize())

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(pattern))
            | (Customer.company_name.ilike(pattern))
            | (Customer.email.ilike(pattern))
        )

    return query.order_by(Customer.company_name.asc()).all()


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    """Retrieves detailed profile for an individual corporate customer."""
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")
    return cust


@router.post("", response_model=CustomerResponse, status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    """
    Onboards a new corporate debtor profile into the system with initial credit risk evaluation.
    """
    # 1. Verify email uniqueness
    existing = db.query(Customer).filter(Customer.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Customer with email {payload.email} already exists.")

    # 2. Determine new customer ID sequence
    total_count = db.query(Customer).count()
    new_id = f"CUST-{total_count + 101:03d}"

    # 3. Create record in PostgreSQL
    new_customer = Customer(
        customer_id=new_id,
        name=payload.name,
        company_name=payload.company_name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        risk_score=payload.risk_score,
        risk_level=payload.risk_level,
        status="ACTIVE",
        created_at=ist_naive_now(),
        updated_at=ist_naive_now(),
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: str, payload: CustomerUpdate, db: Session = Depends(get_db)):
    """Updates contact information, company address, or credit risk profiling."""
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(cust, field, val)

    cust.updated_at = ist_naive_now()
    db.commit()
    db.refresh(cust)
    return cust


@router.delete("/{customer_id}")
def remove_customer(customer_id: str, db: Session = Depends(get_db)):
    """
    Archives a customer to the Removed Section.
    STRICT BUSINESS GUARDRAIL: Customer can ONLY be removed if they have ZERO pending/unpaid invoices.
    """
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

    # Business Rule: Verify no unsettled invoices exist
    unsettled = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == customer_id,
            Invoice.status.in_(["PENDING", "OVERDUE", "PAYMENT_PROMISED", "DISPUTED"]),
        )
        .all()
    )

    if unsettled:
        inv_list = ", ".join(i.invoice_number for i in unsettled)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Customer '{cust.company_name}' cannot be removed because they have "
                f"{len(unsettled)} unsettled invoices ({inv_list}). "
                f"All pending dues must be settled or written off before removal."
            ),
        )

    # Perform soft-delete archive
    cust.status = "ARCHIVED"
    cust.updated_at = ist_naive_now()

    # Log audit entry
    action_log = AgentAction(
        action_id=f"ACT-{uuid.uuid4().hex[:6].upper()}",
        session_id="system-audit",
        action_type="CUSTOMER_ARCHIVED",
        tool_name="remove_customer",
        input_data=f'{{"customer_id": "{customer_id}"}}',
        output_data='{"status": "ARCHIVED"}',
        status="SUCCESS",
        created_at=ist_naive_now(),
    )
    db.add(action_log)
    db.commit()

    return {
        "status": "SUCCESS",
        "message": f"Customer '{cust.company_name}' successfully moved to Removed Section.",
        "customer_id": customer_id,
    }


@router.post("/{customer_id}/restore")
def restore_customer(customer_id: str, db: Session = Depends(get_db)):
    """Restores an archived customer back to Active status."""
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

    cust.status = "ACTIVE"
    cust.updated_at = ist_naive_now()
    db.commit()
    db.refresh(cust)

    return {
        "status": "SUCCESS",
        "message": f"Customer '{cust.company_name}' restored to Active status.",
        "customer": cust,
    }
