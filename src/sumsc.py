#@L 2
# sums family: sumsc helpers.
import node as K
import alg as A
import run as R

def p_tail(p, b):                                              #@L 7
    # Euler-Maclaurin tail from b inclusive, four correction terms; p>1, b>=200.
    return (b ** (1.0 - p) / (p - 1.0) + 0.5 * b ** (-p) +       #@float-ok
            p * b ** (-p - 1.0) / 12.0 -                         #@float-ok
            p * (p + 1.0) * (p + 2.0) * b ** (-p - 3.0) / 720.0) #@float-ok



def g_infinite(f, x, a):                                        #@L 2
    NO = R.need('norm')
    lo = R.MODS['sum'].integer(a)
    if lo is None or lo < 0 or lo > R.MODS['sum'].MAXTERMS:
        yield None
        return
    A.subst(f, x, a)                     # an undefined starting term is never ignored
    r, q = R.MODS['sum'].split_geo(f, x)
    c, core = A.split_const(q, x)
    rt = K.N[r]
    rational = rt[0] == K.NUM and rt[2] == 0
    inside = rational and abs(rt[1]) < rt[3]
    base = 0
    total = None
    fac = K.fn_(K.FACT, x)
    factc = NO.normal(R.MODS['sum'].mul(q, fac))
    if K.free_of(factc, x):
        total = R.MODS['sum'].mul(factc, R.MODS['sum'].power(K.E, r))
    elif core == K.ONE and rational:
        if not inside:
            yield K.mk((K.DIVG, K.TWO))
            return
        total = R.MODS['sum'].div(c, K.add_([K.ONE, R.MODS['sum'].mul(K.MONE, r)]))
    elif core == R.MODS['sum'].power(x, K.MONE) and rational:
        base = 1
        if -rt[3] <= rt[1] < rt[3]:
            total = R.MODS['sum'].mul(K.neg_(c), K.fn_(K.LN, K.add_([K.ONE, K.neg_(r)])))
        elif r == K.ONE:
            yield R.MODS['sum'].mul(c, K.OO)
            return
        else:
            yield K.mk((K.DIVG, K.TWO))
            return
    elif core == x and inside:
        total = R.MODS['sum'].div(R.MODS['sum'].mul(c, r), R.MODS['sum'].power(K.add_([K.ONE, K.neg_(r)]), K.TWO))
    elif r == K.MONE:
        test = NO.normal(R.MODS['sum'].mul(q, K.add_([R.MODS['sum'].mul(K.TWO, x), K.ONE])))
        if K.free_of(test, x):
            total = K.mul_(K.num(1, 0, 4), [(test, K.ONE), (K.PI, K.ONE)])
    if total is None and r == K.ONE:
        t = K.N[core]
        if t[0] == K.MUL and len(t) == 4 and t[2] == x:
            w = K.N[t[3]]
            if w[0] == K.NUM and w[2] == 0 and w[1] < 0:
                base = 1
                if -w[1] <= w[3]:
                    yield R.MODS['sum'].mul(c, K.OO)
                    return
                if w[3] == 1 and -w[1] in (2, 4, 6, 8):
                    total = K.mul_(K.num(1, 0, R.MODS['sum'].ZETA[-w[1] // 2 - 1]),
                                   [(c, K.ONE), (K.PI, K.num(-w[1]))])
                elif lo >= 1 and K.N[c][0] == K.NUM and K.N[c][2] == 0 and -w[1] < 10000*w[3]:
                    p = -w[1] / w[3]                            #@float-ok
                    if p == 1.0:
                        yield None
                        return
                    v = 0.0
                    for j in range(lo, lo + 200):
                        v += j ** (-p)
                        if not j & 31:
                            yield R.TICK
                    v += p_tail(p, float(lo + 200))
                    R.FLAGS |= R.F_APPROX
                    yield K.flt(v * K.N[c][1] / K.N[c][3])        #@float-ok
                    return
    if total is not None:
        if lo < base:
            yield None
            return
        prefix = yield R.MODS['sumb'].g_loop(f, x, base, lo - 1)
        yield NO.normal(K.add_([total, K.neg_(prefix)]))
        return
    out = yield R.MODS['sumb'].g_telescoping(f, x, a, K.OO)
    if out is not None:
        yield out
        return
    LI = R.need('lim')
    if LI is not None:
        term = yield LI.g_lim(f, x, K.OO)
        # Only exact numeric limits certify this discrete divergence test.
        # Floating residuals, oscillation and unresolved constants do not.
        if term is not None and (K.N[term][0] == K.NUM and term != K.ZERO or term == K.OO or K.isninf(term)):
            yield K.mk((K.DIVG, K.TWO))
            return
    SE = R.MODS.get('ser')
    if SE is not None:
        lead = yield SE.g_series(f, x, K.OO, 0)
        if lead is not None and len(lead) > 1 and lead[0] <= 0:
            yield K.mk((K.DIVG, K.TWO))
            return
        if lead is not None and len(lead) > 1 and lead[0] == 1:
            ct = K.N[lead[1]]
            if ct[0] == K.NUM and ct[2] == 0:
                yield R.MODS['sum'].mul(K.ONE if ct[1] > 0 else K.MONE, K.OO)
                return
    yield None
