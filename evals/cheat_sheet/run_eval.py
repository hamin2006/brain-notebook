"""Score a cheat sheet against a course checklist (plans/cheat-sheet.md, Validation).

Builds a sheet through the running API (or scores an existing one) and reports:

- checklist recall: entries on the sheet, out of those the selected documents
  teach (an entry no recall item matches is "not taught" and doesn't count);
- citations: every line cites at least one page, and every cited page exists;
- fit: characters against the page budget (the browser's measure is the real
  test: open the sheet and look for the Shorten / Add more banner);
- cost and time of the build.

Formula correctness is checked by hand against the cited slides.

Usage (next to the API; reads the database for the recall items):
  uv run --env-file .env python evals/cheat_sheet/run_eval.py --notebook "Calculus 2 (UW MATH 138)"
  uv run --env-file .env python evals/cheat_sheet/run_eval.py --notebook "..." --sources "Ch5|Ch6" --pages 1
  uv run --env-file .env python evals/cheat_sheet/run_eval.py --sheet cheat_sheet:abc
"""

import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx

HERE = Path(__file__).parent
API = "http://127.0.0.1:5055/api"


def sheet_text(layout: Dict[str, Any]) -> str:
    return "\n".join(
        [t["title"] for t in layout["topics"]]
        + [line["text"] for t in layout["topics"] for line in t["lines"]]
    ).lower()


def matches(entry: Dict[str, Any], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in entry["patterns"])


def build(client: httpx.Client, args: argparse.Namespace) -> str:
    notebook = next(
        (n for n in client.get("/notebooks").json() if n["name"] == args.notebook), None
    )
    if notebook is None:
        raise SystemExit(f"No notebook named {args.notebook!r}")
    sources = client.get(f"/notebooks/{notebook['id']}/cheat-sheets/sources").json()
    if args.sources:
        sources = [s for s in sources if re.search(args.sources, s["title"])]
    sheet = (
        client.post(
            f"/notebooks/{notebook['id']}/cheat-sheets",
            json={
                "title": f"Eval {datetime.now():%Y-%m-%d %H:%M}",
                "source_ids": [s["id"] for s in sources],
                "pages": args.pages,
                "columns": args.columns,
                "instructions": args.instructions,
            },
        )
        .raise_for_status()
        .json()
    )
    print(f"building {sheet['id']} over {len(sources)} documents")
    return sheet["id"]


def wait(client: httpx.Client, sheet_id: str) -> Dict[str, Any]:
    while True:
        sheet = client.get(f"/cheat-sheets/{sheet_id}").raise_for_status().json()
        if sheet["status"] in ("done", "failed"):
            return sheet
        time.sleep(5)


async def pool_text(source_ids: List[str]) -> str:
    from open_notebook.domain.cheat_sheet import sheet_items

    items = await sheet_items(source_ids)
    return "\n".join(f"{i['title']}\n{i['body']}" for i in items).lower()


def check_citations(client: httpx.Client, layout: Dict[str, Any]) -> Dict[str, Any]:
    pages: Dict[str, int] = {}
    uncited, bad = [], []
    for topic in layout["topics"]:
        for line in topic["lines"]:
            if not line["cites"]:
                uncited.append(line["id"])
            for cite in line["cites"]:
                sid = cite["source"]
                if sid not in pages:
                    structure = client.get(f"/sources/{sid}/structure").json()
                    pages[sid] = int(structure.get("page_count") or 0)
                if not (1 <= cite["page_start"] <= cite["page_end"] <= pages[sid]):
                    bad.append((line["id"], cite))
    return {"uncited_lines": uncited, "invalid_cites": bad}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help="score this sheet instead of building one")
    ap.add_argument("--notebook")
    ap.add_argument("--sources", help="regex on document titles (default: all)")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--columns", type=int, default=3)
    ap.add_argument("--instructions", default="")
    ap.add_argument("--checklist", default=str(HERE / "calc2.json"))
    ap.add_argument("--api", default=API)
    args = ap.parse_args()
    if not args.sheet and not args.notebook:
        ap.error("give --sheet or --notebook")

    checklist = json.loads(Path(args.checklist).read_text())
    with httpx.Client(base_url=args.api, timeout=60) as client:
        sheet_id = args.sheet or build(client, args)
        sheet = wait(client, sheet_id)
        if sheet["status"] == "failed":
            raise SystemExit(f"build failed: {sheet.get('error')}")
        layout = sheet["layout"]
        text = sheet_text(layout)
        taught_text = asyncio.run(pool_text(sheet["sources"]))
        citations = check_citations(client, layout)

    rows = []
    for entry in checklist["checklist"]:
        on_sheet = matches(entry, text)
        rows.append(
            {
                **entry,
                "on_sheet": on_sheet,
                "taught": on_sheet or matches(entry, taught_text),
            }
        )
    taught = [r for r in rows if r["taught"]]
    hits = [r for r in taught if r["on_sheet"]]
    detail = sheet.get("detail") or {}
    lines = sum(len(t["lines"]) for t in layout["topics"])
    summary = {
        "sheet": sheet_id,
        "version": sheet["version"],
        "documents": len(sheet["sources"]),
        "recall": f"{len(hits)}/{len(taught)}",
        "missing": [r["label"] for r in taught if not r["on_sheet"]],
        "not_taught": [r["label"] for r in rows if not r["taught"]],
        "lines": lines,
        "chars": layout.get("chars"),
        "budget_chars": layout.get("budget_chars"),
        "uncited_lines": len(citations["uncited_lines"]),
        "invalid_cites": len(citations["invalid_cites"]),
        "cost": (detail.get("usage") or {}).get("cost"),
        "seconds": detail.get("seconds"),
    }
    for row in rows:
        mark = "✓" if row["on_sheet"] else ("·" if not row["taught"] else "✗")
        print(f"  {mark} {row['label']}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    out = HERE / "results" / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {"summary": summary, "checklist": rows, "citations": citations},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
