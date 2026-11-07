"""PDFium is not thread safe. Serialize complete document lifetimes.

Lock order: Records lock → other resource locks → PDFIUM (innermost).
Never acquire Records/resource locks, await, call AI or run Tesseract while
holding PDFIUM. Only synchronous PDF operations belong in decorated helpers.
"""

import threading
from functools import wraps

PDFIUM = threading.RLock()


def pdfium_locked(function):
    """Guard a synchronous, in-memory PDF operation through final close."""

    @wraps(function)
    def guarded(*args, **kwargs):
        with PDFIUM:
            return function(*args, **kwargs)

    return guarded
