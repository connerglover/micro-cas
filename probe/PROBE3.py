# Recursion + leftovers probe (PROBE2's top lines scrolled away and rec was 0).
import sys
import gc

print("v", str(getattr(sys, "version", "?"))[:28])
gc.collect()
print("free", gc.mem_free())
ok = []
for m in ("cmath", "ti_draw", "ti_plotlib", "time", "array",
          "collections", "micropython", "re", "fractions", "os"):
    try:
        __import__(m)
        ok.append(m)
    except Exception:
        pass
print("mods:", " ".join(ok))


def rec(n):
    if n == 0:
        return 0
    return 1 + rec(n - 1)


best = 0
err = ""
for d in (1, 2, 3, 5, 8, 12, 16, 20, 30, 50, 100, 200, 500):
    try:
        rec(d)
        best = d
    except BaseException as e:
        err = type(e).__name__ + " " + str(e)[:24]
        break
print("rec", best, err)


class Node:
    def __init__(self, k):
        self.k = k

    def depth(self):
        return 0 if self.k is None else 1 + self.k.depth()


n = Node(None)
for i in range(40):
    n = Node(n)
try:
    print("meth rec", n.depth())
except BaseException as e:
    print("meth err", type(e).__name__)

r = []
for name, f in (("cx", lambda: complex(1, 2) * 2),
                ("set", lambda: {1, 2} | {3}),
                ("dm", lambda: divmod(7, 2)),
                ("rnd", lambda: round(2.567, 2)),
                ("inp", lambda: callable(input)),
                ("big", lambda: (3 ** 200) // (7 ** 50)),
                ("sort", lambda: sorted([3, 1], key=lambda x: -x)),
                ("isub", lambda: issubclass(bool, int)),
                ("slots", lambda: hash((1, "a"))),
                ("fmt", lambda: "%.9g" % 3.14159265358)):
    try:
        f()
        r.append(name + "Y")
    except BaseException:
        r.append(name + "N")
print(" ".join(r))
