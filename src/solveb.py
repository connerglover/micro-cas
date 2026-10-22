#@L 2
# CVSOLVE part b: one factor of an equation (DESIGN 11.2 steps 4-8). A polynomial in one kernel
# is solved by formula (degree 1, 2, and P(t^e) through s = t^e) or numerically (nroots, approx);
# its roots go through the kernel's inverse: the template table INV (9.3; one period [0, 2pi)
# for trig, D2, or [0, 360) in degree mode), exponentials b^u = T (u = ln T/ln b) and radicals
# u^(1/q) = T (u = T^q). Several kernels: a radical sqrt(A), abs(u) or sin(u) next to cos(u)
# is squared away; tan, sec, csc, cot and sin powers are rewritten to sin and cos (trigcos,
# trigsin); the rest is solved numerically. Guards with symbols hold (the generic
# solution, as giac).
import math

import node as K
import run as R

TWOPI = 2.0 * math.pi


def g_poly(cs):                                                 #@L 2
    # the values of t with sum(cs[i]*t^i) = 0 (the cs free of the unknown, cs[-1] != 0): in
    # s = t^e (e the exponent gcd) by formula for degree 1 and 2 (a negative discriminant has
    # no real root, D3; a symbolic one gives both roots, as giac), numerically (floats, approx) for
    # constant coefficients; then t = s^(1/e), +- for an even e (none for s < 0).
    NO = R.MODS['norm']
    e = 0
    for i in range(1, len(cs)):
        g = i if cs[i] != K.ZERO else 0
        while g:
            e, g = g, e % g
    d = []
    for i in range(0, len(cs), e):
        d.append(cs[i])
    ss = []
    if len(d) == 2:
        ss.append(K.add_([R.MODS['solvee'].tdiv(d[0], d[1])], K.MONE))
    elif len(d) == 3:
        D = NO.normal(K.add_([K.mul_(K.ONE, [(d[1], K.TWO)]),
                              K.mul_(K.num(-4), [(d[0], K.ONE), (d[2], K.ONE)])]))
        s = R.MODS['solvee'].nv(D, 1)
        q = K.mul_(K.ONE, [(D, K.HALF)])
        for u in (() if s == -1 else ((d[1],) if s == 0 else (K.add_([d[1], q]),
                                                                K.add_([d[1], K.neg_(q)])))):
            ss.append(K.mul_(K.num(-1, 0, 2), [(u, K.ONE), (d[2], K.MONE)]))
    else:
        fs = []
        for c in d:
            t = K.N[c]
            v = t[1] if t[0] == K.NUM and not t[2] and t[3] == 1 else R.MODS['solvee'].nv(c)
            if v is None:
                raise K.CasSoft('Cannot solve')
            fs.append(v)
        for v in R.MODS['factd'].nroots(fs):
            ss.append(K.flt(v))
    out = []
    for s in ss:
        if e > 1:                   # a constant as a sum: denest finds sqrt(2-sqrt(3))
            try:
                s = NO.normal(s, 0 if K.V[s] else 1)
            except K.CasError:
                pass
        g = 1 if e == 1 else R.MODS['solvee'].nv(s, 1)
        if e & 1 or g == 0:
            out.append(s if e == 1 or g == 0 else K.mul_(K.ONE, [(s, K.num(1, 0, e))]))
        elif g != -1:
            q = K.mul_(K.ONE, [(s, K.num(1, 0, e))])
            if e == 2:
                q = R.MODS['ident'].denest(q)
            out.append(K.neg_(q))
            out.append(q)
    yield out


def g_fac(G, ks, x, dep, md):                                   #@L 2
    # the candidate roots of the factor G (a polyc dict over the kernels ks) in x: a tuple,
    # K.TRUE, or a soft failure (see the module comment)
    FA = R.MODS['fact']
    SO = R.MODS['solve']
    nk = len(ks)
    use = [0] * nk
    for z in G:                                                 #@unordered-ok
        for i in range(nk):
            use[i] |= z[i]
    dp = []
    trig = 1
    for i in range(nk):
        if use[i] and not K.free_of(ks[i], x):
            dp.append(i)
            trig = trig and K.SIN <= K.N[ks[i]][0] <= K.COT
    if not dp:
        yield ()
        return
    if len(dp) == 1:
        j = dp[0]
        cs = []
        for c in R.MODS['polyc'].mcoef(G, j):
            cs.append(FA.mkpoly(c, ks, 1) if c else K.ZERO)
        ts = yield g_poly(cs)
        if ts is None or ks[j] == x:
            yield None if ts is None else tuple(ts)
            return
        out = []
        for T in ts:
            v = yield R.scoped(R.MODS['solvee'].g_inv(ks[j], T, x, dep + 1, md))
            if v is None or v == K.TRUE:
                out = v
                break
            out.extend(v)
        if out is not None:         # else: no inverse (x^x, floor(x), ...): numeric below
            yield out if out == K.TRUE else tuple(out)
            return
    for j in dp:                    # a radical r: sqrt(a), abs(u) (a = u^2), sin(u) next to
        k = K.N[ks[j]]              # cos(u) (a = 1-cos(u)^2): G = E+r*O, E, O in a = r^2;
        a = 0                       # square: E^2-a*O^2 = 0 (g_ok drops the extra roots)
        if k[0] == K.ABS:
            a = K.mul_(K.ONE, [(k[1], K.TWO)])
        elif k[0] == K.MUL and len(k) == 4 and k[3] == K.HALF:
            a = k[2]
        elif k[0] == K.SIN:
            c = K.fn_(K.COS, k[1])
            if c in ks and ks.index(c) in dp:
                a = K.add_([K.ONE, K.mul_(K.MONE, [(c, K.TWO)])])
        if a:
            E = {}
            O = {}
            for z in G:                                         #@unordered-ok
                w = list(z)
                w[j] = z[j] >> 1
                (O if z[j] & 1 else E)[tuple(w)] = G[z]
            k2 = ks[:j] + [a] + ks[j + 1:]
            E = FA.mkpoly(E, k2, 1) if E else K.ZERO
            if O:
                E = K.add_([K.mul_(K.ONE, [(E, K.TWO)]), K.mul_(K.MONE, [(a, K.ONE), (
                    FA.mkpoly(O, k2, 1), K.TWO)])])
            v = yield R.scoped(SO.g_eq(E, x, dep + 1, md))
            yield v
            return
    g = FA.mkpoly(G, ks, 1)
    if trig and not md & 2:         # sin, cos and tan powers of one argument: one kernel
        for nm in ('trigcos', 'trigsin'):
            h = yield R.MODS['rules'].g_rewrite(g, nm, 0, 64)
            if h is not None and h != g:
                v = yield R.scoped(SO.g_eq(h, x, dep + 1, md | 2))
                if v is not None:
                    yield v
                    return
    if K.V[g] != K.V[x]:
        raise K.CasSoft(SO.M_CANT)
    w = 360.0 if md & 1 else TWOPI
    out = []
    for v in R.MODS['solved'].nsolve(g, x, 0.0 if trig else -10.0, w if trig else 10.0):
        out.append(K.flt(v))
    yield tuple(out)
