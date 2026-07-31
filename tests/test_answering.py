"""The answer scenario: refuse rather than guess, degrade only on the declared
failure, and never mask a programming error as an outage."""
from __future__ import annotations

import pytest

from pretraga.domain.kinds import ContentHash
from pretraga.domain.ports import SearchHit, SearchUnavailable
from pretraga.domain.provenance import CharSpan, ProvenanceAnchor
from pretraga.domain.synthesis import Answer, Refusal
from pretraga.usecases.answering import answer

_HIT = SearchHit(
    anchor=ProvenanceAnchor(version_key="en:1", text_hash=ContentHash("a" * 64),
                            span=CharSpan(start=0, end=4)),
    score=1.0)


class Empty:
    def search(self, question: str, limit: int) -> list[SearchHit]:
        return []


class OneHit:
    def search(self, question: str, limit: int) -> list[SearchHit]:
        return [_HIT][:limit]


class Down:
    def search(self, question: str, limit: int) -> list[SearchHit]:
        raise SearchUnavailable("cloud down")


class Broken:
    """A buggy adapter: raises a foreign exception, not SearchUnavailable.

    (A renamed parameter is the CONFORMANCE suite's catch — the scenario calls
    positionally, so the rename surfaces there, via the keyword-call test.)
    """

    def search(self, question: str, limit: int) -> list[SearchHit]:
        raise TypeError("programming error inside the adapter")


class NoGraph:
    def expand(self, seeds: list[ContentHash], hops: int) -> list[ContentHash]:
        return seeds


def test_nothing_found_is_a_refusal_never_an_empty_answer() -> None:
    out = answer("q", Empty(), Empty(), NoGraph())
    assert isinstance(out, Refusal)
    assert out.reason


def test_a_hit_yields_an_answer_that_carries_its_anchors() -> None:
    out = answer("q", Empty(), OneHit(), NoGraph())
    assert isinstance(out, Answer)
    assert out.anchors


def test_an_unavailable_cloud_degrades_to_lexical() -> None:
    out = answer("q", Down(), OneHit(), NoGraph())
    assert isinstance(out, Answer)


def test_an_unavailable_cloud_with_no_lexical_hits_refuses() -> None:
    assert isinstance(answer("q", Down(), Empty(), NoGraph()), Refusal)


def test_a_foreign_exception_propagates_instead_of_degrading() -> None:
    """Measured hole this pins: with `except Exception` a TypeError from a
    buggy adapter read as 'not present in the corpus'."""
    with pytest.raises(TypeError):
        answer("q", Broken(), OneHit(), NoGraph())
