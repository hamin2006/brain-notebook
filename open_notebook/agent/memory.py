"""Agent memory: things the user asked the agent to remember, across conversations.

A memory belongs to a notebook or applies everywhere (notebook NONE). The
relevant ones are put in the system prompt at the start of each turn; the
agent adds and removes them with the `remember` and `forget` tools, only when
the user asks or states a lasting preference.
"""

from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from loguru import logger
from pydantic import BaseModel, Field

from open_notebook.agent.scope import AgentScope, ToolError
from open_notebook.database.repository import ensure_record_id, repo_query

MAX_RECALLED = 20
MAX_MEMORY_CHARS = 500


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def list_memories(notebook_id: Optional[str]) -> List[Dict[str, Any]]:
    """Memories that apply in a notebook (its own plus the global ones), oldest first."""
    if notebook_id:
        return await repo_query(
            """
            SELECT id, content, notebook, embedding, created FROM memory
            WHERE notebook = NONE OR notebook = $nb ORDER BY created
            """,
            {"nb": ensure_record_id(notebook_id)},
        )
    return await repo_query(
        "SELECT id, content, notebook, embedding, created FROM memory WHERE notebook = NONE ORDER BY created"
    )


async def recall(
    notebook_id: Optional[str], question: str, k: int = MAX_RECALLED
) -> List[Dict[str, Any]]:
    """The memories to show for a question: all of them when few, else the k most similar."""
    try:
        memories = await list_memories(notebook_id)
    except Exception as e:  # memory must never break a turn
        logger.warning(f"Could not load memories: {e}")
        return []
    if len(memories) <= k:
        return memories
    try:
        from open_notebook.utils.embedding import generate_embedding

        vector = await generate_embedding(question)
    except Exception as e:
        logger.warning(f"Memory recall without vectors: {e}")
        return memories[-k:]  # the most recent
    scored = sorted(
        memories,
        key=lambda m: -_cosine(m["embedding"], vector) if m.get("embedding") else 1.0,
    )
    return scored[:k]


def format_memories(memories: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"- [{m['id']}] {m['content']}{'' if m.get('notebook') else ' (everywhere)'}"
        for m in memories
    )


async def save_memory(content: str, notebook_id: Optional[str]) -> str:
    content = content.strip()
    if not content:
        raise ToolError("Give the fact or preference to remember.")
    if len(content) > MAX_MEMORY_CHARS:
        raise ToolError(
            f"Keep a memory under {MAX_MEMORY_CHARS} characters; save the gist."
        )
    embedding: Optional[List[float]] = None
    try:
        from open_notebook.utils.embedding import generate_embedding

        embedding = await generate_embedding(content)
    except Exception as e:
        logger.warning(f"Memory saved without an embedding: {e}")
    rows = await repo_query(
        "CREATE memory CONTENT {content: $content, notebook: $nb, embedding: $embedding}",
        {
            "content": content,
            "nb": ensure_record_id(notebook_id) if notebook_id else None,
            "embedding": embedding,
        },
    )
    return str(rows[0]["id"])


async def delete_memory(memory_id: str) -> bool:
    if not memory_id.startswith("memory:"):
        return False
    rows = await repo_query(
        "DELETE $id RETURN BEFORE", {"id": ensure_record_id(memory_id)}
    )
    return bool(rows)


class RememberArgs(BaseModel):
    content: str = Field(
        description="The fact or preference, as a short self-contained sentence"
    )
    everywhere: bool = Field(
        False,
        description="True for something about the user that applies in every notebook; false for this notebook only",
    )


class ForgetArgs(BaseModel):
    memory_id: str = Field(description="The memory's id, e.g. memory:abc")


def memory_tools(scope: AgentScope) -> List[StructuredTool]:
    async def remember(content: str, everywhere: bool = False) -> str:
        try:
            notebook = None if everywhere else scope.notebook_id
            memory_id = await save_memory(content, notebook)
        except ToolError as e:
            return f"Error: {e}"
        where = "in this notebook" if notebook else "everywhere"
        return f"Remembered as {memory_id} ({where})."

    async def forget(memory_id: str) -> str:
        if await delete_memory(memory_id.strip()):
            return f"Forgot {memory_id}."
        return f"Error: no memory {memory_id!r}; use an id from the remembered list."

    return [
        StructuredTool.from_function(
            coroutine=remember,
            name="remember",
            description=(
                "Remember something across conversations: only when the user asks you to remember it, or states a "
                "lasting preference or fact about themselves or their goals (e.g. exam dates, preferred answer style). "
                "Never for facts from the documents."
            ),
            args_schema=RememberArgs,
        ),
        StructuredTool.from_function(
            coroutine=forget,
            name="forget",
            description="Delete a remembered item when the user asks you to forget it or it is no longer true.",
            args_schema=ForgetArgs,
        ),
    ]
