"""IFC (STEP, ISO 10303-21), read statement by statement: class counts with element names, a piece
per storey (what it holds, spaces included), and a piece per quantity or property value with its
`#id`, the set it belongs to and the elements it describes. Geometry is skipped unparsed. String
escapes \\X2\\…\\X0\\, \\X4\\…\\X0\\, \\X\\HH and \\S\\ are decoded."""

import io
import re
from collections.abc import Iterator
from functools import cache

from qsone.records.arabic import display_text
from qsone.records.extract import Piece

_MAGIC = re.compile(rb"\A(?:\xef\xbb\xbf)?\s*ISO-10303-21;")
_ENTITY = re.compile(r"#(\d+)\s*=\s*([A-Za-z0-9_]+)\s*\((.*)\)\s*\Z", re.S)
_TOKEN = re.compile(
    r"\s*(?:(?P<s>'(?:[^']|'')*')|#(?P<r>\d+)|\.(?P<e>[A-Za-z0-9_]+)\.|(?P<t>[A-Za-z][A-Za-z0-9_]*)\s*\("
    r"|(?P<n>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)|(?P<o>\()|(?P<c>\))|(?P<x>[$*,])"
    r'|(?P<b>"[0-9A-Fa-f]*"))'
)
_ESCAPE = re.compile(
    r"\\X2\\([0-9A-Fa-f]*)\\X0\\|\\X4\\([0-9A-Fa-f]*)\\X0\\|\\X\\([0-9A-Fa-f]{2})|\\S\\(.)"
    r"|\\P[A-Ia-i]\\|\\\\|''",
    re.S,
)
_QUANTITIES = {
    "IFCQUANTITYLENGTH",
    "IFCQUANTITYAREA",
    "IFCQUANTITYVOLUME",
    "IFCQUANTITYCOUNT",
    "IFCQUANTITYWEIGHT",
    "IFCQUANTITYTIME",
    "IFCQUANTITYNUMBER",
}
_RELS = {
    "IFCRELCONTAINEDINSPATIALSTRUCTURE",
    "IFCRELAGGREGATES",
    "IFCRELDEFINESBYPROPERTIES",
}
_SETS = {"IFCPROPERTYSET": 4, "IFCELEMENTQUANTITY": 5}  # where the list of values is
_LISTED_ELEMENTS = 5


def is_ifc(data: bytes) -> bool:
    return _MAGIC.match(data[:1024]) is not None


def read(data: bytes) -> list[Piece]:
    names: dict[int, tuple[str, str]] = {}  # id -> (class, name) for rooted objects
    counts: dict[str, list[str]] = {}  # class -> names, in file order
    contained: dict[int, list[int]] = {}  # spatial structure -> elements
    parts: dict[int, list[int]] = {}  # whole -> parts (a storey's spaces)
    described: dict[int, list[int]] = {}  # property or quantity set -> objects
    sets: dict[int, tuple[str, list[int]]] = {}  # set -> (name, values)
    values: dict[int, tuple[str, str, str]] = {}  # value -> (class, name, value)
    storeys: list[int] = []
    for number, cls, args in _statements(data):
        if cls in _QUANTITIES:
            a = _parse(args)
            values[number] = (cls, _text(_at(a, 0)), _text(_at(a, 3)))
        elif cls == "IFCPROPERTYSINGLEVALUE":
            a = _parse(args)
            values[number] = (cls, _text(_at(a, 0)), _text(_at(a, 2)))
        elif cls in _RELS:
            a = _parse(args)
            if cls == "IFCRELCONTAINEDINSPATIALSTRUCTURE":
                contained.setdefault(_ref(_at(a, 5)), []).extend(_refs(_at(a, 4)))
            elif cls == "IFCRELAGGREGATES":
                parts.setdefault(_ref(_at(a, 4)), []).extend(_refs(_at(a, 5)))
            else:
                described.setdefault(_ref(_at(a, 5)), []).extend(_refs(_at(a, 4)))
        elif cls in _SETS:
            a = _parse(args)
            sets[number] = (_text(_at(a, 2)), _refs(_at(a, _SETS[cls])))
        elif args.lstrip().startswith("'") and not cls.startswith("IFCREL"):
            a = _parse(args)  # a rooted object: GlobalId first, Name third
            name = _text(_at(a, 2))
            names[number] = (cls, name)
            counts.setdefault(cls, []).append(name)
            if cls == "IFCBUILDINGSTOREY":
                storeys.append(number)
    pieces = []
    for cls, found in counts.items():
        shown = _named(found)
        pieces.append(
            Piece(
                {"class": class_name(cls)}, " | ".join([f"{class_name(cls)} ×{len(found)}", *shown])
            )
        )
    for storey in storeys:
        title = names[storey][1] or f"#{storey}"
        held = list(contained.get(storey, []))
        for part in parts.get(storey, []):
            held += [part, *contained.get(part, [])]
        by_class: dict[str, list[str]] = {}
        for n in held:
            if n in names:
                by_class.setdefault(names[n][0], []).append(names[n][1])
        text = [title] + [
            f"{class_name(c)} ×{len(ns)}" + (": " + ", ".join(_named(ns)) if _named(ns) else "")
            for c, ns in by_class.items()
        ]
        pieces.append(Piece({"storey": title}, " | ".join(text)))
    owner = {v: s for s, (_, vs) in sets.items() for v in vs}
    for number, (cls, name, value) in values.items():
        text = [f"{class_name(cls)} {name} = {value}"]
        s = owner.get(number)
        if s is not None:
            text.append(sets[s][0])
            objects = described.get(s, [])
            for n in objects[:_LISTED_ELEMENTS]:
                cls_name, obj = names.get(n, ("", ""))
                text.append(" ".join(x for x in (class_name(cls_name), f"#{n}", obj) if x))
            if len(objects) > _LISTED_ELEMENTS:
                text.append(f"+{len(objects) - _LISTED_ELEMENTS}")
        pieces.append(Piece({"entity": f"#{number}"}, " | ".join(t for t in text if t)))
    return pieces


def _named(names: list[str]) -> list[str]:
    """Distinct names in order, each with ×n when it repeats."""
    seen: dict[str, int] = {}
    for n in names:
        if n:
            seen[n] = seen.get(n, 0) + 1
    return [n if k == 1 else f"{n} ×{k}" for n, k in seen.items()]


def _statements(data: bytes) -> Iterator[tuple[int, str, str]]:
    """(#id, CLASS, raw arguments) for each entity of the DATA section. A statement ends at a ';'
    outside a string, so it may run over lines or share one."""
    buf, quotes = [], 0
    for raw in io.BytesIO(data):
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            line = raw.decode("latin-1")
        segments = line.rstrip("\r\n").split(";")
        for i, segment in enumerate(segments):
            buf.append(segment)
            quotes += segment.count("'")
            if i == len(segments) - 1:
                break
            if quotes % 2:
                buf.append(";")  # inside a string
                continue
            m = _ENTITY.match("".join(buf).strip())
            buf, quotes = [], 0
            if m:
                yield int(m[1]), m[2].upper(), m[3]


def _parse(args: str) -> list:
    """The arguments as nested lists of ("s", text), ("r", id), ("n", "12.5"), ("e", "T"),
    ("t", TYPE, value) and None for $ or *."""
    stack: list[list] = [[]]
    types: list[str | None] = []
    for m in _TOKEN.finditer(args):
        kind = m.lastgroup
        if kind == "s":
            stack[-1].append(("s", decode_string(m[kind][1:-1])))
        elif kind == "r":
            stack[-1].append(("r", int(m[kind])))
        elif kind == "e":
            stack[-1].append(("e", m[kind].upper()))
        elif kind == "n":
            stack[-1].append(("n", m[kind]))
        elif kind == "b":
            stack[-1].append(("n", m[kind]))
        elif kind in ("t", "o"):
            stack.append([])
            types.append(m[kind].upper() if kind == "t" else None)
        elif kind == "c" and len(stack) > 1:
            inner, typed = stack.pop(), types.pop()
            stack[-1].append(("t", typed, inner[0] if inner else None) if typed else inner)
        elif kind == "x" and m[kind] in "$*":
            stack[-1].append(None)
    return stack[0]


def _at(args: list, i: int):
    return args[i] if i < len(args) else None


def _ref(v) -> int:
    return v[1] if isinstance(v, tuple) and v[0] == "r" else -1


def _refs(v) -> list[int]:
    return [x[1] for x in v if isinstance(x, tuple) and x[0] == "r"] if isinstance(v, list) else []


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(t for t in map(_text, v) if t)
    kind = v[0]
    if kind == "s":
        return " ".join(display_text(v[1]).split())
    if kind == "n":
        return v[1][:-1] if v[1].endswith(".") else v[1].replace(".E", "E")
    if kind == "e":
        return {"T": "TRUE", "F": "FALSE", "U": "UNKNOWN"}.get(v[1], v[1])
    if kind == "t":
        return _text(v[2])
    return f"#{v[1]}"


def decode_string(s: str) -> str:
    """A STEP string's body as text: '' is one quote, and the escapes are decoded. A broken
    escape is decoded as far as it goes."""

    def one(m: re.Match) -> str:
        if m[1] is not None:
            hexes = m[1][: len(m[1]) // 4 * 4]
            return bytes.fromhex(hexes).decode("utf-16-be", "replace")
        if m[2] is not None:
            hexes = m[2][: len(m[2]) // 8 * 8]
            return bytes.fromhex(hexes).decode("utf-32-be", "replace")
        if m[3] is not None:
            return chr(int(m[3], 16))
        if m[4] is not None:
            return chr(ord(m[4]) + 128)
        token = m[0]
        return "\\" if token == "\\\\" else "'" if token == "''" else ""

    return _ESCAPE.sub(one, s)


# Class names as IFC writes them (IfcBuildingStorey): the file has them in capitals.
_WORDS = set(
    """
    ACCESSORY ACTUATOR AIR ALARM ANNOTATION APPLIANCE AREA ASPECT ASSEMBLY AUDIO BAR BEAM BEARING
    BOILER BOX BRIDGE BUILDING BUILT BURNER CABLE CARRIER CASE CHILLER CHIMNEY CIVIL COIL COLUMN
    COMMUNICATIONS COMPRESSOR CONDENSER CONTROLLER CONVERSION COOLED COOLER COUNT COURSE COVERING
    CURTAIN DAMPER DEVICE DISCRETE DISTRIBUTION DOOR DUCT EARTHWORKS ELECTRIC ELEMENT ELEMENTED
    ENERGY ENGINE EQUIPMENT EVAPORATIVE EVAPORATOR FACILITY FAN FASTENER FILL FILTER FIRE FITTING
    FIXTURE FLIGHT FLOW FOOTING FURNISHING FURNITURE GENERATOR GEOGRAPHIC GRID GROUP HEAT IN
    INTERCEPTOR JUNCTION KERB LAMP LENGTH LIGHT MECHANICAL MEDICAL MEMBER MESH METER MOTOR MOVING
    NUMBER OPENING OUTLET PART PAVEMENT PILE PIPE PLATE PROJECT PROTECTIVE PROXY PUMP RAIL RAILING
    RAMP REINFORCING ROOF SANITARY SEGMENT SENSOR SHADING SIGN SIGNAL SITE SLAB SOLAR SPACE
    SPATIAL STACK STAIR STANDARD STOREY STRUCTURE SUPPRESSION SWITCHING SYSTEM TANK TENDON
    TERMINAL TIME TRANSFORMER TRANSPORT TREATMENT TUBE TYPE UNIT UNITARY VALVE VIBRATION VIRTUAL
    VISUAL VOLUME WALL WASTE WEIGHT WINDOW ZONE QUANTITY PROPERTY SINGLE VALUE ISOLATOR PROTECTION
    CONNECTION
    """.split()
)


@cache
def class_name(cls: str) -> str:
    """IFCBUILDINGSTOREY -> IfcBuildingStorey, from a list of the words in IFC class names; a
    name it cannot split stays as the file has it."""
    if not cls.startswith("IFC"):
        return cls
    rest = cls[3:]
    best: list[list[str] | None] = [None] * (len(rest) + 1)
    best[0] = []
    for end in range(1, len(rest) + 1):
        for start in range(max(0, end - 15), end):
            if best[start] is not None and rest[start:end] in _WORDS:
                best[end] = [*best[start], rest[start:end]]
                break
    words = best[-1]
    return cls if not words else "Ifc" + "".join(w.capitalize() for w in words)
