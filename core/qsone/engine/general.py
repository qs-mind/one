"""The Engineer Records file at `<data>/engineer/`: the General chat and the cost book.

It is a Records file like a project's, with the same schema and its own key in the key store,
but it is not under `projects/`, so `Projects.list()` never sees it. Plan 8 opens the same
folder; whichever comes first creates it."""

from pathlib import Path

from qsone.records.project import FILE_NAME, Records

FOLDER = "engineer"
NAME = "Engineer Records"


def open_engineer_records(data_dir: Path) -> Records:
    """Creates the file on first use and opens it otherwise. Raises what `Records.create` and
    `Records.open` raise. Close it when done."""
    folder = Path(data_dir) / FOLDER
    if (folder / FILE_NAME).is_file():
        return Records.open(folder)
    return Records.create(folder, name=NAME, actor="engineer")
