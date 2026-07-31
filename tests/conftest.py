"""Hermeticity by construction: no test may write into the repository.

The tools take their paths as arguments with production defaults, so a test
that forgets to pass a temporary path rewrites the real glossary or the real
lock. The fixture below snapshots the whole tree around every test — files, not
a remembered list of files — and fails naming what moved.
"""
from __future__ import annotations

import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "src", ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

WATCHED = (ROOT / "src", ROOT / "tools", ROOT / "docs")


def _snapshot() -> dict[str, str]:
    out: dict[str, str] = {}
    lock = ROOT / "schema.lock.json"
    if lock.exists():
        out[lock.name] = hashlib.sha256(lock.read_bytes()).hexdigest()
    for root in WATCHED:
        for path in sorted(root.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            out[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@pytest.fixture(autouse=True)
def production_untouched() -> Iterator[None]:
    before = _snapshot()
    yield
    after = _snapshot()
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    assert not (added or removed or changed), (
        "a test wrote into production artifacts: "
        f"changed={changed} added={added} removed={removed}")


@pytest.fixture
def ring(tmp_path: Path) -> Path:
    """A copy of the repository tree at the SAME depth as production.

    Depth matters: the tools derive their paths from their own location, so a
    copy at another depth silently resolves elsewhere — the class of breakage
    that stays quiet until something reads the wrong file.
    """
    import shutil

    dest = tmp_path / "repo"
    dest.mkdir()
    for name in ("src", "tools", "docs", "tests", "pyproject.toml", "schema.lock.json"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, dest / name,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copy2(source, dest / name)
    return dest
