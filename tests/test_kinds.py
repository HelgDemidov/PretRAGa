"""Kind obligations, checked where they are enforced: class creation."""
from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import create_model

from pretraga.domain.kinds import ContentHash, Entity, KindError, Value


def test_a_well_formed_value_is_accepted() -> None:
    class Good(Value):
        """A documented, frozen value."""

        h: ContentHash

    assert Good.model_config.get("frozen") is True


def test_a_well_formed_entity_is_accepted() -> None:
    class Good(Entity):
        """A documented entity with a minted identity."""

        state: str

    assert "uuid" in Good.model_fields


def test_a_concept_without_a_definition_is_rejected() -> None:
    with pytest.raises(KindError, match="defined in prose"):

        class Undefined(Entity):
            state: str


def test_a_blank_definition_is_rejected() -> None:
    with pytest.raises(KindError, match="defined in prose"):

        class Blank(Value):
            """   """  # noqa: D419 — the emptiness IS the case under test

            h: ContentHash


def test_a_value_may_not_unset_frozen() -> None:
    with pytest.raises(KindError, match="frozen"):

        class Mutable(Value):
            """A value trying to become mutable."""

            model_config = {"frozen": False}
            h: ContentHash


def test_a_value_may_not_unset_frozen_through_class_kwargs() -> None:
    with pytest.raises(KindError, match="frozen"):

        class Mutable2(Value, frozen=False):
            """A value trying to become mutable the other way."""

            h: ContentHash


def test_an_underscore_name_does_not_exempt_the_frozen_obligation() -> None:
    """A survey-level backstop re-checks every concept it finds regardless of
    name, which makes this scenario safe end to end either way — but that
    redundancy also means an integration test cannot tell whether THIS
    specific edge-triggered check still refuses the exemption, or whether the
    backstop alone is doing the work. Only a direct, in-process check of class
    creation can."""
    with pytest.raises(KindError, match="frozen"):

        class _Loose(Value, frozen=False):
            """A private-named value trying to dodge its kind via naming."""

            payload: str


def test_a_grandchild_may_not_unset_frozen() -> None:
    class Base(Value):
        """A value."""

        h: ContentHash

    with pytest.raises(KindError, match="frozen"):

        class Child(Base):
            """A subclass trying to become mutable."""

            model_config = {"frozen": False}


def test_overriding_the_hook_does_not_bypass_it() -> None:
    """The obligation is enforced by the base class, not by cooperation."""
    with pytest.raises(KindError, match="frozen"):

        class Bypass(Value):
            """A value trying to disable its own check."""

            model_config = {"frozen": False}

            @classmethod
            def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
                return None


def test_an_entity_may_not_shadow_its_minted_identity() -> None:
    """`uuid` is inherited from Entity itself, so no ordinary subclass omits
    it — the obligation is reachable only by shadowing the inherited field
    with a ClassVar of the same name, which un-declares it as a pydantic
    field."""
    with pytest.raises(KindError, match="minted identity"):

        class NoIdentity(Entity):
            """An entity that un-declares its inherited uuid field."""

            uuid: ClassVar[str] = "shadowed"  # type: ignore[misc,assignment]
            state: str = "x"


def test_an_entity_may_not_be_frozen() -> None:
    with pytest.raises(KindError, match="not frozen"):

        class Immutable(Entity):
            """An entity trying to be immutable."""

            model_config = {"frozen": True}
            state: str


def test_a_dynamically_built_concept_is_checked_too() -> None:
    """create_model is a back door only if the hook does not run."""
    with pytest.raises((KindError, KeyError, TypeError)):
        create_model("Dynamic", __base__=Value, h=(str, ...))
