"""The engine's one refusal: a `copy` text by its key, filled with the values that explain it."""

from qsone import copy
from qsone.records.project import RecordsError


class CalcError(RecordsError):
    """`key` names the `copy` text (e.g. "CALC_UNITS_DIFFER"); `values` fill it and are also
    returned to the caller as detail (at, choices...). Status 422 unless given. A text may also
    show `{field}`."""

    def __init__(self, key: str, *, field: str | None = None, status: int = 422, **values):
        text = copy.fill(vars(copy)[key], **{"field": field, **values})
        super().__init__(text, status=status, field=field)
        self.key = key
        self.values = values
