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


def audit(store: EvidenceStore, sample: int = 200) -> list[str]:
    """Every broken link, named. Empty means every sampled claim resolves all
    the way down to bytes whose hash still matches."""
    broken: list[str] = []
    for c in store.claims(sample):
        anchor = c.anchor
        text = store.canonical_text(anchor.text_hash)
        if text is None:
            broken.append(f"claim {c.normalized[:40]!r}: anchor -> canonical text "
                          f"{anchor.text_hash[:12]} missing")
            continue
        if not (0 <= anchor.span.start <= anchor.span.end <= len(text.body)):
            broken.append(f"claim {c.normalized[:40]!r}: span {anchor.span.start}:"
                          f"{anchor.span.end} outside a text of {len(text.body)} chars")
        if hashlib.sha256(text.body.encode()).hexdigest() != text.content_hash:
            broken.append(f"canonical text {text.content_hash[:12]}: body no longer matches its key")
        raw = store.raw_payload(text.conversion.source)
        if raw is None:
            broken.append(f"canonical text {text.content_hash[:12]}: conversion -> raw "
                          f"{text.conversion.source[:12]} missing")
            continue
        data = store.raw_bytes(raw.content_hash)
        if data is None:
            broken.append(f"raw {raw.content_hash[:12]}: bytes are gone")
        elif hashlib.sha256(data).hexdigest() != raw.content_hash:
            broken.append(f"raw {raw.content_hash[:12]}: content no longer matches its key")
    return broken


def report(store: EvidenceStore, sample: int = 200) -> tuple[int, list[str]]:
    """(records examined, broken links). Zero records is reported as zero and
    must not be read as green: an audit with nothing to audit proves nothing."""
    return len(store.claims(sample)), audit(store, sample)
