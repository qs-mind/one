"""The evaluator: a formula's tree and its inputs in, an exact result in the asked unit out.

Values are `Decimal` inside `CONTEXT`; units are carried as written and cancel exactly. The tree
is walked with an explicit stack, never recursion: a chain like `a + a + … + a` is as deep as it
has nodes. Each operator or call is one step of the trace. `if` runs only the branch it chooses;
the other branch is walked for its units only, so a unit mistake there is still refused.
"""

import decimal
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from qsone import copy
from qsone.calc import CONTEXT
from qsone.calc.errors import CalcError
from qsone.calc.formula import (
    CONSTANTS,
    FUNCTIONS,
    USAGE_AR,
    Binary,
    Call,
    Name,
    Node,
    Num,
    Percent,
    Text,
    Unary,
    walk,
)
from qsone.calc.spec import Rounding
from qsone.calc.units import Unit, UnitTable


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: Unit


@dataclass(frozen=True)
class Input:
    name: str
    values: tuple[Quantity, ...]  # one, or many for a list
    is_list: bool
    origin: Literal["ledger", "constant"]


@dataclass(frozen=True)
class Evaluation:
    value: Decimal  # in the result unit, rounded
    unrounded: Decimal
    unit: Unit  # the result unit as asked (or as found, in a preview without one)
    exact: bool
    steps: list[dict]  # one per operator or call: n, text, op, args, value, unit, factor?, exact
    constants: list[dict]  # {"value", "unit": "%" | "", "at"} for each literal in the formula
    rounding: dict  # {"places", "mode", "from", "to"}
    units: set[str]  # every symbol spelling used, for the engine's unit definitions and notes


PI = Decimal("3.1415926535897932384626433832795028841971693993751")  # 50 significant digits
NO_UNIT = {"en": "no unit", "ar": "من غير وحدة"}  # how a plain number reads in a refusal
_NONE = {"en": "none", "ar": "مفيش"}
_MODES = {
    "half_up": decimal.ROUND_HALF_UP,
    "half_even": decimal.ROUND_HALF_EVEN,
    "up": decimal.ROUND_UP,
    "down": decimal.ROUND_DOWN,
}
_COMPARE: dict[str, Callable[[Decimal, Decimal], bool]] = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}
_LIST_FUNCTIONS = {"sum", "count", "avg", "min", "max"}
_MAX_POWER = 12
_PLACES = range(-9, 11)  # as spec.Rounding
_VISIT, _CHOOSE, _APPLY = "visit", "choose", "apply"


@dataclass(frozen=True)
class _V:
    """A node's result. `value` is None in a branch `if` did not choose, walked for units only."""

    value: Decimal | bool | None
    unit: Unit
    zero: bool = False  # a literal 0, which matches any unit
    items: tuple[Quantity, ...] | None = None  # a list input...
    name: str = ""  # ...and its name
    test: bool = False  # a comparison: it stands only as if()'s condition
    pi: bool = False  # pi, which is not exact


def evaluate(
    tree: Node,
    text: str,
    inputs: Mapping[str, Input],
    table: UnitTable,
    *,
    unit: str | None,
    rounding: Rounding,
) -> Evaluation:
    """`unit` is the result unit ("" for a plain number); None keeps the unit found (a preview)."""
    with decimal.localcontext(CONTEXT) as ctx:
        run = _Run(text, inputs, table, ctx)
        return run.result(run.walk(tree), unit, rounding)


def _refuse(key: str, *, field: str, **values) -> CalcError:
    """A value given as {en, ar} fills each text in its own language."""

    def said_in(lang: str) -> dict:
        return {k: v[lang] if isinstance(v, dict) else v for k, v in values.items()}

    error = CalcError(key, field=field, **said_in("en"))
    error.text = {
        lang: text.format(field=field, **said_in(lang)) for lang, text in vars(copy)[key].items()
    }
    error.values = values
    return error


def _operands(node: Node) -> tuple[Node, ...]:
    """The children walked for a node's value; a power's exponent is read from the tree."""
    match node:
        case Binary(op="^"):
            return (node.left,)
        case Binary():
            return (node.left, node.right)
        case Unary() | Percent():
            return (node.arg,)
        case Call():
            return node.args
    return ()


def _whole_literal(node: Node) -> str | None:
    """`2`, `-2` or `+2` as written in the formula, else None."""
    sign = ""
    if isinstance(node, Unary) and isinstance(node.arg, Num):
        sign, node = ("-" if node.op == "-" else ""), node.arg
    if isinstance(node, Num) and node.text.isdigit():
        return sign + node.text
    return None


def _rounded(value: Decimal, places: int, mode: str) -> Decimal:
    """Rounded to `places`, with all the digits that takes; deliberate, so not marked inexact."""
    with decimal.localcontext() as ctx:
        ctx.prec = max(ctx.prec, value.adjusted() + 1 + places)
        return value.quantize(Decimal((0, (1,), -places)), rounding=_MODES[mode])


def _show(value: Decimal | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return f"{value:f}"


class _Run:
    def __init__(self, text: str, inputs: Mapping[str, Input], table: UnitTable, ctx):
        self.text = text
        self.inputs = inputs
        self.table = table
        self.ctx = ctx
        self.steps: list[dict] = []
        self.constants: list[dict] = []
        self.units: set[str] = set()
        self.exact = True

    # Walking the tree.

    def walk(self, tree: Node) -> _V:
        for node in walk(tree):
            if isinstance(node, Name) and node.name not in CONSTANTS | set(self.inputs):
                names = ", ".join(sorted(self.inputs)) or _NONE
                raise _refuse("CALC_UNKNOWN_NAME", field="inputs", name=node.name, names=names)
        results: list[_V] = []
        todo: list[tuple[Node, bool, str]] = [(tree, True, _VISIT)]
        while todo:
            node, live, state = todo.pop()
            if state == _APPLY:
                n = len(_operands(node))
                args = results[len(results) - n :]
                del results[len(results) - n :]
                results.append(self.apply(node, args, live))
            elif state == _CHOOSE:  # the condition is known: walk both branches, run one
                pick = results[-1].value if live else None
                todo.append((node, live, _APPLY))
                todo.append((node.args[2], live and pick is False, _VISIT))
                todo.append((node.args[1], live and pick is True, _VISIT))
            elif (leaf := self.leaf(node, live)) is not None:
                results.append(leaf)
            elif isinstance(node, Call) and node.fn == "if":
                condition = node.args[0]
                if not (isinstance(condition, Binary) and condition.op in _COMPARE):
                    raise self.usage("if", node)
                todo += [(node, live, _CHOOSE), (condition, live, _VISIT)]
            else:
                if isinstance(node, Binary) and node.op == "^":
                    self.exponent(node)
                todo.append((node, live, _APPLY))
                todo.extend((child, live, _VISIT) for child in reversed(_operands(node)))
        return results[0]

    def leaf(self, node: Node, live: bool) -> _V | None:
        match node:
            case Num():
                return self.literal(node, node, "")
            case Percent(arg=Num() as num):
                self.units.add("%")
                return self.literal(node, num, "%")
            case Text():
                return _V(None, Unit())  # read from the tree by to() and round()
            case Name() if node.name in CONSTANTS:
                return _V(PI, Unit(), pi=True)
            case Name():
                given = self.inputs[node.name]
                for quantity in given.values:
                    self.units |= {symbol.spelling for symbol, _ in quantity.unit.terms}
                if given.is_list:
                    return _V(None, Unit(), items=given.values, name=node.name)
                first = given.values[0]
                return _V(first.value if live else None, first.unit)
        return None

    def literal(self, node: Node, num: Num, unit: str) -> _V:
        self.constants.append({"value": num.text, "unit": unit, "at": node.start})
        value = Decimal(num.text)
        return _V(value, self.table.parse(unit), zero=value == 0)

    def exponent(self, node: Binary) -> int:
        written = _whole_literal(node.right)
        if written is None or abs(int(written)) > _MAX_POWER:
            raise self.refuse("CALC_POWER", node)
        self.constants.append({"value": written, "unit": "", "at": node.right.start})
        return int(written)

    # One operator or call: its value, its unit and its step.

    def apply(self, node: Node, args: list[_V], live: bool) -> _V:
        takes_list = isinstance(node, Call) and node.fn in _LIST_FUNCTIONS and len(args) == 1
        is_if = isinstance(node, Call) and node.fn == "if"
        for place, arg in enumerate(args):
            if arg.items is not None and not takes_list:
                raise self.refuse("CALC_LIST_HERE", node, name=arg.name)
            if arg.test and not (is_if and place == 0):
                raise self.usage("if", node)
        self.ctx.flags[decimal.Inexact] = False
        try:
            out, factor = self.compute(node, args, live)
        except ZeroDivisionError:
            raise self.refuse("CALC_DIVIDE_BY_ZERO", node, text=self.span(node)) from None
        except (decimal.Overflow, decimal.InvalidOperation):
            raise self.refuse("CALC_TOO_BIG", node, text=self.span(node)) from None
        inexact = self.ctx.flags[decimal.Inexact]
        self.ctx.flags[decimal.Inexact] = False
        if not live:
            return out

        if is_if:
            shown = [args[0], args[1] if args[0].value else args[2]]
        elif takes_list:
            shown = []
        else:
            shown = [
                a
                for a, child in zip(args, _operands(node), strict=True)
                if not isinstance(child, Text)
            ]
        inexact = inexact or any(a.pi for a in shown)
        self.exact = self.exact and not inexact
        step = {
            "n": len(self.steps) + 1,
            "text": self.span(node),
            "op": self.op(node),
            "args": [{"value": _show(a.value), "unit": self.table.format(a.unit)} for a in shown],
            "value": _show(out.value),
            "unit": self.table.format(out.unit),
        }
        if takes_list:
            step["count"] = len(args[0].items) if args[0].items is not None else 1
        if factor is not None:
            step["factor"] = _show(factor)
        step["exact"] = not inexact
        self.steps.append(step)
        return out

    def compute(self, node: Node, args: list[_V], live: bool) -> tuple[_V, Decimal | None]:
        """The result and the factor a conversion or cancellation applied (None if none did)."""
        match node:
            case Unary():
                (a,) = args
                value = -a.value if live and node.op == "-" else a.value
                return _V(value, a.unit, zero=a.zero), None
            case Percent():
                (a,) = args
                factor = Decimal("0.01")
                return _V(a.value * factor if live else None, a.unit), factor
            case Binary(op="+" | "-"):
                return self.add(node, *args, live)
            case Binary(op="*" | "/"):
                left, right = args
                combined = left.unit * right.unit if node.op == "*" else left.unit / right.unit
                factor, unit = self.table.simplify(combined)
                value = None
                if live and node.op == "*":
                    value = left.value * right.value * factor
                elif live:
                    if right.value == 0:
                        raise ZeroDivisionError  # decimal calls 0/0 invalid, not a division by zero
                    value = left.value * factor / right.value
                return _V(value, unit), factor if unit != combined else None
            case Binary(op="^"):
                (a,) = args
                n = int(_whole_literal(node.right))
                value = None
                if live and a.value == 0 and n < 0:
                    raise ZeroDivisionError
                if live:
                    value = a.value**n if n else Decimal(1)  # decimal refuses 0^0
                return _V(value, a.unit.power(n)), None
            case Binary():  # a comparison
                left, right = args
                _, factor = self.common(node, left, right)
                value = _COMPARE[node.op](left.value, right.value * factor) if live else None
                return _V(value, Unit(), test=True), None
            case Call(fn="if"):
                return self.choose(node, *args, live)
            case Call(fn="sum" | "count" | "avg" | "min" | "max") if len(args) == 1:
                return self.over_list(node, args[0], live), None
            case Call(fn="min" | "max"):
                return self.extreme(node, args, live), None
            case Call(fn="round"):
                return self.round(node, args, live), None
            case Call(fn="abs"):
                (a,) = args
                return _V(abs(a.value) if live else None, a.unit, zero=a.zero), None
            case Call(fn="sqrt"):
                return self.sqrt(node, args[0], live), None
            case Call(fn="to"):
                a = args[0]
                unit = self.table.parse(node.args[1].value)
                self.units |= {symbol.spelling for symbol, _ in unit.terms}
                factor = Decimal(1) if a.zero else self.convert(a.unit, unit, node)
                value = a.value * factor if live else None
                return _V(value, unit), factor if a.unit != unit and not a.zero else None
        raise AssertionError(node)  # the parser makes no other node

    def add(self, node: Binary, left: _V, right: _V, live: bool) -> tuple[_V, Decimal | None]:
        unit, factor = self.common(node, left, right)
        value = None
        if live:
            r_value = right.value * factor
            value = left.value + r_value if node.op == "+" else left.value - r_value
        shown = factor if not (left.zero or right.zero) and factor != 1 else None
        return _V(value, unit, zero=left.zero and right.zero), shown

    def common(self, node: Node, left: _V, right: _V) -> tuple[Unit, Decimal]:
        """The unit two sides meet in (the left's, or the other's when one is a literal 0) and
        the factor that takes the right side into it."""
        if left.zero and not right.zero:
            return right.unit, Decimal(1)
        if right.zero:
            return left.unit, Decimal(1)
        return left.unit, self.convert(right.unit, left.unit, node)

    def choose(self, node: Call, test: _V, then: _V, other: _V, live: bool):
        unit, _ = self.common(node, then, other)  # both branches' units, run or not
        if not live:
            return _V(None, unit, zero=then.zero and other.zero), None
        chosen = then if test.value else other
        factor = Decimal(1) if chosen.zero else self.convert(chosen.unit, unit, node)
        shown = factor if chosen.unit != unit and not chosen.zero else None
        return _V(chosen.value * factor, unit, zero=then.zero and other.zero), shown

    def over_list(self, node: Call, a: _V, live: bool) -> _V:
        members = a.items if a.items is not None else (Quantity(a.value, a.unit),)
        if node.fn == "count":
            return _V(Decimal(len(members)), Unit())
        if not members:
            if node.fn == "sum":
                return _V(Decimal(0), Unit(), zero=True)
            raise self.usage(node.fn, node)
        unit = members[0].unit
        factors = [self.convert(m.unit, unit, node) for m in members]
        if not live:
            return _V(None, unit)
        values = [m.value * f for m, f in zip(members, factors, strict=True)]
        match node.fn:
            case "sum":
                value = sum(values, Decimal(0))
            case "avg":
                value = sum(values, Decimal(0)) / len(values)
            case "min":
                value = min(values)
            case _:
                value = max(values)
        return _V(value, unit)

    def extreme(self, node: Call, args: list[_V], live: bool) -> _V:
        """min or max of values: each in the unit of the first that is not a literal 0."""
        base = next((a for a in args if not a.zero), None)
        if base is None:
            pick = min if node.fn == "min" else max
            return _V(pick(a.value for a in args), Unit(), zero=True)
        factors = [Decimal(1) if a.zero else self.convert(a.unit, base.unit, node) for a in args]
        if not live:
            return _V(None, base.unit)
        values = [a.value * f for a, f in zip(args, factors, strict=True)]
        return _V(min(values) if node.fn == "min" else max(values), base.unit)

    def round(self, node: Call, args: list[_V], live: bool) -> _V:
        a, places = args[0], args[1]
        mode = node.args[2].value if len(args) == 3 else "half_up"
        whole = live and places.value == places.value.to_integral_value()
        if places.unit.terms or (live and not (whole and int(places.value) in _PLACES)):
            raise self.usage("round", node)
        value = _rounded(a.value, int(places.value), mode) if live else None
        return _V(value, a.unit, zero=a.zero)

    def sqrt(self, node: Call, a: _V, live: bool) -> _V:
        if any(power % 2 for _, power in a.unit.terms) or (live and a.value < 0):
            raise self.refuse("CALC_SQRT", node)
        unit = Unit(tuple((symbol, power // 2) for symbol, power in a.unit.terms))
        return _V(a.value.sqrt() if live else None, unit)

    def convert(self, frm: Unit, to: Unit, node: Node) -> Decimal:
        """value_in_to = value_in_frm * factor. A refusal names `to` first: the side that is kept,
        so an exchange rate reads the right way round (EGP/USD to bring USD into EGP)."""
        if frm.dims == to.dims:
            return self.table.ratio(frm, to)
        try:
            self.table.ratio(to, frm)
        except CalcError as e:
            if e.key == "CALC_CURRENCIES_DIFFER":
                raise self.refuse(e.key, node, **e.values) from None
        raise self.refuse("CALC_UNITS_DIFFER", node, left=self.shown(to), right=self.shown(frm))

    # The result.

    def result(self, found: _V, unit: str | None, rounding: Rounding) -> Evaluation:
        if found.items is not None:
            raise _refuse("CALC_LIST_HERE", field="formula", at=0, name=found.name)
        if found.test:
            raise _refuse("CALC_USAGE", field="formula", at=0, **self.usage_of("if"))
        want = found.unit if unit is None else self.table.parse(unit)
        self.units |= {symbol.spelling for symbol, _ in want.terms}
        if found.zero:
            factor = Decimal(1)
        elif found.unit.dims != want.dims:
            got, asked = self.shown(found.unit), self.shown(want)
            raise _refuse("CALC_RESULT_UNIT", field="result.unit", got=got, want=asked)
        else:
            factor = self.table.ratio(found.unit, want)
        try:
            unrounded = found.value * factor
            value = _rounded(unrounded, rounding.places, rounding.mode)
        except (decimal.Overflow, decimal.InvalidOperation):
            raise _refuse("CALC_TOO_BIG", field="formula", at=0, text=self.text) from None
        exact = self.exact and not found.pi and not self.ctx.flags[decimal.Inexact]
        if value.is_zero():
            value = value.copy_abs()  # never -0
        return Evaluation(
            value=value,
            unrounded=unrounded,
            unit=want,
            exact=exact,
            steps=self.steps,
            constants=self.constants,
            rounding={
                "places": rounding.places,
                "mode": rounding.mode,
                "from": _show(unrounded),
                "to": _show(value),
            },
            units=self.units,
        )

    # Texts.

    @staticmethod
    def op(node: Node) -> str:
        if isinstance(node, Call):
            return node.fn
        return "%" if isinstance(node, Percent) else node.op

    def span(self, node: Node) -> str:
        return self.text[node.start : node.end]

    def shown(self, unit: Unit) -> str | dict:
        return self.table.format(unit) or NO_UNIT

    def refuse(self, key: str, node: Node, **values) -> CalcError:
        return _refuse(key, field="formula", at=node.start, **values)

    @staticmethod
    def usage_of(fn: str) -> dict:
        return {"fn": fn, "usage": {"en": FUNCTIONS[fn], "ar": USAGE_AR[fn]}}

    def usage(self, fn: str, node: Node) -> CalcError:
        return self.refuse("CALC_USAGE", node, **self.usage_of(fn))
