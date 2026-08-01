"""Negative tests for the classification checker: one per rule it enforces.

Every case is planted in a COPY of the ring under tmp_path and run through the
real entry point in a subprocess, so the test exercises what CI exercises.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import truth


def _ENV(ring: Path) -> dict[str, str]:
    """PYTHONDONTWRITEBYTECODE is not a tidiness setting here.

    Measured: a subprocess left `__pycache__` in the ring, a later edit changed
    the file to the SAME length within the SAME second, and every subsequent
    subprocess imported the stale bytecode — the check under test ran against
    code that no longer existed and reported OK. A green test that proves
    nothing is worse than a red one.
    """
    return {"PYTHONPATH": str(ring / "src"), "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1"}


def _run(ring: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/truth.py"], cwd=ring, capture_output=True, text=True,
        env=_ENV(ring), check=False)


def _plant(ring: Path, filename: str, body: str) -> None:
    (ring / "src" / "pretraga" / "domain" / filename).write_text(
        textwrap.dedent(body), encoding="utf-8")


def test_the_untouched_ring_is_green(ring: Path) -> None:
    """The control. Without it a red result could just mean the copy is broken."""
    done = _run(ring)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize(
    ("name", "filename", "body", "expected"),
    [
        ("bare pydantic model", "x1.py", """
            from pydantic import BaseModel
            class Loose(BaseModel):
                '''No kind.'''
                x: int
        """, "neither an Entity nor a Value"),
        ("plain class", "x2.py", """
            class Plain:
                '''No kind.'''
        """, "no kind"),
        ("dataclass", "x3.py", """
            from dataclasses import dataclass
            @dataclass
            class Loose2:
                '''No kind.'''
                x: int = 0
        """, "no kind"),
        ("sum of non-concepts", "x4.py", """
            Bad = int | str
        """, "are not concepts"),
        ("PEP 695 alias of non-concepts", "x5.py", """
            type Weird = int | str
        """, "are not concepts"),
        ("vocabulary without a docstring", "x6.py", """
            from enum import StrEnum
            class Mystery(StrEnum):
                A = "a"
        """, "no docstring"),
        ("port with no declared failure mode", "x7.py", """
            from typing import Protocol
            class Orphan(Protocol):
                '''An interface nobody classified.'''
                def go(self) -> None: ...
        """, "FAILURE_MODES"),
        ("smuggled through the package initialiser", "__init__.py", """
            from pydantic import BaseModel
            class HidingInInit(BaseModel):
                '''Smuggled.'''
                x: int
        """, "neither an Entity nor a Value"),
    ],
)
def test_an_unclassified_name_blocks(ring: Path, name: str, filename: str,
                                     body: str, expected: str) -> None:
    _plant(ring, filename, body)
    done = _run(ring)
    assert done.returncode == 1, f"{name} was accepted:\n{done.stdout}"
    assert expected in done.stdout, done.stdout


@pytest.mark.parametrize(
    ("name", "filename", "body", "expected"),
    [
        ("a callable that is not a function", "y1.py", """
            import functools
            def _pick(table: dict[str, str], surface: str) -> str:
                return table.get(surface, surface)
            normalise = functools.partial(_pick, {"EC": "European Commission"})
        """, "not a function"),
        ("a concept nested inside a concept", "y2.py", '''
            from pretraga.domain.kinds import Value
            class Envelope(Value):
                """A locked value carrying an unlocked one."""
                class Meta(Value):
                    """Nested, persisted, invisible."""
                    weight: int
                meta: Meta
        ''', "nested inside a concept"),
        ("a module-level __getattr__", "y3.py", '''
            from typing import Any
            from pretraga.domain.kinds import Value
            def __getattr__(name: str) -> Any:
                class Ghost(Value):
                    """Materialised on access."""
                    payload: str
                return Ghost
        ''', "only on access"),
        ("a value thawed after class creation", "y5.py", '''
            from pretraga.domain.kinds import Value
            class Thawed(Value):
                """A value whose obligation was undone after it was created."""
                payload: str
            Thawed.model_config["frozen"] = False
            Thawed.model_rebuild(force=True)
        ''', "not frozen"),
        ("a definition removed after class creation", "y6.py", '''
            from pretraga.domain.kinds import Value
            class Undefined(Value):
                """This docstring does not survive the module."""
                payload: str
            Undefined.__doc__ = None
        ''', "no docstring"),
    ],
)
def test_a_surface_escape_blocks(ring: Path, name: str, filename: str,
                                 body: str, expected: str) -> None:
    """Ways a name left the public surface without leaving the code. Each was
    measured passing the whole six-step gate before the check that names it."""
    _plant(ring, filename, body)
    done = _run(ring)
    assert done.returncode == 1, f"{name} was accepted:\n{done.stdout}"
    assert expected in done.stdout, done.stdout


def test_a_declaration_nested_in_a_composite_statement_is_classified(ring: Path) -> None:
    """A class declared inside try:/if:/with:/for: is bound at module level
    exactly like a top-level one — the top-level-only AST reading this
    replaced made it invisible, while the class was live and importable."""
    _plant(ring, "y9.py", '''
        from pretraga.domain.kinds import Value
        try:
            class Nested(Value):
                """Declared inside a try: block."""
                payload: str
        except ImportError:
            pass
    ''')
    done = subprocess.run([sys.executable, "tools/truth.py", "--build"], cwd=ring,
                          capture_output=True, text=True, env=_ENV(ring), check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    glossary = (ring / "docs" / "design_truth" / "domain_glossary.md").read_text(encoding="utf-8")
    assert "Nested" in glossary, glossary


def test_a_class_that_rewrites_its_module_is_still_classified_where_it_lives(
        ring: Path) -> None:
    """The survey decides where a name lives by where it is actually BOUND,
    never by a self-reported __module__ — so a class lying about it is still
    found, not dropped."""
    _plant(ring, "y4.py", '''
        from pretraga.domain.kinds import Value
        class Relocated(Value):
            """A value that lies about where it lives."""
            payload: str
        Relocated.__module__ = "pretraga.domain.kinds"
    ''')
    done = subprocess.run([sys.executable, "tools/truth.py", "--build"], cwd=ring,
                          capture_output=True, text=True, env=_ENV(ring), check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    glossary = (ring / "docs" / "design_truth" / "domain_glossary.md").read_text(encoding="utf-8")
    assert "Relocated" in glossary, glossary


def test_a_duplicate_bare_name_blocks(ring: Path) -> None:
    """Survey, glossary and lock all key on the bare name, so the second
    declaration used to replace the first in silence — two live persisted
    shapes, one locked entry, and the loser's shape guarded by nothing."""
    _plant(ring, "y7.py", '''
        from pretraga.domain.kinds import Value
        class Claim(Value):
            """A DIFFERENT Claim: same name, wrong shape."""
            whatever: int
    ''')
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "declared in both" in done.stdout, done.stdout


def test_a_ring_directory_without_an_initialiser_blocks(ring: Path) -> None:
    """Measured: such a directory is invisible to this survey AND to
    import-linter, so a domain module could reach the network from inside one
    while all three contracts reported kept."""
    sub = ring / "src" / "pretraga" / "domain" / "enrichment"
    sub.mkdir()
    (sub / "shapes.py").write_text(
        '"""A stage subpackage that forgot its initialiser."""\n'
        "from pretraga.domain.kinds import Value\n\n\n"
        'class Buried(Value):\n    """A persisted value nobody surveys."""\n\n    payload: str\n',
        encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "__init__.py" in done.stdout, done.stdout


def test_a_private_class_bound_to_a_public_name_cannot_dodge_its_kind(ring: Path) -> None:
    """The obligations used to skip any class whose name began with an
    underscore, so a private class plus a public alias produced a mutable,
    undefined Value that the whole gate accepted."""
    _plant(ring, "y8.py", '''
        from pretraga.domain.kinds import Value
        class _Loose(Value, frozen=False):
            """A documented private class trying to dodge its kind."""

            payload: str
        Loose = _Loose
    ''')
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    out = done.stdout + done.stderr
    # Measured: matching bare "frozen" passed regardless of this check, because
    # an uncaught KindError's traceback always contains the frame label
    # "<frozen importlib._bootstrap>" — neither text below is that label, and
    # either is genuine evidence the obligation itself fired (at class creation
    # or, if that exemption is reinstated, from the survey's level-triggered
    # re-check).
    assert "is frozen" in out or "not frozen" in out, out


def test_module_level_data_has_a_role(ring: Path) -> None:
    """FAILURE_MODES is the system's own registry and used to fall through the
    survey's silent `else`, so 'every public name has a role' was already false
    for the shipped ring."""
    del ring
    s = truth.survey()
    assert "FAILURE_MODES" in s.tables
    assert "FAILURE_MODES" in truth.render_glossary(s)


def test_a_submodule_import_is_not_classified_as_a_table(ring: Path) -> None:
    """Importing any submodule binds it onto the parent package as a side
    effect of Python's import system, not a declaration — measured: without
    the skip, `domain.kinds` classified itself as a table beside FAILURE_MODES."""
    del ring
    s = truth.survey()
    assert "kinds" not in s.tables
    assert "facts" not in s.tables


def test_imported_names_covers_both_import_forms(tmp_path: Path) -> None:
    """The closed set of ways to bind a name via import: two AST node types.
    Nesting inside try:/if:/with:/for: is free, because an import in a branch
    is still an import — unlike the open-ended set of ways to DECLARE one,
    which is why declared names are read as the complement of this set."""
    probe = tmp_path / "probe.py"
    probe.write_text("""
try:
    import os
    from collections import OrderedDict as OD
except ImportError:
    pass
""", encoding="utf-8")
    assert truth._imported_names(probe) == {"os", "OD"}


@pytest.mark.parametrize("call", ["__import__('urllib.request')", "eval('1+1')", "exec('x=1')"])
def test_a_dynamic_import_escape_blocks(ring: Path, call: str) -> None:
    """The ring contract is read statically, so it only holds while imports are
    static. import-linter cannot see these, which is why this check exists."""
    target = ring / "src" / "pretraga" / "domain" / "facts.py"
    target.write_text(target.read_text(encoding="utf-8")
                      + f"\n\ndef late() -> object:\n    return {call}\n", encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "checkable" in done.stdout, done.stdout


def test_a_stale_glossary_blocks(ring: Path) -> None:
    glossary = ring / "docs" / "design_truth" / "domain_glossary.md"
    glossary.write_text(glossary.read_text(encoding="utf-8") + "\nedited by hand\n",
                        encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 1
    assert "stale or hand-edited" in done.stdout


def test_a_missing_glossary_blocks(ring: Path) -> None:
    (ring / "docs" / "design_truth" / "domain_glossary.md").unlink()
    done = _run(ring)
    assert done.returncode == 1
    assert "missing" in done.stdout


def test_a_definition_change_shows_up_in_the_glossary(ring: Path) -> None:
    """The glossary is generated from docstrings, so a redefinition cannot be
    made without the generated view moving with it."""
    target = ring / "src" / "pretraga" / "domain" / "facts.py"
    target.write_text(target.read_text(encoding="utf-8").replace(
        "not a truth about the world.", "and also a truth about the world."), encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 1
    assert "stale" in done.stdout


def test_build_refuses_to_write_from_an_invalid_survey(ring: Path) -> None:
    """--build used to write unconditionally: an unclassified name was simply
    absent from the output with exit 0 and the word 'written' — the closest
    thing to a green light a developer following the documented workflow
    would see."""
    _plant(ring, "y10.py", """
        class NoKind:
            '''A public class in domain/ with no Entity/Value base.'''
            x: int = 0
    """)
    done = subprocess.run([sys.executable, "tools/truth.py", "--build"], cwd=ring,
                          capture_output=True, text=True, env=_ENV(ring), check=False)
    assert done.returncode == 1, done.stdout
    assert "no kind" in done.stdout, done.stdout
    glossary = (ring / "docs" / "design_truth" / "domain_glossary.md")
    assert "NoKind" not in glossary.read_text(encoding="utf-8")


def test_failure_modes_may_not_list_a_non_port() -> None:
    s = truth.survey()
    assert set(s.ports) == {"SemanticSearch", "LexicalSearch", "GraphExpansion"}


def test_a_class_smuggled_into_the_framework_module_blocks(ring: Path) -> None:
    """kinds.py is surveyed like any module, minus the closed FRAMEWORK
    allowlist — measured: excluding the whole module let anything hide there."""
    target = ring / "src" / "pretraga" / "domain" / "kinds.py"
    target.write_text(target.read_text(encoding="utf-8")
                      + "\n\nclass SmuggledThroughKinds:\n"
                      "    \"\"\"A stray class hiding beside the framework.\"\"\"\n",
                      encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "SmuggledThroughKinds" in done.stdout


def test_a_service_without_a_docstring_blocks(ring: Path) -> None:
    _plant(ring, "helpers.py", """
        def normalise(text: str) -> str:
            return text.strip().lower()
    """)
    done = _run(ring)
    assert done.returncode == 1
    assert "service normalise" in done.stdout


def test_a_documented_service_is_a_role_not_an_error(ring: Path) -> None:
    _plant(ring, "helpers.py", '''
        def normalise(text: str) -> str:
            """Case-fold and trim a surface form before comparison."""
            return text.strip().lower()
    ''')
    done = _run(ring)
    assert done.returncode == 1  # glossary went stale — the service must appear in it
    assert "stale" in done.stdout


def test_dynamic_composition_in_the_entrypoints_ring_is_allowed(ring: Path) -> None:
    """The AST check draws the SAME boundary as the importlib contract: the
    composition root already knows every concretion, so dynamic loading there
    is composition, not an escape."""
    target = ring / "src" / "pretraga" / "entrypoints" / "cli.py"
    target.write_text(target.read_text(encoding="utf-8")
                      + "\n\ndef plugin_loader() -> object:\n"
                      "    return __import__(\"json\")\n", encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 0, done.stdout


def _run_hook(ring: Path, file_path: str) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, "tools/truth.py", "--hook"], cwd=ring, capture_output=True,
        text=True, input=f'{{"tool_input": {{"file_path": "{file_path}"}}}}',
        env=_ENV(ring), check=False)
    return done.returncode, done.stdout


def test_the_hook_is_advisory_and_green_on_a_clean_ring(ring: Path) -> None:
    code, out = _run_hook(ring, str(ring / "src" / "pretraga" / "domain" / "facts.py"))
    assert code == 0
    assert '"decision"' not in out
    assert "governed path" in out


def test_the_hook_blocks_on_a_red_ring_but_still_exits_zero(ring: Path) -> None:
    _plant(ring, "x9.py", """
        class Stray:
            '''No kind.'''
    """)
    code, out = _run_hook(ring, str(ring / "src" / "pretraga" / "domain" / "x9.py"))
    assert code == 0, "the hook is advisory: it must never fail the harness itself"
    assert '"decision": "block"' in out


def test_the_hook_ignores_ungoverned_paths(ring: Path) -> None:
    code, out = _run_hook(ring, "/somewhere/else/entirely.py")
    assert code == 0
    assert out.strip() == ""


def test_the_glossary_carries_the_terminological_conventions() -> None:
    """The old map's conventions block found its v5 home: the domain package
    docstring, rendered into the glossary preamble. Emptying either goes red."""
    text = truth.render_glossary(truth.survey())
    assert "reserved for live speech" in text
    assert "state predicate" in text


def test_the_glossary_render_is_deterministic() -> None:
    assert truth.render_glossary(truth.survey()) == truth.render_glossary(truth.survey())


def test_open_questions_are_counted_not_blocking() -> None:
    s = truth.survey()
    opens = [o for c in s.concepts.values() for o in getattr(c, "open_questions", ())]
    assert opens, "the fixture ring has open questions; if it stops having them, this test lies"
    assert not truth.classification_errors(s)
