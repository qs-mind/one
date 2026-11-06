"""Tender packs. Originals, overlays and outputs stay in memory. Ranges are one-based,
inclusive; stamps address final output pages. Overlay steps run after all page assembly."""

import json
import shutil
import subprocess
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from qsone import copy
from qsone.export.pdf import _compile
from qsone.records import office
from qsone.records.files import file_info, read_original
from qsone.records.project import RecordsError


def refusal(field="steps"):
    return RecordsError(copy.PACK_INVALID, status=422, field=field)


def _parsed(data):
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise RecordsError(copy.PACK_LOCKED, status=422, field="file")
    len(reader.pages)  # Force lazy page-tree errors before accepting the original.
    return reader


def _reader(data):
    try:
        return _parsed(data)
    except (PdfReadError, ValueError):
        # qpdf requires a seekable input. Linux's anonymous memory fd avoids a plaintext file.
        # Elsewhere damaged PDFs are refused; never fall back to a temporary decrypted file.
        import os

        if not shutil.which("qpdf") or not hasattr(os, "memfd_create"):
            raise refusal("file") from None
        fd = os.memfd_create("one-pack")
        try:
            with os.fdopen(os.dup(fd), "wb") as stream:
                stream.write(data)
            os.lseek(fd, 0, os.SEEK_SET)
            result = subprocess.run(
                ["qpdf", f"/proc/self/fd/{fd}", "-"],
                pass_fds=(fd,),
                capture_output=True,
                timeout=30,
            )
            if result.returncode not in (0, 3):
                raise refusal("file")
            return _parsed(result.stdout)
        except (OSError, subprocess.TimeoutExpired, PdfReadError, ValueError):
            raise refusal("file") from None
        finally:
            os.close(fd)


def _pair(value):
    return (
        isinstance(value, dict)
        and set(value) == {"en", "ar"}
        and all(isinstance(v, str) and 0 < len(v.strip()) <= 4000 for v in value.values())
    )


def validate_steps(steps, read):
    """Validate against actual encrypted originals, not reported page counts."""
    if not isinstance(steps, list) or len(steps) > 500:
        raise refusal()
    readers, total = {}, 0
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise refusal()
        kind = step.get("kind")
        allowed = {
            "file": {"file_id", "ranges"},
            "cover": {"text"},
            "divider": {"text"},
            "stamp": {"text", "pages", "position"},
            "page_numbers": set(),
            "seal": set(),
        }
        if (
            not isinstance(kind, str)
            or kind not in allowed
            or set(step) - allowed[kind] - {"kind", "title"}
        ):
            raise refusal()
        if "title" in step and not _pair(step["title"]):
            raise refusal()
        if kind in ("cover", "divider", "stamp") and not _pair(step.get("text")):
            raise refusal()
        if kind == "file":
            fid = step.get("file_id")
            if not isinstance(fid, str) or not fid:
                raise refusal("file_id")
            if fid not in readers:
                try:
                    readers[fid] = _reader(read(fid))
                except (KeyError, ValueError):
                    raise refusal("file_id") from None
            ranges = step.get("ranges")
            if not isinstance(ranges, list) or not ranges:
                raise refusal("ranges")
            for r in ranges:
                if (
                    not isinstance(r, list)
                    or len(r) != 2
                    or any(type(n) is not int for n in r)
                    or not 1 <= r[0] <= r[1] <= len(readers[fid].pages)
                ):
                    raise refusal("ranges")
                total += r[1] - r[0] + 1
        if kind in ("cover", "divider"):
            total += 1
        if kind == "seal" and i != len(steps) - 1:
            raise refusal("seal")
    if total > 2000:
        raise refusal()
    for step in steps:
        if step["kind"] == "stamp":
            pages = step.get("pages")
            if (
                not isinstance(pages, list)
                or not pages
                or any(type(p) is not int or not 1 <= p <= total for p in pages)
                or step.get("position") not in ("top", "center", "bottom")
            ):
                raise refusal("pages")
    if sum(s["kind"] == "page_numbers" for s in steps) > 1:
        raise refusal()
    return readers


def _draw(text, language, width=595.28, height=841.89, position="center", large=False):
    data = {
        "text": text,
        "lang": language,
        "width": width,
        "height": height,
        "position": position,
        "large": large,
    }
    pdf = _reader(_compile("pack.typ", data))
    if len(pdf.pages) != 1:
        raise refusal("text")
    return pdf.pages[0]


def build(steps, read, language, *, apply_seal=True):
    readers = validate_steps(steps, read)
    writer = PdfWriter()
    for step in steps:
        start = len(writer.pages)
        kind = step["kind"]
        if kind == "file":
            for first, last in step["ranges"]:
                for n in range(first - 1, last):
                    reader = readers[step["file_id"]]
                    # A fresh page dictionary alone still shares its content stream in
                    # pypdf. Reset source translations so overlays cannot mutate siblings.
                    writer.reset_translation(reader)
                    writer.add_page(reader.pages[n].clone(writer, force_duplicate=True))
        elif kind in ("cover", "divider"):
            writer.add_page(_draw(step["text"][language], language, large=True))
        if "title" in step and len(writer.pages) > start:
            writer.add_outline_item(step["title"][language], start)
    total = len(writer.pages)
    if not total:
        raise refusal()
    for n, page in enumerate(writer.pages, 1):
        page.transfer_rotation_to_content()
        for step in steps:
            if step["kind"] == "stamp" and n in step["pages"]:
                text, position = step["text"][language], step["position"]
            elif step["kind"] == "page_numbers":
                text = copy.PACK_PAGE[language].format(n=n, total=total)
                position = "bottom"
            else:
                continue
            overlay = _draw(
                text, language, float(page.cropbox.width), float(page.cropbox.height), position
            )
            page.merge_translated_page(
                overlay, float(page.cropbox.left), float(page.cropbox.bottom)
            )
    out = BytesIO()
    writer.write(out)
    data = out.getvalue()
    if apply_seal and any(s["kind"] == "seal" for s in steps):
        from qsone.deliverables.pack_seal import seal

        data = seal(data)
    return data


def _source_pdf(rec, file_id):
    info = file_info(rec, file_id)
    if info is None:
        raise RecordsError(copy.FILE_NOT_FOUND, status=404, field="file_id")
    data = read_original(rec, file_id)
    # Use the kept filename, not extraction status: an Office original can be stored
    # unread until LibreOffice becomes available. Converted bytes are never persisted.
    extension = info.name.rsplit(".", 1)[-1].lower()
    if extension in {"doc", "docx", "xls", "xlsx", "odt", "ods"}:
        if office.find_soffice() is None:
            raise RecordsError(copy.FILE_LIBREOFFICE_MISSING, status=503, field="file_id")
        converted = office.to_pdf(data, info.name)
        if converted is None:
            raise RecordsError(copy.FILE_OFFICE_CONVERSION_FAILED, status=422, field="file_id")
        return converted
    return data


def build_view(rec, view, *, exporting=False):
    if view["kind"] != "pack":
        raise refusal("kind")
    if exporting and view["status"] != "signed_off":
        raise RecordsError(copy.EXPORT_LABELS["needs_signoff"], status=409)
    return build(
        view["steps"], lambda fid: _source_pdf(rec, fid), view["language"], apply_seal=exporting
    )


def validate_op(rec, head, op):
    if set(op) - {"op", "steps", "expect"}:
        raise refusal()
    validate_steps(op.get("steps"), lambda fid: _source_pdf(rec, fid))
    expected = head["template"]["version"]
    if op.get("expect", expected) != expected:
        raise RecordsError(copy.CHANGE_STALE, status=409)
    return {**op, "expect": expected}


def apply_op(conn, rec, head, op, actor, reason):
    from qsone.records import audit

    validate_steps(op["steps"], lambda fid: _source_pdf(rec, fid))
    cursor = conn.execute("SELECT * FROM deliverables WHERE id = ?", (head["id"],))
    old = dict(zip([d[0] for d in cursor.description], cursor.fetchone(), strict=True))
    old["template"] = json.loads(old["template"])
    old["desk"] = json.loads(old["desk"]) if old["desk"] else None
    tmpl = {**old["template"], "steps": op["steps"], "version": op["expect"] + 1}
    at = rec.clock()
    conn.execute(
        "UPDATE deliverables SET template = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tmpl, ensure_ascii=False), at, head["id"]),
    )
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="update",
        table="deliverables",
        row_id=head["id"],
        before=old,
        after={**old, "template": tmpl, "updated_at": at},
    )
    head["template"] = tmpl


def preview(rec, deliverable_id, version, page):
    """Only a page image leaves this in-memory build; no draft PDF download route."""
    import base64

    import pypdfium2 as pdfium

    from qsone.deliverables import store

    data = build_view(rec, store.view(rec, deliverable_id, version=version))
    with pdfium.PdfDocument(data) as pdf:
        if not 1 <= page <= len(pdf):
            raise refusal("page")
        rendered = pdf[page - 1]
        bitmap = rendered.render(scale=min(1.5, 900 / rendered.get_width()))
        try:
            out = BytesIO()
            bitmap.to_pil().save(out, format="PNG")
            return {
                "pages": len(pdf),
                "page": page,
                "image": "data:image/png;base64," + base64.b64encode(out.getvalue()).decode(),
            }
        finally:
            bitmap.close()
            rendered.close()


def file_labels(conn, steps):
    ids = [s["file_id"] for s in steps if s["kind"] == "file"]
    return {
        fid: {"name": name, "added_at": at}
        for fid, name, at in conn.execute(
            "SELECT id, name, added_at FROM files WHERE id IN (SELECT value FROM json_each(?))",
            (json.dumps(ids),),
        )
    }


def describe(view):
    language = view["language"]
    lines = []
    for step in view["steps"]:
        bits = [copy.PACK_LABELS[step["kind"]][language]]
        for key in ("title", "text"):
            if key in step:
                bits.append(step[key][language])
        if step["kind"] == "file":
            source = view["files"].get(step["file_id"], {})
            bits += [source.get("name", ""), source.get("added_at", "")[:10]]
            bits += [f"{first}–{last}" for first, last in step["ranges"]]
        if step["kind"] == "stamp":
            bits += [
                copy.PACK_LABELS[step["position"]][language],
                ", ".join(map(str, step["pages"])),
            ]
        lines.append(" · ".join(b for b in bits if b))
    return "\n".join(lines)
