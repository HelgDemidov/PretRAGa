"""Mutation harness for the NEW truth system: plant a defect in every check,
demand a red suite.

A green suite is not evidence the tests can fail. Each entry below removes or
inverts exactly one check of one tool — the classifier, the kind obligations,
the schema lock, the provenance audit, the conformance machinery, the answer
scenario — and the whole suite must go red on it.

Marked `heavy`: it runs the suite once per mutation. The cheap anchor tests run
in the ordinary gate, so a moved line surfaces in seconds, not after the whole
heavy pass. The inner run excludes THIS module outright, not merely `heavy`:
every mutation rewrites its own anchor, so `test_mutation_anchor_matches_
exactly_once` for the planted one is guaranteed to fail on its own account,
`-x` stops there, and the suite reads "killed" without the tool's own tests
ever running. Measured: 4 of 47 mutations had no other test constraining them
at all, hidden behind this self-inflicted red.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUITE_TIMEOUT_S = 300
_SELF = "test_every_suite_spawning_test_is_marked_heavy"

TRUTH, LOCK = "tools/truth.py", "tools/schema_lock.py"
KINDS = "src/pretraga/domain/kinds.py"
AUDIT = "src/pretraga/usecases/provenance_audit.py"
ANSWER = "src/pretraga/usecases/answering.py"
CONF = "tests/test_conformance.py"
PROVENANCE = "src/pretraga/domain/provenance.py"

_VALIDATOR_DECORATORS = {"model_validator", "field_validator", "root_validator", "validator"}


def _modules_with_imperative_validators() -> set[str]:
    """Same trick as the guarded-tool list: the set of modules owing a planted
    mutation is DERIVED from the domain/usecases source, not maintained by
    hand. Declarative constraints (`Field(ge=0)`, `Field(pattern=...)`) are
    already covered by schema_lock's generic constraint diff; only imperative
    validator logic (a `@model_validator`/`@field_validator` method body) needs
    its own planted defect, because that logic is arbitrary code the lock
    cannot diff structurally."""
    hits: set[str] = set()
    for ring_name in ("domain", "usecases"):
        ring_dir = ROOT / "src" / "pretraga" / ring_name
        for py in sorted(ring_dir.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in node.decorator_list:
                    target = dec.func if isinstance(dec, ast.Call) else dec
                    name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
                    if name in _VALIDATOR_DECORATORS:
                        hits.add(str(py.relative_to(ROOT)))
    return hits


class Mutation(NamedTuple):
    """`find` must occur EXACTLY once in `filename`. `expected_test` is the
    node id that must fail FIRST — a red suite alone proves nothing."""

    name: str
    filename: str
    find: str
    replace: str
    expected_test: str


MUTATIONS = [
    # --- classifier -------------------------------------------------------
    Mutation("unclassified names never reported", TRUTH,
             '    errors += [f"{n} ({s.module_of[n]}): {why}" for n, why in '
             "sorted(s.unclassified.items())]",
             "    pass",
             "tests/test_truth.py::test_an_unclassified_name_blocks"),
    Mutation("structural escapes never reported", TRUTH,
             "    errors = list(s.structural)", "    errors = []",
             "tests/test_truth.py::test_a_surface_escape_blocks"),
    Mutation("kind obligations not re-verified", TRUTH,
             "    errors += kind_obligations(s)", "    pass",
             "tests/test_truth.py::test_a_surface_escape_blocks"),
    Mutation("ring directory without an initialiser accepted", TRUTH,
             "    out.structural += _namespace_packages(package)", "    pass",
             "tests/test_truth.py::test_a_ring_directory_without_an_initialiser_blocks"),
    Mutation("module-level __getattr__ accepted", TRUTH,
             '        if "__getattr__" in vars(mod):', "        if False:",
             "tests/test_truth.py::test_a_surface_escape_blocks"),
    Mutation("a submodule import is classified as a table", TRUTH,
             "            if isinstance(obj, types.ModuleType):", "            if False:",
             "tests/test_truth.py::test_the_untouched_ring_is_green"),
    Mutation("duplicate bare names accepted", TRUTH,
             "            if name in out.module_of:", "            if False:",
             "tests/test_truth.py::test_a_duplicate_bare_name_blocks"),
    Mutation("nested concepts accepted", TRUTH,
             "    out.structural += _nested_concepts(out, entity, value)", "    pass",
             "tests/test_truth.py::test_a_surface_escape_blocks"),
    Mutation("public callable without a role accepted", TRUTH,
             "    elif callable(obj):", "    elif False:",
             "tests/test_truth.py::test_a_surface_escape_blocks"),
    Mutation("ImportFrom names escape the import set", TRUTH,
             "        elif isinstance(node, ast.ImportFrom):", "        elif False:",
             "tests/test_conformance.py::test_every_port_is_either_covered_or_openly_uncovered"),
    Mutation("sum of non-concepts accepted", TRUTH, "        if stray:", "        if False:",
             "tests/test_truth.py::test_an_unclassified_name_blocks"),
    Mutation("vocabulary docstring not required", TRUTH,
             '        if not (voc.__doc__ or "").strip():', "        if False:",
             "tests/test_truth.py::test_an_unclassified_name_blocks"),
    Mutation("service docstring not required", TRUTH,
             '        if not (fn.__doc__ or "").strip():', "        if False:",
             "tests/test_truth.py::test_a_service_without_a_docstring_blocks"),
    Mutation("port failure mode not required", TRUTH,
             "        if port not in declared:", "        if False:",
             "tests/test_truth.py::test_an_unclassified_name_blocks"),
    Mutation("conventions dropped from the glossary", TRUTH,
             '    out.extend(["## Conventions", "", inspect.cleandoc(pkg.__doc__ or ""), ""])',
             "    pass",
             "tests/test_truth.py::test_the_untouched_ring_is_green"),
    Mutation("stale glossary passes", TRUTH,
             '        elif glossary.read_text(encoding="utf-8") != want:', "        elif False:",
             "tests/test_truth.py::test_a_stale_glossary_blocks"),
    Mutation("dynamic-import escapes ignored", TRUTH,
             '    errors += static_import_escapes(src / package.split(".")[0])\n', "",
             "tests/test_truth.py::test_a_dynamic_import_escape_blocks"),
    Mutation("package initialiser skipped again", TRUTH,
             '    out = [(package, pkg_dir / "__init__.py")]', "    out = []",
             "tests/test_truth.py::test_an_unclassified_name_blocks"),
    Mutation("framework allowlist covers everything", TRUTH,
             '            if modname == f"{package}.kinds" and name in FRAMEWORK:',
             '            if modname == f"{package}.kinds":',
             "tests/test_schema_lock.py::test_the_untouched_ring_is_green"),
    Mutation("build writes an invalid survey unconditionally", TRUTH,
             "        errors = classification_errors(s) + static_import_escapes(ns.src / "
             'ns.package.split(".")[0])\n        if errors:',
             "        errors = []\n        if errors:",
             "tests/test_truth.py::test_build_refuses_to_write_from_an_invalid_survey"),
    # --- provenance value invariants ---------------------------------------
    Mutation("CharSpan accepts an inverted span", PROVENANCE,
             "        if self.start > self.end:", "        if False:",
             "tests/test_provenance.py::test_a_char_span_with_start_after_end_is_rejected"),
    # --- kind obligations -------------------------------------------------
    Mutation("value may unset frozen", KINDS,
             '        if not cls.model_config.get("frozen"):', "        if False:",
             "tests/test_kinds.py::test_a_value_may_not_unset_frozen"),
    Mutation("definition not required", KINDS,
             '        if not (cls.__doc__ or "").strip():', "        if False:",
             "tests/test_kinds.py::test_a_concept_without_a_definition_is_rejected"),
    Mutation("entity may be frozen", KINDS,
             '        if cls.model_config.get("frozen"):', "        if False:",
             "tests/test_kinds.py::test_an_entity_may_not_be_frozen"),
    Mutation("entity need not carry a minted identity", KINDS,
             '        if "uuid" not in cls.model_fields:', "        if False:",
             "tests/test_kinds.py::test_an_entity_may_not_shadow_its_minted_identity"),
    Mutation("private-name exemption reinstated", KINDS,
             "        super().__pydantic_init_subclass__(**kwargs)\n"
             '        if not cls.model_config.get("frozen"):',
             "        super().__pydantic_init_subclass__(**kwargs)\n"
             '        if cls.__name__.startswith("_"):\n            return\n'
             '        if not cls.model_config.get("frozen"):',
             "tests/test_kinds.py::test_an_underscore_name_does_not_exempt_the_frozen_obligation"),
    # --- schema lock ------------------------------------------------------
    Mutation("constraint repr records every field again", LOCK,
             "            if getattr(m, f.name) is not None]", "            if True]",
             "tests/test_schema_lock.py::test_the_untouched_ring_is_green"),
    Mutation("callable constraint field reprs by address again", LOCK,
             'parts = (f"{k}={_factory_name(v)}" if callable(v) else f"{k}={v!r}" for k, v in kept)',
             'parts = (f"{k}={v!r}" for k, v in kept)',
             "tests/test_schema_lock.py::test_constraint_repr_names_a_callable_field_without_an_address"),
    Mutation("lambda validator accepted", LOCK,
             '                    if callable(v) and "<lambda>" in _factory_name(v):',
             "                    if False:",
             "tests/test_schema_lock.py::test_a_lambda_validator_is_refused"),
    Mutation("removed field not breaking", LOCK,
             '            breaking.append(f"{name}.{f}: field removed")', "            pass",
             "tests/test_schema_lock.py::test_a_breaking_change_blocks"),
    Mutation("type change invisible", LOCK,
             '            if a["type"] != b["type"]:', "            if False:",
             "tests/test_schema_lock.py::test_a_breaking_change_blocks"),
    Mutation("vocabulary member removal not breaking", LOCK,
             '                breaking.append(f"{name}.{m}: vocabulary member removed — '
             'stored records "\n                                "carrying it stop validating")',
             "                pass",
             "tests/test_schema_lock.py::test_a_breaking_change_blocks"),
    Mutation("generic parameters collapsed again", LOCK,
             "    if typing.get_origin(annotation) is not None:", "    if False:",
             "tests/test_schema_lock.py::test_the_untouched_ring_is_green"),
    Mutation("nested annotated constraint reprs whole again", LOCK,
             "    if typing.get_origin(annotation) is Annotated:\n        found.append(annotation)",
             "    if False:\n        found.append(annotation)",
             "tests/test_schema_lock.py::test_the_untouched_ring_is_green"),
    Mutation("default change invisible", LOCK,
             '            elif a.get("default") != b.get("default") or a.get("factory") != '
             'b.get("factory"):',
             "            elif False:",
             "tests/test_schema_lock.py::test_a_breaking_change_blocks"),
    Mutation("breaking write accepted without a major version bump", LOCK,
             "        if breaking and not proper_bump:",
             "        if False:",
             "tests/test_schema_lock.py::test_a_breaking_write_without_a_new_version_is_refused"),
    Mutation("computed field removal not breaking", LOCK,
             '            breaking.append(f"{name}.{f}: computed field removed — it is written '
             'into every record")',
             "            pass",
             "tests/test_schema_lock.py::test_a_wire_format_change_that_touches_no_field_blocks"),
    Mutation("serialiser change invisible", LOCK,
             '        if o.get("serializers", []) != n.get("serializers", []):',
             "        if False:",
             "tests/test_schema_lock.py::test_a_wire_format_change_that_touches_no_field_blocks"),
    Mutation("alias channels beyond the first ignored", LOCK,
             "                    if a.get(key) != b.get(key):", "                    if False:",
             "tests/test_schema_lock.py::test_dropping_a_union_discriminator_blocks"),
    Mutation("lambda default factory accepted", LOCK,
             '            if fi.default_factory is not None and "<lambda>" in '
             "_factory_name(fi.default_factory):",
             "            if False:",
             "tests/test_schema_lock.py::test_a_lambda_default_factory_is_refused"),
    Mutation("factory named without its module", LOCK,
             '    return f"{mod}.{qual}" if qual and mod else str(factory)',
             "    return qual if qual else str(factory)",
             "tests/test_schema_lock.py::test_constraint_repr_names_a_callable_field_without_an_address"),
    Mutation("deleting the lock skips the version decision", LOCK,
             '        stored = _lock_at(lock_path, "HEAD")', "        stored = None",
             "tests/test_schema_lock.py::test_deleting_the_lock_is_not_a_way_past_the_version_decision"),
    Mutation("lock drift against history ignored", LOCK,
             "        if drift and not proper_bump:",
             "        if False:",
             "tests/test_schema_lock.py::test_a_lock_rewritten_by_hand_against_history_blocks"),
    Mutation("model_config change invisible", LOCK,
             '                breaking.append(f"{name}: model_config[{k}] {oc.get(k)} -> '
             '{nc.get(k)}")',
             "                pass",
             "tests/test_schema_lock.py::test_a_breaking_change_blocks"),
    # --- provenance audit -------------------------------------------------
    Mutation("tampered raw bytes accepted", AUDIT,
             "        elif hashlib.sha256(data).hexdigest() != raw.content_hash:",
             "        elif False:",
             "tests/test_provenance_audit.py::test_tampered_bytes_under_the_same_key_are_caught"),
    Mutation("tampered canonical text accepted", AUDIT,
             "        if hashlib.sha256(text.body.encode()).hexdigest() != text.content_hash:",
             "        if False:",
             "tests/test_provenance_audit.py::test_a_tampered_canonical_text_under_the_same_key_is_caught"),
    Mutation("anchor bounds unchecked", AUDIT,
             "        if not (0 <= anchor.span.start <= anchor.span.end <= len(text.body)):",
             "        if False:",
             "tests/test_provenance_audit.py::test_an_anchor_pointing_outside_the_text_is_caught"),
    Mutation("a substituted canonical text accepted", AUDIT,
             "        if text.content_hash != anchor.text_hash:", "        if False:",
             "tests/test_provenance_audit.py::test_a_substituted_answer_is_caught_even_though_it_is_self_consistent"),
    Mutation("a substituted raw payload accepted", AUDIT,
             "        if raw.content_hash != text.conversion.source:", "        if False:",
             "tests/test_provenance_audit.py::test_a_substituted_raw_payload_is_caught"),
    Mutation("the examined count taken from a second call", AUDIT,
             "    sampled = list(store.claims(sample))\n"
             "    return len(sampled), audit(_SampledOnce(store, sampled), sample)",
             "    return len(store.claims(sample)), audit(store, sample)",
             "tests/test_provenance_audit.py::test_the_examined_count_comes_from_the_audited_sample"),
    Mutation("messages carry a truncated key again", AUDIT,
             '    return (f"claim #{index} @{c.anchor.text_hash}:{c.anchor.span.start}-'
             '{c.anchor.span.end} "\n            f"{c.normalized[:40]!r}")',
             '    return f"claim {c.normalized[:40]!r}"',
             "tests/test_provenance_audit.py::test_span_errors_are_distinguishable_by_the_full_anchor_key"),
    # --- failure-mode machinery -------------------------------------------
    Mutation("raises-mode accepts any exception", CONF,
             "        except SearchUnavailable:", "        except Exception:",
             "tests/test_conformance.py::test_raises_mode_rejects_a_foreign_exception"),
    Mutation("scenario degrades on any exception", ANSWER,
             "    except SearchUnavailable:", "    except Exception:",
             "tests/test_answering.py::test_a_foreign_exception_propagates_instead_of_degrading"),
]


def run_suite(ring: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-m", "not heavy",
         "-p", "no:cacheprovider", "--ignore=tests/test_mutations.py", "tests"],
        capture_output=True, text=True, check=False, timeout=SUITE_TIMEOUT_S, cwd=ring,
        env={"PYTHONPATH": f"{ring / 'src'}:{ring / 'tools'}", "PATH": "/usr/bin:/bin"})


# ---------------------------------------------------------------- cheap gate

def test_mutation_names_are_unique() -> None:
    names = [m.name for m in MUTATIONS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.name)
def test_mutation_anchor_matches_exactly_once(mutation: Mutation) -> None:
    source = (ROOT / mutation.filename).read_text(encoding="utf-8")
    assert source.count(mutation.find) == 1, (
        f"anchor for {mutation.name!r} matches {source.count(mutation.find)} times in "
        f"{mutation.filename} — the code moved; re-anchor the mutation")
    assert mutation.find != mutation.replace
    assert mutation.expected_test, f"{mutation.name!r}: no expected_test declared"


def test_every_tool_and_guarded_module_is_mutated() -> None:
    """A NEW tool cannot ship without planted mutations: the demanded set is
    derived from the filesystem, not from this file's memory of it. Same for a
    NEW imperative validator anywhere in domain/usecases — declarative
    constraints are already covered by schema_lock's generic diff, so only
    modules with actual validator-decorated code owe a planted mutation."""
    tools = {f"tools/{p.name}" for p in (ROOT / "tools").glob("*.py")}
    mutated = {m.filename for m in MUTATIONS}
    assert tools <= mutated, f"tool module(s) without a mutation: {sorted(tools - mutated)}"
    needed = tools | {KINDS, AUDIT, ANSWER, CONF} | _modules_with_imperative_validators()
    assert mutated == needed, (
        f"missing: {sorted(needed - mutated)}, extra: {sorted(mutated - needed)}")


def test_every_suite_spawning_test_is_marked_heavy() -> None:
    import inspect

    module = sys.modules[__name__]
    for name, obj in vars(module).items():
        if not name.startswith("test_") or not callable(obj) or name == _SELF:
            continue
        if "run_suite(" not in inspect.getsource(obj):
            continue
        marks = {m.name for m in getattr(obj, "pytestmark", [])}
        assert "heavy" in marks, f"{name} spawns a suite but is not marked heavy"


# ------------------------------------------------------------------- harness

@pytest.mark.heavy
def test_untouched_ring_suite_is_green(ring: Path) -> None:
    """The control. Without it a red result could just mean the copy is broken."""
    done = run_suite(ring)
    assert done.returncode == 0, done.stdout[-3000:]


@pytest.mark.heavy
@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.name)
def test_planted_defect_turns_the_suite_red(mutation: Mutation, ring: Path) -> None:
    target = ring / mutation.filename
    source = target.read_text(encoding="utf-8")
    assert source.count(mutation.find) == 1
    target.write_text(source.replace(mutation.find, mutation.replace, 1), encoding="utf-8")

    done = run_suite(ring)
    assert done.returncode != 0, (
        f"mutation {mutation.name!r} SURVIVED — no test constrains this behaviour\n"
        + done.stdout[-3000:])
    killer = re.search(r"^FAILED (\S+?::[A-Za-z_]\w*)", done.stdout, re.MULTILINE)
    got = killer.group(1) if killer else None
    assert got == mutation.expected_test, (
        f"mutation {mutation.name!r} killed by {got!r}, expected {mutation.expected_test!r} — "
        "a red suite is not evidence of the RIGHT kill\n" + done.stdout[-3000:])
