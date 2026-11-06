"""The real core, with real AI providers, for a real-window walk (`launch({ core: "real" })` in realapp.mjs).

Everything is the core's own code, started as the release shell starts it, with three things kept off the computer
it runs on: the system key store (keyring's fail backend, so the core keeps its keys in keystore.json inside the
walk's throw-away data folder, as scripts/smoke-core.mjs and scripts/keystore-isolation.test.mjs require), the
engineer's own Claude Code (never found, so never run or billed), and the browser (a link opens nothing).

Usage, from the repository with core/ on PYTHONPATH: python scripts/realapp/realcore.py --data-dir D --port N"""

import os
import sys
import webbrowser

FAIL = "keyring.backends.fail.Keyring"
if os.environ.get("PYTHON_KEYRING_BACKEND") != FAIL:
    sys.exit(f"realcore: PYTHON_KEYRING_BACKEND must be {FAIL} (never the system key store)")
if "--data-dir" not in sys.argv:
    sys.exit("realcore: --data-dir is required (never the engineer's data folder)")

from qsone.engine.connectors import claude_code  # noqa: E402
from qsone.journey import claude_code as first_launch_claude  # noqa: E402

claude_code.executable = lambda picked: (None, "CLAUDE_CODE_MISSING")
first_launch_claude.on_path = lambda: None
first_launch_claude.find_claude = lambda: (None, None)
webbrowser.open = lambda *args, **kwargs: False

from qsone.__main__ import main  # noqa: E402

main(sys.argv[1:])
