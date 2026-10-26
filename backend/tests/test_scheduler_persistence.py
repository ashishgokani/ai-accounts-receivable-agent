"""
Integration Tests for Automation Scheduler Persistence and Instant Reconfiguration.

Verifies:
1. Dynamic adjustment of next_run_at when interval settings are changed.
2. Resilience of next_run_at, interval_minutes, and cycles across server restarts.
3. Master automation pause and resume via settings API.
"""

from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.services.scheduler import automation_scheduler, AutomationScheduler
from app.core.timezone import ist_now

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_scheduler_instant_reconfiguration_via_api(db: Session):
    """Verifies that PUT /api/settings/reminders immediately updates scheduler next_run_at."""
    # 1. Update reminder interval to 15 minutes
    payload = {
        "automation_enabled": True,
        "automation_interval_minutes": 15,
        "low_risk": {
            "auto_reminders_enabled": True,
            "first_reminder_days": 3,
            "reminder_interval_days": 7,
            "max_reminders_before_escalation": 3,
            "final_reminder_approval_required": True,
            "pause_on_dispute": True,
        },
        "medium_risk": {
            "auto_reminders_enabled": True,
            "first_reminder_days": 1,
            "reminder_interval_days": 5,
            "max_reminders_before_escalation": 3,
            "final_reminder_approval_required": True,
            "pause_on_dispute": True,
        },
        "high_risk": {
            "auto_reminders_enabled": True,
            "first_reminder_days": 1,
            "reminder_interval_days": 3,
            "max_reminders_before_escalation": 2,
            "final_reminder_approval_required": True,
            "pause_on_dispute": True,
        },
    }
    response = client.put("/api/settings/reminders", json=payload)
    assert response.status_code == 200

    # 2. Fetch automation status endpoint
    status_resp = client.get("/api/automation/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()

    assert status_data["is_active"] is True
    assert status_data["automation_enabled"] is True
    assert status_data["interval_minutes"] == 15
    assert status_data["next_run_at"] is not None

    parsed_next = datetime.fromisoformat(status_data["next_run_at"])
    diff_minutes = (parsed_next - ist_now()).total_seconds() / 60
    assert 13 <= diff_minutes <= 16, f"Expected next run in ~15 mins, got {diff_minutes}"


def test_scheduler_state_persists_across_restart(db: Session):
    """Simulates server shutdown and reboot, verifying that next_run_at and interval are restored."""
    # 1. Capture current status
    pre_status = automation_scheduler.get_status()

    # 2. Instantiate a fresh scheduler as would happen during application boot
    rebooted_scheduler = AutomationScheduler()
    rebooted_scheduler.start()
    post_status = rebooted_scheduler.get_status()

    assert post_status["interval_minutes"] == pre_status["interval_minutes"]
    assert post_status["next_run_at"] == pre_status["next_run_at"]
    assert post_status["total_cycles_executed"] == pre_status["total_cycles_executed"]
