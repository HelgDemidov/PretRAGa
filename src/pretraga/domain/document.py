"""Document, its content versions, and the coordinates it is compared by."""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from pretraga.domain.kinds import ContentHash, Entity, MintedId, Open, Trigger, Value


class Lifecycle(StrEnum):
    """A closed set. Only ACTIVE documents are corpus; retirement replaces
    deletion, so history survives."""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    RETIRED = "retired"


class CoordinateScheme(StrEnum):
    """Schemes an origin coordinate may be stated in. A canonical URL never
    merges two documents on its own."""

    ELI = "eli"
    CELEX = "celex"
    REGISTRY_NUMBER = "registry_number"
    CANONICAL_URL = "canonical_url"


class OriginCoordinate(Value):
    """A (scheme, value) pair. Comparability runs on these; identity does not."""

    scheme: CoordinateScheme
    value: str


class ContentVersion(Value):
    """A two-axis key (language, edition): a translation is not a new edition,
    and a new edition is not a translation."""

    language: str
    edition: int
    payload: ContentHash = Field(pattern=r"^[0-9a-f]{64}$")


class Document(Entity):
    """The unit of the corpus, at the level of a work. Identity is minted at
    the candidate stage and never recomputed."""

    open_questions = (Open(question="composition of the admission minimum",
                           trigger=Trigger.INGEST_SPEC),)
    origin: tuple[OriginCoordinate, ...]
    lifecycle: Lifecycle
    channel: MintedId = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    versions: tuple[ContentVersion, ...] = ()
