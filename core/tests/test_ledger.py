"""The Source Ledger: every number exact, with a source and a date, corrected by a new entry."""

from decimal import Decimal
from uuid import uuid4

import pytest

from qsone import copy
from qsone.records.ledger import (
    add_item,
    add_source,
    correct_number,
    history,
    numbers,
    record_number,
    update_item,
)
from qsone.records.project import Records, RecordsError


@pytest.fixture
def rec(tmp_path):
    rec = Records.create(tmp_path / uuid4().hex, name="مشروع - عينة", actor="engineer")
    yield rec
    rec.close()


@pytest.fixture
def item(rec):
    return add_item(rec, kind="boq_item", code="03/02", actor="engineer")


@pytest.fixture
def source(rec):
    return add_source(
        rec, kind="quote", title="عرض سعر مورد - عينة", dated="2026-11-02", actor="engineer"
    )


def refusal(call, **kwargs) -> RecordsError:
    with pytest.raises(RecordsError) as e:
        call(**kwargs)
    assert e.value.status == 422
    return e.value


def test_a_number_needs_a_source_and_a_date(rec):
    item = add_item(
        rec,
        kind="boq_item",
        code="03/02",
        fields={"description": "خرسانة مسلحة للأسقف"},
        actor="engineer",
    )
    base = dict(
        rec=rec, item_id=item, name="rate", value="39850", unit="m3", currency="EGP", actor="e"
    )
    e = refusal(record_number, **base, source_id="nope", dated="2026-11-02")
    assert (e.text, e.field) == (copy.NUMBER_NEEDS_SOURCE, "source_id")
    source = add_source(rec, kind="quote", title="عرض سعر - عينة", actor="engineer")
    for dated in ["", "2026-02-30", "02/11/2026", "20261102", "2026-11-02T08:00"]:
        e = refusal(record_number, **base, source_id=source, dated=dated)
        assert (e.text, e.field) == (copy.NUMBER_NEEDS_DATE, "dated"), dated
    with rec.read() as c:
        assert c.execute("select count(*) from numbers").fetchone()[0] == 0


@pytest.mark.parametrize(
    "value",
    [
        39850.5,
        "39,850",
        "1_000",
        "3e4",
        "NaN",
        "Infinity",
        "",
        " 5",
        "1.",
        ".5",
        "٣٩٬٨٥٠",
        True,
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_only_exact_numbers(rec, item, source, value):
    e = refusal(
        record_number,
        rec=rec,
        item_id=item,
        name="rate",
        value=value,
        unit="m3",
        currency="EGP",
        source_id=source,
        dated="2026-11-02",
        actor="engineer",
    )
    assert (e.text, e.field) == (copy.NUMBER_NOT_EXACT, "value")


def test_arabic_digits_are_kept_exact(rec, item, source):
    record_number(
        rec,
        item_id=item,
        name="rate",
        value="٣٩٨٥٠٫٥٠",
        unit="m3",
        currency="EGP",
        source_id=source,
        dated="2026-11-02",
        actor="engineer",
    )
    record_number(
        rec,
        item_id=item,
        name="quantity",
        value="۱۲۰",
        unit="m3",
        source_id=source,
        dated="2026-11-02",
        actor="engineer",
    )
    record_number(
        rec,
        item_id=item,
        name="amount",
        value=Decimal("4782060.00"),
        currency="EGP",
        source_id=source,
        dated="2026-11-02",
        actor="engineer",
    )
    got = {n.name: n.value for n in numbers(rec, item)}
    assert got == {
        "rate": Decimal("39850.50"),
        "quantity": Decimal("120"),
        "amount": Decimal("4782060.00"),
    }
    with rec.read() as c:  # stored as written in digits, never as float
        stored = dict(c.execute("select name, value from numbers"))
    assert stored == {"rate": "39850.50", "quantity": "120", "amount": "4782060.00"}


def test_core_numbers_need_unit_and_currency(rec, item, source):
    base = dict(rec=rec, item_id=item, value="10", source_id=source, dated="2026-11-02", actor="e")
    cases = [
        (dict(name="quantity"), copy.NUMBER_NEEDS_UNIT, "unit"),
        (dict(name="quantity", unit=" "), copy.NUMBER_NEEDS_UNIT, "unit"),
        (dict(name="rate", currency="EGP"), copy.NUMBER_NEEDS_UNIT, "unit"),
        (dict(name="rate", unit="m3"), copy.NUMBER_NEEDS_CURRENCY, "currency"),
        (dict(name="amount"), copy.NUMBER_NEEDS_CURRENCY, "currency"),
        (dict(name="amount", currency="egp"), copy.NUMBER_NEEDS_CURRENCY, "currency"),
        (dict(name="amount", currency="جنيه"), copy.NUMBER_NEEDS_CURRENCY, "currency"),
        (dict(name="rate", unit="m3", currency="EGPP"), copy.NUMBER_NEEDS_CURRENCY, "currency"),
    ]
    for extra, text, field in cases:
        e = refusal(record_number, **base, **extra)
        assert (e.text, e.field) == (text, field), extra
    record_number(**base, name="quantity", unit="م3")
    record_number(**base, name="rate", unit="m3", currency="SAR")
    record_number(**base, name="amount", currency="AED")
    assert sorted(n.name for n in numbers(rec, item)) == ["amount", "quantity", "rate"]


def test_other_named_numbers_are_allowed(rec, item, source):
    waste = record_number(
        rec,
        item_id=item,
        name="waste",
        value="5",
        unit="%",
        source_id=source,
        dated="2026-11-02",
        actor="lead_qs",
    )
    record_number(
        rec,
        item_id=item,
        name="exchange_rate",
        value="48.25",
        source_id=source,
        dated="2026-11-02",
        actor="lead_qs",
    )
    [n] = [n for n in numbers(rec, item) if n.id == waste]
    assert (n.value, n.unit, n.currency, n.recorded_by) == (Decimal("5"), "%", None, "lead_qs")
    e = refusal(
        record_number,
        rec=rec,
        item_id=item,
        name="waste",
        value="5.5.5",
        source_id=source,
        dated="2026-11-02",
        actor="lead_qs",
    )
    assert e.text == copy.NUMBER_NOT_EXACT


def test_correction_keeps_the_old_entry_and_answers_as_of(rec, item, source):
    rec.clock = lambda: "2026-11-01T08:00:00.000000+00:00"
    old = record_number(
        rec,
        item_id=item,
        name="rate",
        value="100",
        unit="m3",
        currency="EGP",
        source_id=source,
        dated="2026-11-01",
        actor="estimator",
    )
    rec.clock = lambda: "2026-11-03T08:00:00.000000+00:00"
    e = refusal(  # no reason
        correct_number,
        rec=rec,
        number_id=old,
        value="120",
        reason=" ",
        source_id=source,
        dated="2026-11-03",
        actor="engineer",
    )
    assert (e.text, e.field) == (copy.CORRECTION_NEEDS_REASON, "reason")
    new = correct_number(
        rec,
        old,
        value="120",
        reason="supplier quote revised",
        source_id=source,
        dated="2026-11-03",
        actor="engineer",
    )
    assert [n.value for n in numbers(rec, item)] == [Decimal("120")]
    [current] = numbers(rec, item)
    assert (current.id, current.replaces, current.reason) == (new, old, "supplier quote revised")
    assert (current.unit, current.currency) == ("m3", "EGP")  # kept from the old entry
    assert [n.value for n in numbers(rec, item, as_of="2026-11-02")] == [Decimal("100")]
    assert numbers(rec, item, as_of="2026-10-31") == []
    assert [n.value for n in numbers(rec, item, as_of="2026-11-03T07:59:59+00:00")] == [
        Decimal("100")
    ]
    assert [n.value for n in numbers(rec, item, as_of="2026-11-03T10:00:00+02:00")] == [
        Decimal("120")
    ]
    [then] = numbers(rec, item, as_of="2026-11-02")
    assert then.valid_until == "2026-11-03T08:00:00.000000+00:00"
    assert [h["action"] for h in history(rec, old)] == ["create", "correct"]
    assert [h["action"] for h in history(rec, new)] == ["create"]
    assert history(rec, old)[1]["actor"] == "engineer"
    assert history(rec, old)[1]["after"]["valid_until"] == "2026-11-03T08:00:00.000000+00:00"
    e = refusal(
        correct_number,
        rec=rec,
        number_id=old,
        value="130",
        reason="again",
        source_id=source,
        dated="2026-11-03",
        actor="engineer",
    )
    assert e.text == copy.ALREADY_CORRECTED


def test_a_correction_follows_the_same_rules(rec, item, source):
    old = record_number(
        rec,
        item_id=item,
        name="rate",
        value="100",
        unit="m3",
        currency="EGP",
        source_id=source,
        dated="2026-11-01",
        actor="estimator",
    )
    base = dict(rec=rec, number_id=old, reason="revised", actor="engineer")
    e = refusal(correct_number, **base, value=120.0, source_id=source, dated="2026-11-03")
    assert e.text == copy.NUMBER_NOT_EXACT
    e = refusal(correct_number, **base, value="120", source_id="nope", dated="2026-11-03")
    assert e.text == copy.NUMBER_NEEDS_SOURCE
    e = refusal(correct_number, **base, value="120", source_id=source, dated="3 Nov")
    assert e.text == copy.NUMBER_NEEDS_DATE
    e = refusal(
        correct_number, **base, value="120", source_id=source, dated="2026-11-03", currency="x"
    )
    assert e.text == copy.NUMBER_NEEDS_CURRENCY
    # every refusal left the old entry current
    assert [(n.id, n.valid_until) for n in numbers(rec, item)] == [(old, None)]


def test_item_fields_are_versioned_with_before_and_after(rec):
    item = add_item(
        rec, kind="boq_item", code="03/02", fields={"description": "خرسانة"}, actor="estimator"
    )
    assert update_item(rec, item, fields={"description": "خرسانة مسلحة"}, actor="engineer") == 2
    assert update_item(rec, item, fields={"description": "خرسانة مسلحة للأسقف"}, actor="e") == 3
    trail = history(rec, item)
    assert [(h["action"], h["actor"]) for h in trail] == [
        ("create", "estimator"),
        ("update", "engineer"),
        ("update", "e"),
    ]
    assert trail[0]["before"] is None
    assert trail[1]["before"]["fields"] == {"description": "خرسانة"}
    assert trail[1]["after"]["fields"] == {"description": "خرسانة مسلحة"}
    assert (trail[1]["before"]["version"], trail[1]["after"]["version"]) == (1, 2)


def test_flexible_fields_keep_arabic(rec):
    fields = {"floor": "الدور الأرضي", "brand": "حديد عز - عينة", "zone": "B"}
    item = add_item(rec, kind="resource", fields=fields, actor="lead_qs")
    with rec.read() as c:
        kind, code, stored = c.execute(
            "select kind, code, fields from items where id = ?", (item,)
        ).fetchone()
    assert (kind, code) == ("resource", None)
    assert "الدور الأرضي" in stored  # JSON keeps Arabic as written, not \u escapes
    assert history(rec, item)[0]["after"]["fields"] == fields


def test_a_source_is_recorded_with_its_audit_row(rec, source):
    [h] = history(rec, source)
    assert (h["action"], h["table"], h["actor"]) == ("create", "sources", "engineer")
    assert h["after"]["title"] == "عرض سعر مورد - عينة"
    assert h["after"]["locator"] == {}
    page = add_source(
        rec, kind="spec", title="المواصفات - عينة", locator={"page": 12}, actor="engineer"
    )
    assert history(rec, page)[0]["after"]["locator"] == {"page": 12}
