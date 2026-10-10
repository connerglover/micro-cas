# Compact probe: short lines so results fit on a few screenshots.
import sys
import gc


def yn(f):
    try:
        f()
        return "Y"
    except Exception:
        return "N"


print("v", str(getattr(sys, "version", "?"))[:28])
gc.collect()
try:
    print("free", gc.mem_free())
except Exception:
    print("free ?")

ok = []
for m in ("cmath", "ti_draw", "ti_plotlib", "ti_image", "time", "array",
          "collections", "micropython", "re", "fractions", "struct", "os"):
    try:
        __import__(m)
        ok.append(m)
    except Exception:
        pass
print("mods:", " ".join(ok))

miss = []
for n in ("exec", "eval", "compile", "open", "input", "complex", "set",
          "frozenset", "property", "divmod", "round"):
    try:
        if n not in dir(__builtins__):
            miss.append(n)
    except Exception:
        miss.append(n + "?")
print("no bi:", " ".join(miss))


def t_exec():
    exec("a=1")


def t_f():
    eval("f'{1}'")


def t_mod():
    import PRBMOD
    PRBMOD.hello()


print("eval", yn(lambda: eval("1+1")), "exec", yn(t_exec),
      "fstr", yn(t_f), "imp", yn(t_mod))


def rec(n):
    return n if n == 0 else 1 + rec(n - 1)


best = 0
for d in (25, 50, 100, 200, 400, 800, 1600):
    try:
        rec(d)
        best = d
    except Exception:
        break
print("rec", best, "list", yn(lambda: list(range(5000))))

try:
    import time
    clk = time.monotonic if hasattr(time, "monotonic") else time.time
    t = clk()
    s = 0
    for i in range(20000):
        s += i * i
    print("loop", clk() - t)
except Exception as e:
    print("loop err", e)

try:
    import ti_system as ts
    print("ts:", " ".join(n for n in dir(ts) if not n.startswith("_")))
except Exception as e:
    print("ts err", e)
