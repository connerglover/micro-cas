#@L 2
# Last-resort changes of variable: hyperbolic functions as exponentials, the half-angle
# substitution, and t = (a*x+b)^(1/n), x^n, e^(a*x), ln(x) or 1/x (integ3c builds those).
# g_int checks every primitive.
import node as K
import alg as A
import run as R


def g_substitutions(f, x, depth=0):                             #@L 2
    if depth >= 3:
        yield None
        return
    t = K.sym(('_weier', '_weies', '_weiet')[depth])    # a nested change: a name of its own
    if not K.free_of(f, t):
        yield None
        return
    u = None
    functions = []
    hyp = []
    for n in A.postorder(f):
        z = K.N[n]
        if K.SINH <= z[0] <= K.TANH and not K.free_of(n, x):
            hyp.append(n)
        if K.SIN <= z[0] <= K.COT and not K.free_of(z[1], x):
            if u is not None and u != z[1]:
                u = 0                   # two angles: no half-angle substitution
            elif u != 0:
                u = z[1]
                functions.append(n)
    if hyp:
        new = []
        for n in hyp:
            z = K.N[n]
            p = K.mul_(K.ONE, [(K.E, z[1])])
            m = K.mul_(K.ONE, [(K.E, K.neg_(z[1]))])
            s = K.add_([p, K.neg_(m)])
            c = K.add_([p, m])
            new.append(K.mul_(K.ONE, [(s, K.ONE), (c, K.MONE)]) if z[0] == K.TANH else
                       K.mul_(K.HALF, [(s if z[0] == K.SINH else c, K.ONE)]))
        r = yield R.MODS['int'].g_int(A.subst(f, tuple(hyp), tuple(new)), x, depth + 1)
        R.MODS['int'].USUB[0] = -1          # for the steps: written as exponentials
        yield r if r is not None and r[1] == K.ZERO else None
        return
    ab = A.linear(u, x) if u else None
    if ab is not None and ab[0] != K.ZERO:
        tt = K.mul_(K.ONE, [(t, K.TWO)])
        den = K.add_([K.ONE, tt])
        sn = K.mul_(K.TWO, [(t, K.ONE), (den, K.MONE)])
        cs = K.mul_(K.ONE, [(K.add_([K.ONE, K.neg_(tt)]), K.ONE), (den, K.MONE)])
        q = f
        for n in functions:
            op = K.N[n][0]
            z = sn if op == K.SIN else cs
            if op == K.TAN or op == K.COT:
                z = K.mul_(K.ONE, [(sn, K.ONE if op == K.TAN else K.MONE),
                                  (cs, K.MONE if op == K.TAN else K.ONE)])
            elif op == K.SEC or op == K.CSC:
                z = K.mul_(K.ONE, [(cs if op == K.SEC else sn, K.MONE)])
            q = A.subst(q, n, z)
        if K.free_of(q, x):
            q = K.mul_(K.TWO, [(q, K.ONE), (ab[0], K.MONE), (den, K.MONE)])
            q = R.MODS['norm'].normal(q)
            r = yield R.MODS['int'].g_int(q, t, depth + 1)
            if r is not None and r[1] == K.ZERO:
                back = K.fn_(K.TAN, K.mul_(K.HALF, [(u, K.ONE)]))
                R.MODS['int'].USUB[0] = -2  # for the steps: the half-angle substitution
                yield (A.subst(r[0], t, back), K.ZERO)
                return
    for B, n in R.MODS['int3c'].cands(f, x):
        m = K.NN
        uq = yield R.MODS['int3c'].g_subs(f, x, B, n, t)
        if uq is not None:
            r = yield R.MODS['int'].g_int(uq[1], t, depth + 1)
            if r is not None and r[1] == K.ZERO:
                F = r[0]
                if B == K.E:            # t = e^(a*x) > 0: ln|t| is a*x
                    F = A.subst(F, K.fn_(K.LN, K.fn_(K.ABS, t)), K.N[uq[0]][3])
                elif uq[2]:             # sqrt(Q(t)) back to sqrt(B)/x
                    F = R.MODS['int3c'].repow(F, uq[2], x, -2, t, B)
                ok = []
                if B == x and n < 0:    # t^(1/n) back to x, never to (x^n)^(1/n)
                    F = R.MODS['int3c'].repow(F, t, x, -n, x)
                    v = K.mul_(K.ONE, [(t, K.num(1, 0, -n))])
                    for j in A.postorder(f):        # the roots of f, as they read in t
                        z = K.N[j]
                        for i in range(2, len(z), 2) if z[0] == K.MUL else ():
                            if K.N[z[i + 1]][0] != K.NUM or K.N[z[i + 1]][3] != 1:
                                ok.append(A.subst(z[i], x, v))
                bad = B == x and n < 0 or uq[2]
                if not (bad and R.MODS['int3c'].stray(F, t, ok)):
                    F = A.subst(F, t, uq[0])
                    if not (bad and R.MODS['int3c'].stray(F, 0)):
                        R.MODS['int'].USUB[0] = (B, n, f)   # read by the steps (sint)
                        yield K.keep(m, (F, K.ZERO))
                        return
        K.keep(m, None)
        yield R.TICK
    yield None
