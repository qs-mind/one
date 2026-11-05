"""Start the real core with the bench's fake AI: `python -m tests.bench --port N --data-dir D`.

Run from `core/` (or with `core/` on PYTHONPATH). `QSONE_SECRET` must be set, as for the real
core. With `--samples DIR`, the sample input files are written there first.

The bench core has one route of its own, `POST /bench/new-computer`: the data folder as on a
computer One was just installed on (no projects, no snapshots, no backup settings, no project
key and no Backup key in the key store), so a walk can restore from the backup folder.

A Claude key is checked by the bench, never by Anthropic (`check_keys`): one with "-bench-ok-" in
it works, any other is refused, each after a short wait so the screen's "Checking…" shows. A walk
that saved one takes it out again with `POST /bench/forget-claude-key`."""

import argparse
import os
import shutil
from pathlib import Path

from tests.bench import fake, guard, samples


def seed() -> None:
    """Every role on a bench model, through the same code the Settings screen saves with. The
    screen counts a model connector as connected once its key is set: each bench connector gets
    a dummy one, in the bench's in-memory key store only."""
    from qsone import keys
    from qsone.engine import roles
    from qsone.journey import setup_state

    for connector in fake.connectors():
        keys.set_key(connector.id, "bench-dummy-not-a-key")
    for role, choice in fake.ROLES.items():
        roles.choose(role, choice)
    setup_state.give_consent(setup_state.CONSENT_VERSION)  # the AI note, as the screen says yes
    for step in setup_state.STEPS:  # the walks start in the app, past the first launch
        setup_state.mark(step, "skipped")
    setup_state.set_language("ar")  # the screen's first language: the Briefs One starts match it


BENCH_KEY = "-bench-ok-"  # in a sample Claude key that the bench's check takes


def check_keys() -> None:
    """The first launch's and AI settings' key check (POST /settings/ai/check, via "api_key") is
    answered here from the key the screen saved: no request leaves the bench."""
    import asyncio

    from qsone import copy, keys
    from qsone.engine import connectors

    real = connectors.check

    async def check(via: str, *, among=None):
        if not via.startswith("anthropic/"):
            return await real(via, among=among)
        await asyncio.sleep(1.2)
        if BENCH_KEY in (keys.get_key("anthropic") or ""):
            return None
        return copy.KEY_REFUSED  # what the Native Link says for a refused Claude key

    connectors.check = check


def forget_claude_key(app) -> None:
    """Adds `POST /bench/forget-claude-key`: the walks after one that saved a key run as before."""
    from qsone import keys

    @app.post("/bench/forget-claude-key")
    def forget() -> dict:
        keys.delete_key("anthropic")
        return {"set": False}


def new_computer(app, data_dir: Path) -> None:
    """Adds `POST /bench/new-computer` to the bench's app (see the module's text)."""
    import keyring

    from qsone import settings
    from qsone.backup import keys

    @app.post("/bench/new-computer")
    def forget() -> dict:
        registry = app.state.projects
        for project_id, _ in registry.opened():
            registry.close(project_id, back_up=False)
        for folder in ("projects", "snapshots"):
            shutil.rmtree(data_dir / folder, ignore_errors=True)
        (data_dir / keys.BACKUP_KEY_FILE).unlink(missing_ok=True)
        settings.save("backup", {})
        settings.save("backups", {})
        store = keyring.get_keyring().store  # the bench's MemoryKeyring: the AI keys stay
        for service, user in list(store):
            if user.startswith(("project:", keys.KEY_USER)):
                del store[(service, user)]
        registry._known.clear()
        app.state.backups._local.clear()
        return {"new": True}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tests.bench")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--exit-with-stdin", action="store_true")
    args = parser.parse_args(argv)

    os.environ["QSONE_DATA_DIR"] = str(args.data_dir)
    # QSONE_BENCH_ALLOW_HOST (comma-separated, off by default): an audit that needs one real AI
    # lets its host through, and the Standard Links it adds are listed beside the bench's own.
    allow = tuple(
        h.strip() for h in os.environ.get("QSONE_BENCH_ALLOW_HOST", "").split(",") if h.strip()
    )
    guard.install(allow)
    from qsone.engine import connectors
    from qsone.engine.connectors import standard

    if allow:
        connectors.connectors = lambda **kw: [
            *fake.connectors(),
            *standard.links(http_client=kw.get("http_client")),
        ]
    else:
        connectors.connectors = lambda **_: fake.connectors()  # the Settings screen's list too
    check_keys()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    seed()
    if args.samples is not None:
        samples.write(args.samples)
        samples.write_tender(args.samples.parent / "tender")  # beside the loose files
        samples.write_old(args.samples.parent / "old")
        samples.write_workspace(args.samples.parent / "workspace")  # the workspace screens' tender

    import qsone.__main__ as core
    from qsone.__main__ import main as core_main

    real_app = core.create_app

    def create_app(*a, **k):
        app = real_app(*a, **k)
        new_computer(app, args.data_dir)
        forget_claude_key(app)
        return app

    core.create_app = create_app

    core_args = ["--port", str(args.port), "--data-dir", str(args.data_dir)]
    core_main(core_args + (["--exit-with-stdin"] if args.exit_with_stdin else []))


if __name__ == "__main__":
    main()
