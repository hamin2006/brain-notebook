"""Chat-session helpers on the agent graph's async checkpointer, shared by the
notebook-chat and source-chat routers."""

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger

from open_notebook.agent.graph import get_agent_graph


async def thread_messages(session_id: str) -> list:
    """The checkpointed messages of a chat session ([] when it has none)."""
    graph = await get_agent_graph()
    state = await graph.aget_state(
        RunnableConfig(configurable={"thread_id": session_id})
    )
    return list((state.values or {}).get("messages", [])) if state else []


async def message_count(session_id: str) -> int:
    try:
        return len(await thread_messages(session_id))
    except Exception as e:
        logger.warning(f"Could not fetch message count for session {session_id}: {e}")
        return 0


async def discard_unanswered(session_id: str, message: HumanMessage) -> None:
    """Drop a question whose turn failed, so a retry doesn't add it twice. Never raises."""
    try:
        graph = await get_agent_graph()
        config = RunnableConfig(configurable={"thread_id": session_id})
        if any(
            getattr(m, "id", None) == message.id
            for m in await thread_messages(session_id)
        ):
            await graph.aupdate_state(
                config, {"messages": [RemoveMessage(id=message.id or "")]}
            )
    except Exception:
        logger.exception(f"Could not discard unanswered message in {session_id}")
