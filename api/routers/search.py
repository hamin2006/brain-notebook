import json
from typing import AsyncGenerator, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from api.models import AskRequest, AskResponse, SearchRequest, SearchResponse
from open_notebook.ai.models import Model, model_manager
from open_notebook.domain.notebook import (
    resolve_notebook_scope,
    text_search,
    vector_search,
)
from open_notebook.exceptions import (
    DatabaseOperationError,
    InvalidInputError,
    OpenNotebookError,
)

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_knowledge_base(search_request: SearchRequest):
    """Search the knowledge base using text or vector search."""
    try:
        notebook_ids = await resolve_notebook_scope(search_request.scope_notebook_ids)

        if search_request.type == "vector":
            # Check if embedding model is available for vector search
            if not await model_manager.get_embedding_model():
                raise HTTPException(
                    status_code=400,
                    detail="Vector search requires an embedding model. Please configure one in the Models section.",
                )

            results = await vector_search(
                keyword=search_request.query,
                results=search_request.limit,
                source=search_request.search_sources,
                note=search_request.search_notes,
                minimum_score=search_request.minimum_score,
                notebook_ids=notebook_ids,
            )
        else:
            # Text search
            results = await text_search(
                keyword=search_request.query,
                results=search_request.limit,
                source=search_request.search_sources,
                note=search_request.search_notes,
                notebook_ids=notebook_ids,
            )

        return SearchResponse(
            results=results or [],
            total_count=len(results) if results else 0,
            search_type=search_request.type,
        )

    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseOperationError as e:
        logger.error(f"Database error during search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


RESEARCH_TOOLS = {"search", "grep", "list", "outline", "read", "view", "delegate"}


def _ask_state(
    question: str, model_id: str, source_ids, note_ids, notebook_ids
) -> dict:
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=question)],
        "notebook_id": notebook_ids[0] if len(notebook_ids) == 1 else None,
        "source_ids": source_ids,
        "note_ids": note_ids,
        "model_override": model_id,
        "effort": "standard",
    }


async def stream_ask_response(
    question: str,
    strategy_model: Model,
    answer_model: Model,
    final_answer_model: Model,
    notebook_ids: List[str],
) -> AsyncGenerator[str, None]:
    """Answer with the research agent, streamed in the Ask page's event format.

    Each research step is added to the "strategy" the page shows; the agent's
    answer is the final answer. The strategy and answer models of the old Ask
    pipeline are accepted for compatibility; the final answer model runs the agent.
    """
    from open_notebook.agent.graph import (
        get_ephemeral_agent_graph,
        knowledge_base_scope,
    )

    try:
        source_ids, note_ids = await knowledge_base_scope(notebook_ids)
        graph = get_ephemeral_agent_graph()
        state = _ask_state(
            question, final_answer_model.id or "", source_ids, note_ids, notebook_ids
        )
        searches: List[dict] = []
        final_answer = None
        async for mode, chunk in graph.astream(  # type: ignore[call-overload]
            state, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                if chunk.get("type") == "step" and chunk.get("tool") in RESEARCH_TOOLS:
                    args = chunk.get("args") or {}
                    term = (
                        args.get("query")
                        or args.get("pattern")
                        or args.get("address")
                        or args.get("source")
                        or ""
                    )
                    searches.append(
                        {
                            "term": str(term) or chunk["tool"],
                            "instructions": chunk["tool"],
                        }
                    )
                    strategy = {
                        "type": "strategy",
                        "reasoning": "Researching the notebook with search, reading and page views.",
                        "searches": searches,
                    }
                    yield f"data: {json.dumps(strategy)}\n\n"
            else:
                messages = chunk.get("messages") or []
                if messages and getattr(messages[-1], "type", None) == "ai":
                    final_answer = messages[-1].content
        if final_answer:
            yield f"data: {json.dumps({'type': 'final_answer', 'content': final_answer})}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'final_answer': final_answer})}\n\n"

    except Exception as e:
        from open_notebook.utils.error_classifier import classify_error

        # Typed errors already carry a user-facing message; only raw provider
        # exceptions need classifying.
        if isinstance(e, OpenNotebookError):
            user_message = str(e)
        else:
            _, user_message = classify_error(e)
        logger.error(f"Error in ask streaming: {str(e)}")
        error_data = {"type": "error", "message": user_message}
        yield f"data: {json.dumps(error_data)}\n\n"


@router.post("/search/ask")
async def ask_knowledge_base(ask_request: AskRequest):
    """Ask the knowledge base a question using AI models."""
    try:
        # Cheapest check first: a malformed or unknown scope fails before any
        # model lookup or embedding check can mask it.
        notebook_ids = await resolve_notebook_scope(ask_request.scope_notebook_ids)

        # Validate models exist
        strategy_model = await Model.get(ask_request.strategy_model)
        answer_model = await Model.get(ask_request.answer_model)
        final_answer_model = await Model.get(ask_request.final_answer_model)

        if not strategy_model:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy model {ask_request.strategy_model} not found",
            )
        if not answer_model:
            raise HTTPException(
                status_code=400,
                detail=f"Answer model {ask_request.answer_model} not found",
            )
        if not final_answer_model:
            raise HTTPException(
                status_code=400,
                detail=f"Final answer model {ask_request.final_answer_model} not found",
            )

        # Check if embedding model is available
        if not await model_manager.get_embedding_model():
            raise HTTPException(
                status_code=400,
                detail="Ask feature requires an embedding model. Please configure one in the Models section.",
            )

        # For streaming response
        return StreamingResponse(
            stream_ask_response(
                ask_request.question,
                strategy_model,
                answer_model,
                final_answer_model,
                notebook_ids,
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
        logger.error(f"Error in ask endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ask operation failed: {str(e)}")


@router.post("/search/ask/simple", response_model=AskResponse)
async def ask_knowledge_base_simple(ask_request: AskRequest):
    """Ask the knowledge base a question and return a simple response (non-streaming)."""
    try:
        # Cheapest check first: a malformed or unknown scope fails before any
        # model lookup or embedding check can mask it.
        notebook_ids = await resolve_notebook_scope(ask_request.scope_notebook_ids)

        # Validate models exist
        strategy_model = await Model.get(ask_request.strategy_model)
        answer_model = await Model.get(ask_request.answer_model)
        final_answer_model = await Model.get(ask_request.final_answer_model)

        if not strategy_model:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy model {ask_request.strategy_model} not found",
            )
        if not answer_model:
            raise HTTPException(
                status_code=400,
                detail=f"Answer model {ask_request.answer_model} not found",
            )
        if not final_answer_model:
            raise HTTPException(
                status_code=400,
                detail=f"Final answer model {ask_request.final_answer_model} not found",
            )

        # Check if embedding model is available
        if not await model_manager.get_embedding_model():
            raise HTTPException(
                status_code=400,
                detail="Ask feature requires an embedding model. Please configure one in the Models section.",
            )

        # Run the research agent over the scope and return its answer
        from open_notebook.agent.graph import (
            get_ephemeral_agent_graph,
            knowledge_base_scope,
        )

        source_ids, note_ids = await knowledge_base_scope(notebook_ids)
        result = await get_ephemeral_agent_graph().ainvoke(  # type: ignore[call-overload]
            _ask_state(
                ask_request.question,
                final_answer_model.id or "",
                source_ids,
                note_ids,
                notebook_ids,
            )
        )
        messages = result.get("messages") or []
        final_answer = messages[-1].content if messages else None

        if not final_answer:
            raise HTTPException(status_code=500, detail="No answer generated")

        return AskResponse(answer=final_answer, question=ask_request.question)

    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error in ask simple endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ask operation failed: {str(e)}")
