"""Start the real core with the bench's fake AI: `python -m tests.bench --port N --data-dir D`.

Run from `core/` (or with `core/` on PYTHONPATH). `QSONE_SECRET` must be set, as for the real
core. With `--samples DIR`, the sample input files are written there first."""

import argparse
import os
from pathlib import Path

from tests.bench import fake, guard, samples


def seed() -> None:
    """Every role on a bench model, through the same code the Settings screen saves with. The
    screen counts a model connector as connected once its key is set: each bench connector gets
    a dummy one, in the bench's in-memory key store only."""
    from qsone import keys
    from qsone.engine import roles

    for connector in fake.connectors():
        keys.set_key(connector.id, "bench-dummy-not-a-key")
    for role, choice in fake.ROLES.items():
        roles.choose(role, choice)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tests.bench")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--exit-with-stdin", action="store_true")
    args = parser.parse_args(argv)

    os.environ["QSONE_DATA_DIR"] = str(args.data_dir)
    guard.install()
    from qsone.engine import connectors

    connectors.connectors = lambda **_: fake.connectors()  # the Settings screen's list too
    args.data_dir.mkdir(parents=True, exist_ok=True)
    seed()
    if args.samples is not None:
        samples.write(args.samples)

    from qsone.__main__ import main as core_main

    core_args = ["--port", str(args.port), "--data-dir", str(args.data_dir)]
    core_main(core_args + (["--exit-with-stdin"] if args.exit_with_stdin else []))


if __name__ == "__main__":
    main()
