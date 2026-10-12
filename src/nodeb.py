#@L 7
# CVNODEB: powers too large to fold (DESIGN 5.3, 6.1). node's constructors keep a cheap test in
# their hot paths and call this module only for a power that may not fold, or once the command
# has built one (K.HUGE). On the calculator it is an aux pack, loaded the first time a command
# meets a giant power, so a session without one never pays for this code.
K = None            #@lazy node   (node binds it when it imports this module)


def nval(x, q):                                                 #@L 7
    # (v, y) with x == q^v * y for a NUM tuple x and an int q >= 2, y free of q: v > 0 from
    # the content of a + b*i, v < 0 from the denominator (0 for x == 0). Divides by a
    # word-sized power of q first, so a large valuation costs about one pass per 30 bits.
    a = x[1]
    b = x[2]
    d = x[3]
    if ((a % q or b % q) and d % q) or (not a and not b):      # the common case: no q at all
        return (0, x)
    m = q
    k = 1
    while m * q < 0x40000000:
        m *= q
        k += 1
    v = 0
    while not a % m and not b % m:
        a //= m
        b //= m
        v += k
    while not a % q and not b % q:
        a //= q
        b //= q
        v += 1
    if not v:                                                   # gcd(a, b, d) == 1
        while not d % m:
            d //= m
            v -= k
        while not d % q:
            d //= q
            v -= 1
    return (v, (K.NUM, a, b, d) if v else x)


def huge(b, e=None):                                            #@L 7
    # True for the pair (b, e) of a power kept whole because its value is too large to fold
    # (5.3, 6.1): a NUM base under an integer, or a real base under a rational outside (0, 1),
    # with a weight 4*|floor(e)|*hexlen(|re|+|im|) over MAXBITS/16, as every kept prime has.
    # (A HOLD's display product, 2^3*3^2*5, has small ones.) huge(u): a term of the sum u
    # holds such a pair.
    N = K.N
    ps = (b, e)
    if e is None:
        ps = []
        t = N[b]
        for j in range(2, len(t), 2):
            x = N[t[j]]
            if x[0] == K.MUL:
                ps.extend(x[2:])
    for j in range(0, len(ps), 2):
        tb = N[ps[j]]
        te = N[ps[j + 1]]
        if tb[0] == K.NUM and te[0] == K.NUM and not te[2] and (
                te[3] == 1 or (not tb[2] and (te[1] < 0 or te[1] > te[3]))) and \
                4 * abs(te[1] // te[3]) * len('%x' % (abs(tb[1]) + abs(tb[2]))) > K.MAXBITS >> 4:
            return True
    return False


def hpow(c, b, e, st, rad):                                     #@L 6
    # mul_'s rule 2 for b^e, b a NUM and e an integer, when the result may be too large to fold
    # (6.1): the new coefficient, or None to keep the pair (5.3). 0^n is 0 at once. A real base
    # gives its primes to rad when a prime power of the result could be kept whole by the fold
    # rule (hfold); a non-real one splits off its real content g/d (onto st) and is kept whole
    # while it is over the npowi estimate. Anything else folds as before.
    tb = K.N[b]
    te = K.N[e]
    if not tb[1] and not tb[2]:
        if te[1] < 0:
            raise K.Undefined()                                 # 0^-n
        return K.nmul(c, K.Q0)
    n = te[1] if te[1] > 0 else -te[1]
    u = n > 1 and (tb[3] > 1 or tb[1] > 1 or tb[1] < -1 or tb[2] > 1 or tb[2] < -1 or
                   (tb[1] and tb[2]))                           # a non-unit exact base
    a = tb[1] if tb[1] > 0 else -tb[1]
    h = len('%x' % a) + len('%x' % tb[3])
    if u and tb[2]:                                             # non-real: the npowi estimate
        g = a                                                   # decides (6.1)
        if a < tb[2] or a < -tb[2]:
            a = tb[2] if tb[2] > 0 else -tb[2]
        if 4 * n * len('%x' % (a if a > tb[3] else tb[3])) > K.MAXBITS:
            h = tb[2]
            while h:
                g, h = h, g % h
            g = g if g > 0 else -g
            if g > 1 or tb[3] > 1:                              # ((a+bi)/d)^n: the real
                st.append((K.mk((K.NUM, g, 0, tb[3])), e))      # content g/d apart
                st.append((K.mk((K.NUM, tb[1] // g, tb[2] // g, 1)), e))
                return c
            if len('%x' % n) > K.MAXBITS >> 2:
                raise K.CasError(K.M_BIG)                       # the exponent itself
            K.HUGE = 1
            return None                                         # keep the pair (5.3)
    elif u and 24 * n * h > K.MAXBITS:
        # real: could a prime power q^(n f) of the result be kept whole by the rule at the end
        # of mul_? For q >= 16 its weight 4 n f hexlen(q) is at most 2 n log2(q^f); below 16
        # the valuations are measured. If it could, the primes of the base go to rad (6.1).
        x = tb
        g = 0
        w = 0
        for q in (2, 3, 5, 7, 11, 13):
            v, x = nval(x, q)
            v = v if v > 0 else -v
            g = v if v > g else g
            w += v
        g *= 4
        v = 8 * len('%x' % (a if a > tb[3] else tb[3]))
        if n * (v if v > g else g) > K.MAXBITS or n * (8 * h + 4 * w) > K.MAXBITS << 1:
            c = K.nneg(c) if tb[1] < 0 and n & 1 else c
            for j in (0, 1):
                f = tb[3] if j else a
                if len('%x' % f) <= 1000:
                    f = K.ifac(f)
                else:                       # over 4,000 bits only the primes below 256 come
                    x = (K.NUM, f, 0, 1)    # out and the rest stays one cofactor, so the cost
                    f = []                  # is linear in the size of the base
                    q = 2
                    while q < 256:
                        v, x = nval(x, q)
                        if v:
                            f.append(q)
                            f.append(v)
                        q += 1 if q == 2 else 2
                    if x[1] > 1:
                        f.append(x[1])
                        f.append(1)
                for i in range(0, len(f), 2):
                    rad[f[i]] = K.nadd(rad.get(f[i], K.Q0),
                                       (K.NUM, f[i + 1] * (-te[1] if j else te[1]), 0, 1))
            return c
    return K.nmul(c, K.npowi(tb, te[1]))


def hfold(c, rad):                                              #@L 6
    # The fold rule at the end of mul_ (6.1) when its answer could differ from folding every
    # prime: (c, lst), lst the (s, p, q) of q^(p/s) left as pairs. A prime power q^n folds into
    # c when its weight 4*|n|*hexlen(q) is at most MAXBITS (the npowi estimate, prime by
    # prime); otherwise q keeps its whole exponent as a pair (5.3), and c gives it its factors
    # q. If the folding weights over MAXBITS/16 total more than MAXFOLD = 2*MAXBITS, those
    # primes are kept whole as well (bounded memory). A coefficient over 2^16384 (a product of
    # folded numbers) may hide such a power: it is searched for the primes below 256, and keeps
    # its value when none is kept whole.
    k = c
    g = not rad
    if c[0] == K.NUM and (rad or len('%x%x%x' % c[1:]) > 4096):
        q = 2 if len('%x%x%x' % c[1:]) > 4096 else 256
        while q < 256:
            v, c = nval(c, q)
            if v:
                rad[q] = K.nadd(rad.get(q, K.Q0), (K.NUM, v, 0, 1))
            q += 1 if q == 2 else 2
        for q in rad:                                           #@unordered-ok (per prime)
            v, c = nval(c, q)
            if v:
                rad[q] = K.nadd(rad[q], (K.NUM, v, 0, 1))
    w = 0                               # the weights over MAXBITS >> 4 that would fold
    for q in rad:                                               #@unordered-ok (a sum)
        n = rad[q][1] // rad[q][3]
        n = 4 * len('%x' % q) * (n if n > 0 else -n)
        if n > K.MAXBITS:
            g = False
        elif n > K.MAXBITS >> 4:
            w += n
    if w > K.MAXBITS << 1:              # too much to fold at once: those primes stay too
        g = False
    if g:                               # only the search found primes, and all fold
        return (k, [])
    lst = []
    for q in rad:                                               #@unordered-ok (sorted later)
        x = rad[q]
        n = x[1] // x[3]
        v = 4 * len('%x' % q) * (n if n > 0 else -n)
        if v > K.MAXBITS or (w > K.MAXBITS << 1 and v > K.MAXBITS >> 4):
            if len('%x' % x[1]) + len('%x' % x[3]) > K.MAXBITS >> 2:
                raise K.CasError(K.M_BIG)                       # the exponent itself (6.1)
            K.HUGE = 1
            lst.append((x[3], x[1], q))                         # q^x kept whole
            continue
        if n:
            c = K.nmul(c, (K.NUM, q ** n, 0, 1) if n > 0 else (K.NUM, 1, 0, q ** -n))
        if x[1] - n * x[3]:
            lst.append((x[3], x[1] - n * x[3], q))
    return (c, lst)


def hmpow(tb, te, st):                                          #@L 6
    # mul_ for (prod B^X)^e, tb a MUL tuple: when its coefficient is 1, e is a real rational and
    # every pair is a power kept whole of a real base (every such B is > 0), push the B^(X e)
    # onto st and return True
    if tb[1] != K.ONE or te[0] != K.NUM or te[2]:
        return False
    for j in range(2, len(tb), 2):
        if not huge(tb[j], tb[j + 1]) or K.N[tb[j]][2]:
            return False
    for j in range(2, len(tb), 2):
        st.append((tb[j], K.mk(K.nmul(K.N[tb[j + 1]], te))))
    return True


def hsum(acc, s):                                               #@L 7
    # add_'s rule (5.3) once the command has built a power kept whole: a term's coefficient
    # gives its factors of the term's real bases kept whole to their exponents (regrouped as
    # rule 11), and terms that then coincide are collected again, to a fixed point. A term is
    # left when an exponent would have to fold, or a regrouped base meets another pair.
    # At level 7 under add_ this calls nothing: it appends (f, args) to s and returns True;
    # add_ makes that call and puts its answer in its place (tiefix, which sorts in place, its
    # list), and hsum runs again from the start with s, the answers so far. acc changes when
    # no call is missing; then the result is None.
    N = K.N
    a = dict(acc)
    st = list(a)                                                #@unordered-ok (a fixed point)
    i = 0
    fs = {}                                     # base -> its primes (ifac), in this run
    while st:
        e = st.pop()
        m = a.get(e)
        t = N[e]
        if m is None or m[0] or t[0] != K.MUL:
            continue
        hl = []
        ps = []
        g = 0
        for j in range(2, len(t), 2):
            f = N[t[j]]
            w = N[t[j + 1]]
            if f[0] or f[2] or w[0] or w[2] or not (w[3] == 1 or w[1] < 0 or w[1] > w[3]) or \
                    4 * abs(w[1] // w[3]) * len('%x' % abs(f[1])) <= K.MAXBITS >> 4:
                ps.append((K.H[t[j]], t[j], t[j + 1]))          # not a real base kept whole
                continue
            f = f[1]
            if len('%x' % f) > 1000:
                f = (f, 1)                                      # as hpow's cofactor
            elif f in fs:
                f = fs[f]                                       # asked for in this run
            elif i == len(s):
                s.append((K.ifac, (f,)))
                return True
            else:
                fs[f] = s[i]
                f = s[i]
                i += 1
            for k in range(0, len(f), 2):
                q = f[k]
                v = 0
                if not ((m[1] % q or m[2] % q) and m[3] % q):   # else nval's common case
                    if i == len(s):
                        s.append((nval, (m, q)))
                        return True
                    v, m = s[i]
                    i += 1
                x = (K.NUM, w[1] + v * w[3], 0, w[3]) if v else w
                if v:                           # the new weight must stay over MAXBITS/16
                    v = x[1] // x[3]
                    v = 4 * len('%x' % q) * (v if v > 0 else -v) > K.MAXBITS >> 4
                    g = 1 if g >= 0 and v else -1
                hl.append((x[3], x[1], q))
        if g <= 0:                      # nothing to move, or an exponent would have to fold
            continue
        hl.sort()
        new = []
        j = 0
        while j < len(hl):                                      # rule 11: one base per exponent
            x = hl[j]
            f = 1
            while j < len(hl) and hl[j][:2] == x[:2]:
                f *= hl[j][2]
                j += 1
            new.append((K.NUM, f, 0, 1))
            new.append((K.NUM, x[1], 0, x[0]))
        for j in range(len(new)):
            if i == len(s):
                s.append((K.mk, (new[j],)))
                return True
            new[j] = s[i]
            i += 1
        for j in range(0, len(new), 2):
            ps.append((K.H[new[j]], new[j], new[j + 1]))
        ps.sort()
        if i == len(s):
            s.append((K.tiefix, (ps,)))
            return True
        ps = s[i]
        i += 1
        out = [K.MUL, K.ONE]
        for j in range(len(ps)):
            if j and ps[j][1] == ps[j - 1][1]:
                out = None                      # a regrouped base meets another pair: keep e
                break
            out.append(ps[j][1])
            out.append(ps[j][2])
        if out is None:
            continue
        if i == len(s):
            s.append((K.mk, (tuple(out),)))
            return True
        del a[e]
        e = s[i]
        i += 1
        if e in a:
            if i == len(s):
                s.append((K.nadd, (a[e], m)))
                return True
            m = s[i]
            i += 1
            st.append(e)
        a[e] = m
    if i:
        acc.clear()
        acc.update(a)
    return None


def hln(a):                                                     #@L 6
    # fn_'s ln(a) for a MUL a with powers kept whole (6.1): for a positive number, by primes as
    # for a NUM (6.4), numerator and denominator apart, g*ln(q) with q^g their product. The
    # terms to add: [ln(a)] when there is no such split (not such a number, q itself too
    # large to fold).
    N = K.N
    t = N[a]
    x = {} if not (N[t[1]][0] or N[t[1]][2]) and N[t[1]][1] > 0 else None
    for j in range(1, len(t) if x is not None else 0):
        w = N[t[j]]
        if j > 1 and not j & 1 and (not huge(t[j], t[j + 1]) or w[2] or N[t[j + 1]][3] != 1):
            x = None
            break
        if j == 1 or not j & 1:
            for i in (1, 3) if j == 1 else (1,):
                f = K.ifac(w[i]) if len('%x' % w[i]) <= 1000 else (w[i], 1)
                for h in range(0, len(f), 2):
                    x[f[h]] = x.get(f[h], 0) + f[h + 1] * (
                        (1 if i == 1 else -1) if j == 1 else N[t[j + 1]][1])
    lst = []
    for s in (1, -1) if x else ():      # numerator, then denominator: g * ln(q)
        p = 0
        for q in x:                                             #@unordered-ok (a gcd)
            h = x[q] * s
            while h > 0:
                p, h = h, p % h
        q = 1
        w = 0
        for h in x:                                             #@unordered-ok (a product)
            if p and x[h] * s > 0:
                w += 4 * len('%x' % h) * (x[h] * s // p)
                q = q * h ** (x[h] * s // p) if w <= K.MAXBITS else q
        if w > K.MAXBITS:
            lst = []                    # q itself would be kept whole: no split
            break
        if q > 1:
            v = K.mk((K.LN, K.mk((K.NUM, q, 0, 1))))
            lst.append(v if p * s == 1 else K.mk((K.MUL, K.mk((K.NUM, p * s, 0, 1)), v, K.ONE)))
    return lst or [K.mk((K.LN, a))]


def hker(b, e, ex):                                             #@L 4
    # norm.normal's kernel for the pair (b, e) of a power kept whole (5.3): b^e, or b^-e under
    # normal (ex 0) when e < 0, the power being that kernel to the -1; else 0 (a HOLD's small
    # powers fold)
    w = K.N[e]
    if not huge(b, e):
        return 0
    c = K.mul_(K.ONE, [(b, K.mk(K.nneg(w)) if w[1] < 0 and not ex else e)])
    return c if K.N[c][0] == K.MUL and K.N[c][1] == K.ONE else 0
