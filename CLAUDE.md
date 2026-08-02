# CLAUDE.md

PretRAGa is a from-scratch repository. These rules are domain-independent engineering
practice — they hold for any codebase this repository grows into.

---

## 1. Memory-keeping principle

One principle, every carrier: this file, the assistant's memory, design documents, the backlog,
code comments.

**Overwrite, never append.** Current content replaces stale content in place. The Nth
implementation of a described pattern → one description plus what is new, not a twin paragraph.
A structural fix closing a recurring problem → outcome + fix, not the incident history beside it.
**Volume grows only from genuinely new content**, never from recording that something changed;
a closed question shrinks the document. Additivity is the root cause of rot, hence the ratchet:
editing a section means re-checking ALL of its claims, not appending to it.

**No tombstones.** Removed things are removed: no "why we declined" paragraph, no comment where
the code was. At most one terminal line, and only where a reader would otherwise start doing the
removed thing. Version control carries the history.

**Style: dry, dense, short.** One claim per sentence. No preamble, no restating the surrounding
text, no anecdote where the rule suffices.

**First deletion candidate: motive detached from fact** ("the owner asked", "a decision was
taken") — motives do not affect the build, only what got built and how it works. Exception: when
the motive IS the rule (a live policy, not its adoption history), phrase it as a rule ("X is not
done"), not as a decision act. **Exempt:** decision rationale — the "why" and rejected
alternatives — explaining non-obvious constraints useful at future forks. "X was asked for" is
noise; "X was rejected because Y" is kept, in ONE place.

---

## 2. Repository and documentation layout

- **Directory structure mirrors the system's architectural layers**, and the documentation tree
  mirrors the code tree. A new module goes into its layer; a new document into the section of the
  layer it describes.
- **Each documentation section separates umbrella documents** (architecture, not implementable in
  one change) **from individually implementable specifications**; both subdirectories always
  exist. Automated scans for pickable work must distinguish the two by file name, not by a status
  line someone has to remember to write.
- **One specification = one directory** with a meaningful name; the document inside always has
  the SAME file name. Specifications are distinguished BY DIRECTORY; assets live beside the
  document. No numeric prefixes, spaces or shell metacharacters in names.
- **A cross-cutting backlog is not a specification** and does not follow its template; exclude it
  from auto-scans by name, not by location.
- **Thin entry-point wrappers left by a reorganisation are a compatibility contract, not
  duplicated code.** They keep documented commands and CI steps working. Do not import them from
  code and do not delete them as duplicates — check by hash first.
- **Tool configuration lives at the repository root**, so every check runs from one place and
  caches land in one place.
- **`.gitignore` is deny-by-default with explicit negation** wherever one directory holds two
  classes of file — the curated, human-authored artifact is versioned; generated output, machine
  state, caches and local artifacts are not. A directory cannot be re-included once the directory
  itself is excluded: exclude its *contents*, then negate.
- **Paths derived from a module's own location break SILENTLY when the module moves** — the code
  keeps running and quietly operates on nothing. On any move, smoke-check that the derived paths
  resolve to something that exists.

---

## 3. Architectural decisions

**Scope: decisions, not classes.** Runs when the data model's shape changes, a contract between
major modules or layers is drawn or redrawn, a major entity's lifecycle is defined, or a boundary
is added or removed. Below that scale the later sections carry these principles concretely;
re-deriving them per class costs more than it saves.

**Read SOLID as five questions about one thing: when this changes, what else must change with
it?** Heuristics about the locality of change, not laws — each narrower than its slogan, each
with a cost that can exceed its benefit. Ask at the decision, record the answers in the design
rationale, and where a principle is knowingly violated write down the bill. Ignoring them gives
a system where one change lands in nine places; applying them everywhere gives nine indirections
between a change and its effect — so the check runs at the few decisions expensive to reverse,
not everywhere.

- **One reason to change.** Does this unit answer to ONE source of change requests? Group by
  *who* asks, not by what the code superficially does — the naive reading shatters code that
  always changes together into fragments that must now change together in five places. *(SRP;
  §4: one writer per artifact, human/machine split.)*
- **Open along the axis that actually varies.** Can the system be extended along THAT axis
  without editing the core? Only that one: pre-opening an axis with no evidence of variation
  costs an abstraction forever. *(OCP; §7 — a variant is an entry, not an edit.)*
- **Substitutable implementations.** Can any implementation behind this interface be swapped
  without the caller learning which one it holds — failure modes, emptiness, ordering, timing,
  not merely types? The realistic violation is a sibling that throws where the others return
  empty. *(LSP; §6 full current view, §5 dispatch by type not name.)*
- **The consumer defines the interface.** Does this boundary expose what the caller needs, or the
  union of whatever the provider happens to have? *(ISP; §4 layer declares what it needs.)*
- **The abstraction belongs to the policy, not the detail.** Does the higher layer own the
  contract? A layer reaching into a lower module is one shape of violation; an abstraction with
  one implementation and no second in prospect is the other. *(DIP; §4 ports.)*
- **Which design_truth axis, beyond kind/role/layer/ring, does this touch?** Those four gate
  mechanically; several others (a value's provenance status, cross-reference identity safety,
  artifact ownership, a port's failure-mode choice, spec-readiness, constant calibration) do not
  — confirm by judgment at the decision, every time it is actually touched, never skipped because
  another document happens to mention the same fact: an unverified "already covered elsewhere" is
  the manual bookkeeping flag §4 warns against. *(design_truth §2.5 — the fifth checker type and
  its record format.)*

---

## 4. Data and state modelling

### Ownership

- **Separate the human-authored from the machine-written.** The record a person edits is the
  source of truth; observed and derived state lives in a separate artifact. **The machine never
  writes into a human-editable file** — that removes comment preservation, round-trip formatting
  and a whole class of ownership questions at once. (Declared intent versus observed status: the
  `spec`/`status` split.)
- **Every artifact has ONE writer.** Several writers is a finding to close, not a convention to
  document.
- **Do not keep manually maintained bookkeeping fields.** A hand-updated "still valid?" flag or
  "last checked" date rots across hundreds of records by construction. Use a machine-written
  cursor, or derive it from data that already exists.

### Identity

- **Entity identity is minted, not derived.** An opaque identifier issued once, at first
  appearance, never recomputed; comparison is a separate mechanism unrelated to it. A key
  computed from mutable payload is silently redefined by the next update touching those fields.
  (Surrogate key, not natural key.)
- **Immutable values are the exception and MUST be content-addressed** — keyed by a hash of their
  content, not by position or row id. No conflict with the rule above: something with a lifecycle
  is an entity and gets a minted id; something that simply *is* its content is a value, and
  content addressing makes "this reference now points elsewhere" impossible rather than guarded
  against.
- **A key that resolves to several entities is an anomaly, not a coincidence.** It is revoked;
  the entities are not merged.
- **An unreliable value is not a key.** A field whose provenance is doubtful yields no key at
  all, rather than a doubtful one.

### Boundaries

- **Every layer declares what it needs, not the union of what its sources provide.** A schema
  shaped by its suppliers cannot be closed, and an open schema swallows field-name typos in
  silence. (Ports and adapters; the anti-corruption layer.)
- **Validation belongs at the entrance, not at the exit.** With shape, identity and reachability
  checked on admission, a flag marking a value "possibly untrustworthy" has nothing left to
  distrust. Convert to the internal type at the boundary. ("Parse, don't validate"; make illegal
  states unrepresentable.) **An obligation enforced only at construction is edge-triggered**: it
  holds for what the constructor saw, not what the object became, and whatever the invariant
  reads is usually reconfigurable afterwards. Construction-time enforcement makes a violation
  hard to WRITE; re-deriving it from current state keeps it from EXISTING. Measured — both.
- **Structural invariants live in ONE function**, used by the loader (which raises) and by the
  validator (which collects). Do not store what the structure already determines.

### Schema change

- **The migration asymmetry follows version control, not importance.** Removing a field from a
  model whose data is versioned needs a data migration in the SAME commit, or a fresh clone fails
  validation. For unversioned, machine-written state the opposite holds: add fields with defaults
  and never migrate. Where both readers and writers must move, use the canonical two steps —
  widen, migrate, narrow (expand/contract).
- **Closed set versus external vocabulary:** a code-level enumeration if the code BRANCHES on the
  value or it is an ordered scale; an external, data-file vocabulary validated in CI for nominal
  classification. Substantive content must be replaceable without editing the schema.
- **Cut fields with zero consumers.** Field inflation is the default trajectory, not an
  accident: measure who actually reads each field before adding the next one.
- **Guard the human decision against HISTORY, not a file's presence.** A machine cannot tell a
  rewritten baseline from an honest one, so a check reading only the current file is bypassed by
  deleting and regenerating it: the breaking change is absorbed, the diff's version line never
  moves. Compare against the committed baseline at the branch point; where nothing is comparable
  say "nothing compared" rather than passing. Measured — any approval encoded as a file's
  contents is revocable by whoever can delete the file.

---

## 5. Derived state

- **A derived layer must be reconstructible from its source alone, and NEVER writes back into
  it.** Reconstructibility is the invariant; full rebuild is merely its cheapest guarantee.
  Incremental derivation is legitimate — and necessary at scale — only while a full rebuild would
  produce the same result, and that equivalence is tested, not assumed.
- **A byte-compared artifact must be reproducible byte for byte** — across processes and
  dependency upgrades, or the comparison reports drift that did not happen and blames the source.
  `repr()` is the standard trap: it embeds memory addresses for some objects, and changes for
  others when the library adds a field. Project the property you mean rather than serialising
  whatever the object prints, and pin the reproducibility with a test.
- **A derived view's notion of "public" must come from the SOURCE, not the runtime namespace.**
  A namespace also holds its imports, so surveying it is at once too wide — imports and language
  machinery look exactly like model surface — and too narrow, since whatever the classifier has
  no branch for falls silently out. Read declarations; give every leftover an explicit role, so
  nothing is classified by an `else` nobody reads.
- **Tools that walk packages are blind to a directory without an initialiser** — a whole subtree
  can sit inside a checked boundary while every contract reports kept. A filesystem walk and a
  package-graph walk disagree exactly there; make the configuration that hides a subtree an
  error, not a style choice.
- **Label the provenance of every derived element from day one**, with more values than currently
  needed (human-curated / deterministically derived / reserved for inferred). Not speculative
  generality: the label's domain is persisted, widening a persisted domain later is a migration,
  and an unused value now costs nothing.
- **A stable primitive that never leaves its own layer protects nobody.** If consumers can only
  address something by its unstable coordinate, the stable one may as well not exist — publish it
  in the interface people actually use.
- **Two-level incrementality:** the unit of re-derivation and the unit of expensive recomputation
  are different objects with different keys. Identical content shared by many carriers then
  collapses to one expensive computation.
- **One entry point per capability**, with an honest degraded mode instead of a silent failure
  when an optional component is absent.
- **A gate applied by one caller must be applied by all of them.** When adding a consumer of an
  expensive, sensitive or rate-limited path, ask explicitly: *how many exits are there, and is
  the gate on every one?* The third ungated door is found by that question, never by a bug report.
- **Distinguish an implementation by type, not by a name string,** whenever the calling code
  holds a heterogeneous collection of already-constructed objects. Comparing a configuration
  string is valid only while one choice governs the whole run.

---

## 6. Reconciliation and batch work

- **Derive the work from the state of the world, not from a stored flag.** A repeat run is a
  no-op and the system self-heals. Level-triggered, not edge-triggered: reconciliation repairs
  historical inconsistencies, not merely prevents future ones.
- **Separate planning from execution.** A dry run writes nothing, takes no lock, touches no
  network, and prints the same plan the real run would execute, computed by the same selection
  functions. Two code paths that can disagree defeat the purpose.
- **The failure of one item never breaks the batch** — catch at the item boundary, report per
  item, continue. **But an aggregate failure rate above a stated threshold must abort the run**:
  isolation without a circuit breaker turns a systemic outage into a silent flood of
  individually-logged failures.
- **Failure isolation holds only while nothing further down re-raises what was suppressed.**
  Suppressing a component's load failure in a registry is undone by a module-level import of the
  same component one floor up. Pin it with a structural test, not a comment.
- **Symmetric backoff across stages.** A pathological item must not repeat its cost every run;
  the same retry policy applies to every expensive stage, not just the first, and an item that
  keeps failing is quarantined rather than retried forever.
- **Prefer a single writer to a lock.** Where concurrent mutation is genuinely possible, ONE lock
  excludes ALL mutators — including maintenance modes and every subcommand of every entry point.
  A lock covering only the first pair of writers you happened to find is not a lock.
- **A cursor suppresses OUTPUT; a cache suppresses WORK.** A cursor permanently masks items never
  actually processed, and the run still looks clean. Prefer caching the raw input; deduplication
  alone usually makes a repeat run cheap.
- **An adapter returns its full current view of its source; the core holds no adapter state.**
  Filtering out what is already known is one dedicated component's only job.
- **Hand another layer the finished result, not a copy of your check.** Two implementations of one
  rule WILL drift, and they drift on a data shape the fixtures do not reproduce.
- **A hint is not a verdict.** A cheap upstream guess may be recorded as a hint and overridden by
  an explicit decision; it never silently becomes the authoritative value.

---

## 7. Extension points

**A new variant is one ENTRY, not an edit to the core.** A dispatch table keyed by the
discriminator replaces `if/elif` chains and makes the extension point explicit and countable
(open/closed, applied concretely). Each entry carries its own version; bumping it invalidates
exactly what that entry produced and nothing else.

---

## 8. Heuristics, thresholds and calibration

- **Constants calibrated on one sample do not transfer.** Every new input class needs a live check
  on real data, not carried-over numbers.
- **Once it works, calibration is FROZEN.** Change it only on (a) a defect blocking the actual
  downstream use, (b) three or more defects of the same shape, or (c) a genuinely new input class.
  The alternative to endless re-tuning is escalating that case to a more expensive path. State the
  freeze explicitly — an unstated freeze is indistinguishable from neglect.
- **A full manual audit runs only for a new path's FIRST item.** After that: automatic quality
  signals plus a spot check.
- **Where a mistake produces a wrong answer rather than no answer, keep the heuristic narrow and
  refuse to generalise it.** A false positive costs more than a miss whenever the output is
  consumed as fact.
- **Do not "repair" degraded input by guessing.** A visible imperfection is safer than a plausible
  fabrication.
- **Pin regression fixtures to a FIXED subset**, so they are not rewritten as the data grows —
  otherwise the oracle tracks the code instead of constraining it.

---

## 9. Expensive, opaque or non-deterministic components

Applies to anything whose output cannot be fully predicted or cheaply reproduced: an external
API, a model, a heavy computation, a third-party service.

- **Compare against a cheap independent witness on invariants that must hold.** A divergence is
  recorded as a defect and does not block — the dangerous failure mode here is a plausible wrong
  answer, not a crash — and the report names the divergent values, never "mismatch". (A parallel
  run against the cheap implementation; the shape of shadow-testing a rewrite.)
- **Agreement between two implementations does not prove correctness** — independently written
  implementations still correlate in their errors. But agreement AGAINST a reference is strong
  evidence the reference is wrong.
- **Embed foreign output inside an explicit bounded block** — opening marker, sanitised content,
  terminator — with the grammar owned by ONE module shared between producer and consumer.
  Sanitisation neutralises anything that would restructure the host document. Treat the content
  as data, never as instructions.
- **Validate generated output by running it through the real consumer, not a syntax checker.**
  Syntactically valid output can still be wrong in use.
- **Checkpoint long batches** so a failure loses at most one batch and a restart catches up
  incrementally. The resumable unit must be idempotent — recovery is at-least-once, so a replayed
  batch has to be harmless. Verify with an actual kill, not by reading the code.
- **Retry armour lives in ONE shared client:** backoff with jitter, retry on transient statuses
  and network errors, and detection of an error delivered inside a success response. Other client
  errors fail fast.

---

## 10. Tests and gates

- **The local full-gate command mirrors the CI filter byte for byte**; on divergence reconcile
  against `.github/workflows/ci.yml`, not against memory or documentation. The mutation harness
  (`-m heavy`) is a separate workflow, not a step of this command — own check-list entry, own
  file (`.github/workflows/mutation-stand.yml`), costing several times the six together. It is
  the evidence the six can fail: run it before pushing anything that touches a check. The local gate:

  ```
  ruff check \
    && git ls-files --cached --others --exclude-standard '*.py' | xargs -r python -m mypy \
    && python -m pytest -m "not heavy" --cov --cov-report=term-missing \
    && PYTHONPATH=src lint-imports \
    && python tools/truth.py \
    && python tools/schema_lock.py
  ```

  `PYTHONPATH=src` on lint-imports is the single concession to a src layout without an installed
  package; tools and pytest resolve `src/` themselves (`pythonpath`/`mypy_path` in pyproject,
  own-location bootstrap). **No path list, and that is the point:** each tool finds its targets
  from `pyproject.toml`, and mypy is fed exactly the files git would commit — so git, not a second
  hand-maintained copy of `.gitignore`, decides what is ours.
- **"It passes" means the WHOLE gate, never a corner of it.** Reporting a subset as the gate is
  the cheapest way to certify a defect absent; a check that never ran cannot have passed. Name
  which steps were executed.
- **Structural fix for "a filter string copied by hand into N places":** an umbrella label applied
  by a collection hook to anything carrying an underlying label. The gate command then never
  changes again, and a new label means editing one list in one file. Hand-maintained copies drift
  independently, so syncing one never guarantees the others.
- **Mutation testing is what makes a green gate mean anything**: plant one defect in each check in
  turn and demand a red suite. Two properties keep the harness honest. Anchors must match EXACTLY
  once, checked cheaply every run, so a moved line surfaces in seconds rather than after the slow
  pass. And a CONTROL — the untouched copy — is mandatory: a red control invalidates the whole
  run, not its own line, since with the inner suite stopping at first failure every mutation then
  reads as killed by the pre-existing break. Measured — a broken control once produced a full
  column of green with nothing behind it.
- **Tests are hermetic against production artifacts BY CONSTRUCTION, not by discipline.** A
  fixture snapshots production files and DIRECTORIES around every test and fails naming the file.
  Watch directories, not a list — "remember to extend the list" is the hole the guard closes. A
  test invoking an entry point passes explicit temporary paths, since argument defaults point at
  production. **A test subprocess must also compile from source** (`PYTHONDONTWRITEBYTECODE`):
  bytecode caching keys on size and mtime-to-the-second, so a same-length edit inside one second
  leaves a stale `.pyc` and the check runs against code that no longer exists, reporting OK.
  Measured; found only because an unrelated control went red.
- **Silent corruption of local state is worse than a crash**: it steals time unnoticed, and a
  self-healing system masks it perfectly.
- **Property-based testing is the default for code with algebraic invariants** (geometry,
  intervals, parsers, merges). Trap: filtering two independently generated values discards most
  examples; CONSTRUCT the value around the known one instead.
- **Before copying a test methodology to a "similar" file, verify the same diagnostic sign is
  present**, or the work duplicates something already done.
- **Structurally unreachable defensive code is documented as an accepted remainder** — not tested,
  not deleted, not left looking forgotten.
- **A fixture encodes its author's imagination of the data's shape**, so a green gate is blind to
  shapes the author did not imagine. After merging, run the output against production data and
  analyse it STRUCTURALLY — counts, distributions, invariants — not by eye.
- **Coverage discipline.** Measure the baseline with EXACTLY the command CI runs — a wider run
  gives a higher, unusable number — and take it from the live CI log, never a config comment,
  which is a snapshot as of its last manual edit. Exclude self-covering test files and
  never-executed wrappers. Verify the threshold affects the exit code: a config setting may only
  warn. Raise it on organic growth, not on a schedule; treat it as a floor catching regressions,
  never a goal. A line-coverage figure says nothing about whether assertions would fail if the
  code broke.
- **Failures must be separately attributable — by whatever costs least.** Separate jobs when they
  need different environments or one is slow enough that parallelism pays; otherwise per-step
  statuses in one job, since a shared install usually dominates. Either way, a step whose
  prerequisites are structurally absent reports "nothing ran" — translate that explicitly rather
  than letting it read as success.

---

## 11. Operating policy

- **Artifact language is fixed by class, not by convenience.** **Code is English-only —
  identifiers, comments and docstrings alike**, whatever language the team speaks; the team's own
  language lives in live dialogue and project documentation (here: Russian). No "new code only"
  carve-out — a comment or docstring you touch is left in English — and no mass-translation
  campaign either, since nothing untouched has to move. A rule, not a preference: a
  mixed-language codebase makes every concept search return half its hits.
- **Cost and budget never enter a versioned artifact** — no amounts, tariffs, balances or
  estimates in tracked files, commit messages, review descriptions, comments or docstrings. Even
  qualitative hints get rephrased in time or operations. History is not rewritten; it is enough
  that the information leaves the tip and does not reappear.
- **Do not claim a background process will survive closing the host application** without
  empirical verification. Process-ancestry analysis is not evidence — an invisible third
  mechanism may govern the lifecycle. Checkpoint first, daemonize second.
- **Do not quote batch duration from a documented per-unit figure.** Real cost scales with the
  derived unit count, not the input count, and with memory pressure on the actual machine. Check
  the current load before giving a number.
- **Feasibility gates before quality discussion** for any third-party component: hardware
  compatibility, licence — of the code AND of bundled artifacts — and dependency weight from a
  real dry-run install. A component that cannot be installed need not be compared.
- **Verify a service against a real target, not against its documentation.** Something that
  works in principle may be blocked in practice at exactly the target class you need.
