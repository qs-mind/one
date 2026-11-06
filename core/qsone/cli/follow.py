"""Read ONE's UI SSE protocol, preserving cards for a later CLI invocation."""

import json
import queue
import threading
import time

from qsone.cli import session
from qsone.cli.texts import CliError


def follow(client, saved, path, chat, *, body=None, guard=None, recover=False):
    result = {"chat": chat, "reply": "", "cards": [], "events": [], "state": "idle"}
    route = "/chat" if body is not None else f"/chat/{chat}/stream"
    method = "POST" if body is not None else "GET"
    # Independent timed polling works even when a stream has no heartbeat or is stalled.
    settled = {
        key
        for key, card in saved["cards"].items()
        if card.get("status") in ("settled", "withdrawn")
    }
    inbox = queue.Queue()
    quit_reader = threading.Event()
    with client.http.stream(method, route, json=body, timeout=None) as response:
        if not response.is_success:
            response.read()
            client.check(response)
        if response.status_code == 204:
            if recover:
                messages = client.get(f"/chat/{chat}/messages")["messages"]
                last = next((m for m in reversed(messages) if m["role"] == "assistant"), {})
                for part in last.get("parts", []):
                    if part["type"] == "text":
                        result["reply"] += part["text"]
                    elif part["type"] == "data-status":
                        result.update(state=part["data"]["state"], brief_id=part["id"])
                    elif part["type"].startswith("data-"):
                        result["events"].append(part)
                result["costs"] = client.get("/costs", brief_id=result.get("brief_id"))
            return result

        def read():
            try:
                for line in response.iter_lines():
                    if quit_reader.is_set():
                        break
                    inbox.put(line)
            except Exception as error:
                if not quit_reader.is_set():
                    inbox.put(error)
            finally:
                inbox.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        checked = 0
        try:
            while True:
                if guard and time.monotonic() - checked >= 5:
                    checked = time.monotonic()
                    if guard(result.get("brief_id")):
                        if not result.get("brief_id"):
                            active = client.get("/briefs/activity")["chats"]
                            for entry in active:
                                if entry["chat_id"] == chat and entry["state"] in (
                                    "working",
                                    "waiting",
                                ):
                                    result["brief_id"] = entry["brief_id"]
                                    guard(entry["brief_id"])
                        result["state"] = "money_cap"
                        break
                try:
                    line = inbox.get(timeout=1)
                except queue.Empty:
                    continue
                if line is None or line == "data: [DONE]":
                    break
                if isinstance(line, Exception):
                    raise CliError() from None
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                kind = event.get("type")
                if kind == "text-delta":
                    result["reply"] += event["delta"]
                elif kind == "data-redo":
                    cut = event["data"]
                    raw = result["reply"].encode("utf-16-le")
                    result["reply"] = (raw[: 2 * cut["from"]] + raw[2 * cut["to"] :]).decode(
                        "utf-16-le"
                    )
                elif kind == "data-card":
                    card = event["data"] | {"id": event["id"], "chat": chat}
                    if not (card["id"] in settled and card.get("status") == "pending"):
                        saved["cards"][card["id"]] = card
                        session.save(path, saved)
                elif kind == "data-status":
                    result.update(state=event["data"]["state"], brief_id=event["id"])
                elif kind == "error":
                    result["state"] = "failed"
                    try:
                        error = json.loads(event.get("errorText", "{}"))
                    except ValueError:
                        error = {}
                    result["error"] = error
                if kind and kind.startswith("data-"):
                    result["events"].append(event)
                pending = [
                    c
                    for c in saved["cards"].values()
                    if c["chat"] == chat and c.get("status") == "pending"
                ]
                if result["state"] in ("done", "failed", "stopped") or (
                    result["state"] in ("waiting_engineer", "paused_cap") and pending
                ):
                    break
        finally:
            quit_reader.set()
        result["cards"] = [
            c for c in saved["cards"].values() if c["chat"] == chat and c.get("status") == "pending"
        ]
    result["costs"] = client.get("/costs", brief_id=result.get("brief_id"))
    return result
