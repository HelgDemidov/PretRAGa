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
    loaded: dict[str, Any] = yaml.safe_load(source_text)
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


@pytest.mark.parametrize("block", ["kinds", "relation_classes", "relation_types", "triggers"])
def test_missing_vocabulary_block_is_rejected(data: dict[str, Any], block: str) -> None:
    del data[block]
    assert any(f"missing top-level {block} block" in e for e in build.validate(data))


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
        entity["attributes"] = [{"name": "smuggled", "status": "fixed"}]
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


def test_placeholder_without_trigger_is_rejected(data: dict[str, Any]) -> None:
    for e in data["entities"]:
        for a in build._attrs(e):
            if a["status"] == "placeholder":
                del a["trigger"]
                assert any("placeholder without trigger" in err for err in build.validate(data))
                return
    pytest.fail("no placeholder in the map to mutate")


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
    entity["attributes"].append({"name": "uuid", "status": "fixed", "marks": "identity"})
    after = build.obligations(data)
    assert (eid, entity["kind"], build.OBLIGATION_LABEL["identity"]) not in after
    assert len(after) == len(build.obligations(yaml.safe_load(build.SOURCE.read_text("utf-8")))) - 1


@given(dropped=st.sets(st.integers(min_value=0, max_value=200)))
@PROPERTY
def test_obligations_stay_justified_on_any_subgraph(source_text: str, dropped: set[int]) -> None:
    """Constructed around the real map rather than generated from nothing:
    drop an arbitrary subset of its relations and the registry must still only
    report gaps its kinds actually require. Dropping edges can only ADD gaps —
    it must never invent one for a kind that does not ask for it."""
    data = yaml.safe_load(source_text)
    data["relations"] = [r for i, r in enumerate(data["relations"]) if i not in dropped]
    _obligations_are_justified(data)


@given(dropped=st.sets(st.integers(min_value=0, max_value=200), min_size=1))
@PROPERTY
def test_dropping_relations_never_reduces_the_registry(source_text: str, dropped: set[int]) -> None:
    data = yaml.safe_load(source_text)
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
    data = yaml.safe_load((truth_copy / "entity_map.yaml").read_text(encoding="utf-8"))
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


def test_impact_flags_a_truth_artifact_edit(data: dict[str, Any]) -> None:
    # The path is derived, never spelled out: a literal would pin the suite to
    # today's directory depth and break silently the moment the truth moves.
    rel = str(build.SOURCE.relative_to(check.ROOT))
    lines = check.impact(data, [rel])
    assert any("TRUTH ARTIFACT edited" in line for line in lines)
