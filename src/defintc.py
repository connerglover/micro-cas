#@L 2
# Definite integration helper family.
import math
import node as K
import alg as A
import parse as P
import run as R

def safe_quad(f, x):                                          #@L 4
    for n in A.postorder(f):
        t = K.N[n]
        if t[0] == K.MUL:
            for j in range(2, len(t), 2):
                base, power = t[j], t[j + 1]
                p = K.N[power]
                u = power if base == K.E else base if p[0] == K.NUM and not p[2] and p[1] < 0 else None
                if u is not None and not K.free_of(u, x) and A.quadratic(u, x) is None:
                    return False       # unresolved narrow features cannot certify sampling
    return True

def candidates(f, x, features=True):                          #@L 4
    out = []
    for n in A.postorder(f):
        t = K.N[n]
        if t[0] == K.MUL:
            for j in range(2, len(t), 2):
                q = K.N[t[j + 1]]
                quadratic = None
                if q[0] == K.NUM and not q[2] and q[1] < 0:
                    if t[j] not in out:
                        out.append(t[j])
                    quadratic = t[j]
                elif t[j] == K.E:
                    quadratic = t[j + 1]
                if features and quadratic is not None:
                    abc = A.quadratic(quadratic, x)
                    if abc is not None and abc[0] != K.ZERO:
                        u = K.add_([K.mul_(K.TWO, [(abc[0], K.ONE), (x, K.ONE)]), abc[1]])
                        if u not in out:
                            out.append(u)
        elif t[0] == K.LN:
            u = t[1]
            if K.N[u][0] == K.ABS:
                u = K.N[u][1]
            if u not in out:
                out.append(u)
        elif t[0] in (K.TAN, K.SEC, K.CSC, K.COT):
            u = K.fn_(K.COS if t[0] in (K.TAN, K.SEC) else K.SIN, t[1])
            if u not in out:
                out.append(u)
    return out



def g_points(f, x, lo, hi):                                    #@L 2
    points = []
    finite = lo != -float('inf') and hi != float('inf')
    for u in candidates(f, x, finite):
        if K.free_of(u, x):
            continue
        t = K.N[u]
        roots = None
        if t[0] in (K.SIN, K.COS):
            linear = A.linear(t[1], x)
            if linear is not None:
                av, bv = R.MODS['defb'].number(linear[0]), R.MODS['defb'].number(linear[1])
                if av is not None and bv is not None and av:
                    offset = 0.5 if t[0] == K.COS else 0.0
                    low, high = sorted((av * lo + bv, av * hi + bv))
                    low = -R.MODS['def'].MAXPOINTS * math.pi if low == -float('inf') else low
                    high = R.MODS['def'].MAXPOINTS * math.pi if high == float('inf') else high
                    start, stop = math.ceil(low / math.pi - offset), math.floor(high / math.pi - offset)
                    if stop - start + 1 > R.MODS['def'].MAXPOINTS:
                        raise K.CasError('Too many break points')
                    roots = []
                    for k in range(start, stop + 1):
                        angle = K.mul_(K.num(2*k + (1 if offset else 0), 0, 2), [(K.PI, K.ONE)])
                        root = K.mul_(K.ONE, [(K.add_([angle, K.neg_(linear[1])]), K.ONE), (linear[0], K.MONE)])
                        roots.append(root)
        if roots is None:
            solver = R.need('solve')
            roots = yield solver.g_roots(u, x, 0)
        if roots is None or roots == K.TRUE:
            continue
        for r in roots:
            value = R.MODS['defb'].number(r)
            if value is not None and lo <= value <= hi and r not in points:
                points.append(r)
        if len(points) > R.MODS['def'].MAXPOINTS:
            raise K.CasError('Too many break points')
    ordered = []
    for point in points:
        ordered.append((R.MODS['defb'].number(point), point))
    ordered.sort()
    out = []
    for value, point in ordered:
        if not out or abs(value - R.MODS['defb'].number(out[-1])) > 1e-10 * (1 + abs(value)):
            out.append(point)
    solver = None
    R.drop(('solve', 'fact'))
    yield tuple(out)



def g_divergence(f, x, a, b, points):                          #@L 2
    limits = R.need('lim')
    for point in (a, b):
        if point == K.OO or K.isninf(point):
            value = yield limits.g_lim(f, x, point)
            if value == K.OO or K.isninf(value) or (K.N[value][0] <= K.FLT and value != K.ZERO):
                yield K.mk((K.DIVG, K.ZERO))
                return
    for point in points:
        sides = (1,) if point == a else (-1,) if point == b else (-1, 1)
        for side in sides:
            lead = yield R.MODS['ser'].g_series(f, x, point, 2, side)
            if lead is not None and len(lead) > 1 and lead[0] <= -1:
                yield K.mk((K.DIVG, K.ONE))
                return
            distance = K.add_([x, K.neg_(point)])
            comparison = K.mul_(K.ONE, [(f, K.ONE), (distance, K.TWO)])
            value = yield limits.g_lim(comparison, x, point, side)
            if value == K.OO or K.isninf(value):
                yield K.mk((K.DIVG, K.ONE))
                return
    yield None
