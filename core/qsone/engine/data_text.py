"""Text is data, never orders.

Every tool result that carries file, web or email text goes to the model inside a fence that is
random for each run: `<<data id=F source=S>> … <</data id=F>>`. Any copy of a fence inside the
text is broken, so the text cannot end the fence early or open a new one."""

import re
import secrets


def new_fence() -> str:
    """12 random hex characters, new for each agent run."""
    return secrets.token_hex(6)


def _broken(text: str) -> str:
    return text.replace("<</data", "<</·data").replace("<<data", "<<·data")


def as_data(text: str, *, source: str, fence: str) -> str:
    """`text` inside the fence. `source` names where it came from, on one line, with no fence
    marks (a file name is untrusted too)."""
    source = re.sub(r"[<>\s]+", " ", source).strip()
    return f"<<data id={fence} source={source}>>\n{_broken(text)}\n<</data id={fence}>>"
