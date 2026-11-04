"""Out-of-date numbers and recalculation in order (synthetic «عينة» data only)."""

from decimal import Decimal
from itertools import count
from unittest.mock import ANY

import pytest

from qsone import copy
from qsone.calc.engine import calculate, explain
from qsone.calc.graph import Recalculated, recalculate, stale, why_stale
from qsone.calc.resolve import define_unit
from qsone.calc.spec import CalcRequest, UnitRequest
from qsone.records.ledger import add_source, correct_number, numbers, update_item
from tests.calc_samples import add, sample_project, source_id

FX_REASON = "سعر البنك المركزي الجديد - عينة"
TABLES = ("numbers", "sources", "calculations", "calc_inputs", "audit")


def ticking(day: str):
    """A clock that moves one second per call, on `day`."""
    seconds = count()

    def clock() -> str:
        s = next(seconds)
        return f"{day}T08:{s // 60 % 60:02d}:{s % 60:02d}.000000+00:00"

    return clock


def save(rec, formula, *, item, unit, name, **inputs):
    request = CalcRequest(
        formula=formula, item=item, inputs=inputs, result={"unit": unit}, save={"name": name}
    )
    return calculate(rec, request, actor="estimator").results[0]


def item_of(rec, code) -> str:
    with rec.read() as c:
        return c.execute("SELECT id FROM items WHERE code = ?", (code,)).fetchone()[0]


def current(rec, code, name):
    (n,) = [n for n in numbers(rec, item_of(rec, code)) if n.name == name]
    return n


def counts(rec) -> dict:
    with rec.read() as c:
        return {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


@pytest.fixture
def chain(tmp_path):
    """FX: 50 EGP/USD. 03/02: rate = steel * price_usd * fx + labour (100 kg/m3 × 900 USD/t ×
    50 EGP/USD + 300 EGP/m3 = 4800.00 EGP/m3), amount = 120 m3 × rate = 576000.00 EGP.
    03/03: 45 m2 × 180.25 EGP/m2 = 8111.25 EGP. Section 03 = sum of the 03/ amounts = 584111.25.
    Bill B1 = section × 1.10 × 1.05 = 674648.49375, so 674648.49."""
    rec = sample_project(tmp_path)
    rec.clock = ticking("2026-11-02")
    add(rec, "FX", kind="exchange_rate", exchange_rate=("50", "EGP/USD", None, "exchange_rate"))
    add(
        rec,
        "03/02",
        quantity=("120", "m3", None, "boq"),
        steel=("100", "kg/m3", None, "mix_design"),
        price_usd=("900", "t", "USD", "quote"),
        labour=("300", "m3", "EGP", "quote"),
    )
    add(rec, "03/03", quantity=("45", "m2", None, "boq"), rate=("180.25", "m2", "EGP", "quote"))
    add(rec, "03", kind="section")
    add(
        rec,
        "B1",
        kind="bill",
        oh=("10", "%", None, "contract"),
        profit=("5", "%", None, "contract"),
    )
    fx = {"item": "FX", "name": "exchange_rate"}
    rec.ids = {
        "rate": save(
            rec, "steel * price_usd * fx + labour", item="03/02", unit="EGP/m3", name="rate", fx=fx
        ),
        "amount": save(rec, "quantity * rate", item="03/02", unit="EGP", name="amount"),
        "amount_0303": save(rec, "quantity * rate", item="03/03", unit="EGP", name="amount"),
        "section": save(
            rec,
            "sum(a)",
            item="03",
            unit="EGP",
            name="amount",
            a={"each": {"code_prefix": "03/"}, "name": "amount"},
        ),
        "bill": save(
            rec,
            "section * (1 + oh) * (1 + profit)",
            item="B1",
            unit="EGP",
            name="amount",
            section={"item": "03", "name": "amount"},
        ),
    }
    yield rec
    rec.close()


def correct_fx(rec) -> str:
    return correct_number(
        rec,
        current(rec, "FX", "exchange_rate").id,
        value="48",
        reason=FX_REASON,
        source_id=source_id(rec, "exchange_rate"),
        dated="2026-11-03",
        actor="engineer",
    )


def test_the_chain_is_hand_checked(chain):
    assert [r.value for r in chain.ids.values()] == [
        "4800.00",
        "576000.00",
        "8111.25",
        "584111.25",
        "674648.49",
    ]
    assert stale(chain) == []


def test_correcting_an_input_lists_everything_built_on_it(chain):
    fx_id = current(chain, "FX", "exchange_rate").id
    correct_fx(chain)
    s = stale(chain)
    assert [(x.code, x.name) for x in s] == [
        ("03/02", "rate"),
        ("03/02", "amount"),
        ("03", "amount"),
        ("B1", "amount"),
    ]
    ids = chain.ids
    assert [x.calculation for x in s] == [
        ids[k].calculation for k in ("rate", "amount", "section", "bill")
    ]
    assert [x.number for x in s] == [ids[k].number for k in ("rate", "amount", "section", "bill")]
    assert s[0].item == item_of(chain, "03/02")
    assert s[0].because == [{"input": "fx", "was": fx_id, "now": ANY, "reason": FX_REASON}]
    assert s[0].because[0]["now"] == current(chain, "FX", "exchange_rate").id
    assert s[1].because == [{"waits_for": s[0].calculation}]
    assert s[2].because == [{"waits_for": s[1].calculation}]
    assert s[3].because == [{"waits_for": s[2].calculation}]


def test_recalculate_in_order_and_keep_the_old(chain):
    correct_fx(chain)
    listed = stale(chain)
    chain.clock = ticking("2026-11-03")
    r = recalculate(chain, actor="engineer")
    # 100 × 0.9 × 48 + 300 = 4620; 120 × 4620 = 554400; + 8111.25 = 562511.25;
    # 562511.25 × 1.155 = 649700.49375.
    assert [(c.code, c.name, c.was, c.now, c.unit) for c in r.changes] == [
        ("03/02", "rate", "4800.00", "4620.00", "EGP/m3"),
        ("03/02", "amount", "576000.00", "554400.00", "EGP"),
        ("03", "amount", "584111.25", "562511.25", "EGP"),
        ("B1", "amount", "674648.49", "649700.49", "EGP"),
    ]
    assert (r.failed, r.waiting) == ([], [])
    assert [c.replaced for c in r.changes] == [x.calculation for x in listed]
    assert [c.replaced_number for c in r.changes] == [x.number for x in listed]
    assert stale(chain) == []

    bill = item_of(chain, "B1")
    assert numbers(chain, bill, as_of="2026-11-02")[-1].value == Decimal("674648.49")
    now = numbers(chain, bill)[-1]
    assert (now.id, now.value, now.replaces) == (
        r.changes[-1].number,
        Decimal("649700.49"),
        listed[-1].number,
    )
    # Every recalculated number names the input that started it.
    reason = copy.fill(copy.CALC_RECALCULATED, name="fx", reason=FX_REASON)["en"]
    assert {c.name: current(chain, c.code, c.name).reason for c in r.changes[:1]} == {
        "rate": reason
    }
    assert current(chain, "B1", "amount").reason == reason

    with chain.read() as c:
        old = c.execute(
            "SELECT valid_until FROM calculations WHERE id = ?", (listed[0].calculation,)
        ).fetchone()[0]
        replaces, why, trace = c.execute(
            "SELECT replaces, reason, trace FROM calculations WHERE id = ?",
            (r.changes[1].calculation,),
        ).fetchone()
    assert old is not None and (replaces, why) == (listed[1].calculation, reason)
    # The trace keeps the cause as data: the rate it read was the recalculated one.
    assert f'"was": "{listed[0].number}"' in trace and f'"now": "{r.changes[0].number}"' in trace

    e = explain(chain, r.changes[0].number)["calculation"]
    assert {i["name"]: (i["value"], i["dated"]) for i in e["inputs"]}["fx"] == ("48", "2026-11-03")
    assert e["stale"] is False


def test_a_hand_correction_is_never_overwritten(chain):
    hand = correct_number(
        chain,
        chain.ids["amount_0303"].number,
        value="9000",
        reason="مبلغ متفق عليه - عينة",
        source_id=source_id(chain, "contract"),
        dated="2026-11-03",
        actor="engineer",
    )
    s = stale(chain)
    assert [(x.code, x.name) for x in s] == [("03", "amount"), ("B1", "amount")]
    assert s[0].because == [
        {
            "input": "a",
            "was": chain.ids["amount_0303"].number,
            "now": hand,
            "reason": "مبلغ متفق عليه - عينة",
        }
    ]
    r = recalculate(chain, actor="engineer")
    assert [(c.code, c.now) for c in r.changes] == [("03", "585000.00"), ("B1", "675675.00")]
    assert current(chain, "03/03", "amount").id == hand
    assert current(chain, "03/03", "amount").value == Decimal("9000")
    # Correcting the hand value's inputs never brings its old calculation back.
    correct_number(
        chain,
        current(chain, "03/03", "rate").id,
        value="200",
        reason="عرض جديد - عينة",
        source_id=source_id(chain, "quote"),
        dated="2026-11-03",
        actor="engineer",
    )
    assert stale(chain) == []


def test_a_new_member_makes_its_total_stale(chain):
    add(chain, "03/04", amount=("1000", None, "EGP", "boq"))
    s = stale(chain)
    assert [(x.code, x.name) for x in s] == [("03", "amount"), ("B1", "amount")]
    assert s[0].because == [{"members": {"added": ["03/04"], "removed": []}}]
    assert s[1].because == [{"waits_for": s[0].calculation}]
    r = recalculate(chain, actor="engineer")
    assert [(c.code, c.now) for c in r.changes] == [("03", "585111.25"), ("B1", "675803.49")]
    assert current(chain, "03", "amount").reason == copy.CALC_RECALC_MEMBERS["en"]
    assert current(chain, "B1", "amount").reason == copy.CALC_RECALC_MEMBERS["en"]
    assert stale(chain) == []


def test_a_removed_member_makes_its_total_stale(chain):
    add(chain, "F1", fields={"floor": "1"}, amount=("100", None, "EGP", "boq"))
    add(chain, "F2", fields={"floor": "1"}, amount=("50", None, "EGP", "boq"))
    add(chain, "T1", kind="section")
    a = {"each": {"where": {"floor": "1"}}, "name": "amount"}
    assert save(chain, "sum(a)", item="T1", unit="EGP", name="amount", a=a).value == "150.00"
    update_item(chain, item_of(chain, "F2"), fields={"floor": "2"}, actor="engineer")
    s = stale(chain)
    assert [(x.code, x.because) for x in s] == [
        ("T1", [{"members": {"added": [], "removed": ["F2"]}}])
    ]
    r = recalculate(chain, actor="engineer")
    assert [(c.code, c.now) for c in r.changes] == [("T1", "100.00")]


def test_a_corrected_unit_definition_reaches_its_users(chain):
    sheet = add_source(chain, kind="datasheet", title="نشرة الأسمنت - عينة", actor="estimator")
    first = define_unit(
        chain,
        UnitRequest(symbol="bag", equals="50 kg", source_id=sheet, dated="2026-11-02"),
        actor="estimator",
    )
    add(
        chain,
        "C1",
        cement=("350", "kg/m3", None, "mix_design"),
        bag_price=("150", "bag", "EGP", "quote"),
    )
    # 350 kg/m3 × 150 EGP/bag ÷ 50 kg/bag = 1050; with a 25 kg bag, 2100.
    assert (
        save(chain, "cement * bag_price", item="C1", unit="EGP/m3", name="rate").value == "1050.00"
    )
    second = define_unit(
        chain,
        UnitRequest(
            symbol="bag",
            equals="25 kg",
            source_id=sheet,
            dated="2026-11-03",
            reason="عبوة جديدة - عينة",
        ),
        actor="engineer",
    )
    s = stale(chain)
    assert [(x.code, x.name) for x in s] == [("C1", "rate")]
    assert s[0].because == [
        {"input": "unit:bag", "was": first, "now": second, "reason": "عبوة جديدة - عينة"}
    ]
    r = recalculate(chain, actor="engineer")
    assert [(c.code, c.now) for c in r.changes] == [("C1", "2100.00")]


def test_a_failed_step_leaves_its_dependents_waiting(chain):
    correct_fx(chain)
    correct_number(
        chain,
        current(chain, "03/02", "quantity").id,
        value="120",
        unit="m2",
        reason="وحدة خطأ - عينة",
        source_id=source_id(chain, "boq"),
        dated="2026-11-03",
        actor="engineer",
    )
    ids = chain.ids
    r = recalculate(chain, actor="engineer")
    assert [(c.code, c.name, c.now) for c in r.changes] == [("03/02", "rate", "4620.00")]
    assert len(r.failed) == 1
    failed = r.failed[0]
    assert (failed["calculation"], failed["code"]) == (ids["amount"].calculation, "03/02")
    assert set(failed["error"]) == {"en", "ar"} and "EGP/m" in failed["error"]["en"]
    assert r.waiting == [ids["section"].calculation, ids["bill"].calculation]

    s = stale(chain)
    assert [x.calculation for x in s] == [ids[k].calculation for k in ("amount", "section", "bill")]
    assert [b.get("input") for b in s[0].because] == ["quantity", "rate"]
    for key, value in (("section", "584111.25"), ("bill", "674648.49")):
        n = current(chain, "03" if key == "section" else "B1", "amount")
        assert (n.id, str(n.value)) == (ids[key].number, value)
    with chain.read() as c:
        rows = c.execute(
            "SELECT count(*) FROM calculations WHERE output IN (?, ?, ?)",
            (ids["amount"].number, ids["section"].number, ids["bill"].number),
        ).fetchone()[0]
    assert rows == 3


def test_only_some(chain):
    correct_fx(chain)
    ids = chain.ids
    r = recalculate(chain, actor="engineer", only=[ids["rate"].calculation])
    assert [(c.code, c.name) for c in r.changes] == [("03/02", "rate")]
    s = stale(chain)
    assert [(x.code, x.name) for x in s] == [
        ("03/02", "amount"),
        ("03", "amount"),
        ("B1", "amount"),
    ]
    assert [b["input"] for b in s[0].because] == ["rate"]


def test_only_runs_what_it_needs_first(chain):
    correct_fx(chain)
    ids = chain.ids
    r = recalculate(chain, actor="engineer", only=[ids["amount"].calculation])
    assert [(c.code, c.name) for c in r.changes] == [("03/02", "rate"), ("03/02", "amount")]
    assert [(x.code, x.name) for x in stale(chain)] == [("03", "amount"), ("B1", "amount")]


def test_nothing_stale_is_a_no_op(chain):
    before = counts(chain)
    assert recalculate(chain, actor="engineer") == Recalculated([], [], [])
    assert counts(chain) == before


def test_explain_shows_stale_and_why(chain):
    correct_fx(chain)
    e = explain(chain, chain.ids["amount"].number)["calculation"]
    assert e["stale"] is True
    assert e["because"] == [{"waits_for": chain.ids["rate"].calculation}]
    with chain.read() as c:
        assert why_stale(c, chain.ids["rate"].calculation)[0]["input"] == "fx"
        assert why_stale(c, "no-such-calculation") == []
    assert explain(chain, chain.ids["amount_0303"].number)["calculation"]["stale"] is False


def test_saving_again_after_recalculating_is_unchanged(chain):
    correct_fx(chain)
    r = recalculate(chain, actor="engineer")
    before = counts(chain)
    again = save(chain, "quantity * rate", item="03/02", unit="EGP", name="amount")
    assert (again.unchanged, again.value, again.number) == (True, "554400.00", r.changes[1].number)
    assert counts(chain) == before


def test_calculations_that_read_each_other_wait(chain):
    # 03/03's rate is worked back from its amount, which was priced from that rate.
    request = CalcRequest(
        formula="amount / quantity",
        item="03/03",
        result={"unit": "EGP/m2"},
        save={"name": "rate", "reason": "سعر محسوب - عينة"},
    )
    back = calculate(chain, request, actor="estimator").results[0]
    ids = chain.ids
    s = stale(chain)
    assert [x.calculation for x in s] == [
        ids["amount_0303"].calculation,
        ids["section"].calculation,
        ids["bill"].calculation,
        back.calculation,
    ]
    assert s[0].because[-1] == {"waits_for": back.calculation}
    before = counts(chain)
    r = recalculate(chain, actor="engineer")
    assert (r.changes, r.failed, r.waiting) == ([], [], [x.calculation for x in s])
    assert counts(chain) == before
