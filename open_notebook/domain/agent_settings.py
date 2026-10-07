from typing import ClassVar, Optional

from pydantic import Field

from open_notebook.domain.base import RecordModel


class AgentSettings(RecordModel):
    """Switches for the agent's optional extensions (agentic RAG plan, Phase 5).

    Model fields hold OpenRouter model ids; empty or None turns the feature off.
    """

    record_id: ClassVar[str] = "open_notebook:agent_settings"
    rerank_model: Optional[str] = Field(
        "voyageai/rerank-3-lite",
        description="Reranks passage search candidates (OpenRouter rerank model)",
    )
    page_embedding_model: Optional[str] = Field(
        "google/gemini-embedding-2",
        description="Embeds rendered pages for visual search (OpenRouter multimodal embedding model)",
    )
    knowledge_graph: Optional[bool] = Field(
        True, description="Extract a concept graph from document sections"
    )
    memory: Optional[bool] = Field(
        True, description="Let the agent remember things across conversations"
    )
    web_search: Optional[bool] = Field(
        False,
        description="Let the agent search the web (self-hosted SearXNG) in notebooks that allow general knowledge",
    )

    @classmethod
    async def load(cls) -> "AgentSettings":
        """The settings as stored now. The API and the worker are separate
        processes, so each read goes to the database instead of a cached copy."""
        instance = cls()
        object.__setattr__(instance, "_db_loaded", False)
        await instance._load_from_db()
        return instance
