"""Domain truth: classification, glossary, open questions, drift hook.

There is no hand-written map. Every public name in the domain ring must fall
into one of a closed set of roles, and the role decides what is owed. The check
is TOTAL — it keeps no list of names, so it cannot inflate and cannot go stale.

  concept        Entity / Value subclass — the things the system is about
  sum            a public union of concepts (an outcome with no fourth shape)
  port           a Protocol the domain declares; owes an entry in FAILURE_MODES
  vocabulary     an Enum the code branches on; owes a docstring
  alias          a NewType over a primitive
  error          an Exception the domain owns (a port's declared failure is
                 raised as a domain type, never as an adapter's own)
  service        a public function (pure domain behaviour); owes a docstring
  table          module-level data the domain declares (FAILURE_MODES is one)
  unclassified   ERROR: it entered the domain without a role

WHAT counts as the public surface is decided from the SOURCE, not from the
module dict: a name the module DECLARES (class, def, assignment, type alias)
owes a role, a name it merely IMPORTS is surveyed where it is declared. Reading
the module dict instead made the survey both too wide and too narrow — too wide
because `annotations`, `hashlib` and `ClassVar` are public entries in it, and
too narrow because everything that was not a class or a function fell through a
silent `else`, which is how FAILURE_MODES ended up with no role at all.

The framework module (kinds.py) is surveyed like any other, minus an explicit
CLOSED allowlist of the framework names themselves — so nothing can be smuggled
in beside them (measured: before this, a class planted in kinds.py escaped the
survey entirely, and so did anything in the package __init__).

Four ways a name used to leave the surface without leaving the code, each now
refused where it happens: a subpackage with no __init__.py (measured: unseen by
this survey AND by import-linter, so a domain module could reach the network
from one), a concept nested inside another concept, a module-level __getattr__,
and a class whose __module__ names somewhere it was not declared.

Whether a port has an implementation is NOT decided here. Two ports with the
same method names are indistinguishable by shape, so a structural count reports
a port as implemented when it is not. That question is answered by the
conformance suite, where the pairing is explicit and executable.

Dynamic-import escapes (__import__/eval/exec) are refused in domain, usecases
and adapters — the SAME modules whose importlib use the ring contract forbids,
so the two mechanisms draw one boundary, not two. The composition root may
compose dynamically; it already knows every concretion.
"""
from __future__ import annotations

import argparse
import ast
import enum
import importlib
import inspect
import sys
import types
import typing
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "docs" / "design_truth" / "domain_glossary.md"
SRC = ROOT / "src"
for _extra in (ROOT / "src", ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

PACKAGE = "pretraga.domain"
_KINDS_MODULE = f"{PACKAGE}.kinds"

# The framework itself, by name, closed. A new name in kinds.py that is not on
# this list is classified like anything else — and blocks if it has no role.
FRAMEWORK = frozenset({"MintedId", "ContentHash", "mint", "content_key",
                       "Entity", "Value", "Open", "KindError"})

# Rings whose import graph must stay statically checkable; mirrors the
# forbidden-importlib contract in pyproject.toml.
STATIC_RINGS = ("domain", "usecases", "adapters")


@dataclass
class Survey:
    concepts: dict[str, type[BaseModel]] = field(default_factory=dict)
    sums: dict[str, object] = field(default_factory=dict)
    ports: dict[str, type] = field(default_factory=dict)
    vocabularies: dict[str, type[enum.Enum]] = field(default_factory=dict)
    aliases: dict[str, object] = field(default_factory=dict)
    services: dict[str, object] = field(default_factory=dict)
    errors: dict[str, type] = field(default_factory=dict)
    tables: dict[str, object] = field(default_factory=dict)
    unclassified: dict[str, str] = field(default_factory=dict)
    module_of: dict[str, str] = field(default_factory=dict)
    structural: list[str] = field(default_factory=list)
    """Ways a name left the surface without leaving the code. Collected while
    walking, because the walk is the only place that knows where it happened."""


def _is_port(obj: object) -> typing.TypeGuard[type]:
    """A narrowing predicate, not a bare bool: the survey's elif chain relies
    on it to tell the type checker that a port IS a class."""
    return isinstance(obj, type) and bool(getattr(obj, "_is_protocol", False))


def _ring_dir(package: str) -> Path:
    return Path(next(iter(importlib.import_module(package).__path__)))


def _module_names(package: str) -> list[tuple[str, Path]]:
    """Every module of the ring INCLUDING the package initialiser, discovered
    from the FILESYSTEM rather than from pkgutil.

    Two measured escapes closed at once. walk_packages does not yield the
    package's own __init__, so a class defined there escaped classification
    entirely — and that is the likeliest place for one to appear, since it is
    where convenience code goes. It also skips any directory without an
    __init__.py, so a whole subpackage could sit in the ring unsurveyed."""
    pkg_dir = _ring_dir(package)
    out = [(package, pkg_dir / "__init__.py")]
    for py in sorted(pkg_dir.rglob("*.py")):
        rel = py.relative_to(pkg_dir)
        if "__pycache__" in rel.parts:
            continue
        if rel.name == "__init__.py":
            if rel.parent != Path("."):
                out.append((f"{package}." + ".".join(rel.parent.parts), py))
        else:
            out.append((f"{package}." + ".".join([*rel.parent.parts, rel.stem]), py))
    return out


def _namespace_packages(package: str) -> list[str]:
    """Directories of the ring that carry modules but no __init__.py.

    Measured, and the reason this is an error rather than a tolerated style: a
    domain module in such a directory importing urllib left import-linter
    reporting `Analyzed 23 files ... 3 kept, 0 broken`. The same directory with
    an __init__.py broke the contract immediately. Two of the three drift
    surfaces go blind together, so the directory is refused, not surveyed."""
    pkg_dir = _ring_dir(package)
    out = []
    for d in sorted(p for p in pkg_dir.rglob("*") if p.is_dir()):
        if "__pycache__" in d.parts or not any(d.glob("*.py")):
            continue
        if not (d / "__init__.py").exists():
            out.append(f"{d.relative_to(pkg_dir.parent.parent)}: a ring directory with modules "
                       "and no __init__.py — neither this survey nor import-linter sees inside")
    return out


def _declared_names(path: Path) -> set[str]:
    """The public names a module DECLARES, read from its source.

    The module dict cannot answer this: it also holds everything imported, so
    `annotations`, `hashlib` and `ClassVar` look exactly like model surface. A
    declaration is a class, a def, a type alias or an assignment; anything else
    in the dict arrived by import and is surveyed where it was declared."""
    out: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            out.add(node.name)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            out.add(node.name.id)
        elif isinstance(node, ast.Assign):
            out.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
    return {n for n in out if not n.startswith("_")}


def _is_union(obj: object) -> bool:
    """`A | B`, `Union[A, B]`, and PEP 695 `type X = A | B` — three spellings of
    one thing, and the third slipped between the branches until it was tried."""
    if isinstance(obj, types.UnionType) or typing.get_origin(obj) is typing.Union:
        return True
    inner = getattr(obj, "__value__", None)  # TypeAliasType
    return inner is not None and (isinstance(inner, types.UnionType)
                                  or typing.get_origin(inner) is typing.Union)


def _union_args(obj: object) -> tuple[object, ...]:
    inner = getattr(obj, "__value__", obj)
    return typing.get_args(inner)


def _classify(out: Survey, name: str, obj: typing.Any, entity: typing.Any, value: typing.Any) ->None:
    """Every declared public name lands in exactly one bucket. There is no
    silent `else`: the one that used to be here is why FAILURE_MODES — the
    system's own port registry — carried no role at all."""
    if isinstance(obj, type) and issubclass(obj, (entity, value)):
        out.concepts[name] = obj
    elif _is_port(obj):
        out.ports[name] = obj
    elif isinstance(obj, type) and issubclass(obj, enum.Enum):
        out.vocabularies[name] = obj
    elif _is_union(obj):
        out.sums[name] = obj
    elif isinstance(obj, typing.NewType):
        out.aliases[name] = obj
    elif inspect.isfunction(obj):
        out.services[name] = obj
    elif isinstance(obj, type) and issubclass(obj, BaseException):
        out.errors[name] = obj
    elif isinstance(obj, type) and issubclass(obj, BaseModel):
        out.unclassified[name] = ("a pydantic model in domain/ that is neither an "
                                  "Entity nor a Value — give it a kind")
    elif isinstance(obj, type):
        out.unclassified[name] = "a public class in domain/ with no kind"
    elif isinstance(obj, typing.TypeAliasType):
        out.unclassified[name] = ("a type alias in domain/ that is not a sum of "
                                  "concepts — make it a NewType or a sum")
    elif callable(obj):
        out.unclassified[name] = ("public domain behaviour that is not a function — a partial "
                                  "or a callable instance owes the same definition a service "
                                  "does; make it a def")
    else:
        out.tables[name] = obj


def _nested_concepts(s: Survey, entity: typing.Any, value: typing.Any) ->list[str]:
    """A concept declared inside another concept is addressable, persisted and
    invisible: the survey reads module level, so the inner shape never reaches
    the lock while travelling inside every record of the outer one."""
    out = []
    for name in sorted(s.concepts):
        for inner, obj in sorted(vars(s.concepts[name]).items()):
            if inner.startswith("_") or not isinstance(obj, type):
                continue
            if issubclass(obj, (entity, value)):
                out.append(f"{name}.{inner} ({s.module_of[name]}): a concept nested inside a "
                           "concept reaches neither the glossary nor the lock, yet its shape is "
                           "persisted inside every outer record — declare it at module level")
    return out


def survey(package: str = PACKAGE) -> Survey:
    kinds = importlib.import_module(f"{package}.kinds")
    entity, value = kinds.Entity, kinds.Value
    out = Survey()
    out.structural += _namespace_packages(package)
    for modname, path in _module_names(package):
        mod = importlib.import_module(modname)
        if "__getattr__" in vars(mod):
            out.structural.append(
                f"{modname}: a module-level __getattr__ — a name that exists only on access is "
                "invisible to any survey of the module; bind it at module level instead")
        for name in sorted(_declared_names(path)):
            if modname == f"{package}.kinds" and name in FRAMEWORK:
                continue
            if name not in vars(mod):
                continue  # declared under a conditional the import did not take
            obj = vars(mod)[name]
            declared_in = getattr(obj, "__module__", modname) if isinstance(obj, type) else modname
            if declared_in != modname:
                out.structural.append(
                    f"{name} ({modname}): declared here but reports __module__={declared_in}, "
                    "so it is skipped here as an import and absent there — surveyed nowhere")
                continue
            if name in out.module_of:
                out.structural.append(
                    f"{name}: declared in both {out.module_of[name]} and {modname} — survey, "
                    "glossary and lock all key on the bare name, so one silently replaces the "
                    "other and its shape stops being guarded")
                continue
            _classify(out, name, obj, entity, value)
            out.module_of[name] = modname
    out.structural += _nested_concepts(out, entity, value)
    return out


def kind_obligations(s: Survey) -> list[str]:
    """The kind obligations, re-checked over what the survey actually found.

    kinds.py enforces them once, at class creation. That is edge-triggered, and
    measured: `Model.model_config["frozen"] = False` plus a rebuild produces a
    mutable Value that every check accepted, because nothing looked again. The
    class-creation hook is still the thing that makes a violator impossible to
    write; this is the level-triggered reading of the same rule."""
    kinds = importlib.import_module(_KINDS_MODULE)
    errors = []
    for name in sorted(s.concepts):
        cls = s.concepts[name]
        if not (cls.__doc__ or "").strip():
            errors.append(f"concept {name}: no docstring — a concept that cannot be defined in "
                          "prose is not ready to enter the domain")
        if issubclass(cls, kinds.Value) and not cls.model_config.get("frozen"):
            errors.append(f"concept {name}: a value that is not frozen — immutability is the "
                          "obligation of the kind, and it was removed after class creation")
        if issubclass(cls, kinds.Entity):
            if "uuid" not in cls.model_fields:
                errors.append(f"concept {name}: an entity without a minted identity")
            if cls.model_config.get("frozen"):
                errors.append(f"concept {name}: an entity has a lifecycle, so it is not frozen")
    return errors


def classification_errors(s: Survey) -> list[str]:
    kinds = importlib.import_module(_KINDS_MODULE)
    errors = list(s.structural)
    errors += [f"{n} ({s.module_of[n]}): {why}" for n, why in sorted(s.unclassified.items())]
    errors += kind_obligations(s)
    for name, obj in sorted(s.sums.items()):
        stray = [getattr(m, "__name__", str(m)) for m in _union_args(obj)
                 if not (isinstance(m, type) and issubclass(m, (kinds.Entity, kinds.Value)))]
        if stray:
            errors.append(f"sum {name}: member(s) {', '.join(stray)} are not concepts")
    for name, voc in sorted(s.vocabularies.items()):
        if not (voc.__doc__ or "").strip():
            errors.append(f"vocabulary {name}: no docstring — say what the code branches on")
    for name, fn in sorted(s.services.items()):
        if not (fn.__doc__ or "").strip():
            errors.append(f"service {name}: no docstring — public domain behaviour is defined "
                          "in prose like any concept")
    for name, exc in sorted(s.errors.items()):
        if not (exc.__doc__ or "").strip():
            errors.append(f"error {name}: no docstring — say who raises it and who may catch it")
    ports_module = importlib.import_module(f"{PACKAGE}.ports")
    declared = getattr(ports_module, "FAILURE_MODES", {})
    for name, port in sorted(s.ports.items()):
        if not (port.__doc__ or "").strip():
            errors.append(f"port {name}: no docstring")
        if port not in declared:
            errors.append(f"port {name}: no entry in FAILURE_MODES — substitutability is about "
                          "how it fails, not only what it returns")
    for port in declared:
        if port.__name__ not in s.ports:
            errors.append(f"FAILURE_MODES lists {port.__name__}, which is not a port")
    return errors


DYNAMIC = {"__import__", "eval", "exec", "compile"}


def static_import_escapes(pkg_root: Path, rings: tuple[str, ...] = STATIC_RINGS) -> list[str]:
    """Calls that make the import graph unknowable, in the rings whose imports
    are contractually checked.

    Measured: `importlib.import_module` is caught by a forbidden-module
    contract, but `__import__("urllib.request")` is invisible to it — the ring
    contract kept reporting green while the domain reached the network. A
    guarantee with a silent exception is worse than no guarantee. The scope is
    the SAME three rings as the importlib contract: the composition root stays
    free to compose dynamically."""
    escapes: list[str] = []
    for ring_name in rings:
        ring_dir = pkg_root / ring_name
        if not ring_dir.exists():
            continue
        for py in sorted(ring_dir.rglob("*.py")):
            for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in DYNAMIC:
                    escapes.append(f"{py.relative_to(pkg_root.parent.parent)}:{node.lineno}: "
                                   f"{node.func.id}() — the import graph stops being "
                                   "checkable here")
    return escapes


def render_glossary(s: Survey) -> str:
    kinds = importlib.import_module(_KINDS_MODULE)
    out = ["# PretRAGa domain glossary", "",
           "GENERATED from the domain package — never edit by hand. A concept's definition",
           "is the docstring of its class, so there is no second copy that could drift.", ""]
    pkg = importlib.import_module(PACKAGE)
    out.extend(["## Conventions", "", inspect.cleandoc(pkg.__doc__ or ""), ""])

    def block(title: str, items: Mapping[str, object], note: str) -> None:
        out.extend([f"## {title}", "", note, ""])
        for name in sorted(items):
            obj = items[name]
            out.extend([f"### {name}", "", inspect.cleandoc(getattr(obj, "__doc__", "") or "")])
            for o in getattr(obj, "open_questions", ()):
                out.append("")
                out.append(f"- open: {o.question} (trigger: `{o.trigger.value}`)")
            out.append("")

    entities = {n: o for n, o in s.concepts.items() if issubclass(o, kinds.Entity)}
    values = {n: o for n, o in s.concepts.items() if issubclass(o, kinds.Value)}
    block("Entities", entities, "Minted opaque identity; a lifecycle; never frozen.")
    block("Values", values,
          "Immutable; identity IS the content. Where persisted, the key is the content hash.")
    block("Ports", s.ports, "Interfaces the domain declares; each declares its failure mode "
                            "in `FAILURE_MODES`.")
    block("Sums", s.sums, "Closed unions: no shape exists outside the listed ones.")
    out.extend(["## Vocabularies", ""])
    for name in sorted(s.vocabularies):
        voc = s.vocabularies[name]
        first = inspect.cleandoc(voc.__doc__ or "").splitlines()[0]
        members = ", ".join(f"`{m.value}`" for m in voc)
        out.append(f"- **{name}** — {first} {members}")
    out.extend(["", "## Services", ""])
    for name in sorted(s.services):
        first = inspect.cleandoc(s.services[name].__doc__ or "").splitlines()[0]
        out.append(f"- **{name}** — {first}")
    out.extend(["", "## Errors", ""])
    for name in sorted(s.errors):
        first = inspect.cleandoc(s.errors[name].__doc__ or "").splitlines()[0]
        out.append(f"- **{name}** — {first}")
    out.extend(["", "## Tables", "",
                ("Module-level data the domain declares. A table owes nothing beyond having a "
                 "role: what it means is checked by the rules that read it. Listed by name only "
                 "— the contents live in the code, and a second copy here would drift."), ""])
    for name in sorted(s.tables):
        out.append(f"- **{name}** ({s.module_of[name]})")
    out.append("")
    return "\n".join(out)


def run(glossary: Path = GLOSSARY, package: str = PACKAGE, src: Path = SRC) -> int:
    s = survey(package)
    errors = classification_errors(s)
    errors += static_import_escapes(src / package.split(".")[0])
    if not errors:
        want = render_glossary(s)
        if not glossary.exists():
            errors.append(f"glossary: {glossary.name} is missing — run --build")
        elif glossary.read_text(encoding="utf-8") != want:
            errors.append(f"glossary: {glossary.name} is stale or hand-edited — run --build")
    if errors:
        print(f"TRUTH: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    kinds = importlib.import_module(_KINDS_MODULE)
    n_entities = sum(1 for c in s.concepts.values() if issubclass(c, kinds.Entity))
    opens = [o for c in s.concepts.values() for o in getattr(c, "open_questions", ())]
    by_trigger: dict[str, int] = {}
    for o in opens:
        by_trigger[o.trigger.value] = by_trigger.get(o.trigger.value, 0) + 1
    print(f"TRUTH: OK — {len(s.concepts)} concepts ({n_entities} entities, "
          f"{len(s.concepts) - n_entities} values), {len(s.ports)} ports, "
          f"{len(s.sums)} sums, {len(s.vocabularies)} vocabularies, "
          f"{len(s.services)} services, {len(s.errors)} errors, {len(s.tables)} tables")
    if opens:
        print(f"  i {len(opens)} open question(s): "
              + ", ".join(f"{k}×{v}" for k, v in sorted(by_trigger.items())))
    return 0


def hook_mode() -> int:
    """Session-hook entry: read the harness PostToolUse JSON from stdin, filter
    to governed paths, run the full check plus the schema lock. Always exits 0
    — the hook is advisory; the blocking exits are the gate and CI. Errors are
    returned as decision:block so red checks are addressed before moving on."""
    import io
    import json as _json
    from contextlib import redirect_stdout

    try:
        payload = _json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — malformed hook input must never crash the hook
        return 0
    file_path = str((payload.get("tool_input") or {}).get("file_path") or "")
    root = str(ROOT)
    if not file_path.startswith(root + "/"):
        return 0
    rel = file_path[len(root) + 1:]
    if not (rel.startswith(("src/", "docs/design_truth/", "docs/core/", "tools/"))
            or rel == "schema.lock.json"):
        return 0
    lines = [f"[truth] change touches governed path: {rel}"]
    buf = io.StringIO()
    failed = False
    try:
        with redirect_stdout(buf):
            failed = run() != 0
            import schema_lock

            failed |= schema_lock.check() != 0
    except Exception as exc:  # noqa: BLE001 — the hook must ALWAYS emit JSON
        lines.append(f"[truth] CHECKER CRASHED: {exc!r}")
        failed = True
    lines += buf.getvalue().strip().splitlines()
    out: dict = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                        "additionalContext": "\n".join(lines)}}
    if failed:
        out["decision"] = "block"
        out["reason"] = ("Domain truth FAILED — fix the ring, regenerate the views "
                         "(--build / --write), or surface the failure before continuing.")
    print(_json.dumps(out, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--hook":
        return hook_mode()
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--glossary", type=Path, default=GLOSSARY)
    ap.add_argument("--package", default=PACKAGE)
    ap.add_argument("--src", type=Path, default=SRC)
    ns = ap.parse_args(argv)
    if ns.build:
        ns.glossary.write_text(render_glossary(survey(ns.package)), encoding="utf-8")
        print(f"written: {ns.glossary}")
        return 0
    return run(ns.glossary, ns.package, ns.src)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
