"""Research-trace text for people: addresses become document names and pages.

Tools take and return addresses (`source:abc#p12-18`), which the agent needs and
the UI turns into links in answers. The research trace shown beside an answer
reads them as text, so every address in a step's subject or result line is
replaced with the document's title and its page, section or layer:

    source:abc#p12-18   ->  Lecture 6.pdf pp. 12–18
    source:abc#s3       ->  Lecture 6.pdf section 4   (outline index, from 0)
    note:xyz            ->  the note's title

Raw arguments stay untouched (the UI counts the documents a trace touched from
them); the readable form goes in `subject` and in the result text.
"""

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from open_notebook.database.repository import ensure_record_id, repo_query

ADDRESS_IN_TEXT = re.compile(
    r"\b(?P<id>(?:source|note|source_insight):[A-Za-z0-9_]+)"
    r"(?:#p(?P<p1>\d+)(?:-(?P<p2>\d+))?|#s(?P<section>\d+)|#c(?P<chunk>\d+)|/(?P<layer>summary|outline))?"
)

# The argument a step is about, in the order the UI picks it.
SUBJECT_ARGS = (
    "query",
    "pattern",
    "address",
    "source",
    "like",
    "title_contains",
    "concept",
    "url",
    "expression",
    "task",
)


def _label(match: re.Match, titles: Mapping[str, str]) -> str:
    record = match["id"]
    table = record.split(":", 1)[0]
    if table == "source_insight":
        return "an insight"
    if table == "note":
        return titles.get(record) or "a note"
    name = titles.get(record) or "a document"
    p1, p2 = match["p1"], match["p2"]
    if p1 and p2 and p2 != p1:
        return f"{name} pp. {p1}–{p2}"
    if p1:
        return f"{name} p. {p1}"
    if match["section"] is not None:
        return f"{name} section {int(match['section']) + 1}"
    if match["chunk"] is not None:
        return f"{name} passage {match['chunk']}"
    if match["layer"]:
        return f"{name} ({match['layer']})"
    return name


def humanize(text: str, titles: Mapping[str, str]) -> str:
    """`text` with every address replaced by a readable name."""
    return ADDRESS_IN_TEXT.sub(lambda m: _label(m, titles), text or "")


def step_subject(args: Mapping[str, Any], titles: Mapping[str, str]) -> Optional[str]:
    """What a step is about, readable (None when it has no subject)."""
    for key in SUBJECT_ARGS:
        value = args.get(key)
        if value:
            return humanize(str(value), titles)
    if args.get("sequence") is not None:
        return f"#{args['sequence']}"
    return None


def display_step(step: Dict[str, Any], titles: Mapping[str, str]) -> Dict[str, Any]:
    """A trace step with its readable subject and an address-free result."""
    shown = dict(step)
    shown["subject"] = step_subject(step.get("args") or {}, titles)
    if step.get("result"):
        shown["result"] = humanize(str(step["result"]), titles)
    return shown


def addresses_in(texts: Iterable[str]) -> List[str]:
    """Record ids (`source:abc`, `note:xyz`) mentioned in the texts."""
    found = {m["id"] for text in texts for m in ADDRESS_IN_TEXT.finditer(text or "")}
    return sorted(found)


async def titles_for(record_ids: Iterable[str]) -> Dict[str, str]:
    """Titles of the sources and notes among `record_ids` (missing ones are left out)."""
    ids = [
        ensure_record_id(r) for r in record_ids if r.startswith(("source:", "note:"))
    ]
    if not ids:
        return {}
    rows = await repo_query("SELECT id, title FROM $ids", {"ids": ids})
    return {str(r["id"]): str(r["title"]) for r in rows if r.get("title")}


async def display_trace(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A stored trace made readable, looking up the titles it mentions."""
    texts = [
        str(step.get("args") or {}) + " " + str(step.get("result") or "")
        for step in trace
    ]
    titles = await titles_for(addresses_in(texts))
    return [display_step(step, titles) for step in trace]
