"""
Pydantic Validation Schemas.

Defines request and response data contracts for REST APIs and Agent Tool Calling
ensuring strict type safety and input validation across system boundaries.
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ==================== Customer Schemas ====================
class CustomerBase(BaseModel):
    name: str = Field(..., max_length=150)
    company_name: str = Field(..., max_length=150)
    email: str = Field(..., max_length=150)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    risk_score: Optional[int] = Field(25, ge=0, le=100)
    risk_level: str = Field("Low", pattern="^(Low|Medium|High)$")
    status: str = Field("ACTIVE")

    @field_validator("risk_score", mode="before")
    @classmethod
    def default_risk_score(cls, v):
        """Ensures null or missing risk_score defaults safely to 25."""
        if v is None:
            return 25
        return v



class CustomerCreate(BaseModel):
    name: str = Field(..., max_length=150)
    company_name: str = Field(..., max_length=150)
    email: str = Field(..., max_length=150)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    risk_score: int = Field(25, ge=0, le=100)
    risk_level: str = Field("Low", pattern="^(Low|Medium|High)$")


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    company_name: Optional[str] = Field(None, max_length=150)
    email: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    risk_level: Optional[str] = Field(None, pattern="^(Low|Medium|High)$")
    status: Optional[str] = None


class CustomerResponse(CustomerBase):
    customer_id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ==================== Invoice Schemas ====================
class InvoiceBase(BaseModel):
    customer_id: str
    invoice_number: str
    invoice_date: date
    due_date: date
    amount: float = Field(..., gt=0)
    penalty_amount: float = Field(0.0, ge=0)
    total_amount: float = Field(..., ge=0)
    status: str = Field("PENDING")
    reminder_count: int = Field(0, ge=0)


class InvoiceCreate(BaseModel):
    customer_id: str = Field(..., description="Target Customer ID")
    invoice_number: str = Field(..., description="Unique Invoice Number (e.g. INV-1099)")
    invoice_date: date = Field(..., description="Issue Date")
    due_date: date = Field(..., description="Payment Due Date")
    amount: float = Field(..., gt=0, description="Principal invoice billing amount")


class InvoiceUpdate(BaseModel):
    due_date: Optional[date] = None
    amount: Optional[float] = Field(None, gt=0)
    status: Optional[str] = None
    dispute_reason: Optional[str] = None
    promised_payment_date: Optional[date] = None


class InvoiceResponse(InvoiceBase):
    invoice_id: str
    last_reminder_at: Optional[datetime] = None
    next_action_at: Optional[datetime] = None
    dispute_reason: Optional[str] = None
    promised_payment_date: Optional[date] = None
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    risk_level: Optional[str] = None
    penalty_rate_percent: Optional[float] = None
    days_overdue: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==================== Payment Schemas ====================
class PaymentCreate(BaseModel):
    invoice_id: str
    amount: float = Field(..., gt=0)
    payment_method: str = Field("NEFT", max_length=50)
    reference_number: str = Field(..., max_length=100)


class PaymentResponse(BaseModel):
    payment_id: str
    invoice_id: str
    customer_id: str
    amount: float
    payment_date: datetime
    payment_method: str
    reference_number: str
    status: str

    model_config = ConfigDict(from_attributes=True)


# ==================== Communication Schemas ====================
class CommunicationResponse(BaseModel):
    communication_id: str
    customer_id: str
    invoice_id: Optional[str] = None
    type: str
    direction: str
    subject: str
    message: str
    intent: Optional[str] = None
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==================== Escalation & Followup Schemas ====================
class EscalationResponse(BaseModel):
    escalation_id: str
    invoice_id: str
    customer_id: str
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    reason: str
    amount: float
    days_overdue: int
    assigned_to: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FollowupResponse(BaseModel):
    followup_id: str
    invoice_id: str
    customer_id: str
    action_type: str
    scheduled_at: datetime
    status: str
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==================== Approval Schemas ====================
class ApprovalResponse(BaseModel):
    approval_id: str
    action_type: str
    invoice_id: str
    customer_id: str
    company_name: Optional[str] = None
    requested_by: str
    details: Dict[str, Any]
    status: str
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class ApprovalDecision(BaseModel):
    status: str = Field(..., description="Action decision: APPROVED, REJECTED, FULL_PAYMENT_APPROVED, PARTIAL_PAYMENT_APPROVED")
    reviewed_by: str = Field("Admin", max_length=80)
    review_notes: Optional[str] = None
    amount_received: Optional[float] = Field(None, ge=0.0, description="Amount verified in bank for partial payments")
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None



# ==================== Agent & Chat Schemas ====================
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None


class ChatMessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    reasoning: Optional[str] = None
    execution_seconds: float = 0.0
    actions_taken: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    created_at: datetime
    is_streaming: bool = False
    streaming_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ActiveTurnResponse(BaseModel):
    is_active: bool
    session_id: str
    status: str = "IDLE"
    reasoning: Optional[str] = None
    current_status: Optional[str] = None
    content: Optional[str] = None
    execution_seconds: float = 0.0
    actions_taken: List[str] = []
    session_title: Optional[str] = None


class ChatSessionResponse(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Conversation"


class ChatSessionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)


class ChatConfigResponse(BaseModel):
    max_history_turns: int
    max_chars: int
    daily_credits: int
    session_credits: int = 15
    credits_left: int = 50
    daily_credits_left: int = 50
    session_credits_left: int = 15
    model_name: str


class AgentActionResponse(BaseModel):
    action_id: str
    session_id: str
    action_type: str
    tool_name: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime


class PaginatedActivityResponse(BaseModel):
    items: List[AgentActionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    session_title: Optional[str] = None
    reasoning: Optional[str] = None
    execution_seconds: float = 0.0
    credits_left: int = 50
    daily_credits_left: int = 50
    session_credits_left: int = 15
    daily_credits: int = 50
    session_credits: int = 15
    tool_calls: List[Dict[str, Any]] = []
    actions_taken: List[str] = []


class AutonomousRunResponse(BaseModel):
    status: str
    invoices_analyzed: int
    actions_executed: int
    approvals_pending: int
    summary: str
    action_logs: List[Dict[str, Any]] = []


# ==================== Automation Pipeline Schemas ====================
class AutomationStatusResponse(BaseModel):
    is_active: bool
    automation_enabled: bool = True
    is_running: bool = False
    interval_minutes: int
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    total_cycles_executed: int = 0
    last_run_result: Optional[Dict[str, Any]] = None



class AutomationPipelineItem(BaseModel):
    id: str
    invoice_id: str
    invoice_number: str
    customer_name: str
    company_name: str
    planned_action: str
    scheduled_for: datetime
    amount: float
    days_overdue: int
    priority: str  # Urgent, High, Standard


class AutomationHistoryItem(BaseModel):
    id: str
    invoice_id: str
    company_name: str
    action_type: str
    subject: Optional[str] = None
    recipient_email: Optional[str] = None
    executed_at: datetime
    status: str
    details: Optional[str] = None


# ==================== Simulation Schemas ====================
class SimulateReplyRequest(BaseModel):
    invoice_id: str
    reply_message: str = Field(..., min_length=2)
    customer_email: Optional[str] = None
