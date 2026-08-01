"""The acquisition side of the domain, plus the triage verdict."""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from pretraga.domain.kinds import ContentHash, Entity, MintedId, Open, Trigger


class ChannelLifecycle(StrEnum):
    """Channels are retired, never deleted, so provenance survives."""

    ACTIVE = "active"
    RETIRED = "retired"


class Decision(StrEnum):
    """A triage outcome. Symmetric: admission and refusal are the same shape."""

    ADMIT = "admit"
    REJECT = "reject"


class AcquisitionChannel(Entity):
    """A configured connector instance. Only what provenance depends on lives
    here; schedule, coverage and gate rules are adapter configuration."""

    open_questions = (Open(question="declared coverage vocabulary",
                           trigger=Trigger.ACQUISITION_SPEC),)
    connector_type: str
    lifecycle: ChannelLifecycle


class AcquisitionAct(Entity):
    """A machine journal record: which channel, when, what it brought."""

    channel: MintedId = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    occurred_at: str
    brought: tuple[ContentHash, ...]


class TriageVerdict(Entity):
    """A first-class decision with a reason. Re-triage under a new policy mints
    a new verdict; the old one stays, because deletion does not exist."""

    open_questions = (Open(question="rule set", trigger=Trigger.INGEST_SPEC),)
    document: MintedId = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    decision: Decision
    reason: str
    policy_version: int
