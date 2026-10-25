"""
Application Configuration Module.

Loads and validates environment variables and business policy constants
governing accounts receivable automation, AWS Bedrock AI integration,
and database persistence settings.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """
    Central settings class parsing values from environment variables or .env file.
    
    Attributes:
        app_name: The display name of the system.
        environment: Current operating environment (development, staging, production).
        log_level: Python logging verbosity level.
        app_host: Host IP interface to bind FastAPI server.
        app_port: TCP port to run FastAPI server.
        database_url: SQLAlchemy connection string.
        aws_region: AWS region where Amazon Bedrock foundation models are hosted.
        aws_access_key_id: Optional AWS Access Key.
        aws_secret_access_key: Optional AWS Secret Key.
        aws_session_token: Optional temporary session token.
        bedrock_model_id: Bedrock model identifier (e.g. Mistral Large, Amazon Nova, Llama).
        use_mock_bedrock_fallback: If True, uses mock response generator when Bedrock credentials are unset.
        penalty_rate_percent: Default interest penalty percentage per overdue cycle.
        penalty_days_cycle: Days per penalty cycle (e.g., 30 days).
        escalation_overdue_days_threshold: Days overdue that trigger automatic escalation.
        max_reminders_before_escalation: Maximum reminders allowed before escalation is required.
        high_value_approval_threshold: Financial value above which actions require human approval.
    """

    model_config = SettingsConfigDict(
        env_file=(str(ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI-Powered Accounts Receivable Management Agent"
    environment: str = "development"
    log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "sqlite:///./ar_management.db"

    # AWS Bedrock Settings
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    bedrock_model_id: str = "us.amazon.nova-pro-v1:0"
    use_mock_bedrock_fallback: bool = False

    # Email Delivery Settings
    email_provider: str = "simulated"
    smtp_host: Optional[str] = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: str = "ar-agent@fintech-enterprise.com"
    from_name: str = "ReceivIQ"
    reply_to_email: str = "ashishgokani58@gmail.com"
    demo_override_email: Optional[str] = None

    # Inbound Email Detection (Gmail API & IMAP SSL)
    gmail_api_enabled: bool = False
    gmail_credentials_file: Optional[str] = None
    gmail_token_file: Optional[str] = None
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    imap_polling_enabled: bool = True
    imap_poll_interval_seconds: int = 30


    # AR Business Policy Parameters
    penalty_rate_percent: float = 2.0
    penalty_days_cycle: int = 30
    escalation_overdue_days_threshold: int = 30
    max_reminders_before_escalation: int = 3
    high_value_approval_threshold: float = 100000.0

    # Chat & Token Control Settings
    chat_max_history_turns: int = 10
    chat_max_chars: int = 1000
    chat_daily_credits: int = 200
    chat_session_credits: int = 25
    automation_interval_minutes: int = 15


# Instantiate singleton settings instance
settings = Settings()
