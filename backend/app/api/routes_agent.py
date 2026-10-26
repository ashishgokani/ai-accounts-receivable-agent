"""
Agent Orchestration and Interaction Endpoints.

Provides REST interfaces for Mode A (Autonomous Batch Execution / 'Run Agent Now')
and Mode B (Interactive Administrator Chat with Session History, Chain-of-Thought
Reasoning, and Configurable Token/Character Guardrails).
"""

import json
import math
import uuid
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import ist_naive_now
from app.db.session import get_db
from app.db.models import AgentAction, ChatSession, ChatMessage
from app.schemas.schemas import (
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatMessageResponse,
    ChatConfigResponse,
    AutonomousRunResponse,
    AgentActionResponse,
    PaginatedActivityResponse,
    ActiveTurnResponse,
)
from app.services.orchestrator import AgentOrchestrator
from app.services.streaming_service import stream_agent_turn, compute_credits
from app.services.turn_manager import agent_turn_manager

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])


@router.get("/config", response_model=ChatConfigResponse)
def get_chat_configuration(
    session_id: Optional[str] = Query(None, description="Optional active session ID to calculate thread token allowance"),
    db: Session = Depends(get_db),
):
    """Returns runtime chat policies, limits, remaining dual credits, and foundation model badge."""
    # Friendly display name without internal technical codes
    model_display = "Amazon Nova Pro"
    if "nova-lite" in settings.bedrock_model_id.lower():
        model_display = "Amazon Nova Lite"
    elif "mistral" in settings.bedrock_model_id.lower():
        model_display = "Mistral Large"
    elif "claude" in settings.bedrock_model_id.lower():
        model_display = "Anthropic Claude"

    credit_info = compute_credits(db, session_id)

    return ChatConfigResponse(
        max_history_turns=settings.chat_max_history_turns,
        max_chars=settings.chat_max_chars,
        daily_credits=credit_info["daily_credits"],
        session_credits=credit_info["session_credits"],
        credits_left=credit_info["credits_left"],
        daily_credits_left=credit_info["daily_credits_left"],
        session_credits_left=credit_info["session_credits_left"],
        model_name=model_display,
    )


@router.get("/sessions", response_model=List[ChatSessionResponse])
def list_chat_sessions(db: Session = Depends(get_db)):
    """Retrieves all chat sessions sorted by most recent activity for the sidebar history."""
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
    results = []

    for s in sessions:
        last_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == s.session_id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        preview = last_msg.content[:80] + ("..." if len(last_msg.content) > 80 else "") if last_msg else None
        results.append(
            ChatSessionResponse(
                session_id=s.session_id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                last_message=preview,
            )
        )
    return results


WELCOME_MESSAGE_CONTENT = (
    "Hello! I am your Autonomous Accounts Receivable Intelligence Assistant.\n\n"
    "You can ask me to monitor overdue accounts, check customer risk ratings, dispatch custom emails, or audit debtor records with live real-time reasoning."
)


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
def create_chat_session(payload: ChatSessionCreate, db: Session = Depends(get_db)):
    """Initializes a new chat session with persistent welcome message."""
    session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
    new_sess = ChatSession(
        session_id=session_id,
        title=payload.title or "New Conversation",
        created_at=ist_naive_now(),
        updated_at=ist_naive_now(),
    )
    db.add(new_sess)
    db.flush()

    # Seed the persistent first welcome message so it is never removed
    welcome_msg = ChatMessage(
        message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
        session_id=session_id,
        role="ai",
        content=WELCOME_MESSAGE_CONTENT,
        reasoning="System initialized with live PostgreSQL database and corporate credit control policies.",
        execution_seconds=0.1,
        actions_taken=json.dumps([]),
        tool_calls=json.dumps([]),
        created_at=ist_naive_now(),
    )
    db.add(welcome_msg)
    db.commit()
    db.refresh(new_sess)

    return ChatSessionResponse(
        session_id=new_sess.session_id,
        title=new_sess.title,
        created_at=new_sess.created_at,
        updated_at=new_sess.updated_at,
        last_message=WELCOME_MESSAGE_CONTENT[:80],
    )


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    """Retrieves conversation history turns for a specific chat session, ensuring welcome message is always first."""
    sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    # If session has no messages or does not start with the welcome message, seed it persistently
    if not msgs:
        welcome_msg = ChatMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            session_id=session_id,
            role="ai",
            content=WELCOME_MESSAGE_CONTENT,
            reasoning="System initialized with live PostgreSQL database and corporate credit control policies.",
            execution_seconds=0.1,
            actions_taken=json.dumps([]),
            tool_calls=json.dumps([]),
            created_at=sess.created_at or ist_naive_now(),
        )
        db.add(welcome_msg)
        db.commit()
        msgs = [welcome_msg]
    elif msgs[0].role != "ai" or "Autonomous Accounts Receivable" not in msgs[0].content:
        # Prepend persistent welcome message for older sessions
        first_created = msgs[0].created_at or ist_naive_now()
        welcome_msg = ChatMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
            session_id=session_id,
            role="ai",
            content=WELCOME_MESSAGE_CONTENT,
            reasoning="System initialized with live PostgreSQL database and corporate credit control policies.",
            execution_seconds=0.1,
            actions_taken=json.dumps([]),
            tool_calls=json.dumps([]),
            created_at=first_created - timedelta(seconds=1),
        )
        db.add(welcome_msg)
        db.commit()
        msgs = [welcome_msg] + msgs

    formatted = []
    for m in msgs:
        formatted.append(
            ChatMessageResponse(
                message_id=m.message_id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                reasoning=m.reasoning,
                execution_seconds=m.execution_seconds or 0.0,
                actions_taken=json.loads(m.actions_taken) if m.actions_taken else [],
                tool_calls=json.loads(m.tool_calls) if m.tool_calls else [],
                created_at=m.created_at,
                is_streaming=False,
                streaming_status=None,
            )
        )

    # Check if a background turn is currently actively running for this session
    active_snap = agent_turn_manager.get_turn_snapshot(session_id)
    if active_snap and active_snap["is_active"]:
        formatted.append(
            ChatMessageResponse(
                message_id=f"active-{session_id}",
                session_id=session_id,
                role="ai",
                content=active_snap.get("content") or "",
                reasoning=active_snap.get("reasoning") or "",
                execution_seconds=active_snap.get("execution_seconds", 0.0),
                actions_taken=active_snap.get("actions_taken", []),
                tool_calls=[],
                created_at=active_snap.get("started_at") or ist_naive_now(),
                is_streaming=True,
                streaming_status=active_snap.get("current_status"),
            )
        )

    return formatted


@router.get("/sessions/{session_id}/active-turn", response_model=ActiveTurnResponse)
def get_session_active_turn(session_id: str):
    """
    Returns the in-progress background turn status and reasoning for a chat session.
    Allows frontend clients to resume thought tracking when switching tabs or reconnecting.
    """
    snap = agent_turn_manager.get_turn_snapshot(session_id)
    if not snap:
        return ActiveTurnResponse(
            is_active=False,
            session_id=session_id,
            status="IDLE",
        )

    return ActiveTurnResponse(
        is_active=snap["is_active"],
        session_id=session_id,
        status=snap["status"],
        reasoning=snap.get("reasoning"),
        current_status=snap.get("current_status"),
        content=snap.get("content"),
        execution_seconds=snap.get("execution_seconds", 0.0),
        actions_taken=snap.get("actions_taken", []),
        session_title=snap.get("session_title"),
    )


@router.delete("/sessions/{session_id}")
def delete_chat_session(session_id: str, db: Session = Depends(get_db)):
    """Deletes a chat session and all associated turns."""
    sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    db.delete(sess)
    db.commit()
    return {"status": "SUCCESS", "message": f"Session {session_id} deleted."}


@router.put("/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_chat_session(
    session_id: str,
    payload: ChatSessionUpdate,
    db: Session = Depends(get_db),
):
    """Renames an existing chat session with custom administrator title."""
    sess = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    sess.title = payload.title.strip()
    sess.updated_at = ist_naive_now()
    db.commit()
    db.refresh(sess)

    return ChatSessionResponse(
        session_id=sess.session_id,
        title=sess.title,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
        last_message=None,
    )


@router.post("/chat", response_model=ChatResponse)
def chat_with_agent(payload: ChatRequest, db: Session = Depends(get_db)):
    """
    Submits a natural-language prompt to the Bedrock Intelligent Orchestrator.
    Enforces maximum character input validation, extracts ReAct reasoning thoughts,
    and returns token credit metrics.
    """
    # 1. Enforce message character limit
    if len(payload.message) > settings.chat_max_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt exceeds the configured maximum limit of {settings.chat_max_chars} characters (submitted {len(payload.message)} characters).",
        )

    # 2. Check remaining credit quota (dual enforcement: daily and per-chat)
    credits_info = compute_credits(db, payload.session_id)
    if credits_info["daily_credits_left"] <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Daily AI credit quota ({settings.chat_daily_credits} messages/day) reached. Quota resets at midnight.",
        )
    if credits_info["session_credits_left"] <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Per-chat credit limit ({settings.chat_session_credits} messages/chat) reached to prevent excessive token context accumulation. Please start a new chat thread.",
        )

    # 3. Process turn through Agent Orchestrator
    result = AgentOrchestrator.process_chat(
        db=db,
        message=payload.message,
        session_id=payload.session_id,
    )

    # 4. Recompute credits after successful turn
    updated_credits = compute_credits(db, result["session_id"])

    return ChatResponse(
        reply=result["reply"],
        session_id=result["session_id"],
        session_title=result.get("session_title"),
        reasoning=result.get("reasoning"),
        execution_seconds=result.get("execution_seconds", 0.0),
        credits_left=updated_credits["credits_left"],
        daily_credits_left=updated_credits["daily_credits_left"],
        session_credits_left=updated_credits["session_credits_left"],
        daily_credits=updated_credits["daily_credits"],
        session_credits=updated_credits["session_credits"],
        tool_calls=result.get("tool_calls", []),
        actions_taken=result.get("actions_taken", []),
    )


@router.post("/chat/stream")
def chat_with_agent_stream(
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Real-Time SSE Streaming Endpoint.
    Streams live chain-of-thought tokens, tool execution statuses,
    and visual response chunks to the frontend in real time.
    """
    if len(payload.message) > settings.chat_max_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt exceeds the configured maximum limit of {settings.chat_max_chars} characters.",
        )

    return StreamingResponse(
        stream_agent_turn(db=db, message=payload.message, session_id=payload.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/run-autonomous", response_model=AutonomousRunResponse)
def trigger_autonomous_agent(db: Session = Depends(get_db)):
    """
    Triggers Mode A: Autonomous periodic collection batch run ('Run Agent Now').
    Checks incoming emails, executes collection decisions, advances scheduler state, and updates last_run_at.
    """
    from app.services.scheduler import automation_scheduler
    result = automation_scheduler.trigger_cycle_now(db)
    return AutonomousRunResponse(
        status=result["status"],
        invoices_analyzed=result["invoices_analyzed"],
        actions_executed=result["actions_executed"],
        approvals_pending=result["approvals_pending"],
        summary=result["summary"],
        action_logs=result["action_logs"],
    )


@router.get("/chat/search")
def search_chat_history(
    q: str = Query(..., min_length=1, description="Query string to search in sessions and messages"),
    db: Session = Depends(get_db),
):
    """
    Searches across all historical user prompts, assistant replies, and chat titles.
    Returns matched sessions with contextual snippets.
    """
    term = f"%{q.strip()}%"

    # Search messages matching content
    matched_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.content.ilike(term))
        .order_by(ChatMessage.created_at.desc())
        .limit(30)
        .all()
    )

    sessions_map = {}
    for m in matched_messages:
        if m.session_id not in sessions_map:
            sess = db.query(ChatSession).filter(ChatSession.session_id == m.session_id).first()
            sessions_map[m.session_id] = {
                "session_id": m.session_id,
                "title": sess.title if sess else "Untitled Conversation",
                "updated_at": sess.updated_at.isoformat() if (sess and sess.updated_at) else (m.created_at.isoformat() if m.created_at else None),
                "matches": [],
            }

        idx = m.content.lower().find(q.strip().lower())
        start = max(0, idx - 35)
        end = min(len(m.content), idx + len(q) + 45)
        snippet = ("..." if start > 0 else "") + m.content[start:end].replace("\n", " ") + ("..." if end < len(m.content) else "")

        sessions_map[m.session_id]["matches"].append({
            "message_id": m.message_id,
            "role": m.role,
            "snippet": snippet,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    # Also search session titles directly
    title_matches = (
        db.query(ChatSession)
        .filter(ChatSession.title.ilike(term))
        .limit(10)
        .all()
    )
    for ts in title_matches:
        if ts.session_id not in sessions_map:
            sessions_map[ts.session_id] = {
                "session_id": ts.session_id,
                "title": ts.title,
                "updated_at": ts.updated_at.isoformat() if ts.updated_at else None,
                "matches": [{
                    "message_id": "title",
                    "role": "session_title",
                    "snippet": f"Matching Chat Title: '{ts.title}'",
                    "created_at": ts.updated_at.isoformat() if ts.updated_at else None,
                }],
            }

    return list(sessions_map.values())
