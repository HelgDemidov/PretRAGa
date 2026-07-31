"""Derivation manifest, deliverable, and the outcome of a query."""
from __future__ import annotations

from pretraga.domain.kinds import Entity, Value
from pretraga.domain.provenance import ProvenanceAnchor


class DerivationManifest(Value):
    """The passport of a derived artifact: the registry commit plus the entry
    versions that produced it."""

    registry_commit: str
    entry_versions: tuple[tuple[str, int], ...]


class Deliverable(Entity):
    """The output document: Markdown in the workspace git, stamped with a
    manifest, versioned by construction."""

    title: str
    body: str
    stamp: DerivationManifest


class Answer(Value):
    """An answer that carries its evidence. Anchors are not optional here."""

    text: str
    anchors: tuple[ProvenanceAnchor, ...]


class Refusal(Value):
    """The corpus does not contain this. A refusal always states why."""

    reason: str


class StaleWarning(Value):
    """The derived layers are behind the registry, stated rather than hidden."""

    behind_by: int


QueryOutcome = Answer | Refusal | StaleWarning
"""The sum of shapes an answer path may return. There is no fourth: a guess is
not representable."""
