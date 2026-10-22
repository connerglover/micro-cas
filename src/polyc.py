#@L 7
"""CVPOLY part C: sparse multivariate polynomials over Z (DESIGN 4.3, 8.5, 8.6; alg 2.6).

A polynomial in n variables is a dict {exponent tuple: nonzero int}; every key is a tuple of n
ints >= 0; {} is 0. Results never depend on dict order. Self-contained: no imports, no calls
into the other parts. The Kronecker gcd of DESIGN 8.6 is composed by norm.py from mkron,
poly.pgcd, munkron and mdivex (docs/notes/T1.2.md).
"""


def madd(a, b, k=1):                                            #@L 7
    # a + k*b; madd({}, a, c) scales a by c
    r = dict(a)
    for e in b:                                     #@unordered-ok
        v = r.get(e, 0) + k * b[e]
        if v:
            r[e] = v
        elif e in r:
            del r[e]
    return r


def mmul(a, b):                                                 #@L 7
    r = {}
    for e in a:                                     #@unordered-ok
        x = a[e]
        for f in b:                                 #@unordered-ok
            g = []
            for i in range(len(e)):
                g.append(e[i] + f[i])
            g = tuple(g)
            v = r.get(g, 0) + x * b[f]
            if v:
                r[g] = v
            elif g in r:
                del r[g]
    return r


def mpow(a, n, nv):                                             #@L 6
    # a^n for n >= 0 in nv variables (0^0 = 1)
    r = {(0,) * nv: 1}
    while n > 0:
        if n & 1:
            r = mmul(r, a)
        n >>= 1
        if n:
            a = mmul(a, a)
    return r


def mcont(a):                                                   #@L 7
    # the integer content, >= 0 (0 for {})
    g = 0
    for e in a:                                     #@unordered-ok
        h = a[e] if a[e] >= 0 else -a[e]
        while h:
            g, h = h, g % h
        if g == 1:
            break
    return g


def mdeg(a, nv):                                                #@L 7
    # [the degree in each variable] (0 for {})
    d = [0] * nv
    for e in a:                                     #@unordered-ok
        for i in range(nv):
            if e[i] > d[i]:
                d[i] = e[i]
    return d


def mmono(a, nv):                                               #@L 7
    # the monomial content: [the least exponent of each variable] (0 for {})
    d = None
    for e in a:                                     #@unordered-ok
        if d is None:
            d = list(e)
        for i in range(nv):
            if e[i] < d[i]:
                d[i] = e[i]
    return d if d is not None else [0] * nv


def mdivex(a, b):                                               #@L 6
    # the exact quotient a/b with integer coefficients, or None (b != {}). Lex division:
    # each step clears the leading term; a quotient exponent above deg a - deg b fails,
    # which also bounds the steps.
    lb = max(b)                                     #@unordered-ok
    cb = b[lb]
    nv = len(lb)
    hi = mdeg(a, nv)
    lo = mdeg(b, nv)
    r = dict(a)
    q = {}
    while r:
        lr = max(r)                                 #@unordered-ok
        t, x = divmod(r[lr], cb)
        if x:
            return None
        d = []
        for i in range(nv):
            x = lr[i] - lb[i]
            if x < 0 or x > hi[i] - lo[i]:
                return None
            d.append(x)
        d = tuple(d)
        q[d] = t
        for f in b:                                 #@unordered-ok
            g = []
            for i in range(nv):
                g.append(d[i] + f[i])
            g = tuple(g)
            v = r.get(g, 0) - t * b[f]
            if v:
                r[g] = v
            elif g in r:
                del r[g]
    return q


def mkron(a, D):                                                #@L 7
    # Kronecker substitution x_i -> x^(D_0*...*D_(i-1)) into a dense poly.py list; it is
    # one-to-one while every exponent of x_i is < D_i (the last D is not used)
    w = [1]
    for i in range(len(D) - 1):
        w.append(w[-1] * D[i])
    p = []
    for e in a:                                     #@unordered-ok
        k = 0
        for i in range(len(e)):
            k += e[i] * w[i]
        if k >= len(p):
            p.extend([0] * (k + 1 - len(p)))
        p[k] = a[e]
    return p


def munkron(p, D):                                              #@L 7
    # the inverse of mkron: mixed-radix digits; the last variable takes the rest
    r = {}
    for k in range(len(p)):
        if p[k]:
            e = []
            j = k
            for i in range(len(D) - 1):
                e.append(j % D[i])
                j //= D[i]
            e.append(j)
            r[tuple(e)] = p[k]
    return r


def mcoef(a, k):                                                #@L 7
    # the coefficients in x_k: a list, by degree, of dicts with x_k's exponent set to 0
    out = []
    for e in a:                                     #@unordered-ok
        j = e[k]
        while len(out) <= j:
            out.append({})
        f = list(e)
        f[k] = 0
        out[j][tuple(f)] = a[e]
    return out
