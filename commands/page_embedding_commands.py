"""Multimodal embeddings of rendered PDF pages, for visual search.

Each page is rendered and embedded with the page-embedding model
(AgentSettings.page_embedding_model, an OpenRouter multimodal embedding
model), so the agent can find diagrams, charts and slide layouts by
description or by similarity to another page. An animation build is embedded
once, from its last (most complete) page, and the vector is stored on every
page of the build.

Runs after document analysis; does nothing when the setting is off or the
source has no original file.
"""

import asyncio
import base64
import time
from typing import Dict, List, Optional

from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command

from open_notebook.ai.openrouter import embed_multimodal, image_input
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.agent_settings import AgentSettings
from open_notebook.domain.ingestion import StageRun, tracked
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import ConfigurationError, NotFoundError
from open_notebook.utils.pdf_pages import PdfPage, group_builds, render_page_png

PAGE_EMBED_RETRY_CONFIG = {
    "max_attempts": 3,
    "wait_strategy": "exponential_jitter",
    "wait_min": 2,
    "wait_max": 60,
    "stop_on": [ValueError, ConfigurationError, NotFoundError],
    "retry_log_level": "warning",
}
BATCH_SIZE = 6
PAGE_IMAGE_SIDE = 1024


class EmbedPagesInput(CommandInput):
    source_id: str
    force: bool = False


class EmbedPagesOutput(CommandOutput):
    success: bool
    source_id: str
    pages_embedded: int
    processing_time: float
    error_message: Optional[str] = None


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


@command("embed_pages", app="open_notebook", retry=PAGE_EMBED_RETRY_CONFIG)
async def embed_pages_command(input_data: EmbedPagesInput) -> EmbedPagesOutput:
    async with tracked(input_data.source_id, "page_images") as run:
        return await _embed_pages(input_data, run)


async def _embed_pages(input_data: EmbedPagesInput, run: StageRun) -> EmbedPagesOutput:
    start = time.time()

    def done(count: int = 0) -> EmbedPagesOutput:
        return EmbedPagesOutput(
            success=True,
            source_id=input_data.source_id,
            pages_embedded=count,
            processing_time=time.time() - start,
        )

    settings = await AgentSettings.load()
    model = (settings.page_embedding_model or "").strip()
    if not model:
        run.skip("page image search is off")
        return done()
    source = await Source.get(input_data.source_id)
    path = source.asset.file_path if source and source.asset else None
    if not path:
        run.skip("no original file")
        return done()

    record = ensure_record_id(input_data.source_id)
    rows = await repo_query(
        "SELECT page, text, image_embedding != NONE AS embedded FROM source_page WHERE source = $s ORDER BY page",
        {"s": record},
    )
    embedded: Dict[int, bool] = {r["page"]: bool(r.get("embedded")) for r in rows}
    groups = group_builds([PdfPage(r["page"], r.get("text") or "") for r in rows])
    todo = [
        g
        for g in groups
        if input_data.force
        or not all(embedded.get(p) for p in range(g.start, g.end + 1))
    ]

    count = 0
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i : i + BATCH_SIZE]
        images: List[str] = []
        for group in batch:  # rendering holds the PDFium lock; one at a time
            png = await asyncio.to_thread(
                render_page_png, path, group.end, PAGE_IMAGE_SIDE
            )
            images.append(_data_url(png))
        vectors = await embed_multimodal(model, [image_input(u) for u in images])
        for group, vector in zip(batch, vectors):
            await repo_query(
                "UPDATE source_page SET image_embedding = $v WHERE source = $s AND page >= $a AND page <= $b",
                {"v": vector, "s": record, "a": group.start, "b": group.end},
            )
            count += group.end - group.start + 1
    run.detail = {"pages": count, "renders": len(todo)}
    logger.info(
        f"Embedded {count} page images of {input_data.source_id} ({len(todo)} renders, {model})"
    )
    return done(count)
