"""The bench's fake AI: model connectors whose models are a scripted brain, never a real provider.

The brain is stateless: each request it reads what it was given (the tools offered, the output
tool, the Brief, the tool results so far) and picks the next step of the Brief's scenario. A
scenario is chosen by a keyword in the Brief: "bench:chat", "bench:question", "bench:boq",
"bench:deliverable", "bench:team", "bench:view" (a view of the first item's numbers); the Briefs
One starts itself (a tender folder's "I understood this", a project's lessons) have their own;
anything else is the full tender walk-through.
Each step is tried once: a tool that refuses is noted in core.log and the brain moves on, so it
never loops. Every text it writes says it is a bench reply, and it writes no number of its own.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import uuid4

from pydantic_ai.messages import (
    ModelRequest,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.profiles import ModelProfile

from qsone import copy
from qsone.engine.types import ModelCard, ModelChoice
from tests.engine_fakes import Scripted, Step, _stream_usage

log = logging.getLogger("qsone.bench")

USAGE = (600, 120)  # tokens in and out of every bench response: 0.0012 USD at the sample prices
PRICE_SOURCE = "bench sample price, not real"
SCENARIOS = (
    *("chat", "question", "boq", "deliverable", "team", "full", "understand", "lessons", "view"),
)
_KEYWORD = re.compile(r"bench:(\w+)")
_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")
# a files_list line: file:<id> | <name> | [in folder <folder> |] <kind> | …
_FILE = re.compile(r"file:([0-9a-f]{32}) \| ([^|]+?) \| (?:in folder [^|]+ \| )?(\w+)")
_NEXT_IMPORT = re.compile(r"Next: boq_import (\{.*\})")
_MODEL = re.compile(r"You run on the model ([\w.:-]+)")


# What the brain sees -------------------------------------------------------------------------


@dataclass
class Seen:
    """One request, read: the Brief (the last user prompt), its language and scenario, and
    each bench step done since, with its result text and whether the tool took it."""

    tools: set[str]
    brief: str
    lang: str  # "ar" | "en"
    scenario: str
    done: dict[str, tuple[str, bool]]  # step -> (result text, ok)
    used: dict[str, str] = field(default_factory=dict)  # step -> the tool it called
    model: str = ""  # the model it runs as, from One's own instructions
    effort: str | None = None  # the `thinking` setting One sent, if any


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


def language(text: str) -> str:
    text = _KEYWORD.sub("", text)
    return "ar" if len(_ARABIC.findall(text)) >= len(_LATIN.findall(text)) else "en"


def read(messages: list, info: AgentInfo) -> Seen:
    start, brief = 0, ""
    for i, message in enumerate(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    start, brief = i, part.content
    steps: dict[str, str] = {}  # tool call id -> step
    done: dict[str, tuple[str, bool]] = {}
    used: dict[str, str] = {}
    for message in messages[start:]:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_call_id.startswith("bench-"):
                steps[part.tool_call_id] = part.tool_call_id.split("-")[1]
                used[steps[part.tool_call_id]] = part.tool_name
                done.setdefault(steps[part.tool_call_id], ("", False))
            elif isinstance(part, ToolReturnPart) and part.tool_call_id in steps:
                done[steps[part.tool_call_id]] = (_text(part.content), True)
            elif isinstance(part, RetryPromptPart) and part.tool_call_id in steps:
                step = steps[part.tool_call_id]
                done[step] = (_text(part.content), False)
                log.warning("bench: %s refused %s: %s", part.tool_name, step, _text(part.content))
    found = _KEYWORD.search(brief)
    scenario = found.group(1) if found and found.group(1) in SCENARIOS else "full"
    if brief in copy.UNDERSTAND_BRIEF.values():  # the Brief a tender folder's import starts
        scenario = "understand"
    elif brief in copy.LESSONS_BRIEF.values():  # the one closing a project starts
        scenario = "lessons"
    tools = {t.name for t in info.function_tools}
    model = _MODEL.search(info.instructions or "")
    effort = info.model_request_parameters.thinking  # PydanticAI moves `thinking` here
    seen = Seen(tools, brief, language(brief), scenario, done, used)
    seen.model = model.group(1) if model else ""
    seen.effort = effort if isinstance(effort, str) else None
    return seen


def _call(step: str, tool: str, args: dict) -> Step:
    part = ToolCallPart(tool, args, tool_call_id=f"bench-{step}-{uuid4().hex[:8]}")
    return Step((part,), USAGE)


def _say(text: str) -> Step:
    return Step((TextPart(text),), USAGE)


def _words(seen: Seen, en: str, ar: str) -> str:
    return ar if seen.lang == "ar" else en


def _data(result: str) -> dict:
    for line in result.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except ValueError:
                return {}
    try:
        found = json.loads(result)
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def _files(seen: Seen) -> list[tuple[str, str, str]]:
    return _FILE.findall(seen.done.get("files", ("", False))[0])


def _file(seen: Seen, kinds: tuple[str, ...]) -> str | None:
    return next((f for f, _, kind in _files(seen) if kind.lower() in kinds), None)


# The Lead QS in a project --------------------------------------------------------------------


def _files_step(seen: Seen) -> Step:
    return _call("files", "files_list", {})


def _read_spec(seen: Seen) -> Step | None:
    found = _file(seen, ("docx", "pdf", "word"))
    return None if found is None else _call("spec", "files_read", {"file_id": found})


def _preview(seen: Seen) -> Step | None:
    found = _file(seen, ("xlsx", "xls", "excel"))
    return None if found is None else _call("preview", "boq_preview", {"file_id": found})


def _import(seen: Seen) -> Step | None:
    result, ok = seen.done.get("preview", ("", False))
    found = _NEXT_IMPORT.search(result) if ok else None
    if found is None:
        return None
    args = json.loads(found.group(1))
    columns = args.get("columns", {})
    if "rate" in columns or "amount" in columns:
        args["currency"] = "EGP"
    return _call("import", "boq_import", args)


def _items(seen: Seen) -> Step | None:
    if not seen.done.get("import", ("", False))[1]:
        return None
    return _call("items", "find_items", {"kind": "boq_item"})


def _ask(seen: Seen) -> Step:
    if seen.lang == "ar":
        questions = [
            {
                "id": "q1",
                "text": "سؤال تجريبي: الخرسانة جاهزة ولا خلط في الموقع؟",
                "options": ["جاهزة", "خلط في الموقع"],
            },
            {"id": "q2", "text": "سؤال تجريبي: عندك ملاحظة على بنود الحفر؟", "free_text": True},
        ]
    else:
        questions = [
            {
                "id": "q1",
                "text": "Bench question: ready-mix concrete or mixed on site?",
                "options": ["Ready-mix", "Mixed on site"],
            },
            {
                "id": "q2",
                "text": "Bench question: any note on the excavation items?",
                "free_text": True,
            },  # fmt: skip
        ]
    return _call("ask", "ask_engineer", {"questions": questions})


def _plan(seen: Seen) -> Step:
    # Just enough requests that, at the sample prices and the assumed tokens of a new project,
    # the plan is over the Brief Budget's threshold (0.50 USD): One asks the engineer first (the
    # approval card of the walks), about 0.6 USD and 15 minutes.
    name = _words(seen, "Estimator (bench)", "مهندس التسعير (تجريبي)")
    task = _words(seen, "Sample prices for the BOQ", "أسعار عينة لجدول الكميات")
    steps = [{"specialist": name, "task": task, "requests": 20},
             {"specialist": name, "task": task, "requests": 20}]  # fmt: skip
    deliverable = _words(seen, "Priced BOQ (bench sample)", "جدول كميات مسعر (عينة تجريبية)")
    return _call("plan", "plan_brief", {"steps": steps, "deliverables": [deliverable]})


ESTIMATOR = (
    "You are the bench Estimator, a stand-in specialist of the QS Mind ONE test bench. You "
    "propose sample prices to the engineer with prices_propose and report what was kept."
)


def _build(seen: Seen) -> Step | None:
    if "build_specialist" not in seen.tools:
        return None
    args = {
        "name_en": "Estimator (bench)",
        "name_ar": "مهندس التسعير (تجريبي)",
        "instructions": ESTIMATOR,
        "tools": ["prices_propose", "send_message"],
        "tier": "specialist",
    }
    return _call("build", "build_specialist", args)


def _delegate(seen: Seen) -> Step | None:
    result, ok = seen.done.get("build", ("", False))
    specialist = _data(result).get("specialist_id") if ok else None
    if not specialist:
        return None
    task = _words(
        seen,
        "Propose the sample prices for cement and rebar to the engineer, then report.",
        "اعرض أسعار العينة للأسمنت والحديد على المهندس، ثم اكتب تقريرك.",
    )
    return _call("delegate", "delegate", {"specialist_id": specialist, "task": task})


EXTRA_CODE = "99/01"  # the bench's own item: not in the client's BOQ, so the Checking QS flags it


def _extra(seen: Seen) -> Step | None:
    if not seen.done.get("import", ("", False))[1]:
        return None
    description = _words(
        seen,
        "Site hoarding (bench extra item, not in the client's BOQ)",
        "سور مؤقت للموقع (بند تجريبي زيادة، مش في مقايسة العميل)",
    )
    args = {"kind": "boq_item", "code": EXTRA_CODE, "fields": {"description": description}}
    return _call("extra", "add_item", args)


def _sheet(seen: Seen) -> Step | None:
    result, ok = seen.done.get("items", ("", False))
    items = [i["id"] for i in _data(result).get("items", []) if isinstance(i, dict)] if ok else []
    if not items:
        return None
    result, ok = seen.done.get("extra", ("", False))
    extra = _data(result).get("item_id") if ok else None
    if extra:
        items.append(extra)
    section = _words(seen, "Sample works (bench)", "أعمال عينة (تجريبي)")
    rows = [{"section": section, "level": 1}, *({"item_id": i} for i in items)]
    args = {
        "kind": "sheet",
        "variant": "boq",
        "title": _words(seen, "Priced BOQ (bench sample)", "جدول كميات مسعر (عينة تجريبية)"),
        "language": seen.lang,
        "rows": rows,
    }
    return _call("sheet", "deliverable_create", args)


def _letter(seen: Seen) -> Step:
    def block(kind: str, text: str) -> dict:
        return {"type": kind, "children": [{"text": text}]}

    blocks = [
        block(
            "h1", _words(seen, "Tender cover letter (bench sample)", "خطاب العطاء (عينة تجريبية)")
        ),
        block(
            "p",
            _words(
                seen,
                "This letter is sample text written by the QS Mind ONE test bench.",
                "هذا الخطاب نص عينة كتبته منصة اختبار كيو إس مايند وان.",
            ),
        ),
    ]
    args = {
        "kind": "document",
        "variant": "letter",
        "title": _words(seen, "Cover letter (bench sample)", "خطاب العطاء (عينة تجريبية)"),
        "language": seen.lang,
        "blocks": blocks,
    }
    return _call("letter", "deliverable_create", args)


def _understood(seen: Seen) -> Step | None:
    """The "I understood this" card: every fact a bench sample, each with a place in the BOQ, the
    count from the BOQ import, and every file sorted."""
    boq = _file(seen, ("xlsx", "xls", "excel"))
    if boq is None:
        return None

    def at(row: int, value: str) -> dict:
        return {"value": value, "file_id": boq, "locator": {"sheet": "BOQ", "row": row}}

    def label(kind: str) -> str:
        if kind.lower() in ("xlsx", "xls", "excel"):
            return _words(seen, "BOQ (bench)", "مقايسة (تجريبي)")
        if kind.lower() in ("docx", "pdf"):
            return _words(seen, "Specification (bench)", "مواصفات (تجريبي)")
        return _words(seen, "Other (bench)", "ملفات تانية (تجريبي)")

    why = _words(seen, "Bench sample sort", "تقسيم عينة من منصة الاختبار")
    args: dict = {
        "client": at(1, _words(seen, "Sample client (bench, not real)", "عميل تجريبي (عينة)")),
        "submission_date": at(1, "2026-12-01"),
        "contract_type": at(2, _words(seen, "Re-measured (bench sample)", "إعادة قياس (عينة)")),
        "missing": [_words(seen, "Soil report (bench sample)", "تقرير التربة (عينة تجريبية)")],
        "files": [{"file_id": f, "label": label(kind), "why": why} for f, _, kind in _files(seen)],
    }
    result, ok = seen.done.get("import", ("", False))
    trace = _data(result).get("import_id") if ok else None
    if trace:
        args["items_count"] = {"value": "0", "trace_id": trace}  # the value saved is the import's
    return _call("understood", "understood", args)


def _lesson(seen: Seen) -> Step:
    text = _words(
        seen,
        "(bench sample lesson) Check the BOQ units before pricing.",
        "(درس عينة من منصة الاختبار) راجع وحدات المقايسة قبل التسعير.",
    )
    return _call("lesson", "note_lesson", {"text": text, "kind": "method"})


def _first_item_numbers(seen: Seen) -> Step | None:
    result, ok = seen.done.get("items", ("", False))
    items = [i["id"] for i in _data(result).get("items", []) if isinstance(i, dict)] if ok else []
    return _call("numbers", "ledger_numbers", {"item": items[0]}) if items else None


def _view(seen: Seen) -> Step | None:
    """A view of the first imported item's numbers (decision 16.1): each figure and each number
    cell a reference to a ledger number, so the screen shows it with its source chip."""
    result, ok = seen.done.get("numbers", ("", False))
    numbers = [n for n in _data(result).get("numbers", []) if isinstance(n, dict)] if ok else []
    if not numbers:
        return None
    columns = [
        {"key": "name", "label": _words(seen, "Number", "الرقم"), "type": "text"},
        {"key": "value", "label": _words(seen, "Value", "القيمة"), "type": "number"},
    ]
    note = _words(
        seen,
        "(bench reply, not a real AI) Each figure opens its source.",
        "(رد تجريبي من منصة الاختبار، وليس ذكاء اصطناعي حقيقي) كل رقم بيفتح مصدره.",
    )
    blocks = [
        {"kind": "heading", "text": _words(seen, "First BOQ item (bench)", "أول بند (تجريبي)")},
        {
            "kind": "figures",
            "items": [{"label": n["name"], "value": {"number": n["id"]}} for n in numbers[:4]],
        },
        {
            "kind": "table",
            "columns": columns,
            "rows": [{"name": n["name"], "value": {"number": n["id"]}} for n in numbers],
        },
        {
            "kind": "group",
            "title": _words(seen, "About this view", "عن العرض ده"),
            "blocks": [{"kind": "prose", "text": note}],
        },
    ]
    title = _words(seen, "BOQ at a glance (bench sample)", "نظرة على المقايسة (عينة تجريبية)")
    return _call("view", "show", {"title": title, "sample": True, "blocks": blocks})


BOQ = (_files_step, _preview, _import, _items)
LEAD_SCENARIOS: dict[str, tuple[Callable[[Seen], Step | None], ...]] = {
    "chat": (),
    "question": (_ask,),
    "boq": BOQ,
    "deliverable": (*BOQ, _extra, _sheet, _letter),  # with one priced row of our own
    "team": (_plan, _build, _delegate),
    "understand": (_files_step, _preview, _import, _understood),
    "lessons": (_lesson,),
    "view": (*BOQ, _first_item_numbers, _view),
    "full": (
        _files_step,
        _read_spec,
        _preview,
        _import,
        _ask,
        _plan,
        _build,
        _delegate,
        _items,
        _sheet,
        _letter,
    ),
}
_STEP_OF = {
    _files_step: "files",
    _read_spec: "spec",
    _preview: "preview",
    _import: "import",
    _items: "items",
    _extra: "extra",
    _ask: "ask",
    _plan: "plan",
    _build: "build",
    _delegate: "delegate",
    _sheet: "sheet",
    _letter: "letter",
    _understood: "understood",
    _lesson: "lesson",
    _first_item_numbers: "numbers",
    _view: "view",
}


def _report(seen: Seen) -> str:
    def said(ok: bool) -> list[str]:  # each step in the Progress Line's own words, never a tool id
        return [
            copy.tool_step(seen.used.get(s, ""))[seen.lang]
            for s, (_, k) in seen.done.items()
            if k is ok
        ]

    refused, done = said(False), said(True)
    if seen.lang == "ar":
        text = "(رد تجريبي من منصة الاختبار، وليس ذكاء اصطناعي حقيقي) "
        text += "اللي اتعمل: " + ("، ".join(done) if done else "لا شيء") + "."
        if refused:
            text += " رفضت الأدوات: " + "، ".join(refused) + "."
        return text
    text = "(bench reply, not a real AI) Steps done: " + (", ".join(done) or "none") + "."
    if refused:
        text += " Refused by the tools: " + ", ".join(refused) + "."
    return text


def lead(seen: Seen) -> Step:
    for step in LEAD_SCENARIOS[seen.scenario]:
        if _STEP_OF[step] in seen.done:
            continue
        found = step(seen)
        if found is not None and found.parts[0].tool_name in seen.tools:
            return found
    if seen.scenario == "chat":
        return _say(
            _words(
                seen,
                "(bench reply, not a real AI) Hello from the QS Mind ONE test bench. "
                f"Model: {seen.model}. Effort: {seen.effort or 'default'}.",
                "(رد تجريبي من منصة الاختبار، وليس ذكاء اصطناعي حقيقي) أهلا من منصة اختبار "
                f"كيو إس مايند وان. الموديل: {seen.model}. عمق التفكير: "
                f"{seen.effort or 'الافتراضي'}.",
            )
        )
    return _say(_report(seen))


# The other agents ----------------------------------------------------------------------------


def _today() -> str:
    return date.today().isoformat()


def specialist(seen: Seen) -> Step:
    if "send_message" in seen.tools and "hello" not in seen.done:
        text = _words(
            seen, "(bench) Starting on the sample prices.", "(تجريبي) بدأت في أسعار العينة."
        )
        return _call("hello", "send_message", {"to": "lead", "text": text})
    if "prices_propose" in seen.tools and "prices" not in seen.done:
        rows = [
            {
                "description": _words(
                    seen, "Portland cement (sample price)", "أسمنت بورتلاندي (سعر عينة)"
                ),
                "unit": _words(seen, "t", "طن"),
                "rate": "3950",
                "currency": "EGP",
                "dated": _today(),
                "vat": "incl",
            },
            {
                "description": _words(
                    seen, "Rebar 16 mm (sample price)", "حديد تسليح ١٦ مم (سعر عينة)"
                ),
                "unit": _words(seen, "t", "طن"),
                "rate": "38500",
                "currency": "EGP",
                "dated": _today(),
                "vat": "incl",
            },
        ]
        return _call("prices", "prices_propose", {"rows": rows, "from": "chat", "where": "project"})
    return _say(_report(seen))


def general(seen: Seen) -> Step:
    if "projects" in seen.tools and "projects" not in seen.done:
        return _call("projects", "projects", {})
    return _say(_report(seen))


def brain(messages: list, info: AgentInfo) -> Step:
    seen = read(messages, info)
    if info.output_tools:  # the Checking QS: its verdict is the output tool
        tool = info.output_tools[0]
        verdict = {
            "code": "A",
            "comments": [{"about": "bench", "text": "(bench check) Sample review, no finding."}],
        }
        if "not in the client's imported BOQ" in seen.brief:  # One's code found such rows
            text = "(bench check) Rows not in the client's BOQ: the engineer keeps or removes each."
            verdict = {"code": "B", "comments": [{"about": EXTRA_CODE, "text": text}]}
        part = ToolCallPart(tool.name, verdict, tool_call_id=f"bench-verdict-{uuid4().hex[:8]}")
        return Step((part,), USAGE)
    if "boq_import" in seen.tools and "ask_engineer" in seen.tools:
        return lead(seen)
    if "hand_to_project" in seen.tools:
        return general(seen)
    if seen.tools:
        return specialist(seen)
    return _say(_words(seen, "(bench reply, not a real AI)", "(رد تجريبي من منصة الاختبار)"))


# The model and its connectors ----------------------------------------------------------------


class BenchModel(Scripted):
    """A `FunctionModel` driven by `brain`, streamed in small chunks like a real model."""

    def __init__(self, model_name: str) -> None:
        super().__init__([], model_name=model_name)
        self._profile = ModelProfile(supports_thinking=True)  # else PydanticAI drops `thinking`

    async def _next(self, messages: list, info: AgentInfo) -> Step:
        self.calls += 1
        return brain(messages, info)

    async def _stream(self, messages: list, info: AgentInfo):
        step = await self._next(messages, info)
        _stream_usage.set(step.usage)
        texts = [p.content for p in step.parts if isinstance(p, TextPart)]
        if texts:
            words = " ".join(texts).split(" ")
            for i in range(0, len(words), 4):
                yield " ".join(words[i : i + 4]) + (" " if i + 4 < len(words) else "")
            return
        from pydantic_ai.models.function import DeltaToolCall

        yield {
            i: DeltaToolCall(p.tool_name, p.args_as_json_str(), tool_call_id=p.tool_call_id)
            for i, p in enumerate(step.parts)
        }


@dataclass
class BenchConnector:
    """A model connector of the bench. Its models are `BenchModel`s at sample prices."""

    id: str
    name: str
    provider: str
    models: tuple[tuple[str, str, str, str], ...]  # (id, name, price in, price out)
    kind: str = "model"
    on_device: bool = False
    # the bench's own effort levels and default, per model id, so the walks can pick and cycle
    efforts: dict[str, tuple[tuple[str, ...], str | None]] = field(default_factory=dict)

    async def cards(self) -> list[ModelCard]:
        return [
            ModelCard(
                choice=ModelChoice(self.id, model),
                name=name,
                provider=self.provider,
                images=False,  # never asked to read a scanned page
                tools=True,
                context=200_000,
                price_in=Decimal(price_in),
                price_out=Decimal(price_out),
                price_source=PRICE_SOURCE,
                efforts=self.efforts.get(model, ((), None))[0],
                effort_default=self.efforts.get(model, ((), None))[1],
            )
            for model, name, price_in, price_out in self.models
        ]

    def model(self, model_id: str) -> BenchModel:
        return BenchModel(model_id)


EFFORTS = ("low", "medium", "high")


def connectors() -> list[BenchConnector]:
    """Two connectors of two providers, so the Checking QS is not a Same-provider check. The
    lead model takes an effort with a known default (as Claude's "high"), the specialist one
    with none known, and the checker none at all (the message box hides the effort)."""
    return [
        BenchConnector(
            "bench",
            "Bench (fake AI)",
            "bench",
            (
                ("bench-lead", "Bench lead (fake AI)", "1", "5"),
                ("bench-specialist", "Bench specialist (fake AI)", "0.5", "2"),
            ),
            efforts={"bench-lead": (EFFORTS, "high"), "bench-specialist": (EFFORTS, None)},
        ),
        BenchConnector(
            "bench-check",
            "Bench checker (fake AI)",
            "bench-check",
            (("bench-checker", "Bench checker (fake AI)", "1", "5"),),
        ),
    ]


ROLES = {
    "lead": ModelChoice("bench", "bench-lead"),
    "checker": ModelChoice("bench-check", "bench-checker"),
    "specialist": ModelChoice("bench", "bench-specialist"),
    "quick": ModelChoice("bench", "bench-specialist"),
}
