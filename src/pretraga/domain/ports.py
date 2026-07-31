"""Ports: interfaces the domain declares and an outer ring implements. Roles,
never engines.

A port's failure mode is part of its contract and is declared ONCE, machine
readably, in FAILURE_MODES below. Prose in a docstring cannot be checked, and a
failure mode recorded in two places is a failure mode that will disagree with
itself. The conformance suite reads this table; the truth checker requires it to
cover every port.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pretraga.domain.kinds import ContentHash, Value
from pretraga.domain.provenance import ProvenanceAnchor


class SearchUnavailable(RuntimeError):
    """The one exception a RAISES-mode port may signal unavailability with.

    The abstraction owns the error type (DIP): adapters translate their
    backend's failures into this, so a caller that degrades on it never
    swallows a programming error by accident — a TypeError from a broken
    adapter stays loud. Measured: catching bare Exception made a wrong-signature
    adapter indistinguishable from a cloud outage.
    """


class FailureMode(StrEnum):
    """How an implementation behaves when it cannot answer.

    This is the substitutability question that types do not reach: an
    implementation that raises where its siblings return empty is a Liskov
    violation that type checking accepts.
    """

    RAISES = "raises"
    """Unavailable means SearchUnavailable — that exception and no other."""
    RETURNS_EMPTY = "returns_empty"
    """Nothing found means an empty result, never an exception."""
    RETURNS_INPUT = "returns_input"
    """Unavailable means the input passes through unchanged."""


class SearchHit(Value):
    """What every search port returns: an anchor and a comparable score."""

    anchor: ProvenanceAnchor
    score: float


@runtime_checkable
class SemanticSearch(Protocol):
    """Dense retrieval over fragments, served from the cloud."""

    def search(self, question: str, limit: int) -> list[SearchHit]: ...


@runtime_checkable
class LexicalSearch(Protocol):
    """Local BM25-class retrieval: precision on identifiers and numbers."""

    def search(self, question: str, limit: int) -> list[SearchHit]: ...


@runtime_checkable
class GraphExpansion(Protocol):
    """Expansion of seed nodes over the derived graph."""

    def expand(self, seeds: list[ContentHash], hops: int) -> list[ContentHash]: ...


FAILURE_MODES: dict[type, FailureMode] = {
    SemanticSearch: FailureMode.RAISES,
    LexicalSearch: FailureMode.RETURNS_EMPTY,
    GraphExpansion: FailureMode.RETURNS_INPUT,
}
