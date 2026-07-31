"""Tests for the design-truth tools.

What is worth testing here is the CHECKS, not the map: the map is curated data
whose content changes by design decision, so pinning its numbers would make the
oracle track the data instead of constraining the code. Two kinds of test:

  regression — the committed map validates and the committed views are fresh;
  negative   — each check actually fires on the defect it claims to catch.

Negative cases are parametrised over the map's own CLOSED vocabularies rather
than over generated examples: the vocabularies are finite and small, so
parametrisation is EXHAUSTIVE where sampling would only be probable. Hypothesis
is used for the one genuinely open-ended claim — that the obligations registry
stays justified for any subgraph of the map, not just for this one.
"""
from __future__ import annotations

import copy
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import entity_map_build as build
import entity_map_check as check

HERE = Path(__file__).parent
FIELD_OF_LABEL = {label: field for field, label in build.OBLIGATION_LABEL.items()}

# The autouse hermeticity fixture is function-scoped and provides no test data;
# it only snapshots the directory, so reusing it across Hypothesis examples is
# safe and the health check does not apply.
PROPERTY = settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)


@pytest.fixture(scope="session")
def source_text() -> str:
    return build.SOURCE.read_text(encoding="utf-8")


@pytest.fixture
def data(source_text: str) -> dict[str, Any]:
    """A fresh mutable copy per test: mutations must not leak between tests."""
    loaded: dict[str, Any] = build.load_yaml(source_text)
    return loaded


# --------------------------------------------------------------------------
# regression: the committed artifacts are consistent
# --------------------------------------------------------------------------

def test_committed_map_validates(data: dict[str, Any]) -> None:
    assert build.validate(data) == []


@pytest.mark.parametrize(
    ("path", "renderer"),
    [(build.MAP_VIEW, build.render), (build.GLOSSARY_VIEW, build.render_glossary)],
    ids=["entity_map.md", "entity_glossary.md"],
)
def test_committed_view_is_fresh(data: dict[str, Any], path: Path, renderer: Any) -> None:
    assert path.read_text(encoding="utf-8") == renderer(data)


def test_rendering_is_deterministic(data: dict[str, Any]) -> None:
    assert build.render(data) == build.render(copy.deepcopy(data))
    assert build.render_glossary(data) == build.render_glossary(copy.deepcopy(data))


# --------------------------------------------------------------------------
# vocabulary closure — every authored value is a declared one, and vice versa
# --------------------------------------------------------------------------

def test_every_authored_kind_is_declared(data: dict[str, Any]) -> None:
    assert {e["kind"] for e in data["entities"]} <= set(data["kinds"])


def test_every_authored_relation_type_is_declared(data: dict[str, Any]) -> None:
    assert {r["type"] for r in data["relations"]} <= set(data["relation_types"])


def test_every_authored_trigger_is_declared(data: dict[str, Any]) -> None:
    used = {a["trigger"] for e in data["entities"] for a in build._attrs(e) if a.get("trigger")}
    assert used <= set(data["triggers"])


def test_no_declared_vocabulary_value_is_dead(data: dict[str, Any]) -> None:
    """A closed vocabulary earns its closure only if every entry is in use;
    an unused entry is speculative generality with a validation cost."""
    assert {e["kind"] for e in data["entities"]} == set(data["kinds"])
    assert {r["type"] for r in data["relations"]} == set(data["relation_types"])
    assert {e["layer"] for e in data["entities"]} == set(data["layers"])
    used_classes = {s["class"] for s in data["relation_types"].values()}
    assert used_classes == set(data["relation_classes"])


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d["entities"][0].update(kind="nonesuch"), "unknown kind 'nonesuch'"),
        (lambda d: d["relations"][0].update(type="nonesuch"), "unknown relation type 'nonesuch'"),
        (lambda d: d["entities"][1]["attributes"][0].update(marks="nonesuch"), "unknown marks 'nonesuch'"),
        (lambda d: d["entities"][0]["attributes"][0].update(status="nonesuch"), "unknown status 'nonesuch'"),
        (lambda d: d["entities"][0].update(group="nonesuch"), "unknown group 'nonesuch'"),
    ],
    ids=["kind", "relation type", "marks", "status", "group"],
)
def test_value_outside_a_closed_vocabulary_is_rejected(
    data: dict[str, Any], mutate: Any, expected: str
) -> None:
    mutate(data)
    assert any(expected in e for e in build.validate(data))


def test_unknown_trigger_is_rejected(data: dict[str, Any]) -> None:
    for e in data["entities"]:
        for a in build._attrs(e):
            if a.get("trigger"):
                a["trigger"] = "nonesuch"
                assert any("unknown trigger 'nonesuch'" in err for err in build.validate(data))
                return
    pytest.fail("no placeholder with a trigger in the map to mutate")


@pytest.mark.parametrize("block", sorted(build.VOCABULARIES))
def test_missing_vocabulary_block_is_rejected(data: dict[str, Any], block: str) -> None:
    del data[block]
    assert any(f"missing top-level {block} block" in e for e in build.validate(data))


def test_no_vocabulary_lives_in_the_code(data: dict[str, Any]) -> None:
    """Every name the model operates with is data. The generator may hold the
    SHAPE of a vocabulary (which obligation fields exist) but never its
    MEMBERS — otherwise adding a status would mean editing Python while adding
    a kind means editing the map, and the map stops being the only channel."""
    for block in build.VOCABULARIES:
        assert data.get(block), f"{block} must be declared in the map"
    source = (HERE / "entity_map_build.py").read_text(encoding="utf-8")
    # Marks are exempt on purpose: a mark's name IS the name of the kind
    # obligation that looks for it (`identity`, `version`), so the two are one
    # concept spelled once. Statuses and layers have no such tie and must not
    # appear as literals at all.
    for name in list(data["statuses"]) + list(data["layers"]):
        assert f'"{name}"' not in source, f"vocabulary member {name!r} is hardcoded in the generator"


def test_missing_conventions_is_rejected(data: dict[str, Any]) -> None:
    data["conventions"] = "  "
    assert any("missing top-level conventions" in e for e in build.validate(data))


@pytest.mark.parametrize("field", sorted(build.OBLIGATION_FIELDS))
def test_bad_obligation_value_on_a_kind_is_rejected(data: dict[str, Any], field: str) -> None:
    kind = next(iter(data["kinds"]))
    data["kinds"][kind][field] = "maybe"
    assert any(f"obligation {field}='maybe'" in e for e in build.validate(data))


def test_relation_type_with_unknown_class_is_rejected(data: dict[str, Any]) -> None:
    data["relation_types"]["reads"]["class"] = "nonesuch"
    assert any("unknown class 'nonesuch'" in e for e in build.validate(data))


def test_relation_type_with_unknown_inverse_is_rejected(data: dict[str, Any]) -> None:
    data["relation_types"]["derived_from"]["inverse_of"] = "nonesuch"
    assert any("unknown inverse_of 'nonesuch'" in e for e in build.validate(data))


# --------------------------------------------------------------------------
# kind obligations: a broken FORBID is an error, exhaustively per kind
# --------------------------------------------------------------------------

def _first_of_kind(data: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return next((e for e in data["entities"] if e["kind"] == kind), None)


def _kinds_where(data: dict[str, Any], field: str, value: str) -> list[str]:
    return [k for k, spec in data["kinds"].items() if spec[field] == value]


def test_anchor_forbidding_kind_rejects_an_anchor(data: dict[str, Any]) -> None:
    kinds = _kinds_where(data, "anchor", "forbidden")
    assert kinds, "no kind forbids anchors — the test would be vacuous"
    for kind in kinds:
        fresh = copy.deepcopy(data)
        entity = _first_of_kind(fresh, kind)
        assert entity is not None
        entity["implements"] = ["src/whatever"]
        assert any("carries implements anchors" in e for e in build.validate(fresh))


def test_identity_forbidding_kind_rejects_an_identity_marker(data: dict[str, Any]) -> None:
    kinds = [k for k in _kinds_where(data, "identity", "forbidden")
             if data["kinds"][k]["attributes"] == "required"]
    assert kinds
    for kind in kinds:
        fresh = copy.deepcopy(data)
        entity = _first_of_kind(fresh, kind)
        assert entity is not None
        entity["attributes"][0]["marks"] = "identity"
        assert any("takes no identity" in e for e in build.validate(fresh))


def test_placement_forbidding_kind_rejects_a_placement_relation(data: dict[str, Any]) -> None:
    placement = next(t for t, s in data["relation_types"].items() if s["class"] == "placement")
    store = _first_of_kind(data, next(iter(_kinds_where(data, "hosts", "required"))))
    assert store is not None
    kinds = _kinds_where(data, "placement", "forbidden")
    assert kinds
    for kind in kinds:
        fresh = copy.deepcopy(data)
        entity = _first_of_kind(fresh, kind)
        assert entity is not None
        fresh["relations"].append({"from": entity["id"], "to": store["id"], "type": placement})
        assert any("is not stored anywhere" in e for e in build.validate(fresh))


def test_attribute_forbidding_kind_rejects_attributes(data: dict[str, Any]) -> None:
    kinds = _kinds_where(data, "attributes", "forbidden")
    assert kinds
    for kind in kinds:
        fresh = copy.deepcopy(data)
        entity = _first_of_kind(fresh, kind)
        assert entity is not None
        settled = next(s for s, spec in fresh["statuses"].items() if spec["settled"])
        entity["attributes"] = [{"name": "smuggled", "status": settled}]
        assert any("takes no attributes" in e for e in build.validate(fresh))


def test_attribute_requiring_kind_rejects_emptiness(data: dict[str, Any]) -> None:
    kind = next(iter(_kinds_where(data, "attributes", "required")))
    entity = _first_of_kind(data, kind)
    assert entity is not None
    entity["attributes"] = []
    assert any("requires attributes, but has none" in e for e in build.validate(data))


def test_anchor_requirement_follows_the_kind(data: dict[str, Any]) -> None:
    for e in data["entities"]:
        expected = data["kinds"][e["kind"]]["anchor"] == "required"
        assert build.anchor_required(data, e) is expected


# --------------------------------------------------------------------------
# named paths: the vision's load-bearing claims, as checks
# --------------------------------------------------------------------------

def test_every_named_path_is_connected_in_the_map(data: dict[str, Any]) -> None:
    """§6 of the vision states the provenance chain as a load-bearing claim.
    Prose cannot notice when a hop stops existing; this can."""
    assert data.get("paths"), "no named paths — the test would be vacuous"
    for pid, spec in data["paths"].items():
        hops = spec["hops"]
        for a, b in zip(hops, hops[1:], strict=False):
            assert build.edge_between(data, a, b) is not None, f"{pid}: {a} — {b}"


def test_a_broken_hop_fails_the_build(data: dict[str, Any]) -> None:
    pid = next(iter(data["paths"]))
    a, b = data["paths"][pid]["hops"][:2]
    data["relations"] = [r for r in data["relations"] if {r["from"], r["to"]} != {a, b}]
    assert any("are not connected by any relation" in e for e in build.validate(data))


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d["paths"][next(iter(d["paths"]))].update(hops=["Nowhere", "Deliverable"]),
         "no such entity: Nowhere"),
        (lambda d: d["paths"][next(iter(d["paths"]))].update(hops=["Deliverable"]),
         "needs at least two hops"),
        (lambda d: d["paths"][next(iter(d["paths"]))].update(ru="  "),
         "has no ru label"),
    ],
    ids=["unknown hop", "too short", "no label"],
)
def test_malformed_path_is_rejected(data: dict[str, Any], mutate: Any, expected: str) -> None:
    mutate(data)
    assert any(expected in e for e in build.validate(data))


def test_edge_between_is_direction_agnostic(data: dict[str, Any]) -> None:
    """A path asserts connectivity, not direction: the map records
    `CanonicalText -> ProvenanceAnchor` while the chain reads the other way."""
    r = data["relations"][0]
    assert build.edge_between(data, r["from"], r["to"]) == r["type"]
    assert build.edge_between(data, r["to"], r["from"]) == r["type"]
    assert build.edge_between(data, r["from"], r["from"]) is None


# --------------------------------------------------------------------------
# the checker, called in process
#
# The subprocess tests below stay: they are the only thing that exercises argv,
# exit codes and the real entry points. These add what those cannot give —
# assertions on the checker's own functions, which is also what makes its
# coverage figure mean something. Measuring the subprocesses instead was
# rejected: it costs ~6.5x per launch and needs a `coverage combine` step in
# both the local gate and CI, and those two must stay identical.
# --------------------------------------------------------------------------

def test_load_map_reads_the_committed_map(data: dict[str, Any]) -> None:
    assert check.load_map() == data


def test_check_map_integrity_is_green_and_prefixes_its_errors(data: dict[str, Any]) -> None:
    assert check.check_map_integrity(data) == []
    data["entities"][0]["kind"] = "nonesuch"
    assert all(e.startswith("map: ") for e in check.check_map_integrity(data))


def test_check_generated_views_is_green_and_notices_staleness(data: dict[str, Any]) -> None:
    assert check.check_generated_views(data) == []
    data["entities"][0]["ru"] = "Переименовано"
    assert any("stale or hand-edited" in e for e in check.check_generated_views(data))


def test_check_anchors_reports_pending_while_src_is_absent(data: dict[str, Any]) -> None:
    errors, info = check.check_anchors(data)
    assert errors == []
    owed = [e for e in data["entities"] if build.anchor_required(data, e)]
    assert any(f"{len(owed)} entities without code anchors" in line for line in info)


def test_check_anchors_errors_on_an_unresolvable_prefix(data: dict[str, Any]) -> None:
    next(e for e in data["entities"] if build.anchor_required(data, e))["implements"] = ["nowhere/"]
    errors, _ = check.check_anchors(data)
    assert any("does not resolve" in e for e in errors)


def test_check_orphans_is_silent_without_src(data: dict[str, Any]) -> None:
    assert not check.SRC_ROOT.exists(), "src/ appeared — this test must be revisited"
    assert check.check_orphans(data) == []


def test_check_obligations_groups_by_what_is_missing(data: dict[str, Any]) -> None:
    lines = check.check_obligations(data)
    unmet = build.obligations(data)
    assert lines[0].startswith(f"obligations: {len(unmet)} unmet")
    assert len(lines) - 1 == len({row[2] for row in unmet})


def test_run_checks_is_green_on_the_committed_map(
    data: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert check.run_checks(data, quick=False) == 0
    assert "ENTITY MAP CHECK: OK" in capsys.readouterr().out


def test_run_checks_reports_and_fails_on_a_broken_map(
    data: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    data["entities"][0]["kind"] = "nonesuch"
    assert check.run_checks(data, quick=False) == 1
    out = capsys.readouterr().out
    assert "ENTITY MAP CHECK: 1 error(s)" in out and "unknown kind" in out


def test_quick_mode_stays_terse(
    data: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """The hook report must not drown in advisory traffic; only demoted view
    staleness is worth a line there."""
    assert check.run_checks(data, quick=True) == 0
    assert capsys.readouterr().out.strip() == "ENTITY MAP CHECK: OK"


def test_demoted_staleness_surfaces_in_quick_mode(
    data: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    data["entities"][0]["ru"] = "Переименовано"
    assert check.run_checks(data, quick=True, demote_views=True) == 0
    assert "expected while a tool is being edited" in capsys.readouterr().out


def test_main_dispatches_every_mode(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main([]) == 0
    assert "ENTITY MAP CHECK: OK" in capsys.readouterr().out
    assert check.main(["--quick"]) == 0
    capsys.readouterr()
    assert check.main(["--impact", str(build.SOURCE.relative_to(check.ROOT))]) == 0
    assert "TRUTH ARTIFACT edited" in capsys.readouterr().out
    assert check.main(["--removal-impact", "Corpus"]) == 0
    assert "removal plan for: Corpus" in capsys.readouterr().out


def test_hook_ignores_paths_the_map_does_not_govern(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The filter is what keeps the hook from firing on every unrelated edit."""
    for rel in ("README.md", "some/notes.txt"):
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": f"{check.ROOT}/{rel}"}}))
        )
        assert check.hook_mode() == 0
        assert capsys.readouterr().out == "", f"{rel} should not have produced a report"


def test_hook_ignores_a_path_outside_the_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": "/etc/hosts"}}))
    )
    assert check.hook_mode() == 0
    assert capsys.readouterr().out == ""


def test_hook_survives_malformed_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("{ not json"))
    assert check.hook_mode() == 0
    assert capsys.readouterr().out == ""


def test_hook_reports_a_governed_edit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_input": {"file_path": str(build.SOURCE)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert check.hook_mode() == 0
    out = json.loads(capsys.readouterr().out)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "change touches governed path" in context
    assert "TRUTH ARTIFACT edited" in context
    assert "decision" not in out, "a green map must not block"


# --------------------------------------------------------------------------
# the loader: fast, and loud where PyYAML is silent
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("doc", "where"),
    [
        ("a: 1\na: 2\n", "top level"),
        ("entities:\n  - id: A\n    definition: x\n    definition: y\n", "inside an entity"),
        ("entities:\n  - {name: n, status: fixed, status: deferred}\n", "inside an attribute"),
        ("kinds:\n  data:\n    ru: a\n    ru: b\n", "inside a nested mapping"),
    ],
)
def test_duplicate_key_raises_instead_of_losing_a_field(doc: str, where: str) -> None:
    """Stock PyYAML resolves a duplicate key in favour of the last one without
    a word. In a hand-written source of truth that is silent data loss: a
    definition can be deleted by a careless paste, the file stays valid YAML,
    and no check downstream can tell it ever existed."""
    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key"):
        build.load_yaml(doc)
    assert yaml.safe_load(doc), f"stock PyYAML still accepts it silently ({where})"


def test_strict_loader_parses_the_real_map_unchanged(source_text: str) -> None:
    assert build.load_yaml(source_text) == yaml.safe_load(source_text)


# --------------------------------------------------------------------------
# --removal-impact: planning narrowing without performing it
# --------------------------------------------------------------------------

def test_removal_plan_names_every_relation_that_would_dangle(data: dict[str, Any]) -> None:
    target = "Translation"
    expected = [r for r in data["relations"] if target in (r["from"], r["to"])]
    assert expected, "target has no relations — the test would be vacuous"
    lines = check.removal_impact(data, [target])
    assert f"relations to delete: {len(expected)}" in "\n".join(lines)
    for r in expected:
        assert any(f"from: {r['from']}, to: {r['to']}" in line for line in lines)


def test_removal_plan_predicts_a_vocabulary_value_left_without_carriers(
    data: dict[str, Any],
) -> None:
    """Deleting the last entity of a kind kills the kind too, and a dead
    vocabulary value fails the build just as hard as a dangling relation."""
    counts: dict[str, int] = {}
    for e in data["entities"]:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    lone_kind, = [k for k, n in counts.items() if n == 1][:1]
    victim = next(e["id"] for e in data["entities"] if e["kind"] == lone_kind)
    lines = check.removal_impact(data, [victim])
    assert any("kinds left with no carrier" in line and lone_kind in line for line in lines)


def test_removal_plan_predicts_isolation(data: dict[str, Any]) -> None:
    degree: dict[str, int] = {e["id"]: 0 for e in data["entities"]}
    for r in data["relations"]:
        degree[r["from"]] += 1
        degree[r["to"]] += 1
    hub = max(degree, key=lambda k: degree[k])
    lines = check.removal_impact(data, [hub])
    text = "\n".join(lines)
    if "would become isolated" in text:
        named = text.split("would become isolated (an error): ")[1].split("\n")[0].split(", ")
        survivors = {e["id"] for e in data["entities"]} - {hub}
        kept = [r for r in data["relations"] if hub not in (r["from"], r["to"])]
        linked = {r["from"] for r in kept} | {r["to"] for r in kept}
        assert set(named) == survivors - linked


def test_removal_plan_matches_what_actually_happens(data: dict[str, Any]) -> None:
    """The plan and the run are computed from the same functions, so the plan
    cannot promise something the deletion does not deliver. Verified by doing
    the deletion the plan describes and re-reading the map."""
    target = "Translation"
    lines = check.removal_impact(data, [target])
    predicted = int("".join(lines).split("open obligations: ")[1].split(" -> ")[1].split(" ")[0])

    data["entities"] = [e for e in data["entities"] if e["id"] != target]
    data["relations"] = [r for r in data["relations"] if target not in (r["from"], r["to"])]
    assert build.validate(data) == [], "the plan missed something that breaks the map"
    assert len(build.obligations(data)) == predicted


def test_removal_plan_writes_nothing(data: dict[str, Any], source_text: str) -> None:
    before = {e["id"] for e in data["entities"]}, len(data["relations"])
    check.removal_impact(data, ["Translation", "Corpus"])
    assert ({e["id"] for e in data["entities"]}, len(data["relations"])) == before
    assert build.SOURCE.read_text(encoding="utf-8") == source_text


def test_removal_plan_rejects_an_unknown_entity(data: dict[str, Any]) -> None:
    lines = check.removal_impact(data, ["Nonesuch"])
    assert lines == ["removal: no such entity: Nonesuch"]


def test_removal_impact_cli_exits_nonzero_on_an_unknown_entity(truth_copy: Path) -> None:
    ok = _run(truth_copy / "entity_map_check.py", "--removal-impact", "Corpus")
    assert ok.returncode == 0 and "removal plan for: Corpus" in ok.stdout
    bad = _run(truth_copy / "entity_map_check.py", "--removal-impact", "Nonesuch")
    assert bad.returncode == 1
    usage = _run(truth_copy / "entity_map_check.py", "--removal-impact")
    assert usage.returncode == 1 and "usage:" in usage.stdout


# --------------------------------------------------------------------------
# the two registries and the flat index
# --------------------------------------------------------------------------

def _unsettled_attributes(data: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (e["id"], a["name"])
        for e in data["entities"]
        for a in build._attrs(e)
        if not data["statuses"][a["status"]]["settled"]
    ]


def test_unsettled_registry_covers_every_unsettled_status(data: dict[str, Any]) -> None:
    """The promise is that nothing agreed-but-unspecified is lost. Before the
    statuses became data the registry listed placeholders only, so the
    attributes awaiting a measurement or a later stage fell out of it."""
    rows = build.unsettled_registry(data).splitlines()[2:]
    assert len(rows) == len(_unsettled_attributes(data))
    unsettled_statuses = {s for s, spec in data["statuses"].items() if not spec["settled"]}
    assert len(unsettled_statuses) > 1, "registry would be indistinguishable from a placeholder list"
    for status in unsettled_statuses:
        label = build._status_label(data, status)
        assert any(label in row for row in rows), f"{status} never reaches the registry"


def test_settling_a_status_empties_its_share_of_the_registry(data: dict[str, Any]) -> None:
    victim = next(s for s, spec in data["statuses"].items() if not spec["settled"])
    before = len(build.unsettled_registry(data).splitlines())
    affected = sum(
        1 for e in data["entities"] for a in build._attrs(e) if a["status"] == victim
    )
    data["statuses"][victim]["settled"] = True
    after = len(build.unsettled_registry(data).splitlines())
    assert before - after == affected


def test_entity_index_lists_every_entity_exactly_once(data: dict[str, Any]) -> None:
    rows = build.entity_index(data).splitlines()[2:]
    assert len(rows) == len(data["entities"])
    listed = [r.split("`")[1] for r in rows]
    assert set(listed) == {e["id"] for e in data["entities"]}


def test_every_entity_listing_is_sorted_by_the_russian_name(data: dict[str, Any]) -> None:
    """One collation for all of them: the index, both registries, the kind
    membership lists and the layer composition must read in the same order, or
    cross-referencing them by eye stops working."""
    expected = [e["ru"] for e in build.entities_ru_sorted(data)]
    keys = [build.ru_key(name) for name in expected]
    assert keys == sorted(keys), "entities_ru_sorted is not actually sorted"

    index_names = [r.split("|")[1].strip() for r in build.entity_index(data).splitlines()[2:]]
    assert index_names == expected

    seen: list[str] = []
    for row in build.unsettled_registry(data).splitlines()[2:]:
        name = row.split("|")[1].strip().rsplit(" (", 1)[0]
        if name not in seen:
            seen.append(name)
    assert seen == [n for n in expected if n in seen]


def test_yo_collates_with_ye_not_at_the_alphabet_edges(data: dict[str, Any]) -> None:
    """Codepoints put `ё` in two wrong places at once: lowercase ё (U+0451)
    lands past я, uppercase Ё (U+0401) lands before А. The key fixes both by
    folding case first and then ё to е."""
    assert build.ru_key("Ёмкость") > build.ru_key("Егерь")
    assert build.ru_key("Ёмкость") < build.ru_key("Жажда")
    # what plain comparison does instead, in both directions
    assert "ёмкость" > "яблоко"
    assert "Ёмкость" < "Абажур"


def test_every_declared_status_and_mark_is_used(data: dict[str, Any]) -> None:
    used_status = {a["status"] for e in data["entities"] for a in build._attrs(e)}
    used_marks = {a["marks"] for e in data["entities"] for a in build._attrs(e) if a.get("marks")}
    assert used_status == set(data["statuses"])
    assert used_marks == set(data["marks"])


@pytest.mark.parametrize("field", sorted(build.OBLIGATION_FIELDS))
def test_every_obligation_can_be_loosened_as_data(data: dict[str, Any], field: str) -> None:
    """Thinning the schema must never require a code edit: `optional` has to be
    a legal value everywhere, or that field can only be tightened."""
    assert "optional" in build.OBLIGATION_FIELDS[field]
    for kind in data["kinds"].values():
        kind[field] = "optional"
    assert not [e for e in build.validate(data) if "obligation" in e]


# --------------------------------------------------------------------------
# layers: the ordering is the contract, so prove it can be broken
# --------------------------------------------------------------------------

def _dependency_edges(data: dict[str, Any]) -> list[dict[str, Any]]:
    types = {t for t, s in data["relation_types"].items() if s["class"] == "dependency"}
    return [r for r in data["relations"] if r["type"] in types]


def test_layer_rank_follows_declaration_order(data: dict[str, Any]) -> None:
    assert list(build.layer_rank(data)) == list(data["layers"])
    assert sorted(build.layer_rank(data).values()) == list(range(len(data["layers"])))


def test_committed_map_has_no_upward_dependency(data: dict[str, Any]) -> None:
    rank = build.layer_rank(data)
    layer_of = {e["id"]: e["layer"] for e in data["entities"]}
    for r in _dependency_edges(data):
        assert rank[layer_of[r["from"]]] <= rank[layer_of[r["to"]]], r


def test_unknown_layer_is_rejected(data: dict[str, Any]) -> None:
    data["entities"][0]["layer"] = "nonesuch"
    assert any("unknown layer 'nonesuch'" in e for e in build.validate(data))


def test_missing_layers_block_is_rejected(data: dict[str, Any]) -> None:
    del data["layers"]
    assert any("missing top-level layers block" in e for e in build.validate(data))


def test_upward_dependency_is_rejected(data: dict[str, Any]) -> None:
    """Moving the depended-upon entity above its dependant must break the
    build. Without this the layering check passes only because the current
    assignment was authored to pass it."""
    edge = _dependency_edges(data)[0]
    rank = build.layer_rank(data)
    layer_of = {e["id"]: e["layer"] for e in data["entities"]}
    top = next(iter(data["layers"]))
    assert rank[layer_of[edge["from"]]] > rank[top], "edge already starts at the top layer"
    target = next(e for e in data["entities"] if e["id"] == edge["to"])
    target["layer"] = top
    errors = build.validate(data)
    assert any("depends upward" in e for e in errors), errors


def test_same_layer_dependency_is_allowed(data: dict[str, Any]) -> None:
    dep_type = next(t for t, s in data["relation_types"].items() if s["class"] == "dependency")
    pair = [e for e in data["entities"] if e["layer"] == data["entities"][0]["layer"]]
    assert len(pair) >= 2, "need two entities in one layer"
    data["relations"].append({"from": pair[0]["id"], "to": pair[1]["id"], "type": dep_type})
    assert not any("depends upward" in e for e in build.validate(data))


def test_governance_edges_are_not_constrained(data: dict[str, Any]) -> None:
    """Deliberate narrowness: a governance edge points the opposite way to the
    code dependency it implies, so constraining it would manufacture errors."""
    gov = next(t for t, s in data["relation_types"].items() if s["class"] == "governance")
    top, bottom = list(data["layers"])[0], list(data["layers"])[-1]
    low = next(e for e in data["entities"] if e["layer"] == bottom)
    high = next(e for e in data["entities"] if e["layer"] == top)
    data["relations"].append({"from": low["id"], "to": high["id"], "type": gov})
    assert not any("depends upward" in e for e in build.validate(data))


# --------------------------------------------------------------------------
# structural checks that predate the vocabularies must not regress
# --------------------------------------------------------------------------

def test_duplicate_id_is_rejected(data: dict[str, Any]) -> None:
    data["entities"].append(copy.deepcopy(data["entities"][0]))
    assert any("duplicate entity id" in e for e in build.validate(data))


def test_dangling_relation_endpoint_is_rejected(data: dict[str, Any]) -> None:
    data["relations"][0]["to"] = "Nowhere"
    assert any("relation endpoint not a defined entity" in e for e in build.validate(data))


def test_isolated_entity_is_rejected(data: dict[str, Any]) -> None:
    orphan = copy.deepcopy(data["entities"][0])
    orphan["id"] = "Orphan"
    data["entities"].append(orphan)
    assert any("isolated entity (no relations): Orphan" in e for e in build.validate(data))


def test_status_requiring_a_trigger_rejects_its_absence(data: dict[str, Any]) -> None:
    needs = [s for s, spec in data["statuses"].items() if spec.get("requires_trigger")]
    assert needs, "no status requires a trigger — the test would be vacuous"
    for e in data["entities"]:
        for a in build._attrs(e):
            if a["status"] in needs:
                del a["trigger"]
                assert any("requires a trigger" in err for err in build.validate(data))
                return
    pytest.fail("no attribute carries a trigger-requiring status")


def test_the_trigger_rule_follows_the_flag_not_the_status_name(data: dict[str, Any]) -> None:
    """Turning the flag on for a status that does not carry triggers must start
    failing those attributes. If the check were still keyed to the literal name
    `placeholder`, flipping the flag would change nothing."""
    victim = next(
        s for s, spec in data["statuses"].items()
        if not spec.get("requires_trigger") and not spec["settled"]
    )
    data["statuses"][victim]["requires_trigger"] = True
    errors = build.validate(data)
    assert any(f"status {victim} requires a trigger" in e for e in errors), errors


def test_entity_without_definition_is_rejected(data: dict[str, Any]) -> None:
    data["entities"][0]["definition"] = "   "
    assert any("has no definition" in e for e in build.validate(data))


# --------------------------------------------------------------------------
# the obligations registry: counted, named, and never invented
# --------------------------------------------------------------------------

def _obligations_are_justified(data: dict[str, Any]) -> None:
    by_id = {e["id"]: e for e in data["entities"]}
    for eid, kind, label in build.obligations(data):
        assert by_id[eid]["kind"] == kind
        assert data["kinds"][kind][FIELD_OF_LABEL[label]] == "required", (
            f"{eid}: reported a {label!r} gap although kind {kind} does not require it"
        )


def test_every_reported_obligation_is_required_by_the_kind(data: dict[str, Any]) -> None:
    _obligations_are_justified(data)


def test_closing_an_obligation_removes_exactly_that_row(data: dict[str, Any]) -> None:
    gaps = [row for row in build.obligations(data)
            if row[2] == build.OBLIGATION_LABEL["identity"]]
    assert gaps, "no identity gap in the map — the test would be vacuous"
    eid = gaps[0][0]
    entity = next(e for e in data["entities"] if e["id"] == eid)
    settled = next(s for s, spec in data["statuses"].items() if spec["settled"])
    entity["attributes"].append({"name": "uuid", "status": settled, "marks": "identity"})
    after = build.obligations(data)
    assert (eid, entity["kind"], build.OBLIGATION_LABEL["identity"]) not in after
    assert len(after) == len(build.obligations(build.load_yaml(build.SOURCE.read_text("utf-8")))) - 1


@given(dropped=st.sets(st.integers(min_value=0, max_value=200)))
@PROPERTY
def test_obligations_stay_justified_on_any_subgraph(source_text: str, dropped: set[int]) -> None:
    """Constructed around the real map rather than generated from nothing:
    drop an arbitrary subset of its relations and the registry must still only
    report gaps its kinds actually require. Dropping edges can only ADD gaps —
    it must never invent one for a kind that does not ask for it."""
    data = build.load_yaml(source_text)
    data["relations"] = [r for i, r in enumerate(data["relations"]) if i not in dropped]
    _obligations_are_justified(data)


@given(dropped=st.sets(st.integers(min_value=0, max_value=200), min_size=1))
@PROPERTY
def test_dropping_relations_never_reduces_the_registry(source_text: str, dropped: set[int]) -> None:
    data = build.load_yaml(source_text)
    baseline = len(build.obligations(data))
    data["relations"] = [r for i, r in enumerate(data["relations"]) if i not in dropped]
    assert len(build.obligations(data)) >= baseline


# --------------------------------------------------------------------------
# end to end, against a copy — the entry points default to production paths
# --------------------------------------------------------------------------

@pytest.fixture
def truth_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "docs" / "system_design" / "design_truth"
    dest.parent.mkdir(parents=True)
    shutil.copytree(HERE, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, check=False
    )


def test_build_and_check_are_green_on_a_copy(truth_copy: Path) -> None:
    assert _run(truth_copy / "entity_map_build.py").returncode == 0
    done = _run(truth_copy / "entity_map_check.py")
    assert done.returncode == 0
    assert "ENTITY MAP CHECK: OK" in done.stdout


def test_unmet_obligations_are_reported_without_blocking(truth_copy: Path) -> None:
    done = _run(truth_copy / "entity_map_check.py")
    assert done.returncode == 0
    assert "unmet kind obligation(s)" in done.stdout


def test_hand_edited_view_is_caught(truth_copy: Path) -> None:
    view = truth_copy / "entity_map.md"
    view.write_text(view.read_text(encoding="utf-8") + "\nsmuggled\n", encoding="utf-8")
    done = _run(truth_copy / "entity_map_check.py")
    assert done.returncode == 1
    assert "stale or hand-edited" in done.stdout


def test_missing_view_is_caught(truth_copy: Path) -> None:
    (truth_copy / "entity_glossary.md").unlink()
    done = _run(truth_copy / "entity_map_check.py")
    assert done.returncode == 1
    assert "is missing" in done.stdout


def test_kinds_forbidding_anchors_are_not_pending(truth_copy: Path) -> None:
    done = _run(truth_copy / "entity_map_check.py")
    line = next(ln for ln in done.stdout.splitlines() if "without code anchors" in ln)
    listed = {token.strip() for token in line.split(":")[-1].split(",")}
    data = build.load_yaml((truth_copy / "entity_map.yaml").read_text(encoding="utf-8"))
    excused = {e["id"] for e in data["entities"] if not build.anchor_required(data, e)}
    assert excused, "no kind excuses anchors — the test would be vacuous"
    assert not (listed & excused)


def test_hook_emits_json_even_when_the_map_is_unreadable(truth_copy: Path) -> None:
    """The hook is the only live exit of the checker; if it dies silently the
    session loses its guard rail without any signal."""
    (truth_copy / "entity_map.yaml").write_text("{[ not yaml", encoding="utf-8")
    payload = f'{{"tool_input": {{"file_path": "{truth_copy / "entity_map.yaml"}"}}}}'
    done = subprocess.run(
        [sys.executable, str(truth_copy / "entity_map_check.py"), "--hook"],
        input=payload, capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0
    assert '"decision": "block"' in done.stdout
    assert "MAP UNREADABLE" in done.stdout


def _hook(truth_copy: Path, edited: Path) -> subprocess.CompletedProcess[str]:
    payload = f'{{"tool_input": {{"file_path": "{edited}"}}}}'
    return subprocess.run(
        [sys.executable, str(truth_copy / "entity_map_check.py"), "--hook"],
        input=payload, capture_output=True, text=True, check=False,
    )


def test_editing_a_tool_does_not_block_on_stale_views(truth_copy: Path) -> None:
    """Editing the renderer redefines what a fresh view is, so the views go
    stale at that instant and cannot be rebuilt until the edit is finished.
    Blocking there demands the impossible, and a block that cannot be obeyed
    trains the operator to ignore blocks."""
    tool = truth_copy / "entity_map_build.py"
    tool.write_text(tool.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    (truth_copy / "entity_map.md").write_text("stale", encoding="utf-8")
    done = _hook(truth_copy, tool)
    assert '"decision": "block"' not in done.stdout
    assert "expected while a tool is being edited" in done.stdout


def test_editing_the_map_still_blocks_on_stale_views(truth_copy: Path) -> None:
    """The demotion is narrow on purpose: staleness caused by a data edit is
    exactly the forgotten regeneration the check exists to catch."""
    (truth_copy / "entity_map.md").write_text("stale", encoding="utf-8")
    done = _hook(truth_copy, truth_copy / "entity_map.yaml")
    assert '"decision": "block"' in done.stdout


def test_hand_editing_a_generated_view_still_blocks(truth_copy: Path) -> None:
    """The other half of what freshness protects. A generated file has one
    writer; editing it by hand must never be waved through."""
    view = truth_copy / "entity_map.md"
    view.write_text(view.read_text(encoding="utf-8") + "\nsmuggled\n", encoding="utf-8")
    done = _hook(truth_copy, view)
    assert '"decision": "block"' in done.stdout


def test_demotion_covers_tools_only(truth_copy: Path) -> None:
    import entity_map_check as chk
    here = str(chk.HERE.relative_to(chk.ROOT))
    assert chk.edit_invalidated_the_views(f"{here}/entity_map_build.py")
    assert chk.edit_invalidated_the_views(f"{here}/entity_map_check.py")
    assert not chk.edit_invalidated_the_views(f"{here}/entity_map.yaml")
    assert not chk.edit_invalidated_the_views(f"{here}/entity_map.md")
    assert not chk.edit_invalidated_the_views("src/anything.py")


def test_a_real_error_still_blocks_even_when_a_tool_was_edited(truth_copy: Path) -> None:
    """Demoting staleness must not demote anything else: a broken map is still
    a hard stop no matter which file the edit touched."""
    (truth_copy / "entity_map.yaml").write_text("{[ not yaml", encoding="utf-8")
    done = _hook(truth_copy, truth_copy / "entity_map_build.py")
    assert '"decision": "block"' in done.stdout


def test_impact_flags_a_truth_artifact_edit(data: dict[str, Any]) -> None:
    # The path is derived, never spelled out: a literal would pin the suite to
    # today's directory depth and break silently the moment the truth moves.
    rel = str(build.SOURCE.relative_to(check.ROOT))
    lines = check.impact(data, [rel])
    assert any("TRUTH ARTIFACT edited" in line for line in lines)
