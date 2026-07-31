"""The provenance chain: raw payload -> conversion record -> canonical text ->
anchor. Every link is content-addressed."""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from pretraga.domain.kinds import ContentHash, Open, Trigger, Value


class ProvenanceLabel(StrEnum):
    """Where a value came from. The answer path branches on this: an unverified
    label may not be presented as fact."""

    DETERMINISTIC = "deterministic"
    INFERRED = "inferred"
    HUMAN_CURATED = "human_curated"


class CharSpan(Value):
    """A half-open character interval inside a canonical text."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class RawPayload(Value):
    """The downloaded body exactly as received. A primary artifact, not a
    derived one: the web rots, so re-fetching restores it only in part."""

    content_hash: ContentHash
    media_type: str


class ConversionRecord(Value):
    """Which converter, at which version, produced a canonical text from raw
    bytes. The second link of the provenance chain."""

    open_questions = (Open(question="full record composition", trigger=Trigger.CONVERSION_SPEC),)
    converter_name: str
    converter_entry_version: int
    source: ContentHash


class CanonicalText(Value):
    """The Markdown rendering of a content version: the single carrying format
    of the corpus, and the space anchors address."""

    content_hash: ContentHash
    conversion: ConversionRecord
    body: str


class ProvenanceAnchor(Value):
    """The publishable stable address of a piece of evidence: a content
    version, a canonical-text hash and a character span. Independent of how the
    text is chunked."""

    version_key: str
    text_hash: ContentHash
    span: CharSpan


class Fragment(Value):
    """A derived unit of search. Re-created freely when chunking changes, so
    long-lived references to fragments are forbidden — they point at anchors."""

    text_hash: ContentHash
    span: CharSpan
    chunker_version: int
