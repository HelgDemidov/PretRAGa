"""Mutation harness for the truth tools: plant a defect, demand a red suite.

A green suite is not evidence the tests can fail. Every check in this system
exists to catch one thing; the only way to know it still does is to break that
thing on purpose and watch the suite go red. Each entry below removes or
inverts exactly one check.

Marked `heavy` — it runs the whole suite once per mutation, so it is excluded
from the default gate filter and invoked deliberately:

    .venv/bin/python -m pytest -m heavy                 # every mutation
    .venv/bin/python -m pytest -m heavy -k duplicate    # one of them

Anchor staleness is checked separately and is NOT heavy: renaming a function
invalidates the literal it is anchored by, and that must surface in the normal
gate rather than after four minutes of the heavy run.

No recursion: the inner run filters on `not heavy`, so the copy's own copy of
this module is deselected there.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

HERE = Path(__file__).parent
BUILD, CHECK = "entity_map_build.py", "entity_map_check.py"
_SELF = "test_every_suite_spawning_test_is_marked_heavy"
SUITE_TIMEOUT_S = 300


class Mutation(NamedTuple):
    """`find` must occur EXACTLY once in `filename`: a literal matching twice
    would mutate whichever came first, and the harness would be testing
    something other than what it names."""

    name: str
    filename: str
    find: str
    replace: str


MUTATIONS = [
    Mutation("unknown kind accepted", BUILD,
             '        if e.get("kind") not in data["kinds"]:\n'
             '            errors.append(f"unknown kind {e.get(\'kind\')!r} on entity {e[\'id\']}")\n', ""),
    Mutation("unknown layer accepted", BUILD,
             '        if e.get("layer") not in data["layers"]:\n'
             '            errors.append(f"unknown layer {e.get(\'layer\')!r} on entity {e[\'id\']}")\n', ""),
    Mutation("unknown status accepted", BUILD, "            if status is None:\n", "            if False:\n"),
    Mutation("marks not validated", BUILD,
             'if a.get("marks") is not None and a["marks"] not in data["marks"]:', "if False:"),
    Mutation("relation type not validated", BUILD,
             '        if r.get("type") not in data["relation_types"]:', "        if False:"),
    Mutation("isolated entity accepted", BUILD,
             "    for node in graph.nodes:\n"
             "        if graph.degree(node) == 0:\n"
             '            errors.append(f"isolated entity (no relations): {node}")\n', ""),
    Mutation("forbidden attributes allowed", BUILD,
             '        if kind["attributes"] == "forbidden" and _attrs(e):',
             "        if False and _attrs(e):  # noqa"),
    Mutation("every kind owes an anchor", BUILD,
             'return bool(kind.get("anchor") == "required")', "return True"),
    Mutation("obligations registry always empty", BUILD,
             '    out: list[tuple[str, str, str]] = []\n    for e in entities_ru_sorted(data):',
             "    out: list[tuple[str, str, str]] = []\n    for e in []:"),
    Mutation("obligations reported regardless of the kind", BUILD,
             'if kind["identity"] == "required" and eid not in {', "if eid not in {"),
    Mutation("registry regressed to placeholders only", BUILD,
             '            if status.get("settled"):\n                continue\n',
             '            if status.get("settled") or not status.get("requires_trigger"):\n'
             "                continue\n"),
    Mutation("requires_trigger flag ignored", BUILD,
             'elif status.get("requires_trigger") and not a.get("trigger"):', "elif False:"),
    Mutation("entity index skips entities", BUILD,
             "    for e in entities_ru_sorted(data):\n        out.append(",
             "    for e in entities_ru_sorted(data)[1:]:\n        out.append("),
    Mutation("upward-dependency check dropped", BUILD, "    errors += _validate_layering(data)\n", ""),
    Mutation("upward dependency allowed", BUILD, "        if rank[src] > rank[dst]:", "        if False:"),
    Mutation("layering over-generalised onto governance", BUILD,
             'if r.get("type") not in _types_of_class(data, "dependency"):',
             'if r.get("type") not in _types_of_class(data, "dependency") '
             '| _types_of_class(data, "governance"):'),
    Mutation("named paths not validated", BUILD, "    errors += _validate_paths(data)\n", ""),
    Mutation("broken hop in a named path allowed", BUILD,
             "            if a in known and b in known and edge_between(data, a, b) is None:",
             "            if False:"),
    Mutation("edge_between made direction-sensitive", BUILD,
             '        if {r["from"], r["to"]} == {a, b}:', '        if (r["from"], r["to"]) == (a, b):'),
    Mutation("duplicate YAML keys let through", BUILD, "        if key in mapping:", "        if False:"),
    Mutation("stale generated view passes", CHECK,
             'elif path.read_text(encoding="utf-8") != content:', "elif False:"),
    Mutation("removal plan forgets dangling relations", CHECK,
             'cut = [r for r in data["relations"] if r["from"] in doomed or r["to"] in doomed]', "cut = []"),
    Mutation("removal plan forgets dead vocabulary values", CHECK,
             "        dead = sorted(set(data[block]) - used)", "        dead = []"),
    Mutation("removal plan accepts an unknown entity", CHECK, "    if unknown:", "    if False:"),
    Mutation("removal plan mutates instead of planning", CHECK,
             '    survivors = {e["id"] for e in data["entities"]} - doomed',
             '    data["entities"] = [e for e in data["entities"] if e["id"] not in doomed]\n'
             '    survivors = {e["id"] for e in data["entities"]} - doomed'),
]

WRITES_INTO_PRODUCTION = '''

def test_planted_write_into_production() -> None:
    import entity_map_build as b
    b.MAP_VIEW.write_text("clobbered", encoding="utf-8")
'''


def run_suite(truth_dir: Path) -> subprocess.CompletedProcess[str]:
    """The suite as the gate runs it, against a copy. `not heavy` keeps the
    copy's own mutation module out — otherwise this would recurse.

    The copy carries no pytest config, so `heavy` is unregistered there and
    pytest warns about it; the filter still applies, which is what matters."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "not heavy", "-p", "no:cacheprovider",
         str(truth_dir)],
        capture_output=True, text=True, check=False, timeout=SUITE_TIMEOUT_S,
        cwd=str(truth_dir),
    )


# --------------------------------------------------------------------------
# cheap, and therefore part of the ordinary gate
# --------------------------------------------------------------------------

def test_mutation_names_are_unique() -> None:
    names = [m.name for m in MUTATIONS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.name)
def test_mutation_anchor_matches_exactly_once(mutation: Mutation) -> None:
    """Anchors are literal source text, so a rename silently invalidates one.
    Catching that here costs milliseconds; catching it inside the heavy run
    costs four minutes and looks like a failure of the tools rather than of
    the harness."""
    source = (HERE / mutation.filename).read_text(encoding="utf-8")
    assert source.count(mutation.find) == 1, (
        f"anchor for {mutation.name!r} matches {source.count(mutation.find)} times in "
        f"{mutation.filename} — the code moved; re-anchor the mutation"
    )
    assert mutation.find != mutation.replace


def test_every_check_module_is_mutated() -> None:
    assert {m.filename for m in MUTATIONS} == {BUILD, CHECK}


def test_every_suite_spawning_test_is_marked_heavy() -> None:
    """The anti-recursion invariant, as a check rather than a habit. The inner
    run filters on `not heavy`; an unmarked test that spawns a suite would
    therefore spawn itself, and so on until the timeout."""
    import inspect

    module = sys.modules[__name__]
    for name, obj in vars(module).items():
        # This function names run_suite in order to look for it, so it would
        # otherwise flag itself and demand a marker that would make the cheap
        # guard heavy.
        if not name.startswith("test_") or not callable(obj) or name == _SELF:
            continue
        if "run_suite(" not in inspect.getsource(obj):
            continue
        marks = {m.name for m in getattr(obj, "pytestmark", [])}
        assert "heavy" in marks, f"{name} spawns a suite but is not marked heavy"


# --------------------------------------------------------------------------
# the harness proper
# --------------------------------------------------------------------------

@pytest.mark.heavy
def test_untouched_copy_is_green(truth_copy: Path) -> None:
    """The control. Without it, a red result from a mutation could just mean
    the copy itself is broken."""
    done = run_suite(truth_copy)
    assert done.returncode == 0, done.stdout[-3000:]


@pytest.mark.heavy
def test_hermeticity_fixture_catches_a_production_write(truth_copy: Path) -> None:
    """The guard that keeps every other test honest, verified by tripping it."""
    victim = truth_copy / "test_design_truth.py"
    victim.write_text(victim.read_text(encoding="utf-8") + WRITES_INTO_PRODUCTION, encoding="utf-8")
    done = run_suite(truth_copy)
    assert done.returncode != 0
    assert "wrote into production truth artifacts" in done.stdout


@pytest.mark.heavy
@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.name)
def test_planted_defect_turns_the_suite_red(mutation: Mutation, truth_copy: Path) -> None:
    target = truth_copy / mutation.filename
    source = target.read_text(encoding="utf-8")
    assert source.count(mutation.find) == 1
    target.write_text(source.replace(mutation.find, mutation.replace, 1), encoding="utf-8")

    done = run_suite(truth_copy)
    assert done.returncode != 0, (
        f"mutation {mutation.name!r} SURVIVED — no test constrains this behaviour\n"
        + done.stdout[-3000:]
    )
