"""YAML scenarios against the same HTTP routes; cost records always come from ONE."""

import json
import os
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

import httpx

from qsone.cli.session import ROOT
from qsone.cli.texts import TEXT, CliError
from qsone.engine.truth import has_json


class Budget:
    def __init__(self, commands, maximum):
        self.c = commands.client
        self.real = commands.saved["mode"] == "real"
        try:
            self.maximum = Decimal(str(maximum))
        except InvalidOperation:
            raise CliError("walk") from None
        if not self.maximum.is_finite() or self.maximum < 0:
            raise CliError("walk")
        baseline = self.c.get("/costs")
        self.baseline = Decimal(baseline["month"])
        self.unpriced = baseline["unpriced"]["month"]
        self.hit = False

    def __call__(self, brief):
        try:
            costs = self.c.get("/costs")
        except (httpx.HTTPError, CliError):
            # A cap cannot be enforced without cost records. Stop, never keep spending blind.
            self.hit = True
        else:
            self.hit |= Decimal(costs["month"]) - self.baseline >= self.maximum
            self.hit |= self.real and costs["unpriced"]["month"] > self.unpriced
        if self.hit and brief:
            try:
                self.c.post(f"/briefs/{brief}/stop")
            except CliError as error:
                if (error.detail or {}).get("status") != 409:
                    raise
        return self.hit


def normal(value):
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
    return str(value).translate(table).replace(",", "").replace("٬", "").casefold()


def same_number(left, right):
    try:
        return Decimal(normal(left)) == Decimal(normal(right))
    except InvalidOperation:
        return False


def test_files():
    override = os.environ.get("QSONE_TEST_FILES")
    if override:
        return Path(override)
    for root in (ROOT, *ROOT.parents):
        if (root / "docs/test-files").is_dir():
            return root / "docs/test-files"
    return ROOT / "docs/test-files"


def expand(value, variables):
    if isinstance(value, str):
        for key, replacement in variables.items():
            value = value.replace("{" + key + "}", str(replacement))
        return value
    if isinstance(value, list):
        return [expand(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: expand(item, variables) for key, item in value.items()}
    return value


class Walk:
    def __init__(self, commands):
        self.commands = commands
        self.c = commands.client
        self.project = None
        self.files = []
        self.last = {"reply": "", "cards": []}
        self.cards = []
        self.boq = {"client_boqs": [], "sheets": []}
        self.original_items = None

    def remember(self, result):
        self.last = result
        self.cards.extend(result.get("cards", []))

    def rows(self):
        return [row for sheet in self.boq["sheets"] for row in sheet["rows"]]

    def check(self, name, expected):
        reply = normal(self.last.get("reply", ""))
        if name in ("reply_contains", "reply_lacks"):
            values = expected if isinstance(expected, list) else [expected]
            matches = [normal(v) in reply for v in values]
            return all(matches) if name == "reply_contains" else not any(matches)
        if name == "no_raw":
            raw = self.last.get("reply", "")
            return not re.search(r"\b[0-9a-f]{32}\b", raw, re.I) and not has_json(raw)
        if name in ("boq_items", "boq_sections"):
            kind = "item" if name == "boq_items" else "section"
            return sum(row["kind"] == kind for row in self.rows()) == int(expected)
        if name == "items_unchanged":
            current = {r["item_id"] for r in self.rows() if r["kind"] == "item"}
            return self.original_items is not None and current == self.original_items
        if name == "card_meanings":
            return any(
                all(
                    {
                        r.get("column"): r.get("meaning")
                        for r in card.get("payload", {}).get("rows", [])
                    }.get(k)
                    == v
                    for k, v in expected.items()
                )
                for card in self.cards
            )
        if name == "max_usd":
            costs = self.c.get("/costs", brief_id=self.last.get("brief_id"))
            return costs["brief"] is not None and Decimal(costs["brief"]) <= Decimal(str(expected))
        if name == "cited":
            # Check the requested page/row only, not metadata or an unrelated sheet row.
            file = self.files[int(expected.get("file", 0))]["id"]
            base = f"/projects/{self.project}/files/{file}"
            if "page" in expected:
                found = self.c.get(base + "/text", page=expected["page"])
                text = " ".join(p["text"] for p in found["pieces"])
            else:
                found = self.c.get(base + "/sheet", name=expected.get("sheet"))
                rows = [r for r in found["rows"] if r["code"] == str(expected["row"])]
                text = " ".join(cell["text"] for r in rows for cell in r["cells"].values())
            value = normal(expected["value"])
            return value in reply and value in normal(text)
        if name == "quantity_rows":
            file = self.files[int(expected.get("file", 0))]["id"]
            raw = self.c.get(
                f"/projects/{self.project}/files/{file}/sheet", name=expected.get("sheet")
            )
            wanted = set(range(int(expected["first"]), int(expected["last"]) + 1))
            originals = {
                int(r["code"]): r["cells"] for r in raw["rows"] if int(r["code"]) in wanted
            }
            found = {}
            for sheet in self.boq["sheets"]:
                if sheet["file_id"] != file:
                    continue
                for row in sheet["rows"]:
                    qty = row["cells"].get("quantity", {})
                    source = sheet["sources"].get(qty.get("source"), {})
                    loc = source.get("locator", {})
                    if loc.get("row") in wanted and loc.get("sheet") == raw["sheet"]:
                        found[loc["row"]] = (qty.get("value"), loc.get("column"))
            return set(originals) == wanted and all(
                not originals[r].get("F", {}).get("text")
                and found.get(r, (None, None))[1] == expected.get("column", "D")
                and same_number(found[r][0], originals[r].get("D", {}).get("text", ""))
                for r in wanted
            )
        raise CliError("walk")

    def step(self, step):
        if "project" in step:
            name = step["project"]
            self.project = self.c.post("/projects", {"name": name})["id"]
            return {"project": self.project}
        if "files" in step:
            paths = step["files"]
            self.commands.files_add(self.project, paths)
            self.files = self.c.get(f"/projects/{self.project}/files")["files"]
            return self.commands.files_report(self.project)
        if "ask" in step:
            self.remember(self.commands.ask(self.project or "general", step["ask"]))
            rules = step.get("answer", {})
            # Explicit rules only: never auto-approve unknown cards or billable operations.
            for _ in range(40):
                if self.last.get("state") == "money_cap":
                    break
                cards = self.last.get("cards", [])
                if not cards:
                    break
                card = cards[0]
                rule = rules.get(card["kind"])
                if rule is None:
                    break
                if isinstance(rule, str):
                    rule = {"choice": rule}
                self.remember(
                    self.commands.answer(
                        card["id"], rule["choice"], rule.get("answers"), rule.get("rows", "all")
                    )
                )
            else:
                raise CliError("walk")
            return self.last
        if "card" in step:
            rule = step["card"]
            card = next(
                (c for c in self.last.get("cards", []) if c["kind"] == rule.get("kind", c["kind"])),
                None,
            )
            if card is None:
                raise CliError("answer")
            self.remember(
                self.commands.answer(
                    card["id"], rule["choice"], rule.get("answers"), rule.get("rows", "all")
                )
            )
            return self.last
        if "boq" in step:
            self.boq = self.commands.boq(self.project)
            if self.original_items is None:
                self.original_items = {r["item_id"] for r in self.rows() if r["kind"] == "item"}
            return self.boq
        if "check" in step:
            return {
                "checks": [
                    {"check": name, "expected": expected, "pass": self.check(name, expected)}
                    for name, expected in step["check"].items()
                ]
            }
        raise CliError("walk")


def run(commands, file, *, max_usd=None, report=None):
    import yaml  # Already locked; only walk needs it.

    try:
        document = yaml.safe_load(Path(file).read_text())
    except yaml.YAMLError:
        raise CliError("walk") from None
    if not isinstance(document, dict):
        raise CliError("walk")
    variables = {
        "samples": commands.saved.get("samples", ""),
        "test_files": test_files(),
        "run": uuid4().hex[:8],
    }
    document = expand(document, variables)
    began = time.monotonic()
    result = {
        "name": document.get("name", Path(file).stem),
        "mode": commands.saved["mode"],
        "at": datetime.now().astimezone().isoformat(),
        "source": "ONE /costs",
        "steps": [],
    }
    missing = [p for p in document.get("needs", []) if not Path(p).is_file()]
    if missing:
        result.update(status="SKIPPED", missing=missing)
    else:
        steps = document.get(commands.saved["mode"])
        if not isinstance(steps, list) or not steps:
            raise CliError("walk")
        budget = Budget(commands, max_usd if max_usd is not None else document.get("max_usd", 3))
        previous_guard, commands.guard = commands.guard, budget
        walk = Walk(commands)
        result["status"] = "PASS"
        try:
            for index, step in enumerate(steps):
                started = time.monotonic()
                entry = {"step": index + 1, "status": "PASS"}
                if budget.hit:
                    entry.update(status="NOT_RUN", reason=TEXT["cap"])
                else:
                    try:
                        output = walk.step(step)
                        if "checks" in output:
                            entry["checks"] = output["checks"]
                            if not all(check["pass"] for check in output["checks"]):
                                entry["status"] = result["status"] = "FAIL"
                        if output.get("state") == "failed":
                            entry["status"] = result["status"] = "FAIL"
                        entry["costs"] = commands.client.get(
                            "/costs", brief_id=walk.last.get("brief_id")
                        )
                        # Also checks the final response, which can settle between stream polls.
                        if budget(walk.last.get("brief_id")):
                            entry["status"] = result["status"] = "CAP"
                    except CliError as error:
                        entry.update(status="FAIL", error=error.text)
                        result["status"] = "FAIL"
                entry["seconds"] = round(time.monotonic() - started, 3)
                result["steps"].append(entry)
        finally:
            commands.guard = previous_guard
        result["costs"] = commands.client.get("/costs")
    result["seconds"] = round(time.monotonic() - began, 3)
    if report:
        Path(report).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result
