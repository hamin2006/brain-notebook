"""Vision captions for visual PDF pages."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from commands.page_commands import CaptionPagesInput, caption_pages_command
from open_notebook.domain.ingestion import STAGE_VERSIONS
from open_notebook.graphs.source import SourceState, save_source
from open_notebook.utils.pdf_pages import (
    PdfPage,
    pages_needing_captions,
    render_page_png,
)

SOURCE_ID = "source:deck"


def test_pages_needing_captions_picks_visual_groups_once():
    pages = [
        PdfPage(1, "Title", image_ratio=0.0),
        PdfPage(2, "Momentum", image_ratio=0.6),  # build start...
        PdfPage(3, "Momentum\n- gains speed", image_ratio=0.6),  # ...build end
        PdfPage(4, "", image_ratio=0.9),  # image-only slide
        PdfPage(5, "Text only slide", image_ratio=0.1),
    ]
    assert pages_needing_captions(pages) == [3, 4]


def test_render_page_png(tmp_path):
    path = tmp_path / "deck.pdf"
    Image.new("RGB", (800, 450), "white").save(path, "PDF")
    png = render_page_png(str(path), 1, max_side=400)
    assert png.startswith(b"\x89PNG")
    with pytest.raises(ValueError):
        render_page_png(str(path), 2)


def _fake_source(tmp_path):
    path = tmp_path / "deck.pdf"
    Image.new("RGB", (800, 450), "white").save(
        path, "PDF", save_all=True, append_images=[Image.new("RGB", (800, 450))] * 2
    )
    source = MagicMock(id=SOURCE_ID, title="Lecture 4", vectorize=AsyncMock())
    source.asset.file_path = str(path)
    return source


@pytest.mark.asyncio
async def test_caption_job_captions_visual_pages_and_embeds_once(tmp_path):
    source = _fake_source(tmp_path)
    rows = [
        {"page": 1, "text": "Adam", "image_ratio": 0.9, "caption": None},
        {"page": 2, "text": "Plain text slide", "image_ratio": 0.0, "caption": None},
        {"page": 3, "text": "", "image_ratio": 0.9, "caption": None},
    ]
    updates = []

    async def fake_query(query, params=None):
        if query.startswith("SELECT"):
            return rows
        updates.append(params)
        return []

    replies = {1: "Adam update rule: $m_k = ...$", 3: "NO_VISUAL_CONTENT"}

    async def fake_caption(model, path, title, page):
        return (
            None
            if replies[page.number] == "NO_VISUAL_CONTENT"
            else replies[page.number]
        )

    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch("commands.page_commands.repo_query", new=fake_query),
        patch("commands.page_commands.provision_langchain_model", new=AsyncMock()),
        patch("commands.page_commands._caption_page", new=fake_caption),
        patch("commands.page_commands.submit_command") as submit,
    ):
        result = await caption_pages_command(CaptionPagesInput(source_id=SOURCE_ID))

    assert result.pages_captioned == 1
    # Both visual pages are recorded as checked; only page 1 got a caption, and
    # page 3 isn't retried until the caption stage's version changes.
    assert [(u["page"], u["caption"]) for u in updates] == [
        (1, replies[1]),
        (3, None),
    ]
    assert {u["version"] for u in updates} == {STAGE_VERSIONS["caption"]}
    source.vectorize.assert_awaited_once()
    submit.assert_called_once_with(
        "open_notebook", "analyze_source", {"source_id": SOURCE_ID}
    )


@pytest.mark.asyncio
async def test_caption_job_survives_a_failing_page_and_retries_it(
    tmp_path, stage_writes
):
    source = _fake_source(tmp_path)
    rows = [
        {"page": 1, "text": "", "image_ratio": 0.9, "caption": None},
        {"page": 2, "text": "", "image_ratio": 0.9, "caption": None},
    ]
    refuse = {1}
    attempted: list = []

    async def fake_caption(model, path, title, page):
        attempted.append(page.number)
        if page.number in refuse:
            raise RuntimeError("image refused")
        return f"Diagram on page {page.number}"

    async def fake_query(query, params=None):
        if query.startswith("SELECT"):
            return rows
        row = next(r for r in rows if r["page"] == params["page"])
        row.update(caption=params["caption"], caption_version=params["version"])
        return []

    def run(**kwargs):
        return caption_pages_command(CaptionPagesInput(source_id=SOURCE_ID, **kwargs))

    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch("commands.page_commands.repo_query", new=fake_query),
        patch("commands.page_commands.provision_langchain_model", new=AsyncMock()),
        patch("commands.page_commands._caption_page", new=fake_caption),
        patch("commands.page_commands.submit_command") as submit,
    ):
        result = await run()
        # The job succeeds and the pipeline continues with what it has...
        assert result.success and result.pages_captioned == 1
        source.vectorize.assert_awaited_once()
        submit.assert_called_once()
        # ...but the stage is failed, naming the page, so it is retried.
        failed = [f for _, stage, f in stage_writes if stage == "caption"][-1]
        assert failed["status"] == "failed" and "pages 1)" in failed["error"]
        assert failed["detail"]["failed_pages"] == [1]

        # The retry (a restart with later stages done) captions only page 1.
        refuse.clear()
        attempted.clear()
        result = await run(reprocess=True)
        assert attempted == [1] and result.pages_captioned == 1
        assert [f for _, st, f in stage_writes if st == "caption"][-1][
            "status"
        ] == "done"
        assert source.vectorize.await_count == 2  # new caption: re-embed
        assert submit.call_count == 2  # and re-analyze


@pytest.mark.asyncio
async def test_caption_prompt_asks_for_latex_on_garbled_math_pages(tmp_path):
    """Caption output fixtures: what the model is asked, and how replies are read."""
    from commands.page_commands import _caption_page

    path = tmp_path / "deck.pdf"
    Image.new("RGB", (800, 450), "white").save(path, "PDF")
    model = MagicMock()

    async def caption(page: PdfPage, reply: str):
        model.ainvoke = AsyncMock(return_value=MagicMock(content=reply))
        result = await _caption_page(model, str(path), "Reduce", page)
        [message] = model.ainvoke.await_args.args[0]
        text, image = message.content
        assert image["image_url"]["url"].startswith("data:image/png;base64,")
        return result, text["text"]

    garbled = PdfPage(1, "T + −1 T +(P −1)T . w c c P", garbled=True)
    result, prompt = await caption(garbled, "$T_w + (N/P - 1) T_c$")
    assert "transcribe every equation on the page in LaTeX" in prompt
    assert "T + −1 T +(P −1)T" in prompt  # the extracted text goes along
    assert result == "$T_w + (N/P - 1) T_c$"

    plain = PdfPage(1, "Reduce tree", shapes=40)
    result, prompt = await caption(plain, "NO_VISUAL_CONTENT")
    assert "transcribe every equation" not in prompt
    assert result is None  # nothing visual: checked, no caption

    result, _ = await caption(plain, "<think>tree?</think>Binary reduce tree")
    assert result == "Binary reduce tree"


@pytest.mark.asyncio
async def test_save_source_queues_captions_instead_of_embedding_for_visual_pdfs():
    source = MagicMock(
        id=SOURCE_ID,
        title="Lecture 4",
        full_text="text",
        vectorize=AsyncMock(),
        save=AsyncMock(),
    )
    state = {
        "content_state": {"file_path": "/tmp/deck.pdf"},
        "extraction": MagicMock(content="--- Page 1 ---\nAdam", title="deck.pdf"),
        "source_id": SOURCE_ID,
        "embed": True,
        "pages": [PdfPage(1, "Adam", image_ratio=0.9)],
    }
    with (
        patch(
            "open_notebook.graphs.source.Source.get", new=AsyncMock(return_value=source)
        ),
        patch("open_notebook.graphs.source._store_pages", new=AsyncMock()) as store,
        patch("open_notebook.graphs.source.submit_command") as submit,
    ):
        await save_source(cast(SourceState, state))

    store.assert_awaited_once()
    submit.assert_called_once_with(
        "open_notebook", "caption_pages", {"source_id": SOURCE_ID, "embed": True}
    )
    source.vectorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_caption_bump_asks_only_pages_that_were_never_checked(tmp_path):
    from commands.page_commands import CAPTION_CHECKS_VALID_FROM

    source = _fake_source(tmp_path)
    rows = [
        # Checked under the last prompt change: nothing visual, not asked again.
        {"page": 1, "text": "", "image_ratio": 0.9, "caption_version": 2},
        # Its call failed under that version: never checked, asked now.
        {"page": 2, "text": "", "image_ratio": 0.9, "caption_version": 0},
        {"page": 3, "text": "", "image_ratio": 0.9, "caption": "Kept"},
    ]
    assert CAPTION_CHECKS_VALID_FROM <= 2 < STAGE_VERSIONS["caption"]
    caption = AsyncMock(return_value="Diagram")
    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch(
            "commands.page_commands.repo_query",
            new=AsyncMock(side_effect=lambda q, p=None: rows if q.startswith("SELECT") else []),
        ),
        patch("commands.page_commands.provision_langchain_model", new=AsyncMock()),
        patch("commands.page_commands._caption_page", new=caption),
        patch("commands.page_commands.submit_command"),
    ):  # fmt: skip
        await caption_pages_command(
            CaptionPagesInput(source_id=SOURCE_ID, reprocess=True)
        )
    assert [c.args[3].number for c in caption.await_args_list] == [2]
