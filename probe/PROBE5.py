# PROBE5 (cas-evo M0.3): fills the [A] gaps of docs/reference/device-python.md:
# missing names, syntax, numbers, strings, sort and dict order, hidden frame
# costs, import depth, and native recursion over nested tuples.
# Send PRBIMP.py too. Run PROBE5. Each page ends with "-- pN: screenshot,
# key --": take a screenshot, then press any key.
# The LAST section (nested tuples) is RISKY: back up the calculator first.
# Device rules: Python 3.4 subset, ASCII only, printed lines <= 30 chars.
import gc
import sys
try:
    from ti_system import wait_key as _wk
except ImportError:            # desktop dry run: never wait
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


def miss(label, names, ns):
    m = []
    for n in names:
        try:
            if ns is None:
                eval(n)
            elif not hasattr(ns, n):
                m.append(n)
        except Exception:
            m.append(n)
    out(label + ": " + (" ".join(m) if m else "-"))


def syn(label, snippets):
    bad = []
    for name, src in snippets:
        try:
            exec(src, {})
        except BaseException:
            bad.append(name)
    out(label + ": " + (" ".join(bad) if bad else "-"))


def tryit(label, f):
    try:
        out(label + " " + str(f()))
    except BaseException as e:
        out(label + " E:" + type(e).__name__)


def _gstop():
    yield 1
    raise StopIteration


NL = chr(10)
out("PROBE5 v1")
out("name " + __name__)
out("impl " + str(getattr(sys, "implementation", "?")))
out("maxsize " + str(getattr(sys, "maxsize", "?")))
gc.collect()
try:
    out("free %d alloc %d" % (gc.mem_free(), gc.mem_alloc()))
except Exception as e:
    out("free E:" + type(e).__name__)
miss("nobi", ("reversed", "frozenset", "compile", "open", "format",
              "vars", "ascii", "delattr", "NotImplemented", "bytearray",
              "memoryview", "RecursionError", "callable", "next", "iter",
              "min", "max", "sum", "any", "all", "zip", "map", "filter",
              "enumerate", "slice", "hex", "bin", "oct", "chr", "ord",
              "id", "hash", "pow", "super", "property", "classmethod",
              "staticmethod", "globals", "locals", "setattr", "getattr",
              "hasattr", "isinstance", "issubclass", "__import__"), None)
import math
miss("nomath", ("gcd", "isqrt", "factorial", "log10", "log2", "sinh",
                "cosh", "tanh", "asinh", "acosh", "atanh", "expm1",
                "log1p", "gamma", "lgamma", "erf", "hypot", "inf", "nan",
                "tau", "isclose", "frexp", "ldexp", "fsum", "comb",
                "prod", "trunc", "modf", "fmod", "copysign", "isnan",
                "isinf", "isfinite", "atan2"), math)
miss("nostr", ("center", "ljust", "rjust", "zfill", "title", "isalnum",
               "isnumeric", "isdecimal", "isidentifier", "partition",
               "rpartition", "rsplit", "splitlines", "casefold",
               "swapcase", "capitalize", "expandtabs", "translate",
               "format", "encode", "count", "rindex", "rfind",
               "removeprefix"), "")
miss("noint", ("bit_length", "to_bytes", "from_bytes"), 0)
miss("nolist", ("copy", "clear", "sort", "reverse", "insert"), [])
miss("nodict", ("copy", "clear", "setdefault", "popitem", "fromkeys",
                "update", "get"), {})
miss("nosys", ("modules", "implementation", "maxsize", "path", "exit",
               "getrecursionlimit", "setrecursionlimit", "intern",
               "print_exception", "settrace", "getsizeof"), sys)
import collections
miss("nocoll", ("OrderedDict", "namedtuple", "deque", "defaultdict"),
     collections)
import time
miss("notime", ("monotonic", "time", "ticks_ms", "perf_counter",
                "sleep"), time)
miss("nogc", ("mem_free", "mem_alloc", "threshold", "enable"), gc)
syn("nosyn", (
    ("fstr", "x=1" + NL + "y=f'{x}'"),
    ("walrus", "y=(x:=1)"),
    ("star=", "a,*b=(1,2,3)"),
    ("kwonly", "def f(a,*,b=0):pass"),
    ("[*a]", "a=[1];b=[*a,2]"),
    ("{**d}", "d={1:2};e={**d}"),
    ("f(*a,*b)", "print(*[],*[],end='')"),
    ("1_0", "x=1_000"),
    ("raisefrom", "try:" + NL + " raise ValueError from None" + NL +
     "except ValueError:pass"),
    ("nonlocal", "def f():" + NL + " x=1" + NL + " def g():" + NL +
     "  nonlocal x" + NL + "  x=2" + NL + " g()" + NL + " return x" + NL +
     "assert f()==2"),
    ("annot", "def f(a:int)->int:return a"),
    ("varannot", "x:int=1"),
    ("async", "async def f():pass"),
    ("with", "class C:" + NL + " def __enter__(s):return s" + NL +
     " def __exit__(s,*a):return False" + NL + "with C() as c:pass"),
    ("deco", "def d(f):return f" + NL + "@d" + NL + "def g():pass"),
    ("setcomp", "s={x for x in range(3)}"),
    ("dictcomp", "d={x:1 for x in range(3)}"),
    ("slots", "class C:" + NL + " __slots__=('a',)" + NL + "C().b=1"),
    ("super0", "class A:" + NL + " def f(s):return 1" + NL +
     "class B(A):" + NL + " def f(s):return super().f()" + NL +
     "assert B().f()==1"),
    ("multinh", "class A:pass" + NL + "class B:pass" + NL +
     "class C(A,B):pass"),
    ("radd", "class A:" + NL + " def __radd__(s,o):return 7" + NL +
     "assert 1+A()==7"),
    ("getattr_", "class A:" + NL + " def __getattr__(s,n):return 7" + NL +
     "assert A().zz==7"),
    ("property", "class A:" + NL + " @property" + NL +
     " def p(s):return 7" + NL + "assert A().p==7"),
    ("ne_auto", "class A:" + NL + " def __eq__(s,o):return True" + NL +
     "assert not (A()!=A())")))
tryit("pow3", lambda: pow(3, 200, 1000003))
tryit("f10^400", lambda: float(10 ** 400))
tryit("bigeqf", lambda: (10 ** 20 + 1) == 1e20)
tryit("rnd2.5", lambda: (round(2.5), round(3.5), round(-0.5)))
tryit("rnd.125", lambda: round(0.125, 2))
tryit("r.1+.2", lambda: repr(0.1 + 0.2))
tryit("s1e16", lambda: (str(1e16), str(1.0), str(1e-5)))
tryit("g10", lambda: "%.10g|%.10g" % (2.0 / 3, 1e22))
tryit("e17", lambda: "%.17g" % 0.1)
tryit("sum.1", lambda: repr(sum([0.1] * 10)))
tryit("star%", lambda: "%*d|%-4s|" % (5, 42, "ab"))
tryit("fmt", lambda: "{0}-{1:>4}".format(1, 2))
tryit("swtup", lambda: "abc".startswith(("x", "a")))
tryit("rsplitN", lambda: "a b c".rsplit(None, 1))
tryit("negmod", lambda: (-7 // 2, -7 % 2, divmod(-7, 2)))
tryit("cplx", lambda: (complex(1, 2) * 2j, abs(3 + 4j)))
tryit("1/0.", lambda: 1.0 / 0.0)
tryit("bigstr", lambda: len(str(7 ** 6000)))
tryit("stopit", lambda: list(_gstop()))
tryit("frzset", lambda: hash(frozenset((1, 2))) is not None)
tryit("revrs", lambda: list(reversed([1, 2, 3])))
tryit("slice", lambda: [0, 1, 2, 3, 4][::-2])
d = {}
for k in ("x", "a", "m", "b", "z", "c", "q", "e"):
    d[k] = 1
out("dictord " + "".join(d))
ks = [(1, "a"), (0, "b"), (1, "c"), (0, "d"), (1, "e"), (0, "f"),
      (1, "g"), (0, "h"), (1, "i"), (0, "j"), (1, "k"), (0, "l")]
calls = [0]


def kf(p):
    calls[0] += 1
    return p[0]


r = sorted(ks, key=kf)
out("stable " + "".join([p[1] for p in r]) + " kc" + str(calls[0]))

# Frame cost of constructs, PROBE4 harness. Each line is
# "name count/ideal error": ideal is the count when the construct costs no
# hidden frame. count = ideal/2 means one hidden frame per level.
cnt = [0]
res = []


def measure(name, start, ideal):
    cnt[0] = 0
    try:
        start()
        res.append(name + " ok")
    except BaseException as e:
        res.append("%s %d/%d %s" % (name, cnt[0], ideal,
                                    type(e).__name__[:4]))


def plain():
    cnt[0] += 1
    plain()


def ks_(x):
    cnt[0] += 1
    sorted((1, 2), key=ks_)
    return 0


def mp_(x):
    cnt[0] += 1
    list(map(mp_, (1,)))


def mk_(x):
    cnt[0] += 1
    min((1, 2), key=mk_)


def ev_():
    cnt[0] += 1
    eval("ev_()")


def lc_():
    cnt[0] += 1
    [lc_() for _ in (1,)]


def ge_():
    cnt[0] += 1
    sum(ge_() for _ in (1,))


class Q:
    def __eq__(s, o):
        cnt[0] += 1
        return Q() == Q()


class R:
    def __init__(s):
        cnt[0] += 1
        R()


class H:
    def __hash__(s):
        cnt[0] += 1
        return hash(H())


class S:
    def __str__(s):
        cnt[0] += 1
        return str(S())


class A:
    def __add__(s, o):
        cnt[0] += 1
        return A() + 1


lam = lambda: (cnt.append(0), lam())
# measure is depth 1; a direct start runs at 2 (ideal 9), a lambda start
# puts the shape at 3 (ideal 8)
measure("plain", plain, 9)
measure("sortk", lambda: ks_(0), 8)
measure("map", lambda: mp_(0), 8)
measure("minkey", lambda: mk_(0), 8)
measure("eval", ev_, 9)
measure("lcomp", lc_, 9)
measure("genexp", ge_, 9)
measure("eq", lambda: Q() == Q(), 8)
measure("init", R, 9)
measure("hash", lambda: hash(H()), 8)
measure("str", lambda: str(S()), 8)
measure("add", lambda: A() + 1, 8)
for line in res:
    out(line)
del cnt[1:]
try:
    lam()                       # from module level: ideal 10
except BaseException as e:
    out("lamb %d/10 %s" % (len(cnt) - 1, type(e).__name__[:4]))
try:
    import PRBIMP               # body at depth 1 if import is free: ideal 9
    out("imptop %d/9" % PRBIMP.N)
except ImportError:
    out("imptop: PRBIMP missing")


def _imp_in_fn():
    if "PRBIMP" in sys.modules:
        del sys.modules["PRBIMP"]
    import PRBIMP               # tryit 1, this 2, body 3: ideal 7
    return "%d/7" % PRBIMP.N


tryit("impfn", _imp_in_fn)
gc.collect()
try:
    out("free %d" % gc.mem_free())
except Exception:
    out("free ?")
# RISKY: native recursion over nested tuples. Each step is printed before it
# runs. If the calculator freezes or resets, the last "nest" line on the
# screen is the answer.
page()
out("RISKY part next. If the")
out("calc freezes: photo the")
out("screen, then reset it.")
for dep in (8, 16, 32, 64, 128):
    t = u = 0
    for i in range(dep):
        t = (i, t)
        u = (i, u)
    for op in ("eq", "hash", "repr", "lt"):
        out("nest %d %s" % (dep, op))
        try:
            if op == "eq":
                t == u
            elif op == "hash":
                hash(t)
            elif op == "repr":
                repr(t)
            else:
                t < u
        except BaseException as e:
            out(" E:" + type(e).__name__)
t = u = None
out("nest done")
print("== PROBE5 end, p%d ==" % (_n[1] + 1))
