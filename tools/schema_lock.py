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
import importlib
import json
import sys
import typing
from pathlib import Path
from typing import Any

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


def _type_name(annotation: Any) -> str:
    """A stable, address-free, PARAMETER-PRESERVING name.

    Measured failure this guards against: `tuple[X, ...].__name__` is just
    "tuple", so naming generics by __name__ made a change of the parameter
    invisible — the exact class of silent corruption the lock exists to catch.
    Parametrised types therefore go through str(), which qualifies every
    argument and embeds no memory address.
    """
    if annotation is None:
        return "None"
    if typing.get_origin(annotation) is not None:
        return str(annotation).replace("typing.", "")
    mod = getattr(annotation, "__module__", "")
    name = getattr(annotation, "__name__", None)
    if name and mod:
        return f"{mod}.{name}"
    if name:
        return str(name)
    return str(annotation).replace("typing.", "")


def _field_contract(finfo: FieldInfo) -> dict[str, Any]:
    factory = finfo.default_factory
    return {
        "type": _type_name(finfo.annotation),
        "required": finfo.is_required(),
        # A default is part of the persisted contract: changing it silently
        # rewrites the meaning of every record that omitted the field. A
        # factory is named by qualname — its repr can embed a memory address,
        # which would make the lock differ between runs.
        "default": repr(finfo.default) if not finfo.is_required() and factory is None else None,
        "factory": getattr(factory, "__qualname__", str(factory)) if factory is not None else None,
        # Constraints travel with the field: tightening one rejects records
        # that used to load.
        "constraints": sorted(repr(m) for m in (finfo.metadata or [])),
        "alias": finfo.alias,
    }


def derive(package: str = "pretraga.domain") -> dict[str, Any]:
    import truth

    kinds = importlib.import_module(f"{package}.kinds")
    s = truth.survey(package)
    shape: dict[str, Any] = {}
    for name in sorted(s.concepts):
        model = s.concepts[name]
        shape[name] = {
            # The kind is decided by the base class, never guessed from a
            # field name: a Value that happens to carry a field called `uuid`
            # is still a Value.
            "kind": "entity" if issubclass(model, kinds.Entity) else "value",
            "fields": {fname: _field_contract(fi) for fname, fi in model.model_fields.items()},
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
            elif a.get("alias") != b.get("alias"):
                breaking.append(f"{name}.{f}: serialisation alias "
                                f"{a.get('alias')} -> {b.get('alias')}")
        oc, nc = o.get("config", {}), n.get("config", {})
        for k in sorted(set(oc) | set(nc)):
            if oc.get(k) != nc.get(k):
                breaking.append(f"{name}: model_config[{k}] {oc.get(k)} -> {nc.get(k)}")
    return breaking, additive


def check(package: str = "pretraga.domain", lock_path: Path = LOCK) -> int:
    fresh = derive(package)
    if not lock_path.exists():
        print(f"SCHEMA: {lock_path.name} is missing — run --write")
        return 1
    locked = json.loads(lock_path.read_text(encoding="utf-8"))
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
    if lock_path.exists():
        stored = json.loads(lock_path.read_text(encoding="utf-8"))
        breaking, _ = classify(stored["shape"], fresh)
        new_version = version or stored["version"]
        if breaking and new_version == stored["version"]:
            print(f"SCHEMA: refusing to overwrite v{stored['version']}: "
                  f"{len(breaking)} breaking change(s) need a NEW --version — "
                  "the bump is the human decision, the machine will not make it")
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
