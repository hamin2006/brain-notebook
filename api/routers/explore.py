"""Read-only views of what ingestion built, for the UI: a notebook's overview
(counts and most shared concepts), one concept's mentions and relations, and a
document's structure (metadata, outline, concepts)."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from open_notebook.agent.retrieval import (
    concept_mentions,
    concept_relations,
    document_summary,
    scoped_concepts,
    sections_of,
)
from open_notebook.agent.scope import AgentScope, load_scope, per_source
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.exceptions import NotFoundError

router = APIRouter()


class ConceptSummary(BaseModel):
    id: str
    name: str
    documents: int
    mentions: int


class NotebookOverview(BaseModel):
    documents: int
    pages: int
    sections: int
    notes: int
    concepts: int
    top_concepts: List[ConceptSummary]


class ConceptMention(BaseModel):
    source_id: str
    source_title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    context: Optional[str] = None


class ConceptRelation(BaseModel):
    concept_id: str
    name: str
    relation: str
    outgoing: bool
    source_id: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class ConceptDetail(BaseModel):
    id: str
    name: str
    mentions: List[ConceptMention]
    relations: List[ConceptRelation]


class SourceSection(BaseModel):
    index: int
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    summary: Optional[str] = None


class SourceStructure(BaseModel):
    id: str
    metadata: Dict[str, Any]
    page_count: int
    summary: Optional[str] = None
    sections: List[SourceSection]
    concepts: List[ConceptSummary]


async def _notebook_scope(notebook_id: str) -> AgentScope:
    from open_notebook.agent.graph import knowledge_base_scope

    rows = await repo_query(
        "SELECT VALUE id FROM $nb", {"nb": ensure_record_id(notebook_id)}
    )
    if not rows:
        raise NotFoundError("Notebook not found")
    sources, notes = await knowledge_base_scope([notebook_id])
    return await load_scope(sources, notes, notebook_id)


def _ranked(concepts: Dict[str, Dict[str, Any]], limit: int) -> List[ConceptSummary]:
    ranked = sorted(
        concepts.items(),
        key=lambda item: (
            -len(item[1]["documents"]),
            -item[1]["mentions"],
            item[1]["name"],
        ),
    )
    return [
        ConceptSummary(
            id=cid,
            name=c["name"],
            documents=len(c["documents"]),
            mentions=c["mentions"],
        )
        for cid, c in ranked[:limit]
    ]


@router.get("/notebooks/{notebook_id}/overview", response_model=NotebookOverview)
async def notebook_overview(
    notebook_id: str, limit: int = Query(24, ge=1, le=200)
) -> NotebookOverview:
    scope = await _notebook_scope(notebook_id)
    source_ids = [ensure_record_id(s) for s in scope.sources]
    sections = await per_source(
        "SELECT source, count() AS n FROM source_section WHERE source = $s GROUP BY source",
        source_ids,
    )
    concepts = await scoped_concepts(scope)
    return NotebookOverview(
        documents=len(scope.sources),
        pages=sum(s.page_count for s in scope.sources.values()),
        sections=sum(row["n"] for row in sections),
        notes=len(scope.notes),
        concepts=len(concepts),
        top_concepts=_ranked(concepts, limit),
    )


@router.get(
    "/notebooks/{notebook_id}/concepts/{concept_id}", response_model=ConceptDetail
)
async def notebook_concept(notebook_id: str, concept_id: str) -> ConceptDetail:
    scope = await _notebook_scope(notebook_id)
    names = await repo_query(
        "SELECT VALUE name FROM $c", {"c": ensure_record_id(concept_id)}
    )
    if not names:
        raise NotFoundError("Concept not found")

    def title(source: Any) -> str:
        found = scope.sources.get(str(source))
        return found.title if found else str(source)

    mentions = [
        ConceptMention(
            source_id=str(m["source"]),
            source_title=title(m["source"]),
            page_start=m.get("page_start"),
            page_end=m.get("page_end"),
            context=m.get("context"),
        )
        for m in await concept_mentions(concept_id, scope)
    ]
    relations = []
    for r in await concept_relations(concept_id, scope):
        outgoing = str(r["from_concept"]) == concept_id
        relations.append(
            ConceptRelation(
                concept_id=str(r["to_concept"] if outgoing else r["from_concept"]),
                name=(r.get("to_name") if outgoing else r.get("from_name")) or "",
                relation=r.get("relation") or "",
                outgoing=outgoing,
                source_id=str(r["source"]),
                page_start=r.get("page_start"),
                page_end=r.get("page_end"),
            )
        )
    return ConceptDetail(
        id=concept_id, name=names[0], mentions=mentions, relations=relations
    )


@router.get("/sources/{source_id}/structure", response_model=SourceStructure)
async def source_structure(source_id: str) -> SourceStructure:
    if not source_id.startswith("source:"):
        source_id = f"source:{source_id}"
    scope = await load_scope([source_id], [])
    source = scope.sources.get(source_id)
    if not source:
        raise NotFoundError("Source not found")
    concepts = await scoped_concepts(scope)
    return SourceStructure(
        id=source_id,
        metadata=source.metadata,
        page_count=source.page_count,
        summary=await document_summary(source_id),
        sections=[
            SourceSection(
                index=s["index"],
                title=s.get("title") or "",
                page_start=s.get("page_start"),
                page_end=s.get("page_end"),
                summary=s.get("summary"),
            )
            for s in await sections_of(source_id)
        ],
        concepts=_ranked(concepts, 40),
    )
