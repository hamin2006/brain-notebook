import asyncio
import json
import traceback
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from api.routers._chat_shared import (
    ChatMessage,
    SuccessResponse,
    extract_chat_messages,
    get_session_or_404,
)
from open_notebook.agent.graph import get_agent_graph
from open_notebook.agent.sessions import (
    discard_unanswered as _discard_unanswered,
)
from open_notebook.agent.sessions import message_count as _message_count
from open_notebook.agent.sessions import thread_messages as _thread_messages
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import ChatSession, Notebook
from open_notebook.exceptions import (
    NotFoundError,
    OpenNotebookError,
)
from open_notebook.utils import token_count
from open_notebook.utils.context_builder import build_notebook_context

router = APIRouter()


def _scope_from_request(
    request: "ExecuteChatRequest",
) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """Explicit ids win; otherwise the ids of the sources/notes the UI put in context."""
    sources, notes = request.source_ids, request.note_ids
    context = request.context or {}
    if sources is None and isinstance(context.get("sources"), list):
        sources = [
            s["id"] for s in context["sources"] if isinstance(s, dict) and s.get("id")
        ]
    if notes is None and isinstance(context.get("notes"), list):
        notes = [
            n["id"] for n in context["notes"] if isinstance(n, dict) and n.get("id")
        ]
    return sources, notes


async def _prepare_turn(request: "ExecuteChatRequest"):
    """Session, notebook, model and the graph input for one chat turn."""
    full_session_id, session = await get_session_or_404(request.session_id)
    notebook_query = await repo_query(
        "SELECT out FROM refers_to WHERE in = $session_id",
        {"session_id": ensure_record_id(full_session_id)},
    )
    notebook_id = str(notebook_query[0]["out"]) if notebook_query else None
    model_override = (
        request.model_override
        if request.model_override is not None
        else getattr(session, "model_override", None)
    )
    source_ids, note_ids = _scope_from_request(request)
    # Explicit id so a failed turn can remove it from the checkpoint.
    images = request.images or []
    user_message = HumanMessage(
        content=request.message,
        id=str(uuid4()),
        additional_kwargs={"attachments": len(images)} if images else {},
    )
    state = {
        "messages": [user_message],
        "notebook_id": notebook_id,
        "source_ids": source_ids,
        "note_ids": note_ids,
        "model_override": model_override,
        "effort": request.effort,
    }
    config = RunnableConfig(
        configurable={
            "thread_id": full_session_id,
            "model_id": model_override,
            "attachments": images,
        }
    )
    return full_session_id, session, user_message, state, config


# Request/Response models
class CreateSessionRequest(BaseModel):
    notebook_id: str = Field(..., description="Notebook ID to create session for")
    title: Optional[str] = Field(None, description="Optional session title")
    model_override: Optional[str] = Field(
        None, description="Optional model override for this session"
    )


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="New session title")
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )


class ChatSessionResponse(BaseModel):
    id: str = Field(..., description="Session ID")
    title: str = Field(..., description="Session title")
    notebook_id: Optional[str] = Field(None, description="Notebook ID")
    created: str = Field(..., description="Creation timestamp")
    updated: str = Field(..., description="Last update timestamp")
    message_count: Optional[int] = Field(
        None, description="Number of messages in session"
    )
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )


class ChatSessionWithMessagesResponse(ChatSessionResponse):
    messages: List[ChatMessage] = Field(
        default_factory=list, description="Session messages"
    )


MAX_ATTACHMENTS = 4
MAX_ATTACHMENT_CHARS = 8_000_000  # base64 of a ~6 MB image


class ExecuteChatRequest(BaseModel):
    session_id: str = Field(..., description="Chat session ID")
    message: str = Field(..., description="User message content")
    context: Dict[str, Any] = Field(
        ..., description="Chat context with sources and notes"
    )
    model_override: Optional[str] = Field(
        None, description="Optional model override for this message"
    )
    effort: Optional[Literal["quick", "standard", "deep"]] = Field(
        None, description="How much research the agent may do (default: standard)"
    )
    source_ids: Optional[List[str]] = Field(
        None,
        description="Sources the agent may search; defaults to the sources in `context`, else the whole notebook",
    )
    note_ids: Optional[List[str]] = Field(
        None, description="Notes the agent may search; same defaults as source_ids"
    )
    images: Optional[List[str]] = Field(
        None,
        max_length=MAX_ATTACHMENTS,
        description="Images attached to this message, as data:image/... URLs. Used for this turn only, not stored",
    )

    @field_validator("images")
    @classmethod
    def _images_are_data_urls(cls, value: Optional[List[str]]):
        for url in value or []:
            if not url.startswith("data:image/"):
                raise ValueError("images must be data:image/... URLs")
            if len(url) > MAX_ATTACHMENT_CHARS:
                raise ValueError("an attached image is too large (max ~6 MB)")
        return value


class ExecuteChatResponse(BaseModel):
    session_id: str = Field(..., description="Session ID")
    messages: List[ChatMessage] = Field(..., description="Updated message list")


class BuildContextRequest(BaseModel):
    notebook_id: str = Field(..., description="Notebook ID")
    context_config: Dict[str, Any] = Field(..., description="Context configuration")


class BuildContextResponse(BaseModel):
    context: Dict[str, Any] = Field(..., description="Built context data")
    token_count: int = Field(..., description="Estimated token count")
    char_count: int = Field(..., description="Character count")


@router.get("/chat/sessions", response_model=List[ChatSessionResponse])
async def get_sessions(notebook_id: str = Query(..., description="Notebook ID")):
    """Get all chat sessions for a notebook."""
    try:
        # Get notebook to verify it exists
        notebook = await Notebook.get(notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        # Get sessions for this notebook
        sessions_list = await notebook.get_chat_sessions()

        results = []
        for session in sessions_list:
            session_id = str(session.id)

            # Get message count from LangGraph state
            msg_count = await _message_count(session_id)

            results.append(
                ChatSessionResponse(
                    id=session.id or "",
                    title=session.title or "Untitled Session",
                    notebook_id=notebook_id,
                    created=str(session.created),
                    updated=str(session.updated),
                    message_count=msg_count,
                    model_override=getattr(session, "model_override", None),
                )
            )

        return results
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching chat sessions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching chat sessions: {str(e)}"
        )


@router.post("/chat/sessions", response_model=ChatSessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new chat session."""
    try:
        # Verify notebook exists
        notebook = await Notebook.get(request.notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        # Create new session
        session = ChatSession(
            title=request.title
            or f"Chat Session {asyncio.get_event_loop().time():.0f}",
            model_override=request.model_override,
        )
        await session.save()

        # Relate session to notebook
        await session.relate_to_notebook(request.notebook_id)

        return ChatSessionResponse(
            id=session.id or "",
            title=session.title or "",
            notebook_id=request.notebook_id,
            created=str(session.created),
            updated=str(session.updated),
            message_count=0,
            model_override=session.model_override,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error creating chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating chat session: {str(e)}"
        )


@router.get(
    "/chat/sessions/{session_id}", response_model=ChatSessionWithMessagesResponse
)
async def get_session(session_id: str):
    """Get a specific session with its messages."""
    try:
        # Get session (normalizes the ID and 404s if missing)
        full_session_id, session = await get_session_or_404(session_id)

        messages: list[ChatMessage] = extract_chat_messages(
            await _thread_messages(full_session_id)
        )

        # Find notebook_id (we need to query the relationship)
        notebook_query = await repo_query(
            "SELECT out FROM refers_to WHERE in = $session_id",
            {"session_id": ensure_record_id(full_session_id)},
        )

        notebook_id = notebook_query[0]["out"] if notebook_query else None

        if not notebook_id:
            # This might be an old session created before API migration
            logger.warning(
                f"No notebook relationship found for session {session_id} - may be an orphaned session"
            )

        return ChatSessionWithMessagesResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            notebook_id=notebook_id,
            created=str(session.created),
            updated=str(session.updated),
            message_count=len(messages),
            messages=messages,
            model_override=getattr(session, "model_override", None),
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching session: {str(e)}")


@router.put("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def update_session(session_id: str, request: UpdateSessionRequest):
    """Update session title."""
    try:
        # Get session (normalizes the ID and 404s if missing)
        full_session_id, session = await get_session_or_404(session_id)

        update_data = request.model_dump(exclude_unset=True)

        if "title" in update_data:
            session.title = update_data["title"]

        if "model_override" in update_data:
            session.model_override = update_data["model_override"]

        await session.save()

        # Find notebook_id
        notebook_query = await repo_query(
            "SELECT out FROM refers_to WHERE in = $session_id",
            {"session_id": ensure_record_id(full_session_id)},
        )
        notebook_id = notebook_query[0]["out"] if notebook_query else None

        # Get message count from LangGraph state
        msg_count = await _message_count(full_session_id)

        return ChatSessionResponse(
            id=session.id or "",
            title=session.title or "",
            notebook_id=notebook_id,
            created=str(session.created),
            updated=str(session.updated),
            message_count=msg_count,
            model_override=session.model_override,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error updating session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating session: {str(e)}")


@router.delete("/chat/sessions/{session_id}", response_model=SuccessResponse)
async def delete_session(session_id: str):
    """Delete a chat session."""
    try:
        # Get session (normalizes the ID and 404s if missing)
        _full_session_id, session = await get_session_or_404(session_id)

        await session.delete()

        return SuccessResponse(success=True, message="Session deleted successfully")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")


@router.post("/chat/execute", response_model=ExecuteChatResponse)
async def execute_chat(request: ExecuteChatRequest):
    """Run one agent turn and return the updated conversation (non-streaming)."""
    try:
        full_session_id, session, user_message, state, config = await _prepare_turn(
            request
        )
        graph = await get_agent_graph()
        try:
            result = await graph.ainvoke(state, config)  # type: ignore[arg-type]
        except BaseException:
            await _discard_unanswered(full_session_id, user_message)
            raise
        await session.save()  # bump the session timestamp
        return ExecuteChatResponse(
            session_id=request.session_id,
            messages=extract_chat_messages(result.get("messages", [])),
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(
            f"Error executing chat: {str(e)}\n"
            f"  Session ID: {request.session_id}\n"
            f"  Traceback:\n{traceback.format_exc()}"
        )
        raise HTTPException(status_code=500, detail=f"Error executing chat: {str(e)}")


def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


async def _stream_turn(
    full_session_id: str,
    session: Any,
    user_message: HumanMessage,
    state: dict,
    config: RunnableConfig,
) -> AsyncIterator[str]:
    answered = False
    try:
        graph = await get_agent_graph()
        final: Dict[str, Any] = {}
        async for mode, chunk in graph.astream(  # type: ignore[call-overload]
            state, config, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                yield _sse(chunk)
            else:
                final = chunk
        messages = extract_chat_messages(final.get("messages", []))
        answered = bool(messages) and messages[-1].type == "ai"
        if answered:
            yield _sse({"type": "ai_message", "message": messages[-1].model_dump()})
        await session.save()
        yield _sse({"type": "complete"})
    except Exception as e:
        from open_notebook.utils.error_classifier import classify_error

        message = str(e) if isinstance(e, OpenNotebookError) else classify_error(e)[1]
        logger.error(f"Error in agent chat stream: {e}")
        yield _sse({"type": "error", "message": message})
    finally:
        # Also covers a client disconnect (the generator is closed mid-turn).
        if not answered:
            await _discard_unanswered(full_session_id, user_message)


@router.post("/chat/execute/stream")
async def execute_chat_stream(request: ExecuteChatRequest):
    """Run one agent turn, streaming its steps and answer as server-sent events.

    Events: step {step, tool, args}, step_result {step, tool, summary},
    text_delta {step, text}, ai_message {message}, complete, error {message}.
    """
    try:
        full_session_id, session, user_message, state, config = await _prepare_turn(
            request
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    return StreamingResponse(
        _stream_turn(full_session_id, session, user_message, state, config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/context", response_model=BuildContextResponse)
async def build_context(request: BuildContextRequest):
    """Build context for a notebook based on context configuration."""
    try:
        # Verify notebook exists
        notebook = await Notebook.get(request.notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        context_data, total_content = await build_notebook_context(
            notebook, request.context_config
        )

        char_count = len(total_content)
        estimated_tokens = token_count(total_content) if total_content else 0

        return BuildContextResponse(
            context=context_data, token_count=estimated_tokens, char_count=char_count
        )
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error building context: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error building context: {str(e)}")
