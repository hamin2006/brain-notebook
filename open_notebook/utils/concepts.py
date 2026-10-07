"""Concept graph extraction models and name normalization (agentic RAG plan, Phase 5)."""

import hashlib
import json
import re
from typing import List, Optional

from pydantic import BaseModel, Field

MAX_CONCEPTS_PER_SECTION = 15
MAX_RELATIONS_PER_SECTION = 20


class ExtractedConcept(BaseModel):
    name: str = Field(
        description="Canonical name, singular, as a textbook index would list it (e.g. 'Batch normalization')"
    )
    page: Optional[int] = Field(
        None, description="Page where it is introduced or explained most"
    )
    context: str = Field(
        "", description="One short sentence: what the section says about it"
    )


class ExtractedRelation(BaseModel):
    source: str = Field(description="Concept name (as listed in concepts)")
    relation: str = Field(
        description="Short verb phrase, e.g. 'is a', 'part of', 'motivates', 'solves', 'variant of', 'uses', 'contrasts with'"
    )
    target: str = Field(description="Concept name (as listed in concepts)")
    page: Optional[int] = Field(None, description="Page that states the relation")


class ConceptExtraction(BaseModel):
    concepts: List[ExtractedConcept] = Field(default_factory=list)
    relations: List[ExtractedRelation] = Field(default_factory=list)


def concept_key(name: str) -> str:
    """Normalized identity of a concept name: case, punctuation and spacing ignored."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


_PARENTHESIZED = re.compile(r"^(.*?)\s*\(([^()]{1,40})\)\s*$")


def concept_names(name: str) -> List[str]:
    """The names a concept goes by: "Rectified linear unit (ReLU)" ->
    ["Rectified linear unit", "ReLU"]; a plain name -> [name]. The first is the
    display name."""
    name = " ".join(name.split())
    match = _PARENTHESIZED.match(name)
    if match and match.group(1).strip():
        return [match.group(1).strip(), match.group(2).strip()]
    return [name] if name else []


def alias_id(key: str) -> str:
    """The concept_alias record id for a normalized name."""
    return "concept_alias:a" + hashlib.sha1(key.encode()).hexdigest()[:20]


def concept_id(key: str) -> str:
    """The concept record id for a normalized key (stable across jobs)."""
    return "concept:c" + hashlib.sha1(key.encode()).hexdigest()[:20]


_BACKSLASH = re.compile(r"\\(\\|[A-Za-z]{2,}|.)", re.DOTALL)
_JSON_ESCAPES = set('"\\/bfnrtu')


def _escape_latex(text: str) -> str:
    """Make LaTeX inside JSON strings parseable: "\\sum" and "\\hat{y}" are invalid
    JSON escapes (and "\\frac" or "\\beta" would silently become control
    characters), so a backslash before a word or an unknown escape is doubled."""

    def fix(match: re.Match) -> str:
        token = match.group(1)
        if token == "\\" or (len(token) == 1 and token in _JSON_ESCAPES):
            return match.group(0)
        return "\\\\" + token

    return _BACKSLASH.sub(fix, text)


def parse_extraction(raw: str) -> ConceptExtraction:
    """A model's concept JSON, tolerating code fences, surrounding prose and LaTeX."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the reply")
    data = json.loads(_escape_latex(raw[start : end + 1]), strict=False)
    return ConceptExtraction.model_validate(data)
