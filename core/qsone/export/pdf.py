"""Sheets, Documents and Review reports to PDF (Typst), in memory. The content goes to fixed
templates only as JSON in `sys_inputs`, so text from a tender file can never become Typst code.
Only our own OFL fonts are used (Kumbh Sans, Zain); system fonts are ignored."""

import json
from importlib.resources import files

import typst

from qsone import copy
from qsone.deliverables.store import ref_key
from qsone.export import (
    DASH,
    LABELS,
    check_draft,
    format_decimal,
    isolate,
    layout,
    marks,
    places,
    say,
    shown_numbers,
    source_line,
    state,
    who,
)

_TEMPLATES = files("qsone.export") / "typst"
_FONTS = files("qsone") / "fonts"
_INLINE = {"num", "cell"}


def _compile(template: str, payload: dict) -> bytes:
    return typst.compile(
        str(_TEMPLATES / template),
        font_paths=[str(_FONTS)],
        ignore_system_fonts=True,
        sys_inputs={"data": json.dumps(payload, ensure_ascii=False)},
    )


def _page(language: str, title: str, page_marks: list[str], page_state: str) -> dict:
    """What every page needs: direction, fonts, title, marks, footer."""
    return {
        "dir": "rtl" if language == "ar" else "ltr",
        "lang": language,
        "fonts": ["Zain", "Kumbh Sans"] if language == "ar" else ["Kumbh Sans", "Zain"],
        "title": title,
        "marks": page_marks,
        "state": page_state,
        "page_of": LABELS["page_of"][language],  # Typst fills {x} and {y}
    }


def to_pdf(view: dict) -> bytes:
    """A Sheet view (A4 landscape) or a Document view (A4) as a PDF."""
    if view.get("kind") not in ("sheet", "document"):
        raise ValueError("only a Sheet or a Document exports to PDF")
    check_draft(view)
    head = _page(view["language"], view["title"], marks(view), state(view))
    if view["kind"] == "sheet":
        return _compile("sheet.typ", head | _sheet(view))
    return _compile("document.typ", head | {"blocks": _Blocks(view).all()})


# Sheets.


def _sheet(view: dict) -> dict:
    language = view["language"]
    numbers = {c["key"] for c in view["columns"] if c["kind"] != "text"}

    def text(shown: dict) -> str:
        cell = shown.get("number")
        return (
            shown["text"] if cell is None else format_decimal(cell["value"], places(cell), language)
        )

    rows = []
    for row in layout(view):
        cells, at = [], 0
        for shown in row["cells"]:
            column = view["columns"][at]
            num = column["key"] in numbers and shown["span"] == 1
            cells.append({"span": shown["span"], "t": text(shown), "num": num})
            at += shown["span"]
        rows.append({"kind": row["kind"], "cells": cells})
    sources = []
    for where, column, cell in shown_numbers(view):
        line = source_line(view, cell)
        value = format_decimal(cell["value"], places(cell), language)
        parts = [
            where,
            column,
            f"{value} {line['unit']}".strip(),
            line["title"],
            line["file"],
            line["place"],
            line["link"],
            line["dated"],
            line["kind"],
        ]
        sources.append(" · ".join(isolate(p) for p in parts if p))
    return {
        "columns": [
            {"label": c["label"][language], "width": c.get("width") or 90} for c in view["columns"]
        ],
        "rows": rows,
        "sources_title": say("sources", language),
        "sources": sources,
    }


# Documents: the Plate tree, flattened to what document.typ draws.


class _Blocks:
    """Blocks as {"k": "h1"|"h2"|"h3"|"p"|"quote", "runs"} | {"k": "list", "ordered", "items"} |
    {"k": "table", "width", "rows"}; runs as {"t", "b", "i"} or a reference {"t", "note"}."""

    def __init__(self, view: dict):
        self.view = view
        self.language = view["language"]

    def all(self) -> list[dict]:
        return [b for block in self.view["blocks"] for b in self.block(block["node"])]

    def runs(self, children: list[dict]) -> list[dict]:
        out = []
        for child in children:
            if child.get("type") in _INLINE:
                out.append(self.ref(child))
            elif "type" not in child:
                out.append(
                    {
                        "t": child.get("text", ""),
                        "b": bool(child.get("bold")),
                        "i": bool(child.get("italic")),
                    }
                )
            else:
                out += self.runs(child.get("children", []))
        return out

    def ref(self, node: dict) -> dict:
        cell = self.view["refs"].get(ref_key(node))
        if cell is None:
            return {"t": DASH}
        line = source_line(self.view, cell)
        parts = (line["title"], line["file"], line["place"], line["dated"], line["link"])
        note = " — ".join(isolate(p) for p in parts if p)
        return {"t": format_decimal(cell["value"], places(cell), self.language), "note": note}

    def block(self, node: dict) -> list[dict]:
        kind = node.get("type")
        children = node.get("children", [])
        if kind in ("ul", "ol"):
            items = [self.item(li) for li in children]
            return [{"k": "list", "ordered": kind == "ol", "items": items}]
        if kind == "table":
            rows = [[self.cell(td) for td in tr.get("children", [])] for tr in children]
            width = max((len(r) for r in rows), default=0)
            if not width:
                return []
            return [
                {"k": "table", "width": width, "rows": [r + [[]] * (width - len(r)) for r in rows]}
            ]
        if all(c.get("type") in _INLINE or "type" not in c for c in children):
            k = {"h1": "h1", "h2": "h2", "h3": "h3", "blockquote": "quote"}.get(kind, "p")
            return [{"k": k, "runs": self.runs(children)}]
        return [b for child in children for b in self.block(child)]

    def item(self, li: dict) -> list[dict]:
        children = li.get("children", [])
        if all(c.get("type") in _INLINE or "type" not in c for c in children):
            return [{"k": "p", "runs": self.runs(children)}]
        return [b for child in children for b in self.block(child)]

    cell = item  # a table cell holds runs or blocks, as a list item does


# The Review report. Only this function reads the report's keys (Task 4's
# `review.review_report`), so a renamed key changes this one place.


def _when(at: str | None) -> str:
    """An audit time as a reader sees it, isolated so it reads in order inside Arabic."""
    return isolate(f"{at[:16].replace('T', ' ')} UTC") if at else ""


def _review(report: dict, language: str) -> dict:
    def line(*parts) -> str:
        return " · ".join(isolate(str(p)) for p in parts if p)

    deliverable, revision = report["deliverable"], report["revision"]
    signed = report.get("signed_off")
    lines = [
        say("rev", language, n=revision["no"]),
        say(
            "issued",
            language,
            at=_when(revision.get("issued_at")),
            by=isolate(who(revision.get("issued_by"), language)),
        ),
        say("signed_by", language, at=_when(signed["at"]), by=isolate(who(signed["by"], language)))
        if signed
        else copy.EXPORT_DRAFT_MARK[language],
    ]
    checks = [
        {
            "head": line(
                say("code", language, code=c["code"]),
                say("version", language, n=c["version_n"]),
                c.get("checker"),
                say("same_provider" if c.get("same_provider") else "other_provider", language),
                _when(c.get("at")),
            ),
            "summary": c.get("summary") or "",
        }
        for c in report.get("checks", [])
    ]
    if not checks:
        checks = [{"head": say("none", language), "summary": ""}]
    threads = [
        {
            "head": line(
                say("review" if t.get("kind") == "review" else "note", language),
                say("code", language, code=t["code"]) if t.get("code") else None,
                say("closed" if t.get("status") == "closed" else "open", language),
                who(t.get("author"), language),
                _when(t.get("created_at")),
            ),
            "body": t.get("body", ""),
            "replies": [
                {
                    "head": line(who(r.get("author"), language), _when(r.get("created_at"))),
                    "body": r.get("body", ""),
                }
                for r in t.get("replies", [])
            ],
        }
        for t in report.get("threads", [])
    ]
    counts = report.get("changes", {})
    sample = [copy.SAMPLE_DATA[language]] if report.get("sample") else []
    page_marks = ([] if signed else [copy.EXPORT_DRAFT_MARK[language]]) + sample
    title = f"{say('report', language)} — {deliverable['title']}"
    return _page(language, title, page_marks, lines[0]) | {
        "lines": lines,
        "checks_title": say("checks", language),
        "checks": checks,
        "changes": say(
            "changes",
            language,
            accepted=counts.get("accepted", 0),
            rejected=counts.get("rejected", 0),
        ),
        "comments_title": say("comments", language),
        "threads": threads,
    }


def review_pdf(report: dict, language: str) -> bytes:
    """A Review report (`review.review_report`) as a PDF in `language`."""
    return _compile("review.typ", _review(report, language))
