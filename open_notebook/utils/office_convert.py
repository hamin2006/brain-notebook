"""Convert office documents (slides, word processing) to PDF before ingestion.

A PDF gets the full page pipeline (pages, captions, page images, outline,
concepts); a .pptx or .docx through content-core is one block of text. When
LibreOffice is installed (`soffice` on PATH) uploads in these formats are
converted with it, headless; without it, or if conversion fails, they are
extracted as text as before.

OPEN_NOTEBOOK_OFFICE_TO_PDF: `auto` (default: convert when soffice is found),
`off`, or the path of the soffice binary.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

OFFICE_SUFFIXES = {
    ".pptx",
    ".ppt",
    ".ppsx",
    ".pps",
    ".odp",
    ".docx",
    ".doc",
    ".odt",
    ".rtf",
}
CONVERT_TIMEOUT_SECONDS = 300


def office_converter() -> Optional[str]:
    """The soffice binary to convert with, or None when conversion is off/unavailable."""
    setting = os.environ.get("OPEN_NOTEBOOK_OFFICE_TO_PDF", "auto").strip()
    if setting.lower() in ("off", "false", "0", "no"):
        return None
    if setting.lower() not in ("", "auto"):
        return setting if Path(setting).is_file() else None
    return shutil.which("soffice") or shutil.which("libreoffice")


def is_office_document(path: str) -> bool:
    return Path(path).suffix.lower() in OFFICE_SUFFIXES


def _free_path(path: Path) -> Path:
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def convert_to_pdf(path: str) -> Optional[str]:
    """Convert `path` to a PDF beside it (synchronous; run in a thread).

    Returns the PDF's path, or None when no converter is available or the
    conversion fails. The original file is left in place.
    """
    soffice = office_converter()
    if not soffice:
        return None
    source = Path(path)
    with tempfile.TemporaryDirectory(prefix="brain-office-") as tmp:
        # A private profile per conversion: concurrent soffice processes
        # sharing the default profile block on its lock.
        profile = Path(tmp, "profile").as_uri()
        try:
            subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmp,
                    str(source),
                ],
                check=True,
                capture_output=True,
                timeout=CONVERT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning(f"Converting {source.name} to PDF failed: {e}")
            return None
        produced = Path(tmp, source.stem + ".pdf")
        if not produced.is_file() or produced.stat().st_size == 0:
            logger.warning(f"Converting {source.name} to PDF produced no file")
            return None
        target = _free_path(source.with_suffix(".pdf"))
        shutil.move(str(produced), target)
    logger.info(f"Converted {source.name} to {target.name}")
    return str(target)
