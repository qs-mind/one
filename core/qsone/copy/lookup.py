"""The text a refusal's English words belong to (`words_for`)."""

import sys


def words_for(said: str) -> dict[str, str] | None:
    """The {en, ar} text whose English words `said` holds (a refusal the model was given in
    English), or None when it holds none.

    Among the package's texts without blanks whose English is at least 20 characters and occurs
    in `said`, the longest wins; of equal length, the one that starts first in `said`. A text is
    never reported for a message it does not occur in."""
    # The package's own names, read at each call: a text added to an area module is found here
    # with no list to keep.
    found, best = None, None
    for value in vars(sys.modules[__spec__.parent]).values():
        if not (
            isinstance(value, dict)
            and isinstance(value.get("en"), str)
            and isinstance(value.get("ar"), str)
            and "{" not in value["en"]
            and len(value["en"]) >= 20
        ):
            continue
        start = said.find(value["en"])
        rank = (-len(value["en"]), start)
        if start >= 0 and (best is None or rank < best):
            found, best = value, rank
    return found
