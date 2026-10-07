"""Upload every PDF in a folder into a notebook (created if missing) via the local API.

Uses the transformations that are marked "apply by default", mirroring what the
UI pre-selects for a new upload, and embeds each source. Skips files whose title
already exists in the notebook, so it is safe to re-run.

Usage (on the PC):
  uv run python scripts/brain/ingest_folder.py --notebook "AI 360 Deep Learning" ~/workplace/Brain/corpus/dl-notes
"""

import argparse
import json
from pathlib import Path

import httpx

API = "http://127.0.0.1:5055/api"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--notebook", required=True)
    ap.add_argument("--description", default="")
    args = ap.parse_args()

    client = httpx.Client(base_url=API, timeout=300)
    notebooks = client.get("/notebooks").raise_for_status().json()
    notebook = next((n for n in notebooks if n["name"] == args.notebook), None)
    if notebook is None:
        notebook = (
            client.post(
                "/notebooks",
                json={"name": args.notebook, "description": args.description},
            )
            .raise_for_status()
            .json()
        )
        print(f"created {notebook['id']}")
    nb_id = notebook["id"]

    defaults = [
        t["id"]
        for t in client.get("/transformations").raise_for_status().json()
        if t.get("apply_default")
    ]
    existing = {
        s.get("title")
        for s in client.get("/sources", params={"notebook_id": nb_id})
        .raise_for_status()
        .json()
    }

    for pdf in sorted(Path(args.folder).expanduser().glob("*.pdf")):
        if pdf.name in existing or pdf.stem in existing:
            print(f"skip  {pdf.name}")
            continue
        with pdf.open("rb") as fh:
            resp = client.post(
                "/sources",
                data={
                    "type": "upload",
                    "notebooks": json.dumps([nb_id]),
                    "transformations": json.dumps(defaults),
                    "embed": "true",
                    "async_processing": "true",
                },
                files={"file": (pdf.name, fh, "application/pdf")},
            )
        resp.raise_for_status()
        print(f"queued {pdf.name} -> {resp.json()['id']}")
    print(f"notebook {nb_id}; default transformations: {defaults}")


if __name__ == "__main__":
    main()
