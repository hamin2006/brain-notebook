"""Page-aware PDF text extraction.

content-core returns a PDF as one string with no page boundaries, so chunks
can't be tied back to pages. This module extracts each page separately with
pdfplumber (the library content-core itself uses) and cleans what slide decks
put in the text layer:

- LaTeXiT equations. Keynote/LaTeXiT stores each equation's source as invisible
  text: `<latexit sha1_base64="...">BASE64</latexit>`, every character printed
  four times, sometimes right-to-left. The base64 is a Qt-compressed archive
  holding the LaTeX source. On the AI 360 decks this junk was ~70% of the
  extracted text; decoded, it becomes `$...$` LaTeX.
- Residual runs of repeated characters (corrupted copies of the above) and NUL
  glyph placeholders.

It also groups animation builds (consecutive slides where each adds a little to
the previous one) so a chunker can embed the build once with its page range.
"""

import base64
import plistlib
import re
import zlib
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, List, Optional, Tuple

from loguru import logger

# Runs of characters each printed 4 times, single spaces allowed between them.
_QUAD_RUN = re.compile(r"(?:(\S)\1{3}\s?){8,}")
_QUAD_CHAR = re.compile(r"(\S)\1{3}")
# Corrupted leftovers: long space-free tokens made mostly of repeated characters.
_LONG_TOKEN = re.compile(r"\S{30,}")
_REPEAT = re.compile(r"(\S)\1{2,}")
_LATEXIT_BLOCK = re.compile(r'<latexit sha1_base64="[^"]*">(.*?)</latexit>', re.S)

BUILD_COVERAGE = 0.9  # share of the previous page a build step must contain


@dataclass
class PdfPage:
    number: int  # 1-based
    text: str
    equations: List[str] = field(default_factory=list)
    image_ratio: float = 0.0  # share of the page area covered by images


@dataclass
class PageGroup:
    """Consecutive pages that form one unit (an animation build, or a single page)."""

    start: int
    end: int
    text: str


def latexit_source(body: str) -> Optional[str]:
    """Decode a LaTeXiT payload to its LaTeX source.

    The payload is base64 of Qt's qCompress format (4-byte length + zlib) around
    a binary plist whose `source` key holds the equation.
    """
    compact = re.sub(r"\s", "", body)
    try:
        raw = base64.b64decode(compact + "=" * (-len(compact) % 4))
        meta = plistlib.loads(zlib.decompress(raw[4:]))
    except (ValueError, zlib.error, plistlib.InvalidFileException):
        return None
    source = meta.get("source") if isinstance(meta, dict) else None
    return source.strip() if isinstance(source, str) and source.strip() else None


def _is_residual_junk(token: str) -> bool:
    repeated = sum(len(m.group(0)) for m in _REPEAT.finditer(token))
    return repeated >= len(token) / 2


def clean_page_text(text: str) -> Tuple[str, List[str]]:
    """Replace LaTeXiT blocks with `$latex$`, drop residual junk. Returns (text, equations)."""
    equations: List[str] = []

    def replace_run(match: re.Match) -> str:
        run = _QUAD_CHAR.sub(r"\1", match.group(0))
        if "tixetal" in run and "latexit" not in run:  # extracted right-to-left
            run = run[::-1]
        decoded = [
            src for src in map(latexit_source, _LATEXIT_BLOCK.findall(run)) if src
        ]
        equations.extend(decoded)
        return " " + " ".join(f"${src}$" for src in decoded) + " " if decoded else " "

    text = _QUAD_RUN.sub(replace_run, text)
    text = _LONG_TOKEN.sub(
        lambda m: " " if _is_residual_junk(m.group(0)) else m.group(0), text
    )
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip(), equations


def _image_ratio(page) -> float:
    area = float(page.width * page.height) or 1.0
    covered = 0.0
    for img in page.images:
        x0, x1 = max(img["x0"], 0), min(img["x1"], page.width)
        top, bottom = max(img["top"], 0), min(img["bottom"], page.height)
        if x1 > x0 and bottom > top:
            covered += (x1 - x0) * (bottom - top)
    return min(covered / area, 1.0)


def extract_pdf_pages(path: str) -> List[PdfPage]:
    """Extract cleaned text for every page of a PDF (synchronous; run in a thread)."""
    import pdfplumber

    pages: List[PdfPage] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            try:
                raw = page.extract_text() or ""
                ratio = _image_ratio(page)
            except Exception as e:  # one malformed page shouldn't lose the document
                logger.warning(f"Page {number} of {path} could not be read: {e}")
                raw, ratio = "", 0.0
            text, equations = clean_page_text(raw)
            pages.append(PdfPage(number, text, equations, ratio))
            page.flush_cache()  # pdfplumber keeps parsed layout objects per page
    return pages


def _is_build_step(previous: str, current: str) -> bool:
    """True when `current` contains nearly all of `previous` (an animation build step)."""
    if not previous.strip() or len(current) < len(previous):
        return False
    matcher = SequenceMatcher(None, previous, current, autojunk=False)
    if matcher.quick_ratio() * (
        len(previous) + len(current)
    ) / 2 < BUILD_COVERAGE * len(previous):
        return False  # cheap upper bound already rules it out
    covered = sum(block.size for block in matcher.get_matching_blocks())
    return covered >= BUILD_COVERAGE * len(previous)


def group_builds(pages: List[PdfPage]) -> List[PageGroup]:
    """Merge runs of animation-build pages; the last (most complete) page carries the text."""
    groups: List[PageGroup] = []
    for page in pages:
        if groups and _is_build_step(groups[-1].text, page.text):
            last = groups[-1]
            groups[-1] = PageGroup(
                last.start,
                page.number,
                page.text if len(page.text) >= len(last.text) else last.text,
            )
        else:
            groups.append(PageGroup(page.number, page.number, page.text))
    return groups


MIN_PAGE_TEXT_CHARS = 200


def has_page_text(pages: List[PdfPage]) -> bool:
    """True when the PDF has a usable text layer (scanned PDFs have none)."""
    return sum(len(page.text) for page in pages) >= MIN_PAGE_TEXT_CHARS


def pages_to_full_text(pages: List[PdfPage]) -> str:
    """Join page texts with page markers, skipping empty pages."""
    return "\n\n".join(
        f"--- Page {page.number} ---\n{page.text}" for page in pages if page.text
    )


@dataclass
class PageChunk:
    text: str
    page_start: int
    page_end: int


def page_chunks(
    title: str,
    pages: List[PdfPage],
    split: Callable[[str], List[str]],
    max_chars: int,
) -> List[PageChunk]:
    """Chunks for a paged source: one per page group, split only when too long.

    Each chunk starts with "<title> — p. N" (or "pp. N–M") so lexical and vector
    search see which document and pages it belongs to.
    """
    chunks: List[PageChunk] = []
    for group in group_builds(pages):
        if not group.text.strip():
            continue
        where = (
            f"p. {group.start}"
            if group.start == group.end
            else f"pp. {group.start}–{group.end}"
        )
        header = f"{title} — {where}\n"
        pieces = [group.text] if len(group.text) <= max_chars else split(group.text)
        chunks.extend(
            PageChunk(header + piece, group.start, group.end)
            for piece in pieces
            if piece.strip()
        )
    return chunks
