"""Local drawing evidence. Geometry yields candidates, never inferred sheet facts.

The subprocess receives decrypted bytes only through stdin. No drawing is written to disk.
PDF callers may supply stored OCR words in pdfplumber's word-box shape.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field, fields
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree


@dataclass
class Drawing:
    format: str = ""
    version: str = ""
    units: int = 0
    summary_info: dict = field(default_factory=dict)
    layers: list[dict] = field(default_factory=list)
    layouts: list[dict] = field(default_factory=list)
    texts: list[dict] = field(default_factory=list)
    inserts: list[dict] = field(default_factory=list)
    dimensions: list[dict] = field(default_factory=list)
    hatches: list[dict] = field(default_factory=list)
    closed: list[dict] = field(default_factory=list)
    xrefs: list[dict] = field(default_factory=list)
    problems: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    note: str | None = None
    repaired: bool = False


@dataclass
class Room:
    name: str
    area_m2: float | None
    outline: list[float]
    source: dict
    candidate: bool = True


@dataclass
class Sheet:
    layout: str = "Model"
    number: str | None = None
    title: str | None = None
    revision: str | None = None
    date: str | None = None
    scale: str | None = None
    discipline_hint: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    rooms: list[Room] = field(default_factory=list)
    texts: list[dict] = field(default_factory=list)
    source: dict[str, dict | list] = field(default_factory=dict)


def find_binary() -> Path | None:
    name = "qsone-drawings" + (".exe" if os.name == "nt" else "")
    explicit = os.environ.get("QSONE_DRAWINGS")
    candidates = [Path(explicit)] if explicit else []
    # Embedded Python lives at core/python.exe on Windows and core/bin/python3 elsewhere.
    executable = Path(sys.executable).resolve()
    candidates += [executable.parent / name, executable.parent.parent / name]
    for parent in Path(__file__).resolve().parents:
        if (parent / "drawings" / "Cargo.toml").is_file():
            candidates.append(parent / "drawings" / "target" / "release" / name)
            break
    return next((p for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


def read_drawing(name: str, data: bytes) -> Drawing:
    binary = find_binary()
    if binary is None:
        return Drawing(note="FILE_DRAWINGS_MISSING")
    if len(data) > 64 * 1024 * 1024:
        return Drawing(note="FILE_DRAWINGS_LIMIT")
    try:
        result = subprocess.run(
            [str(binary), "--name", name],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        if result.returncode not in (0, 2) or len(result.stdout) > 64 * 1024 * 1024:
            return Drawing(note="FILE_UNREADABLE")
        raw = json.loads(result.stdout)
        allowed = {f.name for f in fields(Drawing)} - {"note", "repaired"}
        drawing = Drawing(**{k: v for k, v in raw.items() if k in allowed})
        if not isinstance(drawing.texts, list) or not isinstance(drawing.inserts, list):
            return Drawing(note="FILE_UNREADABLE")
        drawing.repaired = result.returncode == 2
        if drawing.repaired:
            drawing.note = "FILE_DRAWINGS_REPAIRED"
        return drawing
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return Drawing(note="FILE_UNREADABLE")


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DISCIPLINES = {
    "A": "architecture",
    "S": "structure",
    "M": "mechanical",
    "E": "electrical",
    "P": "plumbing",
    "C": "civil",
    "L": "landscape",
}
_LABELS = {
    "number": (
        r"(?:sheet[\s_]*(?:no\.?|number)|drawing[\s_]*(?:no\.?|number)"
        r"|dwg[\s_]*no|رقم\s*اللوح[ةه]|لوح[ةه]\s*رقم)"
    ),
    "title": r"(?:title|sheet[\s_]*title|drawing[\s_]*title|عنوان\s*اللوح[ةه])",
    "revision": r"(?:rev(?:ision)?\.?|المراجع[ةه]|رقم\s*المراجع[ةه]|تعديل)",
    "date": r"(?:date|التاريخ|تاريخ)",
    "scale": r"(?:scale|مقياس\s*الرسم|المقياس)",
}
_SCALE = re.compile(r"(?<!\d)(\d+)\s*[:/]\s*(\d+)(?!\d)")
_SHEET_NO = re.compile(r"(?:[A-Za-z]{1,4}|[\u0621-\u064a]{1,3})\s*[-–]\s*\d+[A-Za-z]?", re.I)


def _source(row: dict) -> dict:
    if "box" in row:
        return {"page": row.get("page", 1), "box": row["box"]}
    return {k: row[k] for k in ("layout", "handle", "x", "y", "block") if k in row}


def _value(key: str, text: str) -> str | None:
    text = text.translate(_DIGITS).strip(" :：=\t\n")
    if key == "scale":
        m = _SCALE.search(text)
        return f"{m[1]}:{m[2]}" if m and int(m[2]) else None
    if key == "number":
        m = _SHEET_NO.fullmatch(text)
        return re.sub(r"\s+", "", m[0]).replace("–", "-") if m else None
    if key == "date":
        return text if re.fullmatch(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", text) else None
    return text or None


def _assign(sheet: Sheet, key: str, value: str | None, row: dict):
    if value and getattr(sheet, key) is None:
        setattr(sheet, key, value)
        sheet.source[key] = _source(row)


def _title(sheet: Sheet, rows: list[dict], inserts: list[dict], bounds: tuple):
    left, bottom, right, top = bounds
    width, height = max(right - left, 1), max(top - bottom, 1)

    # CAD origin is lower left; PDF words are converted to that convention.
    def corner(r):
        return ((right - r.get("x", right)) / width) ** 2 + (
            (r.get("y", bottom) - bottom) / height
        ) ** 2

    attributed = [
        i
        for i in inserts
        if any(
            any(re.fullmatch(pattern, a["tag"], re.I) for pattern in _LABELS.values())
            for a in i.get("attributes", [])
        )
    ]
    if attributed:
        insert = min(attributed, key=corner)
        for a in insert["attributes"]:
            for key, pattern in _LABELS.items():
                if re.fullmatch(pattern, a["tag"], re.I):
                    _assign(sheet, key, _value(key, a["value"]), {**insert, **a})
    corner_rows = [
        r
        for r in rows
        if r.get("x", 0) >= right - width * 0.4 and r.get("y", 0) <= bottom + height * 0.4
    ]
    for row in sorted(corner_rows, key=corner):
        text = row["text"].translate(_DIGITS)
        for key, pattern in _LABELS.items():
            m = re.match(rf"^\s*{pattern}\s*[:：=]?\s*(.+)$", text, re.I)
            if m:
                _assign(sheet, key, _value(key, m[1]), row)
        _assign(sheet, "number", _value("number", text), row)
        for key, pattern in _LABELS.items():
            if not re.fullmatch(pattern, text, re.I):
                continue
            nearby = [
                r
                for r in corner_rows
                if r is not row
                and (
                    # A value on the same baseline, or directly below the label.
                    (
                        abs(r["y"] - row["y"]) <= row.get("height", 3)
                        and 0 < r["x"] - row["x"] < width * 0.2
                    )
                    or (
                        abs(r["x"] - row["x"]) < width * 0.05
                        and 0 < row["y"] - r["y"] < height * 0.05
                    )
                )
                and not any(re.match(p, r["text"], re.I) for p in _LABELS.values())
            ]
            if nearby:
                value_row = min(
                    nearby, key=lambda r: (r["x"] - row["x"]) ** 2 + (r["y"] - row["y"]) ** 2
                )
                _assign(sheet, key, _value(key, value_row["text"]), value_row)

    # An explicit scale anywhere remains evidence, even when a frame was not supplied.
    scales = [(r, _value("scale", r["text"])) for r in rows]
    unique = {s for _, s in scales if s}
    if len(unique) == 1:
        row, value = next((r, s) for r, s in scales if s)
        _assign(sheet, "scale", value, row)
    if sheet.number:
        prefix = sheet.number.split("-")[0].upper()
        discipline = _DISCIPLINES.get(prefix)
        if discipline:
            sheet.discipline_hint = discipline
            sheet.source["discipline_hint"] = sheet.source["number"]


_METRES = {
    1: 0.0254,
    2: 0.3048,
    3: 1609.344,
    4: 0.001,
    5: 0.01,
    6: 1.0,
    7: 1000.0,
    10: 0.9144,
    14: 0.1,
}


def _rooms(sheet: Sheet, outlines: list[dict], units: int):
    polygons = []
    for row in outlines:
        vertices = row.get("vertices", [])
        if len(vertices) < 3:
            continue
        polygon = Polygon(vertices)
        if polygon.is_valid and polygon.area > 0:
            polygons.append((polygon, row))
    tree = STRtree([p for p, _ in polygons])
    for text in sheet.texts:
        name = text["text"].strip()
        if not any(c.isalpha() for c in name) or len(name) > 80 or ":" in name:
            continue
        if _SHEET_NO.fullmatch(name.translate(_DIGITS)) or any(
            re.match(p, name, re.I) for p in _LABELS.values()
        ):
            continue
        point = Point(text["x"], text["y"])
        containing = [polygons[i] for i in tree.query(point, predicate="within")]
        if not containing:
            continue
        polygon, outline = min(containing, key=lambda pair: pair[0].area)
        factor = _METRES.get(units)
        area = outline.get("area", polygon.area) * factor**2 if factor else None
        sheet.rooms.append(
            Room(
                name,
                area,
                list(polygon.bounds),
                {"name": _source(text), "outline": _source(outline), "units": units},
            )
        )


def sheets_from_drawing(drawing: Drawing) -> list[Sheet]:
    names = {
        r.get("layout", "Model")
        for key in ("texts", "inserts", "closed", "dimensions", "hatches")
        for r in getattr(drawing, key)
    } | {"Model"}
    result = []
    for name in sorted(names, key=lambda n: (n != "Model", n)):
        sheet = Sheet(layout=name)
        sheet.texts = [t for t in drawing.texts if t.get("layout", "Model") == name]
        inserts = [i for i in drawing.inserts if i.get("layout", "Model") == name]
        sheet.counts = dict(Counter(i["block"] for i in inserts))
        sheet.source["counts"] = [_source(i) for i in inserts]
        outlines = [o for o in drawing.closed if o.get("layout", "Model") == name]
        points = [(t["x"], t["y"]) for t in sheet.texts + inserts] + [
            tuple(v[:2]) for o in outlines for v in o.get("vertices", [])
        ]
        bounds = (
            (
                min(x for x, y in points),
                min(y for x, y in points),
                max(x for x, y in points),
                max(y for x, y in points),
            )
            if points
            else (0, 0, 1, 1)
        )
        layout = next((layout for layout in drawing.layouts if layout["name"] == name), {})
        paper = layout.get("paper_size", [])
        if len(paper) == 2 and all(paper):
            bounds = (0, 0, *paper)
        _title(sheet, sheet.texts, inserts, bounds)
        if sheet.discipline_hint is None:
            evidence = [
                (r, _DISCIPLINES.get(r.get("layer", "").upper().split("-")[0]))
                for r in sheet.texts + inserts + outlines
            ]
            hints = {hint for _, hint in evidence if hint}
            if len(hints) == 1:
                row, sheet.discipline_hint = next((r, h) for r, h in evidence if h)
                sheet.source["discipline_hint"] = {**_source(row), "layer": row["layer"]}
        _rooms(sheet, outlines, drawing.units)
        result.append(sheet)
    return result


def read_sheets(name: str, data: bytes) -> list[Sheet]:
    drawing = read_drawing(name, data)
    return [] if drawing.note and not drawing.repaired else sheets_from_drawing(drawing)


def read_pdf_sheet(
    words_with_boxes: list[dict],
    page_size: tuple,
    *,
    closed: list[dict] | None = None,
    metres_per_unit: float | None = None,
) -> Sheet:
    """Positioned text/OCR. PDF room areas require vector outlines AND explicit calibration.

    `closed` uses vertices in PDF coordinates. No scale is inferred from page pixels.
    """
    width, height = page_size
    rows = []
    for word in words_with_boxes:
        box = [word[k] for k in ("x0", "top", "x1", "bottom")]
        rows.append(
            {
                "text": word["text"],
                "x": box[0],
                "y": height - box[3],
                "box": box,
                "page": word.get("page", 1),
            }
        )
    # Join words sharing a baseline, retaining the union box for the source.
    lines = []
    for row in sorted(rows, key=lambda r: (r["box"][1], r["x"])):
        if (
            lines
            and abs(lines[-1]["box"][1] - row["box"][1]) <= 2
            and lines[-1]["page"] == row["page"]
        ):
            line = lines[-1]
            if re.search(r"[\u0621-\u064a]", line["text"] + row["text"]):
                line["text"] = row["text"] + " " + line["text"]
            else:
                line["text"] += " " + row["text"]
            line["box"] = [
                min(line["box"][0], row["box"][0]),
                min(line["box"][1], row["box"][1]),
                max(line["box"][2], row["box"][2]),
                max(line["box"][3], row["box"][3]),
            ]
        else:
            lines.append(dict(row))
    sheet = Sheet(layout="PDF", texts=lines)
    _title(sheet, lines, [], (0, 0, width, height))
    if closed:
        outlines = []
        for vector in closed:
            vertices = vector.get("vertices", [])
            if len(vertices) < 3:
                continue
            xs, ys = zip(*vertices, strict=True)
            outlines.append(
                {
                    **vector,
                    "page": vector.get("page", 1),
                    "box": vector.get("box", [min(xs), min(ys), max(xs), max(ys)]),
                    "vertices": [[x, height - y] for x, y in vertices],
                }
            )
        _rooms(sheet, outlines, 0)
        if metres_per_unit is not None and metres_per_unit > 0:
            for room in sheet.rooms:
                outline = next(o for o in outlines if _source(o) == room.source["outline"])
                room.area_m2 = Polygon(outline["vertices"]).area * metres_per_unit**2
                room.source["calibration"] = metres_per_unit
    return sheet
