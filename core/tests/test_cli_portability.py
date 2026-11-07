"""Console and session regressions reproducible without a Windows runner."""

import ast
import io
import subprocess
import sys
from pathlib import Path

import pytest

from qsone.cli import session


def test_text_io_always_declares_encoding():
    core = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(core / "qsone"),
            str(core / "tests"),
            "--select",
            "PLW1514",
            "--preview",
        ],
        capture_output=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout
    # Ruff cannot infer every untyped Path receiver; audit those calls directly too.
    for folder in (core / "qsone", core / "tests"):
        for path in folder.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                name = node.func.attr
                if name not in ("read_text", "write_text"):
                    continue
                positional = 1 if name == "read_text" else 2
                assert len(node.args) >= positional or any(
                    key.arg == "encoding" for key in node.keywords
                ), (path, node.lineno)


def test_cli_reconfigures_legacy_console(monkeypatch):
    from qsone.cli.__main__ import main

    output = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    errors = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "stderr", errors)
    with pytest.raises(SystemExit):
        main(["--help"])
    assert output.encoding == errors.encoding == "utf-8"
    assert output.errors == errors.errors == "replace"


def test_windows_private_parent_ignores_posix_modes(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    tmp_path.chmod(0o755)
    session.private_parent(tmp_path / "session.json")


def test_private_parent_refuses_symlink(tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows privileges")
    with pytest.raises(session.CliError):
        session.private_parent(link / "session.json")


def test_private_parent_refuses_junction(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "is_junction", lambda path: True)
    with pytest.raises(session.CliError):
        session.private_parent(tmp_path / "session.json")
