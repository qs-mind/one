"""Local, verbatim label–value navigation; no inferred facts or calculations."""

import re

# A short words-only label followed by a numeric value, date or percentage.
_LABEL_VALUE = re.compile(r"^([^\W\d_][^\d\n]{0,59}?)\s*[:：–—-]?\s+(\d[^\n]*)$", re.UNICODE)


def key_lines(text):
    result = []
    for line in text.splitlines():
        line = line.strip()
        match = _LABEL_VALUE.match(line)
        if match and len(match[1].strip()) <= 60 and len(line) <= 160 and line not in result:
            result.append(line)
    return result
