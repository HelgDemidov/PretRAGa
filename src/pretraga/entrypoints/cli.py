"""Composition root: the only place that knows concrete implementations."""
from __future__ import annotations

import sys

from pretraga.adapters.lexical_sqlite import SqliteLexicalSearch
from pretraga.domain.ports import LexicalSearch


def main(argv: list[str]) -> int:
    lexical: LexicalSearch = SqliteLexicalSearch(path=":memory:")
    print(len(lexical.search(" ".join(argv), 5)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
