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
import time
from typing import Optional

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command, submit_command

from open_notebook.ai.provision import limit_reasoning, provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import ConfigurationError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.pdf_pages import (
    PdfPage,
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
NO_VISUAL_CONTENT = "NO_VISUAL_CONTENT"


class CaptionPagesInput(CommandInput):
    source_id: str
    embed: bool = True


class CaptionPagesOutput(CommandOutput):
    success: bool
    source_id: str
    pages_captioned: int
    processing_time: float
    error_message: Optional[str] = None


async def _caption_page(model, path: str, title: str, page: PdfPage) -> Optional[str]:
    png = await asyncio.to_thread(render_page_png, path, page.number)
    prompt = Prompter(prompt_template="sources/page_caption").render(
        data={"title": title, "page": page.number, "text": page.text}
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


@command("caption_pages", app="open_notebook", retry=CAPTION_RETRY_CONFIG)
async def caption_pages_command(input_data: CaptionPagesInput) -> CaptionPagesOutput:
    """Caption the visual pages of a PDF source, then (optionally) embed it."""
    start = time.time()
    source = await Source.get(input_data.source_id)
    path = source.asset.file_path if source and source.asset else None
    record = ensure_record_id(input_data.source_id)

    rows = await repo_query(
        "SELECT page, text, image_ratio, caption FROM source_page WHERE source = $source ORDER BY page",
        {"source": record},
    )
    pages = [
        PdfPage(r["page"], r.get("text") or "", image_ratio=r.get("image_ratio") or 0.0)
        for r in rows
    ]
    already = {r["page"] for r in rows if r.get("caption")}
    targets = (
        [n for n in pages_needing_captions(pages) if n not in already] if path else []
    )

    captioned = 0
    if targets:
        model = limit_reasoning(
            await provision_langchain_model("", None, "transformation", max_tokens=2048)
        )
        by_number = {p.number: p for p in pages}
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)
        title = (source.title if source else None) or "Untitled"

        async def run(number: int) -> bool:
            async with semaphore:
                try:
                    caption = await _caption_page(
                        model, str(path), title, by_number[number]
                    )
                except Exception as e:
                    # One unreadable page or refused image shouldn't lose the others.
                    logger.warning(
                        f"Caption failed for {input_data.source_id} p{number}: {e}"
                    )
                    return False
            if caption:
                await repo_query(
                    "UPDATE source_page SET caption = $caption WHERE source = $source AND page = $page",
                    {"caption": caption, "source": record, "page": number},
                )
            return bool(caption)

        captioned = sum(await asyncio.gather(*(run(n) for n in targets)))
        logger.info(
            f"Captioned {captioned}/{len(targets)} visual pages of {input_data.source_id}"
        )

    if input_data.embed and source is not None:
        await source.vectorize()
    # Outline, metadata and summaries read the captions, so they run after.
    submit_command(
        "open_notebook", "analyze_source", {"source_id": input_data.source_id}
    )
    return CaptionPagesOutput(
        success=True,
        source_id=input_data.source_id,
        pages_captioned=captioned,
        processing_time=time.time() - start,
    )
