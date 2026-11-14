#@L 2
# The steps screen (docs/notes/STEPS.md): a modal page over R.STEPS, like the menus. It lays
# out only the steps on the screen, engine-free (draw.mlayout), and keeps no layout of its own.
import gc

import ti_system as TS
import ui as U
import draw as D

TOP = 23            # first content row; the page ends above the footer rule (row 188)
BOT = 187
ROOM = 12288        # free bytes wanted before the first layout
SPARE = 80          # names warm() may intern: 74 reach the line after the lightest session


def warm(need, evict, free):                                    #@L 2
    """Before the first steps job of a session; run.go has emptied the heap of every lazy pack
    (docs/notes/STEPS.md). MicroPython keeps interned names in pools that double: the one for
    names 1,261 to 2,540 is a single block of 5,136 bytes, allocated for good at the moment
    name 1,261 is interned, wherever a run that long is free. A pack interns its names at its
    first import, and a session reaches that line after the engine, the menus and a few
    families; the steps packs bring it nearer. Met while a menu or this screen is imported
    beside the view pack, on a split heap, the block is not to be had (measured: the import
    fails with 47 KB free), and met inside a command it fails that command at an arbitrary
    point. So the line is crossed here, where the block lands low: this pack is imported, the
    menus are, and then spare names are looked up (a name looked up is a name interned) until
    the free heap drops by the block; at most SPARE of them, all of them when the session
    crossed the line earlier. need, evict: run's; free: run.MEMFREE (None on the desktop)
    (run passes them: the UI may not have bound the engine yet)."""
    need('menu')                                                #@calls 3
    evict('menu')                                               #@calls 4
    if free is not None:
        gc.collect()                    # no collection inside the loop hides the drop
        for j in range(SPARE):
            f = free()                                          #@calls 7
            getattr((), '_%d' % j, None)
            if f - free() > 4096:                               #@calls 7
                break


def room():                                                     #@L 3
    """Room for a page of layouts, made as the loader makes it: the least recently used
    family gives way, one at a time, never this screen's own (docs/notes/STEPS.md)."""
    R = U.R
    while R.MEMFREE is not None and R.MEMFREE() < ROOM:
        gc.collect()
        v = R.victim(R.USE['stepv'])
        if R.MEMFREE() >= ROOM or v is None:
            break
        R.evict(v)


def view():                                                     #@L 2
    """Show U.R.STEPS[1:] until CLEAR or ENTER. Up/down move one step, left/right one page.
    A line too long or too wide for the 2D layout is drawn as wrapped text. A key that moves
    nothing repaints nothing."""
    S = U.R.STEPS
    n = len(S) - 1
    room()
    top = end = 0
    was = -1
    C = D.COLORS
    clip = (0, TOP, 319, BOT)
    while True:
        if top != was:
            D.rect(0, 0, 320, 210, C['BG'])
            D.line(0, 19, 319, 19, C['LINE'])
            D.line(0, 188, 319, 188)
            y = TOP
            i = top
            while i < n:
                title, s = S[i + 1]
                # A line too wide for one row is cut at its '=' (the left side, then = right),
                # and a side still too wide at the + or - nearest its middle. parts: text, mark
                # (0 the first row, 1 a row that starts with a drawn =, 2 a continuation).
                parts = [s, 0] if s else []
                blocks = []
                h = 0
                while parts:
                    p = parts.pop(0)
                    mk = parts.pop(0)
                    ind = 15 if blocks else 0
                    lay = None
                    try:
                        lay = D.mlayout(p, 1)       # cached: None past its caps
                    except Exception:               # a layout bug: drawn as text
                        pass
                    if lay is not None and lay[1] <= 290 - ind:
                        blocks.append((mk, lay, (), lay[2] + lay[3] + 4))
                    else:
                        d = 0
                        cut = -1
                        for j in range(1, len(p)):
                            ch = p[j]
                            if ch == '(':
                                d += 1
                            elif ch == ')':
                                d -= 1
                            elif d:
                                pass
                            elif ch == '=' and p is s:
                                cut = j
                                break
                            elif (ch == '+' or ch == '-') and p[j - 1] not in '(*/^,=E' and (
                                    cut < 0 or abs(2 * j - len(p)) < abs(2 * cut - len(p))):
                                cut = j
                        if cut > 0 and p[cut] == '=':
                            parts = [p[:cut], 0, p[cut + 1:], 1]
                            continue
                        if cut > 0:
                            parts[0:0] = [p[:cut], mk, p[cut:], 2]
                            continue
                        rows = D.wrap(p, 29 - ind // 10)[:3]
                        blocks.append((mk, None, rows, 17 * len(rows) + 2))
                    h += blocks[-1][3]
                if i > top and y + 17 + h > BOT:
                    break
                D.text(str(i + 1) + ' ' + title[:28], 5, y, C['ACC'] if i == n - 1 else C['SUB'])
                y += 17
                for mk, lay, rows, bh in blocks:
                    D.color(C['INK'])
                    if mk == 1:
                        D.text('=', 20, y + (lay[2] - 11 if lay is not None else 0), None, clip)
                    if lay is not None:
                        D.mrender(lay[0], 35 if mk else 20, y, clip, 0, 319, C['INK'], False)
                    for j in range(len(rows)):
                        D.text(rows[j], 35 if mk else 20, y + 17 * j, None, clip)
                    y += bh
                y += 3
                i += 1
            end = i
            D.text('Steps ' + str(top + 1) + '-' + str(end) + ' of ' + str(n), 5, 2, C['INK'])
            D.text('Up/down: step   CLEAR: back', 5, 192, C['ACC'])
        was = top
        k = TS.wait_key()
        if k == 45 or k == 105 or k == 11:
            D.clear_cache()
            room()                      # and for the page that is drawn next
            return
        if k == 34 and end < n:
            top += 1
        elif k == 25 and top:
            top -= 1
        elif k == 26 and end < n:
            top = end
        elif k == 24:
            top = max(0, top - 3)
