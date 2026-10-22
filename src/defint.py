#@L 2
# Definite/improper integration: singularity splitting, exact primitives and tanh-sinh.
import node as K
import alg as A
import run as R

MAXEVAL = 400
MAXLEVEL = 6
MAXPOINTS = 16
QTOL = 2e-8
CHECKTOL = 1e-6
M_ARG = 'Invalid argument'


def g_endpoint(F, x, point, side):                             #@L 2
    value = None
    if point != K.OO and not K.isninf(point):
        try:
            value = A.subst(F, x, point)
            if value == K.UNDEF:
                value = None
        except K.CasSoft:
            pass
    if value is None:
        limits = R.need('lim')
        t = K.N[F]
        if t[0] == K.ADD:
            terms = [t[1]]
            good = True
            for j in range(2, len(t), 2):
                v = yield limits.g_lim(t[j], x, point, side)
                if K.N[v][0] in (K.CALL, K.DNE):
                    good = False
                    break
                terms.append(K.mul_(t[j + 1], [(v, K.ONE)]))
            if good:
                value = K.add_(terms)
                if value == K.UNDEF:
                    value = None
        if value is None:
            value = yield limits.g_lim(F, x, point, side)
    if K.N[value][0] == K.CALL and K.N[K.N[value][1]][1] == 'limit':
        value = None
    yield value



def g_defint(args, ctx):                                      #@L 2
    f, x, a, b = args
    if K.LST <= K.N[a][0] <= K.GE or K.LST <= K.N[b][0] <= K.GE:
        raise K.CasError(M_ARG)
    if K.N[f][0] == K.DIVG:
        yield f
        return
    if K.N[x][0] != K.SYM or not K.free_of(a, x) or not K.free_of(b, x):
        raise K.CasError(M_ARG)
    if a == b:
        yield K.ZERO
        return
    lo, hi = R.MODS['defb'].number(a), R.MODS['defb'].number(b)
    direction = K.ONE
    if lo is not None and hi is not None and lo > hi:
        a, b, lo, hi, direction = b, a, hi, lo, K.MONE
    numeric = lo is not None and hi is not None and not (K.V[f] & ~K.V[x])
    points = ()
    if numeric:
        points = yield R.MODS['defc'].g_points(f, x, lo, hi)
    integrand = R.MODS['norm'].normal(f, 1)
    integrator = R.need('int')
    primitive = yield R.scoped(integrator.g_int(integrand, x, 0))
    integrator = None
    R.drop(('int', 'int2b', 'int2', 'int3', 'int3b', 'fact'))
    exact = None
    if primitive is not None and primitive[1] == K.ZERO:
        F = primitive[0]
        if numeric:
            jumps = yield R.MODS['defc'].g_points(F, x, lo, hi)
            allpoints = []
            for p in points + jumps:
                v = R.MODS['defb'].number(p)
                if lo < v < hi and p not in allpoints:
                    allpoints.append(p)
            ordered = []
            for p in allpoints:
                ordered.append((R.MODS['defb'].number(p), p))
            ordered.sort()
            edges = [a]
            for v, p in ordered:
                edges.append(p)
            edges.append(b)
        else:
            edges = [a, b]
        total = []
        good = True
        for j in range(len(edges) - 1):
            left = yield g_endpoint(F, x, edges[j], 1)
            right = yield g_endpoint(F, x, edges[j + 1], -1)
            for value, endpoint in ((left, edges[j]), (right, edges[j + 1])):
                if value is None:
                    good = False
                elif value == K.OO or K.isninf(value) or K.N[value][0] == K.DNE:
                    reason = K.ZERO if endpoint == K.OO or K.isninf(endpoint) else K.ONE
                    yield K.mk((K.DIVG, reason))
                    return
            if left is not None and right is not None:
                total.append(K.add_([right, K.neg_(left)]))
        if good:
            exact = R.MODS['norm'].normal(K.add_(total))
    estimate = None
    if numeric:
        if exact is None:
            divergent = yield R.MODS['defc'].g_divergence(f, x, a, b, points)
            if divergent is not None:
                yield divergent
                return
        edges = [a]
        for p in points:
            if lo < R.MODS['defb'].number(p) < hi:
                edges.append(p)
        edges.append(b)
        values = []
        for j in range(len(edges) - 1) if R.MODS['defc'].safe_quad(f, x) else ():
            value = yield R.MODS['defb'].g_quad(f, x, edges[j], edges[j + 1], max(32, MAXEVAL // (len(edges) - 1)))
            if value is None:
                values = []
                break
            values.append(value)
        if values:
            estimate = K.add_(values)
    if exact is not None:
        ev, qv = R.MODS['defb'].number(exact), R.MODS['defb'].number(estimate) if estimate is not None else None
        if ev is not None and qv is not None and abs(ev - qv) > CHECKTOL * (1 + abs(qv)):
            exact = estimate
            R.FLAGS |= R.F_APPROX
        result = exact
    else:
        result = estimate
        if result is None:
            result = yield R.MODS['defb'].g_double(f, x, a, b)
        if result is not None:
            R.FLAGS |= R.F_APPROX
    if result is None:
        result = K.mk((K.CALL, K.sym('integrate'), f, x, a, b))
    yield K.mul_(direction, [(result, K.ONE)])
