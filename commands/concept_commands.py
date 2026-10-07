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
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import ConfigurationError, NotFoundError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.concepts import (
    MAX_CONCEPTS_PER_SECTION,
    MAX_RELATIONS_PER_SECTION,
    ConceptExtraction,
    concept_id,
    concept_key,
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


async def _extract(model, title: str, section: Section, text: str) -> ConceptExtraction:
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
    try:
        reply = await model.ainvoke(prompt)
        raw = clean_thinking_content(extract_text_content(reply.content)).strip()
        return parser.parse(raw)
    except Exception as e:  # one unreadable section must not lose the others
        logger.warning(f"Concept extraction failed for section {section.index}: {e}")
        return ConceptExtraction()


def _page_range(section: Section, page: Optional[int]) -> tuple[int, int]:
    if page is not None and section.page_start <= page <= section.page_end:
        return page, page
    return section.page_start, section.page_end


async def _concept_ids(names: Dict[str, str]) -> Dict[str, str]:
    """Record ids for concept keys, creating (and embedding) the new ones.

    A concept's id is derived from its key, so lookups are direct record fetches
    and two jobs adding the same concept write the same record."""
    if not names:
        return {}
    ids = {key: concept_id(key) for key in names}
    existing = await repo_query(
        "SELECT VALUE id FROM $records",
        {"records": [ensure_record_id(i) for i in ids.values()]},
    )
    have = {str(i) for i in existing}
    new = [k for k in names if ids[k] not in have]
    if new:
        vectors: List[Optional[List[float]]]
        try:
            vectors = list(await generate_embeddings([names[k] for k in new]))
        except Exception as e:  # lookup by name still works without vectors
            logger.warning(f"Concept embeddings failed: {e}")
            vectors = [None] * len(new)
        for key, vector in zip(new, vectors):
            await repo_query(
                "UPSERT $id CONTENT {name: $name, key: $key, embedding: $embedding}",
                {
                    "id": ensure_record_id(ids[key]),
                    "name": names[key],
                    "key": key,
                    "embedding": vector,
                },
            )
    return ids


@command("extract_concepts", app="open_notebook", retry=CONCEPT_RETRY_CONFIG)
async def extract_concepts_command(
    input_data: ExtractConceptsInput,
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
        return result()
    record = ensure_record_id(input_data.source_id)
    section_rows = await repo_query(
        "SELECT index, title, page_start, page_end FROM source_section WHERE source = $s ORDER BY index",
        {"s": record},
    )
    if not section_rows:
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

    async def one(section: Section) -> ConceptExtraction:
        text = section_text(groups, section)
        if not text.strip():
            return ConceptExtraction()
        async with semaphore:
            return await _extract(model, title, section, text)

    extractions = await asyncio.gather(*(one(s) for s in sections))

    names: Dict[str, str] = {}
    for extraction in extractions:
        for c in extraction.concepts[:MAX_CONCEPTS_PER_SECTION]:
            key = concept_key(c.name)
            if key:
                names.setdefault(key, c.name.strip())
    ids = await _concept_ids(names)

    mentions: List[dict] = []
    relations: List[dict] = []
    for section, extraction in zip(sections, extractions):
        seen = set()
        for c in extraction.concepts[:MAX_CONCEPTS_PER_SECTION]:
            key = concept_key(c.name)
            if key not in ids or key in seen:
                continue
            seen.add(key)
            first, last = _page_range(section, c.page)
            mentions.append(
                {
                    "concept": ensure_record_id(ids[key]),
                    "source": record,
                    "section": section.index,
                    "page_start": first,
                    "page_end": last,
                    "context": c.context.strip()[:300] or None,
                }
            )
        for r in extraction.relations[:MAX_RELATIONS_PER_SECTION]:
            a, b = concept_key(r.source), concept_key(r.target)
            if a not in ids or b not in ids or a == b or not r.relation.strip():
                continue
            first, last = _page_range(section, r.page)
            relations.append(
                {
                    "from_concept": ensure_record_id(ids[a]),
                    "to_concept": ensure_record_id(ids[b]),
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
    logger.info(
        f"Concept graph for {input_data.source_id}: {len(mentions)} mentions of "
        f"{len(ids)} concepts, {len(relations)} relations"
    )
    return result(len(ids), len(relations))
