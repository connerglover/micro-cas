#@L 2
# sums family: sumsb helpers.
import node as K
import alg as A
import run as R

def g_loop(f, x, lo, hi):                                       #@L 2
    out = K.ZERO
    mark = K.NN
    for j in range(lo, hi + 1):
        out = K.add_([out, A.subst(f, x, K.num(j))])
        out = K.keep(mark, out)
        yield R.TICK
    yield out



def g_telescoping(f, x, a, b):                                  #@L 2
    NO = R.need('norm')
    candidates = [R.MODS['sum'].power(x, K.MONE)]
    for e in A.postorder(f):
        if not K.free_of(e, x) and e != f and K.N[e][0] >= K.COMP:
            candidates.append(e)
            if K.N[e][0] == K.ADD and A.degree(e, x) == 1:
                candidates.append(R.MODS['sum'].power(e, K.MONE))
        if len(candidates) >= 12:
            break
    for g in candidates:
        for step in range(1, 5):
            mark = K.NN
            out = None
            try:
                shifted = A.subst(g, x, K.add_([x, K.num(step)]))
                delta = NO.normal(K.add_([g, R.MODS['sum'].mul(K.MONE, shifted)]))
                if delta != K.ZERO:
                    c = NO.normal(R.MODS['sum'].div(f, delta))
                    if K.free_of(c, x):
                        ts = []
                        for j in range(step):
                            ts.append(A.subst(g, x, K.add_([a, K.num(j)])))
                            if b != K.OO:
                                tail = A.subst(g, x, K.add_([b, K.num(j + 1)]))
                            else:
                                LI = R.MODS.get('lim')
                                tail = None
                                try:
                                    tail = A.subst(g, x, K.OO)
                                except K.CasSoft:
                                    tail = None
                                if tail is None and LI is not None:
                                    tail = yield LI.g_lim(g, x, K.OO)
                                if tail is None or K.N[tail][0] >= K.CALL or tail == K.OO:
                                    ts = None
                                    break
                            ts.append(R.MODS['sum'].mul(K.MONE, tail))
                        if ts is not None:
                            out = NO.normal(R.MODS['sum'].mul(c, K.add_(ts)))
            except K.CasSoft:
                out = None
            if out is not None:
                yield K.keep(mark, out)
                return
            K.release(mark)
            yield R.TICK
    yield None



def g_finite(f, x, a, b):                                       #@L 2
    NO = R.need('norm')
    r, q = R.MODS['sum'].split_geo(f, x)
    cs = R.MODS['sum'].coefficients(NO.normal(q, 1), x)
    if cs is not None:
        ps = R.MODS['sum'].discrete(cs, r)
        upper = K.add_([b, K.ONE])
        u = R.MODS['sum'].polynomial(ps, upper)
        v = R.MODS['sum'].polynomial(ps, a)
        if r != K.ONE:
            u = R.MODS['sum'].mul(R.MODS['sum'].power(r, upper), u)
            v = R.MODS['sum'].mul(R.MODS['sum'].power(r, a), v)
        yield NO.normal(K.add_([u, R.MODS['sum'].mul(K.MONE, v)]))
        return
    out = yield g_telescoping(f, x, a, b)
    yield out
