"""Puts characters on spare keys of the virtual screen's keyboard, all at once, so `xdotool type` finds each on a key
of its own and never remaps a key while the window may still be reading the last one (under load, that remapping
turns «راجع» into «رججع»). The keys are pressed by the X server as a person's would be: this only says what they
are labelled. Usage (DISPLAY set): python3 keymap.py map <char>...   -> the keycodes used, one per line
                                   python3 keymap.py unmap <keycode>...
Plain ctypes over libX11, no packages."""

import ctypes
import sys

x = ctypes.CDLL("libX11.so.6")
x.XOpenDisplay.restype = ctypes.c_void_p
x.XOpenDisplay.argtypes = [ctypes.c_char_p]
x.XGetKeyboardMapping.restype = ctypes.POINTER(ctypes.c_ulong)
x.XGetKeyboardMapping.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
x.XChangeKeyboardMapping.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_ulong), ctypes.c_int]
x.XDisplayKeycodes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
x.XFree.argtypes = [ctypes.c_void_p]
x.XCloseDisplay.argtypes = [ctypes.c_void_p]


def keysym(char: str) -> int:
    code = ord(char)
    return code if 0x20 <= code <= 0x7E or 0xA0 <= code <= 0xFF else 0x1000000 + code


def is_unused(sym: int) -> bool:
    """An XF86 multimedia key (volume, mail, …) or F13 to F35."""
    return 0x1008FF00 <= sym <= 0x1008FFFF or 0xFFCA <= sym <= 0xFFE0


def set_key(display, keycode: int, sym: int) -> None:
    row = (ctypes.c_ulong * 2)(sym, sym)  # the same with or without Shift
    x.XChangeKeyboardMapping(display, keycode, 2, row, 1)


def main() -> None:
    command, *args = sys.argv[1:]
    display = x.XOpenDisplay(None)
    if not display:
        sys.exit("cannot open the X display")
    low, high = ctypes.c_int(), ctypes.c_int()
    x.XDisplayKeycodes(display, ctypes.byref(low), ctypes.byref(high))
    if command == "map":
        per = ctypes.c_int()
        count = high.value - low.value + 1
        table = x.XGetKeyboardMapping(display, low.value, count, ctypes.byref(per))
        mapped = {table[i] for i in range(count * per.value)}
        row = lambda k: [table[k * per.value + j] for j in range(per.value)]  # noqa: E731
        # keys with nothing on them, then the multimedia and F13+ keys no one presses on this screen
        empty = [low.value + k for k in range(count) if not any(row(k))]
        unused = [low.value + k for k in range(count) if any(row(k)) and all(s == 0 or is_unused(s) for s in row(k))]
        spare = empty + unused
        x.XFree(table)
        wanted = [s for s in dict.fromkeys(keysym(c) for c in "".join(args)) if s not in mapped]
        if len(wanted) > len(spare):
            sys.exit(f"{len(wanted)} characters need keys but only {len(spare)} keys are spare")
        for keycode, sym in zip(spare, wanted):
            set_key(display, keycode, sym)
            print(keycode)
    elif command == "unmap":
        for keycode in args:
            set_key(display, int(keycode), 0)
    else:
        sys.exit(f"unknown command {command}")
    x.XSync(display, 0)
    x.XCloseDisplay(display)


if __name__ == "__main__":
    main()
