"""Vision captions for PDF pages whose content is mostly visual.

Slide decks often carry their meaning in images (diagrams, screenshots of
equations, whole slides exported as pictures) that the text layer misses. This
job renders those pages and asks the vision-capable default model to describe
what the image adds; the caption is stored on source_page and embedded with the
page's text, so search and the agent can find it.

It runs after page extraction and embeds the source when done, so a source is
embedded once (two embed jobs for one source race: each starts by deleting the
other's chunks).
"""

import asyncio
import base64
import os
import time
from typing import Optional

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command, submit_command

from open_notebook.ai.provision import limit_reasoning, provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.ingestion import STAGE_VERSIONS, stage_queued, tracked
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import ConfigurationError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.pdf_pages import (
    PdfPage,
    extract_pdf_pages,
    pages_needing_captions,
    render_page_png,
)
from open_notebook.utils.text_utils import extract_text_content

CAPTION_RETRY_CONFIG = {
    "max_attempts": 3,
    "wait_strategy": "exponential_jitter",
    "wait_min": 2,
    "wait_max": 60,
    "stop_on": [ValueError, ConfigurationError],
    "retry_log_level": "warning",
}
MAX_CONCURRENT_PAGES = 4
# A page checked at this caption version or later is not asked again. Raise it
# to the new STAGE_VERSIONS["caption"] when a bump changes which pages get
# captioned or what the model is asked; leave it when a bump only re-runs the
# stage (caption 3 retries pages whose model call failed under version 2).
CAPTION_CHECKS_VALID_FROM = 2
NO_VISUAL_CONTENT = "NO_VISUAL_CONTENT"


class CaptionPagesInput(CommandInput):
    source_id: str
    embed: bool = True
    # Re-extract page text and signals from the PDF first (extract stage
    # upgrade), keeping captions and page-image embeddings.
    refresh: bool = False
    # Reprocessing an ingested source: re-embed and re-analyze only when the
    # pages changed. A first ingestion always continues the pipeline.
    reprocess: bool = False


class CaptionPagesOutput(CommandOutput):
    success: bool
    source_id: str
    pages_captioned: int
    processing_time: float
    error_message: Optional[str] = None


async def _caption_page(model, path: str, title: str, page: PdfPage) -> Optional[str]:
    png = await asyncio.to_thread(render_page_png, path, page.number)
    prompt = Prompter(prompt_template="sources/page_caption").render(
        data={
            "title": title,
            "page": page.number,
            "text": page.text,
            "garbled": page.garbled,
        }
    )
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(png).decode()
                },
            },
        ]
    )
    reply = await model.ainvoke([message])
    caption = clean_thinking_content(extract_text_content(reply.content)).strip()
    return None if not caption or caption == NO_VISUAL_CONTENT else caption


async def _refresh_pages(source_id: str, path: str) -> bool:
    """Re-extract page text and caption signals in place. True if any text changed."""
    record = ensure_record_id(source_id)
    rows = await repo_query(
        "SELECT page, text FROM source_page WHERE source = $s", {"s": record}
    )
    old = {r["page"]: r.get("text") or "" for r in rows}
    changed = False
    for page in await asyncio.to_thread(extract_pdf_pages, path):
        if page.number not in old:
            continue
        changed = changed or page.text != old[page.number]
        await repo_query(
            "UPDATE source_page SET text = $text, equations = $equations, "
            "image_ratio = $ratio, shapes = $shapes, garbled = $garbled "
            "WHERE source = $s AND page = $page",
            {
                "s": record,
                "page": page.number,
                "text": page.text,
                "equations": page.equations,
                "ratio": page.image_ratio,
                "shapes": page.shapes,
                "garbled": page.garbled,
            },
        )
    return changed


@command("caption_pages", app="open_notebook", retry=CAPTION_RETRY_CONFIG)
async def caption_pages_command(input_data: CaptionPagesInput) -> CaptionPagesOutput:
    """Caption the visual pages of a PDF source, then embed and analyze it.

    A page is checked once: pages the model found nothing visual on are asked
    again only when CAPTION_CHECKS_VALID_FROM is raised,
    and existing captions are kept. Pages whose model call failed leave the
    stage failed, so the next restart (worker start, Retry) captions them.
    """
    start = time.time()
    source_id = input_data.source_id
    source = await Source.get(source_id)
    path = source.asset.file_path if source and source.asset else None
    has_file = bool(path) and os.path.isfile(str(path))
    record = ensure_record_id(source_id)
    version = STAGE_VERSIONS["caption"]

    text_changed = False
    if input_data.refresh:
        async with tracked(source_id, "extract") as run:
            if has_file:
                text_changed = await _refresh_pages(source_id, str(path))
                run.detail = {"refreshed": True, "text_changed": text_changed}
            else:
                run.skip("original file missing; kept the stored pages")

    async with tracked(source_id, "caption") as run:
        rows = await repo_query(
            "SELECT page, text, image_ratio, shapes, garbled, caption, caption_version "
            "FROM source_page WHERE source = $source ORDER BY page",
            {"source": record},
        )
        pages = [
            PdfPage(
                r["page"],
                r.get("text") or "",
                image_ratio=r.get("image_ratio") or 0.0,
                shapes=r.get("shapes") or 0,
                garbled=bool(r.get("garbled")),
            )
            for r in rows
        ]
        checked = {
            r["page"]
            for r in rows
            if r.get("caption")
            or (r.get("caption_version") or 0) >= CAPTION_CHECKS_VALID_FROM
        }
        visual = pages_needing_captions(pages)
        targets = [n for n in visual if n not in checked] if has_file else []

        captioned = 0
        failed: list[int] = []
        if targets:
            model = limit_reasoning(
                await provision_langchain_model(
                    "", None, "transformation", max_tokens=2048
                )
            )
            by_number = {p.number: p for p in pages}
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)
            title = (source.title if source else None) or "Untitled"

            async def caption_one(number: int) -> Optional[bool]:
                """True: captioned, False: nothing visual to add, None: failed."""
                async with semaphore:
                    try:
                        caption = await _caption_page(
                            model, str(path), title, by_number[number]
                        )
                    except Exception as e:
                        # One unreadable page or refused image shouldn't lose
                        # the others; it stays unchecked, and the stage is
                        # recorded as failed so it is retried.
                        logger.warning(f"Caption failed for {source_id} p{number}: {e}")
                        return None
                await repo_query(
                    "UPDATE source_page SET caption = $caption, caption_version = $version "
                    "WHERE source = $source AND page = $page",
                    {
                        "caption": caption,
                        "version": version,
                        "source": record,
                        "page": number,
                    },
                )
                return bool(caption)

            outcomes = await asyncio.gather(*(caption_one(n) for n in targets))
            captioned = sum(1 for o in outcomes if o)
            failed = [n for n, o in zip(targets, outcomes) if o is None]
            logger.info(
                f"Captioned {captioned}/{len(targets)} visual pages of {source_id}"
            )
        run.detail = {
            "visual_pages": len(visual),
            "checked": len(targets),
            "captioned": captioned,
        }
        if failed:
            run.detail["failed_pages"] = failed
            run.partly_failed(
                f"{len(failed)} of {len(targets)} pages could not be captioned "
                f"(pages {', '.join(map(str, failed[:10]))}"
                f"{', …' if len(failed) > 10 else ''})"
            )
        if not has_file:
            run.skip("original file missing")

    if not input_data.reprocess or captioned or text_changed:
        if input_data.embed and source is not None:
            await source.vectorize()
        # Outline, metadata and summaries read the captions, so they run after.
        await stage_queued(source_id, "analyze")
        submit_command("open_notebook", "analyze_source", {"source_id": source_id})
    return CaptionPagesOutput(
        success=True,
        source_id=source_id,
        pages_captioned=captioned,
        processing_time=time.time() - start,
    )
