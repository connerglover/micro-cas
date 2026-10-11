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
