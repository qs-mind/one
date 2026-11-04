import argparse
import os
import sys
import threading

import uvicorn

from qsone.app import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qsone")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--exit-with-stdin", action="store_true", help="stop when stdin closes (parent died)"
    )
    args = parser.parse_args(argv)

    secret = os.environ.get("QSONE_SECRET", "")
    if not secret:
        sys.exit("QSONE_SECRET is not set; the core will not start without it.")

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(secret), host="127.0.0.1", port=args.port, timeout_graceful_shutdown=3
        )
    )

    if args.exit_with_stdin:

        def watch_stdin() -> None:
            sys.stdin.buffer.read()  # returns at EOF, when the parent closes our stdin
            server.should_exit = True

        threading.Thread(target=watch_stdin, daemon=True).start()

    server.run()


if __name__ == "__main__":
    main()
