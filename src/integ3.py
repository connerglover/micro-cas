#@L 2
# Bounded integration by parts and polynomial quadratic-radical reduction.
import node as K
import alg as A
import run as R


def power(a, b):                                                #@L 4
    return K.mul_(K.ONE, [(a, b)])


def mul(a, b):                                                  #@L 4
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.ONE)])


def div(a, b):                                                  #@L 4
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.MONE)])


def coeff(e, x, n=12):                                         #@L 3
    p = A.pco(e, x, n)
    if p is None:
        return None
    out = []
    for row in p:
        ts = []
        for u, c in row:
            ts.append(K.add_([u], c))
        out.append(K.add_(ts))
    while out and out[-1] == K.ZERO:
        out.pop()
    return out


def g_radical(f, x, depth=0):                                  #@L 2
    t = K.N[f]
    if t[0] != K.MUL:
        yield None
        return
    for j in range(2, len(t), 2):
        q, pw = t[j], K.N[t[j + 1]]
        if pw[0] != K.NUM or pw[2] or pw[3] != 2 or pw[1] not in (-1, 1):
            continue
        abc = A.quadratic(q, x)
        if abc is None:
            continue
        a, b, c = abc
        sq = power(q, K.HALF)
        p = R.MODS['norm'].normal(mul(f, sq), 1)
        cs = coeff(p, x)
        if cs is None:
            continue
        if a == K.ZERO:
            if b == K.ZERO:
                continue
            u = K.sym('_rad')
            p = A.subst(p, x, div(K.add_([u, K.neg_(c)]), b))
            ps = coeff(R.MODS['norm'].normal(p, 1), u)
            if ps is None:
                continue
            out = []
            for k in range(len(ps)):
                exp = K.num(2 * k + 1, 0, 2)
                out.append(div(mul(ps[k], power(q, exp)), mul(b, exp)))
            yield (K.add_(out), K.ZERO)
            return
        if K.V[a] or K.V[b] or K.V[c]:
            continue
        av = A.nev(a)
        z = K.add_([mul(K.TWO, mul(a, x)), b])
        if av > 0:
            sa = power(a, K.HALF)
            arg = K.add_([mul(K.TWO, mul(sa, sq)), z])
            j0 = div(K.fn_(K.LN, K.fn_(K.ABS, arg)), sa)
        else:
            disc = K.add_([power(b, K.TWO), K.neg_(mul(K.num(4), mul(a, c)))])
            if A.nev(disc) <= 0:
                continue
            arg = div(K.neg_(z), power(disc, K.HALF))
            j0 = div(K.fn_(K.ASIN, arg), power(K.neg_(a), K.HALF))
        js = [j0, div(K.add_([sq, K.neg_(mul(mul(b, K.HALF), j0))]), a)]
        for k in range(2, len(cs)):
            z = mul(power(x, K.num(k - 1)), sq)
            z = K.add_([z, K.neg_(mul(mul(K.num(2*k-1, 0, 2), b), js[k-1])),
                       K.neg_(mul(mul(K.num(k-1), c), js[k-2]))])
            js.append(div(z, mul(K.num(k), a)))
        out = []
        for k in range(len(cs)):
            out.append(mul(cs[k], js[k]))
        yield (K.add_(out), K.ZERO)
        return
    yield None


def g_parts(f, x, depth=0):                                    #@L 2
    if depth >= 4:
        yield None
        return
    t = K.N[f]
    if t[0] == K.MUL:
        pairs = []
        for j in range(2, len(t), 2):
            pairs.append((t[j], t[j+1]))
    else:
        pairs = [(f, K.ONE)]
    for b, p in pairs:
        if K.N[b][0] not in (K.LN, K.ASIN, K.ACOS, K.ATAN):
            continue
        u = power(b, p)
        dv = R.MODS['norm'].normal(div(f, u))
        v = yield R.MODS['int'].g_int(dv, x, depth + 1)
        if v is None or v[1] != K.ZERO:
            continue
        du = yield R.MODS['diff'].g_deriv(u, x)
        rest = R.MODS['norm'].normal(mul(v[0], du))
        if rest == f:
            continue
        ir = yield R.MODS['int'].g_int(rest, x, depth + 1)
        if ir is not None and ir[1] == K.ZERO:
            yield (K.add_([mul(u, v[0]), K.neg_(ir[0])]), K.ZERO)
            return
    # Closed cyclic parts for exp(a*x+b)*sin/cos(c*x+d).
    ex = trig = None
    for b, p in pairs:
        if b == K.E and A.linear(p, x) is not None:
            ex = p
        elif K.N[b][0] in (K.SIN, K.COS) and p == K.ONE:
            trig = b
    if ex is not None and trig is not None:
        a = A.linear(ex, x)[0]
        op, u = K.N[trig]
        lu = A.linear(u, x)
        if lu is not None:
            b = lu[0]
            ep = power(K.E, ex)
            if R.MODS['norm'].normal(div(f, mul(ep, trig))) == K.ONE:
                s, c = K.fn_(K.SIN, u), K.fn_(K.COS, u)
                v = K.add_([mul(a, s), K.neg_(mul(b, c))]) if op == K.SIN else K.add_([mul(a, c), mul(b, s)])
                yield (div(mul(ep, v), K.add_([power(a, K.TWO), power(b, K.TWO)])), K.ZERO)
                return
    yield None


def g_advanced(f, x, depth=0):                                 #@L 2
    r = yield g_radical(f, x, depth)
    if r is None:
        r = yield g_parts(f, x, depth)
    yield r
