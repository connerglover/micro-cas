#@L 2
# CVSER: iterative truncated Taylor/Laurent arithmetic; coefficients are node ids.
import node as K
import alg as A
import run as R

MAXORDER = 20
MAXWORK = 40
EXP = 0


def g_fold(f, x, a, n, side):                                   #@L 2
    values = {}
    NO = R.need('norm')
    neginf = K.mul_(K.MONE, [(K.OO, K.ONE)])
    for e in A.postorder(f):
        t = K.N[e]
        op = t[0]
        if e == x:
            if a == K.OO or a == neginf:
                s = tuple([-1, K.MONE if a == neginf else K.ONE] + [K.ZERO] * n)
            else:
                s = R.MODS['serb'].pack(0, [a, K.ONE] + [K.ZERO] * max(0, n - 1))
        elif K.free_of(e, x):
            s = R.MODS['serb'].const(e, n)
        elif op == K.ADD:
            s = R.MODS['serb'].const(t[1], n)
            for j in range(2, len(t), 2):
                z = R.MODS['serb'].smul(values[t[j]], R.MODS['serb'].const(t[j + 1], n), n)
                s = R.MODS['serb'].sadd(s, z, n)
            cs = []
            for c in s[1:]:
                cs.append(NO.normal(c, 0) if K.N[c][0] >= K.COMP else c)
            s = R.MODS['serb'].pack(s[0], cs)
        elif op == K.MUL:
            s = R.MODS['serb'].const(t[1], n)
            for j in range(2, len(t), 2):
                b, r = t[j], t[j + 1]
                if K.free_of(r, x):
                    z = R.MODS['serb'].spow(values[b], r, n)
                else:
                    q = yield R.MODS['serb'].g_fun(K.LN, values[b], n)
                    z = None
                    if q is not None:
                        z = yield R.MODS['serb'].g_fun(EXP, R.MODS['serb'].smul(q, values[r], n), n)
                if z is None:
                    yield None
                    return
                s = R.MODS['serb'].smul(s, z, n)
        elif op >= K.FN0:
            s = yield R.MODS['serb'].g_fun(op, values[t[1]], n)
        else:
            s = None
        if s is None:
            yield None
            return
        values[e] = s
        yield R.TICK
    yield values[f]



def g_series(f, x, a, n, side=1):                               #@L 2
    """Flat (valuation, coefficient ids...), known through exponent >= n.

    Finite centers use h=x-a, independent of side; at +/-oo, x=+/-1/h.
    side is reserved for branch-aware callers (analytic integer powers need no change).
    None means unsupported. A singleton (cutoff,) is zero through cutoff-1.
    Retry work orders n+2, n+4, n+8, ... up to 40 after cancellation or division.
    """
    NO = R.need('norm')
    n = max(0, n)
    work = max(2, n)
    step = 2
    while work <= MAXWORK:
        mark = K.NN
        try:
            s = yield g_fold(f, x, a, work, side)
            if s is not None:
                cs = []
                for c in s[1:]:
                    cs.append(NO.normal(c, 0) if K.N[c][0] >= K.COMP else c)
                s = R.MODS['serb'].pack(s[0], cs)
            if s is not None and len(s) > 1 and s[0] + len(s) - 2 >= n:
                keep = K.keep(mark, tuple(s[1:]))
                yield tuple([s[0]] + list(keep))
                return
            if s is not None and len(s) == 1 and work == MAXWORK:
                K.release(mark)
                yield s
                return
        except K.CasSoft:
            s = None
        K.release(mark)
        if work == MAXWORK:
            break
        work = min(MAXWORK, max(n, 2) + step)
        step *= 2
    yield None



def g_taylor(args, ctx):                                        #@L 2
    f = args[0]
    x = args[1] if len(args) > 1 else K.sym('x')
    a = K.ZERO
    order = 5
    if K.N[x][0] == K.EQ:
        if len(args) > 3:
            raise K.CasError('expected taylor(f,x=a,n)')
        x, a = K.N[x][1:]
        if len(args) > 2:
            order = args[2]
        else:
            order = K.num(order)
    elif len(args) > 2:
        a = args[2]
        order = args[3] if len(args) > 3 else K.num(order)
    else:
        order = K.num(order)
    t = K.N[order]
    if K.N[x][0] != K.SYM or not K.free_of(a, x) or K.LST <= K.N[a][0] <= K.GE:
        raise K.CasError('expected a variable and constant center')
    if t[0] != K.NUM or t[2] or t[3] != 1 or t[1] < 0 or t[1] > MAXORDER:
        raise K.CasError('series order must be an integer from 0 to 20')
    n = t[1]
    s = yield g_series(f, x, a, n)
    if s is None:
        yield K.mk(tuple([K.CALL, K.sym('taylor')] + list(args)))
        return
    neginf = K.mul_(K.MONE, [(K.OO, K.ONE)])
    if a == K.OO or a == neginf:
        h = K.mul_(K.MONE if a == neginf else K.ONE, [(x, K.MONE)])
    else:
        h = K.add_([x, K.mul_(K.MONE, [(a, K.ONE)])])
    ts = []
    for j in range(1, len(s)):
        power = s[0] + j - 1
        if power <= n and s[j] != K.ZERO:
            ts.append(K.mul_(K.ONE, [(s[j], K.ONE), (h, K.num(power))]))
    ts.append(K.mk((K.BIGO, K.mul_(K.ONE, [(h, K.num(n + 1))]))))
    yield K.add_(ts)
