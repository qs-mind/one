"""Thin route adapters shared by argparse and YAML walks."""

import hashlib
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx

from qsone.cli import session
from qsone.cli.follow import follow
from qsone.cli.texts import TEXT, CliError
from qsone.records.pdfium_guard import PDFIUM


class Commands:
    def __init__(self, client, saved, path, lang="en", guard=None):
        self.client, self.saved, self.path, self.lang = client, saved, path, lang
        self.guard = guard

    def consent(self):
        found = self.client.get("/settings/ai-consent")
        if not found["at"]:
            self.client.request(
                "PUT", "/settings/ai-consent", json={"text_version": found["text_version"]}
            )

    def setup_ai(self, provider, model, key_file):
        self.consent()
        # The only place the AI key is read. It is sent only in an HTTP body.
        key = Path(key_file).read_text().strip()
        if not key:
            raise CliError()
        if provider == "anthropic":
            self.client.request(
                "PUT", "/settings/ai-key", json={"provider": "anthropic", "value": key}
            )
            self.client.request("PUT", "/settings/model", json={"id": model})
            self.client.post("/settings/ai/check", {"via": "api_key"})
        else:
            link = self.client.post(
                "/settings/ai/standard",
                {
                    "name": "Google",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                    "key": key,
                    "model": model,
                },
            )
            self.client.post("/settings/ai/check", {"via": "standard", "connector": link["id"]})
            self.client.request(
                "PUT", "/settings/model", json={"id": model, "connector": link["id"]}
            )
        return {"roles": self.client.get("/settings/ai")["roles"]}

    def finish(self):
        self.consent()
        for step in ("language", "account", "ai", "card", "usage"):
            self.client.request(
                "PUT",
                f"/setup/{step}",
                json={
                    "state": "done" if step == "language" else "skipped",
                    **({"lang": self.lang} if step == "language" else {}),
                },
            )
        return {
            "setup": self.client.get("/setup"),
            "roles": self.client.get("/settings/ai")["roles"],
        }

    def files_add(self, project, paths):
        result = []
        expanded = []
        for given in paths:
            given = Path(given)
            if given.is_dir():
                for directory, dirs, files in os.walk(given, followlinks=False):
                    dirs[:] = sorted(
                        d
                        for d in dirs
                        if not d.startswith(".")
                        and d != "__MACOSX"
                        and not (Path(directory) / d).is_symlink()
                    )
                    for name in sorted(files):
                        path = Path(directory) / name
                        if (
                            name.startswith((".", "~$"))
                            or name.casefold() in ("thumbs.db", "desktop.ini")
                            or path.is_symlink()
                        ):
                            continue
                        expanded.append((path, path.parent.relative_to(given.parent).as_posix()))
            else:
                expanded.append((given, ""))
        for path, folder in expanded:
            try:
                with path.open("rb") as source:
                    result.append(
                        self.client.request(
                            "POST",
                            f"/projects/{project}/files",
                            params={"name": path.name, **({"folder": folder} if folder else {})},
                            content=source,
                            timeout=300,
                        )
                    )
            except (CliError, OSError, httpx.HTTPError) as error:
                if isinstance(error, httpx.TimeoutException):
                    try:
                        with path.open("rb") as source:
                            digest = hashlib.file_digest(source, "sha256").hexdigest()
                        found = self.client.get(f"/projects/{project}/files")["files"]
                        match = next(
                            (
                                f
                                for f in found
                                if f.get("name") == path.name and f.get("sha256") == digest
                            ),
                            None,
                        )
                        if match is not None:
                            result.append(match)
                            continue
                    except (CliError, OSError, httpx.HTTPError):
                        pass
                result.append(
                    {
                        "name": path.name,
                        "folder": folder,
                        "status": "failed",
                        "error": (
                            error.text
                            if isinstance(error, CliError)
                            else TEXT["upload_timeout"]
                            if isinstance(error, httpx.TimeoutException)
                            else TEXT["upload_http_error"]
                            if isinstance(error, httpx.HTTPError)
                            else TEXT["error"]
                        ),
                    }
                )
        return {
            "uploads": result,
            "added": sum(r.get("status") != "failed" for r in result),
            "failed": sum(r.get("status") == "failed" for r in result),
        }

    def map(self, project, *, group=None, file=None, cursor=None, wait=None):
        route = f"/projects/{project}/map"
        if file and wait is None:
            return self.client.get(route + f"/files/{file}")
        deadline = time.monotonic() + max(0, wait or 0)
        while True:
            result = self.client.get(route, parent=group, cursor=cursor)
            for entry in result.get("files", []):
                if entry.get("kind") in ("dwg", "dxf"):
                    entry["sheets"] = self.client.get(route + f"/files/{entry['file_id']}").get(
                        "sheets", []
                    )
            if wait is None:
                return result
            # Read all pages for readiness, even when displaying a filtered page.
            scan = result if group is None and cursor is None else self.client.get(route)
            states = []
            while True:
                states.extend(scan.get("files", []))
                if not scan.get("next_cursor"):
                    break
                scan = self.client.get(route, cursor=scan["next_cursor"])
            messages = self.client.get(f"/chat/{project}/messages").get("messages", [])
            cards = {}
            for message in messages:
                for part in message.get("parts", []):
                    if part.get("type") == "data-card":
                        card = part["data"] | {"id": part["id"], "chat": project}
                        cards[card["id"]] = cards.get(card["id"], {}) | card
            pending = [
                card
                for card in cards.values()
                if card.get("kind") == "cost" and card.get("status") == "pending"
            ]
            if pending:
                self.saved["cards"].update({card["id"]: card for card in pending})
                session.save(self.path, self.saved)
                return result | {"cards": pending, "state": "waiting_engineer"}
            status = result.get("status", {})
            settled = not (status.get("waiting", 0) or status.get("reading", 0)) and all(
                (
                    f.get("local_state") not in ("waiting", "reading")
                    and f.get("ai_state") in ("done", "local", "declined", "no_ai", "failed")
                )
                or f.get("local_state") == "failed"
                for f in states
            )
            settled = settled and not any(
                p.get("state") in ("running", "retrying") for p in status.get("passes", {}).values()
            )
            # File classification finishes before enrichment is registered. The
            # checkpoint closes that gap (and the gap between facts and links).
            passes = status.get("passes", {})
            settled = settled and all(
                f.get("ai_state") != "done"
                or f.get("ai_stage") not in ("facts", "links")
                or passes.get(f["ai_stage"], {}).get("state") == "failed"
                for f in states
            )
            if settled or time.monotonic() >= deadline:
                if file:
                    result = self.client.get(route + f"/files/{file}")
                return result | {"state": "done" if settled else "timeout"}
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))

    def map_entries(self, project, name, *, rejected=False):
        route = f"/projects/{project}/map/{name}"
        params = {"rejected": True} if rejected else {}
        key = "rejected" if rejected else name
        result = self.client.get(route, **params)
        while result.get("next_cursor"):
            page = self.client.get(route, cursor=result["next_cursor"], **params)
            result[key].extend(page[key])
            result["next_cursor"] = page.get("next_cursor")
        if rejected:
            for row in result.get("rejected", []):
                row.update(row.get("proposal", {}))
        return result

    def files_report(self, project):
        files = self.client.get(f"/projects/{project}/files")["files"]
        return self.client.post(
            f"/projects/{project}/files/report", {"file_ids": [f["id"] for f in files]}
        )

    def ask(self, chat, text):
        if self.guard and self.guard(None):
            return {"state": "money_cap", "reply": "", "cards": []}
        return follow(
            self.client,
            self.saved,
            self.path,
            chat,
            guard=self.guard,
            body={
                "id": chat,
                "messages": [
                    {"id": uuid4().hex, "role": "user", "parts": [{"type": "text", "text": text}]}
                ],
            },
        )

    def answer(self, card_id, choice, answers=None, rows="all"):
        card = self.saved["cards"].get(card_id)
        if card is None:
            raise CliError("answer")
        if self.guard and self.guard(None):
            return {"state": "money_cap", "reply": "", "cards": []}
        payload = card.get("payload") or {}
        defaults = {
            r["column"]: r["meaning"]
            for r in payload.get("rows", [])
            if "column" in r and "meaning" in r
        }
        answers = defaults | (answers or {})
        if choice != "no" and any(q["id"] not in answers for q in payload.get("questions", [])):
            raise CliError("answer")
        ticked = list(range(len(payload.get("rows", [])))) if payload.get("tick") else []
        if rows != "all":
            ticked = [int(r) for r in rows.split(",") if r]
        self.client.post(
            f"/cards/{card_id}", {"choice": choice, "answers": answers, "rows_ok": ticked}
        )
        card["status"] = "settled"
        session.save(self.path, self.saved)
        return follow(
            self.client, self.saved, self.path, card["chat"], guard=self.guard, recover=True
        )

    def boq(self, project):
        found = self.client.get(f"/projects/{project}/workspace")["client_boqs"]
        return {
            "client_boqs": found,
            "sheets": [
                self.client.get(f"/projects/{project}/client-boq/{entry['file_id']}")
                for entry in found
            ],
        }

    def download(self, route, out, *, method="GET", **params):
        response = self.client.http.request(method, route, params=params)
        self.client.check(response)
        out = Path(out)
        if out.is_dir():
            parts = route.rstrip("/").split("/")
            out = out / ((parts[-2] if len(parts) > 1 else "document") + ".pdf")
        result = {"out": str(out), "bytes": len(response.content)}
        if response.content.startswith(b"%PDF"):
            from io import BytesIO

            from pypdf import PdfReader

            pdf = PdfReader(BytesIO(response.content))
            result.update(pages=len(pdf.pages), bookmarks=[])

            def bookmarks(nodes):
                for node in nodes:
                    if isinstance(node, list):
                        bookmarks(node)
                    else:
                        result["bookmarks"].append(
                            {"title": node.title, "page": pdf.get_destination_page_number(node) + 1}
                        )

            bookmarks(pdf.outline)
            result["signature_fields"] = [
                {
                    "name": name,
                    "type": str(field.get("/FT", "")),
                    "has_contents": bool((field.get("/V") or {}).get("/Contents")),
                }
                for name, field in (pdf.get_fields() or {}).items()
            ]
            from contextlib import closing

            import pypdfium2 as pdfium

            with PDFIUM, pdfium.PdfDocument(response.content) as rendered:
                result["page_texts"] = []
                for page_index in range(len(rendered)):
                    with closing(rendered[page_index]) as page:
                        with closing(page.get_textpage()) as text:
                            result["page_texts"].append(text.get_text_range())
        Path(out).write_bytes(response.content)
        return result

    def run(self, args):
        c = self.client
        cmd, action = args.command, getattr(args, "action", None)
        p = getattr(args, "project", None)
        base = f"/projects/{p}"
        if cmd == "setup":
            return (
                self.finish()
                if action == "finish"
                else self.setup_ai(args.provider, args.model, args.key_file)
            )
        if cmd == "project":
            if action == "new":
                return c.post("/projects", {"name": args.name})
            if action == "list":
                return c.get("/projects")
            return c.post(base + "/open")
        if cmd == "map":
            return self.map(p, group=args.group, file=args.file, cursor=args.cursor, wait=args.wait)
        if cmd in ("facts", "links"):
            return self.map_entries(p, cmd, rejected=getattr(args, "rejected", False))
        if cmd == "fact":
            return c.post(
                base + f"/map/facts/{args.fact}",
                {"confirm": True} if action == "confirm" else {"value": args.value},
            )
        if cmd == "files":
            if action == "add":
                return self.files_add(p, args.paths)
            if action == "report":
                return self.files_report(p)
            return c.get(base + "/files")
        if cmd == "file":
            route = base + f"/files/{args.file}"
            if action == "pdf":
                return self.download(route + "/pdf", args.out, method="POST")
            if args.sheet is not None:
                return c.get(route + "/sheet", name=args.sheet or None)
            return c.get(route + ("/text" if args.page else "/pages"), page=args.page)
        if cmd == "ask":
            return self.ask(p, args.text)
        if cmd == "follow":
            return follow(c, self.saved, self.path, args.chat, guard=self.guard)
        if cmd == "card":
            answers = {}
            for pair in args.answer:
                key, sep, value = pair.partition("=")
                if not sep:
                    raise CliError("answer")
                answers[key] = value
            return self.answer(
                args.card, "yes" if action == "approve" else args.choice, answers, args.rows
            )
        if cmd in ("stop", "steer"):
            return c.post(
                f"/briefs/{args.brief}/{cmd}", {"text": args.text} if cmd == "steer" else None
            )
        if cmd == "boq":
            return self.boq(p)
        if cmd == "deliverable":
            route = base + "/deliverables"
            if action == "list":
                return c.get(route)
            route += f"/{args.deliverable}"
            if action == "show":
                return c.get(route) | {"versions": c.get(route + "/versions")}
            if action == "signoff":
                return c.post(route + "/signoff")
            if action == "check":
                c.get(route)  # Validate the target before starting paid work.
                result = self.ask(
                    p, TEXT["check_request"][self.lang].format(deliverable=args.deliverable)
                )
                closeout = c.get(route + "/closeout")
                version = c.get(route)["version"]
                checked = (closeout.get("check") or {}).get("version_n") == version
                if result.get("state") == "done" and not checked:
                    result.update(state="failed", error=TEXT["not_checked"])
                return result | {"closeout": closeout, "checked": checked}
            return self.download(route + "/export", args.out, format=args.format)
        if cmd == "changes":
            route = base + f"/deliverables/{args.deliverable}/changes"
            if action == "list":
                return c.get(route, status="pending")
            ids = (
                args.ids.split(",")
                if args.ids
                else [change["id"] for change in c.get(route, status="pending")["changes"]]
            )
            return c.post(route + f"/{action}", {"ids": ids})
        if cmd == "undo":
            return c.post(f"/undo/{args.token}")
        if cmd == "search":
            return c.get(
                base + "/search",
                q=args.query,
                mode="meaning" if args.meaning else "exact" if args.words else "auto",
            )
        if cmd == "number":
            return c.get(base + f"/numbers/{args.number}/explain")
        if cmd == "pack":
            route = base + f"/deliverables/{args.deliverable}"
            view = c.get(route)
            if action == "show":
                return view
            c.request("POST", route + "/pack/build", params={"version": view["version"]})
            return self.download(route + "/export", args.out, format="pdf")
        if cmd == "compare":
            return c.post(
                base + "/files/compare",
                {"old_file_id": args.old_file, "new_file_id": args.new_file},
            )
        if cmd == "region":
            route = base + f"/files/{args.file}/comments"
            if action == "list":
                return c.get(route)
            box = [float(v) for v in args.box.split(",")]
            if len(box) != 4:
                raise CliError()
            return c.post(
                route,
                {
                    "anchor": {
                        "kind": "file_region",
                        "file_id": args.file,
                        "page": args.page,
                        "box": box,
                    },
                    "body": args.comment,
                },
            )
        if cmd == "costs":
            result = c.get("/costs", brief_id=args.brief)
            if args.today:
                return {
                    key: value.get("today")
                    if isinstance(value, dict) and "today" in value
                    else value
                    for key, value in result.items()
                    if key not in ("brief", "month")
                }
            return result
        raise CliError()
