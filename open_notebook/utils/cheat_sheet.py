"""Cheat sheets: recall items, page budget and layout checks (plans/cheat-sheet.md).

Recall items are what a student must recall from one outline section: a
formula, a definition, a theorem, a method, a worked-example skeleton or a
pitfall. The composer turns items into a layout of topics and lines; every
line names the items it covers, and its citations come from those items, never
from the model. Lines that cover no known item are dropped.
"""

import copy
import json
import re
from typing import Any, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from open_notebook.utils.concepts import _escape_latex

KINDS = ("formula", "definition", "theorem", "method", "example", "pitfall")
Kind = Literal["formula", "definition", "theorem", "method", "example", "pitfall"]
DEFAULT_KINDS: List[Kind] = ["formula", "definition", "theorem", "method"]

MAX_ITEMS_PER_SECTION = 12
MAX_TITLE_CHARS = 120
MAX_BODY_CHARS = 600

# Characters of Markdown/LaTeX source that fill one printed page at 7 pt in the
# sheet's print stylesheet (Letter, narrow margins), after headings, inline
# math (its source is longer than what it renders) and ragged columns:
# a two-page calculus sheet fit 23.1K and overflowed at 24.4K. The browser measures real overflow;
# this only steers the composer. Type size follows the column count.
CHARS_PER_PAGE_AT_7PT = 12000
FONT_PT_BY_COLUMNS = {2: 8.0, 3: 7.0, 4: 6.0}
# The composer reads at most this much item text (about 45K tokens); beyond
# it, minor items are left out first, then bodies are shortened.
MAX_POOL_CHARS = 150_000
POOL_BODY_CHARS_WHEN_TIGHT = 280


class ExtractedItem(BaseModel):
    kind: Kind = Field(
        description="formula | definition | theorem | method | example | pitfall"
    )
    title: str = Field(description="Short name, e.g. 'Ratio test'")
    body: str = Field(
        description="What to recall, in Markdown with $...$ LaTeX, in the course's notation"
    )
    priority: int = Field(
        2,
        description="1 = must be on the sheet, 2 = useful, 3 = minor or background",
    )
    page_start: Optional[int] = Field(None, description="First page it appears on")
    page_end: Optional[int] = Field(None, description="Last page it appears on")

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: Any) -> str:
        v = str(v or "").strip().lower()
        aliases = {
            "rule": "theorem",
            "property": "theorem",
            "lemma": "theorem",
            "corollary": "theorem",
            "test": "method",
            "procedure": "method",
            "technique": "method",
            "equation": "formula",
            "identity": "formula",
            "worked example": "example",
            "mistake": "pitfall",
            "warning": "pitfall",
        }
        v = aliases.get(v, v)
        return v if v in KINDS else "definition"

    @field_validator("priority", mode="before")
    @classmethod
    def _priority(cls, v: Any) -> int:
        try:
            return min(max(int(v), 1), 3)
        except (TypeError, ValueError):
            return 2


class RecallExtraction(BaseModel):
    items: List[ExtractedItem] = Field(default_factory=list)


def json_object(raw: str) -> Any:
    """The JSON object in a model reply, tolerating fences, prose and LaTeX."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the reply")
    return json.loads(_escape_latex(raw[start : end + 1]), strict=False)


def parse_recall_items(
    raw: str, page_start: int, page_end: int
) -> List[Dict[str, Any]]:
    """Clean recall items from an extraction reply, pages clamped to the section."""
    extraction = RecallExtraction.model_validate(json_object(raw))
    items: List[Dict[str, Any]] = []
    seen = set()
    for item in extraction.items:
        title = " ".join(item.title.split())[:MAX_TITLE_CHARS]
        body = item.body.strip()[:MAX_BODY_CHARS]
        if not title or not body:
            continue
        key = (item.kind, title.lower())
        if key in seen:
            continue
        seen.add(key)
        first = item.page_start or item.page_end or page_start
        last = item.page_end or first
        first = min(max(first, page_start), page_end)
        last = min(max(last, first), page_end)
        items.append(
            {
                "kind": item.kind,
                "title": title,
                "body": body,
                "priority": item.priority,
                "page_start": first,
                "page_end": last,
            }
        )
        if len(items) >= MAX_ITEMS_PER_SECTION:
            break
    return items


# ---------------------------------------------------------------- options


class SheetOptions(BaseModel):
    pages: int = Field(2, ge=1, le=2)
    columns: int = Field(3, ge=2, le=4)
    kinds: List[Kind] = Field(default_factory=lambda: list(DEFAULT_KINDS))
    instructions: str = Field("", max_length=2000)
    paper: Literal["letter", "a4"] = "letter"
    # Budget multiplier set by Shorten (below 1) and Add more (above 1).
    scale: float = Field(1.0, ge=0.3, le=2.0)

    @field_validator("kinds")
    @classmethod
    def _kinds(cls, v: List[str]) -> List[str]:
        kinds = [k for k in KINDS if k in v]
        return kinds or list(DEFAULT_KINDS)


def font_pt(columns: int) -> float:
    return FONT_PT_BY_COLUMNS.get(columns, 7.0)


def budget_chars(options: SheetOptions) -> int:
    """Approximate source characters the sheet can hold (smaller type holds more)."""
    per_page = CHARS_PER_PAGE_AT_7PT * (7.0 / font_pt(options.columns)) ** 2
    return int(per_page * options.pages * options.scale)


# ---------------------------------------------------------------- composer input


def short_ids(items: List[Dict[str, Any]]) -> Dict[str, str]:
    """Short ids the model sees ("r1", "r2", ...) for item record ids."""
    return {f"r{i + 1}": str(item["id"]) for i, item in enumerate(items)}


def _cite_label(item: Dict[str, Any], labels: Dict[str, str]) -> str:
    label = labels.get(str(item["source"]), "")
    pages = (
        f"p.{item['page_start']}"
        if item["page_start"] == item["page_end"]
        else f"pp.{item['page_start']}-{item['page_end']}"
    )
    return f"{label} {pages}".strip()


def pool_lines(
    items: List[Dict[str, Any]],
    ids: Dict[str, str],
    labels: Dict[str, str],
    max_chars: int = MAX_POOL_CHARS,
) -> str:
    """Items as compact lines for the composer: `id · kind · priority · title · body · cite`.

    Items are in course order. Over `max_chars`, priority-3 items are left out,
    then bodies are shortened."""
    by_id = {v: k for k, v in ids.items()}

    def render(pool: Iterable[Dict[str, Any]], body_chars: int) -> str:
        out = []
        for item in pool:
            body = " ".join(item["body"].split())
            if len(body) > body_chars:
                body = body[:body_chars].rstrip() + "…"
            out.append(
                f"{by_id[str(item['id'])]} · {item['kind']} · p{item['priority']} · "
                f"{item['title']} · {body} · {_cite_label(item, labels)}"
            )
        return "\n".join(out)

    text = render(items, MAX_BODY_CHARS)
    if len(text) <= max_chars:
        return text
    core = [i for i in items if i["priority"] < 3]
    text = render(core, MAX_BODY_CHARS)
    if len(text) <= max_chars:
        return text
    return render(core, POOL_BODY_CHARS_WHEN_TIGHT)[:max_chars]


# ---------------------------------------------------------------- layout


_LINE_PREFIX = re.compile(
    r"^\s*(?:-\s*)?(?:l\d+\s*:?\s*)?(?:\[[a-z, ]*\]\s*)?(?:\(items?[^)]*\)\s*)?(?:·\s*)?"
)
_LINE_SUFFIX = re.compile(r"\s*<(?:pinned|edited|items)[^<>]*>\s*$")


def clean_line_text(text: str) -> str:
    """A line's text without the ids, flags and item lists the reviser was shown."""
    text = _LINE_SUFFIX.sub("", text.strip())
    return _LINE_PREFIX.sub("", text, count=1).strip()


class ComposedLine(BaseModel):
    items: List[str] = Field(default_factory=list)
    text: str = ""

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, v: Any) -> List[str]:
        return _short_id_list(v)

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str:
        return clean_line_text(str(v or ""))


class ComposedTopic(BaseModel):
    title: str = ""
    lines: List[ComposedLine] = Field(default_factory=list)


class ComposedSheet(BaseModel):
    title: str = ""
    topics: List[ComposedTopic] = Field(default_factory=list)


def _short_id_list(v: Any) -> List[str]:
    """Short item ids from a model: a list or a string, "r12-r15" ranges expanded."""
    if isinstance(v, str):
        v = re.split(r"[\s,;]+", v)
    out: List[str] = []
    for x in v or []:
        x = str(x).strip()
        match = re.fullmatch(r"r(\d+)\s*[-–—]\s*r?(\d+)", x)
        if match and int(match.group(2)) - int(match.group(1)) < 200:
            out += [
                f"r{n}" for n in range(int(match.group(1)), int(match.group(2)) + 1)
            ]
        elif x:
            out.append(x)
    return out


def _merge_cites(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Citations of a line: one per source, page ranges merged when they touch."""
    cites: List[Dict[str, Any]] = []
    for item in sorted(
        items, key=lambda i: (str(i["source"]), i["page_start"], i["page_end"])
    ):
        last = cites[-1] if cites else None
        if (
            last
            and last["source"] == str(item["source"])
            and item["page_start"] <= last["page_end"] + 1
        ):
            last["page_end"] = max(last["page_end"], item["page_end"])
        else:
            cites.append(
                {
                    "source": str(item["source"]),
                    "page_start": item["page_start"],
                    "page_end": item["page_end"],
                }
            )
    return cites


def _new_line(
    line_id: str,
    text: str,
    record_ids: List[str],
    items_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    covered = [items_by_id[r] for r in record_ids]
    return {
        "id": line_id,
        "text": text,
        "items": record_ids,
        "kind": covered[0]["kind"],
        "cites": _merge_cites(covered),
    }


def _resolve(
    short: List[str], ids: Dict[str, str], items_by_id: Dict[str, Dict[str, Any]]
) -> List[str]:
    return list(
        dict.fromkeys(ids[s] for s in short if s in ids and ids[s] in items_by_id)
    )


def build_layout(
    raws: List[str],
    ids: Dict[str, str],
    items_by_id: Dict[str, Dict[str, Any]],
    fallback_title: str,
) -> Dict[str, Any]:
    """The stored layout from the composer's replies (one per part, in order).

    Lines reference items by short id; unknown ids are ignored and a line left
    with no item is dropped (the model may condense, never invent). Citations
    are computed from the items."""
    sheets = [ComposedSheet.model_validate(json_object(raw)) for raw in raws]
    topics: List[Dict[str, Any]] = []
    dropped = 0
    n_line = 0
    for sheet in sheets:
        for topic in sheet.topics:
            lines = []
            for line in topic.lines:
                record_ids = _resolve(line.items, ids, items_by_id)
                if not record_ids or not line.text:
                    dropped += 1
                    continue
                n_line += 1
                lines.append(
                    _new_line(f"l{n_line}", line.text, record_ids, items_by_id)
                )
            title = " ".join(topic.title.split()) or "Topic"
            # Parts can end and start with the same topic.
            if lines and topics and topics[-1]["title"].lower() == title.lower():
                topics[-1]["lines"] += lines
            elif lines:
                topics.append({"title": title, "lines": lines})
    if not topics:
        raise ValueError("the composed sheet has no lines that cite an item")
    for i, placed in enumerate(topics):
        placed["id"] = f"t{i + 1}"
    # The sheet's own title: a part's title only describes that part.
    return {
        "title": fallback_title,
        "topics": topics,
        "dropped_lines": dropped,
    }


# ---------------------------------------------------------------- composing in parts

# One composer reply tops out around 16K characters of sheet, whatever the
# budget; a larger sheet is composed in parts of about this size, in parallel.
PART_CHARS = 9000


def split_items(items: List[Dict[str, Any]], parts: int) -> List[List[Dict[str, Any]]]:
    """Items (in course order) cut into `parts` contiguous groups of about equal
    weight, cutting between documents where possible. Weight is body length of
    the items likely to make the sheet (priority 1 and 2)."""
    if parts <= 1 or len(items) <= parts:
        return [items]

    def weight(item: Dict[str, Any]) -> int:
        return len(item["body"]) + 40 if item["priority"] < 3 else 10

    total = sum(weight(i) for i in items)
    boundaries = [
        i for i in range(1, len(items)) if items[i]["source"] != items[i - 1]["source"]
    ] or list(range(1, len(items)))
    cumulative, running = [], 0
    for item in items:
        running += weight(item)
        cumulative.append(running)
    cuts: List[int] = []
    for k in range(1, parts):
        target = total * k / parts
        best = min(
            (b for b in boundaries if not cuts or b > cuts[-1]),
            key=lambda b: abs(cumulative[b - 1] - target),
            default=None,
        )
        if best is not None:
            cuts.append(best)
    edges = [0, *cuts, len(items)]
    return [items[a:b] for a, b in zip(edges, edges[1:]) if b > a]


def part_budgets(groups: List[List[Dict[str, Any]]], budget: int) -> List[int]:
    weights = [
        sum(len(i["body"]) + 40 for i in g if i["priority"] < 3) or 1 for g in groups
    ]
    total = sum(weights)
    return [max(800, int(budget * w / total)) for w in weights]


# ---------------------------------------------------------------- revising


class LineEdit(BaseModel):
    line: str
    text: str = ""

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str:
        return clean_line_text(str(v or ""))


class LineAdd(BaseModel):
    topic: str = ""
    after: Optional[str] = None
    items: List[str] = Field(default_factory=list)
    text: str = ""

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, v: Any) -> List[str]:
        return _short_id_list(v)

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str:
        return clean_line_text(str(v or ""))


class CommentNote(BaseModel):
    id: str
    note: str = ""


class RevisionOps(BaseModel):
    remove: List[str] = Field(
        default_factory=list, description="Ids of lines to remove"
    )
    edit: List[LineEdit] = Field(
        default_factory=list, description="Lines to reword: id and new text"
    )
    add: List[LineAdd] = Field(
        default_factory=list,
        description="New lines: topic title, the line id to insert after (optional), item ids, text",
    )
    comments: List[CommentNote] = Field(
        default_factory=list, description="For each comment id, what changed"
    )


def _line_number(line_id: str) -> int:
    match = re.fullmatch(r"l(\d+)", line_id or "")
    return int(match.group(1)) if match else 0


def _is_kept_verbatim(line: Dict[str, Any]) -> bool:
    return bool(line.get("pinned") or line.get("edited"))


def apply_revision(
    previous: Dict[str, Any],
    raw: str,
    ids: Dict[str, str],
    items_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """The current layout with the reviser's operations applied.

    Removals and edits skip pinned and hand-edited lines. Added lines must
    cite items (unknown ids are ignored; a line left with none is dropped) and
    get ids after the highest one used, so comments stay anchored; they go
    after the line named in `after`, else at the end of the topic with that
    title, else into a new topic at the end."""
    ops = RevisionOps.model_validate(json_object(raw))
    topics = copy.deepcopy(previous.get("topics", []))
    lines_by_id = {line["id"]: line for t in topics for line in t["lines"]}
    protected = {i for i, line in lines_by_id.items() if _is_kept_verbatim(line)}

    removed = {i for i in ops.remove if i in lines_by_id and i not in protected}
    for edit in ops.edit:
        line = lines_by_id.get(edit.line)
        if line is not None and edit.line not in protected and edit.text:
            line["text"] = edit.text
    for topic in topics:
        topic["lines"] = [x for x in topic["lines"] if x["id"] not in removed]

    next_number = max((_line_number(i) for i in lines_by_id), default=0)
    dropped = 0
    for add in ops.add:
        record_ids = _resolve(add.items, ids, items_by_id)
        if not record_ids or not add.text:
            dropped += 1
            continue
        next_number += 1
        line = _new_line(f"l{next_number}", add.text, record_ids, items_by_id)
        home = next(
            (t for t in topics if any(x["id"] == add.after for x in t["lines"])), None
        )
        if home is not None:
            at = next(i for i, x in enumerate(home["lines"]) if x["id"] == add.after)
            home["lines"].insert(at + 1, line)
            continue
        title = " ".join(add.topic.split()) or "More"
        home = next((t for t in topics if t["title"].lower() == title.lower()), None)
        if home is None:
            home = {"title": title, "lines": []}
            topics.append(home)
        home["lines"].append(line)

    topics = [t for t in topics if t["lines"]]
    if not topics:
        raise ValueError("the revision removed every line")
    for i, topic in enumerate(topics):
        topic["id"] = f"t{i + 1}"
    return {
        "title": previous.get("title") or "Cheat sheet",
        "topics": topics,
        "dropped_lines": dropped,
        "comment_notes": {c.id: c.note.strip() for c in ops.comments if c.note.strip()},
    }


def revision_lines(layout: Dict[str, Any], short_of: Dict[str, str]) -> str:
    """The current sheet for the reviser: topics, then each line with its id,
    flags and the short ids of items it covers (when they still exist)."""
    out = []
    for topic in layout.get("topics", []):
        out.append(f"## {topic['title']}")
        for line in topic["lines"]:
            flags = [f for f in ("pinned", "edited") if line.get(f)]
            refs = [short_of[i] for i in line["items"] if i in short_of]
            meta = "; ".join(
                ([", ".join(flags)] if flags else [])
                + ([f"items {', '.join(refs)}"] if refs else [])
            )
            out.append(
                f"- {line['id']}: {line['text']}" + (f"  <{meta}>" if meta else "")
            )
    return "\n".join(out)


def layout_chars(layout: Dict[str, Any]) -> int:
    return sum(
        len(t["title"]) + sum(len(line["text"]) for line in t["lines"])
        for t in layout.get("topics", [])
    )


def used_items(layout: Dict[str, Any]) -> set:
    return {
        i
        for t in layout.get("topics", [])
        for line in t["lines"]
        for i in line["items"]
    }


# ---------------------------------------------------------------- .tex export

_TEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_MATH = re.compile(r"(\$\$.+?\$\$|\$[^$\n]+?\$)", re.DOTALL)


def _tex_text(text: str) -> str:
    """Markdown prose to LaTeX: specials escaped, **bold** and *italic* kept."""
    out = "".join(_TEX_SPECIALS.get(ch, ch) for ch in text)
    out = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", out)
    out = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\\emph{\1}", out)
    out = re.sub(r"`([^`]+)`", r"\\texttt{\1}", out)
    return out


def markdown_to_tex(text: str) -> str:
    """A line's Markdown to LaTeX; math between dollar signs is passed through."""
    parts = _MATH.split(text)
    return "".join(
        part if i % 2 else _tex_text(part) for i, part in enumerate(parts)
    ).replace("\n", r"\\ ")


def _cite_text(cites: List[Dict[str, Any]], labels: Dict[str, str]) -> str:
    out = []
    for c in cites:
        pages = (
            f"p.~{c['page_start']}"
            if c["page_start"] == c["page_end"]
            else f"pp.~{c['page_start']}--{c['page_end']}"
        )
        out.append(f"{_tex_text(labels.get(c['source'], ''))} {pages}".strip())
    return "; ".join(out)


def to_tex(
    layout: Dict[str, Any],
    options: SheetOptions,
    labels: Dict[str, str],
    citations: bool = False,
) -> str:
    """A standalone LaTeX document for the sheet (built from the layout, not by a model)."""
    paper = "a4paper" if options.paper == "a4" else "letterpaper"
    pt = font_pt(options.columns)
    lines = [
        r"\documentclass{article}",
        rf"\usepackage[{paper},margin=0.35in]{{geometry}}",
        r"\usepackage{amsmath,amssymb,multicol,xcolor}",
        r"\usepackage[T1]{fontenc}",
        r"\setlength{\parindent}{0pt}\setlength{\parskip}{1pt}",
        r"\setlength{\columnsep}{8pt}\setlength{\columnseprule}{0.2pt}",
        r"\pagestyle{empty}",
        r"\begin{document}",
        rf"\fontsize{{{pt:g}}}{{{pt * 1.15:.1f}}}\selectfont",
        rf"\begin{{center}}\textbf{{{_tex_text(layout.get('title') or 'Cheat sheet')}}}\end{{center}}",
        rf"\begin{{multicols*}}{{{options.columns}}}",
    ]
    for topic in layout.get("topics", []):
        lines.append(
            rf"\par\smallskip\colorbox{{black!10}}{{\parbox{{\dimexpr\linewidth-2\fboxsep}}{{\textbf{{{_tex_text(topic['title'])}}}}}}}\par"
        )
        for line in topic["lines"]:
            body = markdown_to_tex(line["text"])
            if citations and line.get("cites"):
                body += rf" {{\color{{black!50}}\tiny[{_cite_text(line['cites'], labels)}]}}"
            lines.append(body + r"\par")
    lines += [r"\end{multicols*}", r"\end{document}", ""]
    return "\n".join(lines)
