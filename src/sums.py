#@L 2
# CVSUM: bounded exact sums, discrete antiderivatives and Riemann sums.
import node as K
import alg as A
import run as R

MAXTERMS = 1000
MAXDEG = 12
ZETA = (6, 90, 945, 9450)


def mul(a, b):                                                 #@L 4
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.ONE)])



def div(a, b):                                                 #@L 4
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.MONE)])



def power(a, b):                                               #@L 4
    return K.mul_(K.ONE, [(a, b)])



def integer(e):                                                #@L 7
    t = K.N[e]
    return t[1] if t[0] == K.NUM and t[2] == 0 and t[3] == 1 else None



def choose(n, k):                                              #@L 7
    r = 1
    for j in range(1, k + 1):
        r = r * (n - j + 1) // j
    return r



def coefficients(f, x):                                        #@L 4
    d = A.degree(f, x)
    if d < 0 or d > MAXDEG:
        return None
    cs = A.pco(f, x, max(d, 1))
    if cs is None:
        return None
    out = []
    for j in range(d + 1):
        ts = []
        for u, c in cs[j]:
            ts.append(K.add_([u], c))
        out.append(K.add_(ts))
    return out



def polynomial(cs, x):                                         #@L 3
    out = K.ZERO
    for j in range(len(cs) - 1, -1, -1):
        out = K.add_([mul(out, x), cs[j]])
    return out



def discrete(cs, r):                                           #@L 3
    # r*P(k+1)-P(k)=Q(k); r=1 gives the triangular Faulhaber system.
    q = list(cs)
    out = [K.ZERO] * (len(cs) + (1 if r == K.ONE else 0))
    for p in range(len(q) - 1, -1, -1):
        i = p + 1 if r == K.ONE else p
        den = K.num(i) if r == K.ONE else K.add_([r, K.MONE])
        v = div(q[p], den)
        out[i] = v
        for j in range(p):
            z = mul(K.num(-choose(i, j)), v)
            if r != K.ONE:
                z = mul(z, r)
            q[j] = K.add_([q[j], z])
    return out



def split_geo(f, x):                                           #@L 3
    t = K.N[f]
    pairs = t[2:] if t[0] == K.MUL else (f, K.ONE)
    ps = []
    ratio = K.ONE
    for j in range(0, len(pairs), 2):
        b, e = pairs[j], pairs[j + 1]
        ln = A.linear(e, x) if K.free_of(b, x) else None
        if ln is not None and ln[0] != K.ZERO:
            ratio = mul(ratio, power(b, ln[0]))
            if ln[1] != K.ZERO:
                ps.append((b, ln[1]))
        else:
            ps.append((b, e))
    return ratio, K.mul_(t[1] if t[0] == K.MUL else K.ONE, ps)



def g_sum(args, ctx):                                           #@L 2
    f, x = args[:2]
    if K.N[x][0] != K.SYM:
        raise K.CasError('sum index must be a variable')
    if len(args) != 4:
        yield K.mk(tuple([K.CALL, K.sym('sum')] + list(args)))
        return
    a, b = args[2:]
    if not K.free_of(a, x) or not K.free_of(b, x):
        raise K.CasError('sum bounds depend on the index')
    lo, hi = integer(a), integer(b)
    if K.N[a][0] == K.NUM and lo is None or K.N[b][0] == K.NUM and hi is None:
        raise K.CasError('sum bounds must be integers')
    if f == K.ZERO or lo is not None and hi is not None and hi < lo:
        out = K.ZERO
    elif lo is not None and hi is not None and hi - lo < MAXTERMS:
        out = yield R.MODS['sumb'].g_loop(f, x, lo, hi)
    elif b == K.OO:
        out = yield R.MODS['sumc'].g_infinite(f, x, a)
    else:
        out = yield R.MODS['sumb'].g_finite(f, x, a, b)
    if out is None:
        out = K.mk(tuple([K.CALL, K.sym('sum')] + list(args)))
    yield out



def g_riemann(args, ctx):                                       #@L 2
    f, x, a, b, n = args[:5]
    if K.N[x][0] != K.SYM or not K.free_of(a, x) or not K.free_of(b, x):
        raise K.CasError('expected a variable and constant bounds')
    count = integer(n)
    if count is not None and (count < 1 or count > MAXTERMS):
        raise K.CasError('Riemann panels must be from 1 to 1000')
    if count is None and K.N[n][0] != K.SYM:
        raise K.CasError('Riemann panels must be an integer or variable')
    method = 'right'
    if len(args) > 5:
        t = K.N[args[5]]
        method = t[1] if t[0] == K.SYM else ''
    if method not in ('left', 'right', 'mid', 'trap'):
        raise K.CasError('expected left, right, mid or trap')
    NO = R.need('norm')
    dx = div(K.add_([b, K.neg_(a)]), n)
    index = K.sym('_riemann')
    while not K.free_of(f, index) or index == n:
        index = K.sym(K.N[index][1] + '_')
    offset = K.MONE if method == 'left' else K.num(-1, 0, 2) if method == 'mid' else K.ZERO
    point = K.add_([a, mul(K.add_([index, offset]), dx)])
    term = mul(A.subst(f, x, point), dx)
    if count is not None:
        out = yield R.MODS['sumb'].g_loop(term, index, 1, count)
    else:
        out = yield R.MODS['sumb'].g_finite(term, index, K.ONE, n)
    if out is not None and method == 'trap':
        ends = K.add_([A.subst(f, x, a), K.neg_(A.subst(f, x, b))])
        out = K.add_([out, K.mul_(K.HALF, [(dx, K.ONE), (ends, K.ONE)])])
    if out is None:
        out = K.mk(tuple([K.CALL, K.sym('riemann')] + list(args)))
    else:
        out = NO.normal(out)
    yield out
