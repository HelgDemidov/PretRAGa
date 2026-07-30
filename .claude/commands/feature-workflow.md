---
description: Implement an approved spec end to end, commit by commit, to an open review
argument-hint: "[spec-dir-name | slug | path]"
---

Implement an approved but not-yet-implemented spec (`docs/*/tech_specs/*/spec.md`) end to end on its own branch, commit by commit.

Pick up a spec that has been reviewed and approved but not yet built, and take it all the way to an open review. Invoked as `/feature-workflow $ARGUMENTS`.

**⚠ CI does not exist yet in this repo** (no `.github/workflows/`). Every step below that reads a CI baseline or a CI-defined job name is currently a no-op — report that plainly ("no CI baseline exists yet") rather than fabricating a number or a job name. Wire these steps up for real the first time CI is added.

## Step 1 — Find the target spec

If invoked with an argument, use that spec directly.

Otherwise scan `docs/*/tech_specs/*/spec.md` for specs still awaiting implementation. The spec command writes a fixed status vocabulary near the top: `draft v1` (pending), progressing to `implemented (PR #N)` (set by this command's own final step) — select the ones still pending. Older specs predating the convention may use different wording; treat anything that is not the terminal value as pending. Umbrella documents matching `docs/*/charters/*.md` are intentionally NOT matched by the scan, and `docs/core/charters/improvements.md` is not a spec either.

- Zero matches → report that nothing is pending, stop.
- One match → proceed with it.
- Multiple matches → ask the user which one; do not guess.

If a spec's status is ambiguous, cross-check before building: if the work already exists in the code, or a merged branch already covers it, do not re-implement — report it as already done.

## Step 2 — Create or refresh the branch

Fetch first. The spec command normally already created a local, unpushed `feature/<spec-dir-name>` branch when drafting — check it out if present; otherwise create one off an up-to-date main. Never implement on main directly.

**⚠ Check the branch for drift BEFORE writing any code.** A branch created at drafting time can be weeks of merges behind. List the commits unique to it:

- **empty** → the branch is a stale snapshot, not unfinished work; a hard reset onto current main is safe and is the right move. Continuing without it produces a review diff full of unrelated deletions that revert other people's merged work.
- **non-empty** → the branch carries real unfinished work; a reset is FORBIDDEN. Rebase, or ask the user.

**Record the pre-branch coverage baseline NOW, from CI — not from any file**, once CI exists. The authoritative baseline would be the coverage of the latest successful run on main, from its log — never from a comment in a config file or from memory, since a written-down number goes stale while CI runs on every merge and stays current. Until CI exists, skip this and note in the final report that no baseline was available.

## Step 3 — Build the commit plan

Specs carry design sections rather than a ready-made commit list. Read them and turn the work into a task list in this conversation — one coherent, independently buildable unit of change per commit, ordered so that each commit passes its own tests on its own. Natural seams follow the dependency order of the layers the change touches.

The task list MUST include dedicated test-coverage tasks for the new behaviour — tests are commits like any other, not an afterthought.

Because you are inventing the breakdown and the spec does not dictate it, present the plan to the user for a quick confirmation before implementing. If the user has already approved a breakdown, skip the confirmation.

## Step 4 — Implement, commit by commit

Work one commit at a time: implement → run targeted checks for the files touched → commit with a conventional-commit message consistent with the repository's existing history → next. One logical change per commit; never batch unrelated work.

All checks run from the repository root, where the tool configuration lives (`pyproject.toml`):

- While iterating within a commit: **targeted only** — the linter and type checker over `src/`, plus the specific test files you touched.
- **The full gate at most once per commit**, immediately before committing:

  ```
  ruff check src && python -m mypy src && python -m pytest -m "not heavy" --cov --cov-report=term-missing
  ```

  This mirrors what `pyproject.toml`'s dev dependency group documents as the CI-equivalent local gate. Once `.github/workflows/ci.yml` exists, check it for drift before trusting this command verbatim.

The gate's exclusion filter (`not heavy`) is meant to be an umbrella label, applied automatically by a collection hook in `tests/conftest.py` to any test that depends on toolchains or data physically present on the developer's machine — such tests do not skip themselves locally the way they do in CI or a fresh clone, so omitting the filter silently adds real work with zero CI-relevant signal. **When adding a new toolchain-gated label, add it to the umbrella's list in the test configuration — the command in this file never needs to change again.** The once-per-commit budget matters on a constrained machine: use the full gate as the pre-commit checkpoint, not as a companion to every edit.

## Step 5 — Verify behaviour, not just tests

For any change with runtime surface, exercise the real system before wrapping up — a dry run, and a real execution against existing state — and confirm the observed behaviour matches the spec. Green tests are necessary, not sufficient. Where the system is built on reconciliation, confirm the invariant directly: a second run over unchanged state must be a no-op.

## Step 6 — Wrap up

Once all planned commits land:

1. Run the full gate one final time and confirm it passes.
2. **Measure actual coverage and confirm it does not weaken the quality floor** — once a floor exists. Run the exact CI command, read live from `.github/workflows/ci.yml` rather than assuming it has not drifted, once that file exists. A pass means the floor holds; report the resulting figure. If it drops below the pre-branch baseline recorded in Step 2 even while staying above the floor, that is real signal the new code is under-tested relative to the rest of the codebase: add tests before opening the review rather than treating the numeric floor as "good enough". Until CI exists, report the coverage figure from the local run and note that no floor is enforced yet.
3. Push the branch and open a review. The description summarises the spec's goal and scope and gives a test and verification plan, including the coverage figure. If `docs/` is not tracked, do NOT link or paste the spec — it will not appear in the diff; summarise its intent instead. (Currently `docs/` is tracked.) Report the review URL.
4. Update the spec's status line to `implemented (PR #N)` with the actual review number, and tick its checklist.

Do not merge yourself, and do not run the post-merge sync — both happen after human review, as separate steps.
