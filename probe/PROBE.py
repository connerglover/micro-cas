# Environment probe for the TI-84 EVO. Transfer PROBE.py and PRBMOD.py,
# run PROBE, and copy every line of output back.
import sys
import gc

print("ver", getattr(sys, "version", "?"))
print("impl", getattr(sys, "implementation", "?"))
print("plat", getattr(sys, "platform", "?"))

gc.collect()
try:
    print("free", gc.mem_free(), "alloc", gc.mem_alloc())
except Exception as e:
    print("mem err", e)

for m in ("math", "cmath", "ti_system", "ti_draw", "ti_graphics", "ti_plotlib",
          "ti_image", "time", "random", "array", "collections", "micropython",
          "re", "ure", "fractions", "struct", "os", "uos", "io"):
    try:
        __import__(m)
        print("mod ok", m)
    except Exception as e:
        print("mod NO", m, type(e).__name__)

for n in ("exec", "eval", "compile", "open", "input", "complex", "set",
          "frozenset", "property", "staticmethod", "divmod", "round"):
    try:
        print("bi", n, n in dir(__builtins__))
    except Exception as e:
        print("bi", n, "?", type(e).__name__)

try:
    print("eval", eval("2**100"))
except Exception as e:
    print("eval err", e)
try:
    exec("print('exec ok')")
except Exception as e:
    print("exec err", e)
try:
    eval("f'{1+1}'")
    print("fstring ok")
except Exception as e:
    print("fstring err", type(e).__name__)

try:
    import PRBMOD
    print("usermod", PRBMOD.VAL, PRBMOD.hello())
except Exception as e:
    print("usermod err", type(e).__name__, e)


def rec(n):
    return n if n == 0 else 1 + rec(n - 1)


best = 0
for d in (25, 50, 100, 200, 400, 800, 1600):
    try:
        rec(d)
        best = d
    except Exception as e:
        print("rec fail at", d, type(e).__name__)
        break
print("rec ok to", best)

try:
    L = list(range(5000))
    print("list len", len(L))
    del L
except Exception as e:
    print("list err", type(e).__name__)

try:
    print("bigint", len(str(3 ** 2000)))
except Exception as e:
    print("bigint err", e)

try:
    print("float", repr(0.1 + 0.2), repr(1e300 * 10))
except Exception as e:
    print("float err", e)

try:
    import time
    t = time.monotonic() if hasattr(time, "monotonic") else time.time()
    s = 0
    for i in range(20000):
        s += i * i
    t2 = time.monotonic() if hasattr(time, "monotonic") else time.time()
    print("20k loop sec", t2 - t)
except Exception as e:
    print("time err", e)

try:
    import ti_system as ts
    print("ti_system", [n for n in dir(ts) if not n.startswith("_")])
except Exception as e:
    print("ti_system err", e)
for gm in ("ti_draw", "ti_graphics"):
    try:
        g = __import__(gm)
        print(gm, [n for n in dir(g) if not n.startswith("_")])
    except Exception:
        pass

gc.collect()
try:
    print("free end", gc.mem_free())
except Exception:
    pass

print("Keys: press keys to see codes, [clear] to stop")
try:
    import ti_system as ts
    while True:
        k = ts.wait_key()
        print("key", k)
        if k == 9 or k == 15:
            break
except Exception as e:
    print("key err", e)
