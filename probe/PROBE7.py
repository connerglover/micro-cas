# PROBE7 (cas-evo M0.3, DESIGN.md Appendix B): screen size (getPixel and
# setPixel at the edges), setColor/setPixel signatures, setFont sizes,
# string_size per font, which special glyphs drawString renders, drawing
# speed, dir(ti_graphics), whether a .mpy module imports, and an interactive
# loop: does a drawing stay visible between keys, after print, and after
# ti_system.disp_clr()?
# Run PROBE7. Text pages end with "-- pN: screenshot, key --": take a
# screenshot, then press any key. On drawing screens, answer the question
# with ENTER (yes) or CLEAR (no). If a screen is blank or only shows text,
# press CLEAR. Optional: also send PRBMPY.mpy.
# Device rules: Python 3.4 subset, ASCII only, printed lines <= 30 chars.
import gc
import sys
try:
    import ti_system as TS
except ImportError:
    TS = None
try:
    import ti_graphics as G
except ImportError:
    G = None
if TS is not None:
    _wk = TS.wait_key
else:                          # desktop dry run: never wait
    def _wk():
        return 0

W = 30                         # characters per printed line
PAGE = 8                       # lines per page; the 9th is the prompt
_n = [0, 0]                    # lines on this page, pages done


def out(s):
    # print s in lines of at most W chars; pause after PAGE lines
    s = str(s)
    while s:
        if len(s) > W:
            j = s[:W + 1].rfind(" ")
            if j < 1:
                j = W
            p = s[:j]
            s = s[j:].lstrip()
            if s:
                s = " " + s
        else:
            p = s
            s = ""
        print(p)
        _n[0] += 1
        if _n[0] >= PAGE:
            _n[1] += 1
            print("-- p%d: screenshot, key --" % _n[1])
            _wk()
            _n[0] = 0


def page():
    # end the current page now
    if _n[0]:
        _n[1] += 1
        print("-- p%d: screenshot, key --" % _n[1])
        _wk()
        _n[0] = 0


def clock():
    # (seconds function, scale): monotonic, perf_counter, ticks_ms or time
    import time
    for n in ("monotonic", "perf_counter"):
        if hasattr(time, n):
            return getattr(time, n), 1.0
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms, 0.001
    if hasattr(time, "time"):
        return time.time, 1.0
    return None, 0.0


RES = []                       # results gathered while drawings are shown
CM = [0]                       # setColor mode: 0 (r,g,b) 1 ((r,g,b)) 2 int
PM = [0]                       # setPixel mode: 0 (x,y,c) 1 setColor+(x,y)
SW = [320]                     # screen width and height (measured below)
SH = [210]
DY = [0]                       # add to a text top to get drawString's y
LH = [18]                      # text line height in the default font
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
# label, code point: pi sqrt integral Sigma infinity approx le ge ne arrow
# theta middle-dot superscript-2; "q" is "?" and "cjk" a glyph no
# calculator font has (the "missing glyph" reference)
GLYPHS = (("A", 0x41), ("pi", 0x3c0), ("rt", 0x221a), ("int", 0x222b),
          ("Sig", 0x3a3), ("inf", 0x221e), ("apx", 0x2248), ("le", 0x2264),
          ("ge", 0x2265), ("ne", 0x2260), ("to", 0x2192), ("th", 0x3b8),
          ("dot", 0xb7), ("sq2", 0xb2), ("q", 0x3f), ("cjk", 0x4e00))
CLASSES = ("own", "wide", "tofu", "q", "none", "E")


def note(s):
    RES.append(s)


def col(c):
    if CM[0] == 0:
        G.setColor(c[0], c[1], c[2])
    elif CM[0] == 1:
        G.setColor(c)
    else:
        G.setColor((c[0] << 16) | (c[1] << 8) | c[2])


def pset(x, y, c):
    if PM[0] == 0:
        G.setPixel(x, y, c)
    else:
        col(c)
        G.setPixel(x, y)


def alive(x, y):
    # True if pixel (x, y) stores colors: two writes read back differently
    try:
        pset(x, y, RED)
        a = G.getPixel(x, y)
        pset(x, y, BLUE)
        b = G.getPixel(x, y)
        return a != b
    except Exception:
        return False


def text(s, x, top):
    # draw s with its top at y = top, whatever drawString's anchor is
    G.drawString(s, x, top + DY[0])


def t_setcolor():
    r = []
    good = -1
    for m, lab in ((0, "rgb"), (1, "tup"), (2, "int")):
        CM[0] = m
        try:
            col(RED)
            G.fillRect(20, 20, 4, 4)
            a = G.getPixel(21, 21)
            col(BLUE)
            G.fillRect(20, 20, 4, 4)
            b = G.getPixel(21, 21)
            if a != b:
                r.append(lab + " ok")
                if good < 0:
                    good = m
            else:
                r.append(lab + " same")
        except Exception as e:
            r.append(lab + " E:" + type(e).__name__[:9])
    CM[0] = good if good >= 0 else 0
    note("setColor " + " ".join(r))
    col(RED)
    G.fillRect(20, 20, 4, 4)
    note("gp red " + str(G.getPixel(21, 21)))


def t_setpixel():
    r = []
    good = -1
    for m, lab in ((0, "xyc"), (1, "xy")):
        PM[0] = m
        try:
            pset(30, 30, RED)
            a = G.getPixel(30, 30)
            pset(30, 30, BLUE)
            b = G.getPixel(30, 30)
            if a != b:
                r.append(lab + " ok")
                if good < 0:
                    good = m
            else:
                r.append(lab + " same")
        except Exception as e:
            r.append(lab + " E:" + type(e).__name__[:9])
    PM[0] = good if good >= 0 else 0
    note("setPixel " + " ".join(r))


def t_extent():
    w = 0
    for x in range(400):
        if not alive(x, 50):
            break
        w = x + 1
    h = 0
    for y in range(300):
        if not alive(50, y):
            break
        h = y + 1
    note("scr %dx%d" % (w, h))
    note("neg x %d y %d corner %d" % (alive(-1, 50), alive(50, -1),
                                      alive(w - 1, h - 1)))
    if w > 50 and h > 50:
        SW[0] = w
        SH[0] = h


def ink(s, x, y, bw, bh):
    # draw s at (x, y) on white; scan the box around it with getPixel.
    # Returns (ink pixels, pattern signature, x0, x1, y0, y1) relative to
    # (x, y).
    col(WHITE)
    G.fillRect(x - 4, y - bh - 4, bw + 8, 2 * bh + 8)
    bg = G.getPixel(x - 3, y)
    col(BLACK)
    G.drawString(s, x, y)
    n = 0
    sig = 0
    x0 = y0 = 999
    x1 = y1 = -999
    for j in range(y - bh - 2, y + bh + 3):
        for i in range(x - 2, x + bw + 3):
            if G.getPixel(i, j) != bg:
                n += 1
                sig = (sig * 131 + (i - x) * 97 + (j - y)) % 1000003
                if i < x0:
                    x0 = i
                if i > x1:
                    x1 = i
                if j < y0:
                    y0 = j
                if j > y1:
                    y1 = j
    return (n, sig, x0 - x, x1 - x, y0 - y, y1 - y)


def sizes():
    # (width, height) of "M" in the current font, or (12, 16)
    try:
        a = G.string_size("M")
        return int(a[0]), int(a[1])
    except Exception:
        return 12, 16


def t_glyphs(f):
    # classify each glyph in font f: own (a distinct drawing), wide (ink
    # over 1.5 x the width of "M": probably its UTF-8 bytes drawn as several
    # glyphs), tofu (same as the missing-glyph reference), q (drawn as
    # "?"), none (no ink), E (drawString raised)
    w, h = sizes()
    bw = 2 * w + 4
    if bw > 40:
        bw = 40
    bh = h + 2
    if bh > 30:
        bh = 30
    x = 40
    y = 60
    m = ink("M", x, y, bw, bh)
    note("f%s Mbox x%d..%d y%d..%d" % (f, m[2], m[3], m[4], m[5]))
    wmax = (m[3] - m[2] + 1) * 3 // 2 + 1
    rq = ink("?", x, y, bw, bh)
    try:
        ru = ink(chr(0x4e00), x, y, bw, bh)
    except Exception:
        ru = (-1, -1)
    got = {}
    for c in CLASSES:
        got[c] = []
    for lab, cp in GLYPHS:
        try:
            r = ink(chr(cp), x, y, bw, bh)
        except Exception:
            got["E"].append(lab)
            continue
        if r[0] == 0:
            got["none"].append(lab)
        elif lab != "cjk" and r[0] == ru[0] and r[1] == ru[1]:
            got["tofu"].append(lab)
        elif r[3] - r[2] + 1 > wmax:
            got["wide"].append(lab)
        elif lab != "q" and r[0] == rq[0] and r[1] == rq[1]:
            got["q"].append(lab)
        else:
            got["own"].append(lab)
    for c in CLASSES:
        if got[c]:
            note("f%s %s: %s" % (f, c, " ".join(got[c])))
    return m


def t_fonts():
    ok = []
    bad = []
    try:
        d = G.string_size("M")
        note("fdef M%s" % (str(d),))
    except Exception as e:
        d = None
        note("string_size E:" + type(e).__name__)
    for f in range(6):
        try:
            G.setFont(f)
            ok.append(f)
        except Exception as e:
            bad.append("%d:%s" % (f, type(e).__name__[:8]))
    note("setFont ok " + " ".join([str(f) for f in ok]))
    if bad:
        note("setFont bad " + " ".join(bad))
    deff = -1
    for f in ok:
        G.setFont(f)
        try:
            a = G.string_size("M")
            b = G.string_size("MMMMMMMMMM")
            note("f%d M%s 10M%s" % (f, str(a), str(b)))
            if d is not None and a == d and deff < 0:
                deff = f
        except Exception as e:
            note("f%d size E:%s" % (f, type(e).__name__))
    note("default font %d" % deff)
    return ok, deff


def setdef(deff):
    if deff >= 0:
        G.setFont(deff)


def sheet(fonts, deff):
    # every special glyph in each font, for a screenshot
    col(WHITE)
    G.fillRect(0, 0, SW[0], SH[0])
    col(BLACK)
    top = 4
    for f in fonts[:4]:
        G.setFont(f)
        w, h = sizes()
        G.drawString("f%d" % f, 2, top + DY[0])
        x = 34
        for lab, cp in GLYPHS[1:14]:
            try:
                G.drawString(chr(cp), x, top + DY[0])
            except Exception:
                pass
            x += w + 8
        top += h + 8
    setdef(deff)
    text("Glyph sheet: take a", 4, SH[0] - 2 * LH[0] - 4)
    text("screenshot, then a key.", 4, SH[0] - LH[0] - 4)
    _wk()


def t_speed():
    clk, sc = clock()
    if clk is None:
        note("speed: no clock")
        return
    t0 = clk()
    for i in range(5):
        col(WHITE)
        G.fillRect(0, 0, SW[0], SH[0])
    t1 = clk()
    note("fill %.1f ms" % ((t1 - t0) * sc * 200.0))
    col(BLACK)
    t0 = clk()
    for i in range(50):
        G.drawString("x^2+3*x-1", 10, 100)
    t1 = clk()
    note("str %.2f ms" % ((t1 - t0) * sc * 20.0))
    t0 = clk()
    for i in range(300):
        pset(i, 120, BLACK)
    t1 = clk()
    note("setpx %d us" % int((t1 - t0) * sc * 1e6 / 300))
    t0 = clk()
    for i in range(300):
        G.getPixel(i, 120)
    t1 = clk()
    note("getpx %d us" % int((t1 - t0) * sc * 1e6 / 300))
    t0 = clk()
    for k in range(3):
        frame(0)
    t1 = clk()
    note("frame %.1f ms" % ((t1 - t0) * sc * 1000.0 / 3))


def frame(k):
    # a full redraw: background, a 3 px border, a title, the step box
    w = SW[0]
    h = SH[0]
    col(WHITE)
    G.fillRect(0, 0, w, h)
    col(BLACK)
    G.fillRect(0, 0, w, 3)
    G.fillRect(0, h - 3, w, 3)
    G.fillRect(0, 0, 3, h)
    G.fillRect(w - 3, 0, 3, h)
    text("PROBE7 drawing test", 10, 8)
    G.fillRect(60, 40, 200, 2)
    G.fillRect(60, 40 + LH[0] + 10, 200, 2)
    region(k)


def region(k):
    # redraw only the step box
    col(WHITE)
    G.fillRect(60, 43, 200, LH[0] + 6)
    col(BLACK)
    text("step %d of 5" % k, 70, 45)


def yn(k):
    if k == 105:
        return "y"
    if k == 45:
        return "n"
    return "k%s" % (k,)


def ask(a, b):
    # draw a two-line question at the bottom; return the answer key
    col(WHITE)
    G.fillRect(6, SH[0] - 2 * LH[0] - 10, SW[0] - 12, 2 * LH[0] + 6)
    col(BLACK)
    text(a, 10, SH[0] - 2 * LH[0] - 8)
    text(b, 10, SH[0] - LH[0] - 6)
    return yn(_wk())


def border_ok(ref):
    try:
        return "kept" if G.getPixel(1, SH[0] // 2) == ref else "lost"
    except Exception as e:
        return "E:" + type(e).__name__[:8]


def t_loop():
    clk, sc = clock()
    t0 = clk() if clk else 0
    frame(1)
    t1 = clk() if clk else 0
    note("redraw full %.1f ms" % ((t1 - t0) * sc * 1000.0))
    ref = G.getPixel(1, SH[0] // 2)
    ans = [ask("Step 1/5: box with", "step 1? ENTER=y CLEAR=n")]
    px = [border_ok(ref)]
    tr = 0.0
    for k in range(2, 6):
        t0 = clk() if clk else 0
        region(k)
        t1 = clk() if clk else 0
        tr += (t1 - t0) * sc
        ans.append(ask("Step %d/5: box shows" % k,
                       "step %d? ENTER=y CLEAR=n" % k))
        px.append(border_ok(ref))
    note("redraw box %.1f ms" % (tr * 250.0))
    note("steps " + " ".join(ans))
    note("px steps " + " ".join(px))
    # print test
    ask("Key: print a text line.", "Then: box still there?")
    print("PROBE7 print test.")
    print("Is the box still on the")
    print("screen? ENTER=yes CLEAR=no")
    a = yn(_wk())
    note("after print: %s px %s" % (a, border_ok(ref)))
    # disp_clr test
    frame(6)
    ask("Key: run disp_clr. Then", "box still? ENTER=y CLEAR=n")
    try:
        TS.disp_clr()
        e = "ok"
    except Exception as x:
        e = "E:" + type(x).__name__
    a = yn(_wk())
    note("after disp_clr %s: %s px %s" % (e, a, border_ok(ref)))


def step(label, f):
    try:
        f()
    except Exception as e:
        note(label + " E:" + type(e).__name__)


out("PROBE7 v1")
impl = getattr(sys, "implementation", None)
out("impl " + str(impl))
out("mpy ver " + str(getattr(impl, "_mpy", "-")))
try:
    import PRBMPY
    out("mpy import ok %s %d" % (PRBMPY.K, PRBMPY.f(20)))
except BaseException as e:     # ImportError: no file; ValueError: version
    out("mpy import E:%s %s" % (type(e).__name__, str(e)[:30]))
for mname in ("ti_graphics", "ti_draw"):
    try:
        mod = __import__(mname)
        names = []
        for nm in dir(mod):
            if not nm.startswith("_"):
                names.append(nm)
        names.sort()
        out("%s %d names:" % (mname, len(names)))
        out(" ".join(names))
    except BaseException as e:
        out("%s E:%s" % (mname, type(e).__name__))
    mod = None
gc.collect()
if G is None or TS is None:
    out("no ti_graphics: stop")
else:
    page()
    out("Drawing tests next. The")
    out("screen asks questions:")
    out("ENTER = yes, CLEAR = no.")
    out("If a screen is blank or")
    out("shows only this text,")
    out("press CLEAR. Some steps")
    out("take a few seconds.")
    page()
    step("setColor", t_setcolor)
    step("setPixel", t_setpixel)
    step("extent", t_extent)
    fonts = []
    deff = -1
    try:
        fonts, deff = t_fonts()
    except Exception as e:
        note("fonts E:" + type(e).__name__)
    for f in fonts[:3]:
        try:
            G.setFont(f)
            m = t_glyphs(f)
            if f == deff or deff < 0:
                if m[4] < 0:
                    DY[0] = -m[4]
                LH[0] = m[5] - m[4] + 5
        except Exception as e:
            note("glyphs f%d E:%s" % (f, type(e).__name__))
    if not fonts:
        try:
            m = t_glyphs("?")
            if m[4] < 0:
                DY[0] = -m[4]
            LH[0] = m[5] - m[4] + 5
        except Exception as e:
            note("glyphs E:" + type(e).__name__)
    try:
        setdef(deff)
    except Exception:
        pass
    if LH[0] < 8 or LH[0] > 40:
        LH[0] = 18
    note("text dy %d lh %d" % (DY[0], LH[0]))
    step("speed", t_speed)
    step("sheet", lambda: sheet(fonts, deff))
    step("loop", t_loop)
    try:
        TS.disp_clr()
    except Exception:
        pass
    _n[0] = 0
    for s in RES:
        out(s)
print("== PROBE7 end, p%d ==" % (_n[1] + 1))
