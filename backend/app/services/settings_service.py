"""
System Settings Service and Business Policy Persistence.

Manages persistent database configuration for:
1. Penalty & Financial Rules (tiered by Low, Medium, High customer risk).
2. Payment Reminders & Escalation (risk-specific schedules & global automation).
3. Payment & Bank Remittance Details (dynamic templates without hardcoded secrets).
4. AI Agent Master Execution Toggle (enables or pauses AI collection operations).
"""

import json
import logging
import re
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.timezone import ist_naive_now
from app.db.models import SystemSetting

logger = logging.getLogger(__name__)


# ==================== PYDANTIC SCHEMAS ====================

class RiskPenaltyRule(BaseModel):
    """Configuration for late payment interest and grace period by risk tier."""
    penalty_rate_percent: float = Field(default=2.0, ge=0.0, le=100.0, description="Monthly penalty percentage")
    grace_period_days: int = Field(default=7, ge=0, le=365, description="Overdue days before penalties begin accruing")


class PenaltySettings(BaseModel):
    """Complete financial penalty rules for all customer risk levels."""
    calculation_base: str = Field(
        default="PRINCIPAL_ONLY",
        description="Calculation method: applies strictly to principal to avoid compounding",
    )
    low_risk: RiskPenaltyRule = Field(
        default_factory=lambda: RiskPenaltyRule(penalty_rate_percent=1.0, grace_period_days=14)
    )
    medium_risk: RiskPenaltyRule = Field(
        default_factory=lambda: RiskPenaltyRule(penalty_rate_percent=2.0, grace_period_days=7)
    )
    high_risk: RiskPenaltyRule = Field(
        default_factory=lambda: RiskPenaltyRule(penalty_rate_percent=3.0, grace_period_days=3)
    )


class RiskReminderRule(BaseModel):
    """Payment reminder schedule and escalation thresholds for a risk tier."""
    auto_reminders_enabled: bool = Field(default=True, description="Enable automated reminder emails for this tier")
    first_reminder_days: int = Field(default=1, ge=0, le=90, description="Days after due date for the first reminder")
    reminder_interval_days: int = Field(default=5, ge=1, le=90, description="Calendar days between subsequent reminders")
    max_reminders_before_escalation: int = Field(default=3, ge=1, le=10, description="Max reminders before escalating")
    final_reminder_approval_required: bool = Field(default=True, description="Requires human approval for final notice")
    pause_on_dispute: bool = Field(default=True, description="Immediately pause reminders when invoice is disputed")


class ReminderSettings(BaseModel):
    """Reminder rules per risk tier and global scheduler configuration."""
    automation_enabled: bool = Field(default=True, description="Global master switch for background automation")
    automation_interval_minutes: int = Field(default=15, ge=5, le=1440, description="Scheduler cycle interval in minutes")
    low_risk: RiskReminderRule = Field(
        default_factory=lambda: RiskReminderRule(
            auto_reminders_enabled=True,
            first_reminder_days=3,
            reminder_interval_days=7,
            max_reminders_before_escalation=3,
            final_reminder_approval_required=True,
            pause_on_dispute=True,
        )
    )
    medium_risk: RiskReminderRule = Field(
        default_factory=lambda: RiskReminderRule(
            auto_reminders_enabled=True,
            first_reminder_days=1,
            reminder_interval_days=5,
            max_reminders_before_escalation=3,
            final_reminder_approval_required=True,
            pause_on_dispute=True,
        )
    )
    high_risk: RiskReminderRule = Field(
        default_factory=lambda: RiskReminderRule(
            auto_reminders_enabled=True,
            first_reminder_days=1,
            reminder_interval_days=3,
            max_reminders_before_escalation=2,
            final_reminder_approval_required=True,
            pause_on_dispute=True,
        )
    )


class BankSettings(BaseModel):
    """Configured corporate banking details for invoices and notices."""
    beneficiary_name: str = Field(default="Accounts Receivable Management", min_length=2, max_length=150)
    bank_name: str = Field(default="HDFC Corporate Banking", min_length=2, max_length=100)
    account_number: str = Field(default="9182309182301", min_length=6, max_length=34)
    confirm_account_number: Optional[str] = Field(default=None, description="Only used for client-side confirmation")
    ifsc_code: str = Field(default="HDFC0001234", min_length=4, max_length=20)
    payment_instructions: str = Field(
        default="Please share your bank transaction UTR reference upon remittance to ensure immediate ledger credit.",
        max_length=500,
    )

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: str) -> str:
        clean = v.strip().upper()
        if not re.match(r"^[A-Z0-9]{4,15}$", clean):
            raise ValueError("IFSC code must be between 4 and 15 alphanumeric characters.")
        return clean


class AgentSettings(BaseModel):
    """AI Agent operational master switch."""
    agent_enabled: bool = Field(default=True, description="Master switch enabling or disabling the AI Agent")


class AllAdminSettings(BaseModel):
    """Consolidated admin settings response payload."""
    penalty: PenaltySettings
    reminders: ReminderSettings
    bank: BankSettings
    agent: AgentSettings


# ==================== DATABASE ACCESS FUNCTIONS ====================

def _load_setting_json(db: Session, key: str, default_model: BaseModel) -> Dict[str, Any]:
    """Helper to load a JSON setting row from database or return default dictionary."""
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row or not row.value:
        return default_model.model_dump()
    try:
        return json.loads(row.value)
    except Exception as exc:
        logger.warning("Failed to parse JSON setting for %s: %s. Using defaults.", key, exc)
        return default_model.model_dump()


def _save_setting_json(db: Session, key: str, category: str, data: BaseModel, description: str = "") -> None:
    """Helper to persist a Pydantic model as JSON in system_settings."""
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    dumped = json.dumps(data.model_dump(), default=str)
    if row:
        row.value = dumped
        row.updated_at = ist_naive_now()
    else:
        row = SystemSetting(
            key=key,
            value=dumped,
            category=category,
            description=description,
            updated_at=ist_naive_now(),
        )
        db.add(row)
    db.commit()


def get_penalty_settings(db: Session) -> PenaltySettings:
    """Retrieves current financial penalty settings from database."""
    data = _load_setting_json(db, "penalty_rules", PenaltySettings())
    return PenaltySettings(**data)


def update_penalty_settings(db: Session, settings: PenaltySettings) -> PenaltySettings:
    """Updates financial penalty settings in PostgreSQL."""
    _save_setting_json(db, "penalty_rules", "penalty", settings, "Risk-tiered penalty percentage and grace periods")
    logger.info("Updated penalty settings in database.")
    return settings


def get_reminder_settings(db: Session) -> ReminderSettings:
    """Retrieves reminder and escalation schedules from database."""
    data = _load_setting_json(db, "reminder_rules", ReminderSettings())
    return ReminderSettings(**data)


def update_reminder_settings(db: Session, settings: ReminderSettings) -> ReminderSettings:
    """Updates reminder and escalation schedules in database."""
    _save_setting_json(db, "reminder_rules", "reminders", settings, "Risk-tiered reminder intervals and escalation rules")
    logger.info("Updated reminder settings in database.")
    return settings


def get_bank_settings(db: Session) -> BankSettings:
    """Retrieves corporate bank details from database."""
    data = _load_setting_json(db, "bank_details", BankSettings())
    # Exclude confirm_account_number from persistent read
    data.pop("confirm_account_number", None)
    return BankSettings(**data)


def update_bank_settings(db: Session, settings: BankSettings) -> BankSettings:
    """Updates corporate bank details after verifying matching confirmation."""
    if settings.confirm_account_number and settings.account_number != settings.confirm_account_number:
        raise ValueError("Account number and confirmation account number do not match.")
    # Stored without the redundant confirm field
    cleaned = BankSettings(
        beneficiary_name=settings.beneficiary_name.strip(),
        bank_name=settings.bank_name.strip(),
        account_number=settings.account_number.strip(),
        ifsc_code=settings.ifsc_code.strip().upper(),
        payment_instructions=settings.payment_instructions.strip(),
    )
    _save_setting_json(db, "bank_details", "bank", cleaned, "Corporate bank account details for invoices and notices")
    logger.info("Updated bank settings in database.")
    return cleaned


def get_agent_settings(db: Session) -> AgentSettings:
    """Retrieves AI agent operational master switch state."""
    data = _load_setting_json(db, "agent_controls", AgentSettings())
    return AgentSettings(**data)


def update_agent_settings(db: Session, settings: AgentSettings) -> AgentSettings:
    """Updates AI agent master switch state in database."""
    _save_setting_json(db, "agent_controls", "agent", settings, "AI Agent operational master switch")
    logger.info("Updated AI agent settings: agent_enabled=%s", settings.agent_enabled)
    return settings


def get_all_settings(db: Session) -> AllAdminSettings:
    """Aggregates all 4 admin settings sections into a unified response."""
    return AllAdminSettings(
        penalty=get_penalty_settings(db),
        reminders=get_reminder_settings(db),
        bank=get_bank_settings(db),
        agent=get_agent_settings(db),
    )


# ==================== RUNTIME SYSTEM HELPERS ====================

def get_risk_penalty_rule(db: Session, risk_level: Optional[str]) -> RiskPenaltyRule:
    """Resolves penalty rate and grace period for a specific customer risk tier."""
    settings = get_penalty_settings(db)
    norm = (risk_level or "low").strip().lower()
    if norm == "high":
        return settings.high_risk
    elif norm == "medium":
        return settings.medium_risk
    return settings.low_risk


def get_risk_reminder_rule(db: Session, risk_level: Optional[str]) -> RiskReminderRule:
    """Resolves reminder interval, first notice timing, and escalation limit for risk tier."""
    settings = get_reminder_settings(db)
    norm = (risk_level or "low").strip().lower()
    if norm == "high":
        return settings.high_risk
    elif norm == "medium":
        return settings.medium_risk
    return settings.low_risk


def get_bank_details_dict(db: Session) -> Dict[str, str]:
    """Returns bank details formatted for HTML email templates and AI drafter prompts."""
    bank = get_bank_settings(db)
    return {
        "beneficiary_name": bank.beneficiary_name,
        "bank_name": bank.bank_name,
        "account_number": bank.account_number,
        "ifsc_code": bank.ifsc_code,
        "payment_instructions": bank.payment_instructions,
    }


def is_agent_enabled(db: Session) -> bool:
    """Checks whether the AI Agent master switch is active."""
    return get_agent_settings(db).agent_enabled


def is_automation_enabled(db: Session) -> bool:
    """Checks whether the global background automation scheduler is active."""
    return get_reminder_settings(db).automation_enabled
