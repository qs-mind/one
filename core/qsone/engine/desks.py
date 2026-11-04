"""Saved Desks: the engineer's own versioned plain files, in Claude Code's plugin layout.

No Desk ships with One. The Lead QS builds a Temporary Desk for a Brief; a Desk is written here
only after the engineer's yes, as a Draft Desk (Plan 9's Acceptance Tests make Approved ones).
Each save makes `<data>/desks/<slug>/v<N+1>/`, and older versions stay:

    .claude-plugin/plugin.json      name, version, description
    agents/<specialist>.md          frontmatter (name, description), then the instructions
    skills/<procedure>/SKILL.md     frontmatter (name, description), then the text
    qs-desk.json                    the QS parts: names {en, ar}, tools and tier, status "draft"

A Desk is a dict: {"slug", "name": {en, ar}, "purpose", "specialists": [{"name": {en, ar},
"instructions", "tools": [...], "tier"}], "procedures": [{"name", "text"}]}."""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_VERSION = re.compile(r"v([1-9][0-9]*)")
MANIFEST = "qs-desk.json"


def slug_of(text: str) -> str:
    """A file-safe name: lower-case letters, digits and hyphens; "desk" when none is left."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:63].strip("-")
    return slug or "desk"


def _folder(slug: str, data_dir: Path) -> Path:
    if not SLUG.fullmatch(slug):
        raise ValueError(f"not a Desk slug: {slug!r}")
    return data_dir / "desks" / slug


def _versions(folder: Path) -> list[int]:
    if not folder.is_dir():
        return []
    return sorted(
        int(m.group(1))
        for p in folder.iterdir()
        if p.is_dir() and (m := _VERSION.fullmatch(p.name))
    )


def _frontmatter(name: str, description: str, body: str) -> str:
    # JSON strings are YAML strings, so any text is quoted safely.
    head = f"name: {json.dumps(name, ensure_ascii=False)}\n"
    head += f"description: {json.dumps(description, ensure_ascii=False)}\n"
    return f"---\n{head}---\n\n{body.strip()}\n"


def _body(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :].strip()
    return text.strip()


def _unique(names: list[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        candidate, n = name, 2
        while candidate in out:
            candidate, n = f"{name}-{n}", n + 1
        out.append(candidate)
    return out


def files(desk: dict, *, version: int) -> dict[str, str]:
    """Every file of the Desk at `version`: its path inside the version folder and its text.
    This is what the engineer reads on the card before anything is written."""
    agent_names = _unique([slug_of(s["name"]["en"]) for s in desk["specialists"]])
    skill_names = _unique([slug_of(p["name"]) for p in desk["procedures"]])
    plugin = {"name": desk["slug"], "version": f"{version}.0.0", "description": desk["purpose"]}
    out = {".claude-plugin/plugin.json": json.dumps(plugin, ensure_ascii=False, indent=2) + "\n"}
    for spec, name in zip(desk["specialists"], agent_names, strict=True):
        described = f"{spec['name']['en']} ({spec['name']['ar']})"
        out[f"agents/{name}.md"] = _frontmatter(name, described, spec["instructions"])
    for procedure, name in zip(desk["procedures"], skill_names, strict=True):
        out[f"skills/{name}/SKILL.md"] = _frontmatter(name, procedure["name"], procedure["text"])
    manifest = {
        "slug": desk["slug"],
        "name": desk["name"],
        "purpose": desk["purpose"],
        "version": version,
        "status": "draft",
        "specialists": [
            {
                "file": f"agents/{name}.md",
                "name": spec["name"],
                "tools": list(spec["tools"]),
                "tier": spec["tier"],
            }
            for spec, name in zip(desk["specialists"], agent_names, strict=True)
        ],
        "procedures": [
            {"file": f"skills/{name}/SKILL.md", "name": p["name"]}
            for p, name in zip(desk["procedures"], skill_names, strict=True)
        ],
    }
    out[MANIFEST] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return out


def next_version(slug: str, data_dir: Path) -> int:
    return (_versions(_folder(slug, data_dir)) or [0])[-1] + 1


def save(desk: dict, data_dir: Path) -> Path:
    """Writes the Desk as its next version and gives that folder. The folder appears whole or
    not at all. Raises `ValueError` for a bad slug and `OSError`."""
    folder = _folder(desk["slug"], data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    version = next_version(desk["slug"], data_dir)
    work = Path(tempfile.mkdtemp(prefix=".saving-", dir=folder))
    try:
        for relative, text in files(desk, version=version).items():
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        target = folder / f"v{version}"
        os.replace(work, target)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return target


def _manifest(slug: str, data_dir: Path, version: int) -> dict:
    path = _folder(slug, data_dir) / f"v{version}" / MANIFEST
    return json.loads(path.read_text(encoding="utf-8"))


def saved(data_dir: Path) -> list[dict]:
    """Every saved Desk at its latest version: slug, name {en, ar}, purpose, version, status."""
    root = data_dir / "desks"
    out = []
    for folder in sorted(root.iterdir()) if root.is_dir() else []:
        if not SLUG.fullmatch(folder.name) or not (versions := _versions(folder)):
            continue
        try:
            m = _manifest(folder.name, data_dir, versions[-1])
        except (OSError, ValueError):
            continue  # a folder the engineer changed by hand: not a Desk One can read
        out.append({k: m[k] for k in ("slug", "name", "purpose", "version", "status")})
    return out


def load(slug: str, data_dir: Path) -> dict:
    """The Desk's latest version, in the shape `save` takes, plus its version and status.
    Raises `LookupError` when there is no such Desk."""
    versions = _versions(_folder(slug, data_dir))
    if not versions:
        raise LookupError(slug)
    root = _folder(slug, data_dir) / f"v{versions[-1]}"
    m = _manifest(slug, data_dir, versions[-1])

    def text(relative: str) -> str:
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise LookupError(slug)  # the manifest points outside its own Desk
        return _body(path.read_text(encoding="utf-8"))

    return {
        "slug": m["slug"],
        "name": m["name"],
        "purpose": m["purpose"],
        "version": m["version"],
        "status": m["status"],
        "specialists": [
            {
                "name": s["name"],
                "instructions": text(s["file"]),
                "tools": list(s["tools"]),
                "tier": s["tier"],
            }
            for s in m["specialists"]
        ],
        "procedures": [{"name": p["name"], "text": text(p["file"])} for p in m["procedures"]],
    }
