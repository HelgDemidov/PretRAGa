"""Mutation harness for the NEW truth system: plant a defect in every check,
demand a red suite.

A green suite is not evidence the tests can fail. Each entry below removes or
inverts exactly one check of one tool — the classifier, the kind obligations,
the schema lock, the provenance audit, the conformance machinery, the answer
scenario — and the whole suite must go red on it.

Marked `heavy`: it runs the suite once per mutation. The cheap anchor tests run
in the ordinary gate, so a moved line surfaces in seconds, not after the whole
heavy pass. The inner run filters on `not heavy`, so the copy's own copy of
this module never recurses.
"""
from __future__ import annotations

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
             '    errors = [f"{n} ({s.module_of[n]}): {why}" for n, why in '
             "sorted(s.unclassified.items())]",
             "    errors = []"),
    Mutation("sum of non-concepts accepted", TRUTH, "        if stray:", "        if False:"),
    Mutation("vocabulary docstring not required", TRUTH,
             '        if not (voc.__doc__ or "").strip():', "        if False:"),
    Mutation("service docstring not required", TRUTH,
             '        if not (fn.__doc__ or "").strip():', "        if False:"),
    Mutation("port failure mode not required", TRUTH,
             "        if port not in declared:", "        if False:"),
    Mutation("stale glossary passes", TRUTH,
             '        elif glossary.read_text(encoding="utf-8") != want:', "        elif False:"),
    Mutation("dynamic-import escapes ignored", TRUTH,
             '    errors += static_import_escapes(src / package.split(".")[0])\n', ""),
    Mutation("package initialiser skipped again", TRUTH,
             '    return [package] + [i.name for i in pkgutil.walk_packages(root.__path__, '
             'prefix=f"{package}.")]',
             '    return [i.name for i in pkgutil.walk_packages(root.__path__, '
             'prefix=f"{package}.")]'),
    Mutation("framework allowlist covers everything", TRUTH,
             '            if modname == f"{package}.kinds" and name in FRAMEWORK:',
             '            if modname == f"{package}.kinds":'),
    # --- kind obligations -------------------------------------------------
    Mutation("value may unset frozen", KINDS,
             '        if not cls.model_config.get("frozen"):', "        if False:"),
    Mutation("definition not required", KINDS,
             '        if not (cls.__doc__ or "").strip():', "        if False:"),
    Mutation("entity may be frozen", KINDS,
             '        if cls.model_config.get("frozen"):', "        if False:"),
    Mutation("entity need not carry a minted identity", KINDS,
             '        if "uuid" not in cls.model_fields:', "        if False:"),
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
    # --- failure-mode machinery -------------------------------------------
    Mutation("raises-mode accepts any exception", CONF,
             "        except SearchUnavailable:", "        except Exception:"),
    Mutation("scenario degrades on any exception", ANSWER,
             "    except SearchUnavailable:", "    except Exception:"),
]


def run_suite(ring: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-m", "not heavy",
         "-p", "no:cacheprovider", "tests"],
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
    assert {m.filename for m in MUTATIONS} == {TRUTH, LOCK, KINDS, AUDIT, ANSWER, CONF}


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
