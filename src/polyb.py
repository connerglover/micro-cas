#@L 7
"""CVPOLY part B: divisors, rational roots, Gauss-Jordan over Q, Bezout (DESIGN 4.3, 11.2;
alg 2.6, 2.8, 2.9). Dense polynomials as in poly.py: int lists, low degree first, [] is 0.
Self-contained: no imports, no calls into the other parts.
"""

TDMAX = 10000       # trial division bound for divisors (as the radicand bound, DESIGN 6.2)
DIVCAP = 1024       # more divisors than this: give up ([], False)
RRMAX = 4000        # rational-root candidates tested at most (after pruning)


def divisors(n, lim=0):                                         #@L 7
    # (the sorted positive divisors of |n| that are <= lim (0: all), complete) for n != 0.
    # A cofactor that trial division up to TDMAX leaves unproved prime counts as one prime:
    # the list is then only part of the divisors and complete is False. ([], False) when
    # there are more than DIVCAP of them.
    n = n if n >= 0 else -n
    lim = lim or n
    ds = [1]
    p = 2
    while p * p <= n and p <= TDMAX:
        if n % p == 0:
            e = 0
            while n % p == 0:
                n //= p
                s = len(ds)
                for i in range(e, s):               # the last block times p
                    if ds[i] * p <= lim:
                        ds.append(ds[i] * p)
                e = s
                if len(ds) > DIVCAP:
                    return [], False
        p += 1 if p == 2 else 2
    ok = p * p > n
    if n > 1:
        for i in range(len(ds)):
            if ds[i] * n <= lim:
                ds.append(ds[i] * n)
    if len(ds) > DIVCAP:
        return [], False
    ds.sort()
    return ds, ok


def ratroots(a):                                                #@L 6
    # the rational roots of a != []: (roots, cof, complete). roots: [(p, q, m)] with q > 0,
    # multiplicity m, in candidate order (q ascending, then |p|, + before -), p/q in lowest
    # terms (when a is primitive or complete is True); a = cof * prod((q*x - p)^m).
    # complete: cof has no rational root (False if a divisor list or the budget ran short).
    k = 0
    while not a[k]:
        k += 1
    f = a[k:]
    out = [(0, 1, k)] if k else []
    lc = f[-1] if f[-1] > 0 else -f[-1]
    bnd = 1
    for i in range(1, len(f)):                      # Fujiwara: every |root| <= 2*bnd
        while bnd ** i * lc < abs(f[-1 - i]):
            bnd *= 2
    bnd *= 2
    dq, ok = divisors(lc)
    dp, ok2 = divisors(f[0], bnd * lc)
    ok = ok and ok2
    tests = 0
    v1 = None
    for q in dq:
        for p0 in dp:
            if p0 > bnd * q or len(f) < 2 or tests > RRMAX:
                break
            g, h = p0, q
            while h:
                g, h = h, g % h
            if g > 1:
                continue
            for p in (p0, -p0):
                if v1 is None:                      # f(1) and f(-1) of the current f
                    v1 = sum(f)
                    v2 = sum(f[0::2]) - sum(f[1::2])
                if (v1 and (q == p or v1 % (q - p))) or (v2 and (q == -p or v2 % (q + p))):
                    continue                        # (q-p) | f(1) and (q+p) | f(-1)
                tests += 1
                m = 0
                while len(f) > 1:                   # divide by q*x - p while exact
                    gq = [0] * (len(f) - 1)
                    s = 0
                    for i in range(len(f) - 1, 0, -1):
                        t, e = divmod(f[i] + s, q)
                        if e:
                            break
                        gq[i - 1] = t
                        s = p * t
                    if e or f[0] + s:
                        break
                    f = gq
                    m += 1
                if m:
                    out.append((p, q, m))
                    v1 = None
    return out, f, (ok and tests <= RRMAX) or len(f) < 2


def gjsolve(m, nv):                                             #@L 7
    # Gauss-Jordan over Q on integer rows (fraction-free, gcd-reduced). Columns 0..nv-1 are
    # the unknowns, the others right-hand sides. -> (piv, rows): pivot columns ascending; row
    # k has row[piv[k]] > 0, zeros in the other pivot columns, content 1. None: inconsistent.
    rows = list(map(list, m))                       # copies: m is not modified
    piv = []
    for c in range(nv):
        k = len(piv)
        b = -1
        for i in range(k, len(rows)):
            if rows[i][c] and (b < 0 or abs(rows[i][c]) < abs(rows[b][c])):
                b = i
        if b < 0:
            continue
        rows[k], rows[b] = rows[b], rows[k]
        piv.append(c)
        pr = rows[k]
        for i in range(-1, len(rows)):              # -1: normalize the pivot row first
            r = pr if i < 0 else rows[i]
            e = r[c]
            if i == k or not e:
                continue
            if i >= 0:
                for j in range(len(r)):
                    r[j] = r[j] * pr[c] - pr[j] * e
            g = 0
            for x in r:
                x = x if x >= 0 else -x
                while x:
                    g, x = x, g % x
            g = -g if r[c] < 0 else g
            if g < 0 or g > 1:
                for j in range(len(r)):
                    r[j] //= g
    for r in rows[len(piv):]:                       # 0 = rhs != 0: inconsistent
        if any(r):
            return None
    return piv, rows[:len(piv)]


def bezout(a, b, c):                                            #@L 6
    # (s, t, d) with s*a + t*b = d*c, deg s < deg b, d > 0, gcd(d, cont s, cont t) = 1,
    # for a, b != [] coprime; None otherwise. Solved as a square Sylvester-type system.
    if not a or not b:
        return None
    k = len(b) - 1
    nn = max(len(a) - 1 + k, len(c))
    c = c + [0] * (nn - len(c))
    rows = []
    for e in range(nn):                             # the coefficient of x^e
        r = [0] * nn + [c[e]]
        for i in range(nn):                         # column i: s_i (i < k), else t_(i-k)
            u, j = (a, e - i) if i < k else (b, e - i + k)
            if 0 <= j < len(u):
                r[i] = u[j]
        rows.append(r)
    res = gjsolve(rows, nn)
    if res is None or len(res[0]) < nn:
        return None
    rows = res[1]
    d = 1
    for i in range(nn):                             # the lcm of the pivots
        g, h = d, rows[i][i]
        while h:
            g, h = h, g % h
        d = d * rows[i][i] // g
    s = []
    t = []
    for i in range(nn):
        (s if i < k else t).append(rows[i][nn] * (d // rows[i][i]))
    while s and not s[-1]:
        s.pop()
    while t and not t[-1]:
        t.pop()
    return s, t, d
