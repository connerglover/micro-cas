#@L 2
# ode helper family.
import node as K
import alg as A
import run as R

def g_primitive(f, x):                                          #@L 2
    IN = R.need('int')
    v = yield IN.g_int(f, x)
    IN = None
    R.drop(('int', 'int2b', 'int2', 'int3', 'int3b', 'fact'))
    yield v[0] if v is not None and v[1] == K.ZERO else None



def g_linear(r, q, x, c, implicit=None):                        #@L 2
    NO = R.need('norm')
    p = yield g_primitive(K.neg_(r), x)
    if p is None:
        yield None
        return
    mu = R.MODS['ode'].exponential(p)
    iq = yield g_primitive(NO.normal(R.MODS['ode'].mul(mu, q)), x)
    if iq is None:
        yield None
    elif implicit is not None:
        yield K.rel_(K.EQ, R.MODS['ode'].mul(mu, implicit), K.add_([iq, c]))
    else:
        yield NO.normal(R.MODS['ode'].div(K.add_([iq, c]), mu))



def equilibria(h, y):                                          #@L 3
    q = A.quadratic(h, y)
    if q is None:
        return ()
    a, b, c = q
    if a == K.ZERO:
        return (R.MODS['ode'].div(K.neg_(c), b),) if b != K.ZERO else ()
    d = K.add_([R.MODS['ode'].power(b, K.TWO), K.neg_(R.MODS['ode'].mul(K.num(4), R.MODS['ode'].mul(a, c)))])
    t = K.N[d]
    if t[0] != K.NUM or t[2] or t[1] < 0:
        return ()
    root = R.MODS['ode'].power(d, K.HALF)
    den = R.MODS['ode'].mul(K.TWO, a)
    return (R.MODS['ode'].div(K.add_([K.neg_(b), root]), den),
            R.MODS['ode'].div(K.add_([K.neg_(b), K.neg_(root)]), den))



def g_first(f, x, y, yp, c):                                    #@L 2
    NO = R.need('norm')
    lin = A.linear(f, yp)
    if lin is None or lin[0] == K.ZERO:
        yield None
        return
    g = NO.normal(R.MODS['ode'].div(K.neg_(lin[1]), lin[0]), 1)
    ln = A.linear(g, y)
    if ln is not None:
        v = yield g_linear(ln[0], ln[1], x, c)
        yield None if v is None else (K.rel_(K.EQ, y, v),)
        return
    gx, hy = A.split_const(g, y)
    if not K.free_of(hy, x):
        for value in (K.ZERO, K.ONE, K.TWO):
            try:
                candidate = NO.normal(A.subst(g, y, value))
                if candidate != K.ZERO:
                    ratio = NO.normal(R.MODS['ode'].div(g, candidate))
                    if K.free_of(ratio, x):
                        gx, hy = candidate, ratio
                        break
            except K.CasSoft:
                pass
    if K.free_of(hy, x):
        fy = yield g_primitive(R.MODS['ode'].power(hy, K.MONE), y)
        fx = yield g_primitive(gx, x)
        if fy is not None and fx is not None:
            rhs = K.add_([fx, c])
            t = K.N[fy]
            if t[0] == K.LN and (t[1] == y or K.N[t[1]] == (K.ABS, y)):
                sol = K.rel_(K.EQ, y, R.MODS['ode'].mul(c, R.MODS['ode'].exponential(fx)))
            elif t[0] == K.ATAN and t[1] == y:
                sol = K.rel_(K.EQ, y, K.fn_(K.TAN, rhs))
            else:
                sol = K.rel_(K.EQ, fy, rhs)
            out = [sol]
            if t[0] != K.LN or K.N[sol][1] != y:
                roots = list(equilibria(hy, y))
                try:
                    if A.subst(hy, y, K.ZERO) == K.ZERO and K.ZERO not in roots:
                        roots.append(K.ZERO)
                except K.CasSoft:
                    pass
                for root in roots:
                    eq = K.rel_(K.EQ, y, root)
                    if eq not in out:
                        out.append(eq)
            yield tuple(out)
            return
    # Bernoulli: y'=r(x)y+q(x)y^n, transformed by v=y^(1-n).
    t = K.N[g]
    ts = [g]
    if t[0] == K.ADD and t[1] == K.ZERO:
        ts = []
        for j in range(2, len(t), 2):
            ts.append(R.MODS['ode'].mul(t[j], t[j + 1]))
    rr, qq, nn = K.ZERO, K.ZERO, None
    for term in ts:
        k, h = A.split_const(term, y)
        ht = K.N[h]
        if h == y:
            rr = K.add_([rr, k])
        elif ht[0] == K.MUL and len(ht) == 4 and ht[2] == y:
            nt = K.N[ht[3]]
            if nt[0] != K.NUM or nt[2] or ht[3] in (K.ZERO, K.ONE) or (nn is not None and nn != ht[3]):
                nn = None
                break
            nn, qq = ht[3], K.add_([qq, k])
        else:
            nn = None
            break
    if nn is not None:
        m = K.add_([K.ONE, K.neg_(nn)])
        # Keep the integrating factor on the implicit left side: differentiation
        # then reproduces r*y+q*y^n directly, without solving away real branches.
        implicit = None if nn == K.TWO else R.MODS['ode'].power(y, m)
        v = yield g_linear(R.MODS['ode'].mul(m, rr), R.MODS['ode'].mul(m, qq), x, c, implicit)
        if v is not None:
            out = [K.rel_(K.EQ, y, R.MODS['ode'].power(v, K.MONE)) if nn == K.TWO else v]
            try:
                if NO.normal(A.subst(f, (y, yp), (K.ZERO, K.ZERO))) == K.ZERO:
                    out.append(K.rel_(K.EQ, y, K.ZERO))
            except K.CasSoft:
                pass
            yield tuple(out)
            return
    yield None
