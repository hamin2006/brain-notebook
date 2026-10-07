"""The agent's tools: general primitives over a notebook, not task-shaped helpers.

    list     the catalog of documents (filter, sort)         ~ ls
    grep     exhaustive exact/regex matches with pages        ~ grep
    search   meaning-based search at passage, section or document level, or visual
             search over rendered pages (level=page); like=<address>
    outline  a document's sections with page ranges
    read     read an address (pages, section, chunk, summary, note), capped
    view     look at a page or image as a picture

Every tool takes and returns addresses (see addresses.py) and returns plain text
the model reads. Mistakes in arguments come back as an "Error: ..." the model
can act on; they never end the turn.
"""

import ast
import asyncio
import base64
import json
import math
import re
from typing import Annotated, Any, Callable, Dict, List, Optional

from langchain_core.tools import StructuredTool
from loguru import logger
from pydantic import BaseModel, BeforeValidator, Field

from open_notebook.agent import retrieval
from open_notebook.agent.addresses import Address, AddressError, pages, parse_address
from open_notebook.agent.scope import AgentScope, ToolError
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.utils.pdf_pages import render_page_png

SNIPPET = 220
READ_LIMIT = 8000
MAX_GREP_LISTED = 40


def _snippet(text: str, n: int = SNIPPET) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= n else flat[:n] + "…"


def _strip_chunk_header(content: str) -> str:
    """Chunks start with "<title> — pp. N–M"; the address already says that."""
    first, _, rest = content.partition("\n")
    return rest if " — p" in first and rest else content


def _page_text(row: Dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in (
            row.get("text"),
            row.get("caption") and f"[Image] {row['caption']}",
        )
        if part
    )


def _hit_address(hit: Dict[str, Any]) -> str:
    if hit.get("source") is None:
        return str(hit["id"])  # a note
    sid = str(hit["source"])
    if hit.get("page_start") is not None:
        return str(pages(sid, hit["page_start"], hit.get("page_end")))
    return f"{sid}#c{hit.get('order', 0)}"


# ---------------------------------------------------------------- list
async def tool_list(
    scope: AgentScope,
    doc_type: Optional[str] = None,
    course: Optional[str] = None,
    sequence: Optional[int] = None,
    title_contains: Optional[str] = None,
    sort: str = "sequence",
) -> str:
    docs = await retrieval.document_rows(scope)
    rows = []
    for doc in docs:
        src = scope.sources[doc["id"]]
        meta = src.metadata or {}
        if doc_type and (meta.get("doc_type") or "").lower() != doc_type.lower():
            continue
        if course and course.lower() not in (meta.get("course") or "").lower():
            continue
        if sequence is not None and meta.get("sequence") != sequence:
            continue
        if (
            title_contains
            and title_contains.lower() not in f"{src.label} {src.title}".lower()
        ):
            continue
        rows.append((src, meta, doc["summary"]))
    keys: Dict[str, Callable[[Any], Any]] = {
        "sequence": lambda r: (
            r[1].get("sequence") is None,
            r[1].get("sequence") or 0,
            r[0].label,
        ),
        "title": lambda r: r[0].label.lower(),
        "pages": lambda r: -(r[1].get("page_count") or r[0].page_count),
        "date": lambda r: str(r[1].get("date") or ""),
    }
    rows.sort(key=keys.get(sort, keys["sequence"]))
    notes = (
        []
        if any((doc_type, course, sequence, title_contains))
        else list(scope.notes.values())
    )
    if not rows and not notes:
        return "No documents match. Call list with no filters to see everything in context."
    lines = [f"{len(rows)} document(s):"]
    for src, meta, summary in rows:
        bits = [meta.get("doc_type") or src.kind]
        if meta.get("course"):
            bits.append(
                f"{meta['course']}"
                + (f" #{meta['sequence']}" if meta.get("sequence") is not None else "")
            )
        count = meta.get("page_count") or src.page_count
        if count:
            bits.append(f"{count} pages")
        if meta.get("date"):
            bits.append(str(meta["date"]))
        line = f'- {src.id} "{src.label}" ({", ".join(bits)})'
        if summary:
            line += f"\n  {_snippet(summary, 180)}"
        lines.append(line)
    if notes:
        lines.append(f"{len(notes)} note(s):")
        lines += [f'- {n.id} "{n.title}"' for n in notes]
    return "\n".join(lines)


# ---------------------------------------------------------------- grep
async def tool_grep(
    scope: AgentScope,
    pattern: str,
    addresses: Optional[List[str]] = None,
    max_listed: int = MAX_GREP_LISTED,
) -> str:
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise ToolError(f"Invalid regex: {e}")
    only = {parse_address(a).record_id for a in addresses} if addresses else None
    source_ids = [s for s in scope.sources if not only or s in only]
    per_doc: Dict[str, List[str]] = {}
    listed: List[str] = []

    for row in await retrieval.all_pages(source_ids):
        text = _page_text(row)
        found = list(regex.finditer(text))
        if not found:
            continue
        sid = str(row["source"])
        per_doc.setdefault(sid, []).extend([str(row["page"])] * len(found))
        if len(listed) < max_listed:
            m = found[0]
            context = text[max(0, m.start() - 70) : m.end() + 70]
            listed.append(f"{pages(sid, row['page'])}: …{_snippet(context, 180)}…")

    # Sources without pages (web pages, text): search their chunks instead.
    unpaged = [s for s in source_ids if scope.sources[s].page_count == 0]
    if unpaged:
        chunks = await repo_query(
            "SELECT source, order, content FROM source_embedding WHERE source IN $ids ORDER BY source, order",
            {"ids": [ensure_record_id(s) for s in unpaged]},
        )
        for row in chunks:
            found = list(regex.finditer(row["content"]))
            if found:
                sid = str(row["source"])
                per_doc.setdefault(sid, []).extend([f"c{row['order']}"] * len(found))
                if len(listed) < max_listed:
                    listed.append(
                        f"{sid}#c{row['order']}: {_snippet(row['content'], 180)}"
                    )
    note_ids = [n for n in scope.notes if not only or n in only]
    if note_ids:
        for row in await repo_query(
            "SELECT id, content FROM note WHERE id IN $ids",
            {"ids": [ensure_record_id(n) for n in note_ids]},
        ):
            found = list(regex.finditer(row.get("content") or ""))
            if found:
                per_doc.setdefault(str(row["id"]), []).extend(["note"] * len(found))
                if len(listed) < max_listed:
                    listed.append(f"{row['id']}: {_snippet(row['content'], 180)}")

    if not per_doc:
        return f"No matches for /{pattern}/ in {len(source_ids) + len(note_ids)} document(s)."
    total = sum(len(v) for v in per_doc.values())
    lines = [f"{total} match(es) for /{pattern}/ in {len(per_doc)} document(s):"]
    for sid, where in per_doc.items():
        label = (
            scope.sources[sid].label if sid in scope.sources else scope.notes[sid].title
        )
        distinct = list(dict.fromkeys(where))
        shown = ", ".join(f"p{w}" if w.isdigit() else w for w in distinct[:25])
        more = f" (+{len(distinct) - 25} more)" if len(distinct) > 25 else ""
        lines.append(f'- {sid} "{label}": {len(where)} match(es) at {shown}{more}')
    lines.append("First matches:")
    lines += listed
    return "\n".join(lines)


# ---------------------------------------------------------------- search
async def tool_search(
    scope: AgentScope,
    query: str = "",
    level: str = "passage",
    addresses: Optional[List[str]] = None,
    like: Optional[str] = None,
    limit: int = 8,
    image: Optional[str] = None,
) -> str:
    if image:
        level = "page"  # an image can only be compared with page images
    if not query.strip() and not like and not image:
        raise ToolError("Give a query, or like=<address> to find similar material.")
    if level not in ("passage", "section", "document", "page"):
        raise ToolError("level must be passage, section, document or page.")
    limit = max(1, min(limit, 15))
    only = [parse_address(a).record_id for a in addresses] if addresses else None
    if level == "page":
        return await _page_search(scope, query, like, limit, only, image)

    embed: Optional[List[float]] = None
    like_address: Optional[Address] = None
    if like:
        like_address = parse_address(like)
        embed = await retrieval.embedding_of(like_address, scope)
        if embed is None:
            raise ToolError(
                f"{like} has no stored embedding yet; search with a query instead."
            )
    elif query.strip():
        from open_notebook.utils.embedding import generate_embedding

        try:
            embed = await generate_embedding(query)
        except Exception as e:  # no embedding model / provider down: keyword legs only
            logger.warning(f"Agent search without vectors: {e}")

    text_query = query if query.strip() else ""
    if level == "document":
        hits = await retrieval.document_hits(
            scope,
            text_query,
            embed,
            limit,
            exclude=like_address.record_id if like_address else None,
        )
        if not hits:
            return "No matching documents."
        lines = [f"Documents{' like ' + like if like else ''} (best first):"]
        lines += [
            f'- {h["id"]} "{h["label"]}": {_snippet(h["summary"], 200)}' for h in hits
        ]
        return "\n".join(lines)

    candidates = max(limit * 3, retrieval.RERANK_CANDIDATES)
    if level == "section":
        hits = await retrieval.section_hits(
            scope, text_query, embed, candidates, only=only
        )
        if like_address and like_address.section is not None:
            hits = [
                h
                for h in hits
                if not (
                    str(h["source"]) == like_address.record_id
                    and h["index"] == like_address.section
                )
            ]
        hits = await retrieval.rerank(
            text_query, hits, lambda h: f"{h['title']}\n{h['summary']}", limit
        )
        if not hits:
            return "No matching sections (documents may not be analyzed yet; try level=passage)."
        lines = ["Sections (best first):"]
        for h in hits:
            sid = str(h["source"])
            label = scope.sources[sid].label if sid in scope.sources else sid
            lines.append(
                f"- {sid}#s{h['index']} = {pages(sid, h['page_start'], h['page_end'])} "
                f'"{label}" § {h["title"]}: {_snippet(h["summary"], 200)}'
            )
        return "\n".join(lines)

    hits = await retrieval.passage_hits(scope, text_query, embed, candidates, only=only)
    if like_address:
        hits = [h for h in hits if _hit_address(h) != str(like_address)]
    hits = await retrieval.rerank(
        text_query, hits, lambda h: _strip_chunk_header(h["content"]), limit
    )
    if not hits:
        return f"No matches for {query!r}. Try other words, grep for exact terms, or level=section."
    lines = ["Passages (best first):"]
    for h in hits:
        if h.get("source") is not None:
            sid = str(h["source"])
            label = scope.sources[sid].label if sid in scope.sources else sid
            lines.append(
                f'- {_hit_address(h)} "{label}": {_snippet(_strip_chunk_header(h["content"]))}'
            )
        else:
            lines.append(
                f'- {h["id"]} (note "{h.get("title") or ""}"): {_snippet(h["content"])}'
            )
    return "\n".join(lines)


async def _page_search(
    scope: AgentScope,
    query: str,
    like: Optional[str],
    limit: int,
    only: Optional[List[str]],
    image: Optional[str] = None,
) -> str:
    """Visual search: pages whose rendered image matches a description, looks
    like another page, or looks like an image the user attached."""
    model = await retrieval.page_embedding_model()
    if not model:
        raise ToolError(
            "Visual page search is turned off (no page embedding model). Use level=passage."
        )
    like_address = parse_address(like) if like else None
    if like_address:
        embed = await retrieval.page_image_embedding(like_address)
        if embed is None:
            raise ToolError(
                f"{like} has no page image embedding; give a page address like source:abc#p12, "
                "or search with a description."
            )
    else:
        from open_notebook.ai.openrouter import (
            embed_multimodal,
            image_input,
            text_input,
        )

        item = image_input(scope.attachment(image)) if image else text_input(query)
        try:
            [embed] = await embed_multimodal(model, [item])
        except Exception as e:
            raise ToolError(f"Visual search failed ({e}); use level=passage.")
    hits = await retrieval.page_hits(scope, embed, limit + 1, only=only)
    if like_address:
        hits = [
            h
            for h in hits
            if not (
                str(h["source"]) == like_address.record_id
                and h["page_start"] <= (like_address.page_start or 0) <= h["page_end"]
            )
        ]
    hits = hits[:limit]
    if not hits:
        return "No page images are indexed in scope yet; use level=passage."
    target = like or image
    lines = [f"Pages{' like ' + target if target else ''} (by appearance, best first):"]
    for h in hits:
        sid = str(h["source"])
        label = scope.sources[sid].label if sid in scope.sources else sid
        what = h.get("caption") or h.get("text") or ""
        lines.append(
            f'- {pages(sid, h["page_start"], h["page_end"])} "{label}": {_snippet(what, 160)}'
        )
    lines.append("View a page to see it.")
    return "\n".join(lines)


# ---------------------------------------------------------------- outline
async def _outline_text(scope: AgentScope, source_id: str) -> str:
    src = scope.source(source_id)
    meta = src.metadata or {}
    head = [f'{src.id} "{src.label}"']
    details = {
        k: meta.get(k)
        for k in ("doc_type", "course", "sequence", "date", "page_count")
        if meta.get(k)
    }
    if details:
        head.append(", ".join(f"{k}: {v}" for k, v in details.items()))
    if meta.get("topics"):
        head.append("topics: " + "; ".join(meta["topics"]))
    sections = await retrieval.sections_of(source_id)
    if not sections:
        count = src.page_count
        hint = (
            f"{count} pages; read page ranges like {src.id}#p1-10."
            if count
            else f"read {src.id}#c0 onward."
        )
        return "\n".join(head + [f"No outline yet. {hint}"])
    lines = head + ["Sections:"]
    for s in sections:
        first_sentence = re.split(r"(?<=[.!?])\s", s["summary"].strip(), maxsplit=1)[0]
        lines.append(
            f"- {src.id}#s{s['index']} = {pages(src.id, s['page_start'], s['page_end'])} "
            f"{s['title']}: {_snippet(first_sentence, 160)}"
        )
    return "\n".join(lines)


async def tool_outline(scope: AgentScope, source: str) -> str:
    return await _outline_text(scope, parse_address(source).record_id)


# ---------------------------------------------------------------- read
async def tool_read(scope: AgentScope, address: str, limit: int = READ_LIMIT) -> str:
    addr = parse_address(address)
    limit = max(1000, min(limit, 20000))

    if addr.table == "note":
        scope.note(addr.record_id)
        rows = await repo_query(
            "SELECT title, content FROM $id", {"id": ensure_record_id(addr.record_id)}
        )
        return (
            f'{addr} "{rows[0].get("title")}":\n{rows[0].get("content")}'
            if rows
            else f"{addr} not found."
        )
    if addr.table == "source_insight":
        rows = await repo_query(
            "SELECT insight_type, content, source FROM $id",
            {"id": ensure_record_id(addr.record_id)},
        )
        if not rows or str(rows[0]["source"]) not in scope.sources:
            raise ToolError(f"{addr} is not an insight of a source in context.")
        return f"{addr} ({rows[0]['insight_type']}):\n{rows[0]['content']}"

    src = scope.source(addr.record_id)
    if addr.layer == "summary":
        summary = await retrieval.document_summary(src.id)
        return (
            f"{addr}:\n{summary}"
            if summary
            else f"{src.id} has no summary yet; use outline or read page ranges."
        )
    if addr.layer == "outline":
        return await _outline_text(scope, src.id)
    if addr.is_document:
        # Never dump a whole file: give the map, and let the agent pick what to read.
        summary = await retrieval.document_summary(src.id)
        parts = [await _outline_text(scope, src.id)]
        if summary:
            parts.append(f"Summary ({src.id}/summary):\n{_snippet(summary, 1500)}")
        parts.append("Read a section (#sN) or page range (#pN-M) for the full text.")
        return "\n\n".join(parts)
    if addr.chunk is not None:
        rows = await repo_query(
            """
            SELECT order, content FROM source_embedding
            WHERE source = $s AND order >= $lo AND order <= $hi ORDER BY order
            """,
            {"s": ensure_record_id(src.id), "lo": addr.chunk - 1, "hi": addr.chunk + 1},
        )
        if not rows:
            raise ToolError(f"{src.id} has no chunk {addr.chunk}.")
        return "\n\n".join(
            f"--- {src.id}#c{r['order']} ---\n{r['content']}" for r in rows
        )[:limit]

    if addr.section is not None:
        section = next(
            (
                s
                for s in await retrieval.sections_of(src.id)
                if s["index"] == addr.section
            ),
            None,
        )
        if not section:
            raise ToolError(
                f"{src.id} has no section {addr.section}; call outline({src.id})."
            )
        start, end = section["page_start"], section["page_end"]
        header = f"{addr} = {pages(src.id, start, end)} § {section['title']}\nSection summary: {section['summary']}\n"
    else:
        start, end = addr.page_start or 1, addr.page_end or addr.page_start or 1
        if src.page_count and start > src.page_count:
            raise ToolError(f"{src.id} has {src.page_count} pages.")
        header = f'{pages(src.id, start, end)} "{src.label}"\n'

    rows = await retrieval.fetch_pages(src.id, start, end)
    if not rows:
        return header + "(no text on these pages; try view to look at them)"
    body = ""
    for row in rows:
        block = (
            f"\n--- p{row['page']} ---\n{_page_text(row) or '(no text; use view)'}\n"
        )
        if len(header) + len(body) + len(block) > limit and body:
            return (
                header
                + body
                + f"\n[Truncated. Continue with read({pages(src.id, row['page'], end)}).]"
            )
        body += block
    return header + body


# ---------------------------------------------------------------- view
async def tool_view(scope: AgentScope, address: str) -> str:
    addr = parse_address(address)
    src = scope.source(addr.record_id)
    if src.kind not in ("pdf", "image"):
        return f"{src.id} is a {src.kind} source with nothing to look at; use read."
    if not src.has_original:
        return (
            f"The original file of {src.id} is no longer stored, so it can't be viewed."
        )
    if src.kind == "pdf":
        page = addr.page_start
        if page is None and addr.section is not None:
            section = next(
                (
                    s
                    for s in await retrieval.sections_of(src.id)
                    if s["index"] == addr.section
                ),
                None,
            )
            page = section["page_start"] if section else None
        if page is None:
            raise ToolError(f"view needs a page, e.g. {src.id}#p12.")
        png = await asyncio.to_thread(render_page_png, str(src.file_path), page)
        label = str(pages(src.id, page))
    else:
        png = await asyncio.to_thread(_image_png, str(src.file_path))
        label = src.id
    scope.pending_images.append(
        {
            "caption": f'{label} "{src.label}"',
            "data_url": "data:image/png;base64," + base64.b64encode(png).decode(),
        }
    )
    return f"Showing {label}. The image follows in the next message."


def _image_png(path: str, max_side: int = 1400) -> bytes:
    import io

    from PIL import Image

    image = Image.open(path)
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------- note
async def tool_note(scope: AgentScope, title: str, content: str) -> str:
    from open_notebook.domain.notebook import Note

    if not scope.notebook_id:
        raise ToolError("There is no notebook to save a note into.")
    if not content.strip():
        raise ToolError("The note needs content.")
    note = Note(title=title.strip() or "Untitled note", content=content, note_type="ai")
    await note.save()
    await note.add_to_notebook(scope.notebook_id)
    return f'Saved as {note.id} "{note.title}" in the notebook.'


# ---------------------------------------------------------------- calculate
_MATH_NAMES = {
    name: getattr(math, name)
    for name in (
        "sqrt", "exp", "log", "log2", "log10", "sin", "cos", "tan", "floor", "ceil",
        "pi", "e", "inf",
    )
}  # fmt: skip
_MATH_NAMES.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum})
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
    ast.Call, ast.Tuple, ast.List, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
)  # fmt: skip


MAX_EXPONENT = 1000


def evaluate(expression: str) -> float:
    """Evaluate arithmetic safely: numbers, + - * / // % **, and math functions only.

    Model-written input, so: numeric constants only (no strings to multiply into
    huge objects), exponents must be literal numbers <= MAX_EXPONENT (no 9**9**9),
    no attribute access, comprehensions or lambdas.
    """
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ToolError(f"Not allowed in an expression: {type(node).__name__}")
        if isinstance(node, ast.Constant) and (
            isinstance(node.value, bool) or not isinstance(node.value, (int, float))
        ):
            raise ToolError("Only numbers are allowed as constants.")
        if isinstance(node, ast.Name) and node.id not in _MATH_NAMES:
            raise ToolError(
                f"Unknown name {node.id!r}. Available: {', '.join(sorted(_MATH_NAMES))}"
            )
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise ToolError("Only plain function calls like sqrt(2) are allowed.")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = node.right
            if isinstance(exponent, ast.UnaryOp) and isinstance(
                exponent.operand, ast.Constant
            ):
                exponent = exponent.operand
            value = exponent.value if isinstance(exponent, ast.Constant) else None
            if not (isinstance(value, (int, float)) and abs(value) <= MAX_EXPONENT):
                raise ToolError(
                    f"Exponents must be literal numbers up to {MAX_EXPONENT}."
                )
    return eval(
        compile(tree, "<calc>", "eval"), {"__builtins__": {}}, dict(_MATH_NAMES)
    )


async def tool_calculate(scope: AgentScope, expression: str) -> str:
    try:
        value = evaluate(expression)
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"Could not evaluate {expression!r}: {e}")
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        value = int(value)
    return (
        f"{expression} = {value:,}"
        if isinstance(value, int)
        else f"{expression} = {value}"
    )


# ---------------------------------------------------------------- bindings
def _as_list(value: Any) -> Any:
    """Some models send a list argument as a string: '["source:a", "source:b"]',
    'source:a, source:b' or a single address. Accept those as the list they mean."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("["):
        try:
            return json.loads(text)
        except ValueError:
            text = text.strip("[]")
    return [part.strip().strip("'\"") for part in text.split(",") if part.strip()]


# A list of addresses that also accepts the string forms above.
AddressList = Annotated[List[str], BeforeValidator(_as_list)]


class ListArgs(BaseModel):
    doc_type: Optional[str] = Field(None, description="e.g. lecture, paper, notes")
    course: Optional[str] = Field(None, description="Course or series name (substring)")
    sequence: Optional[int] = Field(
        None, description="Number in the series, e.g. 4 for Lecture 4"
    )
    title_contains: Optional[str] = None
    sort: str = Field("sequence", description="sequence, title, pages or date")


class GrepArgs(BaseModel):
    pattern: str = Field(
        description="Case-insensitive regex, e.g. 'adam|rmsprop' or 'dropout'"
    )
    addresses: Optional[AddressList] = Field(
        None, description="Limit to these documents"
    )


class SearchArgs(BaseModel):
    query: str = Field("", description="What to look for, in words")
    level: str = Field(
        "passage",
        description="passage, section, document, or page (visual search over page images)",
    )
    addresses: Optional[AddressList] = Field(
        None, description="Limit to these documents"
    )
    like: Optional[str] = Field(
        None, description="Find material similar to this address instead of a query"
    )
    limit: int = Field(8, description="1-15 results")
    image: Optional[str] = Field(
        None,
        description="attachment:N, an image the user attached: finds pages that look like it",
    )


class OutlineArgs(BaseModel):
    source: str = Field(description="Document address, e.g. source:abc")


class ReadArgs(BaseModel):
    address: str = Field(
        description="e.g. source:abc#p12-18, source:abc#s3, source:abc/summary, note:xyz"
    )
    limit: int = Field(READ_LIMIT, description="Max characters to return (1000-20000)")


class ViewArgs(BaseModel):
    address: str = Field(description="A page (source:abc#p12) or an image source")


class NoteArgs(BaseModel):
    title: str = Field(description="Short title")
    content: str = Field(description="Markdown content, with citations")


class CalculateArgs(BaseModel):
    expression: str = Field(
        description="Arithmetic, e.g. (32 - 5 + 2*2)/1 + 1 or 7*7*512*4096"
    )


TOOL_SPECS = [
    (
        "list",
        tool_list,
        ListArgs,
        "The catalog of documents in context, with type, course, number in series, page count and a summary line. "
        "Use it to resolve references like 'the 4th lecture' or 'the longest paper'.",
    ),
    (
        "grep",
        tool_grep,
        GrepArgs,
        "Exhaustive exact/regex matches across documents, with counts per document and page numbers. "
        "Use it to find every mention of a term (search is top-k and misses some).",
    ),
    (
        "search",
        tool_search,
        SearchArgs,
        "Meaning-based search. level=passage for evidence, section or document for topics and related material; "
        "level=page searches page images by appearance (diagrams, charts, figures, slide layouts: describe what "
        "it looks like). like=<address> finds material similar to a page, section or document "
        "(with level=page: pages that look like that page).",
    ),
    (
        "outline",
        tool_outline,
        OutlineArgs,
        "A document's metadata and sections with page ranges and one-line summaries.",
    ),
    (
        "read",
        tool_read,
        ReadArgs,
        "Read text at an address: a page range, a section, a chunk, a stored summary or a note. "
        "Search results locate evidence; read it before relying on it.",
    ),
    (
        "view",
        tool_view,
        ViewArgs,
        "Look at a PDF page or image source as a picture. Use it when the answer depends on a diagram, chart, "
        "table layout or equation the text may have lost.",
    ),
    (
        "note",
        tool_note,
        NoteArgs,
        "Save a note into the notebook. Only when the user asks you to save or remember something.",
    ),
    (
        "calculate",
        tool_calculate,
        CalculateArgs,
        "Exact arithmetic (+ - * / // % **, sqrt, log, exp, floor, ceil...). Use it instead of computing in your head.",
    ),
]


def build_tools(scope: AgentScope) -> List[StructuredTool]:
    """LangChain tools bound to one turn's scope."""

    def bind(name: str, fn, schema, description: str) -> StructuredTool:
        async def call(**kwargs):
            try:
                return await fn(scope, **kwargs)
            except (ToolError, AddressError) as e:
                return f"Error: {e}"
            except Exception as e:
                logger.exception(f"Agent tool {name} failed")
                return (
                    f"Error: {name} failed ({type(e).__name__}). Try another approach."
                )

        return StructuredTool.from_function(
            coroutine=call, name=name, description=description, args_schema=schema
        )

    return [bind(*spec[:2], spec[2], spec[3]) for spec in TOOL_SPECS]
