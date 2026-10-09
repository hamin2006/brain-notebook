import asyncio
import json
from typing import AsyncGenerator, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
from pydantic import BaseModel, Field

from api.routers._chat_shared import (
    ChatMessage,
    SuccessResponse,
    extract_chat_messages,
    get_source_or_404,
    get_verified_source_session,
    readable_traces,
)
from open_notebook.agent.graph import get_agent_graph
from open_notebook.agent.sessions import (
    discard_unanswered,
    message_count,
    thread_messages,
)
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import ChatSession
from open_notebook.exceptions import (
    NotFoundError,
    OpenNotebookError,
)

router = APIRouter()


# Request/Response models
class CreateSourceChatSessionRequest(BaseModel):
    source_id: str = Field(..., description="Source ID to create chat session for")
    title: Optional[str] = Field(None, description="Optional session title")
    model_override: Optional[str] = Field(
        None, description="Optional model override for this session"
    )


class UpdateSourceChatSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="New session title")
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )


class ContextIndicator(BaseModel):
    sources: List[str] = Field(
        default_factory=list, description="Source IDs used in context"
    )
    insights: List[str] = Field(
        default_factory=list, description="Insight IDs used in context"
    )
    notes: List[str] = Field(
        default_factory=list, description="Note IDs used in context"
    )


class SourceChatSessionResponse(BaseModel):
    id: str = Field(..., description="Session ID")
    title: str = Field(..., description="Session title")
    source_id: str = Field(..., description="Source ID")
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )
    created: str = Field(..., description="Creation timestamp")
    updated: str = Field(..., description="Last update timestamp")
    message_count: Optional[int] = Field(
        None, description="Number of messages in session"
    )


class SourceChatSessionWithMessagesResponse(SourceChatSessionResponse):
    messages: List[ChatMessage] = Field(
        default_factory=list, description="Session messages"
    )
    context_indicators: Optional[ContextIndicator] = Field(
        None, description="Context indicators from last response"
    )


class SendMessageRequest(BaseModel):
    message: str = Field(..., description="User message content")
    model_override: Optional[str] = Field(
        None, description="Optional model override for this message"
    )


@router.post(
    "/sources/{source_id}/chat/sessions", response_model=SourceChatSessionResponse
)
async def create_source_chat_session(
    request: CreateSourceChatSessionRequest,
    source_id: str = Path(..., description="Source ID"),
):
    """Create a new chat session for a source."""
    try:
        # Verify source exists (normalizes the ID and 404s if missing)
        full_source_id, _source = await get_source_or_404(source_id)

        # Create new session with model_override support
        session = ChatSession(
            title=request.title or f"Source Chat {asyncio.get_event_loop().time():.0f}",
            model_override=request.model_override,
        )
        await session.save()

        # Relate session to source using "refers_to" relation
        await session.relate("refers_to", full_source_id)

        return SourceChatSessionResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            source_id=source_id,
            model_override=session.model_override,
            created=str(session.created),
            updated=str(session.updated),
            message_count=0,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error creating source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating source chat session: {str(e)}"
        )


@router.get(
    "/sources/{source_id}/chat/sessions", response_model=List[SourceChatSessionResponse]
)
async def get_source_chat_sessions(source_id: str = Path(..., description="Source ID")):
    """Get all chat sessions for a source."""
    try:
        # Verify source exists (normalizes the ID and 404s if missing)
        full_source_id, _source = await get_source_or_404(source_id)

        # Get sessions that refer to this source - first get relations, then sessions
        relations = await repo_query(
            "SELECT in FROM refers_to WHERE out = $source_id",
            {"source_id": ensure_record_id(full_source_id)},
        )

        sessions = []
        for relation in relations:
            session_id_raw = relation.get("in")
            if session_id_raw:
                session_id = str(session_id_raw)

                session_result = await repo_query(
                    "SELECT * FROM $id", {"id": ensure_record_id(session_id)}
                )
                if session_result and len(session_result) > 0:
                    session_data = session_result[0]

                    msg_count = await message_count(session_id)

                    sessions.append(
                        SourceChatSessionResponse(
                            id=session_data.get("id") or "",
                            title=session_data.get("title") or "Untitled Session",
                            source_id=source_id,
                            model_override=session_data.get("model_override"),
                            created=str(session_data.get("created")),
                            updated=str(session_data.get("updated")),
                            message_count=msg_count,
                        )
                    )

        # Sort sessions by created date (newest first)
        sessions.sort(key=lambda x: x.created, reverse=True)
        return sessions
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching source chat sessions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching source chat sessions: {str(e)}"
        )


@router.get(
    "/sources/{source_id}/chat/sessions/{session_id}",
    response_model=SourceChatSessionWithMessagesResponse,
)
async def get_source_chat_session(
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Get a specific source chat session with its messages."""
    try:
        # Verify source + session exist and are related (404s otherwise)
        (
            _full_source_id,
            _source,
            full_session_id,
            session,
        ) = await get_verified_source_session(source_id, session_id)

        # Source chat runs the research agent scoped to this source; there are
        # no "context indicators" (nothing is pasted into the prompt).
        messages: list[ChatMessage] = await readable_traces(
            extract_chat_messages(await thread_messages(full_session_id))
        )
        context_indicators = None

        return SourceChatSessionWithMessagesResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            source_id=source_id,
            model_override=getattr(session, "model_override", None),
            created=str(session.created),
            updated=str(session.updated),
            message_count=len(messages),
            messages=messages,
            context_indicators=context_indicators,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source or session not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching source chat session: {str(e)}"
        )


@router.put(
    "/sources/{source_id}/chat/sessions/{session_id}",
    response_model=SourceChatSessionResponse,
)
async def update_source_chat_session(
    request: UpdateSourceChatSessionRequest,
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Update source chat session title and/or model override."""
    try:
        # Verify source + session exist and are related (404s otherwise)
        (
            _full_source_id,
            _source,
            full_session_id,
            session,
        ) = await get_verified_source_session(source_id, session_id)

        # Update session fields
        if request.title is not None:
            session.title = request.title
        if request.model_override is not None:
            session.model_override = request.model_override

        await session.save()

        msg_count = await message_count(full_session_id)

        return SourceChatSessionResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            source_id=source_id,
            model_override=getattr(session, "model_override", None),
            created=str(session.created),
            updated=str(session.updated),
            message_count=msg_count,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source or session not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error updating source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating source chat session: {str(e)}"
        )


@router.delete(
    "/sources/{source_id}/chat/sessions/{session_id}", response_model=SuccessResponse
)
async def delete_source_chat_session(
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Delete a source chat session."""
    try:
        # Verify source + session exist and are related (404s otherwise)
        (
            _full_source_id,
            _source,
            full_session_id,
            session,
        ) = await get_verified_source_session(source_id, session_id)

        await session.delete()

        return SuccessResponse(
            success=True, message="Source chat session deleted successfully"
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source or session not found")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error deleting source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting source chat session: {str(e)}"
        )


async def stream_source_chat_response(
    session_id: str, source_id: str, message: str, model_override: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """Run the research agent on this one source, as Server-Sent Events.

    Agent progress events (step, step_result, text_delta) are forwarded; the
    answer comes as the `ai_message` event the source chat UI already handles.
    """
    # Explicit id so a failed turn can remove it from the checkpoint.
    user_message = HumanMessage(content=message, id=str(uuid4()))
    answered = False
    try:
        yield f"data: {json.dumps({'type': 'user_message', 'content': message, 'timestamp': None})}\n\n"
        graph = await get_agent_graph()
        state = {
            "messages": [user_message],
            "notebook_id": None,
            "source_ids": [source_id],
            "note_ids": [],
            "model_override": model_override,
            "effort": None,
        }
        config = RunnableConfig(
            configurable={"thread_id": session_id, "model_id": model_override}
        )
        final: dict = {}
        async for mode, chunk in graph.astream(  # type: ignore[call-overload]
            state, config, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                yield f"data: {json.dumps(chunk, default=str)}\n\n"
            else:
                final = chunk
        messages = final.get("messages") or []
        if messages and getattr(messages[-1], "type", None) == "ai":
            answered = True
            ai_event = {
                "type": "ai_message",
                "content": messages[-1].content,
                "timestamp": None,
            }
            yield f"data: {json.dumps(ai_event)}\n\n"
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    except Exception as e:
        from open_notebook.utils.error_classifier import classify_error

        # Typed errors already carry a user-facing message; only raw provider
        # exceptions need classifying.
        if isinstance(e, OpenNotebookError):
            error_message = str(e)
        else:
            _, error_message = classify_error(e)
        logger.error(f"Error in source chat streaming: {str(e)}")
        error_event = {"type": "error", "message": error_message}
        yield f"data: {json.dumps(error_event)}\n\n"
    finally:
        if not answered:
            await discard_unanswered(session_id, user_message)


@router.post("/sources/{source_id}/chat/sessions/{session_id}/messages")
async def send_message_to_source_chat(
    request: SendMessageRequest,
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Send a message to source chat session with SSE streaming response."""
    try:
        # Verify source + session exist and are related (404s otherwise)
        (
            full_source_id,
            _source,
            full_session_id,
            session,
        ) = await get_verified_source_session(source_id, session_id)

        if not request.message:
            raise HTTPException(status_code=400, detail="Message content is required")

        # Determine model override (request override takes precedence over session override)
        model_override = request.model_override or getattr(
            session, "model_override", None
        )

        # Update session timestamp
        await session.save()

        # Return streaming response
        return StreamingResponse(
            stream_source_chat_response(
                session_id=full_session_id,
                source_id=full_source_id,
                message=request.message,
                model_override=model_override,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error sending message to source chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending message: {str(e)}")
