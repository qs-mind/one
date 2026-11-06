"""Thin route adapters shared by argparse and YAML walks."""

from pathlib import Path
from uuid import uuid4

from qsone.cli import session
from qsone.cli.follow import follow
from qsone.cli.texts import CliError


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
            try:
                self.client.post("/settings/ai/check", {"via": "standard", "connector": link["id"]})
            except Exception:
                self.client.request("DELETE", f"/settings/ai/standard/{link['id']}")
                raise
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
        for path in paths:
            path = Path(path)
            with path.open("rb") as source:
                result.append(
                    self.client.request(
                        "POST",
                        f"/projects/{project}/files",
                        params={"name": path.name},
                        content=source,
                    )
                )
        return {"uploads": result}

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
        if cmd == "files":
            if action == "add":
                return self.files_add(p, args.paths)
            if action == "report":
                return self.files_report(p)
            return c.get(base + "/files")
        if cmd == "file":
            route = base + f"/files/{args.file}"
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
                return c.get(route)
            response = c.http.get(route + "/export", params={"format": args.format})
            c.check(response)
            Path(args.out).write_bytes(response.content)
            return {"out": str(args.out), "bytes": len(response.content)}
        if cmd == "changes":
            route = base + f"/deliverables/{args.deliverable}/changes"
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
        if cmd == "costs":
            return c.get("/costs", brief_id=args.brief)
        raise CliError()
