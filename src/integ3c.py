#@L 2
# integ3b family: the changes of variable of g_substitutions, built and judged.
import node as K
import alg as A
import run as R


def repow(f, B, t, q, x, C=0):                                  #@L 3
    # f with every power B^r written as t^(r*q) (q an int), times C^r when C is given; or for
    # B = e every e^(k*q*x+b) as e^b*t^k (q the number id of the rate of t = e^(q*x), k an
    # integer)
    new = {}
    for n in A.postorder(f):
        z = K.N[n]
        if z[0] != K.MUL:
            m = A.rebuild(n, new)
        else:
            ps = []
            for j in range(2, len(z), 2):
                b, e = z[j], z[j + 1]
                w = K.N[e]
                if b != B:
                    b = new.get(b, b)
                    e = new.get(e, e)
                elif b != K.E:
                    if w[0] == K.NUM and not w[2]:
                        if C:
                            ps.append((C, e))
                        b, e = t, K.num(w[1] * q, 0, w[3])
                    else:
                        e = new.get(e, e)
                else:
                    lu = A.linear(e, x)
                    k = K.ZERO if lu is None else K.mul_(K.ONE, [(lu[0], K.ONE), (q, K.MONE)])
                    w = K.N[k]
                    if k != K.ZERO and w[0] == K.NUM and not w[2] and w[3] == 1:
                        ps.append((b, lu[1]))
                        b, e = t, k
                    else:
                        e = new.get(e, e)
                ps.append((b, e))
            m = K.mul_(z[1], ps)
        if m != n:
            new[n] = m
    return new.get(f, f)


def cands(f, x):                                                #@L 3
    # The changes of variable worth a try, as (B, n): B = e and n = (p, q), t = e^(p*x/q);
    # n > 0, t = B^(1/n) for B linear in x, or t = 1/x for B quadratic under a square root;
    # n < 0, t = x^(-n); n = 0, t = ln(x).
    rate = None
    rad = {}
    rec = []
    pw = []
    out = []
    t = K.N[f]
    for j in range(2, len(t), 2) if t[0] == K.MUL else ():
        w = K.N[t[j + 1]]
        if t[j] == x and w[0] == K.NUM and not w[2] and w[3] == 1 and w[1] > 0:
            pw.append(w[1] + 1)         # x^m dx is a multiple of d(x^(m+1))
    for n in A.postorder(f):
        z = K.N[n]
        if z[0] == K.LN and z[1] == x and not out:
            out.append((x, 0))
        for j in range(2, len(z), 2) if z[0] == K.MUL else ():
            b = z[j]
            w = K.N[z[j + 1]]
            if b == K.E:
                lu = A.linear(z[j + 1], x)
                w = K.N[lu[0]] if lu is not None else w
                if lu is not None and w[0] == K.NUM and not w[2] and w[1] and (
                        rate is None or abs(w[1]) * rate[1] < abs(rate[0]) * w[3]):
                    rate = (w[1], w[3])
            elif w[0] == K.NUM and not w[2]:
                if w[3] > 1:
                    lu = A.linear(b, x)
                    if lu is not None and lu[0] != K.ZERO:
                        g, h = rad.get(b, 1), w[3]
                        while h:
                            g, h = h, g % h
                        rad[b] = rad.get(b, 1) * w[3] // g
                    elif w[3] == 2 and A.quadratic(b, x) is not None and (b, 2) not in rec:
                        rec.append((b, 2))
                elif b == x and n != f and abs(w[1]) > 1 and abs(w[1]) not in pw:
                    pw.append(abs(w[1]))
    for b in sorted(rad):
        if rad[b] <= 6:
            out.append((b, rad[b]))
    if rate is not None:
        out.append((K.E, rate))
    pw.sort()
    for n in pw[:3]:
        if 1 < n <= 12:
            out.append((x, -n))
    return out + rec[:1]


def g_subs(f, x, B, n, t):                                      #@L 2
    # The change of variable (B, n) of cands: (u, q, Q) with t = u(x) and f dx = q dt, q free
    # of x; None when x stays. Q is 0, or for t = 1/x the quadratic with sqrt(B) = sqrt(Q)/t.
    # (A generator only for its level: the substitutions below need the frames.)
    Q = 0
    try:
        if B == K.E:
            a = K.num(n[0], 0, n[1])
            u = K.mul_(K.ONE, [(K.E, K.mul_(a, [(x, K.ONE)]))])
            q = K.mul_(K.ONE, [(repow(f, B, t, a, x), K.ONE), (a, K.MONE), (t, K.MONE)])
        elif n > 0 and A.linear(B, x) is None:
            a, b, c = A.quadratic(B, x)
            u = K.mul_(K.ONE, [(x, K.MONE)])
            Q = K.add_([K.mul_(K.ONE, [(c, K.ONE), (t, K.TWO)]),
                        K.mul_(K.ONE, [(b, K.ONE), (t, K.ONE)]), a])
            q = A.subst(repow(f, B, t, -2, x, Q), x, K.mul_(K.ONE, [(t, K.MONE)]))
            q = K.mul_(K.MONE, [(q, K.ONE), (t, K.num(-2))])
        elif n > 0:
            a, b = A.linear(B, x)
            u = K.mul_(K.ONE, [(B, K.num(1, 0, n))])
            v = K.add_([K.mul_(K.ONE, [(t, K.num(n))]), K.neg_(b)])
            q = A.subst(repow(f, B, t, n, x), x, K.mul_(K.ONE, [(v, K.ONE), (a, K.MONE)]))
            q = K.mul_(K.num(n), [(q, K.ONE), (t, K.num(n - 1)), (a, K.MONE)])
        elif n < 0:
            u = K.mul_(K.ONE, [(x, K.num(-n))])
            q = A.subst(f, x, K.mul_(K.ONE, [(t, K.num(1, 0, -n))]))
            q = K.mul_(K.num(1, 0, -n), [(q, K.ONE), (t, K.num(1 + n, 0, -n))])
        else:
            u = K.fn_(K.LN, x)
            v = K.mul_(K.ONE, [(K.E, t)])
            q = K.mul_(K.ONE, [(A.subst(f, x, v), K.ONE), (v, K.ONE)])
        q = R.MODS['norm'].normal(q)
        for m in A.postorder(q) if B == x and n < 0 else ():
            z = K.N[m]              # t = x^n must leave no root of t: that is x again
            for j in range(2, len(z), 2) if z[0] == K.MUL else ():
                if z[j] == t and K.N[z[j + 1]][3] != 1:
                    q = x
    except (K.CasSoft, K.CasError):
        q = x
    yield (u, q, Q) if K.free_of(q, x) else None


def stray(F, t, ok=()):                                         #@L 3
    # What a change that holds only for x > 0 must not leave in its primitive: a root of
    # something that holds t (t given) other than the roots ok, or an abs that no logarithm
    # wraps. Without them the primitive is an identity in x and the roots of f, true on either
    # side of 0.
    c = 0
    for n in A.postorder(F):
        z = K.N[n]
        if z[0] == K.ABS:
            c += 1
        elif z[0] == K.LN and K.N[z[1]][0] == K.ABS:
            c -= 1
        elif z[0] == K.MUL and t:
            for j in range(2, len(z), 2):
                w = K.N[z[j + 1]]
                if (w[0] != K.NUM or w[2] or w[3] != 1) and z[j] not in ok and not K.free_of(
                        z[j], t):
                    return True
    return c > 0
