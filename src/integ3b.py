#@L 2
# Last-resort rational trigonometric and exponential substitutions.
import node as K
import alg as A
import run as R


def g_substitutions(f, x, depth=0):                             #@L 2
    if depth >= 2:
        yield None
        return
    t = K.sym('_weier')
    if not K.free_of(f, t):
        yield None
        return
    u = None
    functions = []
    for n in A.postorder(f):
        z = K.N[n]
        if K.SIN <= z[0] <= K.COT and not K.free_of(z[1], x):
            if u is not None and u != z[1]:
                yield None
                return
            u = z[1]
            functions.append(n)
    if u is not None:
        ab = A.linear(u, x)
        if ab is None or ab[0] == K.ZERO:
            yield None
            return
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
                yield (A.subst(r[0], t, back), K.ZERO)
                return
    # A single exponential kernel leaves a rational function of the new variable.
    for n in A.postorder(f):
        z = K.N[n]
        if z[0] != K.MUL or len(z) != 4 or z[1] != K.ONE or z[2] != K.E:
            continue
        ab = A.linear(z[3], x)
        if ab is None or ab[0] == K.ZERO:
            continue
        q = A.subst(f, n, t)
        if not K.free_of(q, x):
            continue
        q = K.mul_(K.ONE, [(q, K.ONE), (ab[0], K.MONE), (t, K.MONE)])
        q = R.MODS['norm'].normal(q)
        r = yield R.MODS['int'].g_int(q, t, depth + 1)
        if r is not None and r[1] == K.ZERO:
            yield (A.subst(r[0], t, n), K.ZERO)
            return
    yield None
