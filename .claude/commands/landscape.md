---
description: Compare a named third-party technology against this stack before a pending decision
argument-hint: <target name(s)> -- <decision it serves> [-- <subsystem in scope>]
---

Compare a NAMED external solution (product, framework, library or approach) against this project's stack, as evidence for a decision that is about to be made.

A PRE-DECISION check, not a market survey — the heavyweight version of the spec command's world-grounding step. Run it BEFORE drafting the spec; feed the findings into it. Sweep mode ("scan the landscape of X") is unsupported: unnamed searches return listicles, and verification does not scale to a dozen objects. Paraphrasing READMEs scales; proving claims does not.

**Inputs, from `$ARGUMENTS`:** one to three NAMED targets — a repository, package or product. If given a theme instead, ask for names; do not invent a shortlist. Plus: which decision this serves, and which subsystem is in scope (`core` / `convert` / `acquire` / `browser` / `discovery`). Most tools touch one subsystem; scoring them on the others is a strawman — declare those out of scope explicitly.

## Do NOT run when

- **No decision is pending.** Curiosity is not a trigger: this check is expensive and biased toward finding "gaps".
- **The area is frozen.** A freeze is lifted by its own stated trigger, not by the appearance of a competitor.
- **The bottleneck is not architecture.** If the honest answer to "what unblocks this project today" is more data, more users, or a decision nobody has made — say so and stop.

## Step 1 — Measure our side FIRST

Before reading anything the target publishes; their framing anchors judgement, numbers do not. Take real figures from real artifacts: sizes and counts from the actual store, dependency footprint, a real test and coverage run. Read the modules in scope, not `CLAUDE.md`'s summary of them. Extrapolate to the project's target scale and show the arithmetic.

## Step 2 — Verify the target by archaeology, not by README

READMEs describe intent; commits describe reality. **Precedent:** a search summary reported a project as "actively maintained" — it had read outsiders' issue dates as maintainer activity; the default branch was over a year stale and CI had been deleted. Never accept a maintenance claim from a summary or a landing page.

1. **Maintenance** — last commit to the default branch, last release, CI presence, open issue and review counts, whether maintainers reply.
2. **Dependency weight** — resolve it for real with a dry-run install in a throwaway environment, then delete it. Report the package count and any heavy transitive pulls. Check for a lighter install path and report it: fairness to the target is part of the method.
3. **Licence** — of the code AND of any bundled artifacts or weights, whose terms are routinely different and more restrictive.
4. **Declared scope** — quote what the project says it does NOT do. That is usually its most honest paragraph.

## Step 3 — Feasibility gates (before any quality discussion)

What cannot run here is not a candidate, however good. Check against real constraints, not remembered ones: hardware; the inputs actually present in this project; offline reproducibility of derived artifacts; and any standing prohibition recorded in `CLAUDE.md`. Published benchmarks remain hypotheses until a local comparison on this project's own evaluation data. Never recommend a swap on benchmark evidence alone.

## Step 4 — Report in three categories

**A · Findings about US** — ceilings and defects the comparison exposed in our own stack; historically the highest-value output, actionable without adopting anything.
**B · Confirmed rejections** — earlier decisions re-validated with current evidence; a recorded negative result prevents reopening the question.
**C · Genuine gaps** — target capabilities we lack that survived Step 3.

State plainly where the target is stronger. **A comparison that finds only our own advantages is a failed comparison and must be reported as such.**

Proposals — categories A and C only, at most three in total, three to ten lines each:

```
Proposal:  <slug>
Kind:      A (defect in us) | C (gap versus target)
Gap:       <what we lack, one sentence>
Evidence:  <the measured fact from Step 2 or 3 that proves it>
Conflicts: <existing project decision this touches — or "none">
Cost:      <one spec / one commit / research needed>
Route:     docs/core/charters/improvements.md § <n>
```

Proposals land in the backlog only — **never** in the roadmap or its queue. Prioritisation belongs to the person who owns the project; the queue is generated, not hand-edited. Drafting the spec is a separate command.

**Never:** run sweep mode or assemble an unnamed shortlist · install or benchmark a competitor without explicit approval (metadata probes only — dependency resolution, artifact sizes, repository archaeology; a large download needs a decision, not an assumption) · edit specs, the roadmap or the queue · recommend adoption on published benchmarks alone · reopen a frozen decision without a stated trigger.

**Report:** the targets and the decision they serve · our measured baseline · Step 2 evidence with raw numbers · which gates passed and failed · the three categories · zero to three proposals — zero is legitimate, and "adopt nothing" is a valid verdict. Close by naming the next step: proceed to `/tech-spec`, or record the confirmed rejection and stop.
