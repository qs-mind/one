"""The worked sample BOQ, checked by hand (synthetic «عينة» data only).

A rate for 1 m3 of concrete, the section's amounts, its total, the bill with overheads and
profit, VAT and escalation, then the exchange rate is corrected and everything built on it is
recalculated in order. It runs once through the agents' tools and once through the core API.

Hand checks, with the exchange rate at 50 and then at 48 EGP/USD:
- rate = (350 kg/m3 × 3000 EGP/t + 0.4 × 250 + 0.8 × 300 + 100 kg/m3 × 900 USD/t × fx) × 1.05
  + 2400 EGP/day ÷ 8 m3/day = (1050 + 100 + 240 + 4500) × 1.05 + 300 = 6484.50,
  then (1050 + 100 + 240 + 4320) × 1.05 + 300 = 6295.50;
- 03/02 amount = 120 m3 × rate = 778140.00, then 755460.00; 03/03 = 45 m2 × 180.25 = 8111.25;
- section 03 = 786251.25, then 763571.25;
- bill = section × 1.10 × 1.05 = 908120.19375 → 908120.19, then 881924.79375 → 881924.79;
- with VAT = bill × 1.14 = 1035257.0166 → 1035257.02, then 1005394.2606 → 1005394.26;
- escalated = amount × (0.35 + 0.65 × 132 / 120) = amount × 1.065 = 828719.10, then 804564.90.
"""

import sys
from collections.abc import Callable
from itertools import count

import pytest
from fastapi.testclient import TestClient

from qsone.app import create_app
from qsone.calc.tool import call
from qsone.records import ledger
from qsone.records.ledger import correct_number, numbers
from tests.calc_samples import ACTOR, SOURCES, add, sample_project, source_id
from tests.conftest import AUTH, SECRET

RATE = (
    "(cement_content * cement_price + sand * sand_price + gravel * gravel_price"
    " + steel * steel_price * fx) * (1 + waste) + gang / output"
)
FX_REASON = "سعر جديد - عينة"

# The calculations, in the order they are saved. Bare names read the target item's numbers.
STEPS = [
    {
        "formula": RATE,
        "item": "03/02",
        "inputs": {
            "cement_price": {"item": "CEM", "name": "price"},
            "sand_price": {"item": "SAND", "name": "price"},
            "gravel_price": {"item": "GRAVEL", "name": "price"},
            "steel_price": {"item": "STEEL", "name": "price"},
            "fx": {"item": "FX", "name": "exchange_rate"},
            "waste": {"constant": "5", "unit": "%", "why": "قاعدة الهالك للمقدر - عينة"},
        },
        "result": {"unit": "EGP/m3"},
        "save": {"name": "rate"},
    },
    {
        "formula": "quantity * rate",
        "for_each": {"code_prefix": "03/"},
        "result": {"unit": "EGP"},
        "save": {"name": "amount"},
    },
    {
        "formula": "sum(a)",
        "item": "03",
        "inputs": {"a": {"each": {"code_prefix": "03/"}, "name": "amount"}},
        "result": {"unit": "EGP"},
        "save": {"name": "amount"},
    },
    {
        "formula": "section * (1 + oh) * (1 + profit)",
        "item": "B1",
        "inputs": {"section": {"item": "03", "name": "amount"}},
        "result": {"unit": "EGP"},
        "save": {"name": "amount"},
    },
    {
        "formula": "bill * (1 + vat)",
        "item": "B1",
        "inputs": {"bill": {"item": "B1", "name": "amount"}},
        "result": {"unit": "EGP"},
        "save": {"name": "amount_with_vat"},
    },
    {
        "formula": "amount * (a + b * now / base)",
        "item": "03/02",
        "inputs": {k: {"item": "ESC", "name": k} for k in ("a", "b", "now", "base")},
        "result": {"unit": "EGP"},
        "save": {"name": "escalated"},
    },
]

BEFORE = [
    ["6484.50"],
    ["778140.00", "8111.25"],
    ["786251.25"],
    ["908120.19"],
    ["1035257.02"],
    ["828719.10"],
]

# Kahn's order; of the ready ones, the earliest recorded goes first (escalation was saved last).
STALE = [
    ("03/02", "rate"),
    ("03/02", "amount"),
    ("03", "amount"),
    ("B1", "amount"),
    ("B1", "amount_with_vat"),
    ("03/02", "escalated"),
]

AFTER = {
    ("03/02", "rate"): "6295.50",
    ("03/02", "amount"): "755460.00",
    ("03/02", "escalated"): "804564.90",
    ("03", "amount"): "763571.25",
    ("B1", "amount"): "881924.79",
    ("B1", "amount_with_vat"): "1005394.26",
}


def ticking(day: str) -> Callable[[], str]:
    """A clock that moves one second per call, on `day`."""
    seconds = count()

    def clock() -> str:
        s = next(seconds)
        return f"{day}T08:{s // 60 % 60:02d}:{s % 60:02d}.000000+00:00"

    return clock


def add_sample_boq(rec) -> None:
    """The sample's items and numbers, each with its «عينة» source, dated 2026-11-02."""
    rec.clock = ticking("2026-11-02")
    add(rec, "FX", kind="exchange_rate", exchange_rate=("50", "EGP/USD", None, "exchange_rate"))
    add(rec, "CEM", kind="resource", price=("3000", "t", "EGP", "quote"))
    add(rec, "SAND", kind="resource", price=("250", "m3", "EGP", "quote"))
    add(rec, "GRAVEL", kind="resource", price=("300", "m3", "EGP", "quote"))
    add(rec, "STEEL", kind="resource", price=("900", "t", "USD", "quote"))
    add(
        rec,
        "03/02",
        quantity=("120", "m3", None, "boq"),
        cement_content=("350", "kg/m3", None, "mix_design"),
        sand=("0.4", "m3/m3", None, "mix_design"),
        gravel=("0.8", "m3/m3", None, "mix_design"),
        steel=("100", "kg/m3", None, "mix_design"),
        gang=("2400", "day", "EGP", "estimator"),
        output=("8", "m3/day", None, "estimator"),
    )
    add(rec, "03/03", quantity=("45", "m2", None, "boq"), rate=("180.25", "m2", "EGP", "quote"))
    add(rec, "03", kind="section")
    add(
        rec,
        "B1",
        kind="bill",
        oh=("10", "%", None, "policy"),
        profit=("5", "%", None, "policy"),
        vat=("14", "%", None, "law"),
    )
    add(
        rec,
        "ESC",
        kind="escalation",
        a=("0.35", None, None, "contract"),
        b=("0.65", None, None, "contract"),
        base=("120", "pt", None, "index"),
        now=("132", "pt", None, "index"),
    )


def current(rec, code: str, name: str) -> str:
    with rec.read() as c:
        return c.execute(
            "SELECT n.id FROM numbers n JOIN items i ON i.id = n.item_id"
            " WHERE i.code = ? AND n.name = ? AND n.valid_until IS NULL",
            (code, name),
        ).fetchone()[0]


def value_as_of(rec, code: str, name: str, as_of: str) -> str:
    with rec.read() as c:
        (item,) = c.execute("SELECT id FROM items WHERE code = ?", (code,)).fetchone()
    (n,) = [n for n in numbers(rec, item, as_of=as_of) if n.name == name]
    return str(n.value)


def check_the_sample(rec, send: Callable[[str, dict], dict]) -> None:
    """Runs the sample through `send(tool, payload)` and checks every number by hand."""
    for payload, want in zip(STEPS, BEFORE, strict=True):
        reply = send("calculate", payload)
        assert "error" not in reply, reply
        assert [r["value"] for r in reply["results"]] == want, payload["formula"]
        assert reply["saved"] == len(want)
    for payload, want in zip(STEPS, BEFORE, strict=True):  # again on the same inputs: no change
        assert send("calculate", payload)["unchanged"] == len(want)

    rec.clock = ticking("2026-11-03")
    correct_number(
        rec,
        current(rec, "FX", "exchange_rate"),
        value="48",
        reason=FX_REASON,
        source_id=source_id(rec, "exchange_rate"),
        dated="2026-11-03",
        actor="engineer",
    )
    listed = send("recalculate", {"apply": False})
    assert [(s["code"], s["name"]) for s in listed["stale"]] == STALE
    assert listed["stale"][0]["because"][0]["reason"] == FX_REASON

    done = send("recalculate", {"apply": True})
    assert {(c["code"], c["name"]): c["now"] for c in done["changes"]} == AFTER
    assert [(c["code"], c["name"]) for c in done["changes"]] == STALE
    assert (done["failed"], done["waiting"]) == ([], [])
    assert send("recalculate", {"apply": False}) == {"stale": [], "count": 0}

    assert value_as_of(rec, "B1", "amount", "2026-11-02") == "908120.19"
    assert value_as_of(rec, "03/02", "rate", "2026-11-02") == "6484.50"
    e = send("explain_number", {"number": current(rec, "03/02", "rate")})
    dated = {i["name"]: i["dated"] for i in e["calculation"]["inputs"]}
    assert dated["fx"] == "2026-11-03" and dated["cement_price"] == "2026-11-02"
    assert e["number"]["value"] == "6295.50" and e["source"]["kind"] == "calculation"


@pytest.fixture
def boq(tmp_path):
    rec = sample_project(tmp_path)
    add_sample_boq(rec)
    yield rec
    rec.close()


def test_the_sample_boq_by_hand_through_the_tools(boq):
    check_the_sample(boq, lambda tool, payload: call(boq, tool, payload, actor="lead-qs"))


def test_the_sample_boq_by_hand_through_the_core_api(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        pid = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
        rec = client.app.state.projects.get(pid)
        with rec.write(ACTOR) as conn:
            for kind, title in SOURCES.items():
                ledger.write_source(conn, at=rec.clock(), actor=ACTOR, kind=kind, title=title)
        add_sample_boq(rec)
        base = f"/projects/{pid}"

        def send(tool: str, payload: dict) -> dict:
            if tool == "calculate":
                r = client.post(f"{base}/calc", json=payload, headers=AUTH)
            elif tool == "explain_number":
                r = client.get(f"{base}/numbers/{payload['number']}/explain", headers=AUTH)
            elif payload["apply"]:
                r = client.post(f"{base}/calc/recalculate", headers=AUTH)
            else:
                r = client.get(f"{base}/calc/stale", headers=AUTH)
            assert r.status_code in (200, 201), r.json()
            return r.json()

        check_the_sample(rec, send)


def test_print_the_rate_trace_for_review(boq, capsys):
    """Prints the rate build-up's steps and each input's source and date, for the founder.

    Run: node scripts/python.mjs -m pytest core/tests/test_calc_sample_boq.py -s -k print"""
    reply = call(boq, "calculate", STEPS[0], actor="lead-qs")
    e = call(boq, "explain_number", {"number": reply["results"][0]["number"]}, actor="lead-qs")
    calc = e["calculation"]
    lines = [f"Rate for 1 m3 of concrete, 03/02 = {e['number']['value']} EGP/m3", calc["formula"]]
    lines.append("Steps:")
    for s in calc["steps"]:
        args = ", ".join(f"{a['value']} {a['unit']}".strip() for a in s["args"])
        factor = f"  (× {s['factor']})" if "factor" in s else ""
        lines.append(f"  {s['n']}. {s['text']}: {args} → {s['value']} {s['unit']}{factor}")
    lines.append("Inputs:")
    for i in calc["inputs"]:
        source = i["source"]["title"]
        lines.append(f"  {i['name']} = {i['value']} {i['unit']} ({source}, {i['dated']})")
    for c in calc["constants"]:
        lines.append(f"  constant {c['value']}{c['unit']} at character {c['at']}")
    for name, spec in STEPS[0]["inputs"].items():
        if "constant" in spec:
            lines.append(f"  {name} = {spec['constant']} {spec['unit']} (stated: {spec['why']})")
    text = "\n".join(lines)
    with (
        capsys.disabled()
    ):  # shown with -s; bytes, since a Windows console is cp1252 and has no "→"
        sys.stdout.buffer.write(("\n" + text + "\n").encode("utf-8"))
        sys.stdout.flush()
    assert "6484.50" in text and SOURCES["exchange_rate"] in text
