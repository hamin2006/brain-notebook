"""Office documents are converted to PDF so they get the page pipeline."""

import stat
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.graphs.source import SourceState, content_process
from open_notebook.utils.office_convert import (
    convert_to_pdf,
    is_office_document,
    office_converter,
)
from open_notebook.utils.pdf_pages import PdfPage


def _fake_soffice(tmp_path, writes_pdf=True):
    """A stand-in for soffice: writes <stem>.pdf into --outdir, like the real one."""
    script = tmp_path / "soffice"
    body = (
        'out=""; src=""\n'
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in --outdir) out="$2"; shift 2;; -*) shift;; pdf) shift;; *) src="$1"; shift;; esac\n'
        "done\n"
    )
    if writes_pdf:
        body += 'name=$(basename "$src"); printf "%%PDF-1.4" > "$out/${name%.*}.pdf"\n'
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_office_formats_are_recognised():
    assert is_office_document("/x/Lecture 3.PPTX")
    assert is_office_document("notes.docx")
    assert not is_office_document("deck.pdf")
    assert not is_office_document("image.png")


def test_conversion_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_OFFICE_TO_PDF", "off")
    assert office_converter() is None
    assert convert_to_pdf("/x/deck.pptx") is None


def test_converts_beside_the_original_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_OFFICE_TO_PDF", _fake_soffice(tmp_path))
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"pptx")
    (tmp_path / "deck.pdf").write_bytes(b"an unrelated upload")

    pdf = convert_to_pdf(str(deck))

    assert pdf == str(tmp_path / "deck (1).pdf")
    assert (tmp_path / "deck (1).pdf").read_bytes().startswith(b"%PDF")
    assert (tmp_path / "deck.pdf").read_bytes() == b"an unrelated upload"
    assert deck.exists()  # the caller decides what happens to the original


def test_a_failed_conversion_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OPEN_NOTEBOOK_OFFICE_TO_PDF", _fake_soffice(tmp_path, writes_pdf=False)
    )
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"pptx")
    assert convert_to_pdf(str(deck)) is None


@pytest.mark.asyncio
async def test_converted_slides_go_through_page_extraction(tmp_path):
    deck = tmp_path / "Lecture 3.pptx"
    deck.write_bytes(b"pptx")
    pdf = tmp_path / "Lecture 3.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    pages = [PdfPage(1, "Backpropagation " * 20)]
    state = {"content_state": {"file_path": str(deck)}}
    with (
        patch("open_notebook.graphs.source.convert_to_pdf", return_value=str(pdf)),
        patch("open_notebook.graphs.source.extract_pdf_pages", return_value=pages),
        patch("open_notebook.graphs.source.extract_content", new=AsyncMock()) as cc,
    ):
        result = await content_process(cast(SourceState, state))
    cc.assert_not_awaited()
    assert result["pages"] == pages
    assert result["content_state"]["file_path"] == str(pdf)  # the source's file now
    assert not deck.exists()


@pytest.mark.asyncio
async def test_without_a_converter_slides_are_extracted_as_text(tmp_path):
    deck = tmp_path / "Lecture 3.pptx"
    deck.write_bytes(b"pptx")
    extraction = AsyncMock(
        return_value=type("E", (), {"content": "text", "title": "t"})()
    )
    state = {"content_state": {"file_path": str(deck)}}
    with (
        patch("open_notebook.graphs.source.convert_to_pdf", return_value=None),
        patch("open_notebook.graphs.source.extract_content", new=extraction),
    ):
        result = await content_process(cast(SourceState, state))
    extraction.assert_awaited_once()
    assert result["pages"] == []
    assert result["content_state"]["file_path"] == str(deck)
