#@L 2
# ode helper family.
import node as K
import alg as A
import run as R

def realimag(e):                                               #@L 3
    # normal() leaves Gaussian numbers only in coefficients; all other kernels are real.
    t = K.N[e]
    if t[0] == K.NUM:
        return K.num(t[1], 0, t[3]), K.num(t[2], 0, t[3])
    if t[0] == K.MUL:
        c = K.N[t[1]]
        ps = []
        for j in range(2, len(t), 2):
            ps.append((t[j], t[j + 1]))
        return K.mul_(K.num(c[1], 0, c[3]), ps), K.mul_(K.num(c[2], 0, c[3]), ps)
    if t[0] == K.ADD:
        c = K.N[t[1]]
        re, im = [K.num(c[1], 0, c[3])], [K.num(c[2], 0, c[3])]
        for j in range(2, len(t), 2):
            c = K.N[t[j + 1]]
            re.append(R.MODS['ode'].mul(t[j], K.num(c[1], 0, c[3])))
            im.append(R.MODS['ode'].mul(t[j], K.num(c[2], 0, c[3])))
        return K.add_(re), K.add_(im)
    return e, K.ZERO



def g_particular(g, x, a, b, c):                                #@L 2
    NO = R.need('norm')
    g = NO.normal(g, 1)
    t = K.N[g]
    terms = [g]
    if t[0] == K.ADD:
        terms = [t[1]]
        for j in range(2, len(t), 2):
            terms.append(R.MODS['ode'].mul(t[j], t[j + 1]))
    out = []
    for term in terms:
        if term == K.ZERO:
            continue
        t = K.N[term]
        ps = t[2:] if t[0] == K.MUL else (term, K.ONE)
        rest = []
        alpha, beta, amp = K.ZERO, K.ZERO, K.ONE
        seen = False
        for j in range(0, len(ps), 2):
            base, exp = ps[j], ps[j + 1]
            bt = K.N[base]
            ln = A.linear(exp, x) if base == K.E else None
            trig = A.linear(bt[1], x) if bt[0] in (K.SIN, K.COS) and exp == K.ONE else None
            if ln is not None:
                alpha = K.add_([alpha, ln[0]])
                rest.append((K.E, ln[1]))
            elif trig is not None and not seen:
                beta = trig[0]
                re = K.fn_(K.COS if bt[0] == K.COS else K.SIN, trig[1])
                im = K.fn_(K.SIN if bt[0] == K.COS else K.COS, trig[1])
                amp = K.add_([re, R.MODS['ode'].mul(K.I if bt[0] == K.COS else K.neg_(K.I), im)])
                seen = True
            else:
                rest.append((base, exp))
        if K.N[alpha][0] != K.NUM or K.N[beta][0] != K.NUM:
            yield None
            return
        p = K.mul_(t[1] if t[0] == K.MUL else K.ONE, rest)
        cs = R.MODS['ode'].coefficients(NO.normal(R.MODS['ode'].mul(p, amp), 1), x)
        if cs is None:
            yield None
            return
        lam = K.add_([alpha, R.MODS['ode'].mul(K.I, beta)])
        l0 = NO.normal(K.add_([R.MODS['ode'].mul(a, R.MODS['ode'].power(lam, K.TWO)), R.MODS['ode'].mul(b, lam), c]))
        l1 = NO.normal(K.add_([R.MODS['ode'].mul(R.MODS['ode'].mul(K.TWO, a), lam), b]))
        shift = 0 if l0 != K.ZERO else 1 if l1 != K.ZERO else 2
        qs = [K.ZERO] * (len(cs) + shift + 2)
        for p in range(len(cs) - 1, -1, -1):
            rhs = cs[p]
            if shift < 1:
                rhs = K.add_([rhs, K.neg_(R.MODS['ode'].mul(R.MODS['ode'].mul(K.num(p + 1), l1), qs[p + 1]))])
            if shift < 2:
                rhs = K.add_([rhs, K.neg_(R.MODS['ode'].mul(R.MODS['ode'].mul(K.num((p + 1)*(p + 2)), a), qs[p + 2]))])
            den = l0 if shift == 0 else R.MODS['ode'].mul(K.num(p + 1), l1) if shift == 1 else R.MODS['ode'].mul(K.num((p + 1)*(p + 2)), a)
            qs[p + shift] = NO.normal(R.MODS['ode'].div(rhs, den))
        re, im = [], []
        for q in qs[:len(cs) + shift]:
            u, v = realimag(NO.normal(q, 1))
            re.append(u)
            im.append(v)
        ux, vx = R.MODS['ode'].polynomial(re, x), R.MODS['ode'].polynomial(im, x)
        wave = K.add_([R.MODS['ode'].mul(ux, K.fn_(K.COS, R.MODS['ode'].mul(beta, x))),
                       K.neg_(R.MODS['ode'].mul(vx, K.fn_(K.SIN, R.MODS['ode'].mul(beta, x))))])
        out.append(R.MODS['ode'].mul(R.MODS['ode'].exponential(R.MODS['ode'].mul(alpha, x)), wave))
        yield R.TICK
    yield NO.normal(K.add_(out))



def g_second(f, x, y, yp, ypp, c1, c2):                         #@L 2
    NO = R.need('norm')
    aa = A.linear(f, ypp)
    bb = A.linear(aa[1], yp) if aa is not None else None
    cc = A.linear(bb[1], y) if bb is not None else None
    if aa is None or bb is None or cc is None or aa[0] == K.ZERO:
        yield None
        return
    a, b, c = aa[0], bb[0], cc[0]
    for q in (a, b, c):
        if K.N[q][0] != K.NUM or K.N[q][2]:
            yield None
            return
    d = K.add_([R.MODS['ode'].power(b, K.TWO), K.neg_(R.MODS['ode'].mul(K.num(4), R.MODS['ode'].mul(a, c)))])
    alpha = R.MODS['ode'].div(K.neg_(b), R.MODS['ode'].mul(K.TWO, a))
    sign = K.N[d][1]
    if sign == 0:
        u = R.MODS['ode'].exponential(R.MODS['ode'].mul(alpha, x))
        v = R.MODS['ode'].mul(x, u)
    elif sign > 0:
        beta = R.MODS['ode'].div(R.MODS['ode'].power(d, K.HALF), R.MODS['ode'].mul(K.TWO, a))
        u = R.MODS['ode'].exponential(R.MODS['ode'].mul(K.add_([alpha, beta]), x))
        v = R.MODS['ode'].exponential(R.MODS['ode'].mul(K.add_([alpha, K.neg_(beta)]), x))
    else:
        beta = R.MODS['ode'].div(R.MODS['ode'].power(K.neg_(d), K.HALF), R.MODS['ode'].mul(K.TWO, K.fn_(K.ABS, a)))
        ex = R.MODS['ode'].exponential(R.MODS['ode'].mul(alpha, x))
        u = R.MODS['ode'].mul(ex, K.fn_(K.COS, R.MODS['ode'].mul(beta, x)))
        v = R.MODS['ode'].mul(ex, K.fn_(K.SIN, R.MODS['ode'].mul(beta, x)))
    yp0 = yield g_particular(K.neg_(cc[1]), x, a, b, c)
    if yp0 is None:
        yield None
    else:
        value = NO.normal(K.add_([R.MODS['ode'].mul(c1, u), R.MODS['ode'].mul(c2, v), yp0]))
        yield (K.rel_(K.EQ, y, value),)
