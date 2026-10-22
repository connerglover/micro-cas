#@L 3
# CVNORM part a: expand, normal and together (DESIGN 8.1, 8.5, 8.6) and the commands of the
# family. One fold over postorder(e) maps every node to a fraction (num, den) of polynomials in
# kernels: polyc dicts {exponent tuple: int} over a fixed number of slots, slot 0 being i. The
# relations x_k^q = c (i^2 = -1, sqrt(n)^2 = n, ...) are applied in every product. The gcd
# of num and den is the Kronecker one of 8.6. Part b (normb.py) has the zero test, simplify
# and the factored denominator; the generators here that g_eval reaches through
# R.need('norm') forward to it.
import node as K
import nodeb as KB
import alg as A
import run as R

MAXTERMS = 400      # terms in one polynomial (8.5)
KRONMAX = 64        # univariate degree after the Kronecker substitution (8.6)
NVMAX = 64          # kernel slots in one fold (the length of every exponent tuple)
MAXCELLS = 3200     # terms times slots in one polynomial (memory; with many kernels)
M_LARGE = 'Too many terms'
GAVEUP = [0]        # NORMAL_GAVE_UP: 1 when the last normal returned its input unchanged


def pmul(a, b, rl):                                             #@L 6
    # a*b reduced by the relations rl (slot k: None or (q, c), x_k^q = c; a and b are
    # reduced, so one step per slot is enough). More than MAXTERMS terms (or MAXCELLS
    # exponents) raises CasError, checked every 64 terms with the cancel and memory polls.
    r = {}
    nv = len(rl)
    n = 0
    for e in a:                                                 #@unordered-ok
        for f in b:                                             #@unordered-ok
            v = a[e] * b[f]
            g = []
            for i in range(nv):
                x = e[i] + f[i]
                if rl[i] and x >= rl[i][0]:
                    x -= rl[i][0]
                    v *= rl[i][1]
                g.append(x)
            g = tuple(g)
            v += r.get(g, 0)
            if v:
                r[g] = v
            elif g in r:
                del r[g]
            n += 1
            if not n & 63:
                if len(r) > MAXTERMS or len(r) * nv > MAXCELLS:
                    raise K.CasError(M_LARGE)
                if K.ESC is not None and K.ESC():
                    raise K.Cancel()
                if K.MEMFREE is not None and K.MEMFREE() < K.LOWMEM:
                    raise K.CasMemory()
    if len(r) > MAXTERMS or len(r) * nv > MAXCELLS:
        raise K.CasError(M_LARGE)
    return r


def ppow(a, n, rl):                                             #@L 5
    # a^n for n >= 1 by squaring; a coefficient over MAXBITS bits raises CasError
    r = a
    n -= 1
    while n:
        if n & 1:
            r = pmul(r, a, rl)
        n >>= 1
        if n:
            a = pmul(a, a, rl)
            for z in a:                                         #@unordered-ok
                if len('%x' % a[z]) > K.MAXBITS >> 2:
                    raise K.CasError(K.M_BIG)
    return r


def normal(e, ex=0):                                            #@L 3
    # ex 0: normal (8.6), the canonical k*N/D with the gcd cancelled; kernels (function nodes
    # with normalized arguments, u^(1/q) for u^(p/q), other powers, symbols) are variables.
    # ex 1: expand (8.5): integer powers >= 0 multiplied out; function arguments and the bases
    # and exponents of other powers expanded. normal gives up (returns e, GAVEUP[0] = 1) on
    # oo, undef, the caps or Undefined; expand raises instead.
    N = K.N
    GAVEUP[0] = 0
    po = A.postorder(e)
    nv = 1
    for m in po:                                    # an upper bound of the kernel slots
        t = N[m]
        if t[0] == K.MUL:
            for j in range(3, len(t), 2):
                w = N[t[j]]
                if w[0] or w[2] or w[3] != 1 or (w[1] < 0 and ex) or not N[t[j - 1]][0]:
                    nv += 1
        elif t[0] > K.NUM and t[0] != K.ADD:
            nv += NVMAX if (m == K.OO or m == K.UNDEF) and not ex else 1
    try:
        if nv >= NVMAX:
            raise K.CasError(M_LARGE)
        Z = (0,) * nv
        one = {Z: 1}
        ks = [K.I] + [0] * (nv - 1)
        rl = [(2, -1)] + [None] * (nv - 1)
        PC = R.MODS['polyc']
        NC = R.MODS['normc']
        rf = {}
        for m in po:
            t = N[m]
            op = t[0]
            if op == K.NUM:
                x = ({}, {Z: t[3]})
                if t[1]:
                    x[0][Z] = t[1]
                if t[2]:
                    x[0][NC.kmono(K.I, ks)] = t[2]
            elif op == K.ADD:
                x = rf[t[1]]
                for j in range(2, len(t), 2):
                    y = rf[t[j]]
                    c = rf[t[j + 1]]
                    y = (pmul(y[0], c[0], rl), pmul(y[1], c[1], rl))
                    if x[1] == y[1]:
                        x = (PC.madd(x[0], y[0]), x[1])
                    else:
                        x = (PC.madd(pmul(x[0], y[1], rl), pmul(y[0], x[1], rl)),
                             pmul(x[1], y[1], rl))
            elif op == K.MUL:
                x = rf[t[1]]
                for j in range(2, len(t), 2):
                    y = rf[t[j]]
                    w = N[t[j + 1]]
                    p = w[1] if w[0] == K.NUM and not w[2] else 0
                    h = K.HUGE and KB.hker(t[j], t[j + 1], ex)    # too large to fold (5.3):
                    if h or not p or (p < 0 and ex):        # a power kept whole: a kernel (a
                        c = rf[t[j + 1]]                    # giant one: b^-x is (b^x)^-1)
                        y = ({NC.kmono(h or K.mul_(K.ONE, [(NC.tonode(y[0], y[1], ks, ex),
                                                   NC.tonode(c[0], c[1], ks, ex))]), ks): 1}, one)
                        p = -1 if h and p < 0 and not ex else 1
                    elif w[3] > 1:                          # u^(p/q) = (u^(1/q))^p
                        z = NC.kmono(K.mul_(K.ONE, [(NC.tonode(y[0], y[1], ks, ex),
                                                  K.num(1, 0, w[3]))]), ks)
                        c = y[0].get(Z)
                        if y[1] == one and len(y[0]) == 1 and c:
                            rl[z.index(1)] = (w[3], c)      # an integer radicand
                        y = ({z: 1}, one)
                    if p < 0:
                        if not y[0]:
                            raise K.Undefined()
                        y = (y[1], y[0])
                        p = -p
                    x = (pmul(x[0], ppow(y[0], p, rl), rl), pmul(x[1], ppow(y[1], p, rl), rl))
            else:                                           # a leaf or another composite
                k = m
                if op >= K.COMP:
                    x = {}
                    for j in range(1, len(t)):
                        y = rf[t[j]]
                        x[t[j]] = NC.tonode(y[0], y[1], ks, ex)
                    k = A.rebuild(m, x)
                x = ({NC.kmono(k, ks): 1}, one)
            rf[m] = x
        x = rf[e]
        return NC.tonode(x[0], x[1], ks, ex)
    except (K.CasError, K.CasSoft):
        if ex:
            raise
    GAVEUP[0] = 1
    return e


def g_expand(args, ctx):                                        #@L 2
    yield normal(args[0], 1)


def g_together(args, ctx):                                      #@L 2
    # one fraction (14): normal, the denominator factored when that is not bigger
    yield R.MODS['normc'].dfac(normal(args[0]))


def g_simplify(args, ctx):                                      #@L 2
    r = yield R.MODS['normb'].g_simp(args[0], 1)
    yield r


def g_autosimp(e):                                              #@L 2
    # the default result path (8.7), called by g_eval
    r = yield R.MODS['normb'].g_simp(e, 0)
    yield r
