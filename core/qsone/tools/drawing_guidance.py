"""Drawing guidance supplied only when a tool encounters drawing evidence."""

GUIDANCE = (
    "Drawing guidance: project_map sheets/counts for counts and labels; files_read picture=true "
    "on the needed page, even when text exists. Scale only from the title block or a labelled "
    "dimension, never screen size. Say what the picture lets you measure and what needs the "
    "engineer. Reading method only from read_by: text-layer words are not OCR; never invent "
    "OCR confidence. Take-off is unchecked evidence: add_source with file/page/region "
    "(box in PDF points); ask_engineer confirmation cards each naming file/page/region, "
    "then record confirmed quantities using answer evidence. Totals by calculate. "
    "If there is no vision, say so; text alone cannot establish picture quality."
)


def for_pages(rec, file_id, pages):
    """Only the selected pages' current map entries identify a PDF drawing."""
    with rec.read() as conn:
        sources = conn.execute(
            "SELECT source FROM map_sheets WHERE file_id=? AND valid_until IS NULL",
            (file_id,),
        ).fetchall()
    import json

    return GUIDANCE if any(json.loads(source).get("page") in pages for (source,) in sources) else ""
