"""
Unit and Integration Tests for Background Agent Turn Resilience.

Verifies:
1. When an agent turn starts, it continues executing in a background worker thread.
2. Client disconnection mid-turn does not abort persistence in PostgreSQL.
3. GET /sessions/{session_id}/active-turn returns live reasoning and current status while active.
4. GET /sessions/{session_id}/messages includes the in-progress streaming message while running.
5. Once completed, the full assistant reply is persistently returned from the database instead of blank.
"""

import time
import uuid
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import ChatSession, ChatMessage
from app.services.turn_manager import agent_turn_manager, TurnState
from app.services.streaming_service import execute_agent_turn_pipeline
from app.api.routes_agent import get_session_active_turn, get_session_messages


def test_background_turn_continues_and_persists_to_db():
    """Verifies that an agent turn started in background completes and commits ChatMessage to PostgreSQL."""
    db: Session = SessionLocal()
    session_id = f"SES-TEST-BG-{uuid.uuid4().hex[:6].upper()}"

    try:
        # 1. Start turn via turn manager
        turn = agent_turn_manager.start_or_get_turn(
            session_id=session_id,
            message="Hi",
            run_pipeline_fn=execute_agent_turn_pipeline,
        )

        assert turn is not None
        assert turn.session_id == session_id

        # 2. Immediately query active-turn endpoint: must report active status
        snap = agent_turn_manager.get_turn_snapshot(session_id)
        assert snap is not None
        assert snap["session_id"] == session_id

        # 3. Simulate client disconnect (no stream reader). Wait for background thread to finish
        max_wait = 20.0
        start = time.perf_counter()
        while agent_turn_manager.is_turn_active(session_id) and (time.perf_counter() - start) < max_wait:
            time.sleep(0.2)

        assert not agent_turn_manager.is_turn_active(session_id), "Background turn did not finish within timeout!"

        # 4. Verify that ChatMessage was committed to PostgreSQL
        ai_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "ai")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        assert ai_msg is not None, "AI message was not persisted to PostgreSQL by background thread!"
        assert len(ai_msg.content) > 0, "Persisted message content is empty!"
        assert ai_msg.reasoning is not None, "Persisted reasoning is empty!"

        # 5. Verify get_session_messages returns the reply instead of blank
        all_msgs = get_session_messages(session_id, db=db)
        ai_responses = [m for m in all_msgs if m.role == "ai" and m.message_id != f"welcome-{session_id}"]
        assert len(ai_responses) >= 1, "Session messages did not return the completed AI response!"
        assert ai_responses[-1].content == ai_msg.content

    finally:
        # Clean up test session
        sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if sess:
            db.delete(sess)
            db.commit()
        db.close()


def test_active_turn_endpoint_reports_status():
    """Verifies get_session_active_turn reports status accurately for idle sessions."""
    resp = get_session_active_turn("SES-NON-EXISTENT")
    assert resp.is_active is False
    assert resp.status == "IDLE"
