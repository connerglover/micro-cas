# PRBMEM (cas-evo M0.3; device-python 14.3, DESIGN.md 18.7): RAM per object
# shape, the sys.modules eviction checks, and per module: cost (steady RAM
# after import), import time, kept (RAM not freed by eviction: first cycle,
# second cycle, and with m.__dict__.clear() before the deletion) and peak
# (the compile transient, by a ballast binary search).
# Send PRBMOD.py too; PRBL100/200/300.py come from M0.5. Missing modules are
# reported and skipped. At T1.15, set MODS to the bundled T1 modules (device
# names, leaf modules first). Run from a fresh shell: run PRBMEM.
# Each page ends with "-- pN: screenshot, key --": take a screenshot, then
# press any key.
# Device rules: Python 3.4 subset, ASCII only, printed lines <= 30 chars.
import gc
import sys
try:
    from ti_system import wait_key as _wk
except ImportError:            # desktop dry run: never wait
    def _wk():
        return 0
MODS = ("PRBMOD", "PRBL100", "PRBL200", "PRBL300")
N = 200

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


def free():
    gc.collect()
    gc.collect()
    try:
        return gc.mem_free()
    except AttributeError:     # desktop dry run
        return 0


def per(make):
    keep = [None] * N
    a = free()
    for i in range(N):
        keep[i] = make(i)
    b = free()
    return (a - b) // N


class P:
    def __init__(s, a, b):
        s.a = a
        s.b = b


def mkclo(i):
    def f():
        return i
    return f


def gen8(a, b):
    # a suspended generator with a few locals, like a g_* strategy
    c = a + b
    d = [a]
    yield c
    yield d


def mkgen(i):
    g = gen8(i, 1)
    g.send(None)
    return g


def slots(n):
    # bytes per list slot holding a small int, as the node table's N/H/NX/V
    a = free()
    L = [0] * n
    b = free()
    L = None
    return (a - b) // n


def arr(n):
    from array import array
    a = free()
    A = array('i', [0] * n)    # the temporary list is collected by free()
    b = free()
    A = None
    return (a - b) // n


def dent(n):
    # bytes per dict entry (small-int keys), dict grown one key at a time
    a = free()
    d = {}
    for i in range(n):
        d[i * 7 + 1000] = i
    b = free()
    d = None
    return (a - b) // n


def unload(name, clear):
    m = sys.modules.get(name)
    if m is not None:
        if clear:
            try:
                m.__dict__.clear()
            except Exception:
                pass
        del sys.modules[name]
    m = None
    gc.collect()


def cycle(name, clear):
    # import name and evict it; (cost, kept, ms)
    clk, sc = clock()
    a = free()
    t0 = clk() if clk else 0
    m = __import__(name)
    t1 = clk() if clk else 0
    m = None
    b = free()
    unload(name, clear)
    c = free()
    return a - b, a - c, int((t1 - t0) * sc * 1000)


def peak(name):
    # largest ballast that still lets the import succeed -> peak need
    lo, hi = 0, free()
    while hi - lo > 1024:
        mid = (lo + hi) // 2
        try:
            ballast = bytearray(mid)
        except MemoryError:
            hi = mid
            continue
        ok = True
        try:
            __import__(name)
        except MemoryError:
            ok = False
        ballast = None
        unload(name, 0)
        if ok:
            lo = mid
        else:
            hi = mid
    return free() - lo


out("PRBMEM v1")
out("start %d" % free())
out("tup2 %d" % per(lambda i: (i, i)))
out("tup3 %d" % per(lambda i: (i, i, i)))
out("tup4 %d" % per(lambda i: (i, i, i, i)))
out("tup5 %d" % per(lambda i: (i, i, i, i, i)))
out("tup7 %d" % per(lambda i: (i, i, i, i, i, i, i)))
out("tup9 %d" % per(lambda i: (i, i, i, i, i, i, i, i, i)))
out("list3 %d" % per(lambda i: [i, i, i]))
out("dict2 %d" % per(lambda i: {1: i, 2: i}))
out("inst2 %d" % per(lambda i: P(i, i)))
out("float %d" % per(lambda i: i * 1.5))
out("int64 %d" % per(lambda i: (1 << 64) + i))
out("str20 %d" % per(lambda i: "abcdefghijklmnopqr" + str(i % 10) + "x"))
out("clos %d" % per(mkclo))
out("gen %d" % per(mkgen))
out("slot %d" % slots(1024))
out("arr %d" % arr(1024))
out("dent %d" % dent(400))
# eviction mechanism (DESIGN 18.5, 18.7)
out("sys.modules %s" % ("yes" if hasattr(sys, "modules") else "NO"))
try:
    m = __import__("PRBMOD")
    del sys.modules["PRBMOD"]
    gone = "PRBMOD" not in sys.modules
    m2 = __import__("PRBMOD")
    out("delmod %s reimport %s" % ("ok" if gone else "stays",
                                   "new" if m2 is not m else "same"))
except BaseException as e:
    out("delmod E:" + type(e).__name__)
try:
    m = __import__("PRBMOD")
    m.__dict__.clear()
    out("dictclr %s" % ("ok" if not hasattr(m, "VAL") else "no effect"))
    if "PRBMOD" in sys.modules:
        del sys.modules["PRBMOD"]
except BaseException as e:
    out("dictclr E:" + type(e).__name__)
m = m2 = None
gc.collect()
# per module: cost and import ms; kept for cycle 1, cycle 2, and cycle 3
# with __dict__.clear(); peak
for name in MODS:
    try:
        cost, k1, ms = cycle(name, 0)
    except ImportError:
        out(name + " missing")
        continue
    except MemoryError:
        unload(name, 0)
        out(name + " MemoryError")
        continue
    c2, k2, ms2 = cycle(name, 0)
    c3, kd, ms3 = cycle(name, 1)
    out("%s cost %d ms %d" % (name, cost, ms))
    out(" kept %d k2 %d kD %d" % (k1, k2, kd))
    try:
        out(" peak %d" % peak(name))
    except BaseException as e:
        unload(name, 0)
        out(" peak E:" + type(e).__name__)
out("end %d" % free())
print("== PRBMEM end, p%d ==" % (_n[1] + 1))
