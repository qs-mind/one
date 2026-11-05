"""A zip from a tender folder, opened in memory (Plan 8, decision 15). Nothing touches the disk.

- **Names.** A member name without the UTF-8 flag is read as cp720 (Arabic DOS, what Windows'
  own zip writes on an Arabic system), then cp1256 (Arabic Windows); the first that reads as
  Arabic and plain text wins, else it stays as zipfile read it. A member's folders become its
  `folder`, under the zip's own name: `المناقصة.zip/مواصفات`. A `..` part or a drive letter
  never climbs out: only the plain parts are kept.
- **Limits, checked before anything is read:** at most 5,000 members, 2 GB unpacked in all, and
  a 200:1 packing ratio. Over them the zip is refused (ZIP_TOO_BIG, ZIP_UNSAFE) and the caller
  keeps it as one file, not opened. A member over 256 MB comes back with no bytes, to be listed
  as too big while the others go on. A member that unpacks to more than its header says stops
  the zip as unsafe.
- **Not opened:** a zip inside a zip is a member like any other (kept as a file); RAR and 7z have
  no permissive reader, so they are kept and not read."""

import re
import zipfile
from collections.abc import Iterator
from io import BytesIO

from qsone import copy
from qsone.records.files import MAX_FILE_BYTES
from qsone.records.project import RecordsError

MAX_MEMBERS = 5000
MAX_TOTAL = 2 * 1024**3
MAX_RATIO = 200
MAX_MEMBER = MAX_FILE_BYTES
_READ = 1024 * 1024  # bytes read at a time
_UTF8 = 0x800
# Arabic letters and marks, Latin, digits, spaces and the usual punctuation of a file name.
_PLAIN = re.compile(r"[؀-ۿݐ-ݿ\w\s.,()\[\]{}&+'!#$%@=~^-]*")
_DRIVE = re.compile(r"^[A-Za-z]:$")


def is_zip(name: str, data: bytes) -> bool:
    return name.lower().endswith(".zip") and zipfile.is_zipfile(BytesIO(data))


def _name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & _UTF8:
        return info.filename
    try:
        raw = info.orig_filename.encode("cp437")  # how zipfile read it
    except UnicodeEncodeError:
        return info.filename
    for encoding in ("cp720", "cp1256"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if _PLAIN.fullmatch(text.replace("/", "").replace("\\", "")):
            return text
    return info.filename


def _parts(path: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[/\\]", path)]
    return [p for p in parts if p and p not in (".", "..") and not _DRIVE.match(p)]


def _refuse(text: dict) -> RecordsError:
    return RecordsError(text, status=422)


def members(name: str, data: bytes) -> Iterator[tuple[str, str, bytes | None]]:
    """(folder, name, bytes) for each file in the zip `name`; bytes is None for a member over
    256 MB. Raises `RecordsError` before yielding anything: ZIP_UNSAFE (too many members, packed
    too tightly, or not a zip that opens) or ZIP_TOO_BIG (over 2 GB unpacked); ZIP_UNSAFE also
    when a member unpacks past its stated size."""
    zip_name = _parts(name)[-1] if _parts(name) else "zip"
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except (zipfile.BadZipFile, ValueError, OSError):
        raise _refuse(copy.ZIP_UNSAFE) from None
    with archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if len(infos) > MAX_MEMBERS:
            raise _refuse(copy.ZIP_UNSAFE)
        total = sum(i.file_size for i in infos)
        if total > MAX_TOTAL:
            raise _refuse(copy.ZIP_TOO_BIG)
        packed = sum(i.compress_size for i in infos)
        if total > MAX_RATIO * max(packed, 1):
            raise _refuse(copy.ZIP_UNSAFE)
        for info in infos:
            parts = _parts(_name(info))
            if not parts:
                continue
            folder = "/".join([zip_name, *parts[:-1]])
            if info.file_size > MAX_MEMBER:
                yield folder, parts[-1], None
                continue
            yield folder, parts[-1], _read(archive, info)


def _read(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """The member's bytes, never more than its header says (a lying header is a bomb)."""
    out = bytearray()
    try:
        with archive.open(info) as member:
            while chunk := member.read(_READ):
                out += chunk
                if len(out) > info.file_size:
                    raise _refuse(copy.ZIP_UNSAFE)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError):
        raise _refuse(copy.ZIP_UNSAFE) from None  # damaged, encrypted, or an unknown method
    return bytes(out)
