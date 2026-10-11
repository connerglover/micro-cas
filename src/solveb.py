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
import alg as A
import parse as P
import run as R

# f(u) = T -> u in INV[f][0] when the guard INV[f][1] holds (T is the rule slot P.TSLOT)
INV = {K.SIN: (('asin(T)', 'pi-asin(T)'), 'abs(T)<=1'),
       K.COS: (('acos(T)', '2*pi-acos(T)'), 'abs(T)<=1'),
       K.TAN: (('atan(T)', 'atan(T)+pi'), ''),
       K.SEC: (('acos(1/T)', '2*pi-acos(1/T)'), 'abs(T)>=1'),
       K.CSC: (('asin(1/T)', 'pi-asin(1/T)'), 'abs(T)>=1'),
       K.COT: (('pi/2-atan(T)', '3*pi/2-atan(T)'), ''),
       K.ASIN: (('sin(T)',), 'abs(T)<=pi/2'),
       K.ACOS: (('cos(T)',), 'T>=0,T<=pi'),
       K.ATAN: (('tan(T)',), 'abs(T)<pi/2'),
       K.SINH: (('ln(T+sqrt(T^2+1))',), ''),
       K.TANH: (('ln((1+T)/(1-T))/2',), 'abs(T)<1'),
       K.LN: (('e^T',), ''),
       K.ABS: (('T', '-T'), 'T>=0')}
TWOPI = 2.0 * math.pi


def nv(T, s=0):                                                 #@L 3
    # the float value of the constant T, or (s) its sign 1, -1, 0 (T is ZERO); None when T
    # has symbols, is not real, or its sign is too close to 0 to tell
    t = K.N[T]
    if T == K.ZERO:
        return 0
    if s and t[0] == K.NUM:
        return None if t[2] else K.nsign(t)
    if K.V[T]:
        return None
    try:
        p = A.nprog(T, ())
        r = [0.0] * len(p)
        v = A.nrun(p, (), r)
        w = A.ntol(p, r, [0.0] * len(p))
    except K.CasSoft:
        return None
    if type(v) is complex or w < 0.0:
        return None
    if not s:
        return v
    return 1 if v > w else (-1 if v < -w else None)


def tdiv(n, d):                                                 #@L 4
    # n/d, a sum divided term by term: pi/6-y, 180-asin(1/3) in degree mode, not
    # (pi-6*y)/6 and (180*pi-pi*asin(1/3))/pi (a rational root is put in lowest terms later)
    z = K.N[n]
    if z[0] != K.ADD:
        return K.mul_(K.ONE, [(n, K.ONE), (d, K.MONE)])
    ts = [K.mul_(K.ONE, [(z[1], K.ONE), (d, K.MONE)])]
    for j in range(2, len(z), 2):
        ts.append(K.mul_(z[j + 1], [(z[j], K.ONE), (d, K.MONE)]))
    return K.add_(ts)


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
        ss.append(K.add_([tdiv(d[0], d[1])], K.MONE))
    elif len(d) == 3:
        D = NO.normal(K.add_([K.mul_(K.ONE, [(d[1], K.TWO)]),
                              K.mul_(K.num(-4), [(d[0], K.ONE), (d[2], K.ONE)])]))
        s = nv(D, 1)
        q = K.mul_(K.ONE, [(D, K.HALF)])
        for u in (() if s == -1 else ((d[1],) if s == 0 else (K.add_([d[1], q]),
                                                                K.add_([d[1], K.neg_(q)])))):
            ss.append(K.mul_(K.num(-1, 0, 2), [(u, K.ONE), (d[2], K.MONE)]))
    else:
        fs = []
        for c in d:
            t = K.N[c]
            v = t[1] if t[0] == K.NUM and not t[2] and t[3] == 1 else nv(c)
            if v is None:
                raise K.CasSoft('cannot solve')
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
        g = 1 if e == 1 else nv(s, 1)
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
            v = yield R.scoped(g_inv(ks[j], T, x, dep + 1, md))
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
    for v in R.MODS['solvec'].nsolve(g, x, 0.0 if trig else -10.0, w if trig else 10.0):
        out.append(K.flt(v))
    yield tuple(out)


def g_inv(k, T, x, dep, md):                                    #@L 2
    # the candidate roots in x of the kernel equation k = T (see the module comment)
    SO = R.MODS['solve']
    t = K.N[k]
    if t[0] == K.MUL and len(t) == 4:
        u = t[2]
        w = K.N[t[3]]
        if K.free_of(u, x):                             # u^v = T: v = ln(T)/ln(u), T > 0
            s = nv(T, 1)
            if K.csign(u) < 0 or (s is not None and s < 1):
                yield ()
                return
            ws = [K.fn_(K.LN, T)]
            if u != K.E:
                ws[0] = K.mul_(K.ONE, [(ws[0], K.ONE), (K.fn_(K.LN, u), K.MONE)])
            u = t[3]
        elif w[0] == K.NUM and w[1] == 1 and not w[2] and w[3] > 1:     # u^(1/q) = T
            if not w[3] & 1 and nv(T, 1) == -1:
                yield ()
                return
            ws = [K.mul_(K.ONE, [(T, K.num(w[3]))])]
        else:
            raise K.CasSoft(SO.M_CANT)
    else:
        ent = INV.get(t[0])
        if ent is None:
            raise K.CasSoft(SO.M_CANT)
        u = t[1]
        env = [0] * P.NSLOT
        env[P.TSLOT] = T
        if not K.V[T]:                  # the sum form of a constant: fn_ finds special values
            try:
                env[P.TSLOT] = R.MODS['norm'].normal(T, 1)
            except K.CasError:
                pass
        ok = R.MODS['rules'].guard_ok('~' + ent[1], env) if ent[1] else 1
        if type(ok) is tuple:                           # near 0: the exact test (9.7)
            ok = R.MODS['norm'].normal(ok[2]) == K.ZERO and (ok[1] == K.EQ or ok[1] == K.LE)
        if not ok:
            yield ()
            return
        ws = []
        for s in ent[0]:
            ws.append(P.inst(P.tcode(s), env))
        ab = A.linear(u, x) if K.SIN <= t[0] <= K.COT else None
        a = nv(ab[0]) if ab is not None and ab[0] != K.ZERO else None
        b = nv(ab[1]) if a else None
        cs = []
        for w in ws:
            cs.append(nv(w))
        if b is not None and None not in cs:    # u = a*x+b, all constant: x in [0, 2pi) (D2)
            p = TWOPI / abs(a)                                          #@float-ok
            m = 1 if a > 0 else -1
            W = 360.0 if md & 1 else TWOPI
            out = []
            for i in range(len(ws)):
                w = ws[i]
                c = (cs[i] - b) / a                                     #@float-ok
                j = int(math.ceil(-c / p - 1e-9))                       #@float-ok
                q = tdiv(K.add_([w, K.neg_(ab[1])]), ab[0])
                while c + j * p < W * (1.0 - 1e-12) - 1e-12:
                    out.append(K.add_([q, K.mul_(K.num(2 * j * m), [(K.PI, K.ONE),
                                                                    (ab[0], K.MONE)])]))
                    j += 1
                    if len(out) > SO.MAXROOTS:
                        raise K.CasSoft(SO.M_MANY)
            yield tuple(out)
            return
    out = []
    for w in ws:
        v = yield R.scoped(SO.g_eq(K.add_([u, K.neg_(w)]), x, dep, md))
        if v is None or v == K.TRUE:
            yield v
            return
        out.extend(v)
    yield tuple(out)
