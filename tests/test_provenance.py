"""Behavioural invariants of provenance concepts that schema_lock cannot
diff structurally — imperative validator logic, not a declarative Field()
constraint."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from pretraga.domain.provenance import CharSpan


def test_a_char_span_with_start_after_end_is_rejected() -> None:
    with pytest.raises(ValidationError, match="start"):
        CharSpan(start=5, end=2)


def test_a_char_span_with_start_equal_to_end_is_accepted() -> None:
    CharSpan(start=3, end=3)
