"""Conformance checker: the entity map is the curated truth; this tool diffs
observable reality against it and fails loudly on divergence. It NEVER rewrites
the map — divergence is resolved by a human decision (fix code, or edit the map
as an explicit design decision).

Check classes (grow as the codebase appears):
  1. map integrity        — delegated to entity_map_build.validate
  2. glossary <-> map     — entity code-names in entity_glossary.md headings
                            must match map entity ids, both directions
  3. code anchors         — every `implements` prefix must resolve on disk;
                            entities without anchors are counted as pending
                            (informational until src/ exists)
  4. orphan code          — python files under src/ not covered by any anchor
                            (active only when src/ exists)

Modes:
  (default)          full check, exit 1 on errors
  --quick            same checks, terse output (for the session hook)
  --impact F [F...]  map changed file paths to affected entities (advisory)

Run: .venv/bin/python docs/system_design/entity_map/entity_map_check.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

import entity_map_build

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
SRC_ROOT = ROOT / "src"
GLOSSARY = HERE / "entity_glossary.md"
MAP_FILE = HERE / "entity_map.yaml"

# glossary entries carry their code name in the heading: "### Документ (Document)"
_GLOSSARY_ID_RE = re.compile(r"^###\s+.+\((?P<code>[A-Z][A-Za-z]+)\)\s*$", re.MULTILINE)


def load_map() -> dict:
    return yaml.safe_load(MAP_FILE.read_text(encoding="utf-8"))


def check_map_integrity(data: dict) -> list[str]:
    return [f"map: {e}" for e in entity_map_build.validate(data)]


def check_glossary(data: dict) -> list[str]:
    errors: list[str] = []
    glossary_ids = set(_GLOSSARY_ID_RE.findall(GLOSSARY.read_text(encoding="utf-8")))
    map_ids = {e["id"] for e in data["entities"]}
    for missing in sorted(map_ids - glossary_ids):
        errors.append(f"glossary: map entity {missing} has no glossary entry")
    for stray in sorted(glossary_ids - map_ids):
        errors.append(f"glossary: entry ({stray}) does not match any map entity id")
    return errors


def check_anchors(data: dict) -> tuple[list[str], list[str]]:
    """Returns (errors, info). Anchors must resolve; unanchored entities are
    pending — informational while src/ does not exist, so early design work
    is not drowned in noise the checker cannot yet act on."""
    errors: list[str] = []
    pending: list[str] = []
    for e in data["entities"]:
        anchors = e.get("implements")
        if e.get("code") == "none":
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


def run_checks(data: dict, quick: bool) -> int:
    errors: list[str] = []
    errors += check_map_integrity(data)
    errors += check_glossary(data)
    anchor_errors, info = check_anchors(data)
    errors += anchor_errors
    errors += check_orphans(data)

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
    except Exception:
        return 0
    file_path = str((payload.get("tool_input") or {}).get("file_path") or "")
    root = str(ROOT)
    if not file_path.startswith(root + "/"):
        return 0
    rel = file_path[len(root) + 1 :]
    governed = (
        rel.startswith("src/")
        or rel.startswith("docs/system_design/")
        or rel.endswith((".yaml", ".yml", ".json"))
    )
    if not governed:
        return 0
    lines = [f"[entity-map] change touches governed path: {rel}"]
    try:
        data = load_map()
    except Exception as exc:
        lines.append(f"[entity-map] MAP UNREADABLE (fix before relying on any check): {exc}")
        data = None
    if data is not None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_checks(data, quick=True)
        lines.extend(buf.getvalue().strip().splitlines())
        lines.extend(f"[entity-map] {line}" for line in impact(data, [rel]))
    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(lines)}},
        ensure_ascii=False,
    ))
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
