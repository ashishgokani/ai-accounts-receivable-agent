"""
Autonomous Background Scheduler Service.

Periodically inspects receivables in PostgreSQL, computes upcoming actions,
dispatches reminders and escalations, and maintains the automation pipeline
and historical ledger for frontend visibility. Fully persistent across server restarts.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import ist_now, ist_naive_now, to_ist
from app.db.session import SessionLocal
from app.db.models import Invoice, Customer, Communication, Followup, AgentAction, SystemSetting
from app.services.penalty_engine import (
    calculate_days_overdue,
    sync_invoice_financials,
    determine_recommended_action,
)
from app.services.orchestrator import AgentOrchestrator
from app.services.commitments_service import (
    expire_stale_commitments,
    has_active_hold_or_pause,
)
from app.services.settings_service import (
    get_reminder_settings,
    is_automation_enabled,
    get_risk_penalty_rule,
)

logger = logging.getLogger(__name__)


class AutomationScheduler:
    """
    Manages automated background cycles for accounts receivable monitoring.
    Persists scheduling timestamps and cycle counts in PostgreSQL to ensure
    resilience across application restarts and instant reactivity on settings updates.
    """

    def __init__(self):
        self.is_active: bool = False
        self.is_running: bool = False
        self.interval_minutes: int = 15
        self.last_run_at: Optional[datetime] = None
        self.next_run_at: Optional[datetime] = None
        self.total_cycles_executed: int = 0
        self.last_run_result: Optional[Dict[str, Any]] = None
        self._task: Optional[asyncio.Task] = None
        self._wake_event: Optional[asyncio.Event] = None

    def _load_state(self, db: Session) -> None:
        """Loads persistent scheduler state and reminder configuration from PostgreSQL."""
        try:
            # 1. Load active reminder cadence from database settings
            rem_settings = get_reminder_settings(db)
            self.interval_minutes = rem_settings.automation_interval_minutes
            self.is_active = rem_settings.automation_enabled

            # 2. Load execution history & next run timestamp from SystemSetting
            row = db.query(SystemSetting).filter(SystemSetting.key == "scheduler_state").first()
            if row and row.value:
                data = json.loads(row.value)
                self.total_cycles_executed = int(data.get("total_cycles_executed", 0))

                last_str = data.get("last_run_at")
                if last_str:
                    self.last_run_at = to_ist(datetime.fromisoformat(last_str))
                self.last_run_result = data.get("last_run_result")

                next_str = data.get("next_run_at")
                if next_str:
                    parsed_next = to_ist(datetime.fromisoformat(next_str))
                    # Retain scheduled run if it is still in the future; otherwise compute fresh
                    if parsed_next and parsed_next > ist_now():
                        self.next_run_at = parsed_next
                    else:
                        self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)
                        self._save_state(db)
                else:
                    self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)
                    self._save_state(db)
            else:
                # First run or uninitialized state: schedule from now and persist
                self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)
                self._save_state(db)

            logger.info(
                "Scheduler state loaded from DB: interval=%d min, active=%s, next_run=%s, cycles=%d",
                self.interval_minutes,
                self.is_active,
                self.next_run_at.isoformat() if self.next_run_at else "None",
                self.total_cycles_executed,
            )
        except Exception as exc:
            logger.error("Failed to load scheduler state from database: %s", exc)
            self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)

    def _save_state(self, db: Session) -> None:
        """Persists current scheduler runtime state to PostgreSQL."""
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == "scheduler_state").first()
            payload = {
                "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
                "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
                "total_cycles_executed": self.total_cycles_executed,
                "interval_minutes": self.interval_minutes,
                "is_active": self.is_active,
                "last_run_result": self.last_run_result,
                "updated_at": ist_naive_now().isoformat(),
            }
            dumped = json.dumps(payload)
            if row:
                row.value = dumped
                row.updated_at = ist_naive_now()
            else:
                row = SystemSetting(
                    key="scheduler_state",
                    value=dumped,
                    category="automation",
                    description="Persistent background scheduler operational timestamps and execution counters",
                    updated_at=ist_naive_now(),
                )
                db.add(row)
            db.commit()
        except Exception as exc:
            logger.error("Failed to persist scheduler state to database: %s", exc)
            db.rollback()

    def reconfigure(self, new_interval_minutes: int, enabled: bool, db: Optional[Session] = None) -> None:
        """
        Dynamically adjusts the scheduler interval and active state immediately
        when administrator updates settings, recalculating next_run_at and waking the loop.
        """
        self.interval_minutes = max(5, new_interval_minutes)
        self.is_active = enabled

        now = ist_now()
        if enabled:
            # Set next run cleanly based on new interval from current reconfiguration time
            self.next_run_at = now + timedelta(minutes=self.interval_minutes)
        else:
            self.next_run_at = None

        # Persist to database
        if db:
            self._save_state(db)
        else:
            local_db = SessionLocal()
            try:
                self._save_state(local_db)
            finally:
                local_db.close()

        # Signal wake event to instantly interrupt long async sleeps
        if self._wake_event:
            self._wake_event.set()

        # If enabled and task died or was never started, launch it if event loop is running
        if enabled and (self._task is None or self._task.done()):
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._run_loop())
            except RuntimeError:
                pass

        logger.info(
            "Scheduler reconfigured: interval=%d min, active=%s, next_run=%s",
            self.interval_minutes,
            self.is_active,
            self.next_run_at.isoformat() if self.next_run_at else "None",
        )

    def start(self):
        """Starts background async worker loop on application startup, restoring saved DB state."""
        try:
            if self._wake_event is None:
                self._wake_event = asyncio.Event()
        except RuntimeError:
            pass

        # Restore persistent scheduling parameters from PostgreSQL
        db = SessionLocal()
        try:
            self._load_state(db)
        finally:
            db.close()

        if not self.is_active:
            logger.info("Autonomous AR Scheduler is disabled in settings. Skipping background worker.")
            return

        if self._task and not self._task.done():
            logger.info("Autonomous AR Scheduler task is already running.")
            return

        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run_loop())
            logger.info(
                "Autonomous AR Scheduler started. Interval: %d min. Next execution: %s",
                self.interval_minutes,
                self.next_run_at.isoformat() if self.next_run_at else "None",
            )
        except RuntimeError:
            logger.info("No active asyncio event loop found; scheduler initialized in synchronous/test mode.")

    def stop(self):
        """Cancels background worker task cleanly on application shutdown."""
        self.is_active = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Autonomous AR Scheduler background worker stopped.")

    async def _run_loop(self):
        """Internal asynchronous loop firing periodic collection cycles with slicing for instant wake."""
        while self.is_active:
            try:
                now = ist_now()
                if not self.next_run_at:
                    self.next_run_at = now + timedelta(minutes=self.interval_minutes)
                    with SessionLocal() as db:
                        self._save_state(db)

                # Wait until next_run_at or until interrupted by reconfiguration event
                remaining_seconds = (self.next_run_at - now).total_seconds()
                if remaining_seconds > 0:
                    slice_duration = min(remaining_seconds, 5.0)
                    if self._wake_event:
                        try:
                            await asyncio.wait_for(self._wake_event.wait(), timeout=slice_duration)
                            if self._wake_event.is_set():
                                self._wake_event.clear()
                                continue  # Interrupted by reconfigure: re-evaluate next_run_at immediately
                        except asyncio.TimeoutError:
                            pass
                    else:
                        await asyncio.sleep(slice_duration)
                    continue

                if not self.is_active:
                    break

                # Execute autonomous cycle in a background worker thread so the main asyncio event loop never blocks
                await asyncio.to_thread(self._execute_scheduled_cycle_sync)

            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.error("Unexpected error in automation scheduler loop: %s", loop_err)
                await asyncio.sleep(5)

    def _execute_scheduled_cycle_sync(self) -> None:
        """Executes one autonomous collection cycle in a background worker thread to keep the event loop responsive."""
        db = SessionLocal()
        self.is_running = True
        try:
            if not is_automation_enabled(db):
                logger.info("Autonomous AR scheduler: background collection disabled. Skipping cycle.")
            else:
                logger.info("Triggering scheduled autonomous collection cycle...")
                try:
                    from app.services.email_listener_service import inbound_email_listener
                    inbound_email_listener.check_inbox_and_process(db)
                except Exception as mail_err:
                    logger.warning("Scheduled inbound email check failed: %s", mail_err)
                expire_stale_commitments(db)
                result = AgentOrchestrator.run_autonomous_workflow(db, session_id="auto-cron")
                self.last_run_result = result
                self.last_run_at = ist_now()
                self.total_cycles_executed += 1

            self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)
            self._save_state(db)
        except Exception as exc:
            logger.error("Error executing scheduled collection cycle: %s", exc)
            self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)
            self._save_state(db)
        finally:
            self.is_running = False
            db.close()

    def get_status(self) -> Dict[str, Any]:
        """Returns current operational status of background scheduler synchronized with database."""
        db = SessionLocal()
        automation_enabled = True
        try:
            automation_enabled = is_automation_enabled(db)
            rem = get_reminder_settings(db)
            self.interval_minutes = rem.automation_interval_minutes

            # Always sync runtime scheduler state from DB
            self._load_state(db)

            # If next_run_at passed while server was running, advance to next cycle
            if self.is_active and automation_enabled and self.next_run_at and ist_now() > self.next_run_at:
                self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)
                self._save_state(db)
        except Exception as exc:
            logger.error("Error reading scheduler status: %s", exc)
        finally:
            db.close()

        return {
            "is_active": self.is_active and automation_enabled,
            "automation_enabled": automation_enabled,
            "is_running": self.is_running,
            "interval_minutes": self.interval_minutes,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "total_cycles_executed": self.total_cycles_executed,
            "last_run_result": self.last_run_result,
        }

    def trigger_cycle_now(self, db: Session) -> Dict[str, Any]:
        """Manually fires an autonomous cycle immediately and updates schedule timestamps."""
        self.is_running = True
        try:
            try:
                from app.services.email_listener_service import inbound_email_listener
                inbound_email_listener.check_inbox_and_process(db)
            except Exception as mail_err:
                logger.warning("Manual trigger email listener check failed: %s", mail_err)

            expire_stale_commitments(db)
            result = AgentOrchestrator.run_autonomous_workflow(db, session_id="auto-manual")
            self.last_run_result = result
            self.last_run_at = ist_now()
            self.total_cycles_executed += 1
            self.next_run_at = ist_now() + timedelta(minutes=self.interval_minutes)
            self._save_state(db)
            if self._wake_event:
                self._wake_event.set()
            return result
        finally:
            self.is_running = False

    def get_upcoming_pipeline(self, db: Session) -> List[Dict[str, Any]]:
        """
        Computes forward-looking automation pipeline based on current invoice states,
        risk-tiered penalty rates, and active commercial commitments.
        """
        pipeline = []
        base_time = self.next_run_at or (ist_now() + timedelta(minutes=self.interval_minutes))

        unsettled = (
            db.query(Invoice)
            .join(Customer)
            .filter(Invoice.status.in_(["PENDING", "OVERDUE", "PAYMENT_PROMISED"]))
            .all()
        )

        offset_minutes = 0
        for inv in unsettled:
            sync_invoice_financials(inv, db)
            days = calculate_days_overdue(inv.due_date)
            action, reason = determine_recommended_action(inv)

            is_frozen = has_active_hold_or_pause(db, inv.invoice_id) or (
                inv.next_action_at is not None and inv.next_action_at > ist_now().replace(tzinfo=None)
            )

            if is_frozen:
                action_label = "Reminders Paused (Commercial Commitment Active)"
                priority = "Standard"
            elif action == "NO_ACTION" and inv.status != "PAYMENT_PROMISED":
                continue
            elif action == "FIRST_REMINDER":
                action_label = "Dispatch Initial Courtesy Payment Reminder"
                priority = "Standard"
            elif action == "SECOND_REMINDER":
                risk_level = inv.customer.risk_level if inv.customer else "Medium"
                penalty_rule = get_risk_penalty_rule(db, risk_level)
                action_label = f"Dispatch Second Notice with {penalty_rule.penalty_rate_percent}% Late Penalty"
                priority = "High"
            elif action == "ESCALATE":
                action_label = "Escalate Account to Senior Credit Review"
                priority = "Urgent"
            elif inv.status == "PAYMENT_PROMISED":
                action_label = f"Verify Payment Receipt (Promised Date: {inv.promised_payment_date or 'Pending'})"
                priority = "Standard"
            else:
                action_label = "Automated Overdue Check & Audit"
                priority = "Standard"

            scheduled_time = base_time + timedelta(minutes=offset_minutes)
            offset_minutes += 3  # stagger upcoming execution predictions

            pipeline.append({
                "id": f"PIPE-{inv.invoice_id}",
                "invoice_id": inv.invoice_id,
                "invoice_number": inv.invoice_number,
                "customer_name": inv.customer.name if inv.customer else "N/A",
                "company_name": inv.customer.company_name if inv.customer else "N/A",
                "planned_action": action_label,
                "scheduled_for": scheduled_time,
                "amount": inv.total_amount,
                "days_overdue": max(0, days),
                "priority": priority,
            })

        priority_weights = {"Urgent": 0, "High": 1, "Standard": 2}
        pipeline.sort(key=lambda x: priority_weights.get(x["priority"], 3))
        return pipeline[:20]

    def get_execution_history(self, db: Session, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieves real history of automated actions and emails sent by the system."""
        comms = (
            db.query(Communication)
            .filter(Communication.direction == "OUTGOING")
            .order_by(Communication.sent_at.desc())
            .limit(limit)
            .all()
        )

        history = []
        for c in comms:
            cust = db.query(Customer).filter(Customer.customer_id == c.customer_id).first()
            history.append({
                "id": c.communication_id,
                "invoice_id": c.invoice_id or "General",
                "company_name": cust.company_name if cust else "Corporate Client",
                "action_type": c.type.replace("_", " ").title(),
                "subject": c.subject,
                "recipient_email": cust.email if cust else "client@domain.com",
                "executed_at": c.sent_at,
                "status": "SENT",
                "details": c.message[:150] + ("..." if len(c.message) > 150 else ""),
            })

        return history


# Global singleton scheduler instance
automation_scheduler = AutomationScheduler()
