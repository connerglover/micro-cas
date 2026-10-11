#@L 2
# CVLIM: exact one-sided limits, bounded asymptotic strategies and numeric fallback.
import node as K
import alg as A
import parse as P
import run as R

MAXLH = 4
MAXREWRITE = 3
SERORDER = 4
NUMFIRST = 2
NUMLAST = 8
M_ARG = 'invalid argument'


def numeric(f, x, a, side):                                    #@L 3
    try:
        program = A.nprog(f, (x,))
        infinity = a == K.OO or K.isninf(a)
        center = 0.0 if infinity else A.nrun(A.nprog(a, ()), ())
        values = []
        for k in range(NUMFIRST, NUMLAST + 1):
            point = (-1 if K.isninf(a) else 1) * 10.0 ** k if infinity else center + side * 10.0 ** (-k)
            value = A.nrun(program, (point,))
            if A.LEFTREAL[0] or type(value) is complex or not -1e200 < value < 1e200:
                return None
            values.append(value)
        ds = []
        for j in range(1, len(values)):
            ds.append(values[j] - values[j - 1])
        tail = values[-1]
        if max(abs(ds[-1]), abs(ds[-2])) > 1e-6 * (1 + abs(tail)):
            return None
        for j in range(len(ds) - 3, len(ds)):
            if abs(ds[j]) > 0.85 * abs(ds[j - 1]) + 1e-13 * (1 + abs(tail)):
                return None
        if ds[-2] and ds[-1]:
            q = ds[-1] / ds[-2]
            if abs(q) < 0.85:
                tail += ds[-1] * q / (1 - q)
        return K.flt(tail)
    except K.CasSoft:
        return None



def g_one(f, x, a, side):                                      #@L 2
    f = yield R.MODS['limb'].g_piece(f, x, a, side)
    wrappers = []
    result = None
    for rewrite in range(MAXREWRITE + 1):
        result = yield R.MODS['limb'].g_fast(f, x, a, side)
        if result is None:
            result = yield R.MODS['limc'].g_growth(f, x, a, side)
        if result is None:
            result = yield R.MODS['limc'].g_osc(f, x, a, side)
        if result is None:
            result = yield R.MODS['limc'].g_ratio(f, x, a, side)
        if result is not None:
            break
        t = K.N[f]
        if t[0] == K.MUL and len(t) == 4 and not K.free_of(t[3], x) and rewrite < MAXREWRITE:
            wrappers.append(t[1])
            f = K.mul_(K.ONE, [(t[3], K.ONE), (K.fn_(K.LN, t[2]), K.ONE)])
        else:
            result = numeric(f, x, a, side)
            break
    while wrappers and result is not None:
        coefficient = wrappers.pop()
        if K.N[result][0] == K.DNE:
            break
        result = K.mul_(coefficient, [(K.E, result)])
    yield result



def g_lim(f, x, a, side=0):                                    #@L 2
    if K.LST <= K.N[a][0] <= K.GE:
        raise K.CasError(M_ARG)
    if K.N[x][0] != K.SYM or not K.free_of(a, x) or side not in (-1, 0, 1):
        raise K.CasError(M_ARG)
    if side or a == K.OO or K.isninf(a):
        r = yield R.scoped(g_one(f, x, a, side or 1))
    else:
        left = yield R.scoped(g_one(f, x, a, -1))
        right = yield R.scoped(g_one(f, x, a, 1))
        r = None
        if left is not None and right is not None:
            if left == right:
                r = left
            elif K.N[left][0] == K.DNE or K.N[right][0] == K.DNE:
                r = K.mk((K.DNE, K.UNDEF, K.UNDEF))
            elif K.N[left][0] == K.FLT and K.N[right][0] == K.FLT and abs(K.N[left][1] - K.N[right][1]) < 1e-7 * (1 + abs(K.N[left][1])):
                r = K.flt((K.N[left][1] + K.N[right][1]) * 0.5)
            else:
                r = K.mk((K.DNE, left, right))
    if r is None:
        args = (K.CALL, K.sym('limit'), f, x, a)
        if side:
            args += (K.num(side),)
        r = K.mk(args)
    yield r



def g_limit(args, ctx):                                        #@L 2
    f, x = args[0], args[1]
    t = K.N[x]
    direction = K.ZERO
    if t[0] == K.EQ:
        if len(args) > 3:
            raise K.CasError(M_ARG)
        x, a = t[1], t[2]
        if len(args) == 3:
            direction = args[2]
    else:
        if len(args) < 3:
            raise K.CasError(M_ARG)
        a = args[2]
        if len(args) == 4:
            direction = args[3]
    q = K.N[direction]
    if q[0] != K.NUM or q[2] or q[3] != 1 or q[1] not in (-1, 0, 1):
        raise K.CasError(M_ARG)
    ctx[P.X_MV] = x
    r = yield g_lim(f, x, a, q[1])
    yield r
