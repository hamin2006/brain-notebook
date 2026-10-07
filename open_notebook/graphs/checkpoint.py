"""Async LangGraph checkpointer for the async (agentic) chat graphs.

The original chat graphs use the synchronous SqliteSaver, which forces sync
nodes and a new-event-loop workaround. Async graphs use this AsyncSqliteSaver
instead. Both savers share LANGGRAPH_CHECKPOINT_FILE and its schema, so chat
threads written before the switch stay readable.

The saver holds an aiosqlite connection, which is bound to the event loop that
opened it and keeps a background thread alive until closed. It is therefore
created lazily inside the running loop and closed from the API lifespan.
"""

import asyncio
from typing import Optional

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from open_notebook.config import LANGGRAPH_CHECKPOINT_FILE

_saver: Optional[AsyncSqliteSaver] = None
_lock: Optional[asyncio.Lock] = None


async def get_checkpointer(path: str = LANGGRAPH_CHECKPOINT_FILE) -> AsyncSqliteSaver:
    """Return the process-wide async checkpointer, opening it on first use."""
    global _saver, _lock
    if _saver is not None:
        return _saver
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _saver is None:
            conn = await aiosqlite.connect(path)
            saver = AsyncSqliteSaver(conn)
            await saver.setup()
            _saver = saver
    return _saver


async def close_checkpointer() -> None:
    """Close the checkpointer's connection (API shutdown, tests)."""
    global _saver, _lock
    if _saver is not None:
        await _saver.conn.close()
    _saver = None
    _lock = None
