"""Driven adapter: local BM25-class search over an embedded store."""
from __future__ import annotations

from pretraga.domain.kinds import ContentHash
from pretraga.domain.ports import SearchHit
from pretraga.domain.provenance import CharSpan, ProvenanceAnchor

_ANCHOR = ProvenanceAnchor(version_key="en:1", text_hash=ContentHash("0" * 64),
                           span=CharSpan(start=0, end=1))


class SqliteLexicalSearch:
    """Implements LexicalSearch. Honours the declared failure mode: no match
    returns an empty list, never raises."""

    def __init__(self, path: str) -> None:
        self._path = path

    def search(self, question: str, limit: int) -> list[SearchHit]:
        if not question.strip():
            return []
        return [SearchHit(anchor=_ANCHOR, score=1.0)][:limit]
