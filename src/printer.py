# printer.py (CVPRINT, alias PR): the 1D printer, display order, decimal formatter, messages.
# DESIGN.md section 12. T1.4 wrote the decimal formatter (dec10, fdec10, section 12.6); T1.7
# wrote text, items, the display-order keys and record (docs/notes/T1.7.md).
#
# text(e, ctx) is the answer: canonical input-language text that re-parses (answer path, inert
# g_eval, the same angle mode) to e again (12.5). items(n, need, c) is one node's display
# sequence: literal strings and (child id, precedence) pairs, in display order. Display order
# is computed here, never stored in the nodes (12.3); display-only nodes (a flipped sum, a
# degree-mode argument) are built through the constructors and die with the command.
import math

import node as K
import alg as A
import parse as P

# dec10 refuses integers of 2^DECBITS or more (over about 4,000 decimal digits): str() of a big
# int is quadratic and cannot be cancelled (section 6.1). Such a number's text is over MAXTEXT
# anyway, so the answer is Done and no decimal line is lost. istr uses the same guard.
DECBITS = 13287
MAXTEXT = 4000
LONGPOLY = 70               # a longer (sum)/integer prints term by term (fmt 1.4)

# records (kind, text, approx, flags) (10.4, 13.6). The flag bits are run's (T1.6); F_SOLN is
# the registry flag P.F_SOLN, which the runner passes for an F_SOLN command.
R_ANS = 'ans'
R_MSG = 'msg'
F_PLUSC = 1                 # an antiderivative: the view draws + C
F_PURGEHINT = 2             # a store into a working variable
F_APPROX = 4                # the answer is numeric although the input had no float
F_DEG = 8                   # degree mode
F_SOLN = 16                 # the result of solve: [] and true are messages
M_DONE = 'Done'
M_UNDEF = 'Undefined'
M_NOSOL = 'No solution'
M_EVERY = 'Every %s is a solution'
M_DNE = 'Does not exist: %s from the left, %s from the right'
M_OSC = 'No limit (it oscillates)'
M_DIVG = ('Diverges (the improper integral does not converge)',
          'Diverges (the integrand is unbounded on the interval)',
          'Diverges (the terms do not go to 0)')
SIDE = 40                   # characters of a one-sided value in the DNE message

# output precedence: the rpn levels of section 7.7. A node whose own level is below the need of
# its place is wrapped in parentheses.
Q_ARG = 1                   # a call argument or a list element (above the comma)
Q_REL = 3
Q_ADD = 4
Q_MUL = 5
Q_NEG = 6                   # prefix minus; also the need of a factor b^1 of a product
Q_POW = 7
Q_POST = 8                  # postfix !; also the need of a base b^e
Q_ATOM = 9                  # also the need of a symbolic exponent: e^(2*x), not e^2*x

FNAME = ('sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'asin', 'acos', 'atan', 'sinh', 'cosh',
         'tanh', 'ln', 'abs', 'sign', 'floor', 'ceil')
CNAME = ('pi', 'e', 'oo', 'undef', 'true', 'false')
RNAME = ('=', '!=', '<', '<=')
TRIGORD = (0, 1, 4, 2, 3, 5)       # by op - SIN: sin < cos < sec < csc < tan < cot (12.3)
MVPREF = {'x': 0, 't': 1, 'theta': 2}
R180 = (K.NUM, 180, 0, 1)          # degree mode (6.5): an argument v prints as v*180/pi
D180 = (K.NUM, 1, 0, 180)
Q1 = K.Q1


def dec10(p, q, nd=10):                                         #@L 7
    # p/q (int p, int q > 0) -> nd significant digits, rounded half-up (ties away from zero),
    # integers only. Scientific 'd.ddE-5' / 'dE10' when the rounded value has |x| >= 1e10 or
    # |x| < 1e-4; otherwise fixed. No trailing zeros, no '+'. OverflowError over DECBITS.
    if p == 0:
        return '0'
    s = ''
    if p < 0:
        s = '-'
        p = -p
    if p >> DECBITS or q >> DECBITS:
        raise OverflowError('dec10')
    e = len(str(p)) - len(str(q))          # 10^e <= p/q < 10^(e+1), or e is one too big
    if e >= 0:
        if p < q * 10 ** e:
            e -= 1
    elif p * 10 ** (-e) < q:
        e -= 1
    k = nd - 1 - e                          # m = p/q * 10^k has nd digits before rounding
    if k >= 0:
        m, r = divmod(p * 10 ** k, q)
        den = q
    else:
        den = q * 10 ** (-k)
        m, r = divmod(p, den)
    if 2 * r >= den:                        # half-up
        m += 1
        if m == 10 ** nd:                   # carry into a new decade: 9.99..95 -> 10
            m //= 10
            e += 1
    dg = str(m)
    j = len(dg)
    while j > 1 and dg[j - 1] == '0':
        j -= 1
    dg = dg[:j]
    if e >= 10 or e < -4:                   # scientific: d.ddddE+-n
        t = dg[0]
        if len(dg) > 1:
            t = t + '.' + dg[1:]
        return s + t + 'E' + str(e)
    if e < 0:
        return s + '0.' + '0' * (-e - 1) + dg
    if len(dg) <= e + 1:
        return s + dg + '0' * (e + 1 - len(dg))
    return s + dg[:e + 1] + '.' + dg[e + 1:]


def fdec10(x, nd=10):                                           #@L 6
    # float x -> dec10 of its exact binary value (math.frexp is native: no frame). The digits
    # are the same on the device and the desktop by construction. inf raises OverflowError and
    # nan ValueError (int() of them); nrun has already rejected both (section 6.6).
    if x == 0.0:
        return '0'
    m, ex = math.frexp(x)                   # x = m * 2**ex, 0.5 <= |m| < 1
    p = int(m * 9007199254740992.0)         # m * 2**53: exact
    ex -= 53
    if ex >= 0:
        return dec10(p * 2 ** ex, 1, nd)
    return dec10(p, 2 ** (-ex), nd)


# -- leaves: number text, keys and small predicates -----------------------------------------------

def istr(a):                                                    #@L 7
    # '%d' of the int a >= 0, or None over the str() size guard (6.1): the answer is then Done
    if a >> DECBITS:
        return None
    return '%d' % a


def imstr(b, d):                                                #@L 7
    # the text of the imaginary number b*i/d (b > 0): i, 3*i, i/2, 3*i/2; None if too big
    if b >> DECBITS or d >> DECBITS:
        return None
    s = 'i' if b == 1 else '%d*i' % b
    return s if d == 1 else s + '/%d' % d


def csgn(t):                                                    #@L 7
    # the display sign of a number tuple: its real part, or its imaginary part if that is 0
    v = t[1] if t[1] else t[2]
    return -1 if v < 0 else 1


def xpow(t, mv):                                                #@L 7
    # the x_power key of a sum term t (12.3): floor(60 * the rational exponent of the main
    # variable mv in t); 0 when t has no numeric power of mv as a factor
    if not mv:
        return 0
    if t == mv:
        return 60
    u = K.N[t]
    if u[0] != K.MUL:
        return 0
    for j in range(2, len(u), 2):
        if u[j] == mv:
            w = K.N[u[j + 1]]
            if w[0] > K.FLT or w[2]:
                return 0
            if w[0] == K.NUM:
                return 60 * w[1] // w[3]
            return int(60.0 * w[1] // 1.0)
    return 0


def tkey(t):                                                    #@L 7
    # the tie-break of sum terms with equal x_power (before H): (total degree, kind). The
    # total degree is 60 * the sum of the numeric exponents of the symbols in the product t
    # (b^2 before b); the kind is the op code of t, or of the base of a one-pair product, with
    # the trig functions in the order sin cos sec csc tan cot (sin(x)^2+cos(x)^2)
    N = K.N
    u = N[t]
    s = 0
    b = t
    if u[0] == K.SYM:
        s = 60
    elif u[0] == K.MUL:
        if len(u) == 4:
            b = u[2]
        for j in range(2, len(u), 2):
            w = N[u[j + 1]]
            if N[u[j]][0] == K.SYM and w[0] <= K.FLT and not w[2]:
                if w[0] == K.NUM:
                    s += 60 * w[1] // w[3]
                elif w[0] == K.FLT:
                    s += int(60.0 * w[1] // 1.0)
    o = N[b][0]
    if K.SIN <= o <= K.COT:
        o = K.SIN + TRIGORD[o - K.SIN]
    return (s, o)


def pkey(b):                                                    #@L 7
    # (name, degree, a, d) when the sum b is a polynomial in one symbol with real rational
    # coefficients and constant term a/d; else None (FlowCE poly_key, 12.3)
    N = K.N
    t = N[b]
    c = N[t[1]]
    if c[0] != K.NUM or c[2]:
        return None
    v = 0
    dg = 0
    for j in range(2, len(t), 2):
        k = N[t[j + 1]]
        if k[0] != K.NUM or k[2]:
            return None
        u = N[t[j]]
        if u[0] == K.SYM:
            x = t[j]
            e = 1
        elif u[0] == K.MUL and len(u) == 4 and u[1] == K.ONE and N[u[2]][0] == K.SYM:
            w = N[u[3]]
            if w[0] != K.NUM or w[2] or w[3] != 1 or w[1] < 1:
                return None
            x = u[2]
            e = w[1]
        else:
            return None
        if v and x != v:
            return None
        v = x
        if e > dg:
            dg = e
    return (N[v][1], dg, c[1], c[3])


def scont(b):                                                   #@L 7
    # (g, l): the rational content g/l of the sum b (FlowCE sum_content, fmt 1.3): the gcd of
    # the numerators of its constant and coefficients over the lcm of their denominators;
    # None when it is 1 or when a coefficient is not a real rational (a float, i)
    N = K.N
    t = N[b]
    g = 0
    l = 1
    for j in range(1, len(t), 2):
        w = N[t[j]]
        if w[0] != K.NUM or w[2]:
            return None
        a = w[1] if w[1] > 0 else -w[1]
        while a:
            g, a = a, g % a
        d = w[3]
        x = l
        while d:
            x, d = d, x % d
        l = l // x * w[3]
    if g == 1 and l == 1:
        return None
    return (g, l)


def hasi(t, k):                                                 #@L 7
    # True if the sum term k*t contains i: a non-real coefficient, or a non-real number in t
    N = K.N
    if N[k][2]:
        return True
    if not t:
        return False
    seen = bytearray(t + 1)
    st = [t]
    while st:
        m = st.pop()
        if seen[m]:
            continue
        seen[m] = 1
        u = N[m]
        if u[0] <= K.FLT:
            if u[2]:
                return True
        elif u[0] >= K.COMP:
            for j in range(1, len(u)):
                st.append(u[j])
    return False


def pickmv(e):                                                  #@L 7
    # the main variable of e (12.3): x, then t, then theta, then the first name; 0 if none
    N = K.N
    V = K.V
    if not V[e]:
        return 0
    seen = bytearray(e + 1)
    st = [e]
    best = 0
    bk = None
    while st:
        m = st.pop()
        if seen[m]:
            continue
        seen[m] = 1
        u = N[m]
        if u[0] == K.SYM:
            r = MVPREF.get(u[1])
            k = (3, u[1]) if r is None else (r, '')
            if bk is None or k < bk:
                bk = k
                best = m
        elif u[0] >= K.COMP:
            for j in range(2 if u[0] == K.CALL else 1, len(u)):  # (not a call's name)
                if V[u[j]]:
                    st.append(u[j])
    return best


def bare(e):                                                    #@L 7
    # True if the list e prints without brackets at the top level (12.1): solutions, x=1,x=2
    # or [x=1,y=2],[x=3,y=4]. One element only when it is a relation (FlowCE's x=2).
    N = K.N
    t = N[e]
    n = len(t) - 1
    if n < 1:
        return False
    for j in range(1, len(t)):
        u = N[t[j]]
        if K.EQ <= u[0] <= K.LE:
            continue
        if n < 2 or u[0] != K.LST or len(u) < 2:
            return False
        for i in range(1, len(u)):
            if not K.EQ <= N[u[i]][0] <= K.LE:
                return False
    return True


def cfmt(r, i):                                                 #@L 7
    # 'a+bi' from the decimal texts of the parts (None: the part is 0)
    if i is None:
        return '0' if r is None else r
    if i == '1':
        i = ''
    elif i == '-1':
        i = '-'
    if r is None:
        return i + 'i'
    if i[:1] == '-':
        return r + i + 'i'
    return r + '+' + i + 'i'


def fstr(x):                                                    #@L 6
    # FLT text (12.4): 15 significant digits of the exact binary value, as fdec10(x, 15), with
    # a point or an exponent so that it re-lexes as a float (D8): 2.0, not 2
    if x == 0.0:
        return '0.0'
    m, ex = math.frexp(x)
    p = int(m * 9007199254740992.0)
    ex -= 53
    s = dec10(p * 2 ** ex, 1, 15) if ex >= 0 else dec10(p, 2 ** (-ex), 15)
    if '.' in s or 'E' in s:
        return s
    return s + '.0'


def mainv(e, ctx):                                              #@L 6
    # the main variable (12.3): the command's (ctx[X_MV], a SYM id), else pickmv(e); 0 if none
    m = ctx[P.X_MV] if ctx is not None and len(ctx) > P.X_MV else None
    if type(m) is int and 0 < m < K.NN and K.N[m] is not None and K.N[m][0] == K.SYM:
        return m
    return pickmv(e)


def sorder(n, mv):                                              #@L 6
    # The display order of the terms of the sum n (12.3): a list of (t, k), with t a term id
    # (0 for the real constant, K.I for the imaginary part of a complex constant) and k its
    # coefficient id. Descending x_power, the constant last; a series (an O() term)
    # ascending, O() last. Ties: tkey (total degree, kind), then H, then the id. mv: the
    # main variable; a sum free of it uses its own (pickmv): descending powers of y.
    N = K.N
    t = N[n]
    if not mv or K.free_of(n, mv):
        mv = pickmv(n)
    sg = -1                                     # descending; 1 for a series
    for j in range(2, len(t), 2):
        if N[t[j]][0] == K.BIGO:
            sg = 1
    lst = []
    if t[1] != K.ZERO:                          # the constant: last, or first in a series
        c = N[t[1]]
        r = 1 if sg < 0 else 0
        if not c[2]:
            lst.append((0, 0, r, 0, 0, 0, 0, 0, t[1]))
        elif c[0] == K.NUM:
            if c[1]:
                lst.append((0, 0, r, 0, 0, 0, 0, 0, K.mk(K.nnorm(c[1], 0, c[3]))))
            lst.append((0, 0, r + 1, 0, 0, 0, 1, K.I, K.mk(K.nnorm(c[2], 0, c[3]))))
        else:
            if c[1]:
                lst.append((0, 0, r, 0, 0, 0, 0, 0, K.mk((K.FLT, c[1], 0.0))))
            lst.append((0, 0, r + 1, 0, 0, 0, 1, K.I, K.mk((K.FLT, c[2], 0.0))))
    for j in range(2, len(t), 2):
        m = t[j]
        x = tkey(m)
        lst.append((1 if N[m][0] == K.BIGO else 0, sg * xpow(m, mv), 0 if sg < 0 else 2,
                    sg * x[0], x[1], K.H[m], m, m, t[j + 1]))
    lst.sort()
    out = []
    for r in lst:
        out.append((r[7], r[8]))
    return out


def rstr(t):                                                    #@L 5
    # (negative, unsigned text) of the real number tuple t: 3, 3/4, 0.5; None if too big
    if t[0] == K.FLT:
        return (t[1] < 0, fstr(-t[1] if t[1] < 0 else t[1]))
    a = t[1]
    s = istr(-a if a < 0 else a)
    if s is None or t[3] == 1:
        return None if s is None else (a < 0, s)
    d = istr(t[3])
    return None if d is None else (a < 0, s + '/' + d)


# -- products (12.3) -----------------------------------------------------------------------------

def pdisp(n, k, c):                                             #@L 5
    # The display of a product: n a MUL with k None, or the sum term k*n (k a number id).
    # Returns (negative, seq, prec): seq is the unsigned display (literal strings and (child,
    # need) pairs), prec its precedence; None for a number too big to print. The coefficient
    # prints as p*m/q (x^3/6, 3*x^5/40), the factors in rank order (numbers, pi, variables,
    # e^ and 2^x, the rest: polynomials by poly_key, then trig by argument size and sin cos
    # sec csc tan cot, then H), a numeric negative exponent in the denominator, +-1/2 as sqrt,
    # and LN10^-m with LN factors whose exponents sum to m as log (12.4). A sum factor under
    # an integer exponent whose displayed lead is negative is flipped: -(P)*u -> (-P)*u.
    N = K.N
    t = N[n]
    if t[0] == K.MUL:
        q = N[t[1]] if k is None else K.nmul(N[k], N[t[1]])
        ps = []
        for j in range(2, len(t), 2):
            ps.append((t[j], t[j + 1]))
    else:
        q = Q1 if k is None else N[k]
        ps = [(n, K.ONE)]
    neg = False
    lg = 0
    for p in ps:
        w = N[p[1]]
        if p[0] == K.LN10 and w[0] == K.NUM and not w[2] and w[3] == 1 and w[1] < 0:
            s = 0
            for r in ps:
                v = N[r[1]]
                if r[0] != K.LN10 and N[r[0]][0] == K.LN and v[0] == K.NUM and not v[2] and \
                        v[3] == 1 and v[1] > 0:
                    s += v[1]
            lg = 1 if s == -w[1] else 0
    fs = []
    for p in ps:
        b = p[0]
        e = p[1]
        if lg and b == K.LN10:
            continue
        w = N[e]
        tb = N[b]
        iv = 1 if w[0] <= K.FLT and not w[2] and w[1] < 0 else 0
        if tb[0] == K.ADD and w[0] == K.NUM and not w[2] and w[3] == 1:
            o = sorder(b, c[1])
            g = csgn(N[o[0][1]])
            if len(o) == 2 and g < 0 and csgn(N[o[1][1]]) > 0:
                g = 1
            if g < 0:                                   # the displayed lead is negative
                b = K.neg_(b)
                tb = N[b]
                if w[1] & 1:
                    neg = not neg
        ob = tb[0]
        if ob <= K.FLT and w[0] <= K.FLT:               # a numeric radical
            r = (0, 0, '', tb[1] if ob == K.NUM and not tb[2] and tb[3] == 1 else 0, 0.0, 0)
        elif b == K.PI:
            r = (1, 0, '', 0, 0.0, 0)
        elif ob == K.SYM:
            r = (2, 0, tb[1], 0, 0.0, 0)
        elif b == K.E or ob <= K.FLT:                   # e^u, 2^x
            r = (3, 0, '', 0, 0.0, 0)
        elif K.SIN <= ob <= K.COT:
            r = (4, 1, '', A.size(tb[1]), 0.0, TRIGORD[ob - K.SIN])
        else:
            r = None
            if ob == K.ADD:
                r = pkey(b)
            if r is None:
                r = (4, 2, '', 0, 0.0, 0)
            else:                                       # lower degree, smaller |c0|, c0 < 0
                r = (4, 0, r[0], r[1], A.qf(r[2] if r[2] >= 0 else -r[2], r[3]),
                     0 if r[2] < 0 else 1)
        lf = 1 if (lg and ob == K.LN and b != K.LN10 and w[0] == K.NUM and not w[2] and
                   w[3] == 1 and w[1] > 0) else 0
        fs.append((iv,) + r + (K.H[b], b, e, lf))
    fs.sort()
    # the coefficient: the numerator text cs (None: omitted, a real 1) and the denominator dq
    dq = 1
    cp = Q_ATOM
    if q[0] == K.NUM:
        a = q[1]
        bb = q[2]
        dq = q[3]
        if not bb:
            if a < 0:
                neg = not neg
                a = -a
            cs = istr(a)
            if cs is None:
                return None
            if a == 1:
                cs = None
        elif not a:
            if bb < 0:
                neg = not neg
                bb = -bb
            cs = imstr(bb, 1)
            if cs is None:
                return None
            if bb != 1:
                cp = Q_MUL
        else:
            if a < 0:
                neg = not neg
                a = -a
                bb = -bb
            cs = istr(a)
            x = imstr(bb if bb > 0 else -bb, 1)
            if cs is None or x is None:
                return None
            cs = '(' + cs + ('+' if bb > 0 else '-') + x + ')'
    else:
        re = q[1]
        im = q[2]
        if not im:
            if re < 0:
                neg = not neg
                re = -re
            cs = fstr(re)
        elif not re:
            if im < 0:
                neg = not neg
                im = -im
            cs = fstr(im) + '*i'
            cp = Q_MUL
        else:
            if re < 0:
                neg = not neg
                re = -re
                im = -im
            cs = '(' + fstr(re) + ('+' + fstr(im) if im > 0 else '-' + fstr(-im)) + '*i)'
    # the factors, numerator into seq and denominator into dseq
    seq = []
    dseq = []
    ng = 0
    nd = 0
    prec = cp
    if cs is not None:
        seq.append(cs)
        ng = 1
    if dq != 1:
        x = istr(dq)
        if x is None:
            return None
        dseq.append(x)
        nd = 1
    for f in fs:
        iv = f[0]
        b = f[8]
        e = f[9]
        w = N[e]
        tb = N[b]
        g = dseq if iv else seq
        if nd if iv else ng:
            g.append('*')
        if f[10]:
            g.append('log(')
            g.append((tb[1], Q_ARG))
            g.append(')')
            p = Q_ATOM
            if w[1] != 1:
                x = istr(w[1])
                if x is None:
                    return None
                g.append('^' + x)
                p = Q_POW
        elif w[0] == K.NUM and not w[2]:
            a = -w[1] if iv else w[1]
            if a == 1 and w[3] == 1:
                g.append((b, Q_NEG))
                p = Q_POST
            elif a == 1 and w[3] == 2:
                g.append('sqrt(')
                g.append((b, Q_ARG))
                g.append(')')
                p = Q_ATOM
            else:
                x = istr(a)
                y = istr(w[3])
                if x is None or y is None:
                    return None
                g.append((b, Q_POST))
                g.append('^' + x if w[3] == 1 else '^(' + x + '/' + y + ')')
                p = Q_POW
        elif w[0] == K.FLT and not w[2]:
            g.append((b, Q_POST))
            g.append('^' + fstr(-w[1] if iv else w[1]))
            p = Q_POW
        else:
            g.append((b, Q_POST))
            g.append('^')
            g.append((e, Q_ATOM))
            p = Q_POW
        if iv:
            nd += 1
        else:
            ng += 1
            prec = p
    if not ng:
        seq.append('1')
        ng = 1
        prec = Q_ATOM
    if ng > 1:
        prec = Q_MUL
    if nd:
        seq.append('/')
        if nd > 1:
            seq.append('(')
        for x in dseq:
            seq.append(x)
        if nd > 1:
            seq.append(')')
        prec = Q_MUL
    return (neg, seq, prec)


# -- one node: its display sequence (12.2) --------------------------------------------------------

def items(n, need, c):                                          #@L 4
    # The display sequence of node n: literal strings and (child id, need) pairs in display
    # order, wrapped in parentheses when the node's own precedence is below need. c is
    # (deg, mainvar) from text. None: an integer over the str() size guard (6.1).
    N = K.N
    t = N[n]
    op = t[0]
    p = Q_ATOM
    if op == K.NUM:
        a = t[1]
        b = t[2]
        d = t[3]
        if not b:
            r = rstr(t)
            if r is None:
                return None
            seq = ['-' + r[1] if r[0] else r[1]]
            if d != 1:
                p = Q_MUL
            elif r[0]:
                p = Q_NEG
        elif not a:
            s = imstr(b if b > 0 else -b, d)
            if s is None:
                return None
            if s != 'i':
                p = Q_MUL
            if b < 0:
                s = '-' + s
                if p > Q_NEG:
                    p = Q_NEG
            seq = [s]
        else:
            r = rstr(K.nnorm(a, 0, d))
            w = K.nnorm(b, 0, d)
            s = imstr(w[1] if w[1] > 0 else -w[1], w[3])
            if r is None or s is None:
                return None
            seq = ['-' + r[1] if r[0] else r[1], '+' if w[1] > 0 else '-', s]
            p = Q_ADD
    elif op == K.FLT:
        re = t[1]
        im = t[2]
        if not im:
            seq = [fstr(re)]
            if re < 0:
                p = Q_NEG
        elif not re:
            seq = [fstr(im) + '*i']
            p = Q_MUL
        else:
            seq = [fstr(re), '+' if im > 0 else '-', fstr(im if im > 0 else -im) + '*i']
            p = Q_ADD
    elif op == K.SYM:
        seq = [t[1]]
    elif op == K.CON:
        seq = [CNAME[t[1]]]
    elif op == K.ADD:
        o = sorder(n, c[1])
        ps = []
        for r in o:
            if r[0]:
                d = pdisp(r[0], r[1], c)
            else:
                d = rstr(N[r[1]])
                if d is not None:
                    d = (d[0], [d[1]])
            if d is None:
                return None
            ps.append((d[0], d[1], r[0], r[1]))
        if len(ps) == 2 and (not o[1][0] or N[o[1][0]][0] != K.BIGO):
            # the positive term first, then the real part (12.3); a series keeps its
            # ascending order (-x+O(x^3)), as FlowCE leaves series alone
            if ps[0][0] and not ps[1][0]:
                ps.reverse()
            if hasi(ps[0][2], ps[0][3]) and not hasi(ps[1][2], ps[1][3]):
                ps.reverse()
        seq = []
        for j in range(len(ps)):
            if ps[j][0]:
                seq.append('-')
            elif j:
                seq.append('+')
            for x in ps[j][1]:
                seq.append(x)
        p = Q_ADD
    elif op == K.MUL:
        d = pdisp(n, None, c)
        if d is None:
            return None
        seq = d[1]
        p = d[2]
        if d[0]:
            seq.insert(0, '-')
            if p > Q_NEG:
                p = Q_NEG
    elif op >= K.FN0:
        if op == K.FACT:
            seq = [(t[1], Q_ATOM), '!']
            p = Q_POST
        else:
            a = t[1]
            if c[0] and K.SIN <= op <= K.COT:  # degree mode (6.5): v prints as v*180/pi
                u = N[a]
                if u[0] == K.ADD:
                    lst = [K.mul_(K.nmul(N[u[1]], R180), [(K.PI, K.MONE)])]
                    for j in range(2, len(u), 2):
                        lst.append(K.mul_(K.nmul(N[u[j + 1]], R180),
                                          [(u[j], K.ONE), (K.PI, K.MONE)]))
                    a = K.add_(lst)
                else:
                    a = K.mul_(R180, [(a, K.ONE), (K.PI, K.MONE)])
            seq = [FNAME[op - K.FN0] + '(', (a, Q_ARG), ')']
    elif K.EQ <= op <= K.LE:
        a = t[1]
        b = t[2]
        s = RNAME[op - K.EQ]
        mv = c[1]
        if op >= K.LT and mv and K.free_of(a, mv) and not K.free_of(b, mv):
            a = t[2]                       # the main variable on the left: 3<x is x>3
            b = t[1]
            s = '>' if op == K.LT else '>='
        seq = [(a, Q_ADD), s, (b, Q_ADD)]
        p = Q_REL
    elif op == K.CALL or op == K.LST:
        seq = [N[t[1]][1] + '(' if op == K.CALL else '[']
        for j in range(2 if op == K.CALL else 1, len(t)):
            if len(seq) > 1:
                seq.append(',')
            seq.append((t[j], Q_ARG))
        seq.append(')' if op == K.CALL else ']')
    elif op == K.BIGO:
        seq = ['O(', (t[1], Q_ARG), ')']
    elif op == K.HOLD:                     # keep prime powers, negative ones below the bar
        m = N[t[1]]
        seq = []
        den = []
        counts = [0, 0]
        if m[1] == K.MONE:
            seq.append('-')
        elif m[1] != K.ONE:
            seq.append((m[1], Q_NEG))
            counts[0] = 1
        for j in range(2, len(m), 2):
            e = m[j + 1]
            q = N[e]
            d = 1 if q[0] == K.NUM and not q[2] and q[1] < 0 else 0
            part = den if d else seq
            if d:
                e = K.neg_(e)
            if counts[d]:
                part.append('*')
            counts[d] += 1
            if e == K.ONE:
                part.append((m[j], Q_NEG))
            else:
                part.append((m[j], Q_POST))
                part.append('^')
                part.append((e, Q_ATOM))
        if not counts[0]:
            seq.append('1')
        if den:
            seq.append('/(' if counts[1] > 1 else '/')
            seq.extend(den)
            if counts[1] > 1:
                seq.append(')')
        p = Q_MUL
    elif op == K.DNE or op == K.DIVG:      # a sentinel inside a result has no value
        seq = ['undef']
    elif op == K.WILD:                     # rule patterns only, never an answer
        seq = ['_w%d' % t[1]]
    else:
        raise AssertionError('cannot print node %d' % n)
    if p < need:
        seq.insert(0, '(')
        seq.append(')')
    return seq


# -- the driver (12.2) ----------------------------------------------------------------------------

def text(root, ctx):                                            #@L 3
    # The canonical answer text of root (12.1), or None when it would exceed MAXTEXT (the
    # record is then Done). ctx: the evaluation context [deg, mainvar, ...], or None. In degree
    # mode each inverse-trig node F(u) is first replaced by (pi/180)*CALL(SYM('asin'), u), a
    # print-only atom, through the constructors (6.5). A top-level list of solutions prints
    # bare: x=1,x=2 (12.1). A long (sum)/integer prints term by term (fmt 1.4). The nodes
    # built here are display-only and are released before the return.
    N = K.N
    m0 = K.NN
    deg = 1 if ctx is not None and ctx[P.X_DEG] else 0
    new = {}
    for m in A.postorder(root):                 # the display pass: bottom-up (children
        u = N[m]                                # first, as FlowCE), through the constructors
        if deg and K.ASIN <= u[0] <= K.ATAN:
            x = K.mk((K.CALL, K.sym(FNAME[u[0] - K.FN0]), new.get(u[1], u[1])))
            new[m] = K.mul_(D180, [(K.PI, K.ONE), (x, K.ONE)])
        elif u[0] == K.MUL:                     # sum_content (fmt 1.3): the content of a
            q = N[u[1]]                         # factor S^1, S a sum, goes to the
            ps = []                             # coefficient: y*(2x+2) is 2*y*(x+1)
            ch = 0
            for j in range(2, len(u), 2):
                b = new.get(u[j], u[j])
                e = new.get(u[j + 1], u[j + 1])
                if b != u[j] or e != u[j + 1]:
                    ch = 1
                if e == K.ONE and N[b][0] == K.ADD:
                    r = scont(b)
                    if r is not None:
                        b = K.add_([b], (K.NUM, r[1], 0, r[0]))
                        q = K.nmul(q, (K.NUM, r[0], 0, r[1]))
                        ch = 1
                ps.append((b, e))
            if ch:
                new[m] = K.mul_(q, ps)
        elif new and u[0] >= K.COMP:
            x = A.rebuild(m, new)
            if x != m:
                new[m] = x
    root = new.get(root, root)
    c = (deg, mainv(root, ctx))
    s = None
    for z in (0, 1):
        t = N[root]
        st = []
        if t[0] == K.LST and bare(root):
            for j in range(len(t) - 1, 0, -1):
                st.append((t[j], Q_ARG))
                if j > 1:
                    st.append(',')
        else:
            st.append((root, 0))
        out = []
        n = 0
        while st:
            it = st.pop()
            if type(it) is str:
                if it[0] == '=' and out and out[-1][-1] == '!':
                    out.append(' ')        # n! =1: n!=1 would lex as n != 1
                    n += 1
                out.append(it)
                n += len(it)
                if n > MAXTEXT:            # stop at once: no 30k-digit text is ever built
                    out = None
                    break
                continue
            seq = items(it[0], it[1], c)
            if seq is None:
                out = None
                break
            for i in range(len(seq) - 1, -1, -1):
                st.append(seq[i])
        if out is None:                    # pass 1 over MAXTEXT keeps the factored text
            break
        s = ''.join(out)
        if z or len(s) <= LONGPOLY or t[0] != K.MUL or len(t) != 4 or t[3] != K.ONE:
            break
        u = N[t[2]]
        q = N[t[1]]
        if u[0] != K.ADD or q[0] != K.NUM or q[2]:
            break
        j = len(u) - 2                          # (u has no content left: the display pass)
        while j > 0 and N[u[j]][0] != K.BIGO:
            j -= 2
        if q[3] == 1 or j > 0:                  # no denominator (2*(x^12+...)), or a series
            break
        root = K.add_([t[2]], q)                # (13*x^14+...)/182 -> 13*x^14/182+...
    K.release(m0)
    return s


# -- the decimal line (12.6) and the record -------------------------------------------------------

def dline(e):                                                   #@L 3
    # The decimal line of the result e (12.6), or None: only for an exact result with no free
    # symbols; never for integers, Gaussian integers, floats, lists, relations, calls, O(),
    # sentinels, oo, undef, true, false, or a size of 64 or more. Any exception means none.
    try:
        N = K.N
        t = N[e]
        if t[0] == K.NUM:
            if t[3] == 1:
                return None
            return cfmt(dec10(t[1], t[3]) if t[1] else None,
                        dec10(t[2], t[3]) if t[2] else None)
        for m in A.postorder(e):
            o = N[m][0]
            if o == K.SYM or o == K.FLT or o == K.WILD or (o == K.CON and m != K.PI and
                                                           m != K.E):
                return None
            if K.COMP <= o < K.FN0 and o != K.ADD and o != K.MUL:
                return None
        if A.size(e) >= 64:
            return None
        v = A.nrun(A.nprog(e, ()), ())
        if type(v) is not complex:
            return fdec10(v)
        re = v.real
        im = v.imag
        z = abs(re) if abs(re) > abs(im) else abs(im)
        if abs(re) < 1e-13 * z:            # the rounding noise of a complex evaluation
            re = 0.0
        if abs(im) < 1e-13 * z:
            im = 0.0
        return cfmt(fdec10(re) if re else None, fdec10(im) if im else None)
    except Exception:
        return None


def record(val, job):                                           #@L 2
    # The result record (kind, text, approx, flags) of the value val (10.4, 12.1). job is
    # (kind, input text, ctx, flags) as R.go passes it; ctx and flags may be left out. A
    # top-level sentinel is a message: DNE, DIVG, and with F_SOLN the empty list (or false)
    # and true. A text over MAXTEXT is the message Done. An eval job gets the decimal line,
    # and F_APPROX when the answer holds a float although the input had none. None: undefined.
    ctx = job[2] if len(job) > 2 else None
    fl = job[3] if len(job) > 3 else 0
    if ctx is None and fl & F_DEG:
        ctx = (1, None, 0, 0)
    if val is None:
        return (R_MSG, M_UNDEF, None, 0)
    N = K.N
    t = N[val]
    op = t[0]
    m = None
    if fl & F_SOLN and (val == K.TRUE or val == K.FALSE or (op == K.LST and len(t) == 1)):
        if val == K.TRUE:
            x = mainv(val, ctx)
            m = M_EVERY % (N[x][1] if x else 'x')
        else:
            m = M_NOSOL
    elif op == K.DNE:
        if t[1] == K.UNDEF or t[2] == K.UNDEF:
            m = M_OSC
        else:
            a = text(t[1], ctx)
            b = text(t[2], ctx)
            if a is None or len(a) > SIDE:
                a = (a or '')[:SIDE] + '...'
            if b is None or len(b) > SIDE:
                b = (b or '')[:SIDE] + '...'
            m = M_DNE % (a, b)
    elif op == K.DIVG:
        w = N[t[1]]
        m = M_DIVG[w[1] if w[0] == K.NUM and not w[2] and w[3] == 1 and 0 <= w[1] <= 2
                   else 0]
    if m is not None:
        return (R_MSG, m, None, 0)
    s = text(val, ctx)
    if s is None:
        return (R_MSG, M_DONE, None, 0)
    ap = None
    if job[0] == 'eval':
        ap = dline(val)
        if not (ctx is not None and len(ctx) > P.X_APPROX and ctx[P.X_APPROX]):
            for x in A.postorder(val):
                if N[x][0] == K.FLT:
                    fl |= F_APPROX
                    break
    return (R_ANS, s, ap, fl)
