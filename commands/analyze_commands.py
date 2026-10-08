"""Document analysis for paged sources: metadata, outline, section and document summaries.

Runs after a paged source's pages (and captions) exist. Three steps, all small
model calls, so a long deck is never sent in one prompt:

1. Outline: from the page index, the model returns document metadata (type,
   course, sequence number, topics...) and topic sections with page ranges.
2. One summary per section, from that section's page text and captions.
3. A document summary built from the section summaries.

Writes source.metadata, source_section rows (summaries embedded for
section-level search) and a "Document Summary" insight.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from ai_prompter import Prompter
from langchain_core.output_parsers.pydantic import PydanticOutputParser
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command, submit_command

from open_notebook.ai.provision import limit_reasoning, provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_insert, repo_query
from open_notebook.domain.ingestion import StageRun, stage_queued, tracked
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import ConfigurationError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.embedding import generate_embeddings
from open_notebook.utils.pdf_pages import PDFIUM_LOCK, PdfPage, group_builds
from open_notebook.utils.sections import (
    DocumentMetadata,
    OutlinePlan,
    Section,
    normalize_sections,
    page_index,
    section_text,
)
from open_notebook.utils.text_utils import extract_text_content

ANALYZE_RETRY_CONFIG = {
    "max_attempts": 3,
    "wait_strategy": "exponential_jitter",
    "wait_min": 2,
    "wait_max": 60,
    "stop_on": [ValueError, ConfigurationError],
    "retry_log_level": "warning",
}
DOCUMENT_SUMMARY_INSIGHT = "Document Summary"
MAX_CONCURRENT_SECTIONS = 4


class AnalyzeSourceInput(CommandInput):
    source_id: str


class AnalyzeSourceOutput(CommandOutput):
    success: bool
    source_id: str
    sections: int
    processing_time: float
    error_message: Optional[str] = None


async def _complete(prompt: str, max_tokens: int, json_mode: bool = False) -> str:
    kwargs: Dict[str, Any] = {"max_tokens": max_tokens}
    if json_mode:
        kwargs["structured"] = dict(type="json")
    model = limit_reasoning(
        await provision_langchain_model(prompt, None, "transformation", **kwargs)
    )
    reply = await model.ainvoke(prompt)
    return clean_thinking_content(extract_text_content(reply.content)).strip()


def _pdf_title(path: Optional[str]) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    try:
        import pypdfium2 as pdfium

        with PDFIUM_LOCK:
            pdf = pdfium.PdfDocument(path)
            try:
                return (pdf.get_metadata_dict().get("Title") or "").strip() or None
            finally:
                pdf.close()
    except Exception:
        return None


async def plan_outline(
    source: Source, pages: List[PdfPage]
) -> tuple[DocumentMetadata, List[Section]]:
    groups = group_builds(pages)
    page_count = max(p.number for p in pages)
    path = source.asset.file_path if source.asset else None
    file_name = os.path.basename(path) if path else (source.title or "")
    parser: PydanticOutputParser[OutlinePlan] = PydanticOutputParser(
        pydantic_object=OutlinePlan
    )
    prompt = Prompter(
        prompt_template="sources/outline",
        parser=parser,  # type: ignore[arg-type]
    ).render(
        data={
            "file_name": file_name,
            "pdf_title": _pdf_title(path),
            "page_count": page_count,
            "first_page": pages[0].text[:1500],
            "page_index": page_index(groups),
        }
    )
    try:
        plan = parser.parse(await _complete(prompt, max_tokens=4096, json_mode=True))
        return plan.metadata, normalize_sections(plan.sections, groups, page_count)
    except ConfigurationError:
        raise
    except Exception as e:
        # A model that can't produce the JSON still gets fixed-size sections.
        logger.warning(
            f"Outline parsing failed for {source.id}, using page windows: {e}"
        )
        title = os.path.splitext(file_name)[0] or "Untitled"
        return DocumentMetadata(doc_type="other", title=title), normalize_sections(
            [], groups, page_count
        )


async def summarize_sections(
    source_title: str, pages: List[PdfPage], sections: List[Section]
) -> List[str]:
    groups = group_builds(pages)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SECTIONS)

    async def one(section: Section) -> str:
        text = section_text(groups, section)
        if not text.strip():
            return "(This section has no extractable text.)"
        prompt = Prompter(prompt_template="sources/section_summary").render(
            data={
                "title": source_title,
                "section_title": section.title,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "text": text,
            }
        )
        async with semaphore:
            summary = await _complete(prompt, max_tokens=1500)
            if not summary:
                # Reasoning models can spend the whole budget thinking and
                # return nothing; give it room once before falling back.
                summary = await _complete(prompt, max_tokens=4000)
        return summary or _extract_fallback(section, text)

    return list(await asyncio.gather(*(one(s) for s in sections)))


def _extract_fallback(section: Section, text: str) -> str:
    """A plain extract when the model returns no summary: better than an empty one."""
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("[p")
    ]
    return (
        f"{section.title} (pp. {section.page_start}-{section.page_end}): "
        + " ".join(lines)[:600]
    )


@command("analyze_source", app="open_notebook", retry=ANALYZE_RETRY_CONFIG)
async def analyze_source_command(input_data: AnalyzeSourceInput) -> AnalyzeSourceOutput:
    async with tracked(input_data.source_id, "analyze") as run:
        return await _analyze_source(input_data, run)


async def _analyze_source(
    input_data: AnalyzeSourceInput, run: StageRun
) -> AnalyzeSourceOutput:
    start = time.time()
    source = await Source.get(input_data.source_id)
    record = ensure_record_id(input_data.source_id)
    rows = await repo_query(
        "SELECT page, text, caption FROM source_page WHERE source = $source ORDER BY page",
        {"source": record},
    )
    pages = [
        PdfPage(
            r["page"],
            "\n".join(part for part in (r.get("text"), r.get("caption")) if part),
        )
        for r in rows
    ]
    if not pages or not any(p.text for p in pages):
        run.skip("no page text")
        return AnalyzeSourceOutput(
            success=True,
            source_id=input_data.source_id,
            sections=0,
            processing_time=time.time() - start,
        )

    metadata, sections = await plan_outline(source, pages)
    title = metadata.title or source.title or "Untitled"
    summaries = await summarize_sections(title, pages, sections)
    overview = await _complete(
        Prompter(prompt_template="sources/document_summary").render(
            data={
                "title": title,
                "page_count": max(p.number for p in pages),
                "sections": [
                    {**s.model_dump(), "summary": summary}
                    for s, summary in zip(sections, summaries)
                ],
            }
        ),
        max_tokens=2500,
    ) or "\n\n".join(
        f"{s.title} (pp. {s.page_start}-{s.page_end}): {summary}"
        for s, summary in zip(sections, summaries)
    )
    embeddings = await generate_embeddings(
        [f"{s.title}\n{summary}" for s, summary in zip(sections, summaries)]
    )

    await repo_query("DELETE source_section WHERE source = $source", {"source": record})
    await repo_insert(
        "source_section",
        [
            {
                "source": record,
                "index": s.index,
                "title": s.title,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "summary": summary,
                "embedding": embedding,
            }
            for s, summary, embedding in zip(sections, summaries, embeddings)
        ],
    )
    await repo_query(
        "UPDATE $source SET metadata = $metadata",
        {
            "source": record,
            "metadata": {
                **metadata.model_dump(),
                "page_count": max(p.number for p in pages),
            },
        },
    )
    await repo_query(
        "DELETE source_insight WHERE source = $source AND insight_type = $type",
        {"source": record, "type": DOCUMENT_SUMMARY_INSIGHT},
    )
    await source.add_insight(DOCUMENT_SUMMARY_INSIGHT, overview)
    logger.info(
        f"Analyzed {input_data.source_id}: {len(sections)} sections, metadata {metadata.model_dump()}"
    )
    run.detail = {"sections": len(sections)}
    # Visual search over rendered pages (skipped when the setting is off).
    await stage_queued(input_data.source_id, "page_images")
    submit_command("open_notebook", "embed_pages", {"source_id": input_data.source_id})
    # Concept graph from the new sections (skipped when the setting is off).
    await stage_queued(input_data.source_id, "concepts")
    submit_command(
        "open_notebook", "extract_concepts", {"source_id": input_data.source_id}
    )
    return AnalyzeSourceOutput(
        success=True,
        source_id=input_data.source_id,
        sections=len(sections),
        processing_time=time.time() - start,
    )
