"""Conformance checker: the entity map is the curated truth; this tool diffs
observable reality against it and fails loudly on divergence. It NEVER rewrites
the map — divergence is resolved by a human decision (fix code, or edit the map
as an explicit design decision).

Check classes (grow as the codebase appears):
  1. map integrity        — delegated to entity_map_build.validate (includes
                            definitions-required and the closed vocabularies:
                            the map is the ONLY entry channel for entities,
                            terms, their definitions and their kinds)
  2. generated views      — entity_map.md and entity_glossary.md must equal a
                            fresh render of the map: catches both a forgotten
                            regeneration and a hand edit of a generated file
  3. code anchors         — every `implements` prefix must resolve on disk;
                            entities whose KIND expects an anchor and has none
                            are counted as pending (informational until src/
                            exists). Kinds that forbid anchors are excluded by
                            classification, not by a per-entity escape hatch
  4. orphan code          — python files under src/ not covered by any anchor
                            (active only when src/ exists)
  5. kind obligations     — unmet `required` obligations, reported as a named
                            registry rather than as errors: closing one is a
                            human design decision, not a repair

Modes:
  (default)          full check, exit 1 on errors
  --quick            same checks, terse output (for the session hook)
  --impact F [F...]  map changed file paths to affected entities (advisory)

Run: .venv/bin/python docs/system_design/design_truth/entity_map_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import entity_map_build
import yaml

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
SRC_ROOT = ROOT / "src"
MAP_FILE = HERE / "entity_map.yaml"


def load_map() -> dict:
    return yaml.safe_load(MAP_FILE.read_text(encoding="utf-8"))


def check_map_integrity(data: dict) -> list[str]:
    return [f"map: {e}" for e in entity_map_build.validate(data)]


def check_generated_views(data: dict) -> list[str]:
    """Both generated views must equal a fresh render of the map — anything
    else means a forgotten regeneration or a hand edit of a generated file."""
    errors: list[str] = []
    expected = {
        entity_map_build.MAP_VIEW: entity_map_build.render(data),
        entity_map_build.GLOSSARY_VIEW: entity_map_build.render_glossary(data),
    }
    for path, content in expected.items():
        if not path.exists():
            errors.append(f"views: {path.name} is missing — run entity_map_build.py")
        elif path.read_text(encoding="utf-8") != content:
            errors.append(
                f"views: {path.name} is stale or hand-edited — regenerate with "
                "entity_map_build.py (generated views are never edited by hand)"
            )
    return errors


def check_anchors(data: dict) -> tuple[list[str], list[str]]:
    """Returns (errors, info). Anchors must resolve; unanchored entities are
    pending — informational while src/ does not exist, so early design work
    is not drowned in noise the checker cannot yet act on.

    Which entities owe an anchor is decided by their KIND (`anchor: required`).
    A glossary term and a human-written data file have no code by definition,
    so they are never pending — and there is no per-entity opt-out that could
    be applied in bulk to silence this check."""
    errors: list[str] = []
    pending: list[str] = []
    for e in data["entities"]:
        anchors = e.get("implements")
        if not entity_map_build.anchor_required(data, e):
            continue
        if not anchors:
            pending.append(e["id"])
            continue
        for prefix in anchors:
            if not (ROOT / prefix).exists():
                errors.append(f"anchors: {e['id']} -> {prefix} does not resolve")
    info = []
    if pending:
        level = "ERROR" if SRC_ROOT.exists() else "pending"
        line = f"anchors: {len(pending)} entities without code anchors ({level}): {', '.join(pending)}"
        if SRC_ROOT.exists():
            errors.append(line)
        else:
            info.append(line)
    return errors, info


def check_orphans(data: dict) -> list[str]:
    if not SRC_ROOT.exists():
        return []
    covered = [p for e in data["entities"] for p in e.get("implements", [])]
    errors = []
    for py in SRC_ROOT.rglob("*.py"):
        rel = str(py.relative_to(ROOT))
        if not any(rel.startswith(pref) for pref in covered):
            errors.append(f"orphans: {rel} is not covered by any entity anchor")
    return errors


def impact(data: dict, changed: list[str]) -> list[str]:
    lines: list[str] = []
    truth_files = {str(p.relative_to(ROOT)) for p in HERE.glob("*")}
    for f in changed:
        if f in truth_files:
            lines.append(
                f"{f}: TRUTH ARTIFACT edited — this must be a design decision, not a way to silence a check"
            )
    hits = {
        e["id"]
        for e in data["entities"]
        for prefix in e.get("implements", [])
        for f in changed
        if f.startswith(prefix)
    }
    if hits:
        lines.append(f"affected entities: {', '.join(sorted(hits))}")
    if not lines:
        lines.append("no mapped entities affected (either unmapped code or non-code change)")
    return lines


def check_obligations(data: dict) -> list[str]:
    """Unmet `required` kind obligations, grouped by what is missing. Never an
    error: closing one means deciding what an entity is identified by, what
    invalidates it, or where it lives — a design decision, not a repair."""
    unmet = entity_map_build.obligations(data)
    if not unmet:
        return []
    by_what: dict[str, list[str]] = {}
    for eid, _kind, what in unmet:
        by_what.setdefault(what, []).append(eid)
    lines = [f"obligations: {len(unmet)} unmet kind obligation(s) — design decisions, not blockers"]
    lines += [f"obligations: {what} -> {', '.join(ids)}" for what, ids in by_what.items()]
    return lines


def run_checks(data: dict, quick: bool) -> int:
    errors: list[str] = []
    errors += check_map_integrity(data)
    if not errors:
        # Rendering assumes the invariants integrity just verified (resolvable
        # relation endpoints, triggers, definitions, conventions) — checking
        # view freshness against an invalid map would crash, not diagnose.
        errors += check_generated_views(data)
    anchor_errors, info = check_anchors(data)
    errors += anchor_errors
    errors += check_orphans(data)
    if not errors:
        # Obligations read the vocabularies; on a malformed map they would
        # report cascade noise instead of the actual defect.
        info += check_obligations(data)

    if errors:
        print(f"ENTITY MAP CHECK: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    if not quick:
        for line in info:
            print(f"  i {line}")
    print("ENTITY MAP CHECK: OK")
    return 0


def hook_mode() -> int:
    """Session-hook entry: read the harness PostToolUse JSON from stdin, filter
    to files the map governs, run quick conformance + impact. Always exits 0 —
    the session hook is advisory; the blocking exits are the local gate and CI.
    The report is returned as hookSpecificOutput.additionalContext, which the
    harness injects into the model context deterministically (plain stdout of a
    successful hook is not guaranteed to reach the model)."""
    import io
    import json
    from contextlib import redirect_stdout

    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — malformed hook input must never crash the hook
        return 0
    file_path = str((payload.get("tool_input") or {}).get("file_path") or "")
    root = str(ROOT)
    if not file_path.startswith(root + "/"):
        return 0
    rel = file_path[len(root) + 1 :]
    governed = rel.startswith(("src/", "docs/system_design/")) or rel.endswith(
        (".yaml", ".yml", ".json")
    )
    if not governed:
        return 0
    lines = [f"[entity-map] change touches governed path: {rel}"]
    failed = False
    try:
        data = load_map()
    except Exception as exc:  # noqa: BLE001 — a broken map must be reported, not crash the hook
        lines.append(f"[entity-map] MAP UNREADABLE (fix before relying on any check): {exc}")
        data = None
        failed = True
    if data is not None:
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                failed = run_checks(data, quick=True) != 0
            lines.extend(buf.getvalue().strip().splitlines())
            lines.extend(f"[entity-map] {line}" for line in impact(data, [rel]))
        except Exception as exc:  # noqa: BLE001 — the hook must ALWAYS emit JSON
            lines.extend(buf.getvalue().strip().splitlines())
            lines.append(f"[entity-map] CHECKER CRASHED: {exc!r}")
            failed = True
    out: dict = {
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(lines)}
    }
    if failed:
        # Errors (not advisory info) BLOCK: the harness forces any model —
        # including weaker executors — to address red checks before moving on.
        out["decision"] = "block"
        out["reason"] = (
            "Entity map conformance FAILED — bring the truth system back to green "
            "(usually: fix the map or run entity_map_build.py) or explicitly "
            "surface the failure to the user before continuing."
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--hook":
        return hook_mode()
    data = load_map()
    if argv and argv[0] == "--impact":
        for line in impact(data, argv[1:]):
            print(line)
        return 0
    return run_checks(data, quick=bool(argv) and argv[0] == "--quick")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
