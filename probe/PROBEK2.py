# PROBEK2 (cas-evo M0.3, DESIGN.md 16.4): the code of every key (extends
# PROBEK). It names one key at a time: press that key once. If the code is
# not the TI-84 Plus CE code, it asks for the same key again (a second press
# that agrees confirms a new code; a slip is corrected).
# Then: get_key() with no key pressed, RIGHT held down, keys the list does
# not name, and last the ON key (it may stop the probe: that is an answer).
# Text pages end with "-- pN: screenshot, key --": take a screenshot, then
# press any key.
# Device rules: Python 3.4 subset, ASCII only, printed lines <= 30 chars.
try:
    import ti_system as TS
except ImportError:
    TS = None
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


# (name on a TI-84 Plus CE key, standard getKey code), in keyboard order.
# 2nd comes just before sin and alpha just before math, so those presses
# also show that modifiers arrive as their own codes.
KEYS = (("y= (F1)", 11), ("window (F2)", 12), ("zoom (F3)", 13),
        ("trace (F4)", 14), ("graph (F5)", 15),
        ("mode", 22), ("del", 23),
        ("up", 25), ("left", 24), ("right", 26), ("down", 34),
        ("X,T,theta,n", 32), ("stat", 33),
        ("alpha", 31), ("math", 41), ("apps", 42), ("prgm", 43),
        ("vars", 44), ("clear", 45),
        ("x^-1", 51), ("2nd", 21), ("sin", 52), ("cos", 53), ("tan", 54),
        ("^", 55),
        ("x^2", 61), (",", 62), ("(", 63), (")", 64), ("divide", 65),
        ("log", 71), ("7", 72), ("8", 73), ("9", 74), ("times", 75),
        ("ln", 81), ("4", 82), ("5", 83), ("6", 84), ("minus", 85),
        ("sto->", 91), ("1", 92), ("2", 93), ("3", 94), ("plus", 95),
        ("0", 102), (".", 103), ("(-)", 104), ("enter", 105))


def capture():
    # returns [(name, expected, code, flag)]; flag "" ok, "new" a confirmed
    # other code, "?" three presses that never agreed
    res = []
    for name, exp in KEYS:
        print("press: " + name)
        c = _wk()
        flag = ""
        tries = 1
        while c != exp:
            if tries >= 3:
                flag = "?"
                break
            print(" got %s, not %d. Again:" % (c, exp))
            c2 = _wk()
            tries += 1
            if c2 == c:
                flag = "new"
                break
            c = c2
        res.append((name, exp, c, flag))
    return res


def idle(fn, secs):
    # call fn() for secs seconds with no key pressed: distinct values, calls
    clk, sc = clock()
    vals = []
    i = 0
    t0 = clk() if clk else 0
    while True:
        i += 1
        v = fn()
        if v not in vals and len(vals) < 5:
            vals.append(v)
        if not i & 63:
            if clk:
                if (clk() - t0) * sc >= secs:
                    break
            elif i >= 20000:
                break
    return vals, i


def drain():
    # read keys until none came for 0.5 s (at most 5 s), so that a held
    # key cannot auto-repeat into the next key wait
    clk, sc = clock()
    if clk is None:
        j = 0
        while j < 20000:
            j += 1
            TS.get_key()
        return
    t1 = last = clk()
    while True:
        now = clk()
        if TS.get_key():
            last = now
        if (now - last) * sc > 0.5 or (now - t1) * sc > 5:
            return


def hold(secs):
    # get_key() codes while a key is held for secs seconds
    clk, sc = clock()
    seen = []
    counts = []
    i = 0
    t0 = clk() if clk else 0
    while True:
        i += 1
        k = TS.get_key()
        if k:
            if k in seen:
                counts[seen.index(k)] += 1
            elif len(seen) < 4:
                seen.append(k)
                counts.append(1)
        if not i & 63:
            if clk:
                if (clk() - t0) * sc >= secs:
                    break
            elif i >= 40000:
                break
    r = []
    for j in range(len(seen)):
        r.append("%d x%d" % (seen[j], counts[j]))
    return " ".join(r) if r else "none"


out("PROBEK2 v1: key codes")
if TS is None:
    out("no ti_system: stop")
else:
    out("Each line names a key:")
    out("press that key once. If")
    out("it says Again, press the")
    out("same key once more. Names")
    out("are TI-84 Plus CE names;")
    out("press the key in the same")
    out("place if yours differs.")
    page()
    res = capture()
    # get_key() and getKey() with no key pressed
    print("Hands off the keys for")
    print("2 s. Press ENTER to start.")
    _wk()
    other = []
    for fname in ("get_key", "getKey"):
        if hasattr(TS, fname):
            vals, i = idle(getattr(TS, fname), 1)
            other.append("idle %s %s n%d" % (
                fname, " ".join([str(v) for v in vals]), i))
        else:
            other.append("idle %s missing" % fname)
    # auto-repeat while a key is held
    print("Press ENTER, then hold")
    print("RIGHT down for 3 seconds.")
    _wk()
    other.append("hold right: " + hold(3))
    print("Release RIGHT now.")
    drain()
    # keys the list did not name (new EVO keys?)
    print("Now press each key that")
    print("was NOT asked for (new")
    print("keys), left to right, top")
    print("to bottom. Write their")
    print("names down. Then press")
    print("CLEAR 3 times to finish.")
    extra = []
    z = 0
    while z < 3 and len(extra) < 40:
        k = _wk()
        print(" code %s" % (k,))
        if k == 45:
            z += 1
        else:
            z = 0
            extra.append(k)
    _n[0] = 1                           # the last " code" line
    ok = 0
    for r in res:
        if r[3] == "" and r[2] == r[1]:
            ok += 1
    out("match %d of %d" % (ok, len(res)))
    for r in res:
        if r[2] != r[1]:
            out("%s %s exp %d %s" % (r[0], r[2], r[1], r[3]))
    codes = []
    for r in res:
        codes.append(str(r[2]))
    out("codes " + " ".join(codes))
    for s in other:
        out(s)
    if extra:
        out("extra " + " ".join([str(k) for k in extra]))
    else:
        out("extra none")
    page()
    print("Last: press ON once. It")
    print("may stop the probe; that")
    print("is an answer too.")
    try:
        k = _wk()
        print("on code %s" % (k,))
    except BaseException as e:
        print("on E:" + type(e).__name__)
    _n[0] = 4
print("== PROBEK2 end, p%d ==" % (_n[1] + 1))
