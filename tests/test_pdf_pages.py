"""Page-aware PDF extraction: LaTeXiT decoding, junk removal, build grouping."""

import base64
import plistlib
import struct
import zlib

from PIL import Image

from open_notebook.utils.pdf_pages import (
    PdfPage,
    clean_page_text,
    extract_pdf_pages,
    group_builds,
    has_page_text,
    latexit_source,
    page_chunks,
    pages_to_full_text,
)


def _latexit_block(source: str) -> str:
    """Build the text-layer form LaTeXiT writes: base64(qCompress(bplist))."""
    plist = plistlib.dumps(
        {"source": source, "preamble": "\\documentclass[10pt]{article}"},
        fmt=plistlib.FMT_BINARY,
    )
    payload = struct.pack(">I", len(plist)) + zlib.compress(plist)
    return (
        f'<latexit sha1_base64="abc123">{base64.b64encode(payload).decode()}</latexit>'
    )


def _quadruple(text: str) -> str:
    """Every non-space character printed four times, as in the PDF text layer."""
    return "".join(c if c.isspace() else c * 4 for c in text)


def test_latexit_source_decodes_the_equation():
    block = _latexit_block("\\theta^{t+1} = \\theta^t - \\eta \\nabla J")
    body = block.split('">', 1)[1].rsplit("</latexit>", 1)[0]
    assert latexit_source(body) == "\\theta^{t+1} = \\theta^t - \\eta \\nabla J"


def test_latexit_source_rejects_garbage():
    assert latexit_source("not base64 at all!!") is None
    assert latexit_source(base64.b64encode(b"\x00\x00\x00\x05hello").decode()) is None


def test_clean_page_text_replaces_quadrupled_blocks_with_latex():
    raw = (
        "Training by Gradient Descent\n"
        + _quadruple(_latexit_block("J(\\theta)"))
        + "\nlearning rate"
    )
    text, equations = clean_page_text(raw)
    assert equations == ["J(\\theta)"]
    assert "$J(\\theta)$" in text
    assert "Training by Gradient Descent" in text and "learning rate" in text
    assert "llll" not in text and "latexit" not in text


def test_clean_page_text_handles_right_to_left_blocks():
    raw = "Momentum " + _quadruple(_latexit_block("m_k = \\beta m_{k-1}"))[::-1]
    text, equations = clean_page_text(raw)
    assert equations == ["m_k = \\beta m_{k-1}"]
    assert "$m_k = \\beta m_{k-1}$" in text


def test_clean_page_text_drops_residual_junk_and_nul_glyphs():
    raw = "Slide title\n+bbbm555Yqqq5JJJYAAAIvvvTQQQ/5552wwwMAAA====\nbody\x00 text"
    text, equations = clean_page_text(raw)
    assert equations == []
    assert "bbbm" not in text and "====" not in text
    assert "\x00" not in text and "Slide title" in text and "body text" in text


def test_clean_page_text_keeps_normal_text():
    raw = (
        "Example: N = 7, F = 3\nstride 1 => (9-3)/1+1 = 7\n10000 iterations ...\n"
        "http://code.flickr.net/2014/10/20/introducing-flickr-park-or-bird/"
    )
    text, equations = clean_page_text(raw)
    assert equations == []
    assert "(9-3)/1+1 = 7" in text and "10000 iterations" in text
    assert "introducing-flickr-park-or-bird" in text


def test_group_builds_merges_animation_steps():
    pages = [
        PdfPage(1, "Title slide"),
        PdfPage(2, "Momentum\n- a heavy ball rolling down a hill"),
        PdfPage(3, "Momentum\n- a heavy ball rolling down a hill\n- gains speed"),
        PdfPage(
            4,
            "Momentum\n- a heavy ball rolling down a hill\n- gains speed\n- can help or hurt",
        ),
        PdfPage(5, "RMSProp\nper-dimension magnitude"),
    ]
    groups = group_builds(pages)
    assert [(g.start, g.end) for g in groups] == [(1, 1), (2, 4), (5, 5)]
    assert groups[1].text.endswith("can help or hurt")


def test_group_builds_keeps_empty_pages_separate():
    groups = group_builds([PdfPage(1, ""), PdfPage(2, ""), PdfPage(3, "Text")])
    assert [(g.start, g.end) for g in groups] == [(1, 1), (2, 2), (3, 3)]


def test_extract_pdf_pages_reports_image_only_pages(tmp_path):
    path = tmp_path / "slides.pdf"
    image = Image.new("RGB", (800, 450), "white")
    image.save(
        path, "PDF", save_all=True, append_images=[Image.new("RGB", (800, 450), "gray")]
    )
    pages = extract_pdf_pages(str(path))
    assert [p.number for p in pages] == [1, 2]
    assert all(p.text == "" for p in pages)
    assert all(p.image_ratio > 0.9 for p in pages)


def test_page_chunks_one_per_group_with_page_headers():
    pages = [
        PdfPage(1, "Optimization"),
        PdfPage(2, "Momentum\n- heavy ball"),
        PdfPage(3, "Momentum\n- heavy ball\n- gains speed"),
        PdfPage(4, ""),  # image-only page without a caption
        PdfPage(5, "Adam\ncombines momentum and RMSProp"),
    ]
    chunks = page_chunks("Lecture 4", pages, split=lambda t: [t], max_chars=1000)
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (2, 3), (5, 5)]
    assert chunks[1].text.startswith("Lecture 4 — pp. 2–3\n")
    assert chunks[2].text.startswith("Lecture 4 — p. 5\n")


def test_page_chunks_splits_only_oversized_groups():
    pages = [PdfPage(1, "short"), PdfPage(2, "x" * 50 + " " + "y" * 50)]
    chunks = page_chunks("Doc", pages, split=lambda t: t.split(" "), max_chars=60)
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (2, 2), (2, 2)]
    assert chunks[1].text.endswith("x" * 50) and chunks[2].text.endswith("y" * 50)


def test_pages_to_full_text_marks_pages_and_skips_empty_ones():
    text = pages_to_full_text([PdfPage(1, "a"), PdfPage(2, ""), PdfPage(3, "c")])
    assert text == "--- Page 1 ---\na\n\n--- Page 3 ---\nc"
    assert not has_page_text([PdfPage(1, "tiny")])
