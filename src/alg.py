#@L 7
# CVALG: postorder, substitution, shape predicates, size, the numeric evaluator and the numeric
# probe (DESIGN 6.6, 8.3, 8.6, 8.7, 11, 17.1). Resident; no state survives a call except
# LEFTREAL, which holds no ids.
import math
import node as K
import nodeb as KB

# program instructions (6.6): flat tuples of value indexes and Python numbers
P_CONST = 0                  # (P_CONST, value)
P_VAR = 1                    # (P_VAR, slot)
P_ADD = 2                    # (P_ADD, c, i1, k1, ...)
P_MUL = 3                    # (P_MUL, k, i1, e1, s1, ...): e an int or a float; s = +-1.0 for
                             # an odd-denominator rational (the real odd root, 6.2), else 0
P_POW = 4                    # (P_POW, ib, ie): a symbolic or complex exponent
P_FN = 5                     # (P_FN, op - FN0, i)

NO = 0                       # nprobe results: a mismatch / agreement at every usable point /
LIKELY = 1                   # no usable point
UNKNOWN = -1

TOL = 1e-9                   # relative uncertainty of each leaf in the probe (8.6)
NAN = float('nan')
INF = float('inf')
EF = math.e
HALFPI = 0.5 * math.pi
LEFTREAL = [0]               # 1 after nrun when a value left the reals from real operands
LANCZ = (0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
         -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6,
         1.5056327351493116e-7)


# -- traversal and substitution ------------------------------------------------------------------

def postorder(e):                                               #@L 7
    # the ids reachable from e (an id or a flat tuple of ids), ascending: ids are topological,
    # so every child comes before its parents (5.1)
    rs = e if type(e) is tuple else (e,)
    top = 0
    for r in rs:
        if r > top:
            top = r
    mark = bytearray(top + 1)
    for r in rs:
        mark[r] = 1
    N = K.N
    for i in range(top, 0, -1):
        if mark[i]:
            t = N[i]
            if t[0] >= K.COMP:
                for j in range(1, len(t)):
                    mark[t[j]] = 1
    out = []
    for i in range(1, top + 1):
        if mark[i]:
            out.append(i)
    return out


def rebuild(n, new):                                            #@L 4
    # node n with each child c replaced by new.get(c, c), through the constructors (8.2); n
    # itself when nothing changed. A CALL keeps its head (a name); a changed HOLD folds.
    t = K.N[n]
    op = t[0]
    if op < K.COMP:
        return new.get(n, n)
    c = []
    ch = False
    for j in range(1, len(t)):
        u = new.get(t[j], t[j])
        if u != t[j]:
            ch = True
        c.append(u)
    if not ch:
        return n
    if op == K.ADD:
        ts = [c[0]]
        for j in range(1, len(c), 2):
            ts.append(c[j] if c[j + 1] == K.ONE else
                      K.mul_(K.ONE, [(c[j + 1], K.ONE), (c[j], K.ONE)]))
        return K.add_(ts)
    if op == K.MUL:
        ps = []
        for j in range(1, len(c), 2):
            ps.append((c[j], c[j + 1]))
        k = c[0]
        if K.N[k][0] > K.FLT:                                   # no longer a number
            ps.append((k, K.ONE))
            k = K.ONE
        return K.mul_(k, ps)
    if op >= K.FN0:
        return K.fn_(op, c[0])
    if K.EQ <= op <= K.LE:
        return K.rel_(op, c[0], c[1])
    if op == K.HOLD:
        return c[0]
    if op == K.CALL:
        c[0] = t[1]
    return K.mk(tuple([op] + c))


def subst(e, x, v):                                             #@L 3
    # e with node x replaced by v, or the ids of the tuple x by those of the tuple v at once,
    # rebuilt through the constructors; Undefined (1/0, tan(pi/2), ...) propagates
    if type(x) is not tuple:
        x = (x,)
        v = (v,)
    new = {}
    mask = 0
    for j in range(len(x)):
        new[x[j]] = v[j]
        if mask >= 0 and K.N[x[j]][0] == K.SYM and K.V[x[j]] != K.OVF:
            mask |= K.V[x[j]]
        else:
            mask = -1
    if mask >= 0 and not K.V[e] & mask:
        return e
    for n in postorder(e):
        if n in new or K.N[n][0] < K.COMP or (mask >= 0 and not K.V[n] & mask):
            continue
        m = rebuild(n, new)
        if m != n:
            new[n] = m
    return new.get(e, e)


# -- shape predicates (alg 1.3) ------------------------------------------------------------------

def pco(e, x, n):                                               #@L 6
    # e as a polynomial of degree <= n in x with coefficients free of x, structurally (as
    # built): a list of n + 1 term lists, x^0 first. A term (t, k) means the number tuple k
    # times t, t free of x (ONE for a number). None when e is not such a polynomial, or when a
    # coefficient would be the product of two non-numeric terms (y*(x+z): expand first).
    N = K.N
    vx = K.V[x]
    sx = N[x][0] == K.SYM and vx != K.OVF
    pm = {}
    for m in postorder(e):
        if m != x and ((not K.V[m] & vx) if sx else K.free_of(m, x)):
            continue
        r = []
        for i in range(n + 1):
            r.append([])
        if m == x:
            r[1].append((K.ONE, K.Q1))
            pm[m] = r
            continue
        t = N[m]
        op = t[0]
        if op == K.ADD:
            if t[1] != K.ZERO:
                r[0].append((K.ONE, N[t[1]]))
            for j in range(2, len(t), 2):
                k = N[t[j + 1]]
                s = pm.get(t[j])
                if s is None:
                    r[0].append((t[j], k))
                else:
                    for i in range(n + 1):
                        for u, w in s[i]:
                            r[i].append((u, K.nmul(w, k)))
        elif op == K.MUL:
            fp = []
            dp = []
            for j in range(2, len(t), 2):
                if t[j + 1] in pm:
                    return None                                 # x in an exponent
                if t[j] in pm:
                    dp.append(t[j])
                    dp.append(N[t[j + 1]])
                else:
                    fp.append(t[j])
                    fp.append(t[j + 1])
            if not fp:
                f = K.ONE
            elif len(fp) == 2 and fp[1] == K.ONE:
                f = fp[0]
            else:
                f = K.mk(tuple([K.MUL, K.ONE] + fp))
            r[0].append((f, N[t[1]]))
            for j in range(0, len(dp), 2):
                w = dp[j + 1]
                if w[0] != K.NUM or w[2] or w[3] != 1 or w[1] < 1 or w[1] > n:
                    return None
                s = pm[dp[j]]
                for p in range(w[1]):
                    z = []
                    for i in range(n + 1):
                        z.append([])
                    for i in range(n + 1):
                        for h in range(n + 1):
                            if r[i] and s[h]:
                                if i + h > n:
                                    return None
                                for u1, k1 in r[i]:
                                    for u2, k2 in s[h]:
                                        if u1 != K.ONE and u2 != K.ONE:
                                            return None
                                        z[i + h].append((u2 if u1 == K.ONE else u1,
                                                         K.nmul(k1, k2)))
                    r = z
        else:
            return None
        pm[m] = r
    r = pm.get(e)
    if r is None:
        r = [[(e, K.Q1)]]
        for i in range(n):
            r.append([])
    return r


def linear(e, x):                                               #@L 5
    # e = a*x + b with a, b free of x -> (a, b); a is ZERO when e is free of x, so the LIN
    # wildcard (9.2) must test a != ZERO. None when e is not linear in x as built (see pco).
    r = pco(e, x, 1)
    if r is None:
        return None
    out = []
    for i in (1, 0):
        ts = []
        for u, k in r[i]:
            ts.append(K.mk(k) if u == K.ONE else K.add_([u], k))
        out.append(K.add_(ts))
    return (out[0], out[1])


def quadratic(e, x):                                            #@L 5
    # e = a*x^2 + b*x + c with a, b, c free of x -> (a, b, c); a (and b) may be ZERO, so the
    # QUAD wildcard must test a != ZERO. None as for linear.
    r = pco(e, x, 2)
    if r is None:
        return None
    out = []
    for i in (2, 1, 0):
        ts = []
        for u, k in r[i]:
            ts.append(K.mk(k) if u == K.ONE else K.add_([u], k))
        out.append(K.add_(ts))
    return (out[0], out[1], out[2])


def split_const(e, x):                                          #@L 5
    # e = c*g with c free of x; g holds the factors that depend on x, with coefficient 1:
    # (e, ONE) when e is free of x, (ONE, e) when e is not a product
    N = K.N
    if K.free_of(e, x):
        return (e, K.ONE)
    t = N[e]
    if t[0] != K.MUL:
        return (K.ONE, e)
    cp = []
    gp = []
    for j in range(2, len(t), 2):
        if K.free_of(t[j], x) and K.free_of(t[j + 1], x):
            cp.append(t[j])
            cp.append(t[j + 1])
        else:
            gp.append(t[j])
            gp.append(t[j + 1])
    k = t[1]
    if not cp:
        c = k
    elif len(cp) == 2 and cp[1] == K.ONE and k == K.ONE:
        c = cp[0]
    elif len(cp) == 2 and cp[1] == K.ONE and k == K.MONE and N[cp[0]][0] == K.ADD:
        c = K.neg_(cp[0])                                       # -(sum) is distributed (5.3)
    else:
        c = K.mk(tuple([K.MUL, k] + cp))
    if len(gp) == 2 and gp[1] == K.ONE:
        g = gp[0]
    else:
        g = K.mk(tuple([K.MUL, K.ONE] + gp))
    return (c, g)


def degree(e, x):                                               #@L 6
    # the degree of e as a polynomial in x with coefficients free of x: 0 when e is free of x,
    # -1 when e is not a polynomial in x as built (negative or symbolic powers, functions of x)
    N = K.N
    d = {}
    for m in postorder(e):
        if m == x:
            d[m] = 1
            continue
        t = N[m]
        op = t[0]
        if op < K.COMP:
            continue
        s = 0
        if op == K.ADD:
            for j in range(2, len(t), 2):
                g = d.get(t[j], 0)
                if g < 0:
                    s = -1
                    break
                if g > s:
                    s = g
        elif op == K.MUL:
            for j in range(2, len(t), 2):
                g = d.get(t[j], 0)
                if d.get(t[j + 1], 0):
                    s = -1
                    break
                if g:
                    w = N[t[j + 1]]
                    if g < 0 or w[0] != K.NUM or w[2] or w[3] != 1 or w[1] < 0:
                        s = -1
                        break
                    s += g * w[1]
        else:
            for j in range(1, len(t)):
                if d.get(t[j], 0):
                    s = -1
                    break
        if s:
            d[m] = s
    return d.get(e, 0)


def size(e, extra=False):                                       #@L 6
    # the tree size of e, counted with multiplicity (8.7, 9.2): a leaf is 1; a sum is 1, plus 1
    # for a nonzero constant, plus each term and 1 per coefficient other than 1; a product is
    # 1, plus 1 for a coefficient other than 1, plus each base and each exponent other than 1;
    # any other node is 1 plus its children. extra (the simplify measure): plus 2 per numeric
    # radical pair and 1 per negative numeric exponent.
    N = K.N
    z = {}
    for m in postorder(e):
        t = N[m]
        op = t[0]
        if op < K.COMP:
            continue
        s = 1
        if op == K.ADD:
            if t[1] != K.ZERO:
                s += 1
            for j in range(2, len(t), 2):
                s += z.get(t[j], 1)
                if t[j + 1] != K.ONE:
                    s += 1
        elif op == K.MUL:
            if t[1] != K.ONE:
                s += 1
            for j in range(2, len(t), 2):
                s += z.get(t[j], 1)
                w = t[j + 1]
                if w != K.ONE:
                    s += z.get(w, 1)
                    tw = N[w]
                    if extra and tw[0] <= K.FLT:
                        if N[t[j]][0] <= K.FLT and (tw[0] == K.FLT or tw[3] != 1):
                            s += 2
                        if tw[1] < 0 and not tw[2]:
                            s += 1
        else:
            for j in range(1, len(t)):
                s += z.get(t[j], 1)
        z[m] = s
    return z.get(e, 1)


def simplify_candidate(e):                                      #@L 7
    # True when the default result path should try simplify (8.7): a sum together with a
    # negative power, a tan/sec/csc/cot, or a numeric radical other than sqrt of an integer
    N = K.N
    seen = bytearray(e + 1)
    st = [e]
    add = False
    neg = False
    while st:
        m = st.pop()
        if seen[m]:
            continue
        seen[m] = 1
        t = N[m]
        op = t[0]
        if op < K.COMP:
            continue
        if K.TAN <= op <= K.COT:
            return True
        if op == K.ADD:
            add = True
        elif op == K.MUL:
            for j in range(2, len(t), 2):
                w = N[t[j + 1]]
                if w[0] <= K.FLT:
                    if w[1] < 0 and not w[2]:
                        neg = True
                    b = N[t[j]]                 # a radical; HOLD keeps integer powers
                    if b[0] <= K.FLT and (w[0] == K.FLT or w[3] != 1) and (
                            t[j + 1] != K.HALF or b[0] == K.FLT or b[2] or b[3] != 1):
                        return True
        if add and neg:
            return True
        for j in range(1, len(t)):
            st.append(t[j])
    return False


# -- real and complex function values (6.6; cmath and math.sinh etc. are absent) ----------------

def qf(a, d):                                                   #@L 7
    # the float nearest a/d (ints, d > 0); float() of a big int is not portable (device-python
    # 5.1), so big operands are scaled to about 64 bits first; inf beyond the float range
    na = len('%x' % (a if a >= 0 else -a))
    nd = len('%x' % d)
    if na <= 13 and nd <= 13:
        return a / d
    k = 4 * (nd - na) + 64
    if k >= 0:
        a = (a << k) // d
    else:
        a = a // (d << -k)
    try:
        return math.ldexp(float(a), -k)
    except OverflowError:
        return INF


def cval(t):                                                    #@L 6
    # the Python value of a NUM or FLT tuple: a float, or a complex when it is not real
    if t[0] == K.FLT:
        a = t[1]
        b = t[2]
    else:
        a = qf(t[1], t[3])
        b = qf(t[2], t[3]) if t[2] else 0.0
    v = complex(a, b) if b else a
    if v - v != 0:
        raise K.Undefined()
    return v


def nabs(v):                                                    #@L 7
    # |v| for a float or a complex v, with no overflow in the squares
    if type(v) is not complex:
        return v if v >= 0.0 else -v
    a = v.real if v.real >= 0.0 else -v.real
    b = v.imag if v.imag >= 0.0 else -v.imag
    if a < b:
        a, b = b, a
    if a == 0.0:
        return 0.0
    b = b / a
    return a * math.sqrt(1.0 + b * b)


def fsec(a):                                                    #@L 7
    return 1.0 / math.cos(a)


def fcsc(a):                                                    #@L 7
    return 1.0 / math.sin(a)


def fcot(a):                                                    #@L 7
    return math.cos(a) / math.sin(a)


def fsinh(a):                                                   #@L 7
    b = a if a >= 0.0 else -a
    if b < 1e-3:
        return a * (1.0 + a * a / 6.0 * (1.0 + a * a / 20.0))
    b = math.exp(b)
    b = 0.5 * (b - 1.0 / b)
    return b if a >= 0.0 else -b


def fcosh(a):                                                   #@L 7
    b = math.exp(a if a >= 0.0 else -a)
    return 0.5 * (b + 1.0 / b)


def ftanh(a):                                                   #@L 7
    b = a if a >= 0.0 else -a
    if b > 20.0:
        b = 1.0
    elif b < 1e-3:
        b = b * (1.0 - b * b / 3.0 * (1.0 - 0.4 * b * b))
    else:
        b = math.exp(-2.0 * b)
        b = (1.0 - b) / (1.0 + b)
    return b if a >= 0.0 else -b


def fsign(a):                                                   #@L 7
    return 1.0 if a > 0.0 else -1.0 if a < 0.0 else 0.0


def ffloor(a):                                                  #@L 7
    return float(math.floor(a))


def fceil(a):                                                   #@L 7
    return float(math.ceil(a))


def ffact(a):                                                   #@L 7
    # a! = gamma(a + 1) (math.gamma is absent): products for integers, Lanczos (g = 7)
    # otherwise, with the reflection formula below 1/2; a pole raises ValueError
    if a == math.floor(a):
        if a < 0.0:
            raise ValueError()
        if a > 171.0:
            raise OverflowError()
        v = 1.0
        n = 2.0
        while n <= a:
            v *= n
            n += 1.0
        return v
    z = a + 1.0
    w = (1.0 - z if z < 0.5 else z) - 1.0
    s = LANCZ[0]
    for k in range(1, 9):
        s += LANCZ[k] / (w + k)
    t = w + 7.5
    s = 2.5066282746310002 * t ** (w + 0.5) * math.exp(-t) * s
    if z < 0.5:
        return math.pi / (math.sin(math.pi * z) * s)
    return s


def cexp(z):                                                    #@L 7
    e = math.exp(z.real)
    b = z.imag
    if b == 0.0:
        return complex(e, 0.0)
    return complex(e * math.cos(b), e * math.sin(b))


def clog(z):                                                    #@L 7
    # the principal log; -0.0 counts as +0.0 (ln(-1) = i*pi); log(0) raises ValueError
    a = z.real
    b = z.imag + 0.0
    m = a if a >= 0.0 else -a
    w = b if b >= 0.0 else -b
    if m < w:
        m, w = w, m
    if m == 0.0:
        raise ValueError()
    w = w / m
    return complex(math.log(m) + 0.5 * math.log(1.0 + w * w), math.atan2(b, a))


def csqrt(z):                                                   #@L 7
    # the principal square root
    a = z.real
    b = z.imag
    m = a if a >= 0.0 else -a
    w = b if b >= 0.0 else -b
    if m < w:
        m, w = w, m
    if m == 0.0:
        return complex(0.0, 0.0)
    w = w / m
    r = m * math.sqrt(1.0 + w * w)
    if a >= 0.0:
        s = math.sqrt(0.5 * (r + a))
        return complex(s, 0.5 * b / s)
    s = math.sqrt(0.5 * (r - a))
    return complex(0.5 * (b if b >= 0.0 else -b) / s, s if b >= 0.0 else -s)


def csin(z):                                                    #@L 6
    a = z.real
    b = z.imag
    return complex(math.sin(a) * fcosh(b), math.cos(a) * fsinh(b))


def ccos(z):                                                    #@L 6
    a = z.real
    b = z.imag
    return complex(math.cos(a) * fcosh(b), -math.sin(a) * fsinh(b))


def csinh(z):                                                   #@L 6
    a = z.real
    b = z.imag
    return complex(fsinh(a) * math.cos(b), fcosh(a) * math.sin(b))


def ccosh(z):                                                   #@L 6
    a = z.real
    b = z.imag
    return complex(fcosh(a) * math.cos(b), fsinh(a) * math.sin(b))


def ctan(z):                                                    #@L 6
    # (sin 2a + i sinh 2b) / (cos 2a + cosh 2b); i*sign(b) once cosh overflows the precision
    a = 2.0 * z.real
    b = 2.0 * z.imag
    if b > 40.0 or b < -40.0:
        return complex(0.0, 1.0 if b > 0.0 else -1.0)
    d = math.cos(a) + fcosh(b)
    return complex(math.sin(a) / d, fsinh(b) / d)


def ctanh(z):                                                   #@L 6
    # (sinh 2a + i sin 2b) / (cosh 2a + cos 2b)
    a = 2.0 * z.real
    b = 2.0 * z.imag
    if a > 40.0 or a < -40.0:
        return complex(1.0 if a > 0.0 else -1.0, 0.0)
    d = fcosh(a) + math.cos(b)
    return complex(fsinh(a) / d, math.sin(b) / d)


def csec(z):                                                    #@L 5
    return 1.0 / ccos(z)


def ccsc(z):                                                    #@L 5
    return 1.0 / csin(z)


def ccot(z):                                                    #@L 5
    return 1.0 / ctan(z)


def casin(z):                                                   #@L 6
    # -i*ln(iz + sqrt(1 - z^2)), computed where the two terms do not cancel and extended as
    # an odd function: asin(2) = pi/2 - i*ln(2 + sqrt(3)), asin(-2) = -asin(2) (SymPy, D15)
    g = z.imag > 0.0 or (z.imag == 0.0 and z.real < 0.0)
    if g:
        z = -z
    u = clog(complex(-z.imag, z.real) + csqrt(1.0 - z * z))
    u = complex(u.imag, -u.real)
    return -u if g else u


def cacos(z):                                                   #@L 5
    return HALFPI - casin(z)


def catan(z):                                                   #@L 6
    # (i/2)*(ln(1 - iz) - ln(1 + iz)); the poles +-i raise ValueError
    a = z.real
    b = z.imag
    u = clog(complex(1.0 + b, -a)) - clog(complex(1.0 - b, a))
    return complex(-0.5 * u.imag, 0.5 * u.real)


def cbad(z):                                                    #@L 7
    # sign, floor, ceil and ! have no value at a non-real argument
    raise K.Undefined()


def cpow(b, e):                                                 #@L 6
    # the principal value of b^e for a float or complex b and an int, float or complex e; an
    # int e uses square and multiply; 0 to a power that is not positive raises
    # ZeroDivisionError
    if type(b) is not complex:
        b = complex(b, 0.0)
    if type(e) is int:
        n = e if e >= 0 else -e
        r = complex(1.0, 0.0)
        while n:
            if n & 1:
                r = r * b
            n >>= 1
            if n:
                b = b * b
        return 1.0 / r if e < 0 else r
    if b.real == 0.0 and b.imag == 0.0:
        if (e.real if type(e) is complex else e) > 0.0:
            return complex(0.0, 0.0)
        raise ZeroDivisionError()
    return cexp(e * clog(b))


# indexed by op - FN0: SIN COS TAN SEC CSC COT ASIN ACOS ATAN SINH COSH TANH LN ABS SIGN FLOOR
# CEIL FACT. FNUM takes a float (natives may raise ValueError or return nan off their domain);
# FCPX takes a complex.
FNUM = (math.sin, math.cos, math.tan, fsec, fcsc, fcot, math.asin, math.acos, math.atan,  #@table 7
        fsinh, fcosh, ftanh, math.log, abs, fsign, ffloor, fceil, ffact)
FCPX = (csin, ccos, ctan, csec, ccsc, ccot, casin, cacos, catan, csinh, ccosh, ctanh,  #@table 5
        clog, nabs, cbad, cbad, cbad, cbad)


# -- the numeric evaluator (6.6) -----------------------------------------------------------------

def nprog(e, xs):                                               #@L 4
    # compile e into a flat program for nrun: one instruction per node, the root last; numbers
    # that are coefficients or exponents are folded into their parent's instruction. xs: a
    # tuple of SYM ids, the P_VAR slots. Raises Undefined for what has no numeric value (oo,
    # undef, relations, lists, calls, a symbol not in xs, a power too large to fold).
    N = K.N
    prog = []
    at = {}
    for m in postorder(e):
        t = N[m]
        op = t[0]
        if op <= K.FLT:
            continue                                            # made a constant on use
        if op == K.SYM:
            j = 0
            while j < len(xs) and xs[j] != m:
                j += 1
            if j == len(xs):
                raise K.Undefined()
            ins = (P_VAR, j)
        elif m == K.PI or m == K.E:
            ins = (P_CONST, math.pi if m == K.PI else EF)
        elif op == K.ADD:
            u = [P_ADD, cval(N[t[1]])]
            for j in range(2, len(t), 2):
                u.append(at[t[j]])
                u.append(cval(N[t[j + 1]]))
            ins = tuple(u)
        elif op == K.MUL:
            u = [P_MUL, cval(N[t[1]])]
            for j in range(2, len(t), 2):
                b = t[j]
                c = t[j + 1]
                w = N[c]
                if K.HUGE and KB.huge(b, c):        # beyond the float range (5.3, 6.1)
                    raise K.Undefined()
                for g in (b, c):
                    if g not in at and N[g][0] <= K.FLT and (g == b or w[2]):
                        at[g] = len(prog)
                        prog.append((P_CONST, cval(N[g])))
                u.append(at[b])
                if w[0] == K.NUM and not w[2]:
                    if w[3] == 1:
                        u.append(w[1])
                        u.append(0)
                    else:
                        u.append(qf(w[1], w[3]))
                        u.append((-1.0 if w[1] & 1 else 1.0) if w[3] & 1 else 0)
                elif w[0] == K.FLT and not w[2]:
                    u.append(int(w[1]) if w[1] % 1.0 == 0.0 else w[1])
                    u.append(0)
                else:                                           # symbolic or complex
                    u[-1] = len(prog)
                    prog.append((P_POW, at[b], at[c]))
                    u.append(1)
                    u.append(0)
            ins = tuple(u)
        elif op >= K.FN0:
            a = t[1]
            if a not in at:
                at[a] = len(prog)
                prog.append((P_CONST, cval(N[a])))
            ins = (P_FN, op - K.FN0, at[a])
        elif op == K.HOLD:
            at[m] = at[t[1]]
            continue
        else:
            raise K.Undefined()
        at[m] = len(prog)
        prog.append(ins)
    if e not in at:
        prog.append((P_CONST, cval(N[e])))
    return prog


def nrun(prog, vals, r=None):                                   #@L 4
    # run a program of nprog with the variable values vals (in the order of its xs): the root's
    # value, a float, or a complex when it is not real. Every value is checked for inf and nan
    # (the device may not raise); any failure raises Undefined. LEFTREAL[0] becomes 1 when a
    # value leaves the reals although its operands were real (8.3). r, if given, receives
    # every value (len(prog) slots).
    LEFTREAL[0] = 0
    n = len(prog)
    if r is None:
        r = [0.0] * n
    try:
        for i in range(n):
            ins = prog[i]
            op = ins[0]
            if op == P_CONST:
                v = ins[1]
            elif op == P_VAR:
                v = vals[ins[1]] + 0.0
            elif op == P_ADD:
                v = ins[1]
                for j in range(2, len(ins), 2):
                    v = v + ins[j + 1] * r[ins[j]]
            elif op == P_MUL:
                v = ins[1]
                for j in range(2, len(ins), 3):
                    b = r[ins[j]]
                    e = ins[j + 1]
                    if type(b) is complex:
                        w = cpow(b, e)
                    elif type(e) is int or b >= 0.0:
                        w = b ** e
                    elif ins[j + 2]:
                        w = ins[j + 2] * (-b) ** e                # the real odd root (6.2)
                    else:
                        w = cpow(b, e)
                        if w.imag:
                            LEFTREAL[0] = 1
                    v = v * w
            elif op == P_POW:
                b = r[ins[1]]
                e = r[ins[2]]
                if b == EF:
                    v = cexp(e) if type(e) is complex else math.exp(e)
                elif type(b) is complex or type(e) is complex:
                    v = cpow(b, e)
                elif b >= 0.0 or e % 1.0 == 0.0:
                    v = b ** e
                else:
                    v = cpow(b, e)
                    if v.imag:
                        LEFTREAL[0] = 1
            else:
                a = r[ins[2]]
                if type(a) is complex:
                    v = FCPX[ins[1]](a)                         #@calls 5
                else:
                    v = NAN
                    try:
                        v = FNUM[ins[1]](a)                     #@calls 7
                    except ValueError:
                        pass
                    if v != v:                                  # off the real domain
                        v = FCPX[ins[1]](complex(a, 0.0))       #@calls 5
                        if type(v) is complex and v.imag:
                            LEFTREAL[0] = 1
            if type(v) is complex and v.imag == 0.0:
                v = v.real
            if v - v != 0:
                raise K.Undefined()
            r[i] = v
    except (ZeroDivisionError, OverflowError, ValueError):
        raise K.Undefined()
    return r[n - 1]


def ntol(prog, r, t):                                           #@L 4
    # the absolute tolerance of the root after nrun(prog, ., r) (8.6 step 5): TOL relative at
    # each leaf, propagated through sums and products as an upper bound and through powers
    # and functions with their derivative; t (len(prog) slots) receives every node's. -1.0
    # when the point says nothing: a divisor, a log argument or a symbolic base within its
    # tolerance of 0, an argument within its tolerance of a jump (floor, sign) or of a
    # branch point (asin), or a function or power value whose tolerance is more than 1e-3 of
    # its size (a trig function of a huge, imprecise argument).
    try:
        for i in range(len(prog)):
            ins = prog[i]
            op = ins[0]
            v = nabs(r[i])
            if op <= P_VAR:
                w = TOL * v
            elif op == P_ADD:
                w = TOL * nabs(ins[1])
                for j in range(2, len(ins), 2):
                    w += nabs(ins[j + 1]) * t[ins[j]]
            elif op == P_MUL:
                u = nabs(ins[1])
                for j in range(2, len(ins), 3):
                    b = nabs(r[ins[j]])
                    d = t[ins[j]]
                    e = ins[j + 1]
                    if e > 0:
                        u *= (b + d) ** e
                    elif b > d:
                        u *= (b - d) ** e
                    else:
                        return -1.0
                w = u - v + TOL * v
            else:
                if op == P_POW:                     # d(b^e) = b^e (e db/b + ln(b) de)
                    a = r[ins[1]]
                    b = nabs(a)
                    d = t[ins[1]]
                    if b <= d:
                        return -1.0
                    g = math.fabs(math.log(b))
                    if type(a) is complex or a < 0.0:
                        g += 3.2                    # the argument of a non-positive base
                    w = v * (nabs(r[ins[2]]) * d / b + g * t[ins[2]])
                else:
                    f = ins[1] + K.FN0
                    a = r[ins[2]]
                    b = nabs(a)
                    d = t[ins[2]]
                    if f == K.TAN or f == K.COT:            # 1 + tan^2
                        g = (1.0 + v) * (1.0 + v)
                    elif f == K.SEC or f == K.CSC:          # sec*tan
                        g = v * (1.0 + v)
                    elif f == K.SINH or f == K.COSH or f == K.FACT:
                        g = (1.0 + v) * (1.0 if f != K.FACT else 2.0 + math.log(1.0 + b))
                    elif f == K.LN:
                        if b <= d:
                            return -1.0
                        g = 1.0 / b
                    elif f == K.ASIN or f == K.ACOS:
                        g = nabs(1.0 - a * a)
                        if g <= 2.0 * d * (1.0 + b):
                            return -1.0
                        g = 1.0 / math.sqrt(g)
                    elif f >= K.SIGN:                   # SIGN FLOOR CEIL: jumps
                        g = 0.0
                        b = a - math.floor(a) if f != K.SIGN else b
                        if b <= d or (f != K.SIGN and 1.0 - b <= d):
                            return -1.0
                    else:                               # SIN COS ATAN TANH ABS
                        g = 1.0 + v if type(a) is complex else 1.0
                    w = g * d
                w += TOL * v
                if w > 1e-3 * (1.0 + v):
                    return -1.0
            t[i] = w
    except (OverflowError, ZeroDivisionError, ValueError):
        return -1.0
    return t[len(prog) - 1]


def nev(e, env=None):                                           #@L 3
    # the numeric value of e (6.6): a float, or a complex when it is not real. env maps SYM
    # ids to numbers. Raises Undefined when e has no finite value there.
    xs = []
    vs = []
    if env:
        for k in env:                                           #@unordered-ok (slots only)
            xs.append(k)
            vs.append(env[k])
    return nrun(nprog(e, tuple(xs)), vs)


def nprobe(a, b=None):                                          #@L 3
    # the numeric probe (8.6 step 5, 8.7): a against b (None: against 0) at up to 3 points
    # where a is defined and every subexpression of a is real (LEFTREAL). Each symbol, in name
    # order, takes its own value from a fixed LCG in (0.31, 2.7), negated at the 3rd point,
    # then the signs alternate; 8 points at most. NO: |a - b| exceeds the propagated
    # tolerance at some point, or b fails where a is fine; LIKELY: they agree at every usable
    # point; UNKNOWN: no usable point. Builds no nodes.
    N = K.N
    sy = []
    for m in postorder(a if b is None else (a, b)):
        if N[m][0] == K.SYM:
            sy.append((N[m][1], m))
    sy.sort()
    xs = []
    for s in sy:
        xs.append(s[1])
    xs = tuple(xs)
    try:
        pa = nprog(a, xs)
    except K.Undefined:
        return UNKNOWN
    pb = None
    bad = False
    if b is not None:
        try:
            pb = nprog(b, xs)
        except K.Undefined:
            bad = True
    ra = [0.0] * len(pa)
    ta = [0.0] * len(pa)
    if pb is not None:
        rb = [0.0] * len(pb)
        tb = [0.0] * len(pb)
    s = 4321
    used = 0
    for j in range(8 if xs else 1):
        g = -1.0 if j == 2 or (j > 2 and not j & 1) else 1.0
        vs = []
        for m in xs:
            s = (s * 75 + 74) % 65537
            vs.append(g * (0.31 + 2.39 * s / 65537.0))
        try:
            v = nrun(pa, vs, ra)
        except K.Undefined:
            continue
        if LEFTREAL[0]:
            continue
        w = ntol(pa, ra, ta)
        if w < 0.0:
            continue
        if bad:
            return NO
        if pb is not None:
            try:
                v = v - nrun(pb, vs, rb)
            except K.Undefined:
                return NO
            u = ntol(pb, rb, tb)
            if u < 0.0:
                return NO
            w += u
        if nabs(v) > w:
            return NO
        used += 1
        if used == 3:
            return LIKELY
    return LIKELY if used else UNKNOWN
