"""Optional, unbundled LibreOffice (MPL-2.0), in an isolated disposable profile.

Only conversion writes decrypted bytes to disk. Call from a worker, never the event loop.
The original stays in Project Records; no converted file is retained.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

DOWNLOAD_URL = "https://www.libreoffice.org/download/download-libreoffice/"
TIMEOUT = 60
READ_TARGETS = {
    "doc": "pdf",
    "xls": "xlsx",
    "ods": "xlsx",
    "ppt": "pdf",
    "pptx": "pdf",
    "odt": "pdf",
    "rtf": "pdf",
}
PDF_INPUTS = {*READ_TARGETS, "docx", "xlsx", "xlsm"}


def find_soffice() -> str | None:
    """PATH first, then standard Windows and macOS installation folders."""
    found = shutil.which("soffice")
    if found:
        return found
    candidates = []
    if sys.platform == "win32":
        for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(key)
            if root:
                candidates.append(Path(root) / "LibreOffice/program/soffice.exe")
    elif sys.platform == "darwin":
        candidates = [
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]
    return next((str(p) for p in candidates if p.is_file()), None)


def _run(args: list[str], *, timeout: float, **kwargs):
    """Stop our process tree before removing its profile, including on cancellation."""
    kwargs.pop("check", None)
    with subprocess.Popen(args, start_new_session=os.name != "nt", **kwargs) as process:
        try:
            process.wait(timeout=timeout)
        except BaseException:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.kill()
            process.wait()
            raise
        return subprocess.CompletedProcess(args, process.returncode)


def convert(data: bytes, name: str, target: str) -> bytes | None:
    """Convert in a private temporary directory; missing/failed/timed-out returns None.

    Names are display text, so only the allowlisted extension is used on disk.
    """
    suffix = name.rsplit(".", 1)[-1].lower()
    if suffix not in PDF_INPUTS or target not in {"pdf", "xlsx", "odt", "ods"}:
        return None
    executable = find_soffice()
    if executable is None:
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="qsone-office-") as folder:
            root = Path(folder)
            source = root / f"source.{suffix}"
            output = root / "output"
            output.mkdir()
            profile = root / "profile"
            # Disable macros in this disposable profile.
            user = profile / "user"
            user.mkdir(parents=True)
            (user / "registrymodifications.xcu").write_text(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
                '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
                '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
                "</item></oor:items>",
                encoding="utf-8",
            )
            source.write_bytes(data)
            result = _run(
                [
                    executable,
                    f"-env:UserInstallation={profile.as_uri()}",
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--norestore",
                    "--convert-to",
                    target,
                    "--outdir",
                    str(output),
                    str(source),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=TIMEOUT,
                check=False,
                env={**os.environ, "TMPDIR": folder, "TMP": folder, "TEMP": folder},
            )
            converted = output / f"source.{target}"
            if result.returncode != 0 or not converted.is_file():
                return None
            body = converted.read_bytes()
            return body if body and (target != "pdf" or body.startswith(b"%PDF-")) else None
    except (OSError, subprocess.SubprocessError):
        return None


def to_pdf(data: bytes, name: str) -> bytes | None:
    """Print Word/Excel/OpenDocument/presentation bytes to PDF, or None if unavailable."""
    return convert(data, name, "pdf")
