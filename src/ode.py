#@L 2
# CVODE: first-order separation/linear equations and constant-coefficient second order.
import node as K
import alg as A
import run as R

MAXDEG = 6


def mul(a, b):                                                 #@L 4
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.ONE)])



def div(a, b):                                                 #@L 4
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.MONE)])



def power(a, b):                                               #@L 4
    return K.mul_(K.ONE, [(a, b)])



def exponential(u):                                            #@L 3
    # Integer powers of |u| in an integrating factor can use u on either domain interval.
    t = K.N[u]
    terms = [(u, K.ONE)] if t[0] != K.ADD else [(K.ONE, t[1])]
    if t[0] == K.ADD:
        for j in range(2, len(t), 2):
            terms.append((t[j], t[j + 1]))
    ps = []
    for e, c in terms:
        w = K.N[e]
        if w[0] == K.MUL and len(w) == 4 and w[3] == K.ONE:
            c = mul(c, w[1])
            e = w[2]
            w = K.N[e]
        if w[0] == K.LN:
            base = w[1]
            ct = K.N[c]
            if K.N[base][0] == K.ABS and ct[0] == K.NUM and ct[2] == 0 and ct[3] == 1:
                base = K.N[base][1]
            ps.append((base, c))
        else:
            ps.append((K.E, mul(e, c)))
    return K.mul_(K.ONE, ps)



def coefficients(f, x):                                        #@L 4
    d = A.degree(f, x)
    if d < 0 or d > MAXDEG:
        return None
    cs = A.pco(f, x, max(1, d))
    if cs is None:
        return None
    out = []
    for j in range(d + 1):
        ts = []
        for u, k in cs[j]:
            ts.append(K.add_([u], k))
        out.append(K.add_(ts))
    return out



def polynomial(cs, x):                                         #@L 3
    out = K.ZERO
    for j in range(len(cs) - 1, -1, -1):
        out = K.add_([mul(out, x), cs[j]])
    return out



def g_verify(sol, f, x, y, yp, ypp):                            #@L 2
    mark = K.NN
    DF = R.need('diff')
    NO = R.need('norm')
    t = K.N[sol]
    good = False
    try:
        if t[1] == y:
            d1 = yield DF.g_deriv(t[2], x)
            d2 = yield DF.g_deriv(d1, x)
            delta = A.subst(f, (y, yp, ypp), (t[2], d1, d2))
        else:
            implicit = K.add_([t[1], K.neg_(t[2])])
            dx = yield DF.g_deriv(implicit, x)
            dy = yield DF.g_deriv(implicit, y)
            delta = A.subst(f, yp, div(K.neg_(dx), dy))
        delta = NO.normal(delta)
        ok = yield R.MODS['normb'].g_iszero(delta)
        good = ok == R.MODS['normb'].YES or ok == A.LIKELY
    except K.CasSoft:
        good = False
    K.keep(mark, None)
    yield good



def g_desolve(args, ctx):                                       #@L 2
    x = args[1] if len(args) > 2 else K.sym('x')
    y = args[2] if len(args) > 2 else args[1] if len(args) > 1 else K.sym('y')
    if K.N[x][0] != K.SYM or K.N[y][0] != K.SYM or x == y:
        raise K.CasError('Expected independent and dependent variables')
    data = K.N[args[0]]
    eq = data[1] if data[0] == K.LST and len(data) > 1 else args[0]
    conds = data[2:] if data[0] == K.LST else ()
    if len(conds) > 6:
        raise K.CasError('Too many initial conditions')
    t = K.N[eq]
    f = K.add_([t[1], K.neg_(t[2])]) if t[0] == K.EQ else eq
    NO = R.need('norm')
    f = NO.normal(f, 1)
    yp, ypp = K.sym(K.N[y][1] + "'"), K.sym(K.N[y][1] + "''")
    c1, c2 = K.sym('C1'), K.sym('C2')
    out = None
    constants = (c1,)
    higher = False
    for e in A.postorder(f):
        z = K.N[e]
        if z[0] == K.SYM and z[1].rstrip("'") == K.N[y][1] and len(z[1]) > len(K.N[y][1]) + 2:
            higher = True
    if higher:
        yield K.mk(tuple([K.CALL, K.sym('desolve')] + list(args)))
        return
    if not K.free_of(f, ypp):
        out = yield R.MODS['odec'].g_second(f, x, y, yp, ypp, c1, c2)
        constants = (c1, c2)
    elif not K.free_of(f, yp):
        out = yield R.MODS['odeb'].g_first(f, x, y, yp, c1)
        lead = A.linear(f, yp)
        if out is not None and lead is not None and not K.free_of(lead[0], y):
            out = list(out)
            for root in R.MODS['odeb'].equilibria(lead[0], y):
                check = NO.normal(A.subst(f, (y, yp), (root, K.ZERO)))
                extra = K.rel_(K.EQ, y, root)
                if check == K.ZERO and extra not in out:
                    out.append(extra)
    results = []
    if out is not None:
        for sol in out:
            if conds:
                v = yield R.MODS['oded'].g_conditions(sol, conds, x, y, constants)
            else:
                v = sol
            if v is None:
                out = None
                break
            if K.N[v] != (K.LST,) and v not in results:
                good = yield g_verify(v, f, x, y, yp, ypp)
                if not good:
                    out = None
                    break
                results.append(v)
    if out is None:
        yield K.mk(tuple([K.CALL, K.sym('desolve')] + list(args)))
    elif len(results) == 1:
        yield results[0]
    else:
        if not results:
            R.FLAGS |= R.F_SOLN
        yield K.mk(tuple([K.LST] + results))
