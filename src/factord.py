#@L 2
# CVFACT part d: integer factoring, binomial shapes, cyclotomic polynomials and numeric
# real roots. Part a owns COMPLETE/TDIV; part b owns the cyclotomic search cap CYMAX.
import node as K
import run as R


def ifactor(q):                                                 #@L 4
    # the rational q = (NUM, a, 0, d) as a HOLD of prime powers (the denominator's with
    # negative exponents), by trial division by 2, 3 and 6k+-1 up to TDIV; the NUM itself when
    # that says nothing more (numerator and denominator each 1 or a prime). A cofactor over
    # TDIV^2 stays one base and clears COMPLETE (no primality claim).
    FA = R.MODS['fact']
    ps = []
    t = 1
    for n, s in ((q[1] if q[1] > 0 else -q[1], 1), (q[3], -1)):
        p = 2
        i = 0
        j = len(ps)
        while n > 1 and p * p <= n and p <= FA.TDIV:
            if n % p == 0:
                e = 0
                while n % p == 0:
                    n //= p
                    e += s
                ps.append(K.num(p))
                ps.append(K.num(e))
            p += 1 if p < 3 else (4 if p % 6 == 1 else 2)
            i += 1
            if not i & 1023 and K.ESC is not None and K.ESC():
                raise K.Cancel()
        if n > 1:
            if p * p <= n:
                FA.COMPLETE[0] = 0
            ps.append(K.num(n))
            ps.append(K.num(s))
        t = t and len(ps) - j < 3 and (len(ps) == j or ps[-1] == K.num(s))
    if t:
        return K.mk(q)
    return K.mk((K.HOLD, K.mk(tuple([K.MUL, K.num(1 if q[1] > 0 else -1)] + ps))))


def iroot(n, k):                                                #@L 7
    # the k-th root of the int n >= 1 when n is a perfect k-th power, else 0 (Newton)
    x = 1 << ((len('%x' % n) * 4 + k - 1) // k)
    while True:
        y = ((k - 1) * x + n // x ** (k - 1)) // k
        if y >= x:
            break
        x = y
    return x if x ** k == n else 0


def cyclo(n):                                                   #@L 5
    # {d: Phi_d} for every d | n: Phi_d = (x^d - 1) / prod(Phi_e, e | d, e < d)
    PO = R.MODS['poly']
    ph = {}
    for d in range(1, n + 1):
        if n % d == 0:
            p = [-1] + [0] * (d - 1) + [1]
            for e in range(1, d):
                if d % e == 0:
                    p = PO.pdivex(p, ph[e])
            ph[d] = p
    return ph


def binom(g):                                                   #@L 4
    # g = a*x^n + b (primitive, a > 0, b != 0, n >= 2) -> (factors or None, proven). For the
    # largest k | n with a = al^k, |b| = be^k: Phi_d(al*X, be) homogenized, X = x^(n/k), for
    # d | k (b < 0) or d | 2k, d not | k (b > 0); else u^4 + 4v^4 (Sophie Germain). (None, 1):
    # irreducible by Capelli's theorem; (None, 0): a k over CYMAX was not tried.
    n = len(g) - 1
    a = g[-1]
    b = g[0]
    ok = 1
    for k in range(n, 1, -1):
        al = iroot(a, k) if n % k == 0 else 0
        be = iroot(b if b > 0 else -b, k) if al else 0
        N = k if b < 0 else 2 * k
        if be and N > R.MODS['factb'].CYMAX:
            ok = 0
        elif be:
            ph = cyclo(N)
            m = n // k
            fs = []
            for d in range(1, N + 1):
                if N % d == 0 and (b < 0 or k % d):
                    p = ph[d]
                    e = len(p) - 1
                    h = [0] * (e * m + 1)
                    for i in range(e + 1):
                        h[i * m] = p[i] * al ** i * be ** (e - i)
                    fs.append(h)
            if len(fs) > 1:                 # 2: each is irreducible (Phi_d, linear map)
                return fs, 2 if m == 1 else 1
    m = n // 4
    for u, v in ((1, 4), (4, 1)):
        al = iroot(a // u, 4) if n % 4 == 0 and b > 0 and a % u == 0 and b % v == 0 else 0
        be = iroot(b // v, 4) if al else 0
        if be:
            fs = []
            for s in (2, -2):
                h = [0] * (2 * m + 1)
                h[0] = be * be * (2 if v > 1 else 1)
                h[m] = s * al * be
                h[2 * m] = al * al * (2 if u > 1 else 1)
                fs.append(h)
            return fs, 1
    return None, ok


def nroots(f):                                                  #@L 4
    # the real roots of the square-free f (dense ints, deg >= 1) as ascending floats; [] when
    # floats overflow. f^(k) is monotone between consecutive real roots of f^(k+1), so going up
    # from f^(n-1), each such interval holds at most one root: Illinois regula falsi.
    PO = R.MODS['poly']
    n = len(f) - 1
    try:
        ps = [[]]
        bd = 1.0
        for v in f:
            ps[0].append(float(v))
            bd = max(bd, 1.0 + abs(v / f[-1]))                 #@float-ok
        if bd ** n > 1e300:
            return []
    except OverflowError:
        return []
    for k in range(n - 1):
        q = []
        for i in range(1, len(ps[k])):
            q.append(i * ps[k][i])
        ps.append(q)
    rs = []
    for k in range(n - 1, -1, -1):
        p = ps[k]
        pt = [-bd] + rs + [bd]
        rs = []
        a = pt[0]
        fa = PO.peval(p, a)
        for i in range(1, len(pt)):
            b = pt[i]
            fb = PO.peval(p, b)
            if fa == 0.0 and i > 1:
                rs.append(a)
            elif fa * fb < 0.0:
                x, fx, y, fy = a, fa, b, fb
                for j in range(100):
                    z = (x * fy - y * fx) / (fy - fx)           #@float-ok
                    fz = PO.peval(p, z)
                    if fz == 0.0 or abs(y - x) <= 4e-16 * (abs(x) + abs(y)):
                        break
                    if fz * fy < 0.0:
                        x, fx = y, fy
                    else:
                        fx *= 0.5
                    y, fy = z, fz
                rs.append(z)
            a, fa = b, fb
    return rs
