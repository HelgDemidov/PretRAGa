"""Session-hook entry: print a one-line reminder of the 6 soft design_truth axes
(CLAUDE.md §3, point 6; charter §2.5) on edits to production code.

Deliberately NOT under tools/: it asserts nothing and checks nothing, so subjecting
it to the guarded-tool mutation requirement (CLAUDE.md §10) would be theatre — there
is no computed claim here for a planted defect to falsify. The six axes it names are
themselves checked by human judgment at the decision, not by CI (charter §2.5) —
mechanizing the reminder past a static nudge would contradict that same design.

Always exits 0 and never sets decision:block — advisory only, on every edit in scope,
no attempt to detect "is this decision-scale" (that judgment is exactly what CLAUDE.md
§3 already asks the session to make; a hook approximating it would just be a second,
unverified guess sitting beside the real one).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMINDER = (
    "[axes] production code touched under src/pretraga/ — if this decision touches one "
    "of the 6 soft design_truth axes, confirm and record it: provenance-status · "
    "cross-ref identity safety · artifact owner (human/machine) · port failure-mode "
    "choice · spec-readiness · constant calibration (CLAUDE.md §3, point 6; "
    "design_truth charter §2.5 — human judgment, not CI)."
)


def hook_mode() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — malformed hook input must never crash the hook
        return 0
    file_path = str((payload.get("tool_input") or {}).get("file_path") or "")
    root = str(ROOT)
    if not file_path.startswith(root + "/"):
        return 0
    rel = file_path[len(root) + 1:]
    if not rel.startswith("src/pretraga/"):
        return 0
    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": REMINDER}}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(hook_mode())
