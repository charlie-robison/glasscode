"""Session management endpoints — create, list, stop Claude sessions."""

from fastapi import APIRouter
from pydantic import BaseModel

from .claude_manager import claude_manager
from .project_router import fuzzy_match_project

router = APIRouter()


class CreateSessionRequest(BaseModel):
    project: str
    prompt: str | None = None


@router.post("/sessions")
async def create_session(req: CreateSessionRequest):
    """Open an interactive Claude session in Terminal.app for a project."""
    match = fuzzy_match_project(req.project)
    if not match:
        return {"error": f"No project found matching '{req.project}'"}, 404

    # Step 1: Open interactive Claude in terminal
    session = await claude_manager.open_project(match["path"])

    # Step 2: If a prompt was given, type it into the terminal
    if req.prompt:
        import asyncio
        await asyncio.sleep(3)
        await claude_manager.send_prompt(session.session_id, req.prompt)

    return {
        "session": session.to_dict(),
        "message": f"Opened Terminal.app for {match['name']}"
        + (f" and sent prompt" if req.prompt else ""),
    }


@router.get("/sessions")
async def list_sessions():
    """List all sessions with status."""
    return {
        "sessions": claude_manager.list_sessions(),
        "active_session_id": claude_manager.active_session_id,
    }


@router.delete("/sessions/{session_id}")
async def stop_session(session_id: str):
    """Stop a running session."""
    success = await claude_manager.stop_session(session_id)
    if success:
        return {"status": "stopped", "session_id": session_id}
    return {"error": f"Session {session_id} not found or not running"}
