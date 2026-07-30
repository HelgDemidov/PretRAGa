---
description: Sync CLAUDE.md, memory, and design docs after a merge to main
---

Sync project documentation and long-term memory after a merge into the main branch.

Read the recent history and the merged diff to understand what changed. Then perform ALL of the following steps, in order, without skipping.

## Step 1 — Update the root instruction file

Update ONLY sections of `CLAUDE.md` that are factually outdated because of the merged change:

- new modules under `src/`, new schema fields or controlled vocabularies, changes to the stages of a documented flow;
- changes to commands, environment variables, the dependency setup, or CI structure;
- new architectural constraints or "do NOT" rules — tool choices, hardware limits, encoding risks.

Do NOT add micro-patterns or implementation details — only architectural and infrastructural facts. Keep sections tight; do not bloat the file.

**Ratchet rule (anti-rot):** any section you edit must be re-verified WHOLESALE, not merely appended to. Before finalizing, check every identifier, constant, path and status claim in that section against live code and history, and fix the stale ones you find. Additive-only edits are exactly how an instruction file rots between audits.

**Replace, do not accumulate.** This extends past individual claims to whole paragraphs: when the merged change is the Nth instance of an already-documented pattern, do NOT append a parallel paragraph for the new instance. Consolidate into one description of the pattern plus what is genuinely new this time, and drop or compress now-redundant specifics — exact historical counts, resolved narrative arcs, superseded framing — from the earlier instances. A section's length after the edit should stay flat or shrink, not grow with every merge that touches it.

## Step 2 — Update or create memory files

Read the memory index at `MEMORY.md` (in `/home/fastcentrifuge/.claude/projects/-home-fastcentrifuge--------------Projects-Dev-PretRAGa/memory/`). For each significant change in the merged work, decide:

- **new subsystem or feature** → create a `project` entry;
- **architectural decision with lasting consequences** → create or update a `project` entry;
- **tooling or process lesson learned** → create or update a `feedback` entry;
- **new external resource** → create a `reference` entry.

Body structure: lead with the fact or rule, then the **Why** and **How to apply** lines. Link related entries with `[[slug]]`. Update the index: one line per new file, refresh the description of changed files. Convert relative dates to absolute — "last week" is unreadable six months later.

Memory lives OUTSIDE the repository and is never part of Step 6's commit.

**Replace, do not accumulate — this matters more here than in Step 1.** Unlike `CLAUDE.md`, which is bounded by periodic audits, memory files have no natural pressure to shrink: unchecked appending compounds silently across every future session. Before adding to an existing file, check whether the new fact supersedes, resolves, or re-confirms-for-the-Nth-time something already recorded. A structural fix that closes a recurring problem the file was tracking should REPLACE the old blow-by-blow of prior occurrences with a tight summary of rule plus fix — not stand beside it as one more confirmation paragraph. A stale plan or decision superseded by what actually happened is rewritten in place, not left for a future reader to reconcile against the new fact sitting next to it. Target: total memory volume after a sync stays flat or shrinks even as new work lands.

## Step 3 — Update design and planning documents

If the merged branch had a specification under `docs/*/tech_specs/*/spec.md`:

- append or refresh a concise completion section — merge date, review number, commit hashes, what was done, what remains out of scope;
- tick the relevant checklist items.

**If the spec descended from a numbered item in `docs/core/charters/improvements.md`:** update that item's status AND, in the SAME pass — not "later" — collapse its body to one to three lines: status plus a pointer to wherever the rationale now permanently lives (the memory entry Step 2 just wrote, the spec's own completion section, or a line in `CLAUDE.md`). Do NOT leave the old multi-paragraph analysis in place "as a historical record": that record already exists at the pointer target the moment Step 2 lands, and a second copy here is exactly the duplication the backlog exists to avoid.

**Before collapsing, verify the pointer target genuinely contains the fact** — open it, do not assume from the title. A wrong or missing pointer is worse than an over-long body.

Items genuinely not done keep their full body — that is the backlog's one remaining job. Queue and priority content never belongs in this file at all; that is the roadmap's job exclusively.

## Step 4 — Regenerate and refresh the roadmap

If a roadmap directory mixing generated and hand-written files exists, first regenerate the automatic parts, then touch ONLY the manual files the merge actually made stale. (This repo does not have one yet — this step is a no-op until one is created; do not invent files to satisfy it.)

1. **Generated (always run, once it exists):** the inventory generator, which rebuilds the status tables and the cross-cutting queue from the same resolved status data — a spec whose status just flipped to a terminal value drops off the queue automatically, with no manual pruning. Never hand-edit inside the generated markers.
2. **The manual overlay:** edit only if ordering or an explicit priority override must change. Statuses NEVER live here — a newly drafted spec with no override is auto-numbered to the back of the queue by the generator itself.
3. **Descriptive maps of what the system does today:** refresh only if the merge changed the facts, and update the date in the header when you do.
4. **Target-state maps:** if a realized spec moved from target to current, update the remaining-delta notes.
5. **User-facing guides:** only if the flow a human actually runs has changed.

## Step 5 — Audit trigger check (report only)

Read the memory-sync audit's last-run record (`docs/memory/memory_sync/`). If it is missing, remind the user that `/memory-sync` has never run. Otherwise count merges since the recorded commit — if the count is at or above the threshold, tell the user it is time to run `/memory-sync` in a fresh session. **This step only reports; NEVER start the audit from here** — it is a different job with different rights over the same files.

## Step 6 — Commit documentation changes

Stage only TRACKED documentation. Do NOT stage untracked design docs, memory files, or a badge-stub README that this command does not touch. Commit with a message naming the merged branch.

Then report a short summary: what was updated and why.
