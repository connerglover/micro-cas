#@L 7
"""CVPOLY part A: dense polynomials over Z (DESIGN 4.1, 4.3, 11.2; alg 2.6, 2.7).

A polynomial is a list of ints, low degree first: p[i] is the coefficient of x^i. There are no
trailing zeros; [] is 0 and deg p = len(p) - 1. Inputs are never mutated; outputs are always
normalized. No imports: this family has no node dependency.
"""


def padd(a, b, k=1):                                            #@L 7
    # a + k*b; padd([], a, c) scales a by c
    if len(a) < len(b):
        r = a + [0] * (len(b) - len(a))
    else:
        r = a[:]
    for i in range(len(b)):
        r[i] += k * b[i]
    while r and not r[-1]:
        r.pop()
    return r


def pmul(a, b):                                                 #@L 7
    if not a or not b:
        return []
    r = [0] * (len(a) + len(b) - 1)
    for i in range(len(a)):
        x = a[i]
        if x:
            for j in range(len(b)):
                r[i + j] += x * b[j]
    return r


def ppow(a, n):                                                 #@L 6
    # a^n for n >= 0 (0^0 = 1), binary powering
    r = [1]
    while n > 0:
        if n & 1:
            r = pmul(r, a)
        n >>= 1
        if n:
            a = pmul(a, a)
    return r


def pderiv(a):                                                  #@L 7
    r = []
    for i in range(1, len(a)):
        r.append(i * a[i])
    return r


def peval(a, x):                                                #@L 7
    # a(x) by Horner; x may be an int, a float or a complex
    v = 0
    for i in range(len(a) - 1, -1, -1):
        v = v * x + a[i]
    return v


def pcont(a):                                                   #@L 7
    # the content: gcd of the coefficients, >= 0 (0 for a = [])
    g = 0
    for c in a:
        h = c if c >= 0 else -c
        while h:
            g, h = h, g % h
        if g == 1:
            break
    return g


def pprim(a):                                                   #@L 6
    # the primitive part, with a positive leading coefficient
    g = pcont(a)
    if a and a[-1] < 0:
        g = -g
    r = []
    for c in a:
        r.append(c // g)
    return r


def pdivrem(a, b):                                              #@L 6
    # division over Q in integers: (q, r, m) with m*a = q*b + r, deg r < deg b, m > 0 and
    # gcd(m, cont q, cont r) = 1, so q/m and r/m are the quotient and remainder over Q
    n = len(b) - 1
    lb = b[-1]
    ab = lb if lb > 0 else -lb
    r = a[:]
    q = [0] * max(len(r) - n, 0)
    m = 1
    for i in range(len(q) - 1, -1, -1):
        c = r[i + n]
        if c % lb:                                  # scale by |lb| only when needed
            for j in range(i + n + 1):
                r[j] *= ab
            for j in range(i + 1, len(q)):
                q[j] *= ab
            m *= ab
            c *= ab
        t = c // lb
        q[i] = t
        if t:
            for j in range(n + 1):
                r[i + j] -= t * b[j]
    while r and not r[-1]:
        r.pop()
    g = pcont(q + r + [m])
    if g > 1:
        m //= g
        for j in range(len(q)):
            q[j] //= g
        for j in range(len(r)):
            r[j] //= g
    return q, r, m


def pdivex(a, b):                                               #@L 7
    # the exact quotient a/b in Z[x], or None if b does not divide a there (b != [])
    n = len(b) - 1
    if len(a) <= n:
        return [] if not a else None
    r = a[:]
    q = [0] * (len(a) - n)
    for i in range(len(q) - 1, -1, -1):
        t, e = divmod(r[i + n], b[-1])
        if e:
            return None
        q[i] = t
        if t:
            for j in range(n + 1):
                r[i + j] -= t * b[j]
    for i in range(n):
        if r[i]:
            return None
    return q


def pgcd(a, b):                                                 #@L 5
    # gcd in Z[x]: gcd of the contents times the primitive PRS gcd; lc > 0 ([] for 0, 0)
    g = pcont([pcont(a), pcont(b)])
    a = pprim(a)
    b = pprim(b)
    if len(a) < len(b):
        a, b = b, a
    while b:
        a, b = b, pprim(pdivrem(a, b)[1])
    return padd([], a, g)


def yun(a):                                                     #@L 4
    # square-free decomposition (Yun): (c, [(f1, m1), ...]) with a = c * prod(f^m),
    # every f primitive, square-free, of degree >= 1, lc > 0, pairwise coprime; m increasing
    c = pcont(a)
    if a and a[-1] < 0:
        c = -c
    f = pprim(a)
    out = []
    if len(f) < 2:
        return (a[0] if a else 0), out
    d = pderiv(f)
    g = pgcd(f, d)
    b = pdivex(f, g)
    d = padd(pdivex(d, g), pderiv(b), -1)
    i = 1
    while len(b) > 1:
        g = pgcd(b, d)
        if len(g) > 1:
            out.append((g, i))
        b = pdivex(b, g)
        d = padd(pdivex(d, g), pderiv(b), -1)
        i += 1
    return c, out
