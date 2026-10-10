# PROBE6 (cas-evo M0.3, DESIGN.md Appendix B): the generator trampoline (the
# T1.6 gate), throw, StopIteration.value, bytes per suspended generator,
# list/array facts, time names, math edge cases, native costs at depth
# (exceptions, gc, the compiler, sort) and escape()/get_key() while busy.
# Run PROBE6. Each page ends with "-- pN: screenshot, key --": take a
# screenshot, then press any key. At POLL, tap CLEAR until the countdown
# ends.
# The LAST section (sort at depth 9) is RISKY: back up the calculator first.
# imp6 needs PRBL300.py (made in M0.5); without it, it prints E:ImportError.
# Device rules: Python 3.4 subset, ASCII only, printed lines <= 30 chars.
import gc
import math
try:
    from ti_system import wait_key as _wk, escape as _esc, get_key as _gk
except ImportError:            # desktop dry run: never wait, no poll test
    def _wk():
        return 0
    _esc = None
    _gk = None

W = 30                         # characters per printed line
PAGE = 8                       # lines per page; the 9th is the prompt
_n = [0, 0]                    # lines on this page, pages done


def out(s):
    # print s in lines of at most W chars; pause after PAGE lines.
    # Calls only natives, so it is safe up to depth 9.
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


def memfree():
    gc.collect()
    try:
        return gc.mem_free()
    except AttributeError:     # desktop dry run
        return 0


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


cnt = [0]


def plain():
    cnt[0] += 1
    plain()


def gchild(d):
    cnt[0] += 1
    if d > 0:
        r = yield gchild(d - 1)
        yield r + 1
    else:
        yield 0


GEN = type(gchild(0))


def tramp(g):
    st = [g]
    val = None
    while st:
        try:
            y = st[-1].send(val)
        except StopIteration:
            y = None
        if type(y) is GEN:
            st.append(y)
            val = None
            continue
        st.pop()
        val = y
    return val


def deep_in_gen():
    # one generator at trampoline depth, then plain recursion inside it
    cnt[0] = 0
    try:
        plain()
    except RuntimeError:
        pass
    yield cnt[0]


def t_tramp():
    cnt[0] = 0
    r = tramp(gchild(200))
    return "%d %d" % (r, cnt[0])


def gthrow():
    try:
        yield 1
    except ValueError:
        yield 2


def t_throw():
    g = gthrow()
    a = g.send(None)
    b = g.throw(ValueError("x"))
    return "%d %d" % (a, b)


def gret():
    yield 1
    return 7


def t_ret():
    g = gret()
    g.send(None)
    try:
        g.send(None)
    except StopIteration as e:
        return "val=%s" % (getattr(e, "value", "noattr"),)
    return "nostop"


def gone():
    yield 1
    yield 2


def geight(a, b, c, d):
    # 8 locals, like a typical g_* strategy
    e = a + b
    f = c + d
    g = e * f
    h = [a, b]
    yield g
    yield h


def t_mem():
    keep = [None] * 100       # allocated before the measurement
    a = memfree()
    for i in range(100):
        g = gone()
        g.send(None)          # suspended at its first yield; no child generator
        keep[i] = g
    g = None
    return (a - memfree()) // 100


def t_mem8():
    keep = [None] * 100
    a = memfree()
    for i in range(100):
        g = geight(i, 2, 3, 4)
        g.send(None)
        keep[i] = g
    g = None
    return (a - memfree()) // 100


def t_del():
    L = list(range(10))
    del L[4:]
    from array import array
    A = array('i', range(10))
    r = "list %d" % len(L)
    try:
        del A[4:]
        r += " arr %d" % len(A)
    except Exception as e:
        r += " arr E:" + type(e).__name__
    try:
        A.append(5)
        r += " app ok"
    except Exception as e:
        r += " app E:" + type(e).__name__
    return r


def t_ba():
    b = bytearray(4000)
    b[3999] = 1
    return "%d %d" % (len(b), b[3999])


def t_time():
    import time
    names = []
    for n in ("monotonic", "time", "ticks_ms", "perf_counter"):
        if hasattr(time, n):
            names.append(n)
    return " ".join(names)


def tryit(label, f):
    try:
        out(label + " " + str(f()))
    except BaseException as e:
        out(label + " E:" + type(e).__name__)


# --- native costs at depth: deep(n, f) runs f as the frame at depth n ------


def deep(n, f):
    if n > 2:
        return deep(n - 1, f)
    return f()


class PErr(Exception):
    pass


def t_exc():
    try:
        raise PErr("x")
    except PErr:
        return "ok"


def t_gc():
    gc.collect()
    return "ok"


def t_imp():
    # PRBL300 is the 300-line module that build/genprobe.py writes (M0.5)
    a = memfree()
    __import__("PRBL300")
    return "ok %d" % (a - memfree())


def src300():
    # about 300 lines shaped like cas-evo code: loops over flat tuples,
    # if chains, tuple tables
    L = []
    for k in range(27):
        L.append("def f%d(t, a, b):" % k)
        L.append(" r = []")
        L.append(" i = 1")
        L.append(" while i < len(t):")
        L.append("  x = t[i]")
        L.append("  if x == a:")
        L.append("   r.append((x, b, %d))" % k)
        L.append("  elif x > b and x < a + %d:" % k)
        L.append("   r.append((b, x, t[i + 1]))")
        L.append("  i += 2")
        L.append(" return tuple(r)")
    L.append("TAB = ((1, 'sin', 2), (2, 'cos', 3),")
    L.append("       (3, 'tan', 4), (4, 'ln', 5))")
    L.append("N = len(TAB)")
    return chr(10).join(L)


SRC = [None]


def t_cmp():
    # compile and run SRC (exec) at the caller's depth; bytes kept by the code
    d = {}
    a = memfree()
    exec(SRC[0], d)
    b = memfree()
    d = None
    return "ok %d" % (a - b)


def t_sort():
    # 3,000 flat 2-tuples, sorted at the caller's depth: random, ascending,
    # descending. Calls only natives.
    r = ""
    for mode in (0, 1, 2):
        print("sort mode %d" % mode)    # the last line printed names a crash
        _n[0] += 1
        L = []
        for i in range(3000):
            if mode == 0:
                k = (i * 7919) % 3001
            elif mode == 1:
                k = i
            else:
                k = 3000 - i
            L.append((k, i))
        try:
            L.sort()
            r += " ok"
        except RuntimeError:
            r += " RT"
        except MemoryError:
            r += " MEM"
        L = None
        gc.collect()
    return r


def t_math():
    # how math reports domain errors and overflow: an exception name or value
    for lab, src in (("asin2", "math.asin(2.0)"),
                     ("log0", "math.log(0.0)"),
                     ("sqrtm1", "math.sqrt(-1.0)"),
                     ("0**-1", "0.0 ** -1"),
                     ("cbrt", "(-8.0) ** (1 / 3)"),
                     ("ovf", "1e308 * 10"),
                     ("exp1k", "math.exp(1000.0)"),
                     ("logm1", "math.log(-1.0)"),
                     ("infinf", "float('inf') - float('inf')"),
                     ("intinf", "int(float('inf'))"),
                     ("nanck", "[v - v != 0 for v in (float('nan'), "
                      "float('inf'), 1.5)]")):
        try:
            v = eval(src)
            r = repr(v)
        except Exception as e:
            r = type(e).__name__
        out("math %s %s" % (lab, r))
    return "done"


def drain(clk, sc):
    # read keys until none came for 0.5 s (at most 5 s), so that a held
    # [clear] cannot auto-repeat into the next page's key wait
    if clk is None:
        j = 0
        while j < 20000:
            j += 1
            _gk()
        return
    t1 = last = clk()
    while True:
        now = clk()
        if _gk():
            last = now
        if (now - last) * sc > 0.5 or (now - t1) * sc > 5:
            return


def busy(which, clk, sc):
    # a 3 s busy loop that polls escape() (which 0) or get_key() (which 1)
    # every 256 iterations, with a countdown. Returns (hits, codes, loops).
    hits = 0
    keys = []
    i = 0
    left = 3
    t0 = clk() if clk else 0
    while left > 0:
        i += 1
        if not i & 255:
            if which == 0:
                if _esc():
                    hits += 1
            else:
                k = _gk()
                if k:
                    hits += 1
                    if len(keys) < 6:
                        keys.append(k)
            if clk:
                e = int((clk() - t0) * sc)
                if 3 - e < left:
                    left = 3 - e
                    print(left)           # countdown, once per second
            elif i >= 900000:
                left = 0
    return hits, keys, i


def t_poll():
    # 3 s polling only escape(), then 3 s polling only get_key(), while the
    # user taps [clear]. Keys left queued between the two are counted (q):
    # they show whether escape() consumes the key press.
    if _esc is None:
        return "no ti_system"
    clk, sc = clock()
    page()
    print("POLL: press ENTER. Then")
    print("tap CLEAR about once a")
    print("second until the count-")
    print("down 2 1 0 2 1 0 ends.")
    _wk()
    he, ke, ne = busy(0, clk, sc)
    q = 0
    while _gk() and q < 50:               # presses escape() left queued
        q += 1
    hk, kk, nk = busy(1, clk, sc)
    print("Stop. Release CLEAR.")
    drain(clk, sc)
    _n[0] = 7                             # 6 countdown lines + 1
    out("poll esc %d q %d n %d" % (he, q, ne))
    return "keys %s n %d" % (" ".join([str(k) for k in kk]) or "-", nk)


out("PROBE6 v1")
cnt[0] = 0
try:
    plain()                    # from module level: device expects 10
except RuntimeError:
    pass
out("plain %d" % cnt[0])
# tryit(1) > lambda(2) > tramp(3) > gen(4) > plain x N:
# N = 6 -> resuming a generator with send() costs no extra frame
tryit("ingen", lambda: tramp(deep_in_gen()))
tryit("tramp", t_tramp)
tryit("throw", t_throw)
tryit("ret", t_ret)
tryit("genB", t_mem)
tryit("genB8", t_mem8)
tryit("del", t_del)
tryit("bytea", t_ba)
tryit("time", t_time)
tryit("math", t_math)
CHAIN = None
for i in range(2000):          # a deeply nested chain for the collector to mark
    CHAIN = (CHAIN, i)
for lab, d, f in (("exc9", 9, t_exc), ("exc10", 10, t_exc),
                  ("gc10", 10, t_gc)):
    try:
        out(lab + " " + str(deep(d, f)))
    except BaseException as e:
        out(lab + " E:" + type(e).__name__)
CHAIN = None
SRC[0] = src300()
out("cmp src %d lines" % (SRC[0].count(chr(10)) + 1))
for lab, d, f in (("imp6", 6, t_imp), ("cmp6", 6, t_cmp),
                  ("cmp8", 8, t_cmp), ("cmp9", 9, t_cmp)):
    try:
        out(lab + " " + str(deep(d, f)))
    except BaseException as e:
        out(lab + " E:" + type(e).__name__)
SRC[0] = None
out("free %d" % memfree())
tryit("poll", t_poll)
# RISKY, last: native quicksort at depth 9. The calculator may freeze.
page()
out("RISKY part next. If the")
out("calc freezes: photo the")
out("screen, then reset it.")
try:
    out("sort9" + deep(9, t_sort))
except BaseException as e:
    out("sort9 E:" + type(e).__name__)
print("== PROBE6 end, p%d ==" % (_n[1] + 1))
