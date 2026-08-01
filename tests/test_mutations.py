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
    """`find` must occur EXACTLY once in `filename`, or the harness would be
    testing something other than what it names."""

    name: str
    filename: str
    find: str
    replace: str


MUTATIONS = [
    # --- classifier -------------------------------------------------------
    Mutation("unclassified names never reported", TRUTH,
             '    errors += [f"{n} ({s.module_of[n]}): {why}" for n, why in '
             "sorted(s.unclassified.items())]",
             "    pass"),
    Mutation("structural escapes never reported", TRUTH,
             "    errors = list(s.structural)", "    errors = []"),
    Mutation("kind obligations not re-verified", TRUTH,
             "    errors += kind_obligations(s)", "    pass"),
    Mutation("ring directory without an initialiser accepted", TRUTH,
             "    out.structural += _namespace_packages(package)", "    pass"),
    Mutation("module-level __getattr__ accepted", TRUTH,
             '        if "__getattr__" in vars(mod):', "        if False:"),
    Mutation("a submodule import is classified as a table", TRUTH,
             "            if isinstance(obj, types.ModuleType):", "            if False:"),
    Mutation("duplicate bare names accepted", TRUTH,
             "            if name in out.module_of:", "            if False:"),
    Mutation("nested concepts accepted", TRUTH,
             "    out.structural += _nested_concepts(out, entity, value)", "    pass"),
    Mutation("public callable without a role accepted", TRUTH,
             "    elif callable(obj):", "    elif False:"),
    Mutation("ImportFrom names escape the import set", TRUTH,
             "        elif isinstance(node, ast.ImportFrom):", "        elif False:"),
    Mutation("sum of non-concepts accepted", TRUTH, "        if stray:", "        if False:"),
    Mutation("vocabulary docstring not required", TRUTH,
             '        if not (voc.__doc__ or "").strip():', "        if False:"),
    Mutation("service docstring not required", TRUTH,
             '        if not (fn.__doc__ or "").strip():', "        if False:"),
    Mutation("port failure mode not required", TRUTH,
             "        if port not in declared:", "        if False:"),
    Mutation("conventions dropped from the glossary", TRUTH,
             '    out.extend(["## Conventions", "", inspect.cleandoc(pkg.__doc__ or ""), ""])',
             "    pass"),
    Mutation("stale glossary passes", TRUTH,
             '        elif glossary.read_text(encoding="utf-8") != want:', "        elif False:"),
    Mutation("dynamic-import escapes ignored", TRUTH,
             '    errors += static_import_escapes(src / package.split(".")[0])\n', ""),
    Mutation("package initialiser skipped again", TRUTH,
             '    out = [(package, pkg_dir / "__init__.py")]', "    out = []"),
    Mutation("framework allowlist covers everything", TRUTH,
             '            if modname == f"{package}.kinds" and name in FRAMEWORK:',
             '            if modname == f"{package}.kinds":'),
    Mutation("build writes an invalid survey unconditionally", TRUTH,
             "        errors = classification_errors(s) + static_import_escapes(ns.src / "
             'ns.package.split(".")[0])\n        if errors:',
             "        errors = []\n        if errors:"),
    # --- provenance value invariants ---------------------------------------
    Mutation("CharSpan accepts an inverted span", PROVENANCE,
             "        if self.start > self.end:", "        if False:"),
    # --- kind obligations -------------------------------------------------
    Mutation("value may unset frozen", KINDS,
             '        if not cls.model_config.get("frozen"):', "        if False:"),
    Mutation("definition not required", KINDS,
             '        if not (cls.__doc__ or "").strip():', "        if False:"),
    Mutation("entity may be frozen", KINDS,
             '        if cls.model_config.get("frozen"):', "        if False:"),
    Mutation("entity need not carry a minted identity", KINDS,
             '        if "uuid" not in cls.model_fields:', "        if False:"),
    Mutation("private-name exemption reinstated", KINDS,
             "        super().__pydantic_init_subclass__(**kwargs)\n"
             '        if not cls.model_config.get("frozen"):',
             "        super().__pydantic_init_subclass__(**kwargs)\n"
             '        if cls.__name__.startswith("_"):\n            return\n'
             '        if not cls.model_config.get("frozen"):'),
    # --- schema lock ------------------------------------------------------
    Mutation("removed field not breaking", LOCK,
             '            breaking.append(f"{name}.{f}: field removed")', "            pass"),
    Mutation("type change invisible", LOCK,
             '            if a["type"] != b["type"]:', "            if False:"),
    Mutation("vocabulary member removal not breaking", LOCK,
             '                breaking.append(f"{name}.{m}: vocabulary member removed — '
             'stored records "\n                                "carrying it stop validating")',
             "                pass"),
    Mutation("generic parameters collapsed again", LOCK,
             "    if typing.get_origin(annotation) is not None:", "    if False:"),
    Mutation("default change invisible", LOCK,
             '            elif a.get("default") != b.get("default") or a.get("factory") != '
             'b.get("factory"):',
             "            elif False:"),
    Mutation("breaking write accepted without a major version bump", LOCK,
             "        if breaking and not proper_bump:",
             "        if False:"),
    Mutation("computed field removal not breaking", LOCK,
             '            breaking.append(f"{name}.{f}: computed field removed — it is written '
             'into every record")',
             "            pass"),
    Mutation("serialiser change invisible", LOCK,
             '        if o.get("serializers", []) != n.get("serializers", []):',
             "        if False:"),
    Mutation("alias channels beyond the first ignored", LOCK,
             "                    if a.get(key) != b.get(key):", "                    if False:"),
    Mutation("lambda default factory accepted", LOCK,
             '            if fi.default_factory is not None and "<lambda>" in '
             "_factory_name(fi.default_factory):",
             "            if False:"),
    Mutation("factory named without its module", LOCK,
             '    return f"{mod}.{qual}" if qual and mod else str(factory)',
             "    return qual if qual else str(factory)"),
    Mutation("deleting the lock skips the version decision", LOCK,
             '        stored = _lock_at(lock_path, "HEAD")', "        stored = None"),
    Mutation("lock drift against history ignored", LOCK,
             "        if drift and not proper_bump:",
             "        if False:"),
    Mutation("model_config change invisible", LOCK,
             '                breaking.append(f"{name}: model_config[{k}] {oc.get(k)} -> '
             '{nc.get(k)}")',
             "                pass"),
    # --- provenance audit -------------------------------------------------
    Mutation("tampered raw bytes accepted", AUDIT,
             "        elif hashlib.sha256(data).hexdigest() != raw.content_hash:",
             "        elif False:"),
    Mutation("tampered canonical text accepted", AUDIT,
             "        if hashlib.sha256(text.body.encode()).hexdigest() != text.content_hash:",
             "        if False:"),
    Mutation("anchor bounds unchecked", AUDIT,
             "        if not (0 <= anchor.span.start <= anchor.span.end <= len(text.body)):",
             "        if False:"),
    Mutation("a substituted canonical text accepted", AUDIT,
             "        if text.content_hash != anchor.text_hash:", "        if False:"),
    Mutation("a substituted raw payload accepted", AUDIT,
             "        if raw.content_hash != text.conversion.source:", "        if False:"),
    Mutation("the examined count taken from a second call", AUDIT,
             "    sampled = list(store.claims(sample))\n"
             "    return len(sampled), audit(_SampledOnce(store, sampled), sample)",
             "    return len(store.claims(sample)), audit(store, sample)"),
    Mutation("messages carry a truncated key again", AUDIT,
             '    return (f"claim #{index} @{c.anchor.text_hash}:{c.anchor.span.start}-'
             '{c.anchor.span.end} "\n            f"{c.normalized[:40]!r}")',
             '    return f"claim {c.normalized[:40]!r}"'),
    # --- failure-mode machinery -------------------------------------------
    Mutation("raises-mode accepts any exception", CONF,
             "        except SearchUnavailable:", "        except Exception:"),
    Mutation("scenario degrades on any exception", ANSWER,
             "    except SearchUnavailable:", "    except Exception:"),
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
