"""
SQLAlchemy ORM Database Models for Accounts Receivable Management.

Defines schemas for Customers, Invoices, Payments, Communications,
Followups, Escalations, AgentActions, and Human Approvals.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Date,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.core.timezone import ist_naive_now



class Customer(Base):
    """
    Customer entity storing corporate billing profile, contact info, and risk assessment.
    """
    __tablename__ = "customers"

    customer_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    company_name = Column(String(150), nullable=False, index=True)
    email = Column(String(150), nullable=False, unique=True, index=True)
    phone = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    risk_score = Column(Integer, default=25)  # 0 to 100
    risk_level = Column(String(20), default="Low")  # Low, Medium, High
    status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, default=ist_naive_now)
    updated_at = Column(DateTime, default=ist_naive_now, onupdate=ist_naive_now)

    # Relationships
    invoices = relationship("Invoice", back_populates="customer", cascade="all, delete-orphan")
    communications = relationship("Communication", back_populates="customer")


class Invoice(Base):
    """
    Invoice entity tracking billing amounts, deterministic penalties, overdue aging,
    and workflow progression states.
    """
    __tablename__ = "invoices"

    invoice_id = Column(String(50), primary_key=True, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False, index=True)
    invoice_number = Column(String(50), nullable=False, unique=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    penalty_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    status = Column(String(30), default="PENDING", index=True)
    reminder_count = Column(Integer, default=0)
    last_reminder_at = Column(DateTime, nullable=True)
    next_action_at = Column(DateTime, nullable=True)
    dispute_reason = Column(Text, nullable=True)
    promised_payment_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=ist_naive_now)
    updated_at = Column(DateTime, default=ist_naive_now, onupdate=ist_naive_now)

    # Relationships
    customer = relationship("Customer", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice")
    followups = relationship("Followup", back_populates="invoice")
    escalations = relationship("Escalation", back_populates="invoice")


class Payment(Base):
    """
    Payment transaction record for auditing settlements and auto-reconciliation.
    """
    __tablename__ = "payments"

    payment_id = Column(String(50), primary_key=True, index=True)
    invoice_id = Column(String(50), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_date = Column(DateTime, default=ist_naive_now)
    payment_method = Column(String(50), default="NEFT")
    reference_number = Column(String(100), unique=True, index=True)
    status = Column(String(20), default="SUCCESS")
    created_at = Column(DateTime, default=ist_naive_now)

    invoice = relationship("Invoice", back_populates="payments")


class Communication(Base):
    """
    Communication ledger recording both outbound automated emails and inbound customer replies.
    """
    __tablename__ = "communications"

    communication_id = Column(String(50), primary_key=True, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False, index=True)
    invoice_id = Column(String(50), ForeignKey("invoices.invoice_id"), nullable=True, index=True)
    type = Column(String(30), nullable=False)  # REMINDER, FOLLOW_UP, ESCALATION, PAYMENT_CONFIRMATION, CUSTOMER_REPLY
    direction = Column(String(15), nullable=False)  # OUTGOING, INCOMING
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)  # PAYMENT_PROMISED, DISPUTED, EXTENSION_REQUEST, etc.
    sent_at = Column(DateTime, default=ist_naive_now)
    created_at = Column(DateTime, default=ist_naive_now)

    customer = relationship("Customer", back_populates="communications")


class Followup(Base):
    """
    Scheduled asynchronous tasks and reminders waiting for future execution.
    """
    __tablename__ = "followups"

    followup_id = Column(String(50), primary_key=True, index=True)
    invoice_id = Column(String(50), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), default="PENDING", index=True)  # PENDING, COMPLETED, CANCELLED
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=ist_naive_now)

    invoice = relationship("Invoice", back_populates="followups")


class Escalation(Base):
    """
    Formal escalation cases requiring manual intervention or legal review.
    """
    __tablename__ = "escalations"

    escalation_id = Column(String(50), primary_key=True, index=True)
    invoice_id = Column(String(50), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False)
    reason = Column(Text, nullable=False)
    amount = Column(Float, nullable=False)
    days_overdue = Column(Integer, default=0)
    assigned_to = Column(String(100), default="Ashish Gokani (Admin)")
    status = Column(String(25), default="OPEN", index=True)  # OPEN, UNDER_REVIEW, RESOLVED
    created_at = Column(DateTime, default=ist_naive_now)
    resolved_at = Column(DateTime, nullable=True)

    invoice = relationship("Invoice", back_populates="escalations")


class AgentAction(Base):
    """
    Auditable execution trace storing intermediate agent reasoning steps,
    tool calls, parameters, and results.
    """
    __tablename__ = "agent_actions"

    action_id = Column(String(50), primary_key=True, index=True)
    session_id = Column(String(50), index=True)
    action_type = Column(String(50), nullable=False)
    tool_name = Column(String(80), nullable=True, index=True)
    input_data = Column(Text, nullable=True)
    output_data = Column(Text, nullable=True)
    status = Column(String(25), default="SUCCESS")  # SUCCESS, FAILED, PENDING_APPROVAL
    created_at = Column(DateTime, default=ist_naive_now, index=True)


class Approval(Base):
    """
    Human-in-the-loop approval gate for high-risk or high-value agent actions.
    """
    __tablename__ = "approvals"

    approval_id = Column(String(50), primary_key=True, index=True)
    action_type = Column(String(50), nullable=False)
    invoice_id = Column(String(50), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False)
    requested_by = Column(String(80), default="AI Agent")
    details = Column(Text, nullable=False)  # JSON serialized details
    status = Column(String(20), default="PENDING", index=True)  # PENDING, APPROVED, REJECTED
    reviewed_by = Column(String(80), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=ist_naive_now)
    reviewed_at = Column(DateTime, nullable=True)


class ChatSession(Base):
    """
    Chat session grouping multi-turn conversations with the autonomous agent.
    """
    __tablename__ = "chat_sessions"

    session_id = Column(String(50), primary_key=True, index=True)
    title = Column(String(200), default="New Conversation")
    created_at = Column(DateTime, default=ist_naive_now)
    updated_at = Column(DateTime, default=ist_naive_now, onupdate=ist_naive_now)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")


class ChatMessage(Base):
    """
    Individual chat turn storing user input or AI reasoning, thoughts, and replies.
    """
    __tablename__ = "chat_messages"

    message_id = Column(String(50), primary_key=True, index=True)
    session_id = Column(String(50), ForeignKey("chat_sessions.session_id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, ai, system
    content = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=True)  # chain-of-thought extraction
    execution_seconds = Column(Float, default=0.0)
    actions_taken = Column(Text, nullable=True)  # JSON string
    tool_calls = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=ist_naive_now, index=True)

    session = relationship("ChatSession", back_populates="messages")


class PendingAction(Base):
    """
    Persisted state machine for agent actions awaiting explicit human confirmation.
    Prevents guessing, duplicate dispatches, and lost multi-turn intent.
    """
    __tablename__ = "pending_actions"

    action_id = Column(String(50), primary_key=True, index=True)
    session_id = Column(String(50), ForeignKey("chat_sessions.session_id"), nullable=False, index=True)
    tool_name = Column(String(80), nullable=False)
    description = Column(String(255), nullable=False)
    target_invoices = Column(Text, nullable=True)  # JSON list of invoice IDs
    target_customers = Column(Text, nullable=True)  # JSON list of customer IDs
    parameters = Column(Text, nullable=False)  # JSON payload for tool execution
    status = Column(String(30), default="PENDING_CONFIRMATION", index=True)  # PENDING_CONFIRMATION, EXECUTED, CANCELLED, EXPIRED
    idempotency_key = Column(String(100), unique=True, index=True)
    created_at = Column(DateTime, default=ist_naive_now)
    expires_at = Column(DateTime, nullable=False)
    executed_at = Column(DateTime, nullable=True)
    execution_result = Column(Text, nullable=True)


class InvoiceCommitment(Base):
    """
    Persisted commercial commitments, agreements, and directives made in chat.
    Binds outbound communication directly to database terms and background scheduler.
    """
    __tablename__ = "invoice_commitments"

    commitment_id = Column(String(50), primary_key=True, index=True)
    invoice_id = Column(String(50), ForeignKey("invoices.invoice_id"), nullable=False, index=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False, index=True)
    commitment_type = Column(String(50), nullable=False)  # EARLY_SETTLEMENT_DISCOUNT, GRACE_PERIOD_PAUSE, PAYMENT_PROMISE, PENALTY_WAIVER
    description = Column(String(255), nullable=False)
    parameters = Column(Text, nullable=False)  # Dynamic JSON dictionary of agreed terms
    status = Column(String(30), default="ACTIVE", index=True)  # ACTIVE, FULFILLED, EXPIRED, REVOKED
    created_at = Column(DateTime, default=ist_naive_now)
    valid_until = Column(DateTime, nullable=True)  # Expiration timestamp (e.g., +24 hours)
    revoked_at = Column(DateTime, nullable=True)
    fulfilled_at = Column(DateTime, nullable=True)


class SystemSetting(Base):
    """
    Persistent key-value system settings configuring AR penalties,
    payment reminders, bank remittance details, and agent controls.
    """
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True, index=True)
    value = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, index=True)  # penalty, reminders, bank, agent
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=ist_naive_now, onupdate=ist_naive_now)


class InboundEmailLog(Base):
    """
    Persistent audit ledger for all incoming customer emails.
    Enforces idempotency, deduplication by RFC 822 Message-ID,
    tracks sender verification, semantic classification, and approval links.
    """
    __tablename__ = "inbound_email_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(255), unique=True, nullable=False, index=True)
    sender_email = Column(String(120), nullable=False, index=True)
    recipient_email = Column(String(120), nullable=True)
    subject = Column(String(255), nullable=True)
    clean_body = Column(Text, nullable=False)
    quoted_history = Column(Text, nullable=True)
    received_at = Column(DateTime, default=ist_naive_now, index=True)
    status = Column(String(40), default="RECEIVED", index=True)  # RECEIVED, PROCESSED, FAILED_RETRYABLE, IGNORED_UNVERIFIED, FLAGGED_AMBIGUOUS
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=True, index=True)
    invoice_id = Column(String(50), ForeignKey("invoices.invoice_id"), nullable=True, index=True)
    intent = Column(String(50), nullable=True)  # PAYMENT_CLAIMED, PAYMENT_PROMISED, INVOICE_DISPUTE, EXTENSION_REQUEST, GENERAL_INQUIRY, UNKNOWN_OR_AMBIGUOUS, UNRELATED_SPAM
    extracted_entities = Column(Text, nullable=True)  # JSON dictionary (promised_date, utr, amount, etc.)
    ai_rationale = Column(Text, nullable=True)  # Concise 1-3 sentence summary (no raw CoT)
    requires_approval = Column(Boolean, default=False)
    approval_id = Column(String(50), ForeignKey("approvals.approval_id"), nullable=True, index=True)
    acknowledgment_sent = Column(Boolean, default=False)
    acknowledgment_comm_id = Column(String(50), nullable=True)
    retry_count = Column(Integer, default=0)
    error_details = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=ist_naive_now)



