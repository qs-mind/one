"""The QS Calc Engine's shared contract: texts, schema 2, ledger writers, request shapes."""

import json
import string
from uuid import uuid4

import pytest
from pydantic import ValidationError

from qsone import copy
from qsone.calc import CONTEXT, ENGINE_VERSION
from qsone.calc.errors import CalcError
from qsone.calc.spec import (
    CalcRequest,
    Constant,
    EachRef,
    ExplainRequest,
    ListRef,
    NumberRef,
    RecalcRequest,
    SlotRef,
    UnitRequest,
)
from qsone.records import db, ledger, schema
from qsone.records.project import Records, RecordsError
from tests.calc_samples import add, sample_project, source_id

CALC = (
    "INSERT INTO calculations (id, formula, request, value, unit, exact, trace, engine, output,"
    " recorded_at, recorded_by) VALUES (?, 'q * r', '{}', '10.00', 'EGP', 1, '{}', 1, ?, 't', 't')"
)


@pytest.fixture
def rec(tmp_path):
    rec = Records.create(tmp_path / uuid4().hex, name="مشروع - عينة", actor="estimator")
    yield rec
    rec.close()


def one_number(rec) -> str:
    with rec.write("estimator") as c:
        s = ledger.write_source(c, at=rec.clock(), actor="estimator", kind="quote", title="عينة")
        i = ledger.write_item(c, at=rec.clock(), actor="estimator", kind="boq_item", code="03/02")
        return ledger.write_number(
            c,
            at=rec.clock(),
            actor="estimator",
            item_id=i,
            name="rate",
            value="100",
            unit="m3",
            currency="EGP",
            source_id=s,
            dated="2026-11-02",
        )


def test_engine_version_and_context():
    assert ENGINE_VERSION == 1
    assert CONTEXT.prec == 50 and CONTEXT.rounding == "ROUND_HALF_EVEN"


def test_schema_2_keeps_calculations_append_only(rec):
    n = one_number(rec)
    with rec.write("t") as c:
        c.execute(CALC, ("c1", n))
        c.execute(
            "INSERT INTO calc_inputs (calc_id, name, seq, number_id) VALUES ('c1', 'r', 0, ?)", (n,)
        )
    with pytest.raises(db.IntegrityError):
        with rec.write("t") as c:
            c.execute("UPDATE calculations SET value = '1'")
    with pytest.raises(db.IntegrityError):
        with rec.write("t") as c:
            c.execute("DELETE FROM calculations")
    with rec.write("t") as c:
        c.execute("UPDATE calculations SET valid_until = 'x'")  # allowed once
    with pytest.raises(db.IntegrityError):
        with rec.write("t") as c:
            c.execute("UPDATE calculations SET valid_until = 'y'")
    with pytest.raises(db.IntegrityError):
        with rec.write("t") as c:
            c.execute("UPDATE calc_inputs SET seq = 1")
    with pytest.raises(db.IntegrityError):
        with rec.write("t") as c:
            c.execute("DELETE FROM calc_inputs")
    with rec.read() as c:
        assert c.execute("SELECT value, valid_until FROM calculations").fetchall() == [
            ("10.00", "x")
        ]
        assert c.execute("SELECT count(*) FROM calc_inputs").fetchone()[0] == 1


def test_a_replacing_calculation_needs_a_reason(rec):
    n = one_number(rec)
    with rec.write("t") as c:
        c.execute(CALC, ("c1", n))
    with pytest.raises(db.IntegrityError):
        with rec.write("t") as c:
            c.execute(
                "INSERT INTO calculations (id, formula, request, value, unit, exact, trace, engine,"
                " output, recorded_at, recorded_by, replaces, reason)"
                " VALUES ('c2', 'q', '{}', '1', '', 1, '{}', 1, ?, 't', 't', 'c1', ' ')",
                (n,),
            )


def test_a_schema_1_project_upgrades_with_its_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "MIGRATIONS", schema.MIGRATIONS[:1])
    folder = tmp_path / uuid4().hex
    rec = Records.create(folder, name="مشروع - عينة", actor="estimator")
    n = one_number(rec)
    with rec.read() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 1
    rec.close()
    monkeypatch.undo()
    rec = Records.open(folder)
    try:
        with rec.read() as c:
            assert c.execute("PRAGMA user_version").fetchone()[0] == 2
            assert c.execute("SELECT id, value FROM numbers").fetchall() == [(n, "100")]
            assert c.execute("SELECT count(*) FROM calculations").fetchone()[0] == 0
    finally:
        rec.close()


def test_ledger_writers_share_one_transaction(rec):
    with pytest.raises(RuntimeError):
        with rec.write("estimator") as c:
            s = ledger.write_source(
                c, at=rec.clock(), actor="estimator", kind="quote", title="عينة"
            )
            i = ledger.write_item(
                c, at=rec.clock(), actor="estimator", kind="boq_item", code="03/02"
            )
            ledger.write_number(
                c,
                at=rec.clock(),
                actor="estimator",
                item_id=i,
                name="rate",
                value="100",
                unit="m3",
                currency="EGP",
                source_id=s,
                dated="2026-11-02",
            )
            raise RuntimeError
    with rec.read() as c:
        for table in ("numbers", "sources", "items", "audit"):
            count = c.execute(f"select count(*) from {table}").fetchone()[0]
            assert count == (1 if table == "audit" else 0), table  # the project's own create row


def test_write_correction_keeps_the_old_entry(rec):
    n = one_number(rec)
    with rec.write("engineer") as c:
        s = ledger.write_source(c, at=rec.clock(), actor="engineer", kind="quote", title="عينة 2")
        new = ledger.write_correction(
            c,
            n,
            at=rec.clock(),
            actor="engineer",
            value="90",
            reason="عرض أحدث - عينة",
            source_id=s,
            dated="2026-11-03",
        )
    with rec.read() as c:
        rows = c.execute(
            "SELECT id, value, replaces, valid_until IS NULL FROM numbers ORDER BY recorded_at"
        )
        assert [r[:3] for r in rows] == [(n, "100", None), (new, "90", n)]
    with pytest.raises(RecordsError) as e:
        with rec.write("engineer") as c:
            ledger.write_correction(
                c,
                n,
                at=rec.clock(),
                actor="engineer",
                value="80",
                reason="x",
                source_id=s,
                dated="2026-11-03",
            )
    assert e.value.text == copy.ALREADY_CORRECTED


def test_fill_both_languages():
    t = copy.fill(copy.CALC_UNKNOWN_NAME, name="rat", names="quantity, rate")
    assert "rat" in t["en"] and "rat" in t["ar"] and '"item"' in t["en"]
    assert '{"item": "03/02", "name": "rate"}' in t["ar"]


def placeholders(s: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(s) if name is not None}


def test_every_calc_text_is_a_pair_with_the_same_placeholders():
    texts = {k: v for k, v in vars(copy).items() if k.startswith("CALC_")}
    assert len(texts) == 40
    for key, text in texts.items():
        assert set(text) == {"en", "ar"} and all(text.values()), key
        assert placeholders(text["en"]) == placeholders(text["ar"]), key
        filled = copy.fill(text, **{name: "X" for name in placeholders(text["en"])})
        assert set(filled) == {"en", "ar"}, key


def test_calc_error_carries_key_and_values():
    e = CalcError("CALC_UNEXPECTED", field="formula", at=10, found=")", expected="a name")
    assert (e.key, e.status, e.field, e.values["at"]) == ("CALC_UNEXPECTED", 422, "formula", 10)
    assert isinstance(e, RecordsError)
    assert e.text == copy.fill(copy.CALC_UNEXPECTED, at=10, found=")", expected="a name")
    assert CalcError("CALC_NO_MATCH", status=404, selector="x").status == 404
    shape = CalcError("CALC_REQUEST_SHAPE", field="inputs.a", example='{"number": "<id>"}')
    assert "«inputs.a»" in shape.text["en"] and "«inputs.a»" in shape.text["ar"]
    assert shape.values == {"example": '{"number": "<id>"}'}
    assert "«a / b»" in CalcError("CALC_DIVIDE_BY_ZERO", text="a / b").text["ar"]


@pytest.mark.parametrize(
    "spec, kind",
    [
        ({"number": "a" * 32}, NumberRef),
        ({"item": "03/02", "name": "rate"}, SlotRef),
        ({"numbers": ["a"]}, ListRef),
        ({"each": {"code_prefix": "03/"}, "name": "amount"}, EachRef),
        ({"constant": "5", "unit": "%", "why": "هالك - عينة"}, Constant),
    ],
)
def test_each_input_shape_is_picked_by_its_keys(spec, kind):
    assert isinstance(CalcRequest(formula="x", inputs={"x": spec}).inputs["x"], kind)


def test_a_full_request_reads():
    req = CalcRequest.model_validate(
        {
            "formula": " الكمية * rate ",
            "inputs": {"الكمية": {"item": "03/02", "name": "quantity"}},
            "item": "03/02",
            "result": {"unit": "EGP", "round": {"places": 0, "mode": "up"}},
            "save": {"name": "amount"},
        }
    )
    assert req.formula == "الكمية * rate" and req.result.round.mode == "up"
    assert CalcRequest(formula="x").result.unit is None
    assert CalcRequest(formula="x").result is not CalcRequest(formula="y").result


@pytest.mark.parametrize(
    "body",
    [
        {"formula": "x", "inputs": {"x": {"constant": "48", "unit": "EGP", "why": "سعر"}}},
        {"formula": "x", "inputs": {"x": {"constant": "5"}}},  # no why
        {"formula": "x", "item": "03/02", "for_each": {"code_prefix": "03/"}},
        {"formula": "x", "result": {"unit": "EGP"}, "save": {"name": "amount"}},  # no target
        {"formula": "x", "item": "03/02", "save": {"name": "amount"}},  # no unit
        {"formula": "sum(x)", "inputs": {"sum": {"number": "a"}}},
        {"formula": "pi", "inputs": {"pi": {"number": "a"}}},
        {"formula": "x", "inputs": {"1x": {"number": "a"}}},
        {"formula": "x", "inputs": {"x": {"number": "a", "name": "rate"}}},  # mixed shapes
        {"formula": "x", "for_each": {}},  # empty selector
        {"formula": "x", "extra": 1},
        {"formula": ""},
        {"formula": "x" * 4001},
        {"formula": "x", "result": {"round": {"places": 11}}},
        {"formula": "x", "result": {"round": {"mode": "ceiling"}}},
    ],
)
def test_request_rules(body):
    with pytest.raises(ValidationError):
        CalcRequest.model_validate(body)


def test_rule_refusals_name_their_field():
    cases = [
        ({"formula": "x", "item": "03/02", "for_each": {"code_prefix": "03/"}}, ("for_each",)),
        ({"formula": "x", "item": "03/02", "save": {"name": "amount"}}, ("save",)),
        ({"formula": "x", "inputs": {"if": {"number": "a"}}}, ("inputs",)),
    ]
    for body, loc in cases:
        with pytest.raises(ValidationError) as e:
            CalcRequest.model_validate(body)
        assert e.value.errors()[0]["loc"] == loc, body


def test_other_requests():
    u = UnitRequest(symbol="bag", equals="50 kg", source_id="s", dated="2026-11-02")
    assert u.reason is None
    assert ExplainRequest(number="n").page == 1
    assert RecalcRequest().apply is False and RecalcRequest().only is None
    with pytest.raises(ValidationError):
        ExplainRequest(number="n", page=0)


def test_the_sample_project(tmp_path):
    rec = sample_project(tmp_path)
    try:
        item = add(
            rec,
            "03/02",
            quantity=("120", "m3", None, "boq"),
            rate=("39850.50", "m3", "EGP", "quote"),
        )
        section = add(rec, "03", kind="section", fields={"description": "خرسانة - عينة"})
        nums = sorted(ledger.numbers(rec, item), key=lambda n: n.name)
        assert [(n.name, str(n.value), n.unit, n.currency, n.dated) for n in nums] == [
            ("quantity", "120", "m3", None, "2026-11-02"),
            ("rate", "39850.50", "m3", "EGP", "2026-11-02"),
        ]
        assert nums[1].source_id == source_id(rec, "quote")
        assert ledger.numbers(rec, section) == []
        with rec.read() as c:
            titles = [r[0] for r in c.execute("SELECT title FROM sources ORDER BY title")]
            fields = c.execute("SELECT fields FROM items WHERE id = ?", (section,)).fetchone()[0]
        assert all("عينة" in t for t in titles) and len(titles) == 5
        assert json.loads(fields) == {"description": "خرسانة - عينة"}
    finally:
        rec.close()
