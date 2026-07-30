---
description: Turn a feature/change request into a grounded, structured specification on its own branch
argument-hint: <feature or change request>
---

Turn a feature or change request into a structured specification, following this repo's `docs/*/tech_specs/*/spec.md` convention.

Take the task description from `$ARGUMENTS` (falling back to the surrounding conversation if no arguments were given) as the primary input. Everything below is a DEFAULT — an explicit instruction in that request (different length, different process, different location) overrides it.

## Cross-cutting principle — grounded in current reality, not assumed

A spec is judged by two things: whether it fits the actual codebase (not an imagined one), and whether it fits the actual world as of today (not a training-data snapshot). Apply both on every pass — draft, critique, finalize:

- **Code grounding:** every concrete claim — file path, function name, schema field, config key — must be verified against the real repo, not assumed from a similar-looking prior project (in particular, not assumed from the predecessor repo this one is migrating out of).
- **World grounding:** any claim about an external fact that changes (a service's pricing or limits, a vendor's current behaviour, a dependency's current best practice, a third party's status) MUST be checked live before it goes in the spec. The training cutoff is already stale relative to the current date, and this check has caught real mistakes.

## Project invariants

Every spec is checked against these in Step 3. Source: `docs/old_repo_audit/data_architecture_diagnosis.md` §5 ("Целевая архитектура" — the four target-architecture principles), already established for this project rather than invented here; each invariant below is that document's principle restated as a spec-time check.

1. **Identity is minted, never derived.** An entity gets an opaque id once, at first appearance, and it is never recomputed; comparison is a separate mechanism with no relation to the identifier. A key that resolves to several entities is an anomaly and is revoked — the entities are never merged. A spec that derives an id from mutable payload fields, or merges entities on key collision, is wrong regardless of how well it is implemented.
2. **Every layer declares a port, not a union of what its sources happen to provide.** A new module under `src/` defines its own minimal input type — exactly the fields it actually reads — rather than depending on, or reintroducing, the predecessor's monolithic schema (`core.schema`, `CandidateRecord`, `SourceRecord`). Check: `rg -n "core\.schema|CandidateRecord|SourceRecord" src/` must return nothing for any path the spec touches.
3. **A decision is a first-class entity, symmetric for accept and reject.** One model, one durability, one validator for both outcomes — never an accept-path that is versioned and gated next to a reject-path that is neither.
4. **Validation happens at the boundary, not at the exit.** Reachability, shape and identity are checked on admission; a spec must not introduce a provenance flag whose only job is to mark a later value as "possibly untrustworthy" downstream — if the boundary check is real, there is nothing left to distrust.

**Note (temporary, remove once it stops applying):** there is no CI-enforced coverage gate yet (no `.github/workflows/` in this repo), so a numeric quality-floor invariant cannot be stated truthfully. Until CI exists, the test-coverage section (below) describes coverage qualitatively — which new paths get unit vs. integration tests, and at what depth — rather than citing a floor percentage. Add a fifth invariant here, pointing at the live CI job, the first time CI is wired up.

## Step 1 — Ground the spec in reality

Read: the `src/` modules the spec will touch; the schema or type definitions it extends (new fields must extend them correctly, not duplicate or contradict them); any controlled vocabularies or configuration it depends on; two or three existing specs matching `docs/*/tech_specs/*/spec.md` for tone and structure (there may be none yet — this repo is pre-first-spec; if so, match the tone of `docs/migration_extraction_plan.md` instead); the root `CLAUDE.md`; the project memory index (`MEMORY.md`) and the entries it links; and `docs/core/charters/improvements.md` — many specs originate as a backlog item there.

If the spec depends on an external fact, verify it live now — see "World grounding" above.

## Step 2 — Draft (round 1)

Write an initial spec: problem and goal, technical approach, affected files and modules, test coverage needed, commit breakdown. Base it on the user's requirements plus Step 1 research.

## Step 3 — Adversarial self-critique (round 2)

Re-read the round-1 draft as a skeptical senior reviewer, not as its author. Look for: wrong assumptions about existing code or schema; missing edge cases; unstated scope boundaries; unverified external claims that need a live check instead of an assumption; violations of the project invariants above; gaps in the test plan; an unrealistic commit breakdown. List concrete objections, then revise to address each one.

If a genuine multi-way tradeoff remains that only the user can resolve, capture it as an open question (Step 5) rather than picking silently.

## Step 4 — Verify (round 3, when warranted)

Run a third pass only if round 2 raised material issues or the task is unusually complex. Re-check every file, function and field reference against the repo by reading and searching, not from memory; confirm no contradictions between sections; finalize wording.

Only the synthesized final spec goes in the document — never the round-by-round working.

## Step 5 — Assemble the document

Aim for concision, but do not force it: a spec legitimately runs long when it combines schema changes with policy rationale and a recorded adversarial-critique trail. The "Design rationale" section below has repeatedly caught real flaws in this method's original use — do not compress it away to hit a line count.

```
# Spec: <feature name>

Status: draft v1 · <date>
Branch: `feature/<slug>`
Origin: <if grown from the backlog, name the item; else omit>

## 0. What and why
<problem, motivation, one-line scope boundary>

## 1..N. <technical sections>
<concrete, file- and field-referenced, no filler>

## Design rationale / rejected alternatives
<alternatives considered and why rejected — the Step 3 record>

## Test coverage
<the tests this spec requires, one bullet group per commit in the plan below. Unit tests by default, CI-safe unless explicitly marked; call out where an integration test is the honest way to cover a path a unit test would only fake. Until a CI coverage gate exists (see the temporary note above), state test depth qualitatively rather than against a numeric floor>

## Commit plan
<numbered roadmap, one line per commit, conventional-commit prefixed>

## Implementation checklist
<unchecked boxes mirroring the commit plan — the implementation command ticks these off>

## Open questions
<unresolved forks only the user can decide — omit if none>

## Out of scope
<explicit exclusions, and the trigger that would bring one back in — optional>
```

Status values are a small fixed vocabulary, so the implementation command can detect state unambiguously: `draft v1` (this step's output) → bump the draft number after a material revision, e.g. resolving open questions with the user → `implemented (PR #N)`, set by the implementation command once the review is open, never by this one.

Design documents in this repo are written in Russian (the convention already used in `docs/migration_extraction_plan.md` and the `docs/old_repo_audit/` files) — section headers stay in Russian; only these instructions are English.  Match the tone and terseness of existing specs: concise, technical, file-referenced, no marketing language.

## Step 6 — Place the file

First pick the functional section the spec belongs to (`core` / `convert` / `acquire` / `browser` / `discovery`), matching the code layer it touches; add a new section directory only if none fits. Then create a subfolder under it, kebab-case slug: lowercase, ASCII, no spaces or shell-special characters, derived from the feature itself — not a copy-paste of the user's raw phrasing. The file is always named `spec.md`, because the implementation command globs for it. Umbrella documents that decompose into several child specs go in that section's `charters/` directory under a different file name, so the scanner skips them.

This repo has no specs yet — creating the first one under a given section establishes the convention for that section; do not treat an empty glob match as an error condition.

If `docs/` is gitignored, just write the file to disk — do not stage or commit it. (Currently it is not gitignored.)

If this spec grew out of a `docs/core/charters/improvements.md` item, add a pointer line back to this spec's path in that item — the trace-forward convention that keeps idea and spec linked in both directions.

## Step 7 — Branch

Skip this step only if the work is trivial enough for a direct commit to the main branch — rare, since this command exists for substantial tasks.

1. Fetch, then create `feature/<slug>` off an up-to-date main. Local branch only — do not push yet: if the spec file itself is not tracked there is nothing to commit at draft time, and pushing an empty branch clutters the remote with refs for specs that may never be built.
2. Write the spec file (Step 6).
3. Confirm CI already covers the branch by wildcard — moot until CI exists (see the temporary note above); once it does, registering the trigger is part of this step.

⚠ A branch created now may sit unused for weeks while other work merges. Before implementation begins, it must be checked for drift — see the implementation command's Step 2.

## Step 8 — Report

State the spec path, the branch name and its push status, and confirm CI coverage (or note plainly that CI does not exist yet). Do not start implementation — that is a separate command.
