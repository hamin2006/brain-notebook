"""Agent extensions: settings, memories and backfills (agentic RAG plan, Phase 5)."""

from typing import Any, List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.command_service import CommandService
from open_notebook.agent.memory import delete_memory
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.agent_settings import AgentSettings
from open_notebook.exceptions import NotFoundError

router = APIRouter()


class AgentSettingsModel(BaseModel):
    rerank_model: Optional[str] = Field(
        None, description="OpenRouter rerank model id; empty turns reranking off"
    )
    page_embedding_model: Optional[str] = Field(
        None,
        description="OpenRouter multimodal embedding model id; empty turns visual page search off",
    )
    knowledge_graph: Optional[bool] = Field(
        None, description="Extract a concept graph after document analysis"
    )
    memory: Optional[bool] = Field(
        None, description="Let the agent remember things across conversations"
    )


class MemoryResponse(BaseModel):
    id: str
    content: str
    notebook_id: Optional[str]
    created: str


class RebuildAgentDataRequest(BaseModel):
    what: Literal["page_embeddings", "concepts"]
    force: bool = Field(
        False,
        description="page_embeddings: re-embed pages that already have an embedding (after changing the model)",
    )
    reset: bool = Field(
        False,
        description="concepts: clear the whole concept graph first (a clean rebuild)",
    )


class RebuildAgentDataResponse(BaseModel):
    submitted: int
    command_ids: List[str]


def _settings_model(settings: AgentSettings) -> AgentSettingsModel:
    return AgentSettingsModel(
        rerank_model=settings.rerank_model or "",
        page_embedding_model=settings.page_embedding_model or "",
        knowledge_graph=bool(settings.knowledge_graph),
        memory=bool(settings.memory),
    )


@router.get("/agent/settings", response_model=AgentSettingsModel)
async def get_agent_settings():
    return _settings_model(await AgentSettings.load())


@router.put("/agent/settings", response_model=AgentSettingsModel)
async def update_agent_settings(update: AgentSettingsModel):
    settings = await AgentSettings.load()
    for field in update.model_fields_set:
        value = getattr(update, field)
        if isinstance(value, str):
            value = value.strip()
        setattr(settings, field, value)
    await settings.update()
    return _settings_model(settings)


@router.get("/agent/memories", response_model=List[MemoryResponse])
async def list_memories(notebook_id: Optional[str] = None):
    """All memories, or those that apply in one notebook (its own and the global ones)."""
    if notebook_id:
        rows = await repo_query(
            "SELECT id, content, notebook, created FROM memory WHERE notebook = NONE OR notebook = $nb ORDER BY created",
            {"nb": ensure_record_id(notebook_id)},
        )
    else:
        rows = await repo_query(
            "SELECT id, content, notebook, created FROM memory ORDER BY created"
        )
    return [
        MemoryResponse(
            id=str(r["id"]),
            content=r["content"],
            notebook_id=str(r["notebook"]) if r.get("notebook") else None,
            created=str(r.get("created", "")),
        )
        for r in rows
    ]


@router.delete("/agent/memories/{memory_id}")
async def remove_memory(memory_id: str):
    full_id = memory_id if memory_id.startswith("memory:") else f"memory:{memory_id}"
    if not await delete_memory(full_id):
        raise NotFoundError(f"Memory {full_id} not found")
    return {"deleted": full_id}


@router.post("/agent/rebuild", response_model=RebuildAgentDataResponse)
async def rebuild_agent_data(request: RebuildAgentDataRequest):
    """Run page embedding or concept extraction for every analyzed source, e.g.
    after turning a feature on or changing the page embedding model."""
    table = "source_page" if request.what == "page_embeddings" else "source_section"
    if request.what == "concepts" and request.reset:
        for graph_table in (
            "concept_mention",
            "concept_relation",
            "concept_alias",
            "concept",
        ):
            await repo_query(f"DELETE {graph_table}")
    sources: List[Any] = await repo_query("SELECT VALUE id FROM source")
    ids: List[str] = []
    for source_id in sources:
        has_rows = await repo_query(
            f"SELECT VALUE id FROM {table} WHERE source = $s LIMIT 1",
            {"s": ensure_record_id(str(source_id))},
        )
        if not has_rows:
            continue
        if request.what == "page_embeddings":
            command, args = (
                "embed_pages",
                {"source_id": str(source_id), "force": request.force},
            )
        else:
            command, args = "extract_concepts", {"source_id": str(source_id)}
        ids.append(
            await CommandService.submit_command_job("open_notebook", command, args)
        )
    return RebuildAgentDataResponse(submitted=len(ids), command_ids=ids)
