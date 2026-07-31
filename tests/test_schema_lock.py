"""The persisted-schema contract: one negative test per class of silent
corruption, plus the controls that must stay green."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import schema_lock


def _run(ring: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/schema_lock.py"], cwd=ring, capture_output=True, text=True,
        env={"PYTHONPATH": str(ring / "src"), "PATH": "/usr/bin:/bin"}, check=False)


def _edit(ring: Path, module: str, old: str, new: str) -> None:
    target = ring / "src" / "pretraga" / "domain" / module
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor {old!r} matches {text.count(old)} times in {module}"
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_the_untouched_ring_is_green(ring: Path) -> None:
    done = _run(ring)
    assert done.returncode == 0, done.stdout + done.stderr


BREAKING = [
    ("field removed", "facts.py", "    extractor_version: int\n", "", "field removed"),
    ("field renamed", "facts.py", "    normalized: str", "    text: str", "field removed"),
    ("type narrowed away", "provenance.py", "    content_hash: ContentHash\n    media_type: str",
     "    content_hash: str\n    media_type: str", "type "),
    ("new required field", "document.py", "    lifecycle: Lifecycle",
     "    lifecycle: Lifecycle\n    jurisdiction: str", "REQUIRED"),
    ("default changed", "document.py", "versions: tuple[ContentVersion, ...] = ()",
     "versions: tuple[ContentVersion, ...] = (None,)  # type: ignore[arg-type]", "default"),
    ("constraint tightened", "provenance.py", "start: int = Field(ge=0)",
     "start: int = Field(ge=1)", "constraint tightened"),
    ("vocabulary member removed", "document.py", '    RETIRED = "retired"\n', "",
     "vocabulary member removed"),
    ("shape removed from a sum", "synthesis.py",
     "QueryOutcome = Answer | Refusal | StaleWarning",
     "QueryOutcome = Answer | Refusal", "removed from the sum"),
    # Unsetting `frozen` is deliberately NOT in this list: the kind rejects it
    # at class creation, so the lock never sees it. Tested in test_kinds.py.
    ("model_config narrowed (extra: forbid)", "facts.py",
     '    open_questions = (Open(question="small predicate vocabulary",',
     '    model_config = {"frozen": True, "extra": "forbid"}\n'
     '    open_questions = (Open(question="small predicate vocabulary",', "model_config"),
]


@pytest.mark.parametrize(("name", "module", "old", "new", "expected"), BREAKING,
                         ids=[b[0] for b in BREAKING])
def test_a_breaking_change_blocks(ring: Path, name: str, module: str, old: str,
                                  new: str, expected: str) -> None:
    _edit(ring, module, old, new)
    done = _run(ring)
    assert done.returncode == 1, f"{name} was accepted:\n{done.stdout}"
    assert "BREAKING" in done.stdout or expected in done.stdout, done.stdout


def test_a_new_optional_field_is_additive_not_breaking(ring: Path) -> None:
    _edit(ring, "document.py", "    lifecycle: Lifecycle",
          "    lifecycle: Lifecycle\n    note: str | None = None")
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "additive" in done.stdout and "BREAKING" not in done.stdout, done.stdout


def test_a_new_vocabulary_member_is_additive(ring: Path) -> None:
    _edit(ring, "document.py", '    RETIRED = "retired"',
          '    RETIRED = "retired"\n    SUPERSEDED = "superseded"')
    done = _run(ring)
    assert "additive" in done.stdout and "BREAKING" not in done.stdout, done.stdout


def test_moving_a_concept_between_modules_is_not_a_change(ring: Path) -> None:
    """The lock is about shape, not location. A refactor that moves a class must
    not read as data corruption, or the check trains people to ignore it."""
    facts = ring / "src" / "pretraga" / "domain" / "facts.py"
    text = facts.read_text(encoding="utf-8")
    cut = text.index("class Translation(Value):")
    facts.write_text(text[:cut], encoding="utf-8")
    (ring / "src" / "pretraga" / "domain" / "translation.py").write_text(
        '"""Translations live here now."""\nfrom __future__ import annotations\n\n'
        "from pretraga.domain.kinds import ContentHash, Value\n\n\n" + text[cut:],
        encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 0, done.stdout


def test_the_lock_is_byte_identical_across_runs(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    schema_lock.write("pretraga.domain", "1.0.0", a)
    schema_lock.write("pretraga.domain", "1.0.0", b)
    assert a.read_bytes() == b.read_bytes()


def test_a_missing_lock_blocks(ring: Path) -> None:
    (ring / "docs" / "system_design" / "schema.lock.json").unlink()
    done = _run(ring)
    assert done.returncode == 1
    assert "missing" in done.stdout


def test_the_lock_records_no_memory_addresses(tmp_path: Path) -> None:
    """A repr with an address would make the lock differ between runs and turn
    every gate into a false alarm."""
    out = tmp_path / "lock.json"
    schema_lock.write("pretraga.domain", "1.0.0", out)
    assert "0x" not in out.read_text(encoding="utf-8")


def test_every_concept_is_locked() -> None:
    import truth

    shape = json.loads(json.dumps(schema_lock.derive()))
    assert set(truth.survey().concepts) <= set(shape)


def _run_write(ring: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/schema_lock.py", "--write", *args], cwd=ring,
        capture_output=True, text=True,
        env={"PYTHONPATH": str(ring / "src"), "PATH": "/usr/bin:/bin"}, check=False)


def test_a_breaking_write_without_a_new_version_is_refused(ring: Path) -> None:
    """The version bump is the one human decision; --write must not absorb a
    breaking change under the stored version."""
    _edit(ring, "facts.py", "    extractor_version: int\n", "")
    lock = ring / "docs" / "system_design" / "schema.lock.json"
    before = lock.read_bytes()
    done = _run_write(ring)
    assert done.returncode == 1, done.stdout
    assert "NEW --version" in done.stdout
    assert lock.read_bytes() == before, "the lock must stay untouched on refusal"


def test_a_breaking_write_with_a_new_version_succeeds(ring: Path) -> None:
    _edit(ring, "facts.py", "    extractor_version: int\n", "")
    done = _run_write(ring, "--version", "2.0.0")
    assert done.returncode == 0, done.stdout
    lock = json.loads((ring / "docs" / "system_design" / "schema.lock.json").read_text())
    assert lock["version"] == "2.0.0"
    assert _run(ring).returncode == 0


def test_an_additive_write_keeps_the_stored_version(ring: Path) -> None:
    _edit(ring, "document.py", "    lifecycle: Lifecycle",
          "    lifecycle: Lifecycle\n    note: str | None = None")
    done = _run_write(ring)
    assert done.returncode == 0, done.stdout
    lock = json.loads((ring / "docs" / "system_design" / "schema.lock.json").read_text())
    assert lock["version"] == "1.0.0"


def test_generic_parameters_are_recorded_in_full() -> None:
    """Measured regression this pins: naming generics by __name__ collapsed
    `tuple[OriginCoordinate, ...]` to `builtins.tuple`, so a change of the
    parameter was invisible to the lock."""
    shape = schema_lock.derive()
    recorded = shape["Document"]["fields"]["origin"]["type"]
    assert "OriginCoordinate" in recorded, recorded


def test_a_changed_generic_parameter_is_breaking(ring: Path) -> None:
    _edit(ring, "document.py", "origin: tuple[OriginCoordinate, ...]",
          "origin: tuple[str, ...]")
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "type" in done.stdout and "BREAKING" in done.stdout, done.stdout


def test_a_default_factory_is_named_without_a_memory_address() -> None:
    from pydantic import BaseModel, Field

    class WithFactories(BaseModel):
        xs: list[int] = Field(default_factory=list)
        ys: list[int] = Field(default_factory=lambda: [1])

    for fname in ("xs", "ys"):
        contract = schema_lock._field_contract(WithFactories.model_fields[fname])
        assert "0x" not in str(contract), contract
    assert schema_lock._field_contract(WithFactories.model_fields["xs"])["factory"] == "list"


def test_the_lock_kind_comes_from_the_base_class_not_a_field_name() -> None:
    """A Value carrying a field named uuid must still be locked as a value."""
    shape = schema_lock.derive()
    assert shape["Document"]["kind"] == "entity"
    assert all(shape[n]["kind"] == "value"
               for n in ("Claim", "RawPayload", "CanonicalText", "SearchHit"))
