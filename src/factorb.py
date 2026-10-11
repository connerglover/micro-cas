#@L 2
# CVFACT part b: bounded univariate factoring over Q, by Yun, rational roots and Kronecker.
# Parts c and d share these search budgets; FACTBUG counts failed product checks in part c.
import node as K
import run as R

KBUD = 6000         # Kronecker odometer steps per ufac call
MBUD = 2000         # image-factor subsets tried per g_mfac call
CYMAX = 128         # cyclotomic polynomials up to this index (binomials)
FKMAX = 64          # Kronecker image: prod(deg_i + 1) at most (as KRONMAX, 8.6)
FACTBUG = 0         # product checks that failed (a bug; the tests assert 0)
STEPS = [0]


def kron(f, d):                                                 #@L 4
    # Kronecker: (h, complete): a factor h of f (primitive, f(0) != 0) with 1 <= deg h <= d,
    # or None. h interpolates signed divisors of f at d + 1 integer points (those with the
    # fewest divisors among 0, 1, -1, 2, ...) by divided differences, which must be integers;
    # then lc(h) | lc(f), h(0) | f(0) and exact division. Each odometer step costs one STEPS;
    # past KBUD the search stops incomplete.
    PO = R.MODS['poly']
    PB = R.MODS['polyb']
    cs = []
    dl = []
    for i in range(d + 5):
        x = (i + 1) // 2 if i & 1 else -(i // 2)
        v = PO.peval(f, x)
        if not v:
            return [-x, 1], True
        ds, ok = PB.divisors(v)
        if ok and ds:
            cs.append((len(ds), i, x, len(dl)))
            dl.append(ds)
    if len(cs) <= d:
        return None, False
    cs.sort()
    xs = []
    ls = []
    for j in range(d + 1):
        xs.append(cs[j][2])
        ls.append(dl[cs[j][3]])
    ix = [0] * (d + 1)
    while True:
        STEPS[0] += 1
        if STEPS[0] > KBUD:
            return None, False
        if not STEPS[0] & 255 and K.ESC is not None and K.ESC():
            raise K.Cancel()
        c = []
        for j in range(d + 1):                  # digit j: a divisor, then its sign (j > 0)
            c.append(ls[j][ix[j] >> 1] if ix[j] & 1 == 0 or not j else -ls[j][ix[j] >> 1])
        ok = 1
        for k in range(1, d + 1):
            for i in range(d, k - 1, -1):
                q, r = divmod(c[i] - c[i - 1], xs[i] - xs[i - k])
                ok = ok and not r
                c[i] = q
        if ok and c[d] and f[-1] % c[d] == 0:
            h = [c[d]]
            for i in range(d - 1, -1, -1):      # Newton form to coefficients
                h = PO.padd([0] + h, h, -xs[i])
                h[0] += c[i]
            if len(h) > 1 and h[0] and f[0] % h[0] == 0 and PO.pdivex(f, h) is not None:
                return PO.pprim(h), True
        j = 0
        while j <= d:
            ix[j] += 1 if j else 2
            if ix[j] < 2 * len(ls[j]):
                break
            ix[j] = 0
            j += 1
        if j > d:
            return None, True


def ufac(f):                                                    #@L 3
    # f (dense ints, nonzero) = c * prod(g^m): (c, [(g, m), ...], comp), each g primitive with
    # lc > 0 and deg >= 1; comp: every g is proven irreducible. Yun, then a worklist: each
    # square-free part splits by the first method that applies: binomial shapes; rational roots
    # (numeric real roots rounded to p/q when a divisor list is incomplete); else Kronecker's
    # search for a factor of degree d = 1 (if needed) or 2 .. deg/2, first of g(X) in X = x^e
    # (e the exponent gcd), then of g. All searches complete without a factor: proven. Work
    # items (g, m, fin): fin, g is known irreducible (a cyclotomic factor from binom).
    PO = R.MODS['poly']
    PB = R.MODS['polyb']
    STEPS[0] = 0
    c, sq = PO.yun(f)
    wk = []
    for g, m in sq:
        wk.append((g, m, 0))
    out = []
    comp = 1
    while wk:
        g, m, ok = wk.pop()
        if K.ESC is not None and K.ESC():
            raise K.Cancel()
        n = len(g) - 1
        fs = None
        e = 0                                       # the exponent gcd
        for i in range(1, n + 1):
            j = i if g[i] else 0
            while j:
                e, j = j, e % j
        ok = ok or n < 2
        if not ok and g[0] and e == n:
            fs, ok = R.MODS['factd'].binom(g)
        if not ok and fs is None:                   # not a binomial, or one binom left open
            rs, h, ok = PB.ratroots(g)
            if rs:
                fs = [h]
                for p, q, k in rs:
                    fs = fs + [[-p, q]] * k
            for r in ([] if rs or ok else R.MODS['factd'].nroots(g)):
                for q in PB.divisors(g[-1])[0]:
                    y = r * q
                    p = int(y + 0.5) if y > 0 else -int(0.5 - y)
                    if fs is None and p and PO.pdivex(g, [-p, q]) is not None:
                        fs = [[-p, q], PO.pdivex(g, [-p, q])]
            tg = ((g[::e], e), (g, 1)) if e > 1 else ((g, 1),)
            for p, s in tg:
                d = 1 if s > 1 or not ok else 2
                while fs is None and d <= (len(p) - 1) // 2:
                    h, done = kron(p, d)
                    if h:
                        u = [0] * ((len(h) - 1) * s + 1)
                        for i in range(len(h)):
                            u[i * s] = h[i]
                        fs = [u, PO.pdivex(g, u)]
                    elif not done:
                        d = n
                    d += 1
                if s == 1:                          # every degree searched to the end
                    ok = d == (len(p) - 1) // 2 + 1
        if fs is None:
            out.append((g, m))
            comp = comp and ok
        else:
            for h in fs:
                if len(h) > 1:
                    wk.append((h, m, ok == 2))
    return c, out, comp
