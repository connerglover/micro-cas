#@L 2
# Definite integration across jumps and gaps: the step-function scan, the quadrature edges and
# the refusal of an integrand undefined at a break point; and the exclusion of break points by
# interval arithmetic, which keeps a continuous integrand from loading the solver.
import math
import node as K
import alg as A
import run as R

M_GAP = 'No result: the integrand is not continuous'
CELLS = 256         # the jump scan's grid (an even count: every second sample is the coarse grid)
MAXJUMPS = 24       # jumps per integral: 32 fit native heaps 185,680 and 189,776, 40 do not
EDGE = 1e-9         # the scan stays this fraction of the interval inside the bounds
CELLS2 = 16         # exclusion: the interval as a whole, then in this many cells
SLACK = 1e-9        # exclusion: rounding margin, relative to the largest bound met


def imul(a, b):                                               #@L 5
    p, q, r, s = a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1]
    return min(p, q, r, s), max(p, q, r, s)


def ipow(b, p):                                               #@L 4
    """Bounds of b^p; None where the power is not real or has a pole on b."""
    l, h = b
    if p[0] != p[1]:
        if l <= 0:
            return None
        u, v = imul((math.log(l), math.log(h)), p)
        return math.exp(u), math.exp(v)
    q = p[0]
    if q != int(q):
        if l < 0 or q < 0 and l == 0:
            return None
        return (l ** q, h ** q) if q > 0 else (h ** q, l ** q)
    if q < 0 and l <= 0 <= h:
        return None
    n = int(abs(q))
    u, v = l ** n, h ** n
    if not n & 1:
        u, v = 0.0 if l <= 0 <= h else min(u, v), max(u, v)
    return (u, v) if q > 0 else (1 / v, 1 / u)


def isin(l, h):                                               #@L 4
    if h - l >= 2 * math.pi:
        return -1.0, 1.0
    u, v = math.sin(l), math.sin(h)
    u, v = min(u, v), max(u, v)
    turn = 2 * math.pi
    if math.ceil((l - math.pi / 2) / turn) <= math.floor((h - math.pi / 2) / turn):
        v = 1.0
    if math.ceil((l + math.pi / 2) / turn) <= math.floor((h + math.pi / 2) / turn):
        u = -1.0
    return u, v


def span(order, const, x, lo, hi):                            #@L 3
    """Bounds of the last node of order for x in [lo, hi], and the largest magnitude met, for
    the rounding margin. None for what has no bound here. const: bounds of the nodes free of x
    (None for no real value). Interval arithmetic may widen a range, never narrow it."""
    env = {x: (lo, hi)}
    big = 1.0
    r = None
    for n in order:
        if n == x:
            r = env[x]
            continue
        if n in const:
            r = env[n] = const[n]
            continue
        t = K.N[n]
        op = t[0]
        r = None
        if op == K.ADD or op == K.MUL:
            r = env[t[1]]
            for j in range(2, len(t), 2):
                a, b = env[t[j]], env[t[j + 1]]
                if r is None or a is None or b is None:
                    return None
                if op == K.ADD:
                    a = imul(a, b)
                    r = r[0] + a[0], r[1] + a[1]
                else:
                    a = ipow(a, b)
                    if a is None:
                        return None
                    r = imul(r, a)
        elif env.get(t[1]) is not None:
            l, h = env[t[1]]
            if op == K.SIN:
                r = isin(l, h)
            elif op == K.COS:
                r = isin(l + math.pi / 2, h + math.pi / 2)
            elif op == K.ATAN:
                r = math.atan(l), math.atan(h)
            elif op == K.LN and l > 0:
                r = math.log(l), math.log(h)
            elif op == K.ABS:
                u, v = abs(l), abs(h)
                r = 0.0 if l <= 0 <= h else min(u, v), max(u, v)
        if r is None or not (-1e300 < r[0] and r[1] < 1e300):
            return None
        env[n] = r
        big = max(big, abs(r[0]), abs(r[1]))
    return None if r is None else (r[0], r[1], big)


def g_clear(u, x, lo, hi):                                    #@L 2
    """True when u provably has no zero on the finite closed [lo, hi]. False proves nothing: the
    caller then asks the solver. A zero never passes, so an integrand this clears is continuous
    there and needs no solver pack: on a tight heap that is the difference between an answer and
    Out of memory (docs/notes/FASTBOOT.md)."""
    order = A.postorder(u)
    const = {}
    for n in order:
        if K.free_of(n, x):
            v = R.MODS['defb'].number(n)
            const[n] = None if v is None or not -1e300 < v < 1e300 else (v, v)
    for cells in (1, CELLS2):
        left = lo
        good = True
        for j in range(1, cells + 1):
            right = hi if j == cells else lo + (hi - lo) * j / cells
            try:
                r = span(order, const, x, left, right)
            except (OverflowError, ValueError, ZeroDivisionError):
                r = None
            if r is None:
                yield False
                return
            if r[0] <= SLACK * r[2] and r[1] >= -SLACK * r[2]:
                good = False
                break
            left = right
        if good:
            yield True
            return
    yield False


def stepat(program, v):                                       #@L 3
    """A step node's value at v; None where it is undefined, which then counts as a change."""
    try:
        return A.nrun(program, (v,))
    except K.CasSoft:
        return None


def g_steps(f, x, lo, hi):                                    #@L 2
    """The jumps of f's floor, ceil and sign nodes on a finite (lo, hi), as float nodes, for the
    quadrature to split at; None when f has no such node. Every node is sampled on CELLS cells
    and on half as many: different change counts mean jumps closer than the grid can separate,
    so no split can be trusted."""
    out = None
    width = hi - lo
    for n in A.postorder(f):
        if not K.SIGN <= K.N[n][0] <= K.CEIL or K.free_of(n, x):
            continue
        try:
            program = A.nprog(n, (x,))
        except K.CasSoft:
            continue
        out = out or []
        fine = coarse = 0
        v = lo + EDGE * width
        before = half = stepat(program, v)
        for j in range(1, CELLS + 1):
            u = v
            v = hi - EDGE * width if j == CELLS else lo + width * j / CELLS
            now = stepat(program, v)
            if now != before:
                fine += 1
                w = v
                while w - u > width * 1e-15:        # bisect the change
                    m = (u + w) * 0.5
                    if stepat(program, m) == before:
                        u = m
                    else:
                        w = m
                out.append(K.flt((u + w) * 0.5))
                if len(out) > MAXJUMPS:
                    raise K.CasError('Too many break points')
            before = now
            if j % 2 == 0:
                if now != half:
                    coarse += 1
                half = now
            if j % 64 == 0:
                yield R.TICK
        if fine != coarse:
            raise K.CasError('Too many break points')
    yield None if out is None else tuple(out)


def g_broken(f, x, points):                                   #@L 2
    """Raise when f is undefined at one of points: a value failed there, and the input echoed
    back would read as an answer."""
    try:
        program = A.nprog(f, (x,))
        for p in points:
            A.nrun(program, (R.MODS['defb'].number(p),))
    except K.CasSoft:
        raise K.CasError(M_GAP)
    yield None


def g_edges(a, b, lo, hi, points):                            #@L 2
    """The sorted quadrature edges from a to b through the points strictly inside."""
    cuts = []
    for p in points:
        v = R.MODS['defb'].number(p)
        if lo < v < hi:
            cuts.append((v, p))
    cuts.sort()
    edges = [a]
    for v, p in cuts:
        edges.append(p)
    edges.append(b)
    yield edges
