"""The query-layer scenario: hybrid retrieval, graph expansion, an anchored
answer or an honest refusal. Depends on ports only."""
from __future__ import annotations

from pretraga.domain.ports import (
    GraphExpansion,
    LexicalSearch,
    SearchHit,
    SearchUnavailable,
    SemanticSearch,
)
from pretraga.domain.synthesis import Answer, QueryOutcome, Refusal


def _fuse(left: list[SearchHit], right: list[SearchHit], k: int = 60) -> list[SearchHit]:
    """Reciprocal-rank fusion. A scenario, not a port."""
    scored: dict[str, tuple[SearchHit, float]] = {}
    for ranking in (left, right):
        for rank, hit in enumerate(ranking, start=1):
            key = f"{hit.anchor.text_hash}:{hit.anchor.span.start}"
            prev = scored.get(key, (hit, 0.0))
            scored[key] = (hit, prev[1] + 1.0 / (k + rank))
    return [h for h, _ in sorted(scored.values(), key=lambda p: -p[1])]


def answer(
    question: str,
    semantic: SemanticSearch,
    lexical: LexicalSearch,
    graph: GraphExpansion,
    limit: int = 10,
) -> QueryOutcome:
    """Refuse rather than guess: an empty retrieval is a Refusal, never an
    Answer with no anchors."""
    try:
        dense = semantic.search(question, limit)
    except SearchUnavailable:
        # The port's declared failure mode, and ONLY it: an unexpected
        # exception is a bug and must stay loud, not read as a cloud outage.
        dense = []
    fused = _fuse(dense, lexical.search(question, limit))
    if not fused:
        return Refusal(reason="not present in the corpus")
    graph.expand([h.anchor.text_hash for h in fused[:3]], hops=1)
    return Answer(text="", anchors=tuple(h.anchor for h in fused))
