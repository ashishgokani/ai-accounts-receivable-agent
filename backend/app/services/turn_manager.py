"""
Background Turn Execution and Multi-Session State Synchronization Manager.

Provides thread-safe state tracking for autonomous agent conversational turns.
Guarantees that background LLM reasoning, ReAct tool executions, and PostgreSQL
message persistence run to completion on the server even if an HTTP client
disconnects, switches tabs, or navigates between multiple chat conversations.
"""

from datetime import datetime
import json
import logging
import threading
import time
from typing import Dict, Any, List, Optional, Generator, Callable

logger = logging.getLogger(__name__)


class TurnState:
    """
    Represents the runtime state and event stream of an in-flight or recently completed agent turn.
    Thread-safe container supporting multi-subscriber SSE notification and snapshot retrieval.
    """

    def __init__(self, session_id: str, prompt: str):
        self.session_id = session_id
        self.prompt = prompt
        self.status = "RUNNING"  # "RUNNING", "COMPLETED", "ERROR"
        self.reasoning = ""
        self.current_status = "Initializing agent reasoning loop..."
        self.content = ""
        self.actions_taken: List[str] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.execution_seconds = 0.0
        self.events: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.started_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.session_title: Optional[str] = None

    def add_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Appends an event to the chronological event log and updates aggregated state fields.
        Notifies all waiting SSE streaming generators across threads.

        Args:
            event_type: One of 'thought', 'status', 'content', 'session_info', 'done', 'error'.
            data: Payload dictionary matching the event schema.
        """
        with self.condition:
            payload = {"type": event_type, **data}
            self.events.append(payload)

            if event_type == "thought":
                chunk = data.get("chunk", "")
                self.reasoning += chunk
            elif event_type == "status":
                self.current_status = data.get("message", "")
            elif event_type == "content":
                chunk = data.get("chunk", "")
                self.content += chunk
                self.current_status = ""  # Clear intermediate tool status once answer generation starts
            elif event_type == "session_info":
                if data.get("session_title"):
                    self.session_title = data.get("session_title")
            elif event_type == "done":
                self.status = "COMPLETED"
                self.execution_seconds = data.get("execution_seconds", 0.0)
                self.actions_taken = data.get("actions_taken", [])
                self.completed_at = datetime.now()
                self.current_status = ""
                if data.get("session_title"):
                    self.session_title = data.get("session_title")
            elif event_type == "error":
                self.status = "ERROR"
                self.error_message = data.get("message", "An unexpected error occurred.")
                self.completed_at = datetime.now()
                self.current_status = ""

            # Wake up all listening generator streams
            self.condition.notify_all()

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Returns a thread-safe snapshot dictionary representing current turn progress.

        Returns:
            Dict containing active status, accumulated reasoning, current tool status, and partial content.
        """
        with self.lock:
            return {
                "is_active": self.status == "RUNNING",
                "session_id": self.session_id,
                "status": self.status,
                "reasoning": self.reasoning,
                "current_status": self.current_status,
                "content": self.content,
                "actions_taken": list(self.actions_taken),
                "execution_seconds": self.execution_seconds,
                "error_message": self.error_message,
                "session_title": self.session_title,
                "started_at": self.started_at,
            }


class TurnManager:
    """
    Singleton manager coordinating background agent turn execution and state query across sessions.
    Guarantees persistence and replay across client tab switches, reconnects, and page navigation.
    """

    def __init__(self):
        self._turns: Dict[str, TurnState] = {}
        self._lock = threading.Lock()

    def get_turn(self, session_id: str) -> Optional[TurnState]:
        """Retrieves the TurnState for a specific session ID if registered."""
        with self._lock:
            return self._turns.get(session_id)

    def is_turn_active(self, session_id: str) -> bool:
        """Checks if a background turn is currently actively running for the session."""
        turn = self.get_turn(session_id)
        return bool(turn and turn.status == "RUNNING")

    def get_turn_snapshot(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a thread-safe progress snapshot for a session's turn."""
        turn = self.get_turn(session_id)
        if turn:
            return turn.get_snapshot()
        return None

    def start_or_get_turn(
        self,
        session_id: str,
        message: str,
        run_pipeline_fn: Callable[..., None],
    ) -> TurnState:
        """
        Starts a background execution thread for the requested turn or attaches to an active one.

        Args:
            session_id: Target ChatSession identifier.
            message: User natural language prompt.
            run_pipeline_fn: Callable taking (db, message, session_id, on_event) that executes the turn.

        Returns:
            TurnState: Active or newly started turn instance.
        """
        with self._lock:
            existing = self._turns.get(session_id)
            if existing and existing.status == "RUNNING":
                return existing

            self._cleanup_old_turns()

            new_turn = TurnState(session_id=session_id, prompt=message)
            self._turns[session_id] = new_turn

        # Launch execution in a daemon background thread with independent DB session
        thread = threading.Thread(
            target=self._run_worker,
            args=(new_turn, session_id, message, run_pipeline_fn),
            daemon=True,
            name=f"turn-worker-{session_id}",
        )
        thread.start()
        return new_turn

    def _run_worker(
        self,
        turn: TurnState,
        session_id: str,
        message: str,
        run_pipeline_fn: Callable[..., None],
    ) -> None:
        """
        Worker thread routine that executes the agent pipeline with its own dedicated DB session.
        Guarantees that database commits succeed regardless of client HTTP connection state.
        """
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            logger.info("Starting background agent turn execution for session: %s", session_id)
            run_pipeline_fn(
                db=db,
                message=message,
                session_id=session_id,
                on_event=turn.add_event,
            )
            logger.info("Successfully finished background agent turn for session: %s", session_id)
        except Exception as exc:
            logger.exception("Error executing background agent turn for session %s: %s", session_id, exc)
            turn.add_event("error", {"message": str(exc)})
        finally:
            try:
                db.close()
            except Exception:
                pass

    def stream_events(
        self,
        session_id: str,
        message: Optional[str] = None,
        run_pipeline_fn: Optional[Callable[..., None]] = None,
    ) -> Generator[str, None, None]:
        """
        Generator yielding Server-Sent Events (SSE) in wire format.
        Supports both initial start and catch-up replay for reconnecting clients.

        Args:
            session_id: Chat session ID.
            message: User prompt (if initiating a new turn).
            run_pipeline_fn: Execution pipeline function (if initiating a new turn).

        Yields:
            str: SSE formatted chunks `data: {...}\\n\\n`.
        """
        if message and run_pipeline_fn:
            turn = self.start_or_get_turn(session_id, message, run_pipeline_fn)
        else:
            turn = self.get_turn(session_id)
            if not turn:
                return

        last_idx = 0
        while True:
            events_to_yield = []
            with turn.condition:
                while last_idx < len(turn.events):
                    events_to_yield.append(turn.events[last_idx])
                    last_idx += 1

                is_finished = turn.status in ("COMPLETED", "ERROR")
                # If no events ready and still running, wait for next event notification
                if not events_to_yield and not is_finished:
                    turn.condition.wait(timeout=0.5)

            for evt in events_to_yield:
                yield f"data: {json.dumps(evt, default=str)}\n\n"

            if is_finished and last_idx >= len(turn.events):
                break

    def _cleanup_old_turns(self) -> None:
        """Removes completed or errored turn records older than 10 minutes to prevent memory leaks."""
        now = datetime.now()
        to_del = []
        for sid, t in self._turns.items():
            if t.status in ("COMPLETED", "ERROR") and t.completed_at:
                if (now - t.completed_at).total_seconds() > 600:
                    to_del.append(sid)
        for sid in to_del:
            self._turns.pop(sid, None)


agent_turn_manager = TurnManager()
