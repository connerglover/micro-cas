"""Desktop stand-in for the TI-84 EVO `ti_graphics` module (DESIGN.md sections 13, 16, 20.9).

Desktop only (never ships; its frames are not counted by the depth checker). It does three
things:

1. **Draw transcript.** Every drawing or state call is appended to `CALLS` as a flat tuple
   `(name, arg, ...)`; `transcript_text()` prints it one call per line (ASCII, deterministic),
   for golden files. `setColor` and `setPixel` colors are normalized to `r, g, b`. Pure queries
   (`getPixel`, `string_size`, `hsv_to_rgb`) are not in the transcript; every call of every
   function is counted in `COUNTS`.
2. **Screen model.** A `W` x `H` framebuffer of 0xRRGGBB ints, so `getPixel` answers and
   `screenshot()` writes a PNG (text is drawn as one block per character).
3. **Screen text.** Each `drawString` becomes a text item that owns its cell box. Filled shapes
   (`fillRect`, `fillCircle`, `fillPolygon`, `fillArc`, `cls`, the region restored by
   `popImage`) and later text erase the pixels they cover; an item disappears when all of its
   pixels are erased. Lines, outlines and pixels never erase text. `texts()`, `screen_text()`
   and `texts_in()` read what is left. Text drawn over a *different* live text without a clear
   first is logged in `OVERDRAW` (the device would show both, garbled).

Device facts this shim cannot know yet are module constants marked [A]; PROBE7 settles them
(screen size, font ids and metrics, the `drawString` y convention, `string_size` results). The
UI's metric table (CVDRAW) and `FONTS` here must be updated together.

Argument checks follow MicroPython (`mp_obj_get_int`): coordinates and color channels must be
ints (a float raises TypeError), so layout code that leaks a float fails on the desktop too.
"""

W = 320             # drawable width  [A: PROBE7]
H = 210             # drawable height [A: PROBE7]
FONTS = {0: (8, 14, 4), 1: (6, 9, 3)}  # setFont id -> (advance, ascent, descent) [A: PROBE7];
                    # FlowCE's fixed metrics, big and small (DESIGN 13.3 fallback)
TEXT_Y = 'top'      # drawString(s, x, y): y is the top of the text cell; or 'baseline' [A]
STRICT = True       # ints only for coordinates and colors (MicroPython behaviour)

# Names verified on the EVO (the tail of dir(ti_graphics), PROBE) and names documented for the
# CE whose presence on the EVO is assumed (the head of the listing scrolled off).
VERIFIED = ('drawLine', 'drawPolyLine', 'drawRect', 'drawString', 'fillArc', 'fillCircle',
            'fillPolygon', 'fillRect', 'getPixel', 'hsv_to_rgb', 'popImage', 'pushImage',
            'setColor', 'setFont', 'setPen', 'setPixel', 'string_size')
ASSUMED = ('cls', 'drawArc', 'drawCircle', 'drawImage', 'drawPolygon')

_DEFAULTS = (320, 210, {0: (8, 14, 4), 1: (6, 9, 3)}, 'top', True)


class _Text(object):
    """A drawn string: its cell box (x, y, w, h), and a mask over the on-screen part of the box
    (1 = erased). `live` is the number of visible pixels."""
    __slots__ = ('n', 'text', 'x', 'y', 'w', 'h', 'font', 'color',
                 'cx0', 'cy0', 'cx1', 'cy1', 'mask', 'live')

    def key(self):
        return (self.text, self.x, self.y, self.font, self.color)

    def __repr__(self):
        return '<text %r at %d,%d font %d>' % (self.text, self.x, self.y, self.font)


# ---------------------------------------------------------------- state
FB = []             # FB[y][x] = 0xRRGGBB
CALLS = []          # the draw transcript
COUNTS = {}         # name -> number of calls (queries included)
TEXTS = []          # live _Text items, in drawing order
OVERDRAW = []       # (old text, old x, old y, new text, new x, new y)
IMAGES = []         # pushImage stack
COLOR = (0, 0, 0)
FONT = 0
PEN = (0, 0)
_SEQ = [0]


def reset():
    """Fresh screen (white), empty logs, default color/font/pen and default configuration."""
    global W, H, FONTS, TEXT_Y, STRICT
    W, H, fonts, TEXT_Y, STRICT = _DEFAULTS
    FONTS = dict(fonts)
    _clear_state()


def configure(width=None, height=None, fonts=None, text_y=None, strict=None):
    """Change the [A] constants (for example after PROBE7), then clear the screen and logs."""
    global W, H, FONTS, TEXT_Y, STRICT
    if width is not None:
        W = width
    if height is not None:
        H = height
    if fonts is not None:
        FONTS = dict(fonts)
    if text_y is not None:
        if text_y not in ('top', 'baseline'):
            raise ValueError("text_y must be 'top' or 'baseline'")
        TEXT_Y = text_y
    if strict is not None:
        STRICT = strict
    _clear_state()


def _clear_state():
    global FB, COLOR, FONT, PEN
    FB = [[0xFFFFFF] * W for _ in range(H)]
    del CALLS[:]
    COUNTS.clear()
    del TEXTS[:]
    del OVERDRAW[:]
    del IMAGES[:]
    COLOR = (0, 0, 0)
    FONT = min(FONTS) if FONTS else 0
    PEN = (0, 0)
    _SEQ[0] = 0


# ---------------------------------------------------------------- helpers
def _count(name):
    COUNTS[name] = COUNTS.get(name, 0) + 1


def _int(v, fn, what):
    if type(v) is int:
        return v
    if not STRICT and isinstance(v, (int, float)):
        return int(v)
    raise TypeError('ti_graphics.%s: %s must be an int, got %r' % (fn, what, v))


def _rgb(args, fn):
    if len(args) == 1 and isinstance(args[0], (tuple, list)):
        args = tuple(args[0])
    if len(args) != 3:
        raise TypeError('ti_graphics.%s: a color is (r, g, b), got %r' % (fn, args))
    out = []
    for v in args:
        v = _int(v, fn, 'a color channel')
        if v < 0 or v > 255:
            raise ValueError('ti_graphics.%s: color channel %d out of 0..255' % (fn, v))
        out.append(v)
    return (out[0], out[1], out[2])


def _cint(c):
    return (c[0] << 16) | (c[1] << 8) | c[2]


def _points(pts, fn):
    out = []
    for p in pts:
        if not isinstance(p, (tuple, list)) or len(p) != 2:
            raise TypeError('ti_graphics.%s: points are (x, y) pairs, got %r' % (fn, p))
        out.append((_int(p[0], fn, 'x'), _int(p[1], fn, 'y')))
    return out


def _plot(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        FB[y][x] = c


def _span(y, x0, x1, c):
    """Fill pixels x0..x1 (inclusive) of row y and erase the text under them."""
    if y < 0 or y >= H:
        return
    if x0 < 0:
        x0 = 0
    if x1 >= W:
        x1 = W - 1
    if x1 < x0:
        return
    FB[y][x0:x1 + 1] = [c] * (x1 + 1 - x0)
    _erase(x0, y, x1 + 1, y + 1, None)


def _fill_rect(x0, y0, x1, y1, c):
    """Fill [x0, x1) x [y0, y1), clipped, and erase the text under it."""
    if x0 < 0:
        x0 = 0
    if y0 < 0:
        y0 = 0
    if x1 > W:
        x1 = W
    if y1 > H:
        y1 = H
    if x1 <= x0 or y1 <= y0:
        return
    row = [c] * (x1 - x0)
    for y in range(y0, y1):
        FB[y][x0:x1] = row
    _erase(x0, y0, x1, y1, None)


def _erase(x0, y0, x1, y1, by):
    """Erase text pixels in [x0, x1) x [y0, y1). `by` is the new text item doing it, if any."""
    i = 0
    while i < len(TEXTS):
        t = TEXTS[i]
        ax = max(x0, t.cx0)
        bx = min(x1, t.cx1)
        ay = max(y0, t.cy0)
        by_ = min(y1, t.cy1)
        if ax < bx and ay < by_:
            w = t.cx1 - t.cx0
            ones = b'\x01' * (bx - ax)
            lost = 0
            for y in range(ay, by_):
                a = (y - t.cy0) * w + (ax - t.cx0)
                seg = t.mask[a:a + bx - ax]
                lost += seg.count(0)
                t.mask[a:a + bx - ax] = ones
            if lost and by is not None and t.key() != by.key():
                OVERDRAW.append((t.text, t.x, t.y, by.text, by.x, by.y))
            t.live -= lost
            if t.live <= 0:
                del TEXTS[i]
                continue
        i += 1


def _text_box(s, x, y, font):
    adv, asc, desc = FONTS[font]
    top = y if TEXT_Y == 'top' else y - asc
    return x, top, adv * len(s), asc + desc


# ---------------------------------------------------------------- state calls
def setColor(*args):
    """setColor(r, g, b) or setColor((r, g, b)) [A: PROBE7 checks the signature]."""
    global COLOR
    _count('setColor')
    COLOR = _rgb(args, 'setColor')
    CALLS.append(('setColor',) + COLOR)


def setFont(font):
    global FONT
    _count('setFont')
    font = _int(font, 'setFont', 'font')
    if font not in FONTS:
        raise ValueError('ti_graphics.setFont: unknown font %d (known: %s)'
                         % (font, sorted(FONTS)))
    FONT = font
    CALLS.append(('setFont', font))


def setPen(thickness=0, style=0):
    """Recorded only; lines are drawn 1 px wide whatever the pen."""
    global PEN
    _count('setPen')
    PEN = (thickness, style)
    CALLS.append(('setPen', thickness, style))


# ---------------------------------------------------------------- queries
def string_size(s):
    """(width, height) of s in the current font [A: PROBE7 gives the real results]."""
    _count('string_size')
    if not isinstance(s, str):
        raise TypeError('ti_graphics.string_size: expects a str, got %r' % (s,))
    adv, asc, desc = FONTS[FONT]
    return (adv * len(s), asc + desc)


def getPixel(x, y):
    _count('getPixel')
    x = _int(x, 'getPixel', 'x')
    y = _int(y, 'getPixel', 'y')
    if 0 <= x < W and 0 <= y < H:
        c = FB[y][x]
        return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    return (0, 0, 0)


def hsv_to_rgb(h, s, v):
    """h in degrees, s and v in 0..1 -> [r, g, b] ints [A: CE convention]."""
    _count('hsv_to_rgb')
    h = (h % 360) / 60.0
    i = int(h)
    f = h - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i % 6]
    return [int(round(r * 255)), int(round(g * 255)), int(round(b * 255))]


# ---------------------------------------------------------------- drawing
def cls():
    """Clear the screen to white [A: CE behaviour]."""
    _count('cls')
    CALLS.append(('cls',))
    _fill_rect(0, 0, W, H, 0xFFFFFF)


def setPixel(x, y, *color):
    _count('setPixel')
    x = _int(x, 'setPixel', 'x')
    y = _int(y, 'setPixel', 'y')
    c = _rgb(color, 'setPixel') if color else COLOR
    CALLS.append(('setPixel', x, y) + c)
    _plot(x, y, _cint(c))


def _line(x1, y1, x2, y2, c):
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx + dy
    while True:
        _plot(x1, y1, c)
        if x1 == x2 and y1 == y2:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x1 += sx
        if e2 <= dx:
            err += dx
            y1 += sy


def drawLine(x1, y1, x2, y2):
    _count('drawLine')
    a = (_int(x1, 'drawLine', 'x1'), _int(y1, 'drawLine', 'y1'),
         _int(x2, 'drawLine', 'x2'), _int(y2, 'drawLine', 'y2'))
    CALLS.append(('drawLine',) + a)
    _line(a[0], a[1], a[2], a[3], _cint(COLOR))


def drawPolyLine(points):
    _count('drawPolyLine')
    pts = _points(points, 'drawPolyLine')
    CALLS.append(('drawPolyLine', tuple(pts)))
    c = _cint(COLOR)
    for i in range(len(pts) - 1):
        _line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], c)


def drawPolygon(points):
    _count('drawPolygon')
    pts = _points(points, 'drawPolygon')
    CALLS.append(('drawPolygon', tuple(pts)))
    c = _cint(COLOR)
    for i in range(len(pts)):
        a = pts[i]
        b = pts[(i + 1) % len(pts)]
        _line(a[0], a[1], b[0], b[1], c)


def fillPolygon(points):
    """Even-odd fill sampled at pixel centers."""
    _count('fillPolygon')
    pts = _points(points, 'fillPolygon')
    CALLS.append(('fillPolygon', tuple(pts)))
    if len(pts) < 3:
        return
    c = _cint(COLOR)
    ys = [p[1] for p in pts]
    n = len(pts)
    for y in range(max(min(ys), 0), min(max(ys), H - 1) + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                xs.append(ax + (yc - ay) * (bx - ax) / float(by - ay))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            a = int(-(-(xs[j] - 0.5) // 1))       # ceil
            b = int((xs[j + 1] - 0.5) // 1)       # floor
            if b >= a:
                _span(y, a, b, c)


def drawRect(x, y, w, h):
    _count('drawRect')
    x = _int(x, 'drawRect', 'x')
    y = _int(y, 'drawRect', 'y')
    w = _int(w, 'drawRect', 'w')
    h = _int(h, 'drawRect', 'h')
    CALLS.append(('drawRect', x, y, w, h))
    if w <= 0 or h <= 0:
        return
    c = _cint(COLOR)
    _line(x, y, x + w - 1, y, c)
    _line(x, y + h - 1, x + w - 1, y + h - 1, c)
    _line(x, y, x, y + h - 1, c)
    _line(x + w - 1, y, x + w - 1, y + h - 1, c)


def fillRect(x, y, w, h):
    _count('fillRect')
    x = _int(x, 'fillRect', 'x')
    y = _int(y, 'fillRect', 'y')
    w = _int(w, 'fillRect', 'w')
    h = _int(h, 'fillRect', 'h')
    CALLS.append(('fillRect', x, y, w, h))
    if w > 0 and h > 0:
        _fill_rect(x, y, x + w, y + h, _cint(COLOR))


def _isqrt(n):
    if n <= 0:
        return 0
    r = int(n ** 0.5)
    while r * r > n:
        r -= 1
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r


def drawCircle(x, y, r):
    _count('drawCircle')
    x = _int(x, 'drawCircle', 'x')
    y = _int(y, 'drawCircle', 'y')
    r = _int(r, 'drawCircle', 'r')
    CALLS.append(('drawCircle', x, y, r))
    c = _cint(COLOR)
    for d in range(-r, r + 1):
        e = _isqrt(r * r - d * d)
        _plot(x + d, y + e, c)
        _plot(x + d, y - e, c)
        _plot(x + e, y + d, c)
        _plot(x - e, y + d, c)


def fillCircle(x, y, r):
    _count('fillCircle')
    x = _int(x, 'fillCircle', 'x')
    y = _int(y, 'fillCircle', 'y')
    r = _int(r, 'fillCircle', 'r')
    CALLS.append(('fillCircle', x, y, r))
    c = _cint(COLOR)
    for d in range(-r, r + 1):
        e = _isqrt(r * r - d * d)
        _span(y + d, x - e, x + e, c)


def _arc_args(fn, x, y, w, h, start, arc):
    return (_int(x, fn, 'x'), _int(y, fn, 'y'), _int(w, fn, 'w'), _int(h, fn, 'h'),
            _int(start, fn, 'start'), _int(arc, fn, 'arc'))


def drawArc(x, y, w, h, start, arc):
    """Ellipse arc in the box (x, y, w, h), angles in degrees [A: CE units unverified]."""
    import math
    _count('drawArc')
    a = _arc_args('drawArc', x, y, w, h, start, arc)
    CALLS.append(('drawArc',) + a)
    x, y, w, h, start, arc = a
    c = _cint(COLOR)
    cx = x + (w - 1) / 2.0
    cy = y + (h - 1) / 2.0
    n = max(8, int(abs(arc) / 360.0 * 4 * (w + h)) + 1)
    for i in range(n + 1):
        t = math.radians(start + arc * i / float(n))
        _plot(int(round(cx + (w - 1) / 2.0 * math.cos(t))),
              int(round(cy - (h - 1) / 2.0 * math.sin(t))), c)


def fillArc(x, y, w, h, start, arc):
    """Filled pie slice of the ellipse in (x, y, w, h), angles in degrees [A]."""
    import math
    _count('fillArc')
    a = _arc_args('fillArc', x, y, w, h, start, arc)
    CALLS.append(('fillArc',) + a)
    x, y, w, h, start, arc = a
    if w <= 0 or h <= 0:
        return
    c = _cint(COLOR)
    cx = x + (w - 1) / 2.0
    cy = y + (h - 1) / 2.0
    rx = max(w / 2.0, 0.5)
    ry = max(h / 2.0, 0.5)
    full = abs(arc) >= 360
    lo = start if arc >= 0 else start + arc
    for py in range(y, y + h):
        run = None
        for px in range(x, x + w + 1):
            inside = False
            if px < x + w:
                dx = (px - cx) / rx
                dy = (cy - py) / ry
                if dx * dx + dy * dy <= 1.0:
                    inside = full or (math.degrees(math.atan2(dy, dx)) - lo) % 360 <= abs(arc)
            if inside and run is None:
                run = px
            elif not inside and run is not None:
                _span(py, run, px - 1, c)
                run = None


def drawString(s, x, y):
    """Draw s with the current font and color. In the framebuffer each character is a block."""
    _count('drawString')
    if not isinstance(s, str):
        raise TypeError('ti_graphics.drawString: expects a str, got %r' % (s,))
    x = _int(x, 'drawString', 'x')
    y = _int(y, 'drawString', 'y')
    CALLS.append(('drawString', s, x, y))
    if not s:
        return
    bx, by, bw, bh = _text_box(s, x, y, FONT)
    t = _Text()
    _SEQ[0] += 1
    t.n = _SEQ[0]
    t.text, t.x, t.y, t.w, t.h, t.font, t.color = s, bx, by, bw, bh, FONT, COLOR
    t.cx0, t.cy0 = max(bx, 0), max(by, 0)
    t.cx1, t.cy1 = min(bx + bw, W), min(by + bh, H)
    if t.cx1 <= t.cx0 or t.cy1 <= t.cy0:
        return                              # entirely off screen: nothing visible
    _erase(t.cx0, t.cy0, t.cx1, t.cy1, t)   # text covers what was under its cells
    t.mask = bytearray((t.cx1 - t.cx0) * (t.cy1 - t.cy0))
    t.live = len(t.mask)
    TEXTS.append(t)
    adv, asc, desc = FONTS[FONT]
    c = _cint(COLOR)
    for i in range(len(s)):
        a = max(bx + i * adv + 1, 0)
        b = min(bx + (i + 1) * adv - 1, W)
        if s[i] != ' ' and a < b:
            block = [c] * (b - a)
            for gy in range(max(by + 2, 0), min(by + asc, H)):
                FB[gy][a:b] = block


def drawImage(*args):
    """Recorded only."""
    _count('drawImage')
    CALLS.append(('drawImage',) + tuple(args))


def pushImage(x, y, w, h):
    """Save the region (pixels and the text in it) for popImage()."""
    _count('pushImage')
    x = _int(x, 'pushImage', 'x')
    y = _int(y, 'pushImage', 'y')
    w = _int(w, 'pushImage', 'w')
    h = _int(h, 'pushImage', 'h')
    CALLS.append(('pushImage', x, y, w, h))
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    rows = [FB[r][x0:x1] for r in range(y0, y1)] if x1 > x0 else []
    saved = []
    for t in TEXTS:
        if t.cx0 < x1 and x0 < t.cx1 and t.cy0 < y1 and y0 < t.cy1:
            saved.append((t, bytearray(t.mask)))
    IMAGES.append((x0, y0, x1, y1, rows, saved))


def popImage(*args):
    """Restore the last pushed region: its pixels, and the text that was visible in it."""
    _count('popImage')
    CALLS.append(('popImage',) + tuple(args))
    if not IMAGES:
        raise IndexError('ti_graphics.popImage: no pushed image')
    x0, y0, x1, y1, rows, saved = IMAGES.pop()
    if x1 <= x0 or y1 <= y0:
        return
    _erase(x0, y0, x1, y1, None)
    for r in range(y0, y1):
        FB[r][x0:x1] = rows[r - y0]
    for t, old in saved:
        live = t in TEXTS
        mask = t.mask if live else bytearray(b'\x01' * len(old))
        w = t.cx1 - t.cx0
        ax, bx = max(x0, t.cx0), min(x1, t.cx1)
        for yy in range(max(y0, t.cy0), min(y1, t.cy1)):
            a = (yy - t.cy0) * w + (ax - t.cx0)
            mask[a:a + bx - ax] = old[a:a + bx - ax]
        t.mask = mask
        t.live = mask.count(0)
        if t.live and not live:
            TEXTS.append(t)
    TEXTS.sort(key=lambda t: t.n)


# ---------------------------------------------------------------- readers (desktop only)
def texts():
    """Visible text items as (x, y, text, font, (r, g, b)), sorted by y, then x."""
    out = sorted(TEXTS, key=lambda t: (t.y, t.x, t.n))
    return [(t.x, t.y, t.text, t.font, t.color) for t in out]


def texts_in(x, y, w, h):
    """Visible text items whose cell box intersects the rectangle (x, y, w, h)."""
    return [(t.x, t.y, t.text, t.font, t.color) for t in _sorted_in(x, y, w, h)]


def _sorted_in(x, y, w, h):
    return sorted((t for t in TEXTS
                   if t.x < x + w and x < t.x + t.w and t.y < y + h and y < t.y + t.h),
                  key=lambda t: (t.y, t.x, t.n))


def find(sub):
    """Visible text items whose text contains sub."""
    return [it for it in texts() if sub in it[2]]


def screen_text(x=0, y=0, w=None, h=None):
    """The visible text as lines, top to bottom: by default the whole screen (text partly off
    screen included), otherwise the items whose cell box intersects the rectangle.

    Taking the items by their top edge, an item joins the current line when its cell box
    overlaps the line's first item vertically by at least half the smaller height (so a
    superscript stays on its base's line); otherwise it starts a new line. A line is ordered
    by x; neighbours more than 1 px apart are separated by a space."""
    if w is None:
        w = W - x
    if h is None:
        h = H - y
    if (x, y, w, h) == (0, 0, W, H):
        items = sorted(TEXTS, key=lambda t: (t.y, t.x, t.n))
    else:
        items = _sorted_in(x, y, w, h)
    lines = []
    row = []
    for t in items:
        if row:
            a = row[0]
            overlap = min(a.y + a.h, t.y + t.h) - max(a.y, t.y)
            if 2 * overlap < min(a.h, t.h):
                lines.append(_join(row))
                row = []
        row.append(t)
    if row:
        lines.append(_join(row))
    return '\n'.join(lines)


def _join(row):
    row = sorted(row, key=lambda t: (t.x, t.n))
    out = ''
    right = None
    for t in row:
        if right is not None and t.x - right > 1:
            out += ' '
        out += t.text
        right = t.x + t.w
    return out


def _fmt(v):
    if isinstance(v, str):
        return ascii(v)
    if isinstance(v, tuple):
        return '(' + ','.join(_fmt(a) for a in v) + ')'
    if isinstance(v, list):
        return '[' + ','.join(_fmt(a) for a in v) + ']'
    return str(v)


def transcript_text(calls=None):
    """The transcript, one call per line: `name arg arg ...` (strings in ascii() form)."""
    if calls is None:
        calls = CALLS
    return '\n'.join(' '.join([c[0]] + [_fmt(a) for a in c[1:]]) for c in calls)


def assumed_calls():
    """Names used so far that are not verified on the EVO (see ASSUMED)."""
    return sorted(n for n in COUNTS if n in ASSUMED)


def pixel(x, y):
    """Framebuffer read without counting a getPixel call."""
    c = FB[y][x]
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


def screenshot(path, scale=2):
    """Write the framebuffer as a PNG (8-bit RGB), each pixel scaled to scale x scale."""
    import struct
    import zlib
    raw = bytearray()
    for row in FB:
        line = bytearray(b'\x00')
        for c in row:
            line += bytes(((c >> 16) & 255, (c >> 8) & 255, c & 255)) * scale
        raw += bytes(line) * scale

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n'
                + chunk(b'IHDR', struct.pack('>IIBBBBB', W * scale, H * scale, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
                + chunk(b'IEND', b''))
    return path


reset()
