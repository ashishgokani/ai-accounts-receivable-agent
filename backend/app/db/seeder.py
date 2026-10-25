"""
Realistic Seed Data Generator for Accounts Receivable Management.

Populates initial enterprise customers, realistic multi-stage overdue invoices
in Indian Rupees (₹), historical payment confirmations, and communication threads
specifically tailored for viva demonstrations.
"""

from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from app.core.timezone import ist_today, ist_naive_now
from app.db.models import (
    Customer,
    Invoice,
    Payment,
    Communication,
    Followup,
    Escalation,
    AgentAction,
    Approval,
)
from app.db.session import SessionLocal, Base, engine


def seed_database(db: Session) -> None:
    """
    Populates database with complete Accounts Receivable test scenarios
    if tables are currently empty.
    
    Args:
        db: Active SQLAlchemy database session.
    """
    # Check if database already contains records
    if db.query(Customer).first():
        return

    today = ist_today()

    # 1. Seed Enterprise Customers
    customers_data = [
        Customer(
            customer_id="CUST-001",
            name="Rajesh Sharma",
            company_name="ABC Ltd",
            email="finance@abcltd.com",
            phone="+91 98201 12345",
            address="402 Nariman Point, Mumbai, Maharashtra",
            risk_score=28,
            risk_level="Low",
            status="ACTIVE",
        ),
        Customer(
            customer_id="CUST-002",
            name="Vikram Mehta",
            company_name="XYZ Enterprises",
            email="ap@xyzltd.io",
            phone="+91 98450 23456",
            address="12 MG Road, Bengaluru, Karnataka",
            risk_score=15,
            risk_level="Low",
            status="ACTIVE",
        ),
        Customer(
            customer_id="CUST-003",
            name="Neha Kapoor",
            company_name="NovaTech Solutions",
            email="billing@novatech.ai",
            phone="+91 97110 34567",
            address="Cyber City, Gurugram, Haryana",
            risk_score=45,
            risk_level="Medium",
            status="ACTIVE",
        ),
        Customer(
            customer_id="CUST-004",
            name="Suresh Agarwal",
            company_name="Helios Retail Corp",
            email="accounts@helios.co",
            phone="+91 99880 45678",
            address="Salt Lake Sector V, Kolkata, West Bengal",
            risk_score=85,
            risk_level="High",
            status="ACTIVE",
        ),
        Customer(
            customer_id="CUST-005",
            name="Arun Patel",
            company_name="Orbit Labs Pvt Ltd",
            email="pay@orbitlabs.dev",
            phone="+91 98765 56789",
            address="Hitec City, Hyderabad, Telangana",
            risk_score=20,
            risk_level="Low",
            status="ACTIVE",
        ),
        Customer(
            customer_id="CUST-006",
            name="Sunita Nair",
            company_name="Summit Logistics",
            email="ap@summitlog.com",
            phone="+91 94470 67890",
            address="Willingdon Island, Kochi, Kerala",
            risk_score=18,
            risk_level="Low",
            status="ACTIVE",
        ),
        Customer(
            customer_id="CUST-007",
            name="Amit Singhania",
            company_name="Aether Media Networks",
            email="finance@aether.tv",
            phone="+91 98190 78901",
            address="Andheri West, Mumbai, Maharashtra",
            risk_score=72,
            risk_level="High",
            status="ACTIVE",
        ),
        Customer(
            customer_id="CUST-008",
            name="Dr. Priya Deshmukh",
            company_name="Pinnacle Healthcare",
            email="billing@pinnacle.health",
            phone="+91 98220 89012",
            address="Shivaji Nagar, Pune, Maharashtra",
            risk_score=35,
            risk_level="Medium",
            status="ACTIVE",
        ),
    ]
    db.add_all(customers_data)
    db.commit()

    # 2. Seed Invoices covering the required demonstration scenarios
    invoices_data = [
        # Scenario 1: ABC Ltd - 15 days overdue, 1 reminder already sent, ready for 2nd reminder
        Invoice(
            invoice_id="INV-1024",
            customer_id="CUST-001",
            invoice_number="INV-2026-1024",
            invoice_date=today - timedelta(days=45),
            due_date=today - timedelta(days=15),
            amount=75000.0,
            penalty_amount=1500.0,
            total_amount=76500.0,
            status="OVERDUE",
            reminder_count=1,
            last_reminder_at=ist_naive_now() - timedelta(days=5),
            next_action_at=ist_naive_now() - timedelta(days=1),
        ),
        # Scenario 2: XYZ Enterprises - Fully Paid
        Invoice(
            invoice_id="INV-1002",
            customer_id="CUST-002",
            invoice_number="INV-2026-1002",
            invoice_date=today - timedelta(days=30),
            due_date=today - timedelta(days=5),
            amount=82500.0,
            penalty_amount=0.0,
            total_amount=82500.0,
            status="PAID",
            reminder_count=0,
            last_reminder_at=None,
            next_action_at=None,
        ),
        # Scenario 3: NovaTech - Payment Promised
        Invoice(
            invoice_id="INV-1003",
            customer_id="CUST-003",
            invoice_number="INV-2026-1003",
            invoice_date=today - timedelta(days=35),
            due_date=today - timedelta(days=7),
            amount=41800.0,
            penalty_amount=0.0,
            total_amount=41800.0,
            status="PAYMENT_PROMISED",
            reminder_count=1,
            last_reminder_at=today - timedelta(days=3),
            promised_payment_date=today + timedelta(days=4),
            next_action_at=ist_naive_now() + timedelta(days=4),
        ),
        # Scenario 4: Helios Retail - 45 days overdue, 3 reminders sent, amount > 1 lakh -> Escalation + Approval
        Invoice(
            invoice_id="INV-1004",
            customer_id="CUST-004",
            invoice_number="INV-2026-1004",
            invoice_date=today - timedelta(days=75),
            due_date=today - timedelta(days=45),
            amount=250000.0,
            penalty_amount=10000.0,
            total_amount=260000.0,
            status="OVERDUE",
            reminder_count=3,
            last_reminder_at=today - timedelta(days=10),
            next_action_at=ist_naive_now() - timedelta(hours=2),
        ),
        # Scenario 5: Orbit Labs - Normal pending invoice
        Invoice(
            invoice_id="INV-1005",
            customer_id="CUST-005",
            invoice_number="INV-2026-1005",
            invoice_date=today - timedelta(days=10),
            due_date=today + timedelta(days=20),
            amount=69200.0,
            penalty_amount=0.0,
            total_amount=69200.0,
            status="PENDING",
            reminder_count=0,
            last_reminder_at=None,
            next_action_at=None,
        ),
        # Scenario 6: Summit Logistics - Paid
        Invoice(
            invoice_id="INV-1006",
            customer_id="CUST-006",
            invoice_number="INV-2026-1006",
            invoice_date=today - timedelta(days=40),
            due_date=today - timedelta(days=10),
            amount=98000.0,
            penalty_amount=0.0,
            total_amount=98000.0,
            status="PAID",
            reminder_count=0,
        ),
        # Scenario 7: Aether Media - Disputed Invoice
        Invoice(
            invoice_id="INV-1007",
            customer_id="CUST-007",
            invoice_number="INV-2026-1007",
            invoice_date=today - timedelta(days=50),
            due_date=today - timedelta(days=20),
            amount=75000.0,
            penalty_amount=0.0,
            total_amount=75000.0,
            status="DISPUTED",
            dispute_reason="Client claimed Purchase Order agreed amount was ₹70,000 rather than ₹75,000.",
            reminder_count=1,
            last_reminder_at=today - timedelta(days=12),
        ),
        # Scenario 8: Pinnacle Healthcare - Overdue by 4 days, needs 1st reminder
        Invoice(
            invoice_id="INV-1008",
            customer_id="CUST-008",
            invoice_number="INV-2026-1008",
            invoice_date=today - timedelta(days=34),
            due_date=today - timedelta(days=4),
            amount=211500.0,
            penalty_amount=0.0,
            total_amount=211500.0,
            status="OVERDUE",
            reminder_count=0,
            last_reminder_at=None,
            next_action_at=ist_naive_now() - timedelta(hours=5),
        ),
    ]
    db.add_all(invoices_data)
    db.commit()

    # 3. Seed Payments
    payments_data = [
        Payment(
            payment_id="PAY-901",
            invoice_id="INV-1002",
            customer_id="CUST-002",
            amount=82500.0,
            payment_date=ist_naive_now() - timedelta(days=5),
            payment_method="NEFT",
            reference_number="NEFT/2026/883492",
            status="SUCCESS",
        ),
        Payment(
            payment_id="PAY-902",
            invoice_id="INV-1006",
            customer_id="CUST-006",
            amount=98000.0,
            payment_date=ist_naive_now() - timedelta(days=10),
            payment_method="RTGS",
            reference_number="RTGS/2026/194821",
            status="SUCCESS",
        ),
    ]
    db.add_all(payments_data)

    # 4. Seed Communications History
    comms_data = [
        Communication(
            communication_id="COMM-101",
            customer_id="CUST-001",
            invoice_id="INV-1024",
            type="REMINDER",
            direction="OUTGOING",
            subject="First Payment Reminder: Invoice INV-1024 (ABC Ltd)",
            message="Dear Rajesh Sharma, this is a courteous reminder that invoice INV-1024 for ₹75,000 was due on "
                    + str(today - timedelta(days=15)) + ". Kindly initiate payment.",
            intent="REMINDER",
            sent_at=ist_naive_now() - timedelta(days=5),
        ),
        Communication(
            communication_id="COMM-102",
            customer_id="CUST-003",
            invoice_id="INV-1003",
            type="CUSTOMER_REPLY",
            direction="INCOMING",
            subject="Re: Payment Reminder - INV-1003",
            message="We apologize for the delay. We are processing the payment and funds will reach your account by next Friday.",
            intent="PAYMENT_PROMISED",
            sent_at=ist_naive_now() - timedelta(days=3),
        ),
        Communication(
            communication_id="COMM-103",
            customer_id="CUST-007",
            invoice_id="INV-1007",
            type="CUSTOMER_REPLY",
            direction="INCOMING",
            subject="Dispute Notice for INV-1007",
            message="The invoice amount is incorrect. Our purchase order was for ₹70,000, please verify and reissue.",
            intent="INVOICE_DISPUTE",
            sent_at=ist_naive_now() - timedelta(days=12),
        ),
    ]
    db.add_all(comms_data)

    # 5. Seed Followups
    followups_data = [
        Followup(
            followup_id="FOL-301",
            invoice_id="INV-1003",
            customer_id="CUST-003",
            action_type="PROMISE_CHECK",
            scheduled_at=ist_naive_now() + timedelta(days=4),
            status="PENDING",
        ),
    ]
    db.add_all(followups_data)

    # 6. Seed Initial Agent Actions Audit
    actions_data = [
        AgentAction(
            action_id="ACT-001",
            session_id="SESSION-INIT",
            action_type="AUTONOMOUS_CHECK",
            tool_name="get_overdue_invoices",
            input_data='{"min_days_overdue": 0}',
            output_data='{"found_invoices": 4}',
            status="SUCCESS",
            created_at=ist_naive_now() - timedelta(hours=1),
        ),
    ]
    db.add_all(actions_data)

    db.commit()


def init_db():
    """Initializes tables and seeds initial data."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database schema created and seeded successfully!")
