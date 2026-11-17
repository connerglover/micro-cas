#@L 2
# CVINT: linearity, verified table primitives and bounded exact substitution.
# Every strategy returns (primitive, remainder), preserving f = primitive' + remainder.
import node as K
import alg as A
import parse as P
import run as R

EXTRA = (('int2', 'g_tabular'), ('int2', 'g_trig'), ('int2b', 'g_rational'),
         ('int3', 'g_advanced'), ('int3b', 'g_substitutions'))
# The u of the last successful g_usub (an id inside its f), or the (B, n, f) of the last change
# of variable of integ3b (ids inside f, and numbers), or its -1 (hyperbolic functions written
# as exponentials) or -2 (the half-angle substitution): read by the steps (sint).
USUB = [0]


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
                    USUB[0] = u
                    yield K.keep(m, (F, K.ZERO))
                    return
        K.keep(m, None)
        yield R.TICK
    yield None


def fits(j, v, x):                                              #@L 3
    # a necessary condition of EXTRA[j], tested before its pack loads
    t = K.N[v]
    if j == 3:              # a square root, ln/asin/acos/atan, e^u with sin/cos, or a factor x
        g = 0
        for i in range(2, len(t), 2) if t[0] == K.MUL else ():
            b = K.N[t[i]][0]
            w = K.N[t[i + 1]]
            if (w[0] == K.NUM and w[3] == 2) or b == K.LN or K.ASIN <= b <= K.ATAN or (
                    t[i] == x and t[i + 1] == K.ONE):
                return True
            g |= 1 if t[i] == K.E else 2 if b == K.SIN or b == K.COS else 0
        return g == 3 or t[0] == K.LN or K.ASIN <= t[0] <= K.ATAN
    return True                         # j == 4, the changes of variable, judge for themselves


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
        j = -1
        for key, name in EXTRA:         # (this loop form is what build/shrink.py reads as a
            j += 1                      # registry walk: the getattr below renames with it)
            if j == 2:                  # rational: numbers and x only, once normalized
                q = R.MODS['norm'].normal(v)
                if R.MODS['normc'].kinds(q) & 2 or K.V[q] & ~K.V[x]:
                    continue
            elif not fits(j, v, x):
                continue
            mod = R.need(key)
            r = yield R.scoped(getattr(mod, name)(v, x, depth))    #@calls 2
            if r is not None:
                good = yield g_check(r[0], r[1], v, x)
                if good:
                    break
                r = None
            mod = None
            R.drop((key,), True)   # unpin; need() evicts LRU strategies only for memory
    if r is None and depth < 3:         # last: multiplied out, term by term (x*(e^x+1))
        try:
            q = R.MODS['norm'].normal(v, 1)
        except K.CasError:
            q = v
        if q != v and K.N[q][0] == K.ADD:
            r = yield R.scoped(R.MODS['int'].g_int(q, x, depth + 1))
            if r is not None and r[1] != K.ZERO:
                r = None
    if r is None:
        r = (K.ZERO, v)
    yield (scale(c, r[0]), scale(c, r[1]))


def stepped(f, x):                                              #@L 3
    # f holds a floor or ceil of x: neither has a primitive, so no search can succeed
    for n in A.postorder(f):
        if (K.N[n][0] == K.FLOOR or K.N[n][0] == K.CEIL) and not K.free_of(n, x):
            return True
    return False


def g_prim(args):                                               #@L 2
    # The primitive for a definite integral: g_int's pair, or None when there is none to look
    # for; defint.g_defint judges the arguments. A step integrand on finite numeric bounds skips
    # the search; on any other bounds its failure is what words the message.
    f, x, a, b = args
    if (K.N[f][0] == K.DIVG or K.N[x][0] != K.SYM or a == b or K.LST <= K.N[a][0] <= K.GE or
            K.LST <= K.N[b][0] <= K.GE or not K.free_of(a, x) or not K.free_of(b, x)):
        yield None
        return
    finite = not (K.V[a] or K.V[b] or K.V[f] & ~K.V[x] or a == K.OO or b == K.OO or
                  K.isninf(a) or K.isninf(b))
    if finite and stepped(f, x):
        yield None
        return
    r = yield R.scoped(g_int(R.MODS['norm'].normal(f, 1), x, 0))
    yield r


def g_integrate(args, ctx):                                     #@L 2
    f = args[0]
    if len(args) == 3:
        raise K.CasError('Invalid argument')
    x = args[1] if len(args) > 1 else K.sym('x')
    if K.N[x][0] != K.SYM:
        raise K.CasError('Invalid argument')
    ctx[P.X_MV] = x
    r = yield g_int(f, x, 0)
    if r is None:
        r = (K.ZERO, f)
    F, rest = r
    F = yield R.MODS['normb'].g_polish(F, x, True)
    if rest != K.ZERO:
        F = K.add_([F, K.mk((K.CALL, K.sym('integrate'), rest, x))])
    yield F
