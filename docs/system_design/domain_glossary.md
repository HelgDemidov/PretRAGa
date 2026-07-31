# PretRAGa domain glossary

GENERATED from the domain package — never edit by hand. A concept's definition
is the docstring of its class, so there is no second copy that could drift.

## Conventions

The domain ring: the single hand-written source of the model.

Cross-cutting terminological conventions — the words the model refuses to use,
so they cannot drift into concepts:

- "source" is reserved for live speech and never names a model concept; the
  configured place documents come from is an AcquisitionChannel.
- "candidate" is a stage of a Document's lifecycle, not a concept of its own.
- "corpus" is a state predicate — all ACTIVE documents of the registry — not a
  stored thing: no id, no configuration, no lifecycle.

## Entities

Minted opaque identity; a lifecycle; never frozen.

### AcquisitionAct

A machine journal record: which channel, when, what it brought.

### AcquisitionChannel

A configured connector instance. Only what provenance depends on lives
here; schedule, coverage and gate rules are adapter configuration.

- open: declared coverage vocabulary (trigger: `acquisition_spec`)

### Deliverable

The output document: Markdown in the workspace git, stamped with a
manifest, versioned by construction.

### Document

The unit of the corpus, at the level of a work. Identity is minted at
the candidate stage and never recomputed.

- open: composition of the admission minimum (trigger: `ingest_spec`)

### TriageVerdict

A first-class decision with a reason. Re-triage under a new policy mints
a new verdict; the old one stays, because deletion does not exist.

- open: rule set (trigger: `ingest_spec`)

### WorldEntity

A graph node: an organisation, a country, a technology. Surface forms
are normalised through a human-written table.

- open: entity-resolution table (trigger: `enrichment_spec`)

## Values

Immutable; identity IS the content. Where persisted, the key is the content hash.

### Answer

An answer that carries its evidence. Anchors are not optional here.

### CanonicalText

The Markdown rendering of a content version: the single carrying format
of the corpus, and the space anchors address.

### CharSpan

A half-open character interval inside a canonical text.

### Claim

"Document W in version V asserts X." The anchor is mandatory, so a claim
without evidence is unrepresentable. A claim is the document's position,
not a truth about the world.

- open: small predicate vocabulary (trigger: `enrichment_spec`)

### ContentVersion

A two-axis key (language, edition): a translation is not a new edition,
and a new edition is not a translation.

### ConversionRecord

Which converter, at which version, produced a canonical text from raw
bytes. The second link of the provenance chain.

- open: full record composition (trigger: `conversion_spec`)

### DerivationManifest

The passport of a derived artifact: the registry commit plus the entry
versions that produced it.

### Fragment

A derived unit of search. Re-created freely when chunking changes, so
long-lived references to fragments are forbidden — they point at anchors.

### OriginCoordinate

A (scheme, value) pair. Comparability runs on these; identity does not.

### ProvenanceAnchor

The publishable stable address of a piece of evidence: a content
version, a canonical-text hash and a character span. Independent of how the
text is chunked.

### RawPayload

The downloaded body exactly as received. A primary artifact, not a
derived one: the web rots, so re-fetching restores it only in part.

### Refusal

The corpus does not contain this. A refusal always states why.

### SearchHit

What every search port returns: an anchor and a comparable score.

### StaleWarning

The derived layers are behind the registry, stated rather than hidden.

### Translation

A lens for reading and embedding; never a carrier of anchors, because
extraction runs on the original.

### TypedReference

An edge between documents. Derived deterministically; a finding made in
text carries an anchor.

## Ports

Interfaces the domain declares; each declares its failure mode in `FAILURE_MODES`.

### GraphExpansion

Expansion of seed nodes over the derived graph.

### LexicalSearch

Local BM25-class retrieval: precision on identifiers and numbers.

### SemanticSearch

Dense retrieval over fragments, served from the cloud.

## Sums

Closed unions: no shape exists outside the listed ones.

### QueryOutcome

Represent a PEP 604 union type

E.g. for int | str

## Vocabularies

- **ChannelLifecycle** — Channels are retired, never deleted, so provenance survives. `active`, `retired`
- **CoordinateScheme** — Schemes an origin coordinate may be stated in. A canonical URL never `eli`, `celex`, `registry_number`, `canonical_url`
- **Decision** — A triage outcome. Symmetric: admission and refusal are the same shape. `admit`, `reject`
- **FailureMode** — How an implementation behaves when it cannot answer. `raises`, `returns_empty`, `returns_input`
- **Lifecycle** — A closed set. Only ACTIVE documents are corpus; retirement replaces `candidate`, `active`, `retired`
- **ProvenanceLabel** — Where a value came from. The answer path branches on this: an unverified `deterministic`, `inferred`, `human_curated`
- **ReferenceType** — The base ELI-derived vocabulary of document-to-document edges. `cites`, `amends`, `implements`, `supersedes`
- **Trigger** — Closed vocabulary: a specification finds ITS open questions by trigger, `acquisition_spec`, `ingest_spec`, `conversion_spec`, `enrichment_spec`, `synthesis_spec`

## Services


## Errors

- **SearchUnavailable** — The one exception a RAISES-mode port may signal unavailability with.
