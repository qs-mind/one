"""The request shapes: the contract every part of the engine, its tools and its routes read.

Every model forbids extra keys, so a union picks its member by the keys that were sent.
"""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

# Function names and `pi` are part of the formula language, never inputs.
RESERVED_NAMES = frozenset(
    {"sum", "count", "avg", "min", "max", "round", "abs", "sqrt", "to", "if", "pi"}
)

# Unicode letters, digits and _, starting with a letter or _.
Name = Annotated[str, StringConstraints(pattern=r"^[^\W\d]\w{0,63}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NumberRef(Strict):
    """A Source Ledger number by its id."""

    number: str


class SlotRef(Strict):
    """The current number of that name on an item, found by id or code."""

    item: str
    name: str


class ListRef(Strict):
    numbers: list[str] = Field(min_length=1, max_length=20_000)


class Selector(Strict):
    """Items by kind, code prefix and fields equal to values; at least one is set."""

    kind: str | None = None
    code_prefix: str | None = None
    where: dict[str, str | int | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _something_set(self) -> "Selector":
        if self.kind is None and self.code_prefix is None and not self.where:
            raise ValueError("a selector needs kind, code_prefix or where")
        return self


class EachRef(Strict):
    """That number on every item the selector matches."""

    each: Selector
    name: str


class Constant(Strict):
    """A stated constant: a plain number or %, with the reason it is used."""

    constant: str
    unit: Literal["%"] | None = None
    why: str = Field(min_length=1, max_length=300)


InputSpec = NumberRef | SlotRef | ListRef | EachRef | Constant


class Rounding(Strict):
    places: int = Field(2, ge=-9, le=10)
    mode: Literal["half_up", "half_even", "up", "down"] = "half_up"


class ResultSpec(Strict):
    unit: str | None = None  # "" is a plain number; None only in a preview
    round: Rounding | None = None  # None: the default, reported in defaults_used


class Save(Strict):
    name: str = Field(min_length=1, max_length=64)
    reason: str | None = None


class CalcRequest(Strict):
    formula: str = Field(min_length=1, max_length=4000)
    inputs: dict[Name, InputSpec] = Field(default_factory=dict, max_length=200)
    item: str | None = None  # bare names read this item; the result is saved on it
    for_each: Selector | None = None  # run on every matching item instead (not with `item`)
    result: ResultSpec = Field(default_factory=ResultSpec)
    save: Save | None = None  # omit to preview; needs `item` or `for_each` and `result.unit`
    skip_missing: bool = False  # for_each and EachRef: skip items without the number, listed

    # Each rule is checked on its own field, so a refusal names that field.
    @field_validator("inputs")
    @classmethod
    def _not_reserved(cls, inputs: dict) -> dict:
        taken = sorted(RESERVED_NAMES & set(inputs))
        if taken:
            raise ValueError(f"{taken[0]} is a function or constant, not an input name")
        return inputs

    @field_validator("for_each")
    @classmethod
    def _not_with_item(cls, for_each: Selector | None, info: ValidationInfo):
        if for_each is not None and info.data.get("item") is not None:
            raise ValueError("send item or for_each, not both")
        return for_each

    @field_validator("save")
    @classmethod
    def _save_has_a_target(cls, save: Save | None, info: ValidationInfo):
        if save is None:
            return save
        if info.data.get("item") is None and info.data.get("for_each") is None:
            raise ValueError("save needs item or for_each")
        result = info.data.get("result")
        if result is None or result.unit is None:
            raise ValueError("save needs result.unit")
        return save


class UnitRequest(Strict):
    symbol: str
    equals: str  # e.g. "50 kg"
    source_id: str
    dated: str
    reason: str | None = None


class ExplainRequest(Strict):
    number: str
    page: int = Field(1, ge=1)


class RecalcRequest(Strict):
    apply: bool = False
    only: list[str] | None = None  # calculation ids
