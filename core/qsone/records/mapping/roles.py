"""Conservative source roles for tender requirements versus company working files."""

from qsone import copy
from qsone.records.arabic import clean


def file_role(folder, kind=None):
    path = clean(folder or "").casefold()
    if any(term in path for term in ("المستلم", "received", "tender documents")):
        return copy.MAP_ROLE_RECEIVED
    if any(term in path for term in ("الفني", "المالي", "submission", "working", "our programme")):
        return copy.MAP_ROLE_WORKING
    if any(term in clean(kind or "").casefold() for term in ("submission", "working", "company")):
        return copy.MAP_ROLE_WORKING
    if any(
        term in clean(kind or "").casefold()
        for term in ("tender", "conditions", "invitation to bid")
    ):
        return copy.MAP_ROLE_RECEIVED
    return copy.MAP_ROLE_UNKNOWN
