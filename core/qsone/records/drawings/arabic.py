"""Legacy Arabic SHX keyboard glyphs; font evidence is mandatory.

These fonts store keys, not Unicode Arabic. Capitals select contextual glyphs.
Do not apply this map to Unicode fonts or arbitrary Latin-looking strings.
"""

import re

# Extended only from identified keyboard fonts, never from a style's display name.
KEYBOARD_FONTS = frozenset(
    {"arabic", "arabic1", "arabic2", "arabic3", "arabic4", "xarb", "xarab", "sarb"}
)
# lam-alef occupies a single key but expands to two Unicode letters.
_KEYS = dict(
    zip(
        "`qwertyuiop[]asdfghjkl;'zxcvbnm,./",
        [
            "ذ",
            "ض",
            "ص",
            "ث",
            "ق",
            "ف",
            "غ",
            "ع",
            "ه",
            "خ",
            "ح",
            "ج",
            "د",
            "ش",
            "س",
            "ي",
            "ب",
            "ل",
            "ا",
            "ت",
            "ن",
            "م",
            "ك",
            "ط",
            "ئ",
            "ء",
            "ؤ",
            "ر",
            "لا",
            "ى",
            "ة",
            "و",
            "ز",
            "ظ",
        ],
        strict=True,
    )
)
_KEYS.update({k.upper(): v for k, v in list(_KEYS.items()) if k.isalpha()})
_KEYS.update(
    {
        ":": "ك",
        "B": "لا",
        "_": "ـ",
        "{": "ج",
        "}": "د",
        "<": "و",
        ">": "ز",
        "?": "ظ",
        '"': "ط",
        "~": "ذ",
        "X": "أ",
    }
)
_TABLE = str.maketrans(_KEYS)


def keyboard_font(font: str) -> bool:
    name = re.split(r"[/\\]", font.split("|")[0])[-1].lower()
    if name.endswith(".ttf") or name.endswith(".otf"):
        return False
    return name.removesuffix(".shx") in KEYBOARD_FONTS


def decode_text(row: dict) -> dict:
    if row.get("arabic_decoded"):
        return row
    raw = row.get("raw_text", row.get("text", ""))
    font = row.get("font_file", "")
    active = keyboard_font(font) or keyboard_font(row.get("big_font_file", ""))
    used = False
    if not re.search(r"\\[Ff]", raw):
        if active:
            parts = re.split(r"(%%(?:[cCdDpPuUoOkK]|\d{3}))", row.get("text", raw))
            text = "".join(
                {"c": "Ø", "d": "°", "p": "±", "u": "", "o": "", "k": ""}.get(
                    part[2:].lower(), part
                )
                if part.startswith("%%")
                else part.translate(_TABLE)
                for part in parts
            )
            used = text != row.get("text", raw)
        else:
            return row
    else:
        parts, stack = [], []
        i = 0
        while i < len(raw):
            char = raw[i]
            if raw[i : i + 2] == "%%" and i + 2 < len(raw):
                code = raw[i + 2].lower()
                parts.append({"c": "Ø", "d": "°", "p": "±"}.get(code, ""))
                i += 2
            elif char == "{":
                stack.append(active)
            elif char == "}":
                active = stack.pop() if stack else active
            elif char == "\\" and i + 1 < len(raw):
                command = raw[i + 1]
                if command in "Ff":
                    end = raw.find(";", i + 2)
                    if end < 0:
                        break
                    active = keyboard_font(raw[i + 2 : end])
                    i = end
                elif command in "P~":
                    parts.append("\n" if command == "P" else " ")
                    i += 1
                elif command in "\\{}":
                    parts.append(command)
                    i += 1
                elif command == "U" and raw[i + 2 : i + 3] == "+":
                    try:
                        parts.append(chr(int(raw[i + 3 : i + 7], 16)))
                        i += 6
                    except ValueError:
                        i += 1
                elif command in "LlOoKk":
                    i += 1
                else:
                    end = raw.find(";", i + 2)
                    i = end if end >= 0 else i + 1
            else:
                decoded = char.translate(_TABLE) if active else char
                used |= decoded != char
                parts.append(decoded)
            i += 1
        text = "".join(parts)
        if not used:
            return row
    return {**row, "raw_text": raw, "text": text, "arabic_decoded": used}
