"""What to keep (Plan 5, decision 20): personal data in an item's fields is kept only when the
engineer said so, once per kind, for every project.

- `personal` finds six kinds by field name (English and Arabic lists) and by value pattern:
  phone (Egyptian 01x mobiles, +20, +966, +971, 00…), email, a person's name, address, ID
  number and WhatsApp. A company's or an item's name is not a person's.
- The first time a kind appears, `apply` asks keep / never in a question card, and the answer
  is saved per kind in `keep_policy` in Engineer Records. "Never" drops the field.
- Tasks 6, 10 and 12 run `personal` (or `apply`) on what goes out in a web query, a price
  proposal's supplier or a Connector call.

No PydanticAI here."""

import re
from uuid import uuid4

from qsone import copy
from qsone.engine.types import Card, read_answer
from qsone.records import arabic, audit
from qsone.records.project import Records

KINDS = ("phone", "email", "person_name", "address", "national_id", "whatsapp")
KEEP, NEVER = "keep", "never"
QUESTION = "keep"  # the one question's id in the card
ENGINEER = "engineer"  # the actor of a what-to-keep answer: the engineer chose
_ARABIC = re.compile("[\u0600-\u06ff]")


def _words(names: str) -> frozenset[str]:
    """Each name as `_tokens` gives it, so Arabic letters fold the same way as a field's."""
    return frozenset(t for name in names.split() for t in _tokens(name))


def _tokens(key: str) -> list[str]:
    parts = re.findall(r"[^\W_]+", key.lower())
    return [arabic.normalise(p) if _ARABIC.search(p) else p for p in parts]


_BY_NAME: tuple[tuple[str, frozenset[str]], ...] = (
    ("whatsapp", _words("whatsapp واتساب واتس وتساب")),
    ("national_id", _words("nid passport iqama قومي هوية إقامة")),
    ("email", _words("email mail إيميل ايميل بريد")),
    (
        "phone",
        _words("phone telephone tel mobile cellphone landline تليفون تلفون هاتف موبايل محمول جوال"),
    ),
    ("address", _words("address addr street عنوان شارع")),
    ("person_name", _words("contact person representative attn مسؤول مسئول مندوب شخص")),
)
_ID_PAIRS = {("national", "id"), ("id", "number"), ("emirates", "id"), ("id", "no")}
_NAMED_PERSON = {"contact", "person", "full", "first", "last", "engineer", "manager", "owner"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_RUN = re.compile(r"\+?\d[\d \-().]{6,}\d")  # a phone or ID number, with its separators
_PHONE = re.compile(r"01[0125]\d{8}|(?:\+|00)\d{8,14}")  # 01x, +20, +966, +971, 00…
_NATIONAL_ID = re.compile(r"[23]\d{13}|784\d{12}")  # Egypt's 14 digits; the UAE's 784…
_WHATSAPP_WORD = re.compile(r"whats\s?app|wa\.me|واتس|وتساب", re.IGNORECASE)


def _by_name(key: str) -> str | None:
    tokens = _tokens(key)
    for kind, words in _BY_NAME:
        if any(t in words for t in tokens):
            return kind
    pairs = set(zip(tokens, tokens[1:], strict=False))
    if pairs & _ID_PAIRS:
        return "national_id"
    if "name" in tokens and _NAMED_PERSON & set(tokens):
        return "person_name"
    return None


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, int) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list | tuple):
        return [s for v in value for s in _strings(v)]
    return []


def _by_value(value) -> str | None:
    text = " ".join(_strings(value)).translate(_DIGITS)
    if _EMAIL.search(text):
        return "email"
    numbers = [re.sub(r"[ \-().]", "", run) for run in _RUN.findall(text)]
    if any(_PHONE.fullmatch(n) for n in numbers):
        return "whatsapp" if _WHATSAPP_WORD.search(text) else "phone"
    if any(_NATIONAL_ID.fullmatch(n) for n in numbers):
        return "national_id"
    return None


def personal(fields: dict) -> dict[str, str]:
    """{field: kind} for each field that holds personal data, in the fields' order: by the
    field's name first, then by its value."""
    found = {}
    for key, value in fields.items():
        kind = _by_name(str(key)) or _by_value(value)
        if kind is not None:
            found[key] = kind
    return found


def decisions(eng: Records) -> dict[str, str]:
    """{kind: "keep" | "never"} as the engineer answered, from Engineer Records."""
    with eng.read() as c:
        return dict(c.execute("SELECT kind, decision FROM keep_policy").fetchall())


def decide(eng: Records, kind: str, decision: str, *, card_id: str) -> None:
    """Saves the engineer's answer for one kind, audited. An earlier answer is replaced."""
    at = eng.clock()
    with eng.write(ENGINEER) as c:
        before = c.execute(
            "SELECT decision, decided_at, card_id FROM keep_policy WHERE kind = ?", (kind,)
        ).fetchone()
        c.execute(
            "INSERT INTO keep_policy(kind, decision, decided_at, card_id) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(kind) DO UPDATE SET decision = excluded.decision,"
            " decided_at = excluded.decided_at, card_id = excluded.card_id",
            (kind, decision, at, card_id),
        )
        audit.record(
            c,
            at=at,
            actor=ENGINEER,
            action="create" if before is None else "update",
            table="keep_policy",
            row_id=kind,
            before=None
            if before is None
            else dict(zip(("decision", "decided_at", "card_id"), before, strict=True)),
            after={"decision": decision, "decided_at": at, "card_id": card_id},
        )


async def ask(ctx, card: Card) -> str:
    """Shows `card` and waits for the engineer's answer. The card is stored as pending before
    it is shown, as the gate's are, so a restart withdraws it and the redone call asks again."""
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)
    value = await ctx.host.ask(card)
    try:
        ctx.store.settle(card.id, value)
    except LookupError:
        pass  # the Brief Runner saved the answer itself
    return value


def _language(ctx) -> str:
    """The Brief's language: English when it has more Latin letters than Arabic, else Arabic."""
    text = ctx.store.brief(ctx.brief_id)["text"]
    latin = len(re.findall(r"[A-Za-z]", text))
    return "en" if latin > len(_ARABIC.findall(text)) else "ar"


async def _ask_kind(ctx, kind: str) -> tuple[str, str | None]:
    """The engineer's answer for one kind and the card it came from; (never, None) when the
    card came back with no answer (nothing is saved then, and nothing kept)."""
    lang, words = _language(ctx), copy.KEEP_KINDS[kind]
    options = [copy.KEEP_OPTION_KEEP[lang], copy.KEEP_OPTION_NEVER[lang]]
    question = {"id": QUESTION, "text": copy.fill(copy.KEEP_ASK, kind=words)[lang]}
    card = Card(
        id=uuid4().hex,
        kind="question",
        title=copy.fill(copy.KEEP_ASK, kind=words),
        detail=copy.fill(copy.KEEP_DETAIL, agent=ctx.agent.name, kind=words),
        options=("sent",),
        payload={"questions": [question | {"options": options}]},
    )
    answer = read_answer(card, await ask(ctx, card))["answers"].get(QUESTION)
    if answer in (KEEP, options[0]):
        return KEEP, card.id
    if answer in (NEVER, options[1]):
        return NEVER, card.id
    return NEVER, None


def _engineer_records(ctx) -> Records | None:
    return None if ctx.services is None else ctx.services.engineer()


async def apply(ctx, fields: dict) -> tuple[dict, dict]:
    """(the fields to keep, the fields dropped as {field: kind}). Asks once for each kind with
    no answer yet in Engineer Records, and saves the answer there. With no Engineer Records
    open, it asks each time and saves nothing."""
    found = personal(fields)
    if not found:
        return fields, {}
    eng = _engineer_records(ctx)
    policy = decisions(eng) if eng is not None else {}
    for kind in dict.fromkeys(found.values()):
        if kind in policy:
            continue
        policy[kind], card_id = await _ask_kind(ctx, kind)
        if eng is not None and card_id is not None:
            decide(eng, kind, policy[kind], card_id=card_id)
    dropped = {f: k for f, k in found.items() if policy[k] == NEVER}
    return {f: v for f, v in fields.items() if f not in dropped}, dropped


def dropped_note(dropped: dict) -> list[str]:
    """One English line per kind dropped, for the model: `KEEP_NEVER` with the kind."""
    kinds = dict.fromkeys(dropped.values())
    return [copy.fill(copy.KEEP_NEVER, kind=copy.KEEP_KINDS[k])["en"] for k in kinds]
