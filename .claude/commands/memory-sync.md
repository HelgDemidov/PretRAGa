---
description: Audit every checkable claim in CLAUDE.md and memory against live code
---

# /memory-sync — audit and synchronize project memory against the real repo state

A recurring task, not a one-off: bring EVERY checkable claim in the root instruction file (`CLAUDE.md`) and in the memory directory in line with the live code and history. Triggers: manually, on the post-merge reminder (N merges since the last run), or before a large batch of work that will rely on memory being correct. Run it in a fresh session, with this task alone in the session.

This is an audit of **truth, not completeness**: do NOT add new facts — that is the post-merge sync's job — only fix stale or false claims and flag unverifiable ones. Human fact-checking is impossible at this volume, which is exactly why the evidence discipline below is MANDATORY, not optional.

Paths: memory at `/home/fastcentrifuge/.claude/projects/-home-fastcentrifuge--------------Projects-Dev-PretRAGa/memory/`; audit working files at `docs/memory/memory_sync/` (worklist, last-run record, backup archive).

## 1. Sources of truth (descending priority)

1. **Live code:** `src/`, configuration and vocabulary files (`config/`), the build and tool configuration (`pyproject.toml`, `uv.lock`), `.github/workflows/ci.yml` (once it exists), `.gitignore`, and the command and skill definitions themselves (`.claude/commands/`).
2. **Version-control history:** log, merge list, review metadata.
3. **Filesystem:** path existence, directory layout, presence of generated artifacts.

NOT sources of truth — they are the patients themselves, or derivatives: `CLAUDE.md`, memory files, and all design documentation under `docs/`, which has its own sync process. Do not edit those or use them as evidence. One exception: a memory claim ABOUT a document ("the spec lives at path X", "it is queue position N") — then that file IS the evidence.

⚠ **Context contamination:** at session start your context ALREADY contains `CLAUDE.md` and the memory index (`MEMORY.md`). Before their audit, they are unverified. Knowledge "from your head" or from the starting context is NOT evidence — only fresh command output is.

The sync direction is strictly one-way: **code → memory.** Never "fix" code, tests or documentation to match memory.

## 2. Evidence discipline

- Every fix carries TWO pieces of evidence: (a) disproof of the old claim, (b) confirmation of the new one — a path and line, a commit hash, or command output. After fixing, re-verify the NEW text the same way: verify the fix, not just the defect.
- Verification means RUNNING a command, not recalling one.
- **Absence claims** ("the registry is empty", "there is no such consumer") require at least TWO independent search phrasings before being confirmed. One empty search is not proof of absence.
- If the code confirms neither the old nor the new phrasing → do NOT invent one. Mark the item unresolved in the worklist, add a dated "not confirmed by code" marker in the memory text itself, and move on.
- **Do not blindly trust "the more recently modified file wins"** when two memory entries conflict. If a live check is available, it overrides the timestamp heuristic even when it contradicts the file that was edited later.
- Keep evidence terse and in-flight: a short parenthetical in the worklist status cell, and the full evidence pairs in the final summary. Do not create a second persisted findings file — it duplicates the worklist and the summary, and then rots on its own.

## 3. Claim taxonomy and edit rights

| Class | Example | Verification | Executor's right |
|---|---|---|---|
| **C1 existence** | "function `f` in module `m`" | search | edit autonomously |
| **C2 value** | "the constant is 60", "the default is X" | search for the exact value | edit autonomously |
| **C3 status** | "merged in review #N", "queue position 6", "the registry is empty" | history, review metadata, two searches | edit autonomously |
| **C4 history** | "a live incident consumed 3.5 GB of swap", "the comparison showed 60%→100%" | code cannot disprove it; only internal consistency (the review exists, the files existed) | do NOT rewrite; flag only on a direct contradiction with a later, dated entry |
| **C5 norm or rule** | "an enum if code branches on it", "adopt only after a local comparison" | code illustrates, it does not disprove | do NOT rewrite; on a conflict between two norms the later DATED one wins; if the dating is ambiguous → unresolved, do not guess |

## 4. Different edit rights per memory type

- **`user`** — do NOT touch the body.
- **`feedback`** — the body (the lesson, the Why) is untouchable; audit only the **anchors**: paths, functions, flags, commands. A dead anchor → update it, or append "(mechanism retired; the principle still holds)". Deleting or weakening a feedback entry is FORBIDDEN.
- **`project`** — full C1–C3 audit, conservative on C4–C5. Rationale and rejected alternatives are class C4.
- **`reference`** — out of scope; verifying external resources is a separate task.
- **Autonomously deleting a memory file is FORBIDDEN.** Flag wholly stale files as deletion or compression candidates; the user decides.
- **Anti-bloat:** file size after editing must not exceed the original by more than about a tenth. If an honest fix needs more, flag it unresolved instead of bloating. Copying prose between `CLAUDE.md` and memory, in either direction, is forbidden. Do not hedge claims that were just CONFIRMED by code.
- **Replace in place; do not append a correction — this matters MORE here than in the post-merge sync.** Memory has no natural pressure to shrink between audits, so every accepted append compounds silently until this command catches it. When a C1–C3 claim is stale, rewrite the sentence to state the current truth directly — never leave the old wording standing beside a corrective note. If the fix cannot be expressed as a clean in-place replacement, because the surrounding paragraph is built around the now-stale premise rather than one wrong value, that paragraph is a **compression candidate**, not a one-line fix: flag it, do not patch a correction around it, and do not execute the compression yourself.
- **"Pointer over copy" diet:** mark content fully derivable from code or `CLAUDE.md` as a compress-to-pointer candidate. Flag, do not compress.
- Leave metadata untouched except the one-line description, and only if the body edits made it inaccurate.

## 5. Execution order (phases; checkpoint after each file)

**Phase 0 — safety net and working files.** Every artifact in this phase is runtime state for ONE run, not project history; do not let it accumulate across runs — otherwise a tool built to trim tails grows its own tail on disk.

1. **Backup — a single archive, with one-generation rotation: exactly two archives on disk at all times, never more, never zero.** One compressed archive of the memory directory, never a loose directory of files. If you need to inspect it, extract to a temporary directory, do the work, re-archive — never leave it extracted between operations. On a NEW run: delete the older archive, demote the current one, then take a fresh snapshot. On RESUMING an interrupted run of the same session: do not touch it, it is already valid. No dates in the file name — do not spawn a generation per run.
   *Why rotation and not deletion-after-acceptance:* memory lives outside version control, so without a backup the edits are irreversible, and a single copy means a second bad run in a row erases the only safety net before anyone notices.
2. **Worklist.** If it exists from a previous run and every item is complete, that is a finished prior run: overwrite from scratch, do not append. If it exists but has pending items, that is an interrupted run of this same session: continue from the first pending item, do not recreate.
3. Update the worklist AFTER EVERY file — the session must survive context compaction or a dropped connection. The protocol is idempotent; re-passing over a done file is safe.

**Phase A — `CLAUDE.md`** (the heaviest artifact; go first). Section by section, verify every C1–C3 claim. It is a map of the CURRENT state; historical asides are legitimate as long as their bottom line about the present is correct. Do NOT restructure, shorten or restyle — targeted factual fixes only.

**Phase B — `project` memory.** Build the file list from `MEMORY.md` AND from a directory listing: audit files outside the index too, since an index/directory mismatch is itself a finding for Phase D.

**Phase C — `feedback`, `user`, `reference`** — anchor audit per §4.

**Phase C2 (optional, if session budget remains) — the command and skill definitions themselves** (`.claude/commands/*.md`). Anchor audit only, same rules as `feedback`: never rewrite a protocol body. These files are not exempt from rot — a dead path in a protocol has been found before, and this repo's own command files were freshly instantiated from a portable template, so their placeholder resolutions (paths, the gate command, `SUBSYSTEMS`) are exactly the kind of anchor this phase should re-check as the codebase grows.

**Phase D — cross-consistency:** (1) every cross-link resolves to an existing entry — a broken link is a flag, not a deletion; (2) `MEMORY.md` matches the actual content of the files; (3) contradictions between entries, resolved by rule C5.

**Phase E — wrap-up:** (1) compose the summary DIRECTLY in the reply — N checked, M fixed with their evidence pairs, and a separate list of unresolved items, warnings and deletion or compression candidates; (2) show the user that summary, that list, and the diff of `CLAUDE.md`; (3) on confirmation, commit ONLY `CLAUDE.md` — memory and design docs are never committed; (4) write the last-run record with the date and the current main commit, which the post-merge sync uses to count toward the next trigger; (5) do NOT delete the backup — rotation in Phase 0 is the only size-control mechanism, and the archive stays as the safety net until the next run. Leave the worklist as it is; the next run overwrites it. The final reply IS the durable record of what was found — no on-disk duplicate.

## 6. Environment constraints

- The audit is read-only work: do NOT run the full test suite, expensive computations, or any network call beyond fetching review metadata. Cheap validators and collection-only test runs are fine.
- Subagents only with the user's explicit approval.

## 7. Out of scope

Adding new facts; restructuring `CLAUDE.md`; verifying external references; editing code, tests or design documents; de-duplicating the backlog against `CLAUDE.md` — a separate task that depends on this audit's outcome.

## 8. Definition of done

Every worklist item is closed or explicitly flagged, with each flag explained inline; `CLAUDE.md` is committed after confirmation; the last-run record is written; the reply carries the full summary with evidence pairs and the flagged list. The backup stays on disk per the rotation rule.
