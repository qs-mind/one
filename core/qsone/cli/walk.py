"""YAML scenarios against the same HTTP routes; cost records always come from ONE."""

import json
import os
import re
import tempfile
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

import httpx

from qsone.cli.session import ROOT
from qsone.cli.texts import TEXT, CliError
from qsone.engine.truth import citations, has_json, promise


class Budget:
    def __init__(self, commands, maximum):
        self.c = commands.client
        self.real = commands.saved["mode"] != "scripted"
        try:
            self.maximum = Decimal(str(maximum))
        except InvalidOperation:
            raise CliError("walk") from None
        if not self.maximum.is_finite() or self.maximum < 0:
            raise CliError("walk")
        baseline = self.c.get("/costs")
        self.baseline = Decimal(baseline["month"])
        self.unpriced = baseline["unpriced"]["month"]
        self.hit = self.maximum == 0

    def stop(self, brief):
        if brief:
            try:
                self.c.post(f"/briefs/{brief}/stop")
            except CliError as error:
                if (error.detail or {}).get("status") != 409:
                    raise

    def __call__(self, brief):
        try:
            costs = self.c.get("/costs")
        except (httpx.HTTPError, CliError):
            # Unknown spend is a failed observation, never evidence that a cap was reached.
            # Stop active paid work rather than spending blind, but permit later fresh reads.
            if self.real:
                self.stop(brief)
            raise CliError("costs_unavailable") from None
        self.hit |= Decimal(costs["month"]) - self.baseline >= self.maximum
        self.hit |= self.real and costs["unpriced"]["month"] > self.unpriced
        if self.hit:
            self.stop(brief)
        return self.hit


def normal(value):
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
    return str(value).translate(table).replace(",", "").replace("٬", "").casefold()


def same_number(left, right):
    try:
        return Decimal(normal(left)) == Decimal(normal(right))
    except InvalidOperation:
        return False


def contains_value(text, value):
    if same_number(value, value):
        return any(
            same_number(number, value)
            for number in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w|\.\d)", normal(text))
        )
    return normal(value) in normal(text)


def content_text(node):
    if isinstance(node, dict):
        return (
            bool(str(node.get("text", "")).strip())
            or node.get("type") in ("num", "cell")
            or any(content_text(v) for v in node.values() if isinstance(v, (dict, list)))
        )
    return isinstance(node, list) and any(content_text(v) for v in node)


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


def capability(commands, name):
    if name == "libreoffice":
        from qsone.records.office import find_soffice

        return find_soffice() is not None
    if name == "ocr:ara":
        from qsone.meaning.download import installed
        from qsone.records.ocr import MODELS, find_tesseract

        data = commands.saved.get("data_dir")
        if data is None:
            raise CliError("walk")  # An attached core's model directory is unknown.
        return bool(find_tesseract()) and installed((MODELS,), Path(data) / "models")
    raise CliError("walk")


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
        self.deliverable = {}
        self.observed = {}
        self.evidence = {}
        self.variables = {}
        self.report = {}
        self.failed_action = False
        self.stop_requested = False

    def remember(self, result):
        self.last = result
        self.cards.extend(result.get("cards", []))

    def rows(self):
        return [row for sheet in self.boq["sheets"] for row in sheet["rows"]]

    def prepare_check(self, name, expected):
        """Read evidence before evaluating; check() itself never performs I/O."""
        if name in ("cited", "quantity_rows"):
            file = self.files[int(expected.get("file", 0))]["id"]
            base = f"/projects/{self.project}/files/{file}"
            self.evidence[name] = (
                self.c.get(base + "/text", page=expected.get("page"))
                if "page" in expected or "paragraph" in expected
                else self.c.get(base + "/sheet", name=expected.get("sheet"))
            )

    def check(self, name, expected):
        reply = normal(self.last.get("reply", ""))
        if name in ("reply_contains", "reply_lacks", "reply_not_contains"):
            values = expected if isinstance(expected, list) else [expected]
            matches = [normal(v) in reply for v in values]
            return all(matches) if name == "reply_contains" else not any(matches)
        if name == "reply_contains_any":
            return any(normal(value) in reply for value in expected)
        if name == "scan_report":
            return any(
                (f.get("pdf") or {}).get("needs_reading", 0) for f in self.report.get("files", [])
            )
        if name == "ocr_boxes":
            pieces = [p for p in self.observed.get("pieces", []) if p.get("text", "").strip()]
            return bool(pieces) and all(
                (p.get("locator") or {}).get("read_by") == "tesseract"
                and len((p.get("locator") or {}).get("box", [])) == 4
                for p in pieces
            )
        if name in ("changes_target", "pack_integrity", "calculated_numbers"):
            from qsone.cli import checks

            if name == "changes_target":
                return checks.changes_target(self.deliverable, self.observed, expected)
            if name == "pack_integrity":
                return checks.pack_integrity(self.observed, expected)
            return checks.calculated_numbers(self.deliverable, expected)
        if name == "reply_numbers":
            numbers = re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w|\.\d)", reply)
            return all(any(same_number(value, number) for number in numbers) for value in expected)
        if name == "no_promise":
            return promise(self.last.get("reply", "")) is None
        if name == "deliverable":
            view = self.deliverable
            title = view.get("title", "")
            title = " ".join(title.values()) if isinstance(title, dict) else title
            content = view.get("rows") or view.get("steps") or content_text(view.get("blocks", []))
            return (
                bool(content)
                and all(view.get(k) == expected[k] for k in ("kind", "variant") if k in expected)
                and normal(expected.get("title_contains", "")) in normal(title)
            )
        if name == "deliverable_numbers":
            view = self.deliverable
            cells = [cell for row in view.get("rows", []) for cell in row.get("cells", {}).values()]
            cells += list(view.get("refs", {}).values())
            if view.get("total"):
                cells.append(view["total"])
            return all(
                any(
                    same_number(cell.get("value"), value)
                    and bool(view.get("sources", {}).get(cell.get("source")))
                    for cell in cells
                )
                for value in expected
            )
        if name == "rates_cited":
            rows = [r for r in self.deliverable.get("rows", []) if r["kind"] == "item"]

            def cited_rate(row):
                rate = row.get("cells", {}).get("rate", {})
                source = self.deliverable.get("sources", {}).get(rate.get("source"), {})
                loc = source.get("locator") or {}
                return (
                    rate.get("value") is not None
                    and bool(source.get("file_id"))
                    and all(loc.get(k) == v for k, v in expected.items())
                    and bool(loc.get("row"))
                )

            return bool(rows) and all(cited_rate(row) for row in rows)
        if name == "boq_units":
            units = {
                r.get("cells", {}).get("unit", {}).get("text")
                for r in self.rows()
                if r.get("kind") == "item"
            }
            return set(expected) <= units
        if name == "boq_sources":
            sources = []
            values = []
            for sheet in self.boq.get("sheets", []):
                for row in sheet["rows"]:
                    if row.get("kind") != "item":
                        continue
                    for cell in row.get("cells", {}).values():
                        if "value" in cell:
                            values.append(cell["value"])
                            sources.append(sheet.get("sources", {}).get(cell.get("source"), {}))
            return (
                bool(sources)
                and all(
                    source.get("file_id")
                    and (source.get("locator") or {}).get("page")
                    and len((source.get("locator") or {}).get("box", [])) == 4
                    for source in sources
                )
                and any(
                    Decimal(normal(v)) >= Decimal(str(expected.get("minimum_number", 0)))
                    for v in values
                )
            )
        if name == "boq_total":
            total = self.deliverable.get("total") or {}
            source = self.deliverable.get("sources", {}).get(total.get("source"), {})
            return source.get("kind") == "calculation" and same_number(total.get("value"), expected)
        if name == "changes_count":
            if "changes" not in self.observed:
                return False
            count = len(self.observed["changes"])
            return (
                count >= int(expected["min"])
                if isinstance(expected, dict)
                else count == int(expected)
            )
        if name == "pack_pages":
            return self.observed.get("pages") == int(expected)
        if name == "compare_pages":
            return "changed" in self.observed and sorted(
                c["new"]["page"] for c in self.observed["changed"]
            ) == sorted(expected)
        if name == "export_ok":
            minimum = expected.get("pages", 0) if isinstance(expected, dict) else 0
            return (
                bool(self.observed.get("out"))
                and self.observed.get("bytes", 0) > 0
                and self.observed.get("pages", 0) >= minimum
            )
        if name == "max_steps":
            logs = [
                e["data"] for e in self.last.get("events", []) if e.get("type") == "data-worklog"
            ]
            return bool(logs) and len(logs[-1].get("steps", [])) <= int(expected)
        if name == "max_input_tokens":
            tokens = self.last.get("costs", {}).get("tokens", {}).get("brief")
            return tokens is not None and tokens["input"] <= int(expected)
        if name == "no_raw":
            raw = self.last.get("reply", "")
            return not re.search(r"\b[0-9a-f]{32}\b", raw, re.I) and not has_json(raw)
        if name in ("boq_items", "boq_sections"):
            kind = "item" if name == "boq_items" else "section"
            count = sum(row["kind"] == kind for row in self.rows())
            return (
                count >= int(expected["min"])
                if isinstance(expected, dict)
                else count == int(expected)
            )
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
            costs = self.last.get("costs", {})
            return costs.get("brief") is not None and Decimal(costs["brief"]) <= Decimal(
                str(expected)
            )
        if name == "cited":
            # Check the requested page/row only, not metadata or an unrelated sheet row.
            found = self.evidence.get("cited", {})
            if "page" in expected:
                text = " ".join(p["text"] for p in found.get("pieces", []))
            elif "paragraph" in expected:
                text = " ".join(
                    p["text"]
                    for p in found.get("pieces", [])
                    if (p.get("locator") or {}).get("paragraph") == expected["paragraph"]
                )
            else:
                rows = [r for r in found.get("rows", []) if r["code"] == str(expected["row"])]
                text = " ".join(
                    cell["text"]
                    for r in rows
                    for column, cell in r["cells"].items()
                    if "column" not in expected or column == expected["column"]
                )
            value = normal(expected["value"])
            # DOCX paragraphs and CSV rows have no named worksheet/page citation.
            if "paragraph" in expected or expected.get("sheet", found.get("sheet")) == "":
                key = "paragraph" if "paragraph" in expected else "row"
                label = (
                    r"paragraph|para\.?|الفقرة|فقرة"
                    if key == "paragraph"
                    else r"row|الصف|صف|السطر|سطر"
                )
                pattern = rf"(?<!\w)(?:{label})\s*[:：]?\s*{expected[key]}(?!\d)"
                cited = any(
                    re.search(pattern, segment, re.I) and contains_value(segment, value)
                    for segment in re.split(r"\n|(?<=[!?؟])\s+|(?<=\.)(?!\d)\s+", reply)
                )
                return bool(cited) and contains_value(text, value)
            cited = any(
                contains_value(segment, value)
                and any(
                    expected["page"] in place.pages
                    if "page" in expected
                    else expected["row"] in place.rows
                    and normal(place.sheet) == normal(expected.get("sheet", found.get("sheet")))
                    for place in places
                )
                for segment, places, _ in citations(self.last.get("reply", ""))
            )
            return cited and contains_value(text, value)
        if name == "quantity_rows":
            file = self.files[int(expected.get("file", 0))]["id"]
            raw = self.evidence.get("quantity_rows", {})
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
        if "needs" in step:
            available = capability(self.commands, step["needs"])
            branch = step.get("then" if available else "otherwise", [])
            outputs = []
            for child in branch:
                started = time.monotonic()
                output = self.step(child)
                output["seconds"] = round(time.monotonic() - started, 3)
                if self.c is not None:
                    output["costs"] = self.c.get("/costs", brief_id=self.last.get("brief_id"))
                outputs.append(output)
            return {
                "capability": step["needs"],
                "available": available,
                "checks": [check for output in outputs for check in output.get("checks", [])],
                "results": outputs,
            }
        if "make" in step:
            spec = step["make"]
            output = make_revision(
                spec["source"], self.variables["scratch"], page=int(spec["page"])
            )
            self.variables["revision"] = str(output)
            return {"out": str(output)}
        if "deliverable" in step:
            wanted = step["deliverable"]
            found = self.c.get(f"/projects/{self.project}/deliverables")["deliverables"]
            matching = None
            for entry in found:
                if any(entry.get(k) != v for k, v in wanted.items() if k in entry):
                    continue
                view = self.c.get(f"/projects/{self.project}/deliverables/{entry['id']}")
                if all(view.get(k) == v for k, v in wanted.items()):
                    matching = view
                    break
            if matching is None:
                raise CliError("walk")
            self.deliverable = matching
            self.variables["deliverable"] = matching["id"]
            return self.deliverable
        if "command" in step:
            from qsone.cli.__main__ import parser

            variables = (
                self.variables
                | {"project": self.project}
                | {f"file{i}": f["id"] for i, f in enumerate(self.files)}
            )
            from contextlib import redirect_stderr, redirect_stdout
            from io import StringIO

            try:
                with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                    args = parser().parse_args(expand(step["command"], variables))
            except SystemExit:
                raise CliError("walk") from None
            if args.command in ("start", "attach", "walk", "setup") or (
                args.command == "stop" and not args.brief
            ):
                raise CliError("walk")
            self.observed = self.commands.run(args)
            if "undo" in self.observed:
                self.variables["undo"] = self.observed["undo"]
            if args.command == "deliverable" and args.action == "show":
                self.deliverable = self.observed
            if "brief_id" in self.observed:
                self.remember(self.observed)
            return self.observed
        if "project" in step:
            name = step["project"]
            self.project = self.c.post("/projects", {"name": name})["id"]
            return {"project": self.project}
        if "files" in step:
            paths = expand(step["files"], self.variables)
            self.commands.files_add(self.project, paths)
            self.files = list(reversed(self.c.get(f"/projects/{self.project}/files")["files"]))
            self.report = self.commands.files_report(self.project)
            return self.report
        if "ask" in step:
            variables = (
                self.variables
                | {"project": self.project}
                | {f"file{i}": f["id"] for i, f in enumerate(self.files)}
            )
            self.remember(
                self.commands.ask(self.project or "general", expand(step["ask"], variables))
            )
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
            for name, expected in step["check"].items():
                self.prepare_check(name, expected)
            return {
                "checks": [
                    {"check": name, "expected": expected, "pass": self.check(name, expected)}
                    for name, expected in step["check"].items()
                ]
            }
        raise CliError("walk")


def steps_status(entries):
    if any(entry["status"] == "CAP" for entry in entries):
        return "CAP"
    return "FAIL" if any(entry["status"] == "FAIL" for entry in entries) else "PASS"


def execute_steps(walk, steps, guard):
    entries = []
    capped = False
    for index, step in enumerate(steps):
        started = time.monotonic()
        entry = {"step": index + 1, "status": "PASS"}
        if walk.stop_requested or capped:
            entry.update(status="NOT_RUN", reason=TEXT["cap" if capped else "stop_on_fail"])
        else:
            try:
                if guard(None):
                    capped = True
                    entry.update(status="CAP", reason=TEXT["cap"])
                else:
                    if "check" in step and walk.failed_action:
                        output = {
                            "checks": [
                                {
                                    "check": name,
                                    "expected": expected,
                                    "pass": False,
                                    "error": TEXT["previous_failed"],
                                }
                                for name, expected in step["check"].items()
                            ]
                        }
                    elif "needs" in step:
                        available = capability(walk.commands, step["needs"])
                        children = execute_steps(
                            walk, step.get("then" if available else "otherwise", []), guard
                        )
                        output = {"results": children, "available": available}
                        entry["status"] = steps_status(children)
                    else:
                        output = walk.step(step)
                    if "results" in output:
                        entry["branch"] = output
                    if "checks" in output:
                        entry["checks"] = output["checks"]
                        if not all(c["pass"] for c in output["checks"]):
                            entry["status"] = "FAIL"
                    if output.get("state") == "failed":
                        entry["status"] = "FAIL"
            except CliError as error:
                entry.update(status="FAIL", error=error.text)
            except (OSError, ValueError, KeyError, TypeError, IndexError, httpx.HTTPError):
                entry.update(status="FAIL", error=TEXT["walk"])
            try:
                entry["costs"] = walk.c.get("/costs", brief_id=walk.last.get("brief_id"))
                if guard(walk.last.get("brief_id")):
                    capped = True
                    entry.update(status="CAP", reason=TEXT["cap"])
            except (CliError, httpx.HTTPError):
                entry["cost_error"] = TEXT["costs_unavailable"]
                if entry["status"] != "CAP":
                    entry["status"] = "FAIL"
            if "check" not in step and "needs" not in step:
                walk.failed_action = entry["status"] == "FAIL"
                if walk.failed_action:
                    walk.observed = {}
                    walk.deliverable = {}
                    walk.boq = {"client_boqs": [], "sheets": []}
                    walk.last.update(reply="", events=[], cards=[])
            walk.stop_requested |= entry["status"] == "FAIL" and step.get("stop_on_fail", False)
            capped |= entry["status"] == "CAP"
        entry["seconds"] = round(time.monotonic() - started, 3)
        entries.append(entry)
    return entries


def run(commands, file, *, max_usd=None, report=None, scripted_only=False):
    import yaml  # Already locked; only walk needs it.

    if scripted_only and commands.saved["mode"] != "scripted":
        raise CliError("scripted")

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
        "scratch": tempfile.mkdtemp(prefix="qsone-walk-"),
    }
    document = expand(document, variables)
    began = time.monotonic()
    result = {
        "name": document.get("name", Path(file).stem),
        "mode": commands.saved["mode"],
        "at": datetime.now().astimezone().isoformat(),
        "source": "ONE /costs",
        "steps": [],
        "limitations": document.get("limitations", []),
    }
    needs = document.get("needs", [])
    if isinstance(needs, dict):
        needs = needs.get(commands.saved["mode"], [])
    missing = [p for p in needs if not Path(p).is_file()]
    if missing:
        result.update(status="SKIPPED", missing=missing)
    else:
        steps = document.get(commands.saved["mode"])
        if not isinstance(steps, list) or not steps:
            raise CliError("walk")
        budget = Budget(commands, max_usd if max_usd is not None else document.get("max_usd", 3))
        previous_guard = commands.guard

        def guard(brief):
            return budget(brief) or bool(previous_guard and previous_guard(brief))

        commands.guard = guard
        walk = Walk(commands)
        walk.variables = variables
        result["status"] = "PASS"
        try:
            result["steps"] = execute_steps(walk, steps, guard)
            result["status"] = steps_status(result["steps"])
        finally:
            commands.guard = previous_guard
        try:
            result["costs"] = commands.client.get("/costs")
        except (CliError, httpx.HTTPError):
            result["cost_error"] = TEXT["costs_unavailable"]
            if result["status"] != "CAP":
                result["status"] = "FAIL"
    result["seconds"] = round(time.monotonic() - began, 3)
    write_report(result, report, commands.lang if hasattr(commands, "lang") else "en")
    return result


def write_report(result, report, lang):
    if report:
        from qsone.cli.__main__ import plain

        path = Path(report)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        path.with_suffix(".txt").write_text(plain(result, lang) + "\n")


def run_all(commands, directory, *, max_usd=None, report=None, scripted_only=False):
    import yaml

    if scripted_only and commands.saved["mode"] != "scripted":
        raise CliError("scripted")
    files = sorted({*Path(directory).glob("*.yaml"), *Path(directory).glob("*.yml")})
    if not files:
        raise CliError("walk")
    limits = [Decimal(str(yaml.safe_load(path.read_text()).get("max_usd", 3))) for path in files]
    if any(not limit.is_finite() or limit < 0 for limit in limits):
        raise CliError("walk")
    maximum = min(sum(limits), Decimal(str(max_usd))) if max_usd is not None else sum(limits)
    budget = Budget(commands, maximum)
    previous, commands.guard = commands.guard, budget
    result = {"status": "PASS", "max_usd": str(maximum), "walks": [], "source": "ONE /costs"}
    started = time.monotonic()
    try:
        for path in files:
            if budget.hit:
                result["status"] = "CAP"
                result["walks"].append(
                    {"name": path.stem, "status": "NOT_RUN", "reason": TEXT["cap"]}
                )
                continue
            try:
                entry = run(commands, path, scripted_only=scripted_only)
            except (CliError, OSError, ValueError, KeyError, TypeError, httpx.HTTPError):
                entry = {"name": path.stem, "status": "FAIL", "error": TEXT["walk"]}
            result["walks"].append(entry)
            if entry["status"] not in ("PASS", "SKIPPED"):
                result["status"] = "CAP" if entry["status"] == "CAP" else "FAIL"
    finally:
        commands.guard = previous
    result["seconds"] = round(time.monotonic() - started, 3)
    try:
        result["costs"] = commands.client.get("/costs")
    except (CliError, httpx.HTTPError):
        result["cost_error"] = TEXT["costs_unavailable"]
        if result["status"] != "CAP":
            result["status"] = "FAIL"
    write_report(result, report, commands.lang)
    return result


def make_revision(source, scratch, *, page):
    """Fixed sample-only edit of a scratch copy; no arbitrary code or tender writes."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    reader = PdfReader(source)
    if not 1 <= page <= len(reader.pages):
        raise CliError("walk")
    writer = PdfWriter()
    writer.append(reader)
    target = writer.pages[page - 1]
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(target.get("/Resources", {}))
    fonts = DictionaryObject(resources.get("/Font", {}))
    fonts[NameObject("/ONESample")] = font
    resources[NameObject("/Font")] = fonts
    target[NameObject("/Resources")] = resources
    original = target.get_contents()
    stream = DecodedStreamObject()
    stream.set_data(
        b"q\n"
        + (original.get_data() if original else b"")
        + b"\nQ\nBT /ONESample 16 Tf 20 20 Td (SAMPLE REVISION) Tj ET"
    )
    target[NameObject("/Contents")] = stream
    destination = Path(scratch) / ("revision-" + uuid4().hex[:8] + ".pdf")
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer.write(destination)
    return destination
