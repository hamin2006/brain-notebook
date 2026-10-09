"""Previews of a source's original file, for the UI's file viewer.

`preview_kind` decides how the browser shows a file:

    pages     PDFs (and slides or documents LibreOffice converted): page images
    image     images: the page image endpoint (TIFF and BMP are converted)
    audio     audio the browser plays
    video     video the browser plays (MP4, MOV, WebM; AVI and WMV are download-only)
    text      plain text, shown as is
    markdown  Markdown, rendered
    html      HTML, shown in a sandboxed frame (no scripts)
    table     CSV, TSV and spreadsheets: the first rows of each sheet
    document  Word, PowerPoint and EPUB files that weren't converted: their text as HTML
    archive   ZIP and tar files: the list of entries
    none      nothing to show; the viewer offers the download

Everything is bounded (rows, characters, entries) so a large file can't make a
preview response large. Parsing libraries are imported only when needed.
"""

import csv
import html
import io
import mimetypes
import posixpath
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

MAX_TEXT_CHARS = 1_000_000
MAX_ROWS = 200
MAX_COLUMNS = 40
MAX_SHEETS = 12
MAX_ENTRIES = 500

_KINDS: Dict[str, Tuple[str, ...]] = {
    "pages": (".pdf",),
    "image": (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"),
    "audio": (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".opus"),
    "video": (".mp4", ".m4v", ".mov", ".webm", ".ogv"),
    "text": (".txt", ".text", ".log", ".json", ".xml", ".yaml", ".yml", ".tex"),
    "markdown": (".md", ".markdown"),
    "html": (".html", ".htm"),
    "table": (".csv", ".tsv", ".xlsx", ".xlsm", ".ods"),
    "document": (".docx", ".pptx", ".epub"),
    "archive": (".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"),
}
KIND_OF_SUFFIX = {
    suffix: kind for kind, suffixes in _KINDS.items() for suffix in suffixes
}

_MEDIA_TYPES = {
    ".md": "text/markdown",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".opus": "audio/ogg",
    ".mov": "video/quicktime",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
}


def preview_kind(path: str) -> str:
    return KIND_OF_SUFFIX.get(Path(path).suffix.lower(), "none")


def media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return (
        _MEDIA_TYPES.get(suffix)
        or mimetypes.guess_type(path)[0]
        or "application/octet-stream"
    )


def read_text(path: str, limit: int = MAX_TEXT_CHARS) -> Tuple[str, bool]:
    """The file as text (undecodable bytes replaced) and whether it was cut short."""
    with open(path, "rb") as f:
        data = f.read(limit * 4 + 4)
    text = data.decode("utf-8-sig", errors="replace")
    if len(text) > limit:
        return text[:limit], True
    return text, False


# --- tables ---------------------------------------------------------------


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _sheet(name: str, rows: List[List[str]], total: int) -> Dict[str, Any]:
    width = max((len(r) for r in rows), default=0)
    rows = [(r + [""] * (width - len(r)))[:MAX_COLUMNS] for r in rows]
    return {
        "name": name,
        "rows": rows,
        "total_rows": total,
        "truncated": total > len(rows) or width > MAX_COLUMNS,
    }


def _delimited(path: str) -> List[Dict[str, Any]]:
    text, _ = read_text(path)
    delimiter = "\t" if path.lower().endswith(".tsv") else None
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:20_000], ",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    rows: List[List[str]] = []
    total = 0
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        total += 1
        if len(rows) < MAX_ROWS:
            rows.append(row)
    return [_sheet(Path(path).name, rows, total)]


def _xlsx(path: str) -> List[Dict[str, Any]]:
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = []
        for ws in book.worksheets[:MAX_SHEETS]:
            rows: List[List[str]] = []
            for values in ws.iter_rows(max_row=MAX_ROWS, values_only=True):
                rows.append([_cell(v) for v in values[: MAX_COLUMNS + 1]])
            while rows and not any(rows[-1]):
                rows.pop()
            sheets.append(_sheet(ws.title, rows, max(ws.max_row or 0, len(rows))))
        return sheets
    finally:
        book.close()


def _ods(path: str) -> List[Dict[str, Any]]:
    import pandas as pd

    frames = pd.read_excel(path, engine="odf", sheet_name=None, header=None)
    sheets = []
    for name, frame in list(frames.items())[:MAX_SHEETS]:
        frame = frame.dropna(how="all")
        rows = [
            [_cell(None if pd.isna(v) else v) for v in row]
            for row in frame.head(MAX_ROWS).itertuples(index=False)
        ]
        sheets.append(_sheet(str(name), rows, len(frame)))
    return sheets


def read_table(path: str) -> List[Dict[str, Any]]:
    """The first rows of each sheet: [{name, rows, total_rows, truncated}]."""
    suffix = Path(path).suffix.lower()
    if suffix in (".csv", ".tsv"):
        return _delimited(path)
    if suffix == ".ods":
        return _ods(path)
    return _xlsx(path)


# --- documents (not converted to PDF) --------------------------------------


def _docx_html(path: str) -> str:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(path)
    parts: List[str] = []
    for block in document.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(block, document)
            text = html.escape(paragraph.text)
            if not text.strip():
                continue
            style = (paragraph.style.name if paragraph.style is not None else "") or ""
            level = re.match(r"Heading (\d)", style)
            if style == "Title":
                parts.append(f"<h1>{text}</h1>")
            elif level:
                n = min(int(level.group(1)) + 1, 6)
                parts.append(f"<h{n}>{text}</h{n}>")
            elif "List" in style:
                parts.append(f"<p>• {text}</p>")
            else:
                parts.append(f"<p>{text}</p>")
        elif tag == "tbl":
            table = Table(block, document)
            rows = "".join(
                "<tr>"
                + "".join(f"<td>{html.escape(c.text)}</td>" for c in row.cells)
                + "</tr>"
                for row in table.rows[:MAX_ROWS]
            )
            parts.append(f"<table>{rows}</table>")
    return "\n".join(parts)


def _pptx_html(path: str) -> str:
    from pptx import Presentation

    parts: List[str] = []
    for number, slide in enumerate(Presentation(path).slides, start=1):
        title = slide.shapes.title.text if slide.shapes.title is not None else ""
        heading = html.escape(title.strip()) or f"Slide {number}"
        parts.append(f'<section><h2><span class="n">{number}</span> {heading}</h2>')
        for shape in slide.shapes:
            if shape == slide.shapes.title or not shape.has_text_frame:
                continue
            for paragraph in shape.text_frame.paragraphs:
                text = "".join(run.text for run in paragraph.runs).strip()
                if text:
                    indent = min(paragraph.level, 4)
                    parts.append(f'<p class="l{indent}">{html.escape(text)}</p>')
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                parts.append(f'<p class="notes">{html.escape(notes)}</p>')
        parts.append("</section>")
    return "\n".join(parts)


_BODY = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
_UNSAFE = re.compile(
    r"<(script|style|iframe|object|embed|link|meta)\b.*?(?:</\1>|/?>)", re.S | re.I
)


def _epub_html(path: str) -> str:
    """The book's chapters in reading order (text only; images aren't served)."""
    ns = {
        "c": "urn:oasis:names:tc:opendocument:xmlns:container",
        "o": "http://www.idpf.org/2007/opf",
    }
    with zipfile.ZipFile(path) as book:
        container = ElementTree.fromstring(book.read("META-INF/container.xml"))
        rootfile = container.find(".//c:rootfile", ns)
        if rootfile is None:
            return ""
        opf_path = rootfile.get("full-path", "")
        opf = ElementTree.fromstring(book.read(opf_path))
        base = posixpath.dirname(opf_path)
        manifest = {
            item.get("id"): item.get("href", "")
            for item in opf.findall(".//o:manifest/o:item", ns)
        }
        chapters: List[str] = []
        size = 0
        for ref in opf.findall(".//o:spine/o:itemref", ns):
            href = manifest.get(ref.get("idref"))
            if not href:
                continue
            try:
                raw = book.read(posixpath.normpath(posixpath.join(base, href)))
            except KeyError:
                continue
            page = raw.decode("utf-8", errors="replace")
            body = _BODY.search(page)
            chapter = _UNSAFE.sub("", body.group(1) if body else page)
            chapter = re.sub(r"<img\b[^>]*>", "", chapter, flags=re.I)
            chapters.append(f"<section>{chapter}</section>")
            size += len(chapter)
            if size > MAX_TEXT_CHARS:
                break
    return "\n<hr>\n".join(chapters)


_DOCUMENT_STYLE = """<style>
body{font:15px/1.6 system-ui,sans-serif;max-width:46rem;margin:1.5rem auto;padding:0 1rem;color:#1f2328}
h1,h2,h3{line-height:1.3}table{border-collapse:collapse;margin:1rem 0}
td{border:1px solid #d0d7de;padding:4px 8px;vertical-align:top}
section{border-bottom:1px solid #d0d7de;padding-bottom:.75rem}
.n{color:#8b949e;font-weight:400;margin-right:.4rem}.notes{color:#57606a;font-style:italic}
.l1{margin-left:1.5rem}.l2{margin-left:3rem}.l3,.l4{margin-left:4.5rem}
@media (prefers-color-scheme:dark){body{color:#e6edf3;background:#0d1117}td{border-color:#30363d}}
</style>"""


def document_html(path: str) -> str:
    """A Word, PowerPoint or EPUB file's text as a standalone HTML page."""
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        body = _docx_html(path)
    elif suffix == ".pptx":
        body = _pptx_html(path)
    else:
        body = _epub_html(path)
    return f'<!doctype html><meta charset="utf-8">{_DOCUMENT_STYLE}{body}'


# --- archives --------------------------------------------------------------


def archive_entries(path: str) -> Tuple[List[Dict[str, Any]], bool]:
    """Files in a ZIP or tar archive: ([{name, size, dir}], truncated)."""
    entries: List[Dict[str, Any]] = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            for info in infos[:MAX_ENTRIES]:
                entries.append(
                    {
                        "name": info.filename,
                        "size": info.file_size,
                        "dir": info.is_dir(),
                    }
                )
            return entries, len(infos) > MAX_ENTRIES
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            truncated = False
            for member in archive:
                if len(entries) >= MAX_ENTRIES:
                    truncated = True
                    break
                entries.append(
                    {"name": member.name, "size": member.size, "dir": member.isdir()}
                )
            return entries, truncated
    return [], False


def build_preview(path: str, pages: Optional[int] = None) -> Dict[str, Any]:
    """The viewer's description of a file (synchronous; run in a thread).

    A file that can't be parsed (a damaged spreadsheet, a .gz that isn't a tar)
    falls back to `none` instead of failing: the download still works.
    """
    kind = preview_kind(path)
    result: Dict[str, Any] = {
        "kind": kind,
        "filename": Path(path).name,
        "media_type": media_type(path),
        "size": Path(path).stat().st_size,
    }
    try:
        if kind == "pages":
            from open_notebook.utils.pdf_pages import pdf_page_count

            result["pages"] = pages or pdf_page_count(path)
        elif kind in ("text", "markdown", "html"):
            result["text"], result["truncated"] = read_text(path)
        elif kind == "table":
            result["sheets"] = read_table(path)
        elif kind == "document":
            result["html"] = document_html(path)
        elif kind == "archive":
            entries, truncated = archive_entries(path)
            if not entries:
                result["kind"] = "none"
            result["entries"], result["truncated"] = entries, truncated
    except Exception as e:  # noqa: BLE001 - any parse failure means "no preview"
        from loguru import logger

        logger.warning(f"No preview for {Path(path).name}: {e}")
        result = {**result, "kind": "none"}
    return result
