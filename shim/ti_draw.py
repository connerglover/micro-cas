"""Desktop stand-in for the TI-84 EVO `ti_draw` module (docs/notes/FASTBOOT.md).

Desktop only (never ships; its frames are not counted by the depth checker). The semantics are
the ones CalcPlex documents from the EVO, and the checks are strict so that a call the device
would reject fails on the desktop too:

* The screen is 320 x 210 pixels, origin top-left, y down; `get_screen_dim()` is [319, 209].
* `set_color(r, g, b)`: three ints in 0..255. Slow on the device, so every call is counted
  (`COUNTS['set_color']`); the UI caches the current color.
* `fill_rect(x, y, w, h)` fills the *interior* only: columns x+1 .. x+w-1, rows y+1 .. y+h-1.
  An exact area x..x+w-1 x y..y+h-1 is `fill_rect(x-1, y-1, w+1, h+1)`. w or h below 2 raises
  `tidrawException`. `fill_rect(-1, -1, 321, 211)` fills the whole screen.
* `draw_text(x, y, s)`: one fixed-width font, 10 px per character; the ink sits *above* y, in
  rows y-17 .. y-3. The text cell of s is columns x .. x+10*len(s)-1, rows y-17 .. y-3. The
  background is not erased.
* `draw_line(x1, y1, x2, y2)` in the current color; pixels off screen are dropped silently.
* `clear()` paints the screen white (slow on the device: the UI paints with fill_rect).

Arguments follow MicroPython (`mp_obj_get_int`): coordinates and channels must be ints.

Besides the framebuffer (`FB`, `pixel`, `screenshot`), the shim keeps:

1. **CALLS**, the draw transcript (`transcript_text()` prints it), and **COUNTS** per name.
2. **OFFSCREEN**: every call that draws (or would draw) outside 0..319 x 0..209: a fill_rect
   interior, a text cell or a line endpoint off screen. The UI must keep this empty.
3. **Screen text.** Each `draw_text` becomes an item owning its cell. A fill_rect erases the
   cell pixels it covers; an item disappears once all its pixels are erased (a partial fill,
   such as a caret, leaves it). Lines never erase text. Text drawn over a *different* live
   text item is logged in **OVERDRAW** and both stay (the device shows both, garbled); the
   same text redrawn at the same place replaces the old item. `texts()`, `screen_text()` and
   `texts_in()` read what is visible.
"""

W = 320
H = 210
ADV = 10            # pixels per character
ABOVE = 17          # draw_text(x, y, s): the first ink row is y - ABOVE
CELL = 15           # ink rows per text line: y-17 .. y-3

# Calls CalcPlex documents from the EVO; the UI uses only these (and not clear()).
VERIFIED = ('set_color', 'fill_rect', 'draw_text', 'draw_line', 'get_screen_dim', 'clear')


class tidrawException(Exception):
    """Raised by the device for an invalid argument (fill_rect with w or h below 2)."""


class _Text(object):
    __slots__ = ('n', 'text', 'x', 'y', 'w', 'h', 'color',
                 'cx0', 'cy0', 'cx1', 'cy1', 'mask', 'live')

    def key(self):
        return (self.text, self.x, self.y)

    def __repr__(self):
        return '<text %r at %d,%d>' % (self.text, self.x, self.y)


# ---------------------------------------------------------------- state
FB = []             # FB[y][x] = 0xRRGGBB
CALLS = []          # the draw transcript
COUNTS = {}         # name -> number of calls
TEXTS = []          # live _Text items in drawing order
OVERDRAW = []       # (old text, old x, old top, new text, new x, new top)
OFFSCREEN = []      # calls (as in CALLS) that reach outside the screen
COLOR = (0, 0, 0)
_SEQ = [0]


def reset():
    """A fresh white screen, black ink and empty logs."""
    global FB, COLOR
    FB = [[0xFFFFFF] * W for _ in range(H)]
    del CALLS[:]
    COUNTS.clear()
    del TEXTS[:]
    del OVERDRAW[:]
    del OFFSCREEN[:]
    COLOR = (0, 0, 0)
    _SEQ[0] = 0


# ---------------------------------------------------------------- helpers
def _count(name):
    COUNTS[name] = COUNTS.get(name, 0) + 1


def _int(v, fn, what):
    if type(v) is int:
        return v
    raise TypeError('ti_draw.%s: %s must be an int, got %r' % (fn, what, v))


def _cint(c):
    return (c[0] << 16) | (c[1] << 8) | c[2]


def _on(x, y):
    return 0 <= x < W and 0 <= y < H


def _plot(x, y, c):
    if _on(x, y):
        FB[y][x] = c


def _fill(x0, y0, x1, y1, c):
    """Fill [x0, x1) x [y0, y1), clipped, and erase the text under it."""
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 <= x0 or y1 <= y0:
        return
    row = [c] * (x1 - x0)
    for y in range(y0, y1):
        FB[y][x0:x1] = row
    i = 0
    while i < len(TEXTS):
        t = TEXTS[i]
        ax, bx = max(x0, t.cx0), min(x1, t.cx1)
        ay, by = max(y0, t.cy0), min(y1, t.cy1)
        if ax < bx and ay < by:
            w = t.cx1 - t.cx0
            ones = b'\x01' * (bx - ax)
            lost = 0
            for y in range(ay, by):
                a = (y - t.cy0) * w + (ax - t.cx0)
                lost += t.mask[a:a + bx - ax].count(0)
                t.mask[a:a + bx - ax] = ones
            t.live -= lost
            if t.live <= 0:
                del TEXTS[i]
                continue
        i += 1


# ---------------------------------------------------------------- the device calls
def set_color(*args):
    """set_color(r, g, b), each an int in 0..255."""
    global COLOR
    _count('set_color')
    if len(args) != 3:
        raise TypeError('ti_draw.set_color takes 3 positional arguments but %d were given'
                        % len(args))
    out = []
    for v in args:
        v = _int(v, 'set_color', 'a color channel')
        if v < 0 or v > 255:
            raise ValueError('ti_draw.set_color: color channel %d out of 0..255' % v)
        out.append(v)
    COLOR = (out[0], out[1], out[2])
    CALLS.append(('set_color',) + COLOR)


def fill_rect(x, y, w, h):
    """Fill the interior x+1..x+w-1 x y+1..y+h-1; w or h below 2 raises tidrawException."""
    _count('fill_rect')
    x = _int(x, 'fill_rect', 'x')
    y = _int(y, 'fill_rect', 'y')
    w = _int(w, 'fill_rect', 'w')
    h = _int(h, 'fill_rect', 'h')
    if w < 2 or h < 2:
        raise tidrawException('fill_rect: width and height must be at least 2, got %d x %d'
                              % (w, h))
    call = ('fill_rect', x, y, w, h)
    CALLS.append(call)
    if x + 1 < 0 or y + 1 < 0 or x + w - 1 > W - 1 or y + h - 1 > H - 1:
        OFFSCREEN.append(call)
    _fill(x + 1, y + 1, x + w, y + h, _cint(COLOR))


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


def draw_line(x1, y1, x2, y2):
    _count('draw_line')
    a = (_int(x1, 'draw_line', 'x1'), _int(y1, 'draw_line', 'y1'),
         _int(x2, 'draw_line', 'x2'), _int(y2, 'draw_line', 'y2'))
    call = ('draw_line',) + a
    CALLS.append(call)
    if not (_on(a[0], a[1]) and _on(a[2], a[3])):
        OFFSCREEN.append(call)
    _line(a[0], a[1], a[2], a[3], _cint(COLOR))


def draw_text(x, y, s):
    """Draw s with its ink in rows y-17 .. y-3, 10 px per character, background untouched."""
    _count('draw_text')
    x = _int(x, 'draw_text', 'x')
    y = _int(y, 'draw_text', 'y')
    if not isinstance(s, str):
        raise TypeError('ti_draw.draw_text: expects a str, got %r' % (s,))
    call = ('draw_text', x, y, s)
    CALLS.append(call)
    if not s:
        return
    top = y - ABOVE
    w = ADV * len(s)
    if x < 0 or top < 0 or x + w - 1 > W - 1 or top + CELL - 1 > H - 1:
        OFFSCREEN.append(call)
    t = _Text()
    _SEQ[0] += 1
    t.n = _SEQ[0]
    t.text, t.x, t.y, t.w, t.h, t.color = s, x, top, w, CELL, COLOR
    t.cx0, t.cy0 = max(x, 0), max(top, 0)
    t.cx1, t.cy1 = min(x + w, W), min(top + CELL, H)
    if t.cx1 <= t.cx0 or t.cy1 <= t.cy0:
        return                              # entirely off screen: nothing visible
    i = 0
    while i < len(TEXTS):
        o = TEXTS[i]
        if o.cx0 < t.cx1 and t.cx0 < o.cx1 and o.cy0 < t.cy1 and t.cy0 < o.cy1:
            if o.key() == t.key():          # the same text again: the new ink covers it
                del TEXTS[i]
                continue
            OVERDRAW.append((o.text, o.x, o.y, s, x, top))
        i += 1
    t.mask = bytearray((t.cx1 - t.cx0) * (t.cy1 - t.cy0))
    t.live = len(t.mask)
    TEXTS.append(t)
    c = _cint(COLOR)
    for i in range(len(s)):
        a = max(x + i * ADV + 1, 0)
        b = min(x + (i + 1) * ADV - 1, W)
        if s[i] != ' ' and a < b:
            block = [c] * (b - a)
            for gy in range(max(top + 2, 0), min(top + CELL - 3, H)):
                FB[gy][a:b] = block


def get_screen_dim():
    _count('get_screen_dim')
    return [W - 1, H - 1]


def clear():
    """Paint the screen white (slow on the device)."""
    _count('clear')
    CALLS.append(('clear',))
    _fill(0, 0, W, H, 0xFFFFFF)


# ---------------------------------------------------------------- readers (desktop only)
def texts():
    """Visible text items as (x, top, text, (r, g, b)), sorted by top, then x."""
    return [(t.x, t.y, t.text, t.color) for t in sorted(TEXTS, key=lambda t: (t.y, t.x, t.n))]


def texts_in(x, y, w, h):
    """Visible text items whose cell intersects the rectangle (x, y, w, h)."""
    return [(t.x, t.y, t.text, t.color) for t in _sorted_in(x, y, w, h)]


def _sorted_in(x, y, w, h):
    return sorted((t for t in TEXTS
                   if t.x < x + w and x < t.x + t.w and t.y < y + h and y < t.y + t.h),
                  key=lambda t: (t.y, t.x, t.n))


def find(sub):
    """Visible text items whose text contains sub."""
    return [it for it in texts() if sub in it[2]]


def screen_text(x=0, y=0, w=None, h=None):
    """The visible text as lines, top to bottom (by default the whole screen).

    An item joins the current line when its cell overlaps the line's first item vertically by
    at least half a cell; a line is ordered by x, and neighbours more than 1 px apart are
    separated by a space."""
    if w is None:
        w = W - x
    if h is None:
        h = H - y
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
    out = ''
    right = None
    for t in sorted(row, key=lambda t: (t.x, t.n)):
        if right is not None and t.x - right > 1:
            out += ' '
        out += t.text
        right = t.x + t.w
    return out


def _fmt(v):
    if isinstance(v, str):
        return ascii(v)
    return str(v)


def transcript_text(calls=None):
    """The transcript, one call per line: `name arg arg ...` (strings in ascii() form)."""
    if calls is None:
        calls = CALLS
    return '\n'.join(' '.join([c[0]] + [_fmt(a) for a in c[1:]]) for c in calls)


def pixel(x, y):
    """Framebuffer read (r, g, b)."""
    c = FB[y][x]
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


def screenshot(path, scale=2):
    """Write the framebuffer as a PNG (8-bit RGB); text is drawn as one block per character."""
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
