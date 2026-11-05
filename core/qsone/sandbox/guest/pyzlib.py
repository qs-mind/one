"""zlib for the Sandbox's Python, in pure Python: the WASI builds of CPython ship without it.

xlsx and docx files are zip files whose parts are deflated, so openpyxl needs `zipfile` to
inflate. The guest registers this module as `zlib` when the real one is missing. It inflates
raw, zlib and gzip streams (RFC 1950-1952), checked by their CRC or Adler-32. It writes valid
deflate streams made of stored blocks: correct, but not smaller; Excel opens them as usual.
`crc32` is binascii's, which is C code.

A decompressor gives its output once the whole stream has arrived (zipfile then calls `flush`),
and tries earlier only each time its input has doubled, so the total work stays linear.
"""

import binascii
from itertools import accumulate

DEFLATED = 8
MAX_WBITS = 15
DEF_MEM_LEVEL = 8
DEF_BUF_SIZE = 16384
Z_NO_COMPRESSION, Z_BEST_SPEED, Z_BEST_COMPRESSION, Z_DEFAULT_COMPRESSION = 0, 1, 9, -1
Z_DEFAULT_STRATEGY, Z_FILTERED, Z_HUFFMAN_ONLY, Z_RLE, Z_FIXED = 0, 1, 2, 3, 4
Z_NO_FLUSH, Z_PARTIAL_FLUSH, Z_SYNC_FLUSH, Z_FULL_FLUSH, Z_FINISH, Z_BLOCK = 0, 1, 2, 3, 4, 5
ZLIB_VERSION = ZLIB_RUNTIME_VERSION = "1.3.1 (pure Python, stored blocks)"


class error(Exception):  # noqa: N818 - zlib's own name
    pass


class _Short(Exception):
    """The stream stops before its end: more input may complete it."""


crc32 = binascii.crc32


def adler32(data, value=1) -> int:
    a, b = value & 0xFFFF, (value >> 16) & 0xFFFF
    view = memoryview(data).cast("B")
    for i in range(0, len(view), 1 << 16):
        sums = list(accumulate(view[i : i + (1 << 16)], initial=a))
        b = (b + sum(sums) - a) % 65521
        a = sums[-1] % 65521
    return (b << 16) | a


# --- inflate (RFC 1951) ---------------------------------------------------------------------

_LBASE = (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99,
          115, 131, 163, 195, 227, 258)  # fmt: skip
_LEXT = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0)
_DBASE = (1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025,
          1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577)  # fmt: skip
_DEXT = (0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12,
         13, 13)  # fmt: skip
_ORDER = (16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15)


def _table(lengths) -> tuple[list[int], int]:
    """A lookup table for a canonical Huffman code: `table[next bits]` = symbol << 4 | length.

    An entry of 0 is a code that does not exist. Incomplete codes are allowed (RFC 1951 lets a
    single distance code stand alone); over-subscribed ones are not."""
    bits = max(lengths, default=0) or 1
    if sum(1 << (bits - n) for n in lengths if n) > 1 << bits:
        raise error("Error -3 while decompressing data: invalid code lengths set")
    count = [0] * (bits + 1)
    for n in lengths:
        count[n] += 1
    count[0] = 0
    code, next_code = 0, [0] * (bits + 1)
    for n in range(1, bits + 1):
        code = (code + count[n - 1]) << 1
        next_code[n] = code
    table = [0] * (1 << bits)
    for symbol, n in enumerate(lengths):
        if n:
            reverse = int(format(next_code[n], f"0{n}b")[::-1], 2)
            next_code[n] += 1
            table[reverse :: 1 << n] = [symbol << 4 | n] * (1 << (bits - n))
    return table, bits


_FIXED = (_table([8] * 144 + [9] * 112 + [7] * 24 + [8] * 8), _table([5] * 30))


def _inflate(data: bytes, pos: int) -> tuple[bytearray, int]:
    """Inflates one raw deflate stream from `data[pos:]`; returns the bytes and where it ended."""
    out = bytearray()
    bb = bc = 0  # bit buffer (least significant bit first) and how many bits it holds
    n = len(data)
    final = 0
    try:
        while not final:
            if bc < 32:
                chunk = data[pos : pos + 4]
                bb |= int.from_bytes(chunk, "little") << bc
                bc += len(chunk) << 3
                pos += len(chunk)
            final, kind = bb & 1, (bb >> 1) & 3
            bb >>= 3
            bc -= 3
            if bc < 0:
                raise _Short
            if kind == 0:  # stored: whole bytes after the header's byte
                pos -= bc >> 3
                bb = bc = 0
                if pos + 4 > n:
                    raise _Short
                size = data[pos] | data[pos + 1] << 8
                if size != (~(data[pos + 2] | data[pos + 3] << 8)) & 0xFFFF:
                    raise error("Error -3 while decompressing data: invalid stored block lengths")
                pos += 4
                if pos + size > n:
                    raise _Short
                out += data[pos : pos + size]
                pos += size
                continue
            if kind == 1:
                (lt, lbits), (dt, dbits) = _FIXED
            elif kind == 2:
                if bc < 32:
                    chunk = data[pos : pos + 4]
                    bb |= int.from_bytes(chunk, "little") << bc
                    bc += len(chunk) << 3
                    pos += len(chunk)
                hlit, hdist, hclen = (bb & 31) + 257, ((bb >> 5) & 31) + 1, ((bb >> 10) & 15) + 4
                bb >>= 14
                bc -= 14
                lens = [0] * 19
                for i in range(hclen):
                    if bc < 32:
                        chunk = data[pos : pos + 4]
                        bb |= int.from_bytes(chunk, "little") << bc
                        bc += len(chunk) << 3
                        pos += len(chunk)
                    lens[_ORDER[i]] = bb & 7
                    bb >>= 3
                    bc -= 3
                if bc < 0:
                    raise _Short
                ct, cbits = _table(lens)
                cmask = (1 << cbits) - 1
                lengths: list[int] = []
                while len(lengths) < hlit + hdist:
                    if bc < 32:
                        chunk = data[pos : pos + 4]
                        bb |= int.from_bytes(chunk, "little") << bc
                        bc += len(chunk) << 3
                        pos += len(chunk)
                    e = ct[bb & cmask]
                    if not e:
                        raise error("Error -3 while decompressing data: invalid code lengths set")
                    bb >>= e & 15
                    bc -= e & 15
                    symbol = e >> 4
                    if symbol < 16:
                        lengths.append(symbol)
                    elif symbol == 16:
                        if not lengths:
                            raise error(
                                "Error -3 while decompressing data: invalid bit length repeat"
                            )
                        lengths += [lengths[-1]] * (3 + (bb & 3))
                        bb >>= 2
                        bc -= 2
                    elif symbol == 17:
                        lengths += [0] * (3 + (bb & 7))
                        bb >>= 3
                        bc -= 3
                    else:
                        lengths += [0] * (11 + (bb & 127))
                        bb >>= 7
                        bc -= 7
                    if bc < 0:
                        raise _Short
                if len(lengths) > hlit + hdist:
                    raise error("Error -3 while decompressing data: invalid bit length repeat")
                if not lengths[256]:
                    raise error(
                        "Error -3 while decompressing data: invalid code -- missing end-of-block"
                    )
                (lt, lbits), (dt, dbits) = _table(lengths[:hlit]), _table(lengths[hlit:])
            else:
                raise error("Error -3 while decompressing data: invalid block type")
            lmask, dmask = (1 << lbits) - 1, (1 << dbits) - 1
            while True:  # the hot loop: one literal, or one length and distance, per turn
                if bc < 48:
                    chunk = data[pos : pos + 6]
                    bb |= int.from_bytes(chunk, "little") << bc
                    bc += len(chunk) << 3
                    pos += len(chunk)
                e = lt[bb & lmask]
                length = e & 15
                bb >>= length
                bc -= length
                symbol = e >> 4
                if symbol < 256:
                    if not e:
                        raise error(
                            "Error -3 while decompressing data: invalid literal/length code"
                        )
                    out.append(symbol)
                    if bc < 0:
                        raise _Short
                    continue
                if symbol == 256:
                    if bc < 0:
                        raise _Short
                    break
                symbol -= 257
                if symbol >= 29:
                    raise error("Error -3 while decompressing data: invalid literal/length code")
                extra = _LEXT[symbol]
                length = _LBASE[symbol] + (bb & ((1 << extra) - 1))
                bb >>= extra
                bc -= extra
                e = dt[bb & dmask]
                if not e or e >> 4 >= 30:
                    raise error("Error -3 while decompressing data: invalid distance code")
                bb >>= e & 15
                bc -= e & 15
                symbol = e >> 4
                extra = _DEXT[symbol]
                distance = _DBASE[symbol] + (bb & ((1 << extra) - 1))
                bb >>= extra
                bc -= extra
                if bc < 0:
                    raise _Short
                if distance > len(out):
                    raise error("Error -3 while decompressing data: invalid distance too far back")
                start = len(out) - distance
                if length <= distance:
                    out += out[start : start + length]
                else:
                    piece = out[start:]
                    out += (piece * (length // distance + 1))[:length]
    except error:
        if pos >= n:  # the bits after the end read as zeros: likely only cut short
            raise _Short from None
        raise
    return out, pos - (bc >> 3)


def _unwrap(data: bytes, wbits: int) -> tuple[bytes, int]:
    """One whole stream in the format `wbits` names; returns the bytes and where it ended."""
    if wbits >= 32:  # 32 + n: zlib or gzip, by the header
        wbits = 16 + MAX_WBITS if data[:2] == b"\x1f\x8b" else MAX_WBITS
    if -15 <= wbits <= -8:
        out, end = _inflate(data, 0)
        return bytes(out), end
    if 0 <= wbits <= 15:
        if len(data) < 2:
            raise _Short
        if (data[0] << 8 | data[1]) % 31 or data[0] & 15 != DEFLATED:
            raise error("Error -3 while decompressing data: incorrect header check")
        if data[1] & 0x20:
            raise error("Error 2 while decompressing data: a preset dictionary is not supported")
        out, end = _inflate(data, 2)
        if len(data) < end + 4:
            raise _Short
        if int.from_bytes(data[end : end + 4], "big") != adler32(out):
            raise error("Error -3 while decompressing data: incorrect data check")
        return bytes(out), end + 4
    if 24 <= wbits <= 31:
        if len(data) < 10:
            raise _Short
        if data[:3] != b"\x1f\x8b\x08":
            raise error("Error -3 while decompressing data: incorrect header check")
        flags, pos = data[3], 10
        if flags & 4:  # FEXTRA
            if len(data) < pos + 2:
                raise _Short
            pos += 2 + (data[pos] | data[pos + 1] << 8)
        for bit in (8, 16):  # FNAME, FCOMMENT: zero-terminated
            if flags & bit:
                zero = data.find(b"\x00", pos)
                if zero < 0:
                    raise _Short
                pos = zero + 1
        if flags & 2:  # FHCRC
            pos += 2
        if len(data) < pos:
            raise _Short
        out, end = _inflate(data, pos)
        if len(data) < end + 8:
            raise _Short
        if (
            int.from_bytes(data[end : end + 4], "little") != crc32(out)
            or int.from_bytes(data[end + 4 : end + 8], "little") != len(out) & 0xFFFFFFFF
        ):
            raise error("Error -3 while decompressing data: incorrect data check")
        return bytes(out), end + 8
    raise ValueError("Invalid initialization option")


def decompress(data, /, wbits=MAX_WBITS, bufsize=DEF_BUF_SIZE) -> bytes:
    try:
        out, _end = _unwrap(bytes(data), wbits)
    except _Short:
        raise error("Error -5 while decompressing data: incomplete or truncated stream") from None
    return out


class _Decompress:
    def __init__(self, wbits: int) -> None:
        self._wbits = wbits
        self._input = bytearray()
        self._tried = 0  # input size at the last try that ran short
        self.eof = False
        self.unused_data = b""
        self.unconsumed_tail = b""

    def decompress(self, data, max_length=0) -> bytes:
        if self.eof:
            self.unused_data += bytes(data)
            return b""
        self._input += data
        if len(self._input) < 2 * self._tried:
            return b""
        return self._try(last=False)

    def _try(self, last: bool) -> bytes:
        try:
            out, end = _unwrap(bytes(self._input), self._wbits)
        except (_Short, error) as problem:
            if last and isinstance(problem, error):
                raise
            self._tried = len(self._input)
            return b""
        self.eof = True
        self.unused_data = bytes(self._input[end:])
        self._input = bytearray()
        return out

    def flush(self, length=DEF_BUF_SIZE) -> bytes:
        if self.eof or not self._input:
            return b""
        return self._try(last=True)


def decompressobj(wbits=MAX_WBITS, zdict=b"") -> _Decompress:
    if zdict:
        raise error("a preset dictionary is not supported")
    if not (-15 <= wbits <= -8 or 0 <= wbits <= 15 or 24 <= wbits <= 31 or 40 <= wbits <= 47):
        raise ValueError("Invalid initialization option")
    return _Decompress(wbits)


# --- deflate, in stored blocks --------------------------------------------------------------


def _stored(data, last: bool) -> bytes:
    data = bytes(data)
    parts = []
    for i in range(0, len(data), 0xFFFF):
        piece = data[i : i + 0xFFFF]
        final = last and i + 0xFFFF >= len(data)
        size = len(piece)
        parts.append(bytes((final, size & 255, size >> 8, ~size & 255, (~size >> 8) & 255)) + piece)
    if last and not data:
        parts.append(b"\x01\x00\x00\xff\xff")
    return b"".join(parts)


class _Compress:
    def __init__(self, wbits: int) -> None:
        if -15 <= wbits <= -9:
            self._head, self._kind = b"", "raw"
        elif 9 <= wbits <= 15:
            self._head, self._kind = b"\x78\x01", "zlib"
        elif 25 <= wbits <= 31:
            self._head, self._kind = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff", "gzip"
        else:
            raise ValueError("Invalid initialization option")
        self._crc, self._adler, self._size, self._done = 0, 1, 0, False

    def compress(self, data, /) -> bytes:
        if self._done:
            raise error("Error -2 while compressing data: inconsistent stream state")
        self._crc, self._size = crc32(data, self._crc), self._size + len(data)
        if self._kind == "zlib":
            self._adler = adler32(data, self._adler)
        head, self._head = self._head, b""
        return head + (_stored(data, last=False) if len(data) else b"")

    def flush(self, mode=Z_FINISH, /) -> bytes:
        if self._done or mode == Z_NO_FLUSH:
            return b""
        head, self._head = self._head, b""
        if mode != Z_FINISH:
            return head + b"\x00\x00\x00\xff\xff"  # an empty stored block, as zlib's sync flush
        self._done = True
        tail = b""
        if self._kind == "zlib":
            tail = self._adler.to_bytes(4, "big")
        elif self._kind == "gzip":
            tail = self._crc.to_bytes(4, "little") + (self._size & 0xFFFFFFFF).to_bytes(4, "little")
        return head + _stored(b"", last=True) + tail


def compressobj(
    level=Z_DEFAULT_COMPRESSION,
    method=DEFLATED,
    wbits=MAX_WBITS,
    memLevel=DEF_MEM_LEVEL,  # noqa: N803 - zlib's own name
    strategy=Z_DEFAULT_STRATEGY,
    zdict=None,
) -> _Compress:
    if method != DEFLATED:
        raise ValueError("Invalid initialization option")
    return _Compress(wbits)


def compress(data, /, level=Z_DEFAULT_COMPRESSION, wbits=MAX_WBITS) -> bytes:
    c = _Compress(wbits)
    return c.compress(data) + c.flush()
