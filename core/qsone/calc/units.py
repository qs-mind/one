"""Units as written, matched by key, converted exactly; currencies kept apart.

A unit is a list of symbols with powers, kept in the order and spelling the caller wrote
(`EGP/m3`). Matching uses each symbol's key, so `m`, `M` and `م` are one unit. Sizes are exact
decimals in base units: m, kg, s, each currency, and each unit of its own. Each currency is its
own base, so EGP and USD meet only through an exchange rate. Project units come from the Source
Ledger as `symbol -> (factor, unit text it equals, number id)`.
"""

import decimal
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal

from qsone.calc import CONTEXT
from qsone.calc.currencies import CURRENCIES
from qsone.calc.errors import CalcError

Dims = tuple[tuple[str, int], ...]  # sorted base -> power; () is a plain number

_M: Dims = (("m", 1),)
_M2: Dims = (("m", 2),)
_M3: Dims = (("m", 3),)
_KG: Dims = (("kg", 1),)
_S: Dims = (("s", 1),)

# SI only, plus the Arabic symbols (Decision 5). Day, week, month, bag, ton and inch are not here:
# their size depends on the job, so the project defines them.
BUILT_IN: Mapping[str, tuple[str, str, Dims]] = {
    "m": ("m", "1", _M),
    "mm": ("mm", "0.001", _M),
    "cm": ("cm", "0.01", _M),
    "km": ("km", "1000", _M),
    "م": ("m", "1", _M),
    "مم": ("mm", "0.001", _M),
    "سم": ("cm", "0.01", _M),
    "كم": ("km", "1000", _M),
    "م.ط": ("m", "1", _M),  # linear metre
    "ha": ("ha", "10000", _M2),
    "هكتار": ("ha", "10000", _M2),
    "L": ("L", "0.001", _M3),
    "l": ("L", "0.001", _M3),
    "لتر": ("L", "0.001", _M3),
    "g": ("g", "0.001", _KG),
    "kg": ("kg", "1", _KG),
    "t": ("t", "1000", _KG),
    "جم": ("g", "0.001", _KG),
    "غ": ("g", "0.001", _KG),
    "كجم": ("kg", "1", _KG),
    "كغ": ("kg", "1", _KG),
    "طن": ("t", "1000", _KG),
    "s": ("s", "1", _S),
    "min": ("min", "60", _S),
    "h": ("h", "3600", _S),
    "ث": ("s", "1", _S),
    "دقيقة": ("min", "60", _S),
    "ساعة": ("h", "3600", _S),
    "%": ("%", "0.01", ()),
}
_FACTORS = {spelling: Decimal(factor) for spelling, (_, factor, _) in BUILT_IN.items()}
_FOLDED = {spelling.casefold(): spelling for spelling in BUILT_IN}

_DIGITS = "0-9٠-٩۰-۹"  # ASCII, Arabic-Indic, Persian
_TOKEN = r"%|[^\W\d][\w.]*"  # a symbol: % or a letter (or _) then letters, digits, _ and .
_TRAILING = rf"(.+?)([{_DIGITS}]+)"
_POWER = rf"[-−]?[{_DIGITS}]+"
_SUPERSCRIPTS = {"²": 2, "³": 3}
_STOP = "/*·^" + "".join(_SUPERSCRIPTS)
_MAX_POWER = 12


def _exact(compute: Callable[[], Decimal]) -> Decimal:
    """Runs `compute` in a copy of CONTEXT. A result that does not end raises Inexact in the
    caller's context too, so the evaluator (inside `localcontext(CONTEXT)`) sees it."""
    outer = decimal.getcontext()
    with decimal.localcontext(CONTEXT) as ctx:
        value = compute()
    if ctx.flags[decimal.Inexact]:
        outer.flags[decimal.Inexact] = True
    return value


@dataclass(frozen=True)
class Symbol:
    key: str  # what matching uses: "m" for m, M, م; "EGP"; "bag"; "ls" for LS and ls
    spelling: str = field(compare=False)  # as written, for display
    factor: Decimal  # size in base units, exact
    dims: Dims  # bases: "m", "kg", "s", each currency code, each unit of its own
    kind: Literal["built_in", "currency", "defined", "own"]
    number_id: str | None = None  # the ledger number behind a defined unit


def _dims(terms) -> Dims:
    total: dict[str, int] = {}
    for symbol, power in terms:
        for base, n in symbol.dims:
            total[base] = total.get(base, 0) + n * power
    return tuple(sorted((base, n) for base, n in total.items() if n))


def _product(terms) -> Decimal:
    value = Decimal(1)
    for symbol, power in terms:
        value *= symbol.factor**power
    return value


@dataclass(frozen=True)
class Unit:
    terms: tuple[tuple[Symbol, int], ...] = ()  # written order; one entry per key; no zero powers

    def __mul__(self, other: "Unit") -> "Unit":
        merged: dict[str, list] = {}
        for symbol, power in self.terms + other.terms:
            if symbol.key in merged:
                merged[symbol.key][1] += power
            else:
                merged[symbol.key] = [symbol, power]
        return Unit(tuple((symbol, power) for symbol, power in merged.values() if power))

    def __truediv__(self, other: "Unit") -> "Unit":
        return self * other.power(-1)

    def power(self, n: int) -> "Unit":
        return Unit(tuple((symbol, power * n) for symbol, power in self.terms if power * n))

    @property
    def factor(self) -> Decimal:
        return _exact(lambda: _product(self.terms))

    @property
    def dims(self) -> Dims:
        return _dims(self.terms)

    @property
    def plain(self) -> bool:
        """No dimension left: "", "%" and "m3/L" are plain."""
        return not self.dims


class UnitTable:
    """The built-ins, the currencies and the project's own definitions.

    `defined` maps symbol -> (factor, unit text it equals, ledger number id). `currencies` adds the
    codes found in the ledger's currency column to ISO 4217 List One."""

    def __init__(
        self,
        defined: Mapping[str, tuple[Decimal, str, str]] | None = None,
        *,
        currencies: Iterable[str] = (),
    ):
        defined = dict(defined or {})
        self._currencies = CURRENCIES | frozenset(currencies)
        self._names = set(defined)
        self._folded: dict[str, list[str]] = {}
        for symbol in defined:
            self._folded.setdefault(symbol.casefold(), []).append(symbol)
        self._defined: dict[str, Symbol] = {}
        self._uses: dict[str, tuple[str, ...]] = {}  # symbol -> defined symbols its unit names

        pending: dict[str, tuple[Decimal, list[tuple[str, int]], str, tuple[str, ...]]] = {}
        for symbol, (factor, text, number_id) in defined.items():
            self._check_symbol(symbol)
            if not factor > 0:
                raise CalcError("CALC_UNIT_FACTOR", symbol=symbol)
            tokens = self._scan(text)
            if any(self.is_currency(token) for token, _ in tokens):
                raise CalcError("CALC_UNIT_CURRENCY", symbol=symbol)
            uses = tuple(d for d in (self._definition_of(t, text) for t, _ in tokens) if d)
            pending[symbol] = (factor, tokens, number_id, uses)

        while pending:
            ready = [
                s for s, (*_, uses) in pending.items() if all(u in self._defined for u in uses)
            ]
            if not ready:
                raise CalcError("CALC_UNIT_LOOP", symbol=_on_a_loop(pending))
            for symbol in ready:
                factor, tokens, number_id, uses = pending.pop(symbol)
                unit = self._unit(tokens, "")
                if unit.plain:
                    raise CalcError("CALC_UNIT_FACTOR", symbol=symbol)
                size = _exact(lambda f=factor, u=unit: f * u.factor)
                self._defined[symbol] = Symbol(
                    symbol, symbol, size, unit.dims, "defined", number_id
                )
                self._uses[symbol] = uses

    # Reading a unit.

    def parse(self, text: str | None) -> Unit:
        """ "" or None is a plain number. `EGP/m3/day` reads left to right: EGP·m⁻³·day⁻¹."""
        return self._unit(self._scan(text), text)

    def _unit(self, tokens: list[tuple[str, int]], text: str | None) -> Unit:
        unit = Unit()
        for token, power in tokens:
            unit = unit * Unit(((self._lookup(token, text), power),))
        return unit

    def _scan(self, text: str | None) -> list[tuple[str, int]]:
        """The written terms as (symbol text, power), before the symbols are looked up."""
        if text is None or not text.strip():
            return []
        terms: list[tuple[str, int]] = []
        i, n, sign = 0, len(text), 1
        while True:
            while i < n and text[i].isspace():
                i += 1
            j = i
            while j < n and text[j] not in _STOP and not text[j].isspace():
                j += 1
            token, power, split = text[i:j], 1, False
            trailing = re.fullmatch(_TRAILING, token)
            if self._definition_of(token, text) is None and trailing and self._known(trailing[1]):
                token, power, split = trailing[1], int(trailing[2]), True
            if not re.fullmatch(_TOKEN, token):
                raise _unreadable(text)
            i = j
            if i < n and text[i] == "^" and not split:
                written = re.match(_POWER, text[i + 1 :])
                if not written:
                    raise _unreadable(text)
                power = int(written[0].replace("−", "-"))
                i += 1 + written.end()
            elif i < n and text[i] in _SUPERSCRIPTS and not split:
                power = _SUPERSCRIPTS[text[i]]
                i += 1
            if not 1 <= abs(power) <= _MAX_POWER:
                raise _unreadable(text)
            terms.append((token, sign * power))

            spaced = i < n and text[i].isspace()
            while i < n and text[i].isspace():
                i += 1
            if i == n:
                return terms
            if text[i] in "/*·":
                sign = -1 if text[i] == "/" else 1
                i += 1
            elif spaced:
                sign = 1
            else:
                raise _unreadable(text)

    def _lookup(self, token: str, text: str | None) -> Symbol:
        """A project definition (exact), a built-in (exact, then ignoring case), a currency, a
        project definition ignoring case, else a unit of its own."""
        if token in self._defined:
            return replace(self._defined[token], spelling=token)
        built_in = _built_in(token)
        if built_in:
            key, _, dims = BUILT_IN[built_in]
            return Symbol(key, token, _FACTORS[built_in], dims, "built_in")
        if self.is_currency(token):
            return Symbol(token, token, Decimal(1), ((token, 1),), "currency")
        defined = self._definition_of(token, text)
        if defined:
            return replace(self._defined[defined], spelling=token)
        key = token.casefold()
        return Symbol(key, token, Decimal(1), ((key, 1),), "own")

    def _definition_of(self, token: str, text: str | None) -> str | None:
        """The defined symbol `token` names, exactly or ignoring case."""
        if token in self._names:
            return token
        if _built_in(token) or self.is_currency(token):
            return None
        matches = self._folded.get(token.casefold(), [])
        if len(matches) > 1:
            raise _unreadable(text)
        return matches[0] if matches else None

    def _known(self, token: str) -> bool:
        return bool(_built_in(token) or self.is_currency(token) or self._definition_of(token, None))

    def _check_symbol(self, symbol: str) -> None:
        if not re.fullmatch(_TOKEN, symbol):
            raise _unreadable(symbol)
        trailing = re.fullmatch(_TRAILING, symbol)
        for text in (symbol, trailing and trailing[1]):
            if text and _built_in(text):
                raise CalcError("CALC_UNIT_BUILT_IN", symbol=symbol)
            if text and self.is_currency(text):
                raise CalcError("CALC_UNIT_CURRENCY", symbol=symbol)

    # Writing, cancelling and converting.

    def format(self, unit: Unit) -> str:
        """`EGP/m3`, `kg·m`, `m3/day`; a unit with nothing above the line is `s^-1`; "" is plain."""
        above = [self._term(symbol, power) for symbol, power in unit.terms if power > 0]
        below = [self._term(symbol, -power) for symbol, power in unit.terms if power < 0]
        if not above:
            return "·".join(self._term(symbol, power) for symbol, power in unit.terms)
        return "·".join(above) + "".join("/" + term for term in below)

    def _term(self, symbol: Symbol, power: int) -> str:
        if power == 1:
            return symbol.spelling
        digits = f"{symbol.spelling}{power}"
        if (
            power > 0
            and symbol.kind != "own"
            and not re.fullmatch(rf".*[{_DIGITS}]", symbol.spelling)
            and self._definition_of(digits, None) is None
        ):
            return digits
        return f"{symbol.spelling}^{power}"

    def simplify(self, unit: Unit) -> tuple[Decimal, Unit]:
        """Cancels two terms whose dims are exact opposites (`kg` with `/t`, `m3` with `/L`) and
        folds `%`; the value multiplies by the returned factor. The factor is exact, or Inexact is
        raised in the caller's context."""
        rest = list(unit.terms)
        kept: list[tuple[Symbol, int]] = []
        folded: list[tuple[Symbol, int]] = []
        while rest:
            symbol, power = rest.pop(0)
            dims = _dims([(symbol, power)])
            if not dims:
                folded.append((symbol, power))
                continue
            opposite = tuple((base, -n) for base, n in dims)
            match = next((k for k, term in enumerate(rest) if _dims([term]) == opposite), None)
            if match is None:
                kept.append((symbol, power))
            else:
                folded += [(symbol, power), rest.pop(match)]
        return _exact(lambda: _product(folded)), Unit(tuple(kept))

    def ratio(self, frm: Unit, to: Unit) -> Decimal:
        """value_in_to = value_in_frm * ratio. CALC_CURRENCIES_DIFFER when the mismatch is between
        currencies, else CALC_UNITS_DIFFER."""
        if frm.dims != to.dims:
            left = [b for b, n in frm.dims if self.is_currency(b) and (b, n) not in to.dims]
            right = [b for b, n in to.dims if self.is_currency(b) and (b, n) not in frm.dims]
            if left and right:
                raise CalcError("CALC_CURRENCIES_DIFFER", left=left[0], right=right[0])
            raise CalcError("CALC_UNITS_DIFFER", left=self.format(frm), right=self.format(to))
        return _exact(lambda: frm.factor / to.factor)

    # Facts the engine reports.

    def is_currency(self, token: str) -> bool:
        return token in self._currencies

    def own_units(self, unit: Unit) -> list[str]:
        """Spellings of the units of their own in `unit`, for the note."""
        return [symbol.spelling for symbol, _ in unit.terms if symbol.kind == "own"]

    def definitions(self, unit: Unit) -> dict[str, str]:
        """symbol -> number id for every defined unit `unit` uses, through chains too."""
        found: dict[str, str] = {}
        todo = [symbol.key for symbol, _ in unit.terms if symbol.kind == "defined"]
        while todo:
            symbol = todo.pop(0)
            if symbol not in found:
                found[symbol] = self._defined[symbol].number_id
                todo += self._uses[symbol]
        return found


def _built_in(token: str) -> str | None:
    """The built-in spelling `token` names, exactly or ignoring case."""
    return token if token in BUILT_IN else _FOLDED.get(token.casefold())


def _unreadable(text: str | None) -> CalcError:
    return CalcError("CALC_UNIT_UNREADABLE", unit=text)


def _on_a_loop(pending: Mapping[str, tuple]) -> str:
    """A symbol on a definition loop: follow pending uses until one repeats."""
    symbol, seen = next(iter(pending)), []
    while symbol not in seen:
        seen.append(symbol)
        symbol = next(u for u in pending[symbol][-1] if u in pending)
    return symbol
