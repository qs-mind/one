"""The formula language: text in, a tree out. The tree is data; nothing here runs it.

Excel-like: `+ - * / ^`, postfix `%`, one comparison `< <= > >= = !=`, brackets, the functions in
`FUNCTIONS` and the constant `pi`. Also read: `× · ÷ −  ≤ ≥ ≠ ==`, `،` as a comma, `٫` as a decimal
point, and Arabic-Indic and Persian digits. Quoted text stands only as `to()`'s unit and
`round()`'s mode. Written by hand with depth and node counters, and every walk over a tree uses
an explicit stack, so no formula can reach Python's recursion limit.
"""

from dataclasses import dataclass, replace
from typing import Literal

from qsone import copy
from qsone.calc.errors import CalcError


@dataclass(frozen=True)
class Node:
    start: int  # character span in the formula, for step text and errors
    end: int


@dataclass(frozen=True)
class Num(Node):
    text: str  # exact digits, already mapped to 0-9 and "."


@dataclass(frozen=True)
class Name(Node):
    name: str


@dataclass(frozen=True)
class Text(Node):
    value: str  # only as to()'s unit or round()'s mode


@dataclass(frozen=True)
class Unary(Node):
    op: Literal["-", "+"]
    arg: Node


@dataclass(frozen=True)
class Percent(Node):
    arg: Node  # postfix %


@dataclass(frozen=True)
class Binary(Node):
    op: Literal["+", "-", "*", "/", "^", "<", "<=", ">", ">=", "=", "!="]
    left: Node
    right: Node


@dataclass(frozen=True)
class Call(Node):
    fn: str
    args: tuple[Node, ...]


# Function names and `pi` are the same as spec.RESERVED_NAMES (a test keeps them equal).
FUNCTIONS = {
    "sum": "sum(list)",
    "count": "count(list)",
    "avg": "avg(list)",
    "min": "min(a, b, …) or min(list)",
    "max": "max(a, b, …) or max(list)",
    "round": 'round(x, places[, "half_up"|"half_even"|"up"|"down"])',
    "abs": "abs(x)",
    "sqrt": "sqrt(x)",
    "to": 'to(x, "unit")',
    "if": "if(condition, then, else)",
}
CONSTANTS = {"pi"}
MAX_CHARS, MAX_DEPTH, MAX_NODES = 4000, 50, 2000
MAX_TEXT = 64

# The same usage lines for the Arabic text, so it holds no English words.
USAGE_AR = {
    "sum": "sum(قايمة)",
    "count": "count(قايمة)",
    "avg": "avg(قايمة)",
    "min": "min(أ، ب، …) أو min(قايمة)",
    "max": "max(أ، ب، …) أو max(قايمة)",
    "round": 'round(س، عدد الخانات[، "half_up"|"half_even"|"up"|"down"])',
    "abs": "abs(س)",
    "sqrt": "sqrt(س)",
    "to": 'to(س، "الوحدة")',
    "if": "if(شرط، لو صح، لو غلط)",
}
# Argument counts (fewest, most; None is no limit) and the one place a quoted text stands.
_ARITY = {
    "sum": (1, 1),
    "count": (1, 1),
    "avg": (1, 1),
    "min": (1, None),
    "max": (1, None),
    "round": (2, 3),
    "abs": (1, 1),
    "sqrt": (1, 1),
    "to": (2, 2),
    "if": (3, 3),
}
_TEXT_AT = {"to": 1, "round": 2}
_ROUND_MODES = {"half_up", "half_even", "up", "down"}

_DIGITS = {c: c for c in "0123456789"}
_DIGITS |= {chr(0x0660 + d): str(d) for d in range(10)}  # Arabic-Indic ٠-٩
_DIGITS |= {chr(0x06F0 + d): str(d) for d in range(10)}  # Persian ۰-۹
_POINTS = {".", "٫"}
_PAIRS = {"<=": "<=", ">=": ">=", "!=": "!=", "==": "="}
_SINGLE = {"+": "+", "-": "-", "−": "-", "*": "*", "×": "*", "·": "*", "/": "/", "÷": "/"}
_SINGLE |= {"^": "^", "%": "%", "(": "(", ")": ")", ",": ",", "،": ","}
_SINGLE |= {"<": "<", ">": ">", "=": "=", "≤": "<=", "≥": ">=", "≠": "!="}
_COMPARISONS = {"<", "<=", ">", ">=", "=", "!="}

# What One expected, in each language, for CALC_UNEXPECTED.
_VALUE = {"en": "a number, a name or an opening bracket (", "ar": "رقم أو اسم أو قوس فتح ("}
_AFTER_VALUE = {
    "en": "an operator such as + or *, or the end of the formula",
    "ar": "علامة حساب زي + أو *، أو نهاية المعادلة",
}
_IN_BRACKETS = {"en": "an operator or a closing bracket )", "ar": "علامة حساب أو قوس قفل )"}
_IN_CALL = {
    "en": "an operator, a comma or a closing bracket )",
    "ar": "علامة حساب أو فاصلة أو قوس قفل )",
}
_TEXT_HERE = {
    "en": "a number, a name or a bracket; quoted text stands only as to()'s unit "
    "and round()'s mode",
    "ar": "رقم أو اسم أو قوس؛ النص بين علامتي تنصيص مكانه بس وحدة to وطريقة التقريب في round",
}
_SEPARATOR = {
    "en": "an operator after the number; write 1000, not 1,000",
    "ar": "علامة حساب بعد الرقم؛ اكتب 1000 مش 1,000",
}
_EXPONENT = {
    "en": "an operator after the number; write numbers in full (1000, not 1e3) "
    "and give units through the inputs",
    "ar": "علامة حساب بعد الرقم؛ اكتب الرقم كامل (1000 مش 1e3) والوحدة تيجي من المدخلات",
}
_CLOSE_QUOTE = {"en": "a quote mark that closes the text", "ar": "علامة تنصيص تقفل النص"}
_SHORT_TEXT = {
    "en": f"quoted text of at most {MAX_TEXT} characters",
    "ar": f"نص بين علامتي تنصيص في حدود {MAX_TEXT} حرف",
}
_END = {"en": "the end of the formula", "ar": "نهاية المعادلة"}


def parse(text: str) -> Node:
    """The tree of `text`. CalcError: CALC_UNEXPECTED (at, found, expected), CALC_TOO_LONG,
    CALC_TOO_DEEP, CALC_UNKNOWN_FUNCTION, CALC_USAGE; each with `at`, field "formula"."""
    if len(text) > MAX_CHARS:
        raise _refuse("CALC_TOO_LONG", MAX_CHARS)
    parser = _Parser(text)
    tree = parser.expression()
    if parser.tok.kind != "end":
        raise parser.unexpected(_AFTER_VALUE)
    return tree


def names(tree: Node) -> set[str]:
    """Input names used, without pi."""
    return {n.name for n in walk(tree) if isinstance(n, Name) and n.name not in CONSTANTS}


def show(tree: Node) -> str:
    """Fully bracketed, for tests and the trace: `(a + (b * c))`, `(round x 2 "up")`."""
    parts: list[str] = []
    for node in walk(tree):
        match node:
            case Num():
                parts.append(node.text)
            case Name():
                parts.append(node.name)
            case Text():
                parts.append(f'"{node.value}"')
            case Unary():
                parts.append(f"({node.op}{parts.pop()})")
            case Percent():
                parts.append(f"({parts.pop()} %)")
            case Binary():
                right, left = parts.pop(), parts.pop()
                parts.append(f"({left} {node.op} {right})")
            case Call():
                args = parts[len(parts) - len(node.args) :]
                del parts[len(parts) - len(node.args) :]
                parts.append("(" + " ".join([node.fn, *args]) + ")")
    return parts[0]


def walk(tree: Node) -> list[Node]:
    """Every node, children before their parent, left to right; an explicit stack, no recursion
    (a chain like `a + a + … + a` is as deep as it has nodes)."""
    out: list[Node] = []
    stack: list[tuple[Node, bool]] = [(tree, False)]
    while stack:
        node, ready = stack.pop()
        if ready:
            out.append(node)
            continue
        stack.append((node, True))
        stack.extend((child, False) for child in reversed(_children(node)))
    return out


def _children(node: Node) -> tuple[Node, ...]:
    match node:
        case Unary() | Percent():
            return (node.arg,)
        case Binary():
            return (node.left, node.right)
        case Call():
            return node.args
    return ()


def _refuse(key: str, at: int, **values) -> CalcError:
    """A refusal of the formula. A value given as {en, ar} fills each text in its own language.
    `at` counts from 0 in `values`; the text shows at + 1, the character a person counts."""

    def said_in(lang: str) -> dict:
        return {k: v[lang] if isinstance(v, dict) else v for k, v in values.items()}

    error = CalcError(key, field="formula", at=at + 1, **said_in("en"))
    error.text = {
        lang: text.format(field="formula", at=at + 1, **said_in(lang))
        for lang, text in vars(copy)[key].items()
    }
    error.values = {"at": at, **values}
    return error


@dataclass(frozen=True)
class _Token:
    kind: Literal["num", "name", "text", "op", "bad", "end"]
    value: str
    start: int
    end: int
    expected: dict | None = None  # a bad token can say what it needed


def _name_start(ch: str) -> bool:  # [^\W\d], as spec.Name
    return (ch.isalnum() or ch == "_") and not ch.isdecimal()


def _name_part(ch: str) -> bool:  # \w
    return ch.isalnum() or ch == "_"


def _tokens(text: str) -> list[_Token]:
    """The tokens, ending with "end". The first character that cannot be read becomes a "bad"
    token and ends the list, so the parser refuses it where it stands, saying what it expected."""
    out: list[_Token] = []
    i, n = 0, len(text)
    while i < n:
        ch, start = text[i], i
        if ch.isspace():
            i += 1
        elif ch in _DIGITS:
            digits = []
            while i < n and text[i] in _DIGITS:
                digits.append(_DIGITS[text[i]])
                i += 1
            if i + 1 < n and text[i] in _POINTS and text[i + 1] in _DIGITS:
                digits.append(".")
                i += 1
                while i < n and text[i] in _DIGITS:
                    digits.append(_DIGITS[text[i]])
                    i += 1
            out.append(_Token("num", "".join(digits), start, i))
        elif _name_start(ch):
            i += 1
            while i < n and _name_part(text[i]):
                i += 1
            out.append(_Token("name", text[start:i], start, i))
        elif ch in "\"'":
            close = text.find(ch, i + 1)
            if close < 0:
                out.append(_Token("bad", ch, start, start + 1, _CLOSE_QUOTE))
                break
            if close - i - 1 > MAX_TEXT:
                out.append(_Token("bad", ch, start, start + 1, _SHORT_TEXT))
                break
            out.append(_Token("text", text[i + 1 : close], start, close + 1))
            i = close + 1
        elif text[i : i + 2] in _PAIRS:
            out.append(_Token("op", _PAIRS[text[i : i + 2]], start, i + 2))
            i += 2
        elif ch in _SINGLE:
            out.append(_Token("op", _SINGLE[ch], start, i + 1))
            i += 1
        else:
            out.append(_Token("bad", ch, start, start + 1))
            break
    out.append(_Token("end", "", n, n))
    return out


class _Parser:
    """Precedence climbs: comparison < `+ -` < `* /` < unary `- +` < `^` (right) < postfix `%`."""

    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokens(text)
        self.i = 0
        self.depth = 0
        self.count = 0

    @property
    def tok(self) -> _Token:
        return self.tokens[self.i]

    def take(self) -> _Token:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def is_op(self, *ops: str) -> bool:
        return self.tok.kind == "op" and self.tok.value in ops

    def node(self, cls: type[Node], start: int, end: int, *fields) -> Node:
        self.count += 1
        if self.count > MAX_NODES:
            raise _refuse("CALC_TOO_DEEP", start)
        return cls(start, end, *fields)

    def enter(self, token: _Token) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise _refuse("CALC_TOO_DEEP", token.start)

    def unexpected(self, expected: dict) -> CalcError:
        token = self.tok
        found = _END if token.kind == "end" else self.text[token.start : token.end]
        expected = token.expected or expected
        before = self.tokens[self.i - 1] if self.i else None
        if before is not None and before.kind == "num" and before.end == token.start:
            after = self.tokens[self.i + 1] if token.kind != "end" else None
            if token.kind == "name":
                expected = _EXPONENT
            elif self.is_op(",") and after.kind == "num" and after.start == token.end:
                expected = _SEPARATOR
        return _refuse("CALC_UNEXPECTED", token.start, found=found, expected=expected)

    def expression(self) -> Node:
        left = self.additive()
        if self.tok.kind == "op" and self.tok.value in _COMPARISONS:
            op = self.take().value
            right = self.additive()
            left = self.node(Binary, left.start, right.end, op, left, right)
        return left

    def additive(self) -> Node:
        left = self.term()
        while self.is_op("+", "-"):
            op = self.take().value
            right = self.term()
            left = self.node(Binary, left.start, right.end, op, left, right)
        return left

    def term(self) -> Node:
        left = self.unary()
        while self.is_op("*", "/"):
            op = self.take().value
            right = self.unary()
            left = self.node(Binary, left.start, right.end, op, left, right)
        return left

    def signs(self) -> list[_Token]:
        signs = []
        while self.is_op("+", "-"):
            signs.append(self.take())
        return signs

    def signed(self, signs: list[_Token], tree: Node) -> Node:
        for sign in reversed(signs):
            tree = self.node(Unary, sign.start, tree.end, sign.value, tree)
        return tree

    def unary(self) -> Node:
        signs = self.signs()
        return self.signed(signs, self.power())

    def power(self) -> Node:
        """`a ^ -b ^ c` is `a ^ (-(b ^ c))`, folded from the right without recursion."""
        chain = [([], self.postfix())]
        while self.is_op("^"):
            self.take()
            signs = self.signs()
            chain.append((signs, self.postfix()))
        signs, tree = chain.pop()
        tree = self.signed(signs, tree)
        while chain:
            signs, base = chain.pop()
            tree = self.signed(signs, self.node(Binary, base.start, tree.end, "^", base, tree))
        return tree

    def postfix(self) -> Node:
        tree = self.primary()
        while self.is_op("%"):
            sign = self.take()
            tree = self.node(Percent, tree.start, sign.end, tree)
        return tree

    def primary(self) -> Node:
        token = self.tok
        if token.kind == "num":
            self.take()
            return self.node(Num, token.start, token.end, token.value)
        if token.kind == "name":
            self.take()
            if self.is_op("("):
                return self.call(token)
            if token.value in FUNCTIONS:
                raise self.usage(token)
            return self.node(Name, token.start, token.end, token.value)
        if self.is_op("("):
            self.take()
            self.enter(token)
            inner = self.expression()
            if not self.is_op(")"):
                raise self.unexpected(_IN_BRACKETS)
            close = self.take()
            self.depth -= 1
            return replace(inner, start=token.start, end=close.end)
        raise self.unexpected(_TEXT_HERE if token.kind == "text" else _VALUE)

    def call(self, name: _Token) -> Node:
        if name.value not in FUNCTIONS:
            raise _refuse("CALC_UNKNOWN_FUNCTION", name.start, name=name.value)
        self.take()  # (
        self.enter(name)
        args: list[Node] = []
        if not self.is_op(")"):
            args.append(self.argument())
            while not self.is_op(")"):
                if not self.is_op(","):
                    raise self.unexpected(_IN_CALL)
                self.take()
                args.append(self.argument())
        close = self.take()
        self.depth -= 1
        if not self.fits(name.value, args):
            raise self.usage(name)
        return self.node(Call, name.start, close.end, name.value, tuple(args))

    def argument(self) -> Node:
        """A quoted text standing alone as an argument, else an expression."""
        token = self.tok
        if token.kind == "text":
            after = self.tokens[self.i + 1]
            if after.kind == "op" and after.value in (",", ")"):
                self.take()
                return self.node(Text, token.start, token.end, token.value)
        return self.expression()

    @staticmethod
    def fits(fn: str, args: list[Node]) -> bool:
        fewest, most = _ARITY[fn]
        if len(args) < fewest or (most is not None and len(args) > most):
            return False
        for place, arg in enumerate(args):
            if isinstance(arg, Text) != (_TEXT_AT.get(fn) == place):
                return False
            if isinstance(arg, Text) and fn == "round" and arg.value not in _ROUND_MODES:
                return False
        return True

    @staticmethod
    def usage(name: _Token) -> CalcError:
        usage = {"en": FUNCTIONS[name.value], "ar": USAGE_AR[name.value]}
        return _refuse("CALC_USAGE", name.start, fn=name.value, usage=usage)
