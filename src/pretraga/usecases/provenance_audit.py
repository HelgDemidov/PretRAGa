"""Walk the provenance chain over DATA and name every link that does not
resolve.

Checking this chain through type annotations was measured at 2 of 5 hops: the
three invisible ones are content-addressed, so the link is a ContentHash field
rather than a field of the next type — which is what the project's own identity
rule requires. The claim is therefore checked where it actually lives.
"""
from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from pretraga.domain.facts import Claim
from pretraga.domain.kinds import ContentHash
from pretraga.domain.provenance import CanonicalText, RawPayload


@runtime_checkable
class EvidenceStore(Protocol):
    """What the audit needs, not the union of what a store happens to have.

    Failure mode is part of the contract: a lookup that finds nothing returns
    None and never raises, so a missing link is reported rather than crashing
    the audit halfway through.
    """

    def claims(self, limit: int) -> list[Claim]: ...
    def canonical_text(self, key: ContentHash) -> CanonicalText | None: ...
    def raw_payload(self, key: ContentHash) -> RawPayload | None: ...
    def raw_bytes(self, key: ContentHash) -> bytes | None: ...


class _SampledOnce:
    """The sampled claims, frozen; every other lookup goes through untouched."""

    def __init__(self, store: EvidenceStore, claims: list[Claim]) -> None:
        self._store, self._claims = store, claims

    def claims(self, limit: int) -> list[Claim]:
        return self._claims[:limit]

    def canonical_text(self, key: ContentHash) -> CanonicalText | None:
        return self._store.canonical_text(key)

    def raw_payload(self, key: ContentHash) -> RawPayload | None:
        return self._store.raw_payload(key)

    def raw_bytes(self, key: ContentHash) -> bytes | None:
        return self._store.raw_bytes(key)


def _claim_id(c: Claim, index: int) -> str:
    """Which claim a message is about, unambiguously.

    The quoted text alone does not identify one: legal wording shares long
    openings by nature, so two different claims truncate to the same prefix and
    the operator cannot tell which record is broken. The anchor is the claim's
    address, so it is what the message leads with."""
    return (f"claim #{index} @{c.anchor.text_hash}:{c.anchor.span.start}-{c.anchor.span.end} "
            f"{c.normalized[:40]!r}")


def audit(store: EvidenceStore, sample: int = 200) -> list[str]:
    """Every broken link, named. Empty means every sampled claim resolves all
    the way down to bytes whose hash still matches — AND that every answer the
    store gave is the one that was asked for."""
    broken: list[str] = []
    for i, c in enumerate(store.claims(sample)):
        anchor = c.anchor
        who = _claim_id(c, i)
        text = store.canonical_text(anchor.text_hash)
        if text is None:
            broken.append(f"{who}: anchor -> canonical text {anchor.text_hash} missing")
            continue
        # A lookup that answers with a DIFFERENT record is the failure this
        # chain exists to catch, and hashing the answer does not catch it: a
        # substituted text is internally consistent, so every downstream check
        # passes. Measured: a store answering every query with one well-formed
        # text produced an empty report while the evidence under the claim said
        # the opposite of the claim.
        if text.content_hash != anchor.text_hash:
            broken.append(f"{who}: asked the store for canonical text {anchor.text_hash} and it "
                          f"answered with {text.content_hash} — the evidence under this claim is "
                          "not the evidence it names")
            continue
        if not (0 <= anchor.span.start <= anchor.span.end <= len(text.body)):
            broken.append(f"{who}: span {anchor.span.start}:{anchor.span.end} outside a text of "
                          f"{len(text.body)} chars")
        if hashlib.sha256(text.body.encode()).hexdigest() != text.content_hash:
            broken.append(f"canonical text {text.content_hash}: body no longer matches its key")
        raw = store.raw_payload(text.conversion.source)
        if raw is None:
            broken.append(f"canonical text {text.content_hash}: conversion -> raw "
                          f"{text.conversion.source} missing")
            continue
        if raw.content_hash != text.conversion.source:
            broken.append(f"canonical text {text.content_hash}: conversion names raw "
                          f"{text.conversion.source} and the store answered with "
                          f"{raw.content_hash}")
            continue
        data = store.raw_bytes(raw.content_hash)
        if data is None:
            broken.append(f"raw {raw.content_hash}: bytes are gone")
        elif hashlib.sha256(data).hexdigest() != raw.content_hash:
            broken.append(f"raw {raw.content_hash}: content no longer matches its key")
    return broken


def report(store: EvidenceStore, sample: int = 200) -> tuple[int, list[str]]:
    """(records examined, broken links). Zero records is reported as zero and
    must not be read as green: an audit with nothing to audit proves nothing.

    The count comes from the SAME call the audit walked, never from a second
    one. Measured: a store answering claims() differently on each call reported
    "200 records examined, nothing broken" having been audited zero times — the
    honesty signal itself was the thing being faked."""
    sampled = list(store.claims(sample))
    return len(sampled), audit(_SampledOnce(store, sampled), sample)
