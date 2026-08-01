"""Persisted-schema contract: the shape of every domain concept, locked.

The single mechanism aimed at the failure that killed the previous project —
a data schema that changed without anyone noticing.

Taxonomy, stated against the industry frame rather than invented:
  * In Confluent schema-registry terms this check is BACKWARD compatibility
    against the latest lock (the reader always ships with the code, so FORWARD
    and TRANSITIVE modes buy nothing here) — PLUS a stricter rule the registry
    does not have: field removal is breaking too, because corpus records are
    long-lived assets, and a field nothing reads any more is silent information
    loss even when the record still parses.
  * buf's split of breakage surfaces: code-surface breakage (a renamed member,
    a moved class) is mypy's and the type system's job; THIS lock guards the
    data surface only. That is why moving a concept between modules is not a
    change (measured), while renaming a field is (measured).
  * Rejected alternative: locking `model_json_schema()` output instead of
    introspecting fields. Measured: JSON Schema collapses NewType to its base
    ("ContentHash" becomes "string"), so the one mutation this lock exists to
    catch — a hash key quietly widening to a bare string — becomes invisible.

The lock is DERIVED and machine-written. The only human decision it asks for
is the version bump, which is the one thing a machine must not choose.
Until a storage engine exists the lock cannot know WHICH shapes are persisted,
so it locks all of them and says so honestly (an oasdiff-style rule: severity
stays error, the message states the condition). When the store adapter lands,
its registered tables become the source of that knowledge and the message can
name the affected tables exactly.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import subprocess
import sys
import typing
from pathlib import Path
from typing import Annotated, Any

from pydantic.fields import FieldInfo

ROOT = Path(__file__).resolve().parents[1]
# Beside uv.lock: a lock is a machine-written, diff-reviewed baseline, not
# documentation — the lockfile convention puts it at the repository root.
LOCK = ROOT / "schema.lock.json"

for _extra in (ROOT / "src", ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

FIX_LINE = ("  fix: bump the schema version; wherever this shape is persisted, the data "
            "migration ships in the SAME commit; then rerun --write")


def _major(version: str) -> int | None:
    """The leading integer of a dotted version string, or None if it is not
    shaped like one. A breaking change demands a MAJOR bump specifically —
    any differing string used to satisfy the version-changed check, which
    accepted a cosmetic or even backward-sorting change as evidence a human
    decided this was breaking."""
    head = version.split(".", 1)[0]
    return int(head) if head.lstrip("-").isdigit() else None


def _annotated_nodes(annotation: Any) -> list[Any]:
    """Every `Annotated[X, *metadata]` reachable inside a parametrised
    annotation. The only place one can appear: pydantic strips a field's OWN
    outermost Annotated into `finfo.metadata` before `_type_name` ever sees
    it, so a nested one — an element type inside `tuple[...]`, which `Field()`
    cannot reach (`AcquisitionAct.brought`) — is the sole survivor, found by
    walking `typing.get_args()`."""
    found: list[Any] = []
    if typing.get_origin(annotation) is Annotated:
        found.append(annotation)
    for arg in typing.get_args(annotation):
        found.extend(_annotated_nodes(arg))
    return found


def _type_name(annotation: Any) -> str:
    """A stable, address-free, PARAMETER-PRESERVING name.

    Measured failure this guards against: `tuple[X, ...].__name__` is just
    "tuple", so naming generics by __name__ made a change of the parameter
    invisible — the exact class of silent corruption the lock exists to catch.
    Parametrised types therefore go through str(), which qualifies every
    argument and embeds no memory address — except a nested `Annotated`,
    whose metadata str() reprs whole, every None-valued field included, and
    is spliced out for the already-adversarially-tested `_constraint_repr()`
    instead, same as a top-level Field() constraint.
    """
    if annotation is None:
        return "None"
    if typing.get_origin(annotation) is not None:
        raw = str(annotation).replace("typing.", "")
        for node in _annotated_nodes(annotation):
            base, *metadata = typing.get_args(node)
            clean = (f"Annotated[{_type_name(base)}, "
                     f"{', '.join(_constraint_repr(m) for m in metadata)}]")
            raw = raw.replace(str(node).replace("typing.", ""), clean)
        return raw
    mod = getattr(annotation, "__module__", "")
    name = getattr(annotation, "__name__", None)
    if name and mod:
        return f"{mod}.{name}"
    if name:
        return str(name)
    return str(annotation).replace("typing.", "")


def _factory_name(factory: Any) -> str:
    """A factory is named by module AND qualname — never by repr, which can
    embed a memory address and would make the lock differ between runs.

    Measured: the bare qualname is not identity. Two modules each with a helper
    called `_default` both record `_default`, so swapping one for the other
    changed the default of every record that omitted the field under a green
    gate. Qualifying by module closes that; two lambdas in ONE class body still
    collide, which is why a lambda factory is refused outright below."""
    qual, mod = getattr(factory, "__qualname__", None), getattr(factory, "__module__", None)
    return f"{mod}.{qual}" if qual and mod else str(factory)


def _constraint_repr(m: Any) -> str:
    """Non-None dataclass fields only: a NEW field a future annotated-types
    bump adds, defaulting to None, must not move this string — measured on
    StringConstraints.ascii_only (added between 2.12 and 2.13, a bump already
    in this repo's history). A callable field (AfterValidator.func and
    friends) is named like a default factory — module and qualname, never
    repr, which embeds a memory address; the lambda refusal is in derive(),
    where the field name is available for the error."""
    if not dataclasses.is_dataclass(m) or isinstance(m, type):
        return repr(m)
    kept = [(f.name, getattr(m, f.name)) for f in dataclasses.fields(m)
            if getattr(m, f.name) is not None]
    parts = (f"{k}={_factory_name(v)}" if callable(v) else f"{k}={v!r}" for k, v in kept)
    return f"{type(m).__name__}({', '.join(parts)})"


def _field_contract(finfo: FieldInfo) -> dict[str, Any]:
    factory = finfo.default_factory
    return {
        "type": _type_name(finfo.annotation),
        "required": finfo.is_required(),
        # A default is part of the persisted contract: changing it silently
        # rewrites the meaning of every record that omitted the field.
        "default": repr(finfo.default) if not finfo.is_required() and factory is None else None,
        "factory": _factory_name(factory) if factory is not None else None,
        # Constraints travel with the field: tightening one rejects records
        # that used to load.
        "constraints": sorted(_constraint_repr(m) for m in (finfo.metadata or [])),
        # THREE alias channels, not one. `alias` alone left two of them
        # unrecorded, and each is a persisted-data change: renaming the
        # validation alias makes yesterday's record fail to load (measured:
        # REJECTED, "missing"), renaming the serialisation alias writes every
        # new record under a different key.
        "alias": finfo.alias,
        "validation_alias": None if finfo.validation_alias is None else str(finfo.validation_alias),
        "serialization_alias": finfo.serialization_alias,
        # The tag rule of a union: dropping it does not change the members, so
        # the type name stays identical while a record that used to be rejected
        # starts loading as whichever shape happens to match first.
        "discriminator": finfo.discriminator,
    }


def _serializers(model: Any) -> list[str]:
    """Custom validators and serialisers, by what they act on. Validators
    decide whether a record LOADS at all, so an added one is exactly the class
    of change this lock exists to catch, same as a serialiser rewriting what
    is written. The category set is PROJECTED from the pydantic decorator
    registry rather than enumerated: the same trick the guarded-tool list
    uses, so an eighth category pydantic adds later does not need a matching
    edit here. computed_fields is excluded — it is captured separately via
    model_computed_fields, which carries the field itself rather than a bare
    method name."""
    dec = model.__pydantic_decorators__
    out = []
    for cat in dataclasses.fields(dec):
        if cat.name == "computed_fields":
            continue
        for d in getattr(dec, cat.name).values():
            fields = getattr(d.info, "fields", None)
            tag = f"{cat.name}({','.join(sorted(fields))})" if fields else cat.name
            out.append(f"{tag}:{d.info.mode}")
    return sorted(out)


def derive(package: str = "pretraga.domain") -> dict[str, Any]:
    import truth

    kinds = importlib.import_module(f"{package}.kinds")
    s = truth.survey(package)
    shape: dict[str, Any] = {}
    for name in sorted(s.concepts):
        model = s.concepts[name]
        for fname, fi in model.model_fields.items():
            if fi.default_factory is not None and "<lambda>" in _factory_name(fi.default_factory):
                raise ValueError(
                    f"SCHEMA: {name}.{fname} defaults to a lambda. A factory is identified by "
                    "module and qualname, and every lambda in one scope shares a qualname — so "
                    "swapping one for another rewrites the default of every record that omitted "
                    "the field with nothing to show for it. Give the factory a name.")
            for m in fi.metadata or ():
                for cf in dataclasses.fields(m) if dataclasses.is_dataclass(m) else ():
                    v = getattr(m, cf.name)
                    if callable(v) and "<lambda>" in _factory_name(v):
                        raise ValueError(
                            f"SCHEMA: {name}.{fname} validator uses a lambda ({type(m).__name__}."
                            f"{cf.name}). Every lambda in one scope shares a qualname — give it "
                            "a name.")
        shape[name] = {
            # The kind is decided by the base class, never guessed from a
            # field name: a Value that happens to carry a field called `uuid`
            # is still a Value.
            "kind": "entity" if issubclass(model, kinds.Entity) else "value",
            "fields": {fname: _field_contract(fi) for fname, fi in model.model_fields.items()},
            # A computed field is absent from model_fields and present in every
            # persisted record. Measured: adding one, plus a field serialiser,
            # moved the wire format from {"amount_cents":350} to
            # {"amount_cents":"350c","amount":3.5} while this entry stayed
            # byte-identical.
            "computed": {n: {"type": _type_name(ci.return_type), "alias": ci.alias}
                         for n, ci in model.model_computed_fields.items()},
            "serializers": _serializers(model),
            # The whole config, not just `frozen`: switching extra from allow
            # to forbid rejects records that used to load, and locking one key
            # while ignoring the rest is a guarantee with a hole in it.
            "config": {k: repr(v) for k, v in sorted(model.model_config.items())},
        }
    # Vocabularies are persisted VALUES, not just code. Dropping a member makes
    # every stored record carrying it unreadable — the quietest corruption of
    # all, and invisible if only the enum's type name were locked.
    for name in sorted(s.vocabularies):
        shape[name] = {"kind": "vocabulary",
                       "members": sorted(str(m.value) for m in s.vocabularies[name])}
    for name in sorted(s.sums):
        shape[name] = {"kind": "sum",
                       "members": sorted(_type_name(m) for m in truth._union_args(s.sums[name]))}
    return shape


def classify(old: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(breaking, additive), in the BACKWARD-plus-no-silent-loss sense above."""
    breaking: list[str] = []
    additive: list[str] = []
    for name in sorted(set(old) - set(new)):
        breaking.append(f"{name}: removed — persisted records become unreadable")
    for name in sorted(set(new) - set(old)):
        additive.append(f"{name}: new {new[name].get('kind', 'concept')}")
    for name in sorted(set(old) & set(new)):
        o, n = old[name], new[name]
        if o.get("kind") != n.get("kind"):
            breaking.append(f"{name}: kind {o.get('kind')} -> {n.get('kind')}")
            continue
        if o.get("kind") == "vocabulary":
            for m in sorted(set(o["members"]) - set(n["members"])):
                breaking.append(f"{name}.{m}: vocabulary member removed — stored records "
                                "carrying it stop validating")
            for m in sorted(set(n["members"]) - set(o["members"])):
                additive.append(f"{name}.{m}: new vocabulary member")
            continue
        if o.get("kind") == "sum":
            for m in sorted(set(o["members"]) - set(n["members"])):
                breaking.append(f"{name}: shape {m} removed from the sum")
            for m in sorted(set(n["members"]) - set(o["members"])):
                additive.append(f"{name}: new shape {m}")
            continue
        of, nf = o["fields"], n["fields"]
        for f in sorted(set(of) - set(nf)):
            breaking.append(f"{name}.{f}: field removed")
        for f in sorted(set(nf) - set(of)):
            (breaking if nf[f]["required"] else additive).append(
                f"{name}.{f}: new {'REQUIRED' if nf[f]['required'] else 'optional'} field")
        for f in sorted(set(of) & set(nf)):
            a, b = of[f], nf[f]
            if a["type"] != b["type"]:
                breaking.append(f"{name}.{f}: type {a['type']} -> {b['type']}")
            elif not a["required"] and b["required"]:
                breaking.append(f"{name}.{f}: became required")
            elif a.get("default") != b.get("default") or a.get("factory") != b.get("factory"):
                breaking.append(f"{name}.{f}: default {a.get('default') or a.get('factory')} -> "
                                f"{b.get('default') or b.get('factory')} — records that omitted "
                                "this field change meaning")
            elif set(b.get("constraints") or []) - set(a.get("constraints") or []):
                breaking.append(f"{name}.{f}: constraint tightened — records that used to load "
                                "may now be rejected")
            else:
                for key, why in (
                        ("alias", "alias"),
                        ("validation_alias",
                         ("validation alias — records stored under the old name stop loading")),
                        ("serialization_alias",
                         ("serialisation alias — new records are written under a different name")),
                        ("discriminator",
                         ("union discriminator — the tag rule deciding which shape a record is"))):
                    if a.get(key) != b.get(key):
                        breaking.append(f"{name}.{f}: {why} {a.get(key)} -> {b.get(key)}")
        ocf, ncf = o.get("computed", {}), n.get("computed", {})
        for f in sorted(set(ocf) - set(ncf)):
            breaking.append(f"{name}.{f}: computed field removed — it is written into every record")
        for f in sorted(set(ncf) - set(ocf)):
            additive.append(f"{name}.{f}: new computed field")
        for f in sorted(set(ocf) & set(ncf)):
            if ocf[f] != ncf[f]:
                breaking.append(f"{name}.{f}: computed field {ocf[f]} -> {ncf[f]}")
        if o.get("serializers", []) != n.get("serializers", []):
            breaking.append(f"{name}: validators/serialisers {o.get('serializers', [])} -> "
                            f"{n.get('serializers', [])} — whether a record loads, or what is "
                            "written, changes without any field changing")
        oc, nc = o.get("config", {}), n.get("config", {})
        for k in sorted(set(oc) | set(nc)):
            if oc.get(k) != nc.get(k):
                breaking.append(f"{name}: model_config[{k}] {oc.get(k)} -> {nc.get(k)}")
    return breaking, additive


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def _lock_at(lock_path: Path, ref: str) -> dict[str, Any] | None:
    """The lock as git has it at `ref`. The version decision is enforced
    against HISTORY, not against a file on disk: measured, `rm
    schema.lock.json && --write --version <the version already stored>`
    absorbed a breaking change, left the version line of the diff untouched,
    and the gate said OK."""
    raw = _git(lock_path.parent, "show", f"{ref}:./{lock_path.name}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _base_lock(lock_path: Path) -> tuple[str, dict[str, Any]] | None:
    """The lock as of the point this branch left the trunk."""
    for trunk in ("origin/main", "main"):
        merge = _git(lock_path.parent, "merge-base", "HEAD", trunk)
        if merge is None:
            continue
        stored = _lock_at(lock_path, merge.strip())
        if stored is not None:
            return trunk, stored
    return None


def check(package: str = "pretraga.domain", lock_path: Path = LOCK) -> int:
    fresh = derive(package)
    if not lock_path.exists():
        print(f"SCHEMA: {lock_path.name} is missing — run --write")
        return 1
    locked = json.loads(lock_path.read_text(encoding="utf-8"))
    base = _base_lock(lock_path)
    if base is None:
        print("SCHEMA: NOTHING COMPARED against history — no base lock reachable in git, so the "
              "version rule checked nothing this run")
    else:
        trunk, stored = base
        drift, _ = classify(stored["shape"], locked["shape"])
        old_major, new_major = _major(stored["version"]), _major(locked["version"])
        proper_bump = old_major is not None and new_major is not None and new_major > old_major
        if drift and not proper_bump:
            print(f"SCHEMA: {len(drift)} breaking change(s) in the lock against {trunk} "
                  f"(v{stored['version']}) without a MAJOR version bump (now v{locked['version']})")
            for d in drift:
                print(f"  - {d}")
            print("  fix: the bump is the human decision; a rewritten lock file is not evidence "
                  "that it was taken, and only a major bump states it")
            return 1
    breaking, additive = classify(locked["shape"], fresh)
    if breaking:
        print(f"SCHEMA: {len(breaking)} BREAKING change(s) against v{locked['version']}")
        for b in breaking:
            print(f"  - {b}")
        print(FIX_LINE)
        return 1
    if additive:
        print(f"SCHEMA: {len(additive)} additive change(s) against v{locked['version']} "
              "— rerun --write to record")
        for a in additive:
            print(f"  i {a}")
        return 1
    print(f"SCHEMA: OK (v{locked['version']}, {len(fresh)} locked shapes)")
    return 0


def write(package: str, version: str | None, lock_path: Path) -> int:
    """Rewrite the lock. The version bump is the ONE human decision here, so
    the machine refuses to absorb a breaking change under the stored version:
    without a NEW --version, breaking changes do not get recorded."""
    fresh = derive(package)
    stored = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else None
    if stored is None:
        stored = _lock_at(lock_path, "HEAD")
        if stored is not None:
            print("SCHEMA: the lock is absent from the tree but git still has it — deleting the "
                  "file is not a way past the version decision")
    if stored is not None:
        breaking, _ = classify(stored["shape"], fresh)
        new_version = version or stored["version"]
        old_major, new_major = _major(stored["version"]), _major(new_version)
        proper_bump = old_major is not None and new_major is not None and new_major > old_major
        if breaking and not proper_bump:
            print(f"SCHEMA: refusing to overwrite v{stored['version']}: "
                  f"{len(breaking)} breaking change(s) need a MAJOR --version bump, not merely a "
                  "differing string — the bump is the human decision, the machine will not guess "
                  "which digit means it was taken")
            return 1
    else:
        new_version = version or "1.0.0"
    lock_path.write_text(
        json.dumps({"version": new_version, "shape": fresh}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"written: {lock_path} (v{new_version})")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default="pretraga.domain")
    ap.add_argument("--lock", type=Path, default=LOCK)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--version", default=None)
    ns = ap.parse_args(argv)
    return write(ns.package, ns.version, ns.lock) if ns.write else check(ns.package, ns.lock)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
