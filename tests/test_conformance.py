"""Port conformance: one executable suite per port, run against every
implementation of it.

This is where substitutability is actually decided. mypy was measured on four
ways to break a port and caught one: it flags a changed return type, and stays
silent on a renamed parameter, an extra defaulted parameter, and an
implementation that RAISES where its siblings return empty — which is the
violation CLAUDE.md §3 names as the realistic one.

The registry below is also the answer to "does this port have an
implementation". Two ports with the same method names are indistinguishable by
shape, so counting implementations structurally reports a port as implemented
when it is not; here the pairing is stated and executed.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from pretraga.adapters.lexical_sqlite import SqliteLexicalSearch
from pretraga.domain.kinds import ContentHash
from pretraga.domain.ports import (
    FAILURE_MODES,
    FailureMode,
    LexicalSearch,
    SearchHit,
    SearchUnavailable,
    SemanticSearch,
)


@dataclass(frozen=True)
class Case:
    """One implementation, with what its port's failure mode means for it."""

    port: type
    name: str
    make: Callable[[], object]
    unfindable: str
    """An input that finds nothing — the shape of 'nothing' is the contract."""


CASES: list[Case] = [
    Case(LexicalSearch, "SqliteLexicalSearch", lambda: SqliteLexicalSearch(path=":memory:"), " "),
]


def check_failure_mode(impl: object, port: type, unfindable: str) -> None:
    """The declared failure mode, executed. RAISES accepts SearchUnavailable
    and NOTHING else: a TypeError from a broken adapter must propagate, or a
    bug becomes indistinguishable from an outage (measured)."""
    mode = FAILURE_MODES[port]
    if mode is FailureMode.RETURNS_EMPTY:
        assert impl.search(unfindable, 5) == []  # type: ignore[attr-defined]
    elif mode is FailureMode.RAISES:
        try:
            impl.search(unfindable, 5)  # type: ignore[attr-defined]
        except SearchUnavailable:
            return
        pytest.fail(f"{type(impl).__name__} did not raise SearchUnavailable on {unfindable!r}")
    else:  # RETURNS_INPUT
        seeds = [ContentHash("0" * 64)]
        assert impl.expand(seeds, 1) == seeds  # type: ignore[attr-defined]


def _ids(c: Case) -> str:
    return f"{c.port.__name__}:{c.name}"


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_returns_the_declared_shape(case: Case) -> None:
    got = case.make().search("regulation", 5)  # type: ignore[attr-defined]
    assert isinstance(got, list)
    assert all(isinstance(h, SearchHit) for h in got)


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_limit_is_honoured(case: Case) -> None:
    impl = case.make()
    for limit in (0, 1, 5):
        assert len(impl.search("regulation", limit)) <= limit  # type: ignore[attr-defined]


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_keyword_call_works(case: Case) -> None:
    """A renamed parameter type-checks clean and fails here. Callers name the
    argument, so the name is part of the contract."""
    impl = case.make()
    assert isinstance(impl.search(question="regulation", limit=3), list)  # type: ignore[attr-defined]


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_failure_mode_matches_the_port(case: Case) -> None:
    check_failure_mode(case.make(), case.port, case.unfindable)


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_repeated_call_is_stable(case: Case) -> None:
    impl = case.make()
    assert impl.search("regulation", 5) == impl.search("regulation", 5)  # type: ignore[attr-defined]


def test_raises_mode_accepts_the_declared_exception() -> None:
    """The machinery itself, given a live input it will not have until a cloud
    adapter exists: an honest RAISES implementation passes."""

    class Honest:
        def search(self, question: str, limit: int) -> list[SearchHit]:
            raise SearchUnavailable("backend down")

    check_failure_mode(Honest(), SemanticSearch, "anything")


def test_raises_mode_rejects_a_foreign_exception() -> None:
    """A broken adapter raising TypeError must FAIL the conformance check, not
    satisfy it — this is the measured pytest.raises(Exception) hole."""

    class Broken:
        def search(self, question: str, limit: int) -> list[SearchHit]:
            raise TypeError("programming error")

    with pytest.raises(TypeError):
        check_failure_mode(Broken(), SemanticSearch, "anything")


def test_raises_mode_rejects_a_silent_success() -> None:
    class Quiet:
        def search(self, question: str, limit: int) -> list[SearchHit]:
            return []

    with pytest.raises(pytest.fail.Exception):
        check_failure_mode(Quiet(), SemanticSearch, "anything")


def test_every_port_is_either_covered_or_openly_uncovered() -> None:
    """The registry may not silently omit a port. An unimplemented port is
    listed here as unimplemented, so 'we forgot' and 'not built yet' stop
    looking the same."""
    import truth

    ports = set(truth.survey().ports.values())
    covered = {c.port for c in CASES}
    uncovered = sorted(p.__name__ for p in ports - covered)
    assert uncovered == ["GraphExpansion", "SemanticSearch"], (
        f"the list of ports without an implementation changed: {uncovered}. "
        "Add the implementation to CASES, or update this list deliberately.")
