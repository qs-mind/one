"""What the engineer reads is words and views, never ONE's insides (the real walk, 6 Nov 2026):
the Brissa reply carried the raw JSON of a view, and a red "blanks" line full of hex ids; the
breakdown table showed twice in one reply. Scripted models only; synthetic «عينة» data only."""

# ruff: noqa: F811 (the fixtures, imported)

import json

from qsone.engine import truth
from qsone.engine.runner import _stored_events
from qsone.engine.truth import Brief
from tests.engine_fakes import scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import (  # noqa: F401 - the runner's fixtures
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    store_of,
)
from tests.test_truth_runner import datas, reply
from tests.test_view import figures, ledger, show, views  # noqa: F401

HEX = "9f0c2a7e5b1d4c3a8e6f7a1b2c3d4e5f"
LEAKED = (
    "دي بيانات العقد - عينة:\n"
    f'{{"title": "بيانات العقد", "blocks": [{{"kind": "figures", "items": [{{"value": '
    f'{{"number": "{HEX}"}}}}]}}]}}\n'
    "راجعها قبل التسليم."
)


def test_ids_and_json_are_no_blanks():
    assert truth.placeholders(f'القيمة ["{HEX}"] من العقد') == []
    assert truth.placeholders(f"المرجع [{HEX}]") == []
    assert truth.placeholders('[{"number": "x"}]') == []
    assert truth.placeholders("اسم المقاول: [اسم المقاول]") == ["[اسم المقاول]"]


def test_json_in_a_reply_goes_back():
    kinds = {p.kind for p in truth.reply_problems(LEAKED, cov=None, did=Brief(), engineer_text="")}
    assert kinds == {"json"}


def test_a_reply_is_cleaned_of_json_and_ids():
    clean = truth.clean_reply(LEAKED, shown=False)
    assert "{" not in clean and HEX not in clean
    assert clean.startswith("دي بيانات العقد - عينة:") and clean.endswith("راجعها قبل التسليم.")
    table = "الأعلى - عينة:\n| البند | القيمة |\n|---|---|\n| خرسانة | 1,250 |\n| حديد | 980 |"
    assert truth.clean_reply(table, shown=False) == table
    assert truth.clean_reply(table, shown=True) == "الأعلى - عينة:"  # the view shows it


async def test_json_that_stays_is_never_shown(make_engine, project):
    lead = scripted(said(LEAKED), said(LEAKED))  # the retry did not fix it
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, "بيانات العقد")
    events = await finish(engine, brief)
    assert lead.calls == 2
    shown = reply(events)
    assert "{" not in shown and HEX not in shown and "راجعها قبل التسليم." in shown
    flags = [f for d in datas(events, "facts") for f in d.data["flags"]]
    assert not any(HEX in json.dumps(f, ensure_ascii=False) for f in flags)
    store = store_of(engine, project)
    replayed = _stored_events(store, store.brief(brief), engine)
    assert "{" not in reply(replayed) and HEX not in reply(replayed)


async def test_the_same_view_twice_shows_once(ledger):
    ctx, host, ids = ledger
    blocks = [figures({"number": ids["rate"]})]
    first = await show(ctx, blocks=blocks)
    again = await show(ctx, blocks=blocks)
    assert len(views(host)) == 1 and again["shown"] == first["shown"]
    assert "already" in again["note"]
