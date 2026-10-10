# Recursion deep-dive: exact max depth under different call shapes.
import gc

gc.collect()
out = []
cnt = [0]


def measure(name, start):
    cnt[0] = 0
    try:
        start()
        out.append(name + " ok")
    except BaseException as e:
        out.append("%s %d %s" % (name, cnt[0], type(e).__name__[:6]))


def plain():
    cnt[0] += 1
    plain()


def noargs():
    cnt[0] += 1
    noargs()


def biglocals(a=1, b=2, c=3, d=4, e=5, f=6, g=7, h=8):
    cnt[0] += 1
    i = j = k = l = m = n = o = p = 0
    biglocals(a, b, c, d, e, f, g, h)


def ping():
    cnt[0] += 1
    pong()


def pong():
    cnt[0] += 1
    ping()


class C:
    def m(self):
        cnt[0] += 1
        self.m()


def gen(n):
    cnt[0] += 1
    yield from gen(n + 1)


lam = None


def via_lambda():
    global lam
    lam = lambda: (cnt.__setitem__(0, cnt[0] + 1), lam())
    lam()


measure("plain", plain)
measure("biglc", biglocals)
measure("mutl", ping)
measure("meth", C().m)
measure("lamb", via_lambda)
measure("gen", lambda: list(gen(0)))


# Chain of distinct (non-recursive) functions: is it call depth or recursion?
def mk(n):
    src = "def f%d():\n cnt[0]+=1\n f%d()\n" % (n, n + 1)
    exec(src, globals())


for i in range(40):
    mk(i)
exec("def f40():\n cnt[0]+=1\n", globals())
measure("chain", lambda: f0())


# Same plain recursion but started from inside 3 extra frames.
def w1():
    w2()


def w2():
    w3()


def w3():
    plain()


measure("nest3", w1)

# Nested expression depth in the parser itself.
best = 0
for d in (5, 10, 20, 40, 80):
    try:
        eval("(" * d + "1" + ")" * d)
        best = d
    except BaseException:
        break
out.append("paren %d" % best)

for line in out:
    print(line)
