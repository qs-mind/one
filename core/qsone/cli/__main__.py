"""Run from core/: python -m qsone.cli [--session PATH] COMMAND."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

from qsone.cli import session
from qsone.cli.client import Client
from qsone.cli.commands import Commands
from qsone.cli.texts import TEXT, CliError


def parser():
    root = argparse.ArgumentParser(prog="qsone-cli", description="ONE local HTTP CLI / أوامر ONE")
    root.add_argument("--session")
    root.add_argument("--json", action="store_true")
    root.add_argument("--lang", choices=["en", "ar"], default="en")
    commands = root.add_subparsers(dest="command", required=True)

    def command(name):
        return commands.add_parser(name)

    def group(name, actions):
        sub = command(name).add_subparsers(dest="action", required=True)
        return [sub.add_parser(action) for action in actions]

    start = command("start")
    start.add_argument("--port", type=int, default=0)
    start.add_argument("--data-dir", type=Path)
    start.add_argument("--mode", choices=["scripted", "real"], default="scripted")
    attach = command("attach")
    attach.add_argument("--port", type=int, required=True)
    attach.add_argument("--secret-file", type=Path, required=True)
    command("stop").add_argument("brief", nargs="?")
    ai, finish = group("setup", ["ai", "finish"])
    ai.add_argument("--provider", choices=["google", "anthropic"], required=True)
    ai.add_argument("--model", required=True)
    ai.add_argument("--key-file", required=True, type=Path)
    new, listing, opening = group("project", ["new", "list", "open"])
    new.add_argument("name")
    opening.add_argument("project")
    add, report, listing = group("files", ["add", "report", "list"])
    for item in (add, report, listing):
        item.add_argument("project")
    add.add_argument("paths", nargs="+", type=Path)
    (show,) = group("file", ["show"])
    show.add_argument("project")
    show.add_argument("file")
    location = show.add_mutually_exclusive_group()
    location.add_argument("--sheet", nargs="?", const="")
    location.add_argument("--page", type=int)
    ask = command("ask")
    ask.add_argument("project")
    ask.add_argument("text")
    command("follow").add_argument("chat")
    answer, approve = group("card", ["answer", "approve"])
    for item in (answer, approve):
        item.add_argument("card")
        item.add_argument("--answer", action="append", default=[])
        item.add_argument("--rows", default="all")
    answer.add_argument("choice")
    steer = command("steer")
    steer.add_argument("brief")
    steer.add_argument("text")
    (show,) = group("boq", ["show"])
    show.add_argument("project")
    listing, show, export = group("deliverable", ["list", "show", "export"])
    for item in (listing, show, export):
        item.add_argument("project")
    for item in (show, export):
        item.add_argument("deliverable")
    export.add_argument("--format", required=True)
    export.add_argument("--out", required=True, type=Path)
    accept, reject = group("changes", ["accept", "reject"])
    for item in (accept, reject):
        item.add_argument("project")
        item.add_argument("deliverable")
        item.add_argument("--ids")
    command("undo").add_argument("token")
    search = command("search")
    search.add_argument("project")
    search.add_argument("query")
    mode = search.add_mutually_exclusive_group()
    mode.add_argument("--meaning", action="store_true")
    mode.add_argument("--words", action="store_true")
    (explain,) = group("number", ["explain"])
    explain.add_argument("project")
    explain.add_argument("number")
    command("costs").add_argument("--brief")
    walk = command("walk")
    walk.add_argument("file", type=Path)
    walk.add_argument("--max-usd", default=None)
    walk.add_argument("--report", type=Path)
    return root


def global_flags(argv):
    """Accept shared flags before or after the subcommand (including --json on every command)."""
    prefix, rest = [], []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--json", "--lang", "--session"):
            prefix.append(arg)
            if arg != "--json" and index + 1 < len(argv):
                index += 1
                prefix.append(argv[index])
        elif arg.startswith(("--lang=", "--session=")):
            prefix.append(arg)
        else:
            rest.append(arg)
        index += 1
    return prefix + rest


def plain(value, lang, indent=""):
    if isinstance(value, dict):
        if "en" in value and "ar" in value:
            return indent + str(value[lang])
        return "\n".join(
            indent + str(k) + ":\n" + plain(v, lang, indent + "  ")
            if isinstance(v, (dict, list))
            else indent + f"{k}: {v}"
            for k, v in value.items()
        )
    if isinstance(value, list):
        return "\n".join(plain(v, lang, indent) for v in value)
    return indent + str(value)


def main(argv=None):
    args = parser().parse_args(global_flags(list(sys.argv[1:] if argv is None else argv)))
    path = session.session_path(args.session)
    client = None
    mode = None
    code = 0
    try:
        if args.command == "start":
            result = session.start(path, port=args.port, data_dir=args.data_dir, mode=args.mode)
            mode = args.mode
        elif args.command == "attach":
            result = session.attach(path, port=args.port, secret_file=args.secret_file)
        elif args.command == "stop" and not args.brief:
            result = session.stop(path)
        else:
            saved = session.load(path)
            mode = saved["mode"]
            client = Client(saved)
            commands = Commands(client, saved, path, args.lang)
            if args.command == "walk":
                from qsone.cli.walk import run

                result = run(commands, args.file, max_usd=args.max_usd, report=args.report)
                code = int(result["status"] not in ("PASS", "SKIPPED"))
            else:
                result = commands.run(args)
                code = int(result.get("state") in ("failed", "money_cap"))
    except CliError as error:
        result = {"error": error.text}
        if error.detail:
            result["detail"] = error.detail
        code = 1
    except (OSError, ValueError, KeyError, TypeError, httpx.HTTPError):
        # No exception repr: it can include a provider key, request body, or sensitive filename.
        result, code = {"error": TEXT["error"]}, 1
    finally:
        if client:
            client.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(TEXT["source"][args.lang], datetime.now().astimezone().isoformat(timespec="seconds"))
        if mode == "scripted":
            print(TEXT["sample"][args.lang])
        print(plain(result, args.lang))
    return code


if __name__ == "__main__":
    sys.exit(main())
