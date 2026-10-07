"""MCP server: the notebook's research tools for Claude Code, Claude Desktop and
other MCP clients (agentic RAG plan §4.4).

Served by the API at /mcp (streamable HTTP). Two ways to use it:

- `ask`: the built-in research agent answers with page citations.
- The agent's own primitives (list_documents, grep, search, outline, read,
  graph, view), scoped to a notebook, so the client's model can do the
  research itself; `view` returns the page as an image.

Every tool takes `notebook` (a notebook id or name; omitted = all notebooks).
Hosts other than localhost must be listed in OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS
(e.g. "100.120.164.122:*"), which keeps DNS-rebinding protection on.
"""

import base64
import os
from typing import Any, List, Literal, Optional, Union

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

from open_notebook.agent import tools as agent_tools
from open_notebook.agent.addresses import AddressError
from open_notebook.agent.scope import AgentScope, ToolError, load_scope
from open_notebook.database.repository import repo_query

INSTRUCTIONS = (
    "Research tools over the user's notebooks (lecture slides, papers, notes). Addresses like "
    "source:abc#p12-18 (pages), source:abc#s3 (section), source:abc/summary and note:xyz are "
    "taken and returned by every tool; cite them. Start with list_notebooks, then either `ask` "
    "for a cited answer from the built-in agent, or research yourself: list_documents, "
    "grep/search to locate, read or view to verify."
)


def _allowed_hosts() -> List[str]:
    extra = os.environ.get("OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS", "")
    return ["127.0.0.1:*", "localhost:*", "[::1]:*"] + [
        h.strip() for h in extra.split(",") if h.strip()
    ]


mcp = FastMCP(
    "Open Notebook (Brain)",
    instructions=INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts(),
        allowed_origins=[],
    ),
)


async def _notebook_id(notebook: Optional[str]) -> Optional[str]:
    if not notebook:
        return None
    if notebook.startswith("notebook:"):
        return notebook
    rows = await repo_query("SELECT id, name FROM notebook")
    wanted = notebook.strip().lower()
    for row in rows:
        if (row.get("name") or "").strip().lower() == wanted:
            return str(row["id"])
    names = ", ".join(repr(r.get("name")) for r in rows)
    raise ToolError(f"No notebook named {notebook!r}. Notebooks: {names}")


async def _scope(notebook: Optional[str]) -> AgentScope:
    from open_notebook.agent.graph import knowledge_base_scope

    notebook_id = await _notebook_id(notebook)
    sources, notes = await knowledge_base_scope([notebook_id] if notebook_id else [])
    return await load_scope(sources, notes, notebook_id)


async def _run(notebook: Optional[str], fn, **kwargs: Any) -> str:
    try:
        scope = await _scope(notebook)
        return await fn(scope, **kwargs)
    except (ToolError, AddressError) as e:
        return f"Error: {e}"


@mcp.tool()
async def list_notebooks() -> str:
    """The user's notebooks with their ids and document counts."""
    rows = await repo_query(
        "SELECT id, name, description, count(<-reference.in) AS sources, count(<-artifact.in) AS notes FROM notebook ORDER BY name"
    )
    if not rows:
        return "No notebooks."
    return "\n".join(
        f'- {r["id"]} "{r["name"]}": {r["sources"]} document(s), {r["notes"]} note(s)'
        + (f" — {r['description']}" if r.get("description") else "")
        for r in rows
    )


@mcp.tool()
async def ask(
    question: str,
    notebook: Optional[str] = None,
    effort: Literal["quick", "standard", "deep"] = "standard",
) -> str:
    """Answer a question with the notebook's research agent; the answer cites
    pages as [source:abc#p12]. Takes 10-60 s."""
    from langchain_core.messages import HumanMessage

    from open_notebook.agent.graph import get_ephemeral_agent_graph

    try:
        notebook_id = await _notebook_id(notebook)
    except ToolError as e:
        return f"Error: {e}"
    state: dict = {
        "messages": [HumanMessage(content=question)],
        "notebook_id": notebook_id,
        "effort": effort,
    }
    if not notebook_id:  # the whole knowledge base
        from open_notebook.agent.graph import knowledge_base_scope

        state["source_ids"], state["note_ids"] = await knowledge_base_scope([])
    result = await get_ephemeral_agent_graph().ainvoke(state)
    return str(result["messages"][-1].content)


@mcp.tool()
async def list_documents(
    notebook: Optional[str] = None,
    doc_type: Optional[str] = None,
    course: Optional[str] = None,
    sequence: Optional[int] = None,
    title_contains: Optional[str] = None,
    sort: str = "sequence",
) -> str:
    """The catalog of documents: type, course, number in series, page count, summary line."""
    return await _run(
        notebook,
        agent_tools.tool_list,
        doc_type=doc_type,
        course=course,
        sequence=sequence,
        title_contains=title_contains,
        sort=sort,
    )


@mcp.tool()
async def grep(
    pattern: str,
    notebook: Optional[str] = None,
    addresses: Optional[List[str]] = None,
) -> str:
    """Exhaustive case-insensitive regex matches with per-document counts and page numbers."""
    return await _run(
        notebook, agent_tools.tool_grep, pattern=pattern, addresses=addresses
    )


@mcp.tool()
async def search(
    query: str = "",
    notebook: Optional[str] = None,
    level: Literal["passage", "section", "document", "page"] = "passage",
    addresses: Optional[List[str]] = None,
    like: Optional[str] = None,
    limit: int = 8,
) -> str:
    """Meaning-based search. level=passage for evidence; section/document for topics;
    page for page images by appearance. like=<address> finds similar material."""
    return await _run(
        notebook,
        agent_tools.tool_search,
        query=query,
        level=level,
        addresses=addresses,
        like=like,
        limit=limit,
    )


@mcp.tool()
async def outline(source: str, notebook: Optional[str] = None) -> str:
    """A document's metadata and sections with page ranges and one-line summaries."""
    return await _run(notebook, agent_tools.tool_outline, source=source)


@mcp.tool()
async def read(address: str, notebook: Optional[str] = None, limit: int = 6000) -> str:
    """Read pages (source:abc#p12-18), a section (#s3), a summary (/summary) or a note."""
    return await _run(notebook, agent_tools.tool_read, address=address, limit=limit)


@mcp.tool()
async def graph(
    concept: Optional[str] = None, notebook: Optional[str] = None, limit: int = 15
) -> str:
    """The concept graph: where a concept appears (pages) and its relations; without a
    concept, the concepts shared by the most documents."""
    return await _run(notebook, agent_tools.tool_graph, concept=concept, limit=limit)


@mcp.tool(structured_output=False)
async def view(address: str, notebook: Optional[str] = None) -> List[Union[str, Image]]:
    """Look at a PDF page (source:abc#p12) or image source as a picture."""
    try:
        scope = await _scope(notebook)
        text = await agent_tools.tool_view(scope, address=address)
    except (ToolError, AddressError) as e:
        return [f"Error: {e}"]
    images: List[Union[str, Image]] = [text]
    for item in scope.pending_images:
        header, _, data = item["data_url"].partition(",")
        fmt = header.removeprefix("data:image/").split(";")[0] or "png"
        images.append(Image(data=base64.b64decode(data), format=fmt))
    return images
