"""Re-run vision captions for PDFs ingested before a caption-rule change.

Re-extracts each PDF's page signals (image area, drawn shapes, garbled text),
stores them on source_page, and queues the caption job for sources that now
have uncaptioned visual pages. Pages that already have a caption are kept.
The caption job then re-embeds the source and re-runs analysis (outline,
summaries, concepts), which read the captions.

Usage (on the machine running the worker, from the project directory):
  uv run python scripts/brain/recaption_pages.py --notebook "My Course" [--dry-run]
"""

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")

from surreal_commands import submit_command  # noqa: E402

import commands  # noqa: E402,F401  (registers the caption command)
from open_notebook.agent.graph import knowledge_base_scope  # noqa: E402
from open_notebook.database.repository import (  # noqa: E402
    ensure_record_id,
    repo_query,
)
from open_notebook.domain.notebook import Source  # noqa: E402
from open_notebook.utils.pdf_pages import (  # noqa: E402
    extract_pdf_pages,
    pages_needing_captions,
)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook", required=True, help="notebook name")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    found = await repo_query(
        "SELECT VALUE id FROM notebook WHERE name = $name", {"name": args.notebook}
    )
    if not found:
        raise SystemExit(f"No notebook named {args.notebook!r}")
    source_ids, _ = await knowledge_base_scope([str(found[0])])

    queued = 0
    for source_id in source_ids:
        source = await Source.get(source_id)
        path = source.asset.file_path if source and source.asset else None
        if not path or Path(path).suffix.lower() != ".pdf" or not Path(path).is_file():
            continue
        record = ensure_record_id(source_id)
        captioned = {
            r["page"]
            for r in await repo_query(
                "SELECT page FROM source_page WHERE source = $s AND caption != NONE",
                {"s": record},
            )
        }
        pages = await asyncio.to_thread(extract_pdf_pages, path)
        new = [n for n in pages_needing_captions(pages) if n not in captioned]
        print(f"{source.title}: {len(new)} new visual pages", flush=True)
        if args.dry_run:
            continue
        for page in pages:
            await repo_query(
                "UPDATE source_page SET image_ratio = $ratio, shapes = $shapes, garbled = $garbled "
                "WHERE source = $s AND page = $page",
                {
                    "s": record,
                    "page": page.number,
                    "ratio": page.image_ratio,
                    "shapes": page.shapes,
                    "garbled": page.garbled,
                },
            )
        if new:
            submit_command("open_notebook", "caption_pages", {"source_id": source_id})
            queued += 1
    print(f"queued caption jobs for {queued} sources")


if __name__ == "__main__":
    asyncio.run(main())
