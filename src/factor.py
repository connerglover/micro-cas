#@L 2
# CVFACT part a: the factor command (DESIGN 11.2; alg 2.8). An integer or a rational becomes a
# HOLD of its prime powers (5.2). Any other expression is brought to its normal form k*N/D
# (CVNORM); N and D become sparse polynomials over Z (polyc dicts) in their kernels: symbols,
# functions, radicals u^(1/q), powers with a symbolic exponent. Part c (factorc.py) factors
# each one (g_mfac); the factors are rebuilt with the constructors, which keep a product of
# sums. Factoring is over Q only, and the result never claims irreducibility: COMPLETE[0] is
# 1 when every factor of the last factor command is proven irreducible (for the tests).
import node as K
import alg as A
import parse as P
import run as R

TDIV = 1000000      # integer trial division bound (11.2): a cofactor above it stays one base
M_ARG = 'invalid argument'
COMPLETE = [1]


def terms(e, ks, out):                                          #@L 4
    # append the terms of the polynomial e (a sum or a monomial in kernels) to out, each a
    # list [c, p0, p1, ...]: an integer coefficient and the powers of the kernels ks (new
    # kernels are appended to ks; the lists are padded later). False if a coefficient is not
    # an integer (Gaussian or rational) or a kernel would be a number.
    t = K.N[e]
    ms = [(e, K.ONE)]
    if t[0] == K.ADD:
        ms = [(K.ONE, t[1])] if t[1] != K.ZERO else []
        for j in range(2, len(t), 2):
            ms.append((t[j], t[j + 1]))
    for m, c in ms:
        c = K.N[c]
        x = K.N[m]
        prs = (m, K.ONE)
        if x[0] == K.MUL:
            c = K.nmul(c, K.N[x[1]])
            prs = x[2:]
        elif x[0] == K.NUM:
            c = K.nmul(c, x)
            prs = ()
        if c[0] != K.NUM or c[2] or c[3] != 1:
            return False
        p = [c[1]] + [0] * len(ks)
        for j in range(0, len(prs), 2):
            b = prs[j]
            w = K.N[prs[j + 1]]
            n = 1
            if w[0] == K.NUM and not w[2] and w[1] > 0 and not (
                    K.HUGE and K.N[b][0] == K.NUM and (w[3] == 1 or not K.N[b][2] and
                                                       w[1] > w[3])):   # kept whole (nodeb.huge)
                n = w[1]
                if w[3] > 1:                                    # u^(n/q) = (u^(1/q))^n
                    b = K.mul_(K.ONE, [(b, K.num(1, 0, w[3]))])
            else:                       # b^(n*u) = (b^u)^n, n > 0; a power kept whole (6.1):
                y = K.N[w[1]] if w[0] == K.MUL else K.Q0                # one kernel, n = 1
                u = prs[j + 1]
                if y[0] == K.NUM and not y[2] and y[3] == 1 and y[1] > 1:
                    n = y[1]
                    u = w[2] if len(w) == 4 and w[3] == K.ONE else K.mk((K.MUL, K.ONE) + w[2:])
                b = K.mul_(K.ONE, [(b, u)])
            if K.N[b][0] <= K.FLT:
                return False
            if b not in ks:
                ks.append(b)
                p.append(0)
            p[ks.index(b) + 1] += n
        out.append(p)
    return True


def mkpoly(F, ks, dv):                                          #@L 4
    # the node of the polynomial F (a polyc dict over the kernels ks) divided by the int dv
    ts = []
    for z in F:                                                 #@unordered-ok (add_ sorts)
        ps = []
        for i in range(len(z)):
            if z[i]:
                ps.append((ks[i], K.num(z[i])))
        ts.append(K.mul_(K.nnorm(F[z], 0, dv), ps))
    return K.add_(ts)


def g_factor(args, ctx):                                        #@L 2
    # factor(e, [x]): x, a symbol, is the main variable of the display; a list or a relation
    # is factored element by element
    if len(args) > 1:
        if K.N[args[1]][0] != K.SYM:
            raise K.CasError(M_ARG)
        ctx[P.X_MV] = args[1]
    COMPLETE[0] = 1
    e = args[0]
    t = K.N[e]
    es = [e]
    if t[0] == K.LST or K.EQ <= t[0] <= K.LE:
        es = list(t[1:])
    out = [t[0]]
    for c in es:
        r = yield g_fac(c, ctx[P.X_APPROX])
        out.append(c if r is None else r)
    yield out[1] if len(es) == 1 and es[0] == e else K.mk(tuple(out))


def g_fac(e, ap):                                               #@L 2
    # one expression: k*N/D (normal) with N and D factored by part c. ap (the input had a
    # float, 6.3): every factor is made monic in its leading term, so that approx() prints
    # (x-0.5)*(x+0.5) rather than 0.25*(2.0*x-1.0)*(2.0*x+1.0)
    NO = R.MODS['norm']
    FC = R.MODS['factc']
    PC = R.MODS['polyc']
    for m in A.postorder(e):
        if K.N[m][0] == K.FLT or P.issent(m):
            yield e
            return
    r = NO.normal(e)
    t = K.N[r]
    if NO.GAVEUP[0] or t[0] == K.NUM:
        yield R.MODS['factd'].ifactor(t) if t[0] == K.NUM and not t[2] else r
        return
    k = K.Q1
    prs = [r, K.ONE]
    if t[0] == K.MUL:
        k = K.N[t[1]]
        prs = t[2:]
    ks = []
    tl = ([], [])                                   # (terms, power) per side: N, then D
    for j in range(0, len(prs), 2):
        b = prs[j]
        x = prs[j + 1]
        w = K.N[x]
        s = 1 if w[0] == K.NUM and not w[2] and w[1] < 0 else 0
        if s:
            x = K.num(-w[1], 0, w[3])
            w = K.N[x]
        n = 1
        if K.N[b][0] == K.ADD and w[0] == K.NUM and not w[2] and w[3] == 1:
            n = w[1]
        else:
            b = K.mul_(K.ONE, [(b, x)])
        out = []
        if not terms(b, ks, out):
            yield r
            return
        tl[s].append((out, n))
    nv = len(ks)
    pairs = []
    for s in (0, 1):
        F = {(0,) * nv: 1}
        for out, n in tl[s]:
            d = {}
            for p in out:
                z = tuple(p[1:] + [0] * (nv + 1 - len(p)))
                d[z] = d.get(z, 0) + p[0]
            F = PC.mmul(F, PC.mpow(d, n, nv))
        a, b, fs, comp = yield FC.g_mfac(F, nv)
        COMPLETE[0] &= comp
        for F, m in fs:
            dv = F[max(F)] if ap else 1                         #@unordered-ok (a max)
            a *= dv ** m
            pairs.append((mkpoly(F, ks, dv), K.num(-m if s else m)))
        k = K.nmul(k, K.nnorm(b, 0, a) if s else K.nnorm(a, 0, b))
    yield K.mul_(k, pairs)
