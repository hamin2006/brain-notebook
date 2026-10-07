"""Retrieval backends for the agent tools, all limited to an AgentScope.

- passages: chunk-level hybrid search (BM25 + vector, reciprocal rank fusion)
  over source chunks and notes
- sections: vector search over embedded section summaries, plus keyword overlap
- documents: vector search over "Document Summary" insights, plus keyword overlap
  with titles, metadata and topics
- `like`: the stored embedding of an address, for "more like this"
- rerank: optionally reorders fused candidates with a rerank model
- pages: visual search over rendered-page embeddings (multimodal model)
- concepts: the concept graph (concepts, their mentions and relations)

Vector similarity is brute force over the scope, which is fine at notebook
scale (thousands of chunks).
"""

import re
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

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


RERANK_CANDIDATES = 24
RERANK_TEXT_CHARS = 2000


async def rerank_model() -> Optional[str]:
    from open_notebook.domain.agent_settings import AgentSettings

    try:
        settings = await AgentSettings.load()
    except Exception as e:
        logger.warning(f"Could not read agent settings: {e}")
        return None
    return (settings.rerank_model or "").strip() or None


async def rerank(
    query: str,
    hits: List[Dict[str, Any]],
    text_of: Callable[[Dict[str, Any]], str],
    limit: int,
) -> List[Dict[str, Any]]:
    """The best `limit` hits by the rerank model; the fused order when reranking
    is off, has nothing to rank, or fails."""
    model = await rerank_model() if query.strip() and len(hits) > 1 else None
    if not model:
        return hits[:limit]
    from open_notebook.ai.openrouter import rerank as rerank_call

    try:
        ranked = await rerank_call(
            model, query, [text_of(h)[:RERANK_TEXT_CHARS] for h in hits], limit
        )
    except Exception as e:
        logger.warning(f"Rerank failed, keeping fused order: {e}")
        return hits[:limit]
    return [hits[i] for i, _ in ranked if 0 <= i < len(hits)][:limit]


async def page_embedding_model() -> Optional[str]:
    from open_notebook.domain.agent_settings import AgentSettings

    try:
        settings = await AgentSettings.load()
    except Exception as e:
        logger.warning(f"Could not read agent settings: {e}")
        return None
    return (settings.page_embedding_model or "").strip() or None


async def page_hits(
    scope: AgentScope,
    embed: List[float],
    k: int,
    only: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Pages whose rendered image is closest to `embed`, best first. Pages of one
    animation build share a vector, so they come back as one hit (page_start..page_end)."""
    sources, _ = _ids(scope, only)
    if not sources:
        return []
    rows = await per_source(
        """
        SELECT source, page, text, caption,
            vector::similarity::cosine(image_embedding, $embed) AS score
        FROM source_page WHERE source = $s AND image_embedding != NONE
        ORDER BY score DESC LIMIT $k
        """,
        sources,
        embed=embed,
        k=k * 3,
    )
    groups: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        key = (str(row["source"]), round(float(row["score"]), 6))
        hit = groups.get(key)
        if hit is None:
            groups[key] = {**row, "page_start": row["page"], "page_end": row["page"]}
        else:  # same vector: another page of the same build; keep the fullest text
            hit["page_start"] = min(hit["page_start"], row["page"])
            hit["page_end"] = max(hit["page_end"], row["page"])
            if len(row.get("text") or "") > len(hit.get("text") or ""):
                hit["text"], hit["caption"] = row.get("text"), row.get("caption")
    return sorted(groups.values(), key=lambda h: -float(h["score"]))[:k]


async def page_image_embedding(address: Address) -> Optional[List[float]]:
    """The image embedding of an address's (first) page, for like= page searches."""
    if address.table != "source" or address.page_start is None:
        return None
    rows = await repo_query(
        "SELECT VALUE image_embedding FROM source_page WHERE source = $s AND page = $p",
        {"s": ensure_record_id(address.record_id), "p": address.page_start},
    )
    return _first_vector(rows)


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


# ---------------------------------------------------------------- concept graph
async def scoped_concepts(scope: AgentScope) -> Dict[str, Dict[str, Any]]:
    """Concepts mentioned by the scoped sources: id -> {name, key, embedding,
    documents (set of source ids), mentions (count)}."""
    sources, _ = _ids(scope)
    if not sources:
        return {}
    rows = await per_source(
        "SELECT concept, source FROM concept_mention WHERE source = $s", sources
    )
    if not rows:
        return {}
    stats: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        entry = stats.setdefault(
            str(row["concept"]), {"documents": set(), "mentions": 0}
        )
        entry["documents"].add(str(row["source"]))
        entry["mentions"] += 1
    concepts = await repo_query(
        "SELECT id, name, key, embedding FROM $records",
        {"records": [ensure_record_id(c) for c in stats]},
    )
    for c in concepts:
        stats[str(c["id"])].update(
            name=c["name"], key=c["key"], embedding=c.get("embedding")
        )
    return {cid: entry for cid, entry in stats.items() if "name" in entry}


def match_concepts(
    concepts: Dict[str, Dict[str, Any]],
    name: str,
    embed: Optional[List[float]],
    k: int,
) -> List[str]:
    """Concept ids best matching a name: exact (normalized) name, then names
    containing it or contained in it, then embedding similarity."""
    from open_notebook.utils.concepts import concept_key

    key = concept_key(name)
    exact = [cid for cid, c in concepts.items() if c["key"] == key]
    partial = [
        cid
        for cid, c in concepts.items()
        if cid not in exact and key and (key in c["key"] or c["key"] in key)
    ]
    partial.sort(key=lambda cid: -len(concepts[cid]["documents"]))
    similar: List[str] = []
    if embed is not None:
        scored = [
            (_cosine(c["embedding"], embed), cid)
            for cid, c in concepts.items()
            if c.get("embedding") and cid not in exact and cid not in partial
        ]
        similar = [cid for score, cid in sorted(scored, reverse=True) if score > 0.5]
    return (exact + partial + similar)[:k]


async def concept_for_name(name: str) -> Optional[str]:
    """The concept a name is an alias of, if any ("relu" -> the ReLU concept)."""
    from open_notebook.utils.concepts import alias_id, concept_key

    key = concept_key(name)
    if not key:
        return None
    rows = await repo_query(
        "SELECT VALUE concept FROM $alias", {"alias": ensure_record_id(alias_id(key))}
    )
    return str(rows[0]) if rows and rows[0] else None


async def concept_mentions(concept_id: str, scope: AgentScope) -> List[Dict[str, Any]]:
    rows = await repo_query(
        """
        SELECT source, section, page_start, page_end, context FROM concept_mention
        WHERE concept = $c ORDER BY source, page_start
        """,
        {"c": ensure_record_id(concept_id)},
    )
    return [r for r in rows if str(r["source"]) in scope.sources]


async def concept_relations(concept_id: str, scope: AgentScope) -> List[Dict[str, Any]]:
    record = ensure_record_id(concept_id)
    rows = await repo_query(
        """
        SELECT from_concept, to_concept, from_concept.name AS from_name,
            to_concept.name AS to_name, relation, source, page_start, page_end
        FROM concept_relation WHERE from_concept = $c OR to_concept = $c
        """,
        {"c": record},
    )
    return [r for r in rows if str(r["source"]) in scope.sources]
