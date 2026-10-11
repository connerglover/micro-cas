#@L 2
# CVSOLVE part a: the solve command (DESIGN 11.2; alg 2.10). solve(eq, [x]) gives the list
# x=r1, ... of the real roots, the empty list (no solution) or TRUE (every x); a list of
# equations goes to the system solver (part c). g_eq finds the candidate roots: normal, then
# the numerator's factors over Q in their kernels (factor.terms, g_mfac), each solved by part b
# (polynomials by formula, kernels by their inverse, radicals by squaring, numeric last).
# g_roots checks every candidate against the equation (11.2) and sorts them.
import node as K
import alg as A
import parse as P
import run as R

MAXDEP = 8          # nested sub-solves (kernel inverses, squaring, rewrites, elimination)
MAXROOTS = 24       # roots of one equation, solutions of one system
M_CANT = 'cannot solve'
M_MANY = 'too many solutions'
M_ARG = 'invalid argument'


def nd(r):                                                      #@L 4
    # (numerator, denominator) of the normal form r = k*N/D: the pairs with a negative
    # rational exponent make D
    t = K.N[r]
    if t[0] != K.MUL:
        return (r, K.ONE)
    a = []
    b = []
    for j in range(2, len(t), 2):
        w = K.N[t[j + 1]]
        if w[0] == K.NUM and not w[2] and w[1] < 0:
            b.append((t[j], K.num(-w[1], 0, w[3])))
        else:
            a.append((t[j], t[j + 1]))
    return (K.mul_(t[1], a), K.mul_(K.ONE, b))


def syms(e):                                                    #@L 6
    # the symbols of e (an id or a flat tuple), in name order
    s = []
    for m in A.postorder(e):
        if K.N[m][0] == K.SYM:
            s.append((K.N[m][1], m))
    s.sort()
    out = []
    for n, m in s:
        out.append(m)
    return out


def g_solve(args, ctx):                                         #@L 2
    # solve(eq, [x]); solve([eqs], [vars]). A relation other than = cannot be solved; an
    # expression means expr = 0; with no variable, the only symbol, else x (giac, FlowCE).
    # Sets the main variable of the display. TRUE and FALSE are the folded relations (8.2).
    e = args[0]
    v = args[1] if len(args) > 1 else 0
    md = 1 if ctx[P.X_DEG] else 0
    t = K.N[e]
    vt = K.N[v] if v else None
    if vt is not None and vt[0] == K.LST and len(vt) == 2:
        v = vt[1]
        vt = K.N[v]
    if t[0] == K.LST and len(t) == 2 and (vt is None or vt[0] != K.LST):
        e = t[1]
        t = K.N[e]
    if t[0] == K.LST or (vt is not None and vt[0] == K.LST):
        r = yield R.MODS['solvec'].g_sys(e, v, md)
        yield r
        return
    if K.NE <= t[0] <= K.LE:
        raise K.CasSoft(M_CANT)
    f = K.add_([t[1], K.neg_(t[2])]) if t[0] == K.EQ else e
    if not v:
        v = syms(f)
        v = v[0] if len(v) == 1 else K.sym('x')
    if K.N[v][0] != K.SYM:
        raise K.CasError(M_ARG)
    ctx[P.X_MV] = v
    if e == K.FALSE or e == K.TRUE:
        yield e if e == K.TRUE else K.mk((K.LST,))
        return
    r = yield g_roots(f, v, md)
    if r is None or r == K.TRUE:
        yield r
        return
    out = [K.LST]
    for x in r:
        out.append(K.rel_(K.EQ, v, x))
    yield K.mk(tuple(out))


def g_roots(f, x, md):                                          #@L 2
    # the real roots of f = 0 in x (md: 1 degree mode), checked and sorted (g_fin): a tuple
    # of ids; K.TRUE when every x is a root; None (a soft failure, LASTSOFT) when f cannot
    # be solved
    r = R.MODS['norm'].normal(f)
    d = nd(r)[1]
    rs = yield R.scoped(g_eq(r, x, 0, md))
    if rs is None or rs == K.TRUE:
        yield rs
        return
    ss = []
    for r in rs:
        ss.append((r,))
    ss = yield R.MODS['solved'].g_fin((f,), (d,) if d != K.ONE else (), (x,), ss)
    out = []
    for s in ss:
        out.append(s[0])
    yield tuple(out)


def g_eq(f, x, dep, md):                                        #@L 2
    # the candidate roots of f = 0 in x (unchecked): a tuple of ids, K.TRUE, or a soft
    # failure. md: 1 degree mode, 2 the trig rewrite was tried. normal -> k*N/D; each factor
    # of N that depends on x becomes a polyc dict over its kernels (factor.terms), is factored
    # over Q (g_mfac), and each factor is solved by solveb.g_fac. A factor that terms refuses
    # (Gaussian or float coefficients) is solved as a polynomial of degree <= 2 in x, or
    # numerically.
    if dep > MAXDEP:
        raise K.CasSoft(M_CANT)
    FA = R.MODS['fact']
    SB = R.MODS['solveb']
    r = R.MODS['norm'].normal(f)
    if r == K.ZERO:
        yield K.TRUE
        return
    t = K.N[r]
    prs = t[2:] if t[0] == K.MUL else (r, K.ONE)
    ks = []
    outs = []
    rs = []
    for j in range(0, len(prs), 2):
        b = prs[j]
        w = K.N[prs[j + 1]]
        if (w[0] == K.NUM and not w[2] and w[1] < 0) or (K.free_of(b, x) and
                                                         K.free_of(prs[j + 1], x)):
            continue
        if K.N[b][0] != K.ADD or w[0] != K.NUM or w[2] or w[3] != 1:
            b = K.mul_(K.ONE, [(b, prs[j + 1])])
        out = []
        if FA.terms(b, ks, out):
            outs.append(out)
            continue
        n = A.degree(b, x)
        q = A.quadratic(b, x) if 0 < n < 3 else None
        if q is None:
            if K.V[b] != K.V[x]:
                raise K.CasSoft(M_CANT)
            for v in R.MODS['solved'].nsolve(b, x, -10.0, 10.0):
                rs.append(K.flt(v))
        else:
            v = yield SB.g_poly([q[2], q[1], q[0]] if n == 2 else [q[2], q[1]])
            if v is None:
                return
            rs.extend(v)
    nv = len(ks)
    for out in outs:
        d = {}
        for p in out:
            z = tuple(p[1:] + [0] * (nv + 1 - len(p)))
            d[z] = d.get(z, 0) + p[0]
        a = yield R.MODS['factc'].g_mfac(d, nv)
        for G, m in a[2]:
            v = yield R.scoped(SB.g_fac(G, ks, x, dep, md))
            if v is None or v == K.TRUE:
                yield v
                return
            rs.extend(v)
            if len(rs) > MAXROOTS:
                raise K.CasSoft(M_MANY)
    yield tuple(rs)
