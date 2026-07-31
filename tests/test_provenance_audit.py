"""The provenance chain, checked over data. Six corruption modes, plus the
empty corpus, plus the property that the chain holds for any generated corpus."""
from __future__ import annotations

import hashlib

from hypothesis import given, settings
from hypothesis import strategies as st

from pretraga.domain.facts import Claim
from pretraga.domain.kinds import ContentHash, content_key
from pretraga.domain.provenance import (
    CanonicalText,
    CharSpan,
    ConversionRecord,
    ProvenanceAnchor,
    ProvenanceLabel,
    RawPayload,
)
from pretraga.usecases.provenance_audit import report


class MemoryStore:
    """A store that honours the port's declared failure mode: a miss is None."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.raws: dict[str, RawPayload] = {}
        self.texts: dict[str, CanonicalText] = {}
        self.claim_list: list[Claim] = []

    def claims(self, limit: int) -> list[Claim]:
        return self.claim_list[:limit]

    def canonical_text(self, key: ContentHash) -> CanonicalText | None:
        return self.texts.get(key)

    def raw_payload(self, key: ContentHash) -> RawPayload | None:
        return self.raws.get(key)

    def raw_bytes(self, key: ContentHash) -> bytes | None:
        return self.blobs.get(key)


def build(bodies: list[str]) -> MemoryStore:
    store = MemoryStore()
    for i, body in enumerate(bodies):
        blob = body.encode()
        raw_key = content_key(blob)
        store.blobs[raw_key] = blob
        store.raws[raw_key] = RawPayload(content_hash=raw_key, media_type="text/plain")
        text_key = content_key(blob)
        store.texts[text_key] = CanonicalText(
            content_hash=text_key,
            conversion=ConversionRecord(converter_name="t", converter_entry_version=1,
                                        source=raw_key),
            body=body)
        store.claim_list.append(Claim(
            anchor=ProvenanceAnchor(version_key="en:1", text_hash=text_key,
                                    span=CharSpan(start=0, end=min(3, len(body)))),
            normalized=f"claim {i}", label=ProvenanceLabel.DETERMINISTIC, extractor_version=1))
    return store


SAMPLE = ["regulation body one", "regulation body two", "regulation body three"]


def test_an_intact_corpus_is_green() -> None:
    n, broken = report(build(SAMPLE))
    assert n == 3
    assert broken == []


def test_a_missing_canonical_text_is_named() -> None:
    store = build(SAMPLE)
    store.texts.clear()
    _, broken = report(store)
    assert len(broken) == 3
    assert "canonical text" in broken[0]


def test_a_missing_raw_payload_is_named() -> None:
    store = build(SAMPLE)
    store.raws.pop(next(iter(store.raws)))
    _, broken = report(store)
    assert any("raw" in b and "missing" in b for b in broken)


def test_tampered_bytes_under_the_same_key_are_caught() -> None:
    """The quietest corruption there is: the key still resolves, the content is
    no longer what the key names."""
    store = build(SAMPLE)
    key = next(iter(store.blobs))
    store.blobs[key] = b"tampered"
    _, broken = report(store)
    assert any("no longer matches its key" in b for b in broken)


def test_a_tampered_canonical_text_under_the_same_key_is_caught() -> None:
    store = build(SAMPLE)
    key = next(iter(store.texts))
    original = store.texts[key]
    store.texts[key] = CanonicalText(content_hash=original.content_hash,
                                     conversion=original.conversion, body="tampered body")
    _, broken = report(store)
    assert any("body no longer matches its key" in b for b in broken)


def test_an_anchor_pointing_outside_the_text_is_caught() -> None:
    store = build(SAMPLE)
    old = store.claim_list[0]
    store.claim_list[0] = Claim(
        anchor=ProvenanceAnchor(version_key="en:1", text_hash=old.anchor.text_hash,
                                span=CharSpan(start=0, end=99_999)),
        normalized=old.normalized, label=old.label, extractor_version=1)
    _, broken = report(store)
    assert any("outside a text" in b for b in broken)


def test_a_fabricated_anchor_is_caught() -> None:
    """The asymmetry the whole product rests on: a fabricated statement is a
    defect, a missed fact is tolerable."""
    store = build(SAMPLE)
    store.claim_list[0] = Claim(
        anchor=ProvenanceAnchor(version_key="en:1", text_hash=ContentHash("f" * 64),
                                span=CharSpan(start=0, end=5)),
        normalized="fabricated", label=ProvenanceLabel.INFERRED, extractor_version=1)
    _, broken = report(store)
    assert any("fabricated" in b for b in broken)


def test_an_empty_corpus_reports_zero_records_rather_than_success() -> None:
    n, broken = report(MemoryStore())
    assert (n, broken) == (0, [])


@settings(max_examples=50, deadline=None)
@given(st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=6, unique=True))
def test_any_intact_corpus_resolves(bodies: list[str]) -> None:
    """Built around a real corpus rather than by generating two values and
    filtering: filtering would discard most examples."""
    _, broken = report(build(bodies))
    assert broken == []


@settings(max_examples=30, deadline=None)
@given(st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=5, unique=True),
       st.binary(min_size=1, max_size=20))
def test_any_tampering_is_detected(bodies: list[str], tamper: bytes) -> None:
    store = build(bodies)
    key = next(iter(store.blobs))
    if hashlib.sha256(tamper).hexdigest() == key:
        return
    store.blobs[key] = tamper
    _, broken = report(store)
    assert broken
