"""Concept graph extraction from document sections (agentic RAG plan, Phase 5).

For each section of an analyzed source, the research ("tools") model lists the
concepts the section covers and the relations it states. Concepts are shared
across documents by normalized name; mentions and relations belong to the
source and section they came from, so re-running replaces only this source's
part of the graph. The agent reads the graph with the `graph` tool.
"""

import asyncio
import time
from typing import Dict, List, Optional

from ai_prompter import Prompter
from langchain_core.output_parsers.pydantic import PydanticOutputParser
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command

from open_notebook.ai.provision import limit_reasoning, provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_insert, repo_query
from open_notebook.domain.agent_settings import AgentSettings
from open_notebook.domain.ingestion import StageRun, tracked
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import ConfigurationError, NotFoundError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.concepts import (
    MAX_CONCEPTS_PER_SECTION,
    MAX_RELATIONS_PER_SECTION,
    ConceptExtraction,
    alias_id,
    concept_id,
    concept_key,
    concept_names,
    parse_extraction,
)
from open_notebook.utils.embedding import generate_embeddings
from open_notebook.utils.pdf_pages import PdfPage, group_builds
from open_notebook.utils.sections import Section, section_text
from open_notebook.utils.text_utils import extract_text_content

CONCEPT_RETRY_CONFIG = {
    "max_attempts": 3,
    "wait_strategy": "exponential_jitter",
    "wait_min": 2,
    "wait_max": 60,
    "stop_on": [ValueError, ConfigurationError, NotFoundError],
    "retry_log_level": "warning",
}
MAX_CONCURRENT_SECTIONS = 4


class ExtractConceptsInput(CommandInput):
    source_id: str


class ExtractConceptsOutput(CommandOutput):
    success: bool
    source_id: str
    concepts: int
    relations: int
    processing_time: float
    error_message: Optional[str] = None


async def _extract(
    model, title: str, section: Section, text: str
) -> Optional[ConceptExtraction]:
    """The section's concepts, or None when the model's reply could not be read."""
    parser: PydanticOutputParser[ConceptExtraction] = PydanticOutputParser(
        pydantic_object=ConceptExtraction
    )
    prompt = Prompter(prompt_template="sources/concepts", parser=parser).render(  # type: ignore[arg-type]
        data={
            "title": title,
            "section_title": section.title,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "text": text,
            "max_concepts": MAX_CONCEPTS_PER_SECTION,
            "max_relations": MAX_RELATIONS_PER_SECTION,
        }
    )
    error: Exception = ValueError("no attempt")
    for _ in range(2):  # one retry: replies vary
        try:
            reply = await model.ainvoke(prompt)
            raw = clean_thinking_content(extract_text_content(reply.content)).strip()
            return parse_extraction(raw)
        except Exception as e:
            error = e
    # One unreadable section must not lose the others (the stage is recorded
    # as failed, so it is retried).
    logger.warning(f"Concept extraction failed for section {section.index}: {error}")
    return None


def _page_range(section: Section, page: Optional[int]) -> tuple[int, int]:
    if page is not None and section.page_start <= page <= section.page_end:
        return page, page
    return section.page_start, section.page_end


def _keys(name: str) -> List[str]:
    """Normalized names of a concept: display name first, then aliases."""
    return [k for k in dict.fromkeys(concept_key(n) for n in concept_names(name)) if k]


async def _resolve_concepts(raw_names: List[str]) -> Dict[str, str]:
    """Concept record id for every normalized name of the extracted concepts.

    Names resolve through concept_alias records, so "ReLU", "Rectified linear
    unit" and "Rectified linear unit (ReLU)" land on one concept wherever each
    was seen first. New concepts are created (and embedded); every name gets an
    alias record. Ids derive from names, so lookups are direct record fetches."""
    groups = [(concept_names(n)[0], _keys(n)) for n in raw_names]
    groups = [(display, keys) for display, keys in groups if keys]
    if not groups:
        return {}
    all_keys = list(dict.fromkeys(k for _, keys in groups for k in keys))
    rows = await repo_query(
        "SELECT key, concept FROM $records",
        {"records": [ensure_record_id(alias_id(k)) for k in all_keys]},
    )
    resolved: Dict[str, str] = {r["key"]: str(r["concept"]) for r in rows}
    new_aliases: Dict[str, str] = {}
    new_concepts: Dict[str, tuple[str, str]] = {}
    for display, keys in groups:
        concept = next((resolved[k] for k in keys if k in resolved), None)
        if concept is None:
            concept = concept_id(keys[0])
            new_concepts.setdefault(concept, (display, keys[0]))
        for key in keys:
            if key not in resolved:
                resolved[key] = concept
                new_aliases[key] = concept

    if new_concepts:
        existing = await repo_query(
            "SELECT VALUE id FROM $records",
            {"records": [ensure_record_id(c) for c in new_concepts]},
        )
        have = {str(i) for i in existing}
        create = [c for c in new_concepts if c not in have]
        vectors: List[Optional[List[float]]] = [None] * len(create)
        if create:
            try:
                vectors = list(
                    await generate_embeddings([new_concepts[c][0] for c in create])
                )
            except Exception as e:  # lookup by name still works without vectors
                logger.warning(f"Concept embeddings failed: {e}")
        for concept, vector in zip(create, vectors):
            display, key = new_concepts[concept]
            await repo_query(
                "UPSERT $id CONTENT {name: $name, key: $key, embedding: $embedding}",
                {
                    "id": ensure_record_id(concept),
                    "name": display,
                    "key": key,
                    "embedding": vector,
                },
            )
    for key, concept in new_aliases.items():
        await repo_query(
            "UPSERT $id CONTENT {concept: $concept, key: $key}",
            {
                "id": ensure_record_id(alias_id(key)),
                "concept": ensure_record_id(concept),
                "key": key,
            },
        )
    return resolved


@command("extract_concepts", app="open_notebook", retry=CONCEPT_RETRY_CONFIG)
async def extract_concepts_command(
    input_data: ExtractConceptsInput,
) -> ExtractConceptsOutput:
    async with tracked(input_data.source_id, "concepts") as run:
        return await _extract_concepts(input_data, run)


async def _extract_concepts(
    input_data: ExtractConceptsInput, run: StageRun
) -> ExtractConceptsOutput:
    start = time.time()

    def result(concepts: int = 0, relations: int = 0) -> ExtractConceptsOutput:
        return ExtractConceptsOutput(
            success=True,
            source_id=input_data.source_id,
            concepts=concepts,
            relations=relations,
            processing_time=time.time() - start,
        )

    settings = await AgentSettings.load()
    if not settings.knowledge_graph:
        run.skip("concept graph is off")
        return result()
    record = ensure_record_id(input_data.source_id)
    section_rows = await repo_query(
        "SELECT index, title, page_start, page_end FROM source_section WHERE source = $s ORDER BY index",
        {"s": record},
    )
    if not section_rows:
        run.skip("no outline sections")
        return result()
    page_rows = await repo_query(
        "SELECT page, text, caption FROM source_page WHERE source = $s ORDER BY page",
        {"s": record},
    )
    groups = group_builds(
        [
            PdfPage(
                r["page"],
                "\n".join(p for p in (r.get("text"), r.get("caption")) if p),
            )
            for r in page_rows
        ]
    )
    source = await Source.get(input_data.source_id)
    title = (source.metadata or {}).get("title") or source.title or "Untitled"
    sections = [Section(**r) for r in section_rows]

    model = limit_reasoning(
        await provision_langchain_model(
            "", None, "tools", max_tokens=4096, structured=dict(type="json")
        )
    )
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SECTIONS)

    async def one(section: Section) -> Optional[ConceptExtraction]:
        text = section_text(groups, section)
        if not text.strip():
            return ConceptExtraction()
        async with semaphore:
            return await _extract(model, title, section, text)

    results = await asyncio.gather(*(one(s) for s in sections))
    failed = [s.index for s, r in zip(sections, results) if r is None]
    extractions = [r or ConceptExtraction() for r in results]

    resolved = await _resolve_concepts(
        [
            c.name
            for extraction in extractions
            for c in extraction.concepts[:MAX_CONCEPTS_PER_SECTION]
        ]
    )

    def concept_of(name: str) -> Optional[str]:
        return next((resolved[k] for k in _keys(name) if k in resolved), None)

    mentions: List[dict] = []
    relations: List[dict] = []
    for section, extraction in zip(sections, extractions):
        seen = set()
        for c in extraction.concepts[:MAX_CONCEPTS_PER_SECTION]:
            concept = concept_of(c.name)
            if concept is None or concept in seen:
                continue
            seen.add(concept)
            first, last = _page_range(section, c.page)
            mentions.append(
                {
                    "concept": ensure_record_id(concept),
                    "source": record,
                    "section": section.index,
                    "page_start": first,
                    "page_end": last,
                    "context": c.context.strip()[:300] or None,
                }
            )
        for r in extraction.relations[:MAX_RELATIONS_PER_SECTION]:
            a, b = concept_of(r.source), concept_of(r.target)
            if a is None or b is None or a == b or not r.relation.strip():
                continue
            first, last = _page_range(section, r.page)
            relations.append(
                {
                    "from_concept": ensure_record_id(a),
                    "to_concept": ensure_record_id(b),
                    "relation": r.relation.strip()[:60],
                    "source": record,
                    "section": section.index,
                    "page_start": first,
                    "page_end": last,
                }
            )

    await repo_query("DELETE concept_mention WHERE source = $s", {"s": record})
    await repo_query("DELETE concept_relation WHERE source = $s", {"s": record})
    if mentions:
        await repo_insert("concept_mention", mentions)
    if relations:
        await repo_insert("concept_relation", relations)
    concepts = len({str(m["concept"]) for m in mentions})
    run.detail = {"concepts": concepts, "relations": len(relations)}
    if failed:
        run.detail["failed_sections"] = failed
        run.partly_failed(
            f"Concept extraction failed for {len(failed)} of {len(sections)} sections"
        )
    logger.info(
        f"Concept graph for {input_data.source_id}: {len(mentions)} mentions of "
        f"{concepts} concepts, {len(relations)} relations"
    )
    return result(concepts, len(relations))
