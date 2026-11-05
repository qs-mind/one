import argparse
import logging
import os
import sys
import threading
from pathlib import Path

import uvicorn

from qsone import keystore, settings, usage
from qsone.app import create_app


class NoQuery(logging.Filter):
    """The access log keeps the path only: a query may hold a file name or search words."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:  # client, method, path, version, status
            record.args = (args[0], args[1], str(args[2]).split("?", 1)[0], *args[3:])
        return True


_no_query = NoQuery()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qsone")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--exit-with-stdin", action="store_true", help="stop when stdin closes (parent died)"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="the app data folder (default: QSONE_DATA_DIR or the system's)",
    )
    args = parser.parse_args(argv)

    secret = os.environ.get("QSONE_SECRET", "")
    if not secret:
        sys.exit("QSONE_SECRET is not set; the core will not start without it.")

    if args.data_dir is not None:
        os.environ["QSONE_DATA_DIR"] = str(args.data_dir)  # settings.json follows it too
    usage.install_hooks()  # a crash outside a request is reported too (class and line only)
    keystore.choose()  # before anything uses a key: the system key store, or One's key file
    usage.core_stopped(settings.data_dir())  # the last run's core died with the window open
    config = uvicorn.Config(
        create_app(secret, data_dir=args.data_dir),
        host="127.0.0.1",
        port=args.port,
        timeout_graceful_shutdown=3,
    )
    logging.getLogger("uvicorn.access").addFilter(_no_query)  # after Config sets up logging
    server = uvicorn.Server(config)

    if args.exit_with_stdin:

        def watch_stdin() -> None:
            sys.stdin.buffer.read()  # returns at EOF, when the parent closes our stdin
            server.should_exit = True

        threading.Thread(target=watch_stdin, daemon=True).start()

    server.run()


if __name__ == "__main__":
    main()
