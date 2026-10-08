"""Upload every PDF in a folder into a notebook (created if missing) via the local API.

Uses the transformations that are marked "apply by default", mirroring what the
UI pre-selects for a new upload, and embeds each source. Skips files whose title
already exists in the notebook, so it is safe to re-run.

With --wait it follows the notebook's ingestion (GET /notebooks/{id}/ingestion)
until every source has finished every stage, printing progress each minute and
then the time each stage took.

Usage (on the machine running the API):
  uv run python scripts/brain/ingest_folder.py --notebook "My Course" path/to/pdfs [--wait]
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx

API = "http://127.0.0.1:5055/api"
STAGES = ["extract", "caption", "embed", "analyze", "page_images", "concepts"]


def _ts(value: Optional[str]) -> Optional[float]:
    return datetime.fromisoformat(value).timestamp() if value else None


def report(body: dict, started: float) -> None:
    """Per-stage run time (sum and slowest source) and when the stage finished."""
    run: Dict[str, List[float]] = defaultdict(list)
    finished: Dict[str, float] = {}
    for item in body["items"]:
        for stage in item["stages"]:
            if stage.get("seconds") is not None:
                run[stage["stage"]].append(stage["seconds"])
            end = _ts(stage.get("finished_at"))
            if end:
                finished[stage["stage"]] = max(finished.get(stage["stage"], 0), end)
    print(
        f"{'stage':12} {'sources':>7} {'total run':>10} {'slowest':>8} {'done at':>8}"
    )
    for name in STAGES:
        times = run.get(name, [])
        done_at = (finished[name] - started) / 60 if name in finished else None
        print(
            f"{name:12} {len(times):7} {sum(times) / 60:9.1f}m {max(times, default=0):7.0f}s "
            + (f"{done_at:7.1f}m" if done_at is not None else "      -")
        )
    for item in body["items"]:
        for stage in item["stages"]:
            if stage["status"] == "failed":
                print(f"FAILED {item['title']}: {stage['stage']}: {stage.get('error')}")


def wait(client: httpx.Client, nb_id: str, started: float, timeout_min: float) -> None:
    last = 0.0
    while True:
        body = client.get(f"/notebooks/{nb_id}/ingestion").raise_for_status().json()
        elapsed = time.time() - started
        if body["complete"] or (
            body["sources_failed"]
            and body["sources_complete"] + body["sources_failed"] == body["sources"]
        ):
            print(
                f"finished in {elapsed / 60:.1f} min: {body['sources_complete']}/{body['sources']} "
                f"sources complete, {body['sources_failed']} failed"
            )
            report(body, started)
            return
        if elapsed - last >= 60:
            active = (
                ", ".join(f"{k} {v}" for k, v in body["active"].items()) or "waiting"
            )
            print(
                f"t+{elapsed / 60:4.1f}m {body['sources_complete']}/{body['sources']} done; {active}",
                flush=True,
            )
            last = elapsed
        if elapsed > timeout_min * 60:
            print(f"stopped waiting after {timeout_min:.0f} min; ingestion continues")
            report(body, started)
            return
        time.sleep(10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--notebook", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--wait", action="store_true", help="follow ingestion to the end")
    ap.add_argument("--timeout", type=float, default=180, help="minutes to wait")
    args = ap.parse_args()
    started = time.time()
    folder = Path(args.folder).expanduser()
    pdfs = sorted(p for p in folder.glob("*.pdf") if not p.name.startswith("."))
    if not pdfs:  # before touching the notebook: a typo shouldn't create one
        raise SystemExit(
            f"no PDFs in {folder}" + ("" if folder.is_dir() else " (no such folder)")
        )

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

    for pdf in pdfs:  # ._name.pdf (macOS metadata files) were left out above
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
    if args.wait:
        wait(client, nb_id, started, args.timeout)


if __name__ == "__main__":
    main()
