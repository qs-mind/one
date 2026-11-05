"""A Brief's work log: the real times of each step its team reported, and of the Brief itself,
which the screen settles to ("Worked for 2m · 6 steps"). Synthetic «عينة» data only."""

from qsone.engine.types import Progress
from qsone.engine.worklog import WorkLog

LEAD = {"en": "Lead QS", "ar": "كبير مهندسي الكميات"}
READ = {"en": "reading A-101.dwg", "ar": "بيقرا A-101.dwg"}
PAGES = {"en": "reading A-101.dwg, pages 1-3", "ar": "بيقرا A-101.dwg، صفحات 1-3"}
PRICE = {"en": "pricing - sample", "ar": "بيسعّر - عينة"}
T0, T1, T2, T3 = (f"2026-11-05T08:00:0{s}.000+00:00" for s in range(4))


def step(text, *, run="lead", tool=True):
    return Progress("b1", run, LEAD, text, tool=tool)


def test_a_tool_step_is_open_until_its_tools_return():
    log = WorkLog(started=T0)
    log.add(step(READ), T1)
    assert log.as_json()["steps"] == [{"agent": LEAD, "text": READ, "at": T1, "until": None}]
    assert log.tools_done("lead", T2)
    assert log.steps[0]["until"] == T2
    assert not log.tools_done("lead", T3)  # nothing open: no change to send


def test_words_from_inside_a_running_tool_update_its_step():
    log = WorkLog(started=T0)
    log.add(step(READ), T1)
    log.add(step(PAGES, tool=False), T2)
    [only] = log.steps
    assert only["text"] == PAGES and only["at"] == T1 and only["until"] is None


def test_parallel_tool_calls_of_one_answer_stay_open_together():
    log = WorkLog(started=T0)
    log.add(step(READ), T1)
    log.add(step(PRICE), T1)
    assert [s["until"] for s in log.steps] == [None, None]
    log.tools_done("lead", T2)
    assert [s["until"] for s in log.steps] == [T2, T2]


def test_a_plain_step_ends_the_one_before_it_of_the_same_agent_only():
    log = WorkLog(started=T0)
    log.add(step(READ, tool=False), T1)
    log.add(step(PRICE, run="rates", tool=False), T1)
    log.add(step(PAGES, tool=False), T2)
    assert [s["until"] for s in log.steps] == [T2, None, None]


def test_the_end_closes_every_step_and_stamps_the_brief():
    log = WorkLog(started=T0)
    log.add(step(READ), T1)
    log.end(T3)
    assert log.ended == T3 and log.steps[0]["until"] == T3
    assert log.as_json() == {
        "started": T0,
        "ended": T3,
        "steps": [{"agent": LEAD, "text": READ, "at": T1, "until": T3}],
    }


def test_saved_and_read_again_it_goes_on_from_where_it_was():
    log = WorkLog(started=T0)
    log.add(step(READ), T1)
    again = WorkLog.load(log.saved(), stopped_at=T2)
    # a step left open by a core that stopped ends at the last time the core wrote
    assert again.steps[0]["until"] == T2 and again.ended is None and again.started == T0
    again.add(step(PRICE), T3)
    assert len(again.as_json()["steps"]) == 2
