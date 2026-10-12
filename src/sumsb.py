#@L 2
# sums family: sumsb helpers.
import node as K
import alg as A
import run as R

# At most 13200 bits across the exact numerator, imaginary part and denominator (about the
# printer's 4000-character limit). Larger
# partial sums stay formal; silently switching an exact sum to floating point would lose
# cancellation. This also bounds the work between CLEAR polls on the calculator.
SUMHEX = 3300

def g_loop(f, x, lo, hi):                                       #@L 2
    out = K.ZERO
    mark = K.NN
    for j in range(lo, hi + 1):
        if K.ESC is not None and K.ESC():
            raise K.Cancel()
        out = K.add_([out, A.subst(f, x, K.num(j))])
        out = K.keep(mark, out)
        t = K.N[out]
        for h in range(1, len(t) if t[0] == K.ADD else 2, 2):
            v = K.N[t[h]] if t[0] == K.ADD or t[0] == K.MUL else t
            if v[0] == K.NUM and len('%x%x%x' % v[1:]) > SUMHEX:
                K.release(mark)
                yield None
                return
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
