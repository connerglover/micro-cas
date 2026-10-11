#@L 2
# CVINT: linearity, verified table primitives and bounded exact substitution.
# Every strategy returns (primitive, remainder), preserving f = primitive' + remainder.
import node as K
import alg as A
import parse as P
import run as R

EXTRA = (('int2', 'g_tabular'), ('int2', 'g_trig'), ('int2b', 'g_rational'),
         ('int3', 'g_advanced'), ('int3b', 'g_substitutions'))


def scale(c, f):                                                #@L 3
    return K.mul_(K.ONE, [(c, K.ONE), (f, K.ONE)])


def g_check(F, rest, f, x):                                      #@L 2
    m = K.NN
    d = yield R.MODS['diff'].g_deriv(F, x)
    delta = K.add_([d, rest, K.neg_(f)])
    ok = yield R.MODS['normb'].g_iszero(delta)
    K.keep(m, None)
    yield ok != A.NO


def g_table(f, x, depth=0):                                     #@L 2
    ru = R.MODS['rules']
    rs = ru.rset('itab')
    for pat, rhs, guard in rs.get(K.N[f][0], rs[ru.VIEW]):
        for alt in range(ru.MAXALT):
            env = [0] * P.NSLOT
            env[P.XSLOT] = x
            if not R.MODS['rulesb'].match(pat, f, env, x, alt):
                break
            ok = ru.guard_ok(guard, env)
            if type(ok) is tuple:
                ok = R.MODS['norm'].normal(ok[2]) == K.ZERO and ok[1] in (K.EQ, K.LE)
            if ok:
                F = P.inst(P.tcode(rhs), env)
                good = yield g_check(F, K.ZERO, f, x)
                if good:
                    yield (F, K.ZERO)
                    return
            yield R.TICK
    yield None


def g_usub(f, x, depth=0):                                      #@L 2
    if depth >= 3:
        yield None
        return
    # An unused symbol, even when the input already contains our private names.
    ns = 1
    temp = K.sym('_u%d' % ns)
    while not K.free_of(f, temp):
        ns += 1
        temp = K.sym('_u%d' % ns)
    for u in A.postorder(f):
        if u == x or u == f or K.free_of(u, x) or A.linear(u, x) is not None:
            continue
        m = K.NN
        du = yield R.MODS['diff'].g_deriv(u, x)
        if du == K.ZERO:
            K.keep(m, None)
            continue
        q = K.mul_(K.ONE, [(f, K.ONE), (du, K.MONE)])
        q = R.MODS['norm'].normal(q)
        q = A.subst(q, u, temp)
        if K.free_of(q, x):
            v = yield g_int(q, temp, depth + 1)
            if v is not None and v[1] == K.ZERO:
                F = A.subst(v[0], temp, u)
                good = yield g_check(F, K.ZERO, f, x)
                if good:
                    yield K.keep(m, (F, K.ZERO))
                    return
        K.keep(m, None)
        yield R.TICK
    yield None


def g_int(f, x, depth=0):                                       #@L 2
    if K.free_of(f, x):
        yield (scale(f, x), K.ZERO)
        return
    c, v = A.split_const(f, x)
    t = K.N[v]
    if t[0] == K.ADD:
        fs = [scale(t[1], x)]
        rests = []
        for j in range(2, len(t), 2):
            r = yield R.scoped(R.MODS['int'].g_int(t[j], x, depth))
            if r is None:
                r = (K.ZERO, t[j])
            fs.append(scale(t[j + 1], r[0]))
            rests.append(scale(t[j + 1], r[1]))
        yield (scale(c, K.add_(fs)), scale(c, K.add_(rests)))
        return
    r = yield R.scoped(g_table(v, x, depth))
    if r is None:
        r = yield R.scoped(g_usub(v, x, depth))
    if r is None:
        for key, name in EXTRA:
            mod = R.need(key)
            r = yield R.scoped(getattr(mod, name)(v, x, depth))    #@calls 2
            if r is not None:
                good = yield g_check(r[0], r[1], v, x)
                if good:
                    break
                r = None
            mod = None
            R.drop((key,))
    if r is None:
        r = (K.ZERO, v)
    yield (scale(c, r[0]), scale(c, r[1]))


def g_integrate(args, ctx):                                     #@L 2
    f = args[0]
    if len(args) == 3:
        raise K.CasError('invalid argument')
    x = args[1] if len(args) > 1 else K.sym('x')
    if K.N[x][0] != K.SYM:
        raise K.CasError('invalid argument')
    ctx[P.X_MV] = x
    if len(args) == 4:
        r = yield R.need('def').g_defint(args, ctx)               #@calls 2
        yield r
        return
    r = yield g_int(f, x, 0)
    if r is None:
        r = (K.ZERO, f)
    F, rest = r
    F = yield R.MODS['normb'].g_polish(F, x, True)
    if rest != K.ZERO:
        F = K.add_([F, K.mk((K.CALL, K.sym('integrate'), rest, x))])
    yield F
