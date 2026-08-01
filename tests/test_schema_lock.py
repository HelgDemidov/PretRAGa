"""The persisted-schema contract: one negative test per class of silent
corruption, plus the controls that must stay green."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import schema_lock


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
        [sys.executable, "tools/schema_lock.py"], cwd=ring, capture_output=True, text=True,
        env=_ENV(ring), check=False)


def _edit(ring: Path, module: str, old: str, new: str) -> None:
    target = ring / "src" / "pretraga" / "domain" / module
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor {old!r} matches {text.count(old)} times in {module}"
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def _next_major(ring: Path) -> str:
    stored = json.loads((ring / "schema.lock.json").read_text())["version"]
    return f"{int(stored.split('.')[0]) + 1}.0.0"


def test_the_untouched_ring_is_green(ring: Path) -> None:
    done = _run(ring)
    assert done.returncode == 0, done.stdout + done.stderr


BREAKING = [
    ("field removed", "facts.py", "    extractor_version: int\n", "", "field removed"),
    ("field renamed", "facts.py", "    normalized: str", "    text: str", "field removed"),
    ("type narrowed away", "provenance.py",
     '    content_hash: ContentHash = Field(pattern=r"^[0-9a-f]{64}$")\n    media_type: str',
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
     ('    model_config = {"frozen": True, "extra": "forbid"}\n'
      '    open_questions = (Open(question="small predicate vocabulary",'), "model_config"),
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


_MOVABLE = ('"""Probe module."""\nfrom __future__ import annotations\n\n'
           "from pretraga.domain.kinds import Value\n\n\n"
           'class Movable(Value):\n    """A synthetic concept with no production coupling."""\n\n'
           "    payload: str\n")


def test_moving_a_concept_between_modules_is_not_a_change(ring: Path) -> None:
    """The lock is about shape, not location. A refactor that moves a class must
    not read as data corruption, or the check trains people to ignore it.

    A synthetic class with no production coupling, not `Translation`: the
    earlier version spliced a real concept's fields out of `facts.py`, so any
    unrelated future change to Translation's shape broke this test for a
    reason that has nothing to do with what it verifies (measured: adding
    `Field(pattern=...)` to `of_text` orphaned the moved snippet's missing
    `pydantic.Field` import)."""
    (ring / "src" / "pretraga" / "domain" / "synthetic_a.py").write_text(_MOVABLE, encoding="utf-8")
    assert _run_write(ring).returncode == 0, "record the synthetic concept before moving it"

    (ring / "src" / "pretraga" / "domain" / "synthetic_a.py").unlink()
    (ring / "src" / "pretraga" / "domain" / "synthetic_b.py").write_text(_MOVABLE, encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 0, done.stdout


def test_the_lock_is_byte_identical_across_runs(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    schema_lock.write("pretraga.domain", "1.0.0", a)
    schema_lock.write("pretraga.domain", "1.0.0", b)
    assert a.read_bytes() == b.read_bytes()


def test_a_missing_lock_blocks(ring: Path) -> None:
    (ring / "schema.lock.json").unlink()
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
        env=_ENV(ring), check=False)


def test_a_breaking_write_without_a_new_version_is_refused(ring: Path) -> None:
    """The version bump is the one human decision; --write must not absorb a
    breaking change under the stored version."""
    _edit(ring, "facts.py", "    extractor_version: int\n", "")
    lock = ring / "schema.lock.json"
    before = lock.read_bytes()
    done = _run_write(ring)
    assert done.returncode == 1, done.stdout
    assert "MAJOR --version" in done.stdout
    assert lock.read_bytes() == before, "the lock must stay untouched on refusal"


def test_a_breaking_write_with_a_new_version_succeeds(ring: Path) -> None:
    bumped = _next_major(ring)
    _edit(ring, "facts.py", "    extractor_version: int\n", "")
    done = _run_write(ring, "--version", bumped)
    assert done.returncode == 0, done.stdout
    lock = json.loads((ring / "schema.lock.json").read_text())
    assert lock["version"] == bumped
    assert _run(ring).returncode == 0


def test_write_then_check_round_trips_in_isolation(tmp_path: Path) -> None:
    """The entry points, in process, against a throwaway lock: production
    defaults are never touched because the path is passed explicitly."""
    lock = tmp_path / "lock.json"
    assert schema_lock.check(lock_path=lock) == 1          # missing
    assert schema_lock.write("pretraga.domain", "1.0.0", lock) == 0
    assert schema_lock.check(lock_path=lock) == 0
    assert schema_lock.write("pretraga.domain", None, lock) == 0   # additive keeps the version
    assert json.loads(lock.read_text())["version"] == "1.0.0"


def test_history_lookups_are_absent_rather_than_wrong_outside_git(tmp_path: Path) -> None:
    """Outside a repository the version rule has nothing to compare. It must
    say so rather than invent an answer."""
    assert schema_lock._lock_at(tmp_path / "lock.json", "HEAD") is None
    assert schema_lock._base_lock(tmp_path / "lock.json") is None


def test_serialisers_are_named_by_the_fields_they_rewrite() -> None:
    from pydantic import BaseModel, field_serializer, model_serializer

    class Plain(BaseModel):
        x: int

    class Rewritten(BaseModel):
        x: int

        @field_serializer("x")
        def _x(self, v: int) -> str:
            return f"{v}!"

        @model_serializer(mode="wrap")
        def _all(self, handler: object) -> dict[str, object]:
            return {"wrapped": self.x}

    assert schema_lock._serializers(Plain) == []
    got = schema_lock._serializers(Rewritten)
    assert any("field_serializers(x)" in g for g in got), got
    assert any(g.startswith("model_serializers:") for g in got), got


def test_dropping_a_union_discriminator_blocks(ring: Path) -> None:
    """The members do not change, so the type name is identical — and a record
    that used to be rejected starts loading as whichever shape matches first."""
    tagged = (
        '"""A tagged union in the domain."""\n'
        "from __future__ import annotations\n\n"
        "from typing import Literal\n\n"
        "from pydantic import Field\n\n"
        "from pretraga.domain.kinds import Value\n\n\n"
        'class Cat(Value):\n    """A cat."""\n\n    kind: Literal["cat"] = "cat"\n\n\n'
        'class Dog(Value):\n    """A dog."""\n\n    kind: Literal["dog"] = "dog"\n\n\n'
        'class Pen(Value):\n    """Holds exactly one animal."""\n\n'
        '    pet: Cat | Dog = Field(discriminator="kind")\n')
    target = ring / "src" / "pretraga" / "domain" / "pen.py"
    target.write_text(tagged, encoding="utf-8")
    assert _run_write(ring).returncode == 0, "a new concept is additive"
    target.write_text(tagged.replace('= Field(discriminator="kind")', ""), encoding="utf-8")
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "discriminator" in done.stdout, done.stdout


def _git_ring(ring: Path) -> None:
    """A ring with history, so the version rule has something to compare to."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(ring), "GIT_CONFIG_GLOBAL": "/dev/null"}
    for args in (["init", "-q", "-b", "main"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"]):
        subprocess.run(["git", *args], cwd=ring, env=env, check=True, capture_output=True)


def test_deleting_the_lock_is_not_a_way_past_the_version_decision(ring: Path) -> None:
    """Measured: `rm schema.lock.json && --write --version <the version already
    stored>` absorbed a breaking change, left the version line of the diff
    untouched, and the gate reported OK."""
    _git_ring(ring)
    stored = json.loads((ring / "schema.lock.json").read_text())["version"]
    _edit(ring, "facts.py", "    extractor_version: int\n", "")
    (ring / "schema.lock.json").unlink()
    done = _run_write(ring, "--version", stored)
    assert done.returncode == 1, done.stdout
    assert "MAJOR --version" in done.stdout, done.stdout


def test_a_lock_rewritten_by_hand_against_history_blocks(ring: Path) -> None:
    """The lock file is machine-written, so a rewritten file is indistinguishable
    from an honest one. History is not: a breaking difference from the trunk
    with the version unchanged is the bump that was never taken."""
    _git_ring(ring)
    lock = ring / "schema.lock.json"
    d = json.loads(lock.read_text())
    d["shape"]["Claim"]["fields"].pop("extractor_version")
    lock.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")
    _edit(ring, "facts.py", "    extractor_version: int\n", "")
    done = _run(ring)
    assert done.returncode == 1, done.stdout
    assert "against main" in done.stdout or "against origin/main" in done.stdout, done.stdout


def test_a_ring_without_history_says_so_instead_of_passing_quietly(ring: Path) -> None:
    """A step whose prerequisite is structurally absent must not read as
    success — it says what it did not do."""
    done = _run(ring)
    assert done.returncode == 0, done.stdout
    assert "NOTHING COMPARED" in done.stdout, done.stdout


def test_an_additive_write_keeps_the_stored_version(ring: Path) -> None:
    before = json.loads((ring / "schema.lock.json").read_text())["version"]
    _edit(ring, "document.py", "    lifecycle: Lifecycle",
          "    lifecycle: Lifecycle\n    note: str | None = None")
    done = _run_write(ring)
    assert done.returncode == 0, done.stdout
    lock = json.loads((ring / "schema.lock.json").read_text())
    assert lock["version"] == before


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
    assert schema_lock._field_contract(WithFactories.model_fields["xs"])["factory"] == "builtins.list"


def test_a_factory_is_identified_by_module_and_not_by_bare_qualname() -> None:
    """Measured: two modules each with a helper called `_default` both recorded
    `_default`, so swapping one for the other changed the default of every
    record that omitted the field while the gate stayed green."""
    import types

    from pydantic import BaseModel, Field

    a, b = types.ModuleType("stage_a"), types.ModuleType("stage_b")
    src = "def _default() -> tuple[str, ...]:\n    return ()\n"
    exec(compile(src, "a", "exec"), a.__dict__)  # noqa: S102 — building the collision on purpose
    exec(compile(src, "b", "exec"), b.__dict__)  # noqa: S102
    a._default.__module__, b._default.__module__ = "stage_a", "stage_b"

    class A(BaseModel):
        xs: tuple[str, ...] = Field(default_factory=a._default)

    class B(BaseModel):
        xs: tuple[str, ...] = Field(default_factory=b._default)

    ca = schema_lock._field_contract(A.model_fields["xs"])["factory"]
    cb = schema_lock._field_contract(B.model_fields["xs"])["factory"]
    assert ca != cb, (ca, cb)


def test_a_lambda_default_factory_is_refused(ring: Path) -> None:
    """Qualifying by module is not enough for a lambda: every lambda in one
    scope shares a qualname, so identity is unavailable. Refuse it instead."""
    _edit(ring, "document.py", "from __future__ import annotations",
          "from __future__ import annotations\n\nfrom pydantic import Field")
    _edit(ring, "document.py", "    versions: tuple[ContentVersion, ...] = ()",
          "    versions: tuple[ContentVersion, ...] = Field(default_factory=lambda: ())")
    done = _run(ring)
    assert done.returncode == 1
    # Measured: bare "lambda" passed even with this refusal disabled, because
    # the factory's OWN name embeds "<lambda>" and shows up anyway once the
    # change is merely reported as an ordinary breaking default change — the
    # refusal's own wording is what must be present.
    assert "defaults to a lambda" in done.stdout + done.stderr


ANCHOR = "    extractor_version: int"
COMPUTED = ('\n\n    @computed_field  # type: ignore[prop-decorator]\n    @property\n'
            '    def shout(self) -> str:\n        """Written into every record."""\n'
            "        return self.normalized.upper()\n")
SERIALISER = ('\n\n    @field_serializer("normalized")\n'
              "    def _ser(self, v: str) -> str:\n        return v.upper()\n")

PERSISTED_BUT_NOT_A_FIELD = [
    ("computed field removed", COMPUTED, "computed field removed"),
    ("field serialiser removed", SERIALISER, "serialisers"),
]


@pytest.mark.parametrize(("name", "member", "expected"), PERSISTED_BUT_NOT_A_FIELD,
                         ids=[c[0] for c in PERSISTED_BUT_NOT_A_FIELD])
def test_a_wire_format_change_that_touches_no_field_blocks(ring: Path, name: str, member: str,
                                                           expected: str) -> None:
    """Measured: a computed field plus a serialiser moved the persisted form
    from {"amount_cents":350} to {"amount_cents":"350c","amount":3.5} with the
    locked entry byte-identical. Recorded first, then removed: the removal is
    the breaking direction, and neither touches any field."""
    _edit(ring, "facts.py", "from __future__ import annotations",
          "from __future__ import annotations\n\n"
          "from pydantic import computed_field, field_serializer")
    _edit(ring, "facts.py", ANCHOR, ANCHOR + member)
    assert _run_write(ring, "--version", _next_major(ring)).returncode == 0, (
        "recording the member is itself a wire-format change: allowed WITH a bump")
    _edit(ring, "facts.py", member, "")
    done = _run(ring)
    assert done.returncode == 1, f"{name} was accepted:\n{done.stdout}"
    assert expected in done.stdout, done.stdout


ALIAS_CASES = [
    ("validation alias renamed", 'validation_alias="incoming"', 'validation_alias="renamed"',
     "validation alias"),
    ("serialisation alias renamed", 'serialization_alias="out_a"', 'serialization_alias="out_b"',
     "serialisation alias"),
]


@pytest.mark.parametrize(("name", "before", "after", "expected"), ALIAS_CASES,
                         ids=[c[0] for c in ALIAS_CASES])
def test_an_alias_channel_change_blocks(ring: Path, name: str, before: str, after: str,
                                        expected: str) -> None:
    """`alias` alone left two of the three channels unrecorded, and each one is
    a persisted-data change: the stored key stops loading, or new records are
    written under a different key."""
    _edit(ring, "facts.py", "from __future__ import annotations",
          "from __future__ import annotations\n\nfrom pydantic import Field")
    _edit(ring, "facts.py", "    normalized: str", f"    normalized: str = Field({before})")
    assert _run_write(ring, "--version", _next_major(ring)).returncode == 0
    _edit(ring, "facts.py", before, after)
    done = _run(ring)
    assert done.returncode == 1, f"{name} was accepted:\n{done.stdout}"
    assert expected in done.stdout, done.stdout


def test_the_lock_kind_comes_from_the_base_class_not_a_field_name() -> None:
    """A Value carrying a field named uuid must still be locked as a value."""
    shape = schema_lock.derive()
    assert shape["Document"]["kind"] == "entity"
    assert all(shape[n]["kind"] == "value"
               for n in ("Claim", "RawPayload", "CanonicalText", "SearchHit"))
