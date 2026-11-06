#@L 2
# Definite integration across jumps and gaps: the step-function scan, the quadrature edges and
# the refusal of an integrand undefined at a break point.
import node as K
import alg as A
import run as R

M_GAP = 'No result: the integrand is not continuous'
CELLS = 256         # the jump scan's grid (an even count: every second sample is the coarse grid)
MAXJUMPS = 24       # jumps per integral: 32 fit native heaps 185,680 and 189,776, 40 do not
EDGE = 1e-9         # the scan stays this fraction of the interval inside the bounds


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
