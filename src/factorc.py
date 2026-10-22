#@L 2
# CVFACT part c: multivariate factoring by monomial content, dehomogenization and
# recombination of the Kronecker image. Every result is checked by exact multiplication.
import node as K
import run as R


def g_mfac(P, nv):                                              #@L 2
    # P (a nonzero polyc dict in nv variables) = (a/b) * prod(F^m): (a, b, [(F, m), ...],
    # comp). The monomial content first. A binomial a*U^d + b*V^d in several variables (U, V
    # monomials, d the gcd of the exponents) goes through a*T^d + b: complete, since a
    # monomial change of variables makes it univariate. A homogeneous P in several variables
    # is dehomogenized in its last one (rehomogenized at the end). Then the Kronecker image
    # u = P(X^w0, X^w1, ...) (P itself for one variable) is factored by ufac, and the products
    # of image factors, fewest first, that map back (munkron) to divisors of P are its factors:
    # irreducible when the image factorization is complete. The product is checked against
    # P: a mismatch is a bug (FACTBUG), and P comes back unfactored.
    FB = R.MODS['factb']
    PO = R.MODS['poly']
    PC = R.MODS['polyc']
    mo = PC.mmono(P, nv)
    z = []
    for i in range(nv):
        z.append(-mo[i])
    Q = PC.mmul(P, {tuple(z): 1})
    D = PC.mdeg(Q, nv)
    fs = []
    comp = 1
    ks = sorted(Q)
    if len(ks) == 2 and nv - D.count(0) > 1:
        d = 0
        for i in ks[0] + ks[1]:
            while i:
                d, i = i, d % i
        x, us, comp = FB.ufac([Q[ks[0]]] + [0] * (d - 1) + [Q[ks[1]]])
        for g, m in us:
            F = {}
            for i in range(len(g)):
                z = []
                for j in range(nv):
                    z.append((i * ks[1][j] + (len(g) - 1 - i) * ks[0][j]) // d)
                if g[i]:
                    F[tuple(z)] = g[i]
            fs.append((F, m))
        Q = {(0,) * nv: 1}
        D = [0] * nv
    td = {}
    for z in Q:                                                 #@unordered-ok (a set)
        td[sum(z)] = 1
    h = -1
    for i in range(nv if len(td) == 1 and nv - D.count(0) > 1 else 0):
        h = i if D[i] else h
    if h >= 0:
        T = Q
        Q = {}
        for z in T:                                             #@unordered-ok
            Q[z[:h] + (0,) + z[h + 1:]] = T[z]
        D[h] = 0
        mo[h] += max(td)                                        #@unordered-ok (one key)
    w = 1
    for i in range(nv):
        D[i] += 1
        w *= D[i]
    its = []
    one = nv - D.count(1) < 2                                   # one variable: u is Q
    if w <= FB.FKMAX or one:
        x, us, c = FB.ufac(PC.mkron(Q, D))
        comp = comp and c
        for g, m in us:
            if one:
                fs.append((PC.munkron(g, D), m))
            for i in range(0 if one else m):
                its.append(g)
        Q = {(0,) * nv: 1} if one else Q
    else:
        comp = 0
    s = 1
    n = 0
    while 2 * s <= len(its):
        ix = list(range(s))
        while ix:
            n += 1
            if n > FB.MBUD:
                comp = 0
                its = []
                break
            if not n & 255 and K.ESC is not None and K.ESC():
                raise K.Cancel()
            g = [1]
            for i in ix:
                g = PO.pmul(g, its[i])
            F = PC.munkron(g, D)
            q = PC.mdivex(Q, F)
            if q is not None:
                fs.append((F, 1))
                Q = q
                for i in range(s - 1, -1, -1):
                    its.pop(ix[i])
                break
            i = s - 1
            while i >= 0 and ix[i] == len(its) - s + i:
                i -= 1
            if i < 0:
                s += 1
                break
            ix[i] += 1
            for j in range(i + 1, s):
                ix[j] = ix[j - 1] + 1
    if max(Q) > (0,) * nv:                                      #@unordered-ok (a max)
        fs.append((Q, 1))
    for j in range(len(fs) if h >= 0 else 0):                   # rehomogenize in x_h
        F, m = fs[j]
        t = 0
        for z in F:                                             #@unordered-ok (a max)
            t = max(t, sum(z))
        G = {}
        for z in F:                                             #@unordered-ok
            G[z[:h] + (t - sum(z),) + z[h + 1:]] = F[z]
        fs[j] = (G, m)
        mo[h] -= t * m
    for i in range(nv):
        if mo[i]:
            z = [0] * nv
            z[i] = 1
            fs.append(({tuple(z): 1}, mo[i]))
    G = {(0,) * nv: 1}
    for F, m in fs:
        G = PC.mmul(G, PC.mpow(F, m, nv))
    z = max(P)                                                  #@unordered-ok (a max)
    a = P[z]
    b = G.get(z, 0)
    if b < 0:
        a = -a
        b = -b
    if not b or PC.madd(PC.madd({}, P, b), G, -a):
        FB.FACTBUG += 1
        a = b = 1
        fs = [(P, 1)]
        comp = 0
    yield (a, b, fs, comp)
