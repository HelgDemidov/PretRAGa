"""Claims, typed references, world entities, translations."""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from pretraga.domain.kinds import ContentHash, Entity, MintedId, Open, Trigger, Value
from pretraga.domain.provenance import ProvenanceAnchor, ProvenanceLabel


class ReferenceType(StrEnum):
    """The base ELI-derived vocabulary of document-to-document edges."""

    CITES = "cites"
    AMENDS = "amends"
    IMPLEMENTS = "implements"
    SUPERSEDES = "supersedes"


class WorldEntity(Entity):
    """A graph node: an organisation, a country, a technology. Surface forms
    are normalised through a human-written table."""

    open_questions = (Open(question="entity-resolution table", trigger=Trigger.ENRICHMENT_SPEC),)
    surface_forms: tuple[str, ...]


class Claim(Value):
    """"Document W in version V asserts X." The anchor is mandatory, so a claim
    without evidence is unrepresentable. A claim is the document's position,
    not a truth about the world."""

    open_questions = (Open(question="small predicate vocabulary", trigger=Trigger.ENRICHMENT_SPEC),)
    anchor: ProvenanceAnchor
    normalized: str
    label: ProvenanceLabel
    extractor_version: int


class TypedReference(Value):
    """An edge between documents. Derived deterministically; a finding made in
    text carries an anchor."""

    source: MintedId
    target_coordinate: str
    kind: ReferenceType
    anchor: ProvenanceAnchor | None = None


class Translation(Value):
    """A lens for reading and embedding; never a carrier of anchors, because
    extraction runs on the original."""

    of_text: ContentHash = Field(pattern=r"^[0-9a-f]{64}$")
    language: str
    body: str
