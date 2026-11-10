"""The arithmetic of reading text in pictures, numpy and Pillow only (no OpenCV, no pyclipper,
no python-bidi): text boxes from the detector's probability map, line crops, cut points for long
lines, CTC decoding, and word boxes from the recogniser's columns.

Ported from the OCR spike's prototype (research_notes/2026-11-10-phase1-spikes/ocr.md), which
follows RapidOCR 3.10.0's pre- and post-processing numbers (Apache-2.0) with the spike's tuning:
box padding 1.3 instead of 1.6, and lines wider than 4 times their height read in pieces cut at
blank gaps."""

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from qsone.records.arabic import logical_order

THRESH = 0.3  # a map pixel is text above this
BOX_THRESH = 0.5  # a box is kept when its pixels' mean is above this
UNCLIP = 1.3  # box padding (the spike's tuning; RapidOCR uses 1.6)
MIN_SIZE = 3
CHUNK = 4  # a line wider than this many times its height is read in pieces


@dataclass
class Word:
    text: str
    box: list[float]  # x0, y0, x1, y1 in image pixels
    confidence: float  # mean of its characters' probabilities, 0..1


@dataclass
class Line:
    quad: list[list[float]]
    words: list[Word] = field(default_factory=list)


def components(mask: np.ndarray):
    """8-connected components of a boolean map, from its row runs. Returns per-run arrays (row,
    start, end exclusive, label) and the number of labels."""
    h, w = mask.shape
    padded = np.zeros((h, w + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    rs, s = np.nonzero(d == 1)
    _, e = np.nonzero(d == -1)
    n = len(s)
    first = np.searchsorted(rs, np.arange(h + 1))
    par = list(range(n))
    starts, ends = s.tolist(), e.tolist()

    def find(a):
        root = a
        while par[root] != root:
            root = par[root]
        while par[a] != root:
            par[a], a = root, par[a]
        return root

    for y in range(1, h):
        a, a_end = first[y - 1], first[y]
        b, b_end = first[y], first[y + 1]
        while a < a_end and b < b_end:
            # 8-connectivity: runs touch when they overlap or meet at a corner
            if starts[a] <= ends[b] and starts[b] <= ends[a]:
                ra, rb = find(a), find(b)
                if ra != rb:
                    par[rb] = ra
            if ends[a] < ends[b]:
                a += 1
            else:
                b += 1
    roots = np.fromiter((find(i) for i in range(n)), dtype=np.int64, count=n)
    _, labels = np.unique(roots, return_inverse=True)
    return rs, s, e, labels, (int(labels.max()) + 1 if n else 0)


def boxes_from_map(prob: np.ndarray, *, unclip: float = UNCLIP):
    """Oriented text boxes (4 corners in map pixels) and their scores from a DB probability map."""
    mask = prob > THRESH
    m = mask.copy()  # 2x2 dilation
    m[1:, :] |= mask[:-1, :]
    m[:, 1:] |= mask[:, :-1]
    m[1:, 1:] |= mask[:-1, :-1]
    rs, s, e, lab, count = components(m)
    if not count:
        return []
    n = (e - s).astype(np.float64)
    last = (e - 1).astype(np.float64)
    sx = (s + last) * n / 2
    sxx = (last * (last + 1) * (2 * last + 1) - (s - 1.0) * s * (2 * s - 1.0)) / 6
    y = rs.astype(np.float64)
    area = np.bincount(lab, n, count)
    mx = np.bincount(lab, sx, count) / area
    my = np.bincount(lab, y * n, count) / area
    cxx = np.bincount(lab, sxx, count) / area - mx * mx
    cyy = np.bincount(lab, y * y * n, count) / area - my * my
    cxy = np.bincount(lab, y * sx, count) / area - mx * my
    theta = 0.5 * np.arctan2(2 * cxy, cxx - cyy)  # the principal axis
    theta[np.abs(theta) < math.radians(0.7)] = 0.0  # printed pages: keep boxes upright
    cos, sin = np.cos(theta)[lab], np.sin(theta)[lab]
    corners = [(s - 0.5, y - 0.5), (e - 0.5, y - 0.5), (s - 0.5, y + 0.5), (e - 0.5, y + 0.5)]
    u = np.stack([xs * cos + ys * sin for xs, ys in corners])
    v = np.stack([-xs * sin + ys * cos for xs, ys in corners])
    umin, umax = np.full(count, np.inf), np.full(count, -np.inf)
    vmin, vmax = np.full(count, np.inf), np.full(count, -np.inf)
    np.minimum.at(umin, lab, u.min(0))
    np.maximum.at(umax, lab, u.max(0))
    np.minimum.at(vmin, lab, v.min(0))
    np.maximum.at(vmax, lab, v.max(0))
    # the mean probability over the component's own pixels, from prefix sums along rows
    csum = np.concatenate(
        [np.zeros((prob.shape[0], 1)), np.cumsum(prob, axis=1, dtype=np.float64)], 1
    )
    score = np.bincount(lab, csum[rs, e] - csum[rs, s], count) / area
    found = []
    for i in range(count):
        bw, bh = umax[i] - umin[i], vmax[i] - vmin[i]
        if min(bw, bh) < MIN_SIZE or score[i] < BOX_THRESH:
            continue
        dist = bw * bh * unclip / (2 * (bw + bh))
        u0, u1, v0, v1 = umin[i] - dist, umax[i] + dist, vmin[i] - dist, vmax[i] + dist
        if min(u1 - u0, v1 - v0) < MIN_SIZE + 2:
            continue
        c, sn = math.cos(theta[i]), math.sin(theta[i])
        quad = [
            [a * c - b * sn, a * sn + b * c] for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
        ]
        found.append((quad, float(score[i])))
    return found


def crop(image: Image.Image, quad) -> tuple[Image.Image, int]:
    """The line under `quad`, upright; turned 90° (and so said) when it stands taller than wide."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    cw = max(1, int(max(math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x3, y2 - y3))))
    ch = max(1, int(max(math.hypot(x3 - x0, y3 - y0), math.hypot(x2 - x1, y2 - y1))))
    if abs(y1 - y0) < 0.5 and abs(x3 - x0) < 0.5:
        left, top = int(round(x0)), int(round(y0))
        out = image.crop((left, top, left + cw, top + ch))
    else:  # Pillow's QUAD takes upper left, lower left, lower right, upper right
        out = image.transform((cw, ch), Image.QUAD, (x0, y0, x3, y3, x2, y2, x1, y1), Image.BICUBIC)
    if ch / cw >= 1.5:
        return out.transpose(Image.ROTATE_90), 90
    return out, 0


def split_line(line: Image.Image, max_ratio: int = CHUNK) -> list[tuple[int, int]]:
    """Cut points for a long line image: pieces at most `max_ratio` times as wide as high, cut in
    the middle of a blank gap between words, never through ink when a gap exists."""
    w, h = line.size
    target = max_ratio * h
    if w <= target * 1.15:
        return [(0, w)]
    g = np.asarray(line.convert("L"), dtype=np.int16)
    ink = (np.abs(g - np.median(g)) > 50).any(axis=0)
    edges = np.flatnonzero(np.diff(np.concatenate([[1], ink.astype(np.int8), [1]])))
    gaps = [
        (a, b) for a, b in zip(edges[::2], edges[1::2], strict=False) if b - a >= max(3, h // 8)
    ]
    mids = [int((a + b) // 2) for a, b in gaps]
    cuts, last = [], 0
    while w - last > target * 1.15:
        near = [m for m in mids if last + target * 0.5 <= m <= last + target]
        if not near:
            near = [m for m in mids if m > last + target * 0.5][:1]
        if not near or near[-1] >= w - 4:
            break
        last = near[-1]
        cuts.append(last)
    xs = [0, *cuts, w]
    return list(zip(xs, xs[1:], strict=False))


def decode(pred: np.ndarray, chars: list[str], used: list[float]):
    """Greedy CTC: per row, (character, probability, x as a fraction of the crop's width) in
    visual order. `chars[0]` is the blank; `used[i]` is how much of the batch width row i fills."""
    best, prob = pred.argmax(2), pred.max(2)
    steps = pred.shape[1]
    out = []
    for row, ids in enumerate(best):
        keep = ids != 0
        keep[1:] &= ids[1:] != ids[:-1]
        out.append(
            [
                (chars[ids[c]], float(prob[row, c]), min(1.0, (c + 0.5) / steps / used[row]))
                for c in np.nonzero(keep)[0]
            ]
        )
    return out


def span(quad, f0: float, f1: float, turned: int) -> list[float]:
    """The upright box of the part of `quad` between fractions f0 and f1 of its reading width."""
    p0, p1, p2, p3 = (np.array(p, dtype=np.float64) for p in quad)
    if turned == 90:  # the crop was turned: its width runs along the box's height
        pts = [p0 + f0 * (p3 - p0), p1 + f0 * (p2 - p1), p0 + f1 * (p3 - p0), p1 + f1 * (p2 - p1)]
    else:
        pts = [p0 + f0 * (p1 - p0), p3 + f0 * (p2 - p3), p0 + f1 * (p1 - p0), p3 + f1 * (p2 - p3)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]


def words(chars, quad, turned: int = 0) -> list[Word]:
    """A line's characters (visual order) as words in reading order, each with its box."""
    ordered = logical_order([(c, (p, fx)) for c, p, fx in chars])
    half = 0.5 / max(len(chars), 1)
    out, current = [], []
    for ch, (p, fx) in [*ordered, (" ", (1.0, 0.0))]:
        if ch != " ":
            current.append((ch, p, fx))
            continue
        if current:
            f0 = max(0.0, min(f for _, _, f in current) - half)
            f1 = min(1.0, max(f for _, _, f in current) + half)
            text = "".join(c for c, _, _ in current)
            out.append(
                Word(text, span(quad, f0, f1, turned), sum(q for _, q, _ in current) / len(current))
            )
            current = []
    return out


def sort_lines(lines: list[Line]) -> list[Line]:
    """Top to bottom; inside a row, right to left when most lines hold Arabic."""
    if not lines:
        return lines
    arabic = sum(any("؀" <= c <= "ۿ" for w in ln.words for c in w.text) for ln in lines)
    rtl = arabic * 2 >= len(lines)
    rows, row, row_y = [], [], 0.0
    for ln in sorted(lines, key=lambda ln: min(p[1] for p in ln.quad)):
        y0, y1 = min(p[1] for p in ln.quad), max(p[1] for p in ln.quad)
        if row and y0 > row_y + 0.5 * (y1 - y0):
            rows.append(row)
            row = []
        if not row:
            row_y = y0
        row.append(ln)
    rows.append(row)
    return [
        ln for r in rows for ln in sorted(r, key=lambda ln: min(p[0] for p in ln.quad), reverse=rtl)
    ]
