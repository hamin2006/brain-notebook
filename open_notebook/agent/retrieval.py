"""Retrieval backends for the agent tools, all limited to an AgentScope.

- passages: chunk-level hybrid search (BM25 + vector, reciprocal rank fusion)
  over source chunks and notes
- sections: vector search over embedded section summaries, plus keyword overlap
- documents: vector search over "Document Summary" insights, plus keyword overlap
  with titles, metadata and topics
- `like`: the stored embedding of an address, for "more like this"

Vector similarity is brute force over the scope, which is fine at notebook
scale (thousands of chunks).
"""

import re
from typing import Any, Dict, List, Optional

from open_notebook.agent.addresses import Address
from open_notebook.agent.scope import AgentScope, per_source
from open_notebook.database.repository import ensure_record_id, repo_query

RRF_K = 60
DOCUMENT_SUMMARY = "Document Summary"
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "what", "how", "does", "are", "from",
    "about", "into", "which", "when", "where", "who", "why", "lecture", "slide", "slides",
}  # fmt: skip


def terms(text: str) -> List[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 2 and t not in _STOPWORDS
    ]


def fuse(rankings: List[List[Dict[str, Any]]], limit: int) -> List[Dict[str, Any]]:
    """Reciprocal rank fusion over ranked hit lists, keyed by hit id."""
    scores: Dict[str, float] = {}
    hits: Dict[str, Dict[str, Any]] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking):
            key = str(hit["id"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            hits.setdefault(key, hit)
    ordered = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [hits[k] for k in ordered[:limit]]


def keyword_rank(
    items: List[Dict[str, Any]], query: str, text_of
) -> List[Dict[str, Any]]:
    """Items that share query terms, most shared first (a lexical leg without an index)."""
    wanted = set(terms(query))
    if not wanted:
        return []
    scored = [(len(wanted & set(terms(text_of(item)))), item) for item in items]
    return [item for score, item in sorted(scored, key=lambda s: -s[0]) if score]


def _ids(scope: AgentScope, only: Optional[List[str]] = None):
    source_ids = [s for s in scope.sources if not only or s in only]
    note_ids = [n for n in scope.notes if not only or n in only]
    return [ensure_record_id(s) for s in source_ids], [
        ensure_record_id(n) for n in note_ids
    ]


async def passage_hits(
    scope: AgentScope,
    query: str,
    embed: Optional[List[float]],
    k: int,
    only: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    sources, notes = _ids(scope, only)
    rankings: List[List[Dict[str, Any]]] = []
    keyword = bool(query.strip())  # like= searches have no text, only a vector
    if sources and keyword:
        rankings.append(
            await repo_query(
                """
                SELECT id, source, order, page_start, page_end, content, search::score(1) AS score
                FROM source_embedding WHERE source IN $sources AND content @1@ $q
                ORDER BY score DESC LIMIT $k
                """,
                {"sources": sources, "q": query, "k": k},
            )
        )
    if sources and embed is not None:
        rankings.append(
            await repo_query(
                """
                    SELECT id, source, order, page_start, page_end, content,
                        vector::similarity::cosine(embedding, $embed) AS score
                    FROM source_embedding WHERE source IN $sources
                    ORDER BY score DESC LIMIT $k
                    """,
                {"sources": sources, "embed": embed, "k": k},
            )
        )
    if notes and keyword:
        rankings.append(
            await repo_query(
                """
                SELECT id, title, content, search::score(1) AS score
                FROM note WHERE id IN $notes AND content @1@ $q
                ORDER BY score DESC LIMIT $k
                """,
                {"notes": notes, "q": query, "k": k},
            )
        )
    if notes and embed is not None:
        rankings.append(
            await repo_query(
                """
                    SELECT id, title, content, vector::similarity::cosine(embedding, $embed) AS score
                    FROM note WHERE id IN $notes AND embedding != NONE
                    ORDER BY score DESC LIMIT $k
                    """,
                {"notes": notes, "embed": embed, "k": k},
            )
        )
    return fuse(rankings, k)


async def section_rows(
    scope: AgentScope, only: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    sources, _ = _ids(scope, only)
    if not sources:
        return []
    return await per_source(
        """
        SELECT id, source, index, title, page_start, page_end, summary, embedding
        FROM source_section WHERE source = $s ORDER BY index
        """,
        sources,
    )


async def section_hits(
    scope: AgentScope,
    query: str,
    embed: Optional[List[float]],
    k: int,
    only: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    rows = await section_rows(scope, only)
    rankings = [keyword_rank(rows, query, lambda r: f"{r['title']} {r['summary']}")]
    if embed is not None:
        rankings.append(_by_similarity(rows, embed))
    return fuse(rankings, k)


async def document_rows(scope: AgentScope) -> List[Dict[str, Any]]:
    """One row per scoped source: its id, label, metadata and summary embedding/text."""
    sources, _ = _ids(scope)
    if not sources:
        return []
    insights = await repo_query(
        """
        SELECT source, content, embedding FROM source_insight
        WHERE source IN $sources AND insight_type = $type
        """,
        {"sources": sources, "type": DOCUMENT_SUMMARY},
    )
    by_source = {str(i["source"]): i for i in insights}
    rows = []
    for sid, src in scope.sources.items():
        insight = by_source.get(sid, {})
        meta = src.metadata or {}
        rows.append(
            {
                "id": sid,
                "label": src.label,
                "text": " ".join(
                    [
                        src.label,
                        src.title,
                        str(meta.get("course") or ""),
                        " ".join(meta.get("topics") or []),
                    ]
                ),
                "summary": insight.get("content") or "",
                "embedding": insight.get("embedding"),
            }
        )
    return rows


async def document_hits(
    scope: AgentScope,
    query: str,
    embed: Optional[List[float]],
    k: int,
    exclude: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows = [r for r in await document_rows(scope) if r["id"] != exclude]
    rankings = (
        [keyword_rank(rows, query, lambda r: f"{r['text']} {r['summary']}")]
        if query
        else []
    )
    if embed is not None:
        rankings.append(_by_similarity(rows, embed))
    return fuse(rankings, k)


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _by_similarity(
    rows: List[Dict[str, Any]], embed: List[float]
) -> List[Dict[str, Any]]:
    scored = [(_cosine(r["embedding"], embed), r) for r in rows if r.get("embedding")]
    return [r for _, r in sorted(scored, key=lambda s: -s[0])]


def _first_vector(rows: List[Any]) -> Optional[List[float]]:
    value: Any = rows[0] if rows else None
    return value or None


async def embedding_of(address: Address, scope: AgentScope) -> Optional[List[float]]:
    """The stored embedding behind an address, for `like=` searches."""
    if address.table != "source":
        rows = await repo_query(
            "SELECT VALUE embedding FROM $id",
            {"id": ensure_record_id(address.record_id)},
        )
        return _first_vector(rows)
    if address.section is not None:
        rows = await repo_query(
            "SELECT VALUE embedding FROM source_section WHERE source = $s AND index = $i",
            {"s": ensure_record_id(address.record_id), "i": address.section},
        )
        return _first_vector(rows)
    if address.page_start is not None:
        vectors = await repo_query(
            """
            SELECT VALUE embedding FROM source_embedding
            WHERE source = $s AND page_start <= $end AND page_end >= $start
            """,
            {
                "s": ensure_record_id(address.record_id),
                "start": address.page_start,
                "end": address.page_end,
            },
        )
        vectors = [v for v in vectors if v]
        if not vectors:
            return None
        return [sum(col) / len(vectors) for col in zip(*vectors)]
    doc = next(
        (r for r in await document_rows(scope) if r["id"] == address.record_id), None
    )
    return doc["embedding"] if doc else None


async def fetch_pages(source_id: str, start: int, end: int) -> List[Dict[str, Any]]:
    return await repo_query(
        """
        SELECT page, text, caption FROM source_page
        WHERE source = $s AND page >= $start AND page <= $end ORDER BY page
        """,
        {"s": ensure_record_id(source_id), "start": start, "end": end},
    )


async def all_pages(source_ids: List[str]) -> List[Dict[str, Any]]:
    if not source_ids:
        return []
    return await per_source(
        "SELECT source, page, text, caption FROM source_page WHERE source = $s ORDER BY page",
        [ensure_record_id(s) for s in source_ids],
    )


async def sections_of(source_id: str) -> List[Dict[str, Any]]:
    return await repo_query(
        "SELECT index, title, page_start, page_end, summary FROM source_section WHERE source = $s ORDER BY index",
        {"s": ensure_record_id(source_id)},
    )


async def document_summary(source_id: str) -> Optional[str]:
    rows = await repo_query(
        "SELECT VALUE content FROM source_insight WHERE source = $s AND insight_type = $type",
        {"s": ensure_record_id(source_id), "type": DOCUMENT_SUMMARY},
    )
    value: Any = rows[0] if rows else None
    return value
