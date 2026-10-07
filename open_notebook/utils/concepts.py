"""Concept graph extraction models and name normalization (agentic RAG plan, Phase 5)."""

import hashlib
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


def concept_id(key: str) -> str:
    """The concept record id for a normalized key (stable across jobs)."""
    return "concept:c" + hashlib.sha1(key.encode()).hexdigest()[:20]
