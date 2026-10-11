#@L 7
# CVNODE: the node table, number kernels and constructors (DESIGN 5, 6, 8.2).
import array
import gc
import math

# -- op codes (5.2) ------------------------------------------------------------------------------
NUM = 0
FLT = 1
SYM = 2
CON = 3
WILD = 4
DEAD = 7                     # a released slot under the debug arena (20.4)
COMP = 8
ADD = 8
MUL = 9
CALL = 10
LST = 11
EQ = 12
NE = 13
LT = 14
LE = 15
BIGO = 16
DNE = 17
DIVG = 18
HOLD = 19
GT = 20                      # rel_ only: a > b is built as LT(b, a)
GE = 21                      # rel_ only: a >= b is built as LE(b, a)
FN0 = 24
SIN = 24
COS = 25
TAN = 26
SEC = 27
CSC = 28
COT = 29
ASIN = 30
ACOS = 31
ATAN = 32
SINH = 33
COSH = 34
TANH = 35
LN = 36
ABS = 37
SIGN = 38
FLOOR = 39
CEIL = 40
FACT = 41
ODDF = (SIN, TAN, CSC, COT, ASIN, ATAN, SINH, TANH)
EVENF = (COS, SEC, COSH)

# -- preallocated ids (5.5) ----------------------------------------------------------------------
ZERO = 1
ONE = 2
MONE = 3
TWO = 4
HALF = 5
I = 6
PI = 7
E = 8
OO = 9
UNDEF = 10
TEN = 11
LN10 = 12
TRUE = 13
FALSE = 14
BASE = 15

# -- sizes and caps ------------------------------------------------------------------------------
M25 = 0x1FFFFFF
OVF = 1 << 29
NB = 1024
NBM = NB - 1
NMAX = 768
LOWMEM = 24576
MAXBITS = 65536
TRIAL = 10000
M_COMPLEX = 'expression too complex'
M_BIG = 'number too large'
M_RESULT = 'invalid use of a result'

Q0 = (NUM, 0, 0, 1)
Q1 = (NUM, 1, 0, 1)
QM1 = (NUM, -1, 0, 1)
QH = (NUM, 1, 0, 2)
DEADT = (DEAD,)
IPOW = (Q1, (NUM, 0, 1, 1), QM1, (NUM, 0, -1, 1))              # i^n for n mod 4
# e^(i*pi*a/4) / sqrt(2) for odd a (mul_ multiplies the sqrt(2) back in)
OMEGA = (None, (NUM, 1, 1, 2), None, (NUM, -1, 1, 2), None, (NUM, -1, -1, 2), None,
         (NUM, 1, -1, 2))

# -- the table (5.1); ids 1..14 hold the preallocated nodes (generated, tests/test_node.py) ------
N = [None, (NUM, 0, 0, 1), (NUM, 1, 0, 1), (NUM, -1, 0, 1), (NUM, 2, 0, 1), (NUM, 1, 0, 2),
     (NUM, 0, 1, 1), (CON, 0), (CON, 1), (CON, 2), (CON, 3), (NUM, 10, 0, 1), (LN, 11),
     (CON, 4), (CON, 5)] + [None] * (NMAX - BASE)
H = [0, 1, 9, 33554113, 17, 10, 3, 12288, 12305, 12322, 12339, 81, 1233, 12356,
     12373] + [0] * (NMAX - BASE)
NX = [0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0] + [0] * (NMAX - BASE)
V = [0] * NMAX
B = array.array('i', [0] * NB)
B[0], B[1], B[3], B[9], B[10], B[17], B[34] = 7, 1, 6, 2, 5, 8, 9
B[51], B[68], B[81], B[85], B[209], B[705] = 10, 13, 11, 14, 12, 3
NN = BASE
SYMN = []
SYMI = {}
RULECACHE = {}
TCACHE = {}
FCACHE = {}
DEBUG_ARENA = False

ESC = None  #@native
MEMFREE = None  #@native
ONRESET = None  #@native


class CasError(Exception):
    pass


class CasSoft(Exception):
    pass


class Undefined(CasSoft):
    pass


class Cancel(BaseException):
    pass


class CasMemory(BaseException):
    pass


# -- special values (6.4): angles in units of pi/120 in [0, 60] ----------------------------------
# A value is a tuple of terms: (p, q, r) is (p/q)*sqrt(r) (r = 1: p/q), and (p, q, a, b, c) is
# (p/q)*sqrt(a + b*sqrt(c)). sin and csc use cos and sec at 60 - m; cot uses tan at 60 - m.
COS_T = {0: ((1, 1, 1),), 10: ((1, 4, 6), (1, 4, 2)), 12: ((1, 4, 10, 2, 5),),
         15: ((1, 2, 2, 1, 2),), 20: ((1, 2, 3),), 24: ((1, 4, 1), (1, 4, 5)),
         30: ((1, 2, 2),), 36: ((1, 4, 10, -2, 5),), 40: ((1, 2, 1),),
         45: ((1, 2, 2, -1, 2),), 48: ((-1, 4, 1), (1, 4, 5)), 50: ((1, 4, 6), (-1, 4, 2)),
         60: ()}
TAN_T = {0: (), 10: ((2, 1, 1), (-1, 1, 3)), 12: ((1, 5, 25, -10, 5),),
         15: ((-1, 1, 1), (1, 1, 2)), 20: ((1, 3, 3),), 24: ((1, 1, 5, -2, 5),),
         30: ((1, 1, 1),), 36: ((1, 5, 25, 10, 5),), 40: ((1, 1, 3),),
         45: ((1, 1, 1), (1, 1, 2)), 48: ((1, 1, 5, 2, 5),), 50: ((2, 1, 1), (1, 1, 3))}
SEC_T = {0: ((1, 1, 1),), 10: ((1, 1, 6), (-1, 1, 2)), 12: ((1, 5, 50, -10, 5),),
         15: ((1, 1, 4, -2, 2),), 20: ((2, 3, 3),), 24: ((-1, 1, 1), (1, 1, 5)),
         30: ((1, 1, 2),), 36: ((1, 5, 50, 10, 5),), 40: ((2, 1, 1),),
         45: ((1, 1, 4, 2, 2),), 48: ((1, 1, 1), (1, 1, 5)), 50: ((1, 1, 6), (1, 1, 2))}
# H of the value sin(m*pi/120) (ASIN_H) and tan(m*pi/120) (ATAN_H) -> m, for m in -60..60; the
# value is rebuilt and compared by id before it is trusted (tests/test_special.py regenerates)
ASIN_H = {1: 0, 7211684: 10, 7002003: -10, 23803571: 12, 24112004: -12, 32200764: 15,
          1080259: -15, 10: 20, 33554114: -20, 30887740: 24, 2911427: -24, 305706: 30,
          33524181: -30, 9442636: 36, 9750651: -36, 305962: 40, 33523925: -40, 1343779: 45,
          32482012: -45, 2660899: 48, 30652892: -48, 26342508: 50, 26552667: -50, 9: 60,
          33554113: -60}
ATAN_H = {1: 0, 24076161: 10, 23724726: -10, 26956604: 12, 6320323: -12, 23839414: 15,
          24059777: -15, 306986: 20, 33524949: -20, 32201532: 24, 1079491: -24, 9: 30,
          33554113: -30, 6592035: 36, 27243996: -36, 304938: 40, 33522901: -40, 9494857: 45,
          9714814: -45, 1347107: 48, 32484828: -48, 9478473: 50, 9829502: -50}


# -- the intern table ----------------------------------------------------------------------------

def mk(t):                                                      #@L 7
    # intern the flat tuple t (5.10); the children of a composite are older ids
    global NN
    op = t[0]
    v = 0
    if op >= COMP:
        h = op
        for j in range(1, len(t)):
            c = t[j]
            if DEBUG_ARENA and (N[c] is None or N[c][0] == DEAD):
                raise AssertionError('dead node id %d' % c)
            h = ((h << 5) ^ (h >> 20) ^ H[c]) & M25
            v |= V[c]
    elif op == NUM:
        h = (((t[1] % 33554393) << 3) ^ ((t[2] % 1048573) << 1) ^ (t[3] % 65521)) & M25
    elif op == SYM:
        h = 5381
        for ch in t[1]:
            h = ((h << 5) ^ (h >> 20) ^ ord(ch)) & M25
        v = SYMI.get(t[1])
        if v is None:
            v = len(SYMN)
            SYMN.append(t[1])
            SYMI[t[1]] = v
        v = (1 << v) if v < 29 else OVF
    elif op == FLT:
        h = FLT
        for j in (1, 2):
            m, x = math.frexp(t[j])
            h = ((h << 5) ^ (h >> 20) ^ (int(m * 1048576) & M25) ^ ((x & 255) << 17)) & M25
    else:
        h = ((op << 12) ^ (t[1] << 4) ^ t[-1]) & M25
    b = h & NBM
    i = B[b]
    while i:
        if H[i] == h and N[i] == t:
            return i
        i = NX[i]
    i = NN
    if i >= NMAX:
        raise CasError(M_COMPLEX)
    if not i & 255 and MEMFREE is not None and MEMFREE() < LOWMEM:
        gc.collect()
        if MEMFREE() < LOWMEM:
            raise CasMemory()
    N[i] = t
    H[i] = h
    NX[i] = B[b]
    V[i] = v
    B[b] = i
    NN = i + 1
    return i


def chk(x):                                                     #@L 7
    # an argument check: a released id is a bug; a sentinel takes no part in arithmetic (10.5)
    t = N[x]
    if t is None or t[0] == DEAD:
        raise AssertionError('dead node id %d' % x)
    if x == TRUE or x == FALSE or DNE <= t[0] <= HOLD:
        raise CasError(M_RESULT)


def release(m):                                                 #@L 7
    # drop every node >= m (the newest id is always the head of its chain)
    global NN
    n = NN
    for i in range(n - 1, m - 1, -1):
        if N[i][0] != DEAD:
            B[H[i] & NBM] = NX[i]
        N[i] = DEADT if DEBUG_ARENA else None
    if m < n and not DEBUG_ARENA:
        NN = m


def keep(m, y):                                                 #@L 4
    # Release the nodes >= m not reachable from y (None, an id or a flat tuple of ids) or from
    # RULECACHE (entry[0] of every rule entry is its pattern id). Survivors move down in id
    # order (to fresh ids under the debug arena); y comes back remapped and RULECACHE is
    # rewritten in place.
    global NN
    n = NN
    if n <= m:
        return y
    if y is None and not RULECACHE:
        release(m)
        return None
    live = bytearray(n - m)
    st = []
    for r in (y if type(y) is tuple else (y,)):
        if type(r) is int and r >= m:
            st.append(r)
    for nm in RULECACHE:                                        #@unordered-ok
        rs = RULECACHE[nm]
        for op in rs:                                           #@unordered-ok
            for r in rs[op]:
                if r[0] >= m:
                    st.append(r[0])
    while st:
        i = st.pop()
        if live[i - m]:
            continue
        live[i - m] = 1
        t = N[i]
        if t[0] == DEAD:
            raise AssertionError('dead node id %d' % i)
        if t[0] >= COMP:
            for j in range(1, len(t)):
                if t[j] >= m:
                    st.append(t[j])
    for i in range(n - 1, m - 1, -1):
        if N[i][0] != DEAD:
            B[H[i] & NBM] = NX[i]
    rm = [0] * (n - m)
    k = n if DEBUG_ARENA else m
    for i in range(m, n):
        if live[i - m]:
            t = N[i]
            if t[0] >= COMP:
                u = [t[0]]
                for j in range(1, len(t)):
                    c = t[j]
                    u.append(rm[c - m] if c >= m else c)
                t = tuple(u)
            if k >= NMAX:
                raise CasError(M_COMPLEX)
            h = H[i]
            N[k] = t
            H[k] = h
            V[k] = V[i]
            NX[k] = B[h & NBM]
            B[h & NBM] = k
            rm[i - m] = k
            k += 1
    for i in (range(m, n) if DEBUG_ARENA else range(k, n)):
        N[i] = DEADT if DEBUG_ARENA else None
    NN = k
    for nm in RULECACHE:                                        #@unordered-ok
        rs = RULECACHE[nm]
        for op in rs:                                           #@unordered-ok
            out = []
            for r in rs[op]:
                if r[0] >= m:
                    r = (rm[r[0] - m],) + r[1:]
                out.append(r)
            rs[op] = tuple(out)
    if type(y) is tuple:
        out = []
        for r in y:
            out.append(rm[r - m] if type(r) is int and r >= m else r)
        return tuple(out)
    return rm[y - m] if type(y) is int and y >= m else y


def reset():                                                    #@L 4
    # end of a command: truncate the table to BASE and clear the per-command caches
    global NN
    if ONRESET is not None:
        ONRESET()
    for i in range(NN - 1, BASE - 1, -1):
        t = N[i]
        if t is not None and t[0] != DEAD:
            B[H[i] & NBM] = NX[i]
        N[i] = None
    NN = BASE
    del SYMN[:]
    SYMI.clear()
    RULECACHE.clear()
    TCACHE.clear()
    FCACHE.clear()


# -- number kernels on (NUM, a, b, d) and (FLT, re, im) tuples (6.1) -----------------------------

def nnorm(a, b, d):                                             #@L 7
    # (a + b*i)/d -> a normalized NUM tuple; d == 0 raises Undefined
    if d == 0:
        raise Undefined()
    if d < 0:
        a = -a
        b = -b
        d = -d
    g = a if a >= 0 else -a
    h = b if b >= 0 else -b
    while h:
        g, h = h, g % h
    h = d
    while h:
        g, h = h, g % h
    if g > 1:
        a //= g
        b //= g
        d //= g
    return (NUM, a, b, d)


def nadd(x, y):                                                 #@L 7
    if x[0] or y[0]:                                            # FLT contagion
        try:
            z = (complex(x[1], x[2]) / (1 if x[0] else x[3]) +             #@float-ok
                 complex(y[1], y[2]) / (1 if y[0] else y[3]))               #@float-ok
        except OverflowError:
            raise CasError(M_BIG)
        if z.real - z.real != 0 or z.imag - z.imag != 0:
            raise CasError(M_BIG)
        return (FLT, z.real + 0.0, z.imag + 0.0)
    if x[3] == y[3]:
        a = x[1] + y[1]
        b = x[2] + y[2]
        d = x[3]
        if d == 1:
            return (NUM, a, b, 1)
    else:
        a = x[1] * y[3] + y[1] * x[3]
        b = x[2] * y[3] + y[2] * x[3]
        d = x[3] * y[3]
    g = a if a >= 0 else -a
    h = b if b >= 0 else -b
    while h:
        g, h = h, g % h
    h = d
    while h:
        g, h = h, g % h
    if g > 1:
        a //= g
        b //= g
        d //= g
    return (NUM, a, b, d)


def nmul(x, y):                                                 #@L 7
    if x[0] or y[0]:                                            # FLT contagion
        try:
            z = (complex(x[1], x[2]) / (1 if x[0] else x[3]) *              #@float-ok
                 complex(y[1], y[2]) / (1 if y[0] else y[3]))               #@float-ok
        except OverflowError:
            raise CasError(M_BIG)
        if z.real - z.real != 0 or z.imag - z.imag != 0:
            raise CasError(M_BIG)
        return (FLT, z.real + 0.0, z.imag + 0.0)
    if x[2] == 0 and y[2] == 0:                                 # real fast path
        a = x[1] * y[1]
        b = 0
    else:
        a = x[1] * y[1] - x[2] * y[2]
        b = x[1] * y[2] + x[2] * y[1]
    d = x[3] * y[3]
    if d == 1:
        return (NUM, a, b, 1)
    g = a if a >= 0 else -a
    h = b if b >= 0 else -b
    while h:
        g, h = h, g % h
    h = d
    while h:
        g, h = h, g % h
    if g > 1:
        a //= g
        b //= g
        d //= g
    return (NUM, a, b, d)


def ninv(x):                                                    #@L 7
    # 1/x; zero raises Undefined
    if not x[1] and not x[2]:
        raise Undefined()
    if x[0]:
        try:
            z = 1 / complex(x[1], x[2])                         #@float-ok
        except (OverflowError, ZeroDivisionError):
            raise CasError(M_BIG)
        if z.real - z.real != 0 or z.imag - z.imag != 0:
            raise CasError(M_BIG)
        return (FLT, z.real + 0.0, z.imag + 0.0)
    a = x[1]
    b = x[2]
    d = x[3]
    if b == 0:
        return (NUM, -d, 0, -a) if a < 0 else (NUM, d, 0, a)
    m = a * a + b * b
    a = d * a
    b = -d * b
    g = a if a >= 0 else -a
    h = b if b >= 0 else -b
    while h:
        g, h = h, g % h
    h = m
    while h:
        g, h = h, g % h
    return (NUM, a // g, b // g, m // g)


def nneg(x):                                                    #@L 7
    if x[0]:
        return (FLT, -x[1] + 0.0, -x[2] + 0.0)
    return (NUM, -x[1], -x[2], x[3])


def nsign(x):                                                   #@L 7
    # -1, 0 or 1 for a real number; a non-real one raises Undefined
    if x[2]:
        raise Undefined()
    return (x[1] > 0) - (x[1] < 0)


def ncmp(x, y):                                                 #@L 7
    # -1, 0 or 1 comparing two real numbers; a non-real one raises Undefined
    if x[2] or y[2]:
        raise Undefined()
    if x[0] or y[0]:
        try:
            u = x[1] / (1 if x[0] else x[3])                    #@float-ok
            v = y[1] / (1 if y[0] else y[3])                    #@float-ok
        except OverflowError:
            raise CasError(M_BIG)
    else:
        u = x[1] * y[3]
        v = y[1] * x[3]
    return (u > v) - (u < v)


def npowi(x, n):                                                #@L 7
    # x^n for a number tuple and an int n; the size of the result is checked first (MAXBITS)
    if n == 0:
        return Q1
    if not x[1] and not x[2] and n < 0:
        raise Undefined()
    if x[0]:
        try:
            z = complex(x[1], x[2]) ** n
        except (OverflowError, ZeroDivisionError):
            raise CasError(M_BIG)
        if z.real - z.real != 0 or z.imag - z.imag != 0:
            raise CasError(M_BIG)
        return (FLT, z.real + 0.0, z.imag + 0.0)
    a = x[1]
    b = x[2]
    d = x[3]
    if n < 0:                                                   # invert first
        n = -n
        if b == 0:
            a, d = (-d, -a) if a < 0 else (d, a)
        else:
            m = a * a + b * b
            a = d * a
            b = -d * b
            g = a if a >= 0 else -a
            h = b if b >= 0 else -b
            while h:
                g, h = h, g % h
            h = m
            while h:
                g, h = h, g % h
            a //= g
            b //= g
            d = m // g
    if n == 1:
        return (NUM, a, b, d)
    if d == 1 and a * a + b * b == 1:                           # 1, -1, i, -i
        return IPOW[(n * (0 if a > 0 else 2 if a < 0 else 1 if b > 0 else 3)) & 3]
    w = a if a >= 0 else -a
    if b > w or -b > w:
        w = b if b >= 0 else -b
    if d > w:
        w = d
    if n * 4 * len('%x' % w) > MAXBITS:
        raise CasError(M_BIG)
    if b == 0:
        return (NUM, a ** n, 0, d ** n)
    d = d ** n
    ra = 1
    rb = 0
    while True:                                                 # square and multiply
        if n & 1:
            ra, rb = ra * a - rb * b, ra * b + rb * a
        n >>= 1
        if not n:
            break
        a, b = a * a - b * b, 2 * a * b
    g = ra if ra >= 0 else -ra                                  # (a+bi)^n / d^n: reduce
    h = rb if rb >= 0 else -rb
    while h:
        g, h = h, g % h
    h = d
    while h:
        g, h = h, g % h
    return (NUM, ra // g, rb // g, d // g)


def fpow(x, y):                                                 #@L 7
    # x^y as a FLT, for number tuples x, y when one is a FLT; a rational y with an odd
    # denominator takes the real root of a negative real x (6.2)
    try:
        u = complex(x[1], x[2]) / (1 if x[0] else x[3])         #@float-ok
        w = complex(y[1], y[2]) / (1 if y[0] else y[3])         #@float-ok
        if u == 0:
            if w.real > 0:
                return (FLT, 0.0, 0.0)
            raise Undefined()
        if not u.imag and not w.imag and (u.real > 0 or (y[0] == NUM and y[3] & 1)):
            z = (u.real if u.real > 0 else -u.real) ** w.real
            z = complex(-z if u.real < 0 and y[1] & 1 else z, 0.0)
        else:
            z = u ** w
    except (OverflowError, ZeroDivisionError):
        raise CasError(M_BIG)
    if z.real - z.real != 0 or z.imag - z.imag != 0:
        raise CasError(M_BIG)
    return (FLT, z.real + 0.0, z.imag + 0.0)


def ifac(n):                                                    #@L 7
    # n >= 1 -> (p1, a1, p2, a2, ...): primes ascending, complete below TRIAL^2; above, the
    # last base may be a cofactor whose prime factors all exceed TRIAL, written as a perfect
    # power when it is one (up to 4000 bits). Cached for the command.
    r = FCACHE.get(n)
    if r is not None:
        return r
    out = []
    c = n
    p = 2
    while p * p <= c and p <= TRIAL:
        if c % p == 0:
            a = 0
            while c % p == 0:
                c //= p
                a += 1
            out.append(p)
            out.append(a)
        p += 1 if p == 2 else 2
        if p & 1023 == 1 and ESC is not None and ESC():
            raise Cancel()
    if c > 1:
        a = 1
        h = 2
        if p * p <= c and len('%x' % c) <= 1000:
            while (TRIAL + 1) ** h <= c:
                x = 1 << ((len('%x' % c) * 4 + h - 1) // h)     # x >= c^(1/h): Newton down
                while True:
                    y = ((h - 1) * x + c // x ** (h - 1)) // h
                    if y >= x:
                        break
                    x = y
                if x ** h == c:
                    c = x
                    a *= h
                else:
                    h += 1 if h == 2 else 2
                if ESC is not None and ESC():
                    raise Cancel()
        out.append(c)
        out.append(a)
    r = tuple(out)
    if len(FCACHE) > 64:
        FCACHE.clear()
    FCACHE[n] = r
    return r


def rootsplit(n, s):                                            #@L 6
    # n >= 1 -> (outside, inside) with n == outside^s * inside, inside s-th-power-free (6.2)
    f = ifac(n)
    o = 1
    r = 1
    for j in range(0, len(f), 2):
        o *= f[j] ** (f[j + 1] // s)
        r *= f[j] ** (f[j + 1] % s)
    return (o, r)


# -- predicates and ordering ---------------------------------------------------------------------

def isninf(x):                                                  #@L 7
    t = N[x]
    return t[0] == MUL and len(t) == 4 and t[2] == OO and t[1] == MONE and t[3] == ONE


def negfirst(u):                                                #@L 7
    # True if -u is the canonical representative (6.4): a negative number, a MUL with a
    # negative coefficient, an ADD whose first pair has a negative coefficient. "Negative"
    # for a complex number: real part < 0, or real part 0 and imaginary part < 0.
    t = N[u]
    op = t[0]
    if op == ADD:
        t = N[t[3]]
    elif op == MUL:
        t = N[t[1]]
    elif op > FLT:
        return False
    return t[1] < 0 or (t[1] == 0 and t[2] < 0)


def csign(u):                                                   #@L 7
    # +1 / -1 when u is provably a positive / negative real constant, else 0: real numbers,
    # pi, e, sums whose numbers share one sign, products with real numeric exponents; every
    # term and base must itself be positive
    if V[u]:
        return 0
    s = 0
    st = [u]
    while st:
        x = st.pop()
        t = N[x]
        op = t[0]
        if x == PI or x == E:
            g = 1
        elif op <= FLT:
            if t[2]:
                return 0
            g = (t[1] > 0) - (t[1] < 0)
        elif op == ADD or op == MUL:                            # odd slots: numbers
            g = 0
            for j in range(1, len(t)):
                if j & 1:
                    w = N[t[j]]
                    if w[0] > FLT or w[2]:
                        return 0
                    if j == 1 or op == ADD:
                        h = (w[1] > 0) - (w[1] < 0)
                        if h and g and h != g:
                            return 0
                        if h:
                            g = h
                else:
                    st.append(t[j])
        else:
            return 0
        if x == u:
            s = g
        elif g <= 0:
            return 0
    return s


def isreal(u):                                                  #@L 7
    # True if u is provably real (8.3): symbols, real numbers, pi, e, and sums, products,
    # odd-root powers, positive-base powers and real functions of these; abs of anything
    st = [u]
    while st:
        x = st.pop()
        t = N[x]
        op = t[0]
        if op <= FLT:
            if t[2]:
                return False
        elif op == ADD:
            for j in range(1, len(t)):
                st.append(t[j])
        elif op == MUL:
            st.append(t[1])
            for j in range(2, len(t), 2):
                b = N[t[j]]
                w = N[t[j + 1]]
                if w[0] == NUM and not w[2] and w[3] & 1:   # real^integer, real odd roots
                    st.append(t[j])
                elif t[j] == E or t[j] == PI or (b[0] == NUM and not b[2] and b[1] > 0):
                    st.append(t[j + 1])                     # positive^real
                else:
                    return False
        elif op >= FN0 and op != LN and op != ASIN and op != ACOS:
            if op != ABS:
                st.append(t[1])
        elif op != SYM and x != PI and x != E:
            return False
    return True


def free_of(e, x):                                              #@L 7
    # True if node x does not occur in e (5.8): a mask test, or a walk when masks cannot tell
    vx = V[x]
    ve = V[e]
    if N[x][0] == SYM and vx != OVF:
        return not (ve & vx)
    if (vx and (vx & ve) != vx) or e < x:
        return True
    seen = bytearray(e - x + 1)
    st = [e]
    while st:
        i = st.pop()
        if i == x:
            return False
        if i < x or seen[i - x]:
            continue
        seen[i - x] = 1
        t = N[i]
        if t[0] >= COMP:
            for j in range(1, len(t)):
                st.append(t[j])
    return True


def tiefix(lst):                                                #@L 7
    # lst: (H, id, ...) tuples sorted natively. Reorder each run of equal H by the
    # id-independent structural key of 5.7: (op, len), then the leaf payload or the
    # children's H, then a preorder walk of both nodes in parallel.
    n = len(lst)
    i = 0
    while i < n - 1:
        j = i + 1
        while j < n and lst[j][0] == lst[i][0]:
            j += 1
        if j - i > 1:
            keys = []
            for r in range(i, j):
                t = N[lst[r][1]]
                kk = [t[0], len(t)]
                for c in range(1, len(t)):
                    kk.append(H[t[c]] if t[0] >= COMP else t[c])
                keys.append(tuple(kk))
            for a in range(i + 1, j):                           # insertion sort of the run
                cur = lst[a]
                ck = keys[a - i]
                b = a - 1
                while b >= i:
                    pk = keys[b - i]
                    if pk < ck:
                        break
                    if pk == ck:
                        c = 0
                        st = [(lst[b][1], cur[1])]
                        while st and not c:
                            x, y = st.pop()
                            tx = N[x]
                            ty = N[y]
                            if x == y:
                                continue
                            if tx[0] != ty[0] or len(tx) != len(ty):
                                c = -1 if (tx[0], len(tx)) < (ty[0], len(ty)) else 1
                            elif tx[0] < COMP:
                                c = -1 if tx[1:] < ty[1:] else 1
                            else:
                                for q in range(len(tx) - 1, 0, -1):
                                    st.append((tx[q], ty[q]))
                        if c <= 0:
                            break
                    lst[b + 1] = lst[b]
                    keys[b + 1 - i] = pk
                    b -= 1
                lst[b + 1] = cur
                keys[b + 1 - i] = ck
        i = j


# -- leaves --------------------------------------------------------------------------------------

def num(a, b=0, d=1):                                           #@L 6
    return mk(nnorm(a, b, d))


def flt(re, im=0.0):                                            #@L 6
    re = float(re) + 0.0
    im = float(im) + 0.0
    if re - re != 0 or im - im != 0:
        raise Undefined()
    return mk((FLT, re, im))


def sym(name):                                                  #@L 6
    return mk((SYM, name))


# -- constructors (8.2) --------------------------------------------------------------------------

def add_(terms, k=None):                                        #@L 6
    # canonical k * sum(terms); terms: ids; k: None, a number tuple or a number id
    m0 = Q1 if k is None else (N[k] if type(k) is int else k)
    c = Q0
    acc = {}
    inf = 0
    st = []
    for e in terms:
        chk(e)
        st.append((e, m0))
    while st:
        e, m = st.pop()
        t = N[e]
        op = t[0]
        if op <= FLT:
            c = nadd(c, nmul(t, m))
            continue
        if op == ADD:                                           # flatten nested sums
            st.append((t[1], m))
            for j in range(2, len(t), 2):
                st.append((t[j], nmul(N[t[j + 1]], m)))
            continue
        if op == MUL and t[1] != ONE:                           # split the coefficient
            m = nmul(N[t[1]], m)
            if len(t) == 4 and t[3] == ONE:
                e = t[2]
                if N[e][0] == ADD:                              # c*(sum): distribute
                    st.append((e, m))
                    continue
            else:
                e = mk((MUL, ONE) + t[2:])
        elif e == UNDEF:
            return UNDEF
        if e == OO and not m[2]:                                # a real multiple of oo
            inf |= 1 if m[1] > 0 else 2
            continue
        acc[e] = nadd(acc[e], m) if e in acc else m
    lst = []
    hold = False                                                # x*oo is kept as a term
    for e in acc:                                               #@unordered-ok (sorted below)
        m = acc[e]
        if m[1] or m[2]:
            lst.append((H[e], e))                               # flat sort keys (5.7)
            if N[e][0] == MUL:
                for j in range(2, len(N[e]), 2):
                    if N[e][j] == OO:
                        hold = True
    if inf == 3 or (inf and OO in acc):
        return UNDEF
    if inf:
        if not hold:
            return OO if inf == 1 else mk((MUL, MONE, OO, ONE))
        acc[OO] = Q1 if inf == 1 else QM1
        lst.append((H[OO], OO))
    if not lst:
        return mk(c)
    lst.sort()
    tiefix(lst)
    if len(lst) == 1 and not c[1] and not c[2]:                 # k*t is a product
        e = lst[0][1]
        if acc[e] == Q1:
            return e
        t = N[e]
        return mk((MUL, mk(acc[e])) + (t[2:] if t[0] == MUL else (e, ONE)))
    out = [ADD, mk(c) if c[1] or c[2] else ZERO]
    for r in lst:
        out.append(r[1])
        out.append(mk(acc[r[1]]))
    return mk(tuple(out))


def neg_(u):                                                    #@L 6
    # -u without add_ (6.4): the pair order does not depend on coefficients
    chk(u)
    t = N[u]
    op = t[0]
    if op <= FLT:
        return mk(nneg(t))
    if op == ADD:
        out = [ADD]
        for j in range(1, len(t)):
            out.append(t[j] if j % 2 == 0 else mk(nneg(N[t[j]])))
        return mk(tuple(out))
    if op == MUL:
        k = nneg(N[t[1]])
        if k == Q1 and len(t) == 4 and t[3] == ONE:
            return t[2]
        return mk((MUL, mk(k)) + t[2:])
    if u == UNDEF:
        return UNDEF
    return mk((MUL, MONE, u, ONE))


def absn(u):                                                    #@L 6
    # the canonical abs(u) (6.4): |c| * abs(w) with c the numeric content of u
    chk(u)
    t = N[u]
    op = t[0]
    if u == UNDEF or u == OO or isninf(u):
        return UNDEF if u == UNDEF else OO
    if op == ABS:
        return u
    k = N[t[1]] if op == MUL else t                             # a number, or the coefficient
    c = Q1
    if k[0] == FLT:
        c = (FLT, abs(complex(k[1], k[2])), 0.0)
    elif k[0] == NUM:                                           # |(a+bi)/d| = o*sqrt(r)/d
        f = ifac(k[1] * k[1] + k[2] * k[2]) if k[2] else (k[1] if k[1] > 0 else -k[1], 2)
        o = 1
        r = 1
        for j in range(0, len(f), 2):
            o *= f[j] ** (f[j + 1] >> 1)
            r *= f[j] if f[j + 1] & 1 else 1
        c = nnorm(o, 0, k[3])
        if r > 1:
            if op == NUM:
                return mk((MUL, mk(c), mk((NUM, r, 0, 1)), HALF))
            c = None                            # an irrational modulus stays inside abs
    if op <= FLT:
        return mk(c)
    if c is None:
        c = Q1
    elif op == MUL:
        u = t[2] if len(t) == 4 and t[3] == ONE else mk((MUL, ONE) + t[2:])
        t = N[u]
    if t[0] == ADD:                                             # the rational content
        g = 0
        dl = 1
        for j in range(1, len(t), 2):
            w = N[t[j]]
            if w[0] or w[2]:
                g = 1
                dl = 1
                break
            h = w[1] if w[1] >= 0 else -w[1]
            while h:
                g, h = h, g % h
            h = w[3]
            x = dl
            while h:
                x, h = h, x % h
            dl = dl * w[3] // x
        if g != 1 or dl != 1:
            out = [ADD]
            for j in range(1, len(t)):
                w = N[t[j]]
                out.append(t[j] if j % 2 == 0 else mk(nnorm(w[1] * dl, 0, w[3] * g)))
            u = mk(tuple(out))
            t = N[u]
            c = nmul(c, (NUM, g, 0, dl))
    if negfirst(u):                                             # the sign rule
        out = [t[0]]
        for j in range(1, len(t)):
            out.append(mk(nneg(N[t[j]])) if j == 1 or (j & 1 and t[0] == ADD) else t[j])
        u = mk(tuple(out))
        t = N[u]
    ev = t[0] == MUL and t[1] == ONE                            # abs(w^(2k)) = w^(2k)
    if ev:
        for j in range(3, len(t), 2):
            w = N[t[j]]
            if w[0] or w[2] or w[3] != 1 or w[1] & 1:
                ev = False
    r = u if ev or csign(u) > 0 else mk((ABS, u))
    if c == Q1:
        return r
    return mk((MUL, mk(c)) + (t[2:] if r == u and t[0] == MUL else (r, ONE)))


def mul_(k, pairs):                                             #@L 5
    # canonical k * prod(b^e) (8.2); k: a number id or tuple; pairs: (base id, exponent id)
    c = N[k] if type(k) is int else k
    acc = {}                                 # base id -> exponent id
    rad = {}                                 # prime (or cofactor) -> rational exponent tuple
    inf = 0
    st = []
    for p in pairs:
        chk(p[0])
        chk(p[1])
        st.append(p)
    while st:
        b, e = st.pop()
        tb = N[b]
        te = N[e]
        ob = tb[0]
        oe = te[0]
        if oe <= FLT and not te[1] and not te[2]:              # rule 1: b^0 = 1 (0^0 too)
            continue
        if b == UNDEF or e == UNDEF:
            return UNDEF
        ie = oe == NUM and not te[2] and te[3] == 1             # an integer exponent
        if b == OO or ((e == OO or isninf(e)) and (ob <= FLT or b == E or b == PI)):
            g = 0                                               # rule 12: 1 oo, -1 zero
            if b == OO:
                g = 1 if e == OO else -1 if isninf(e) else 0
                if oe <= FLT and not te[2]:
                    g = 1 if te[1] > 0 else -1
            elif ob > FLT:                                      # e or pi, to +-oo
                g = 1 if e == OO else -1
            elif not tb[2]:
                x = tb
                if e != OO:                                     # k^(-oo) = (1/k)^oo
                    x = ninv(x) if x[1] else (NUM, 2, 0, 1)
                g = 1 if ncmp(x, Q1) > 0 else -1 if ncmp(x, QM1) > 0 and ncmp(x, Q1) else 0
            if g == 0 and (b != OO or oe <= FLT):
                return UNDEF
            if g:
                inf += g > 0
                c = c if g > 0 else Q0
                continue
        elif ob <= FLT and oe <= FLT:                           # a number to a number power
            if ie:                                              # rule 2
                c = nmul(c, npowi(tb, te[1]))
                continue
            if ob == FLT or oe == FLT:
                c = nmul(c, fpow(tb, te))
                continue
            if not te[2] and not tb[2]:                         # rule 3: radicals (6.2)
                p = te[1]
                s = te[3]
                n = p // s
                p -= n * s                                      # 0 < p/s < 1
                if not tb[1]:
                    if n < 0:
                        raise Undefined()
                    c = Q0
                    continue
                c = nmul(c, npowi(tb, n))
                a = tb[1]
                d = tb[3]
                if d > 1:                                       # rationalize: 1/v -> v^(s-1)/v
                    if len('%x' % d) * 4 * s > MAXBITS:
                        raise CasError(M_BIG)
                    a *= d ** (s - 1)
                    c = nmul(c, (NUM, 1, 0, d ** p))
                if a < 0:
                    a = -a
                    if s & 1:                                   # a real odd root
                        c = nneg(c) if p & 1 else c
                    else:                                       # (-a)^(p/s) = a^(p/s) e^(i pi p/s)
                        st.append((E, mk((MUL, mk(nnorm(0, p, s)), PI, ONE))))
                f = ifac(a)
                for j in range(0, len(f), 2):
                    rad[f[j]] = nadd(rad.get(f[j], Q0), nnorm(f[j + 1] * p, 0, s))
                continue
        elif ob == MUL and ie:                                  # rule 5: distribute
            c = nmul(c, npowi(N[tb[1]], te[1]))
            for j in range(2, len(tb), 2):
                w = N[tb[j + 1]]
                st.append((tb[j], mk(nmul(w, te)) if w[0] <= FLT else add_([tb[j + 1]], te)))
            continue
        elif ob == MUL and tb[1] != ONE and N[tb[1]][0] == NUM and not N[tb[1]][2] and \
                N[tb[1]][1] > 0:                                # rule 6: (c*u)^e = c^e u^e
            st.append((tb[1], e))
            st.append((tb[2] if len(tb) == 4 and tb[3] == ONE else mk((MUL, ONE) + tb[2:]), e))
            continue
        elif ob == MUL and tb[1] == ONE and len(tb) == 4 and oe == NUM and not te[2] and (
                V[tb[2]] or isreal(tb[2])):                     # rule 7: (u^2k)^e, u real
            w = N[tb[3]]
            if w[0] == NUM and not w[2] and w[3] == 1 and not w[1] & 1:
                x = nmul(w, te)
                if x[3] == 1:
                    st.append((absn(tb[2]) if x[1] & 1 else tb[2], mk(x)))
                    continue
        elif b == E and oe == LN:                               # rule 8: e^ln(u) = u
            st.append((te[1], ONE))
            continue
        elif b == E and oe == MUL and len(te) == 4 and te[3] == ONE:
            q = N[te[1]]
            if N[te[2]][0] == LN and q[0] == NUM and not q[2] and q[3] == 1:
                st.append((N[te[2]][1], te[1]))                 # e^(n ln u) = u^n
                continue
            if te[2] == PI and q[0] == NUM and not q[1] and 4 % q[3] == 0:
                a = q[2] * (4 // q[3]) % 8                      # e^(i pi a/4)
                if a & 1:
                    c = nmul(c, OMEGA[a])
                    rad[2] = nadd(rad.get(2, Q0), QH)
                else:
                    c = nmul(c, IPOW[a >> 1])
                continue
        elif ob == ABS and ie and not te[1] & 1 and (V[tb[1]] or isreal(tb[1])):
            st.append((tb[1], e))                               # rule 9: abs(u)^2k = u^2k
            continue
        if ob == ADD and ie and negfirst(b):                    # (-S)^n = (-1)^n S^n (6.4)
            b = neg_(b)
            c = nneg(c) if te[1] & 1 else c
        if b in acc:                                            # rule 10: merge, then recheck
            x = acc.pop(b)
            w = N[x]
            st.append((b, mk(nadd(w, te)) if w[0] <= FLT and oe <= FLT else add_([x, e])))
        else:
            acc[b] = e
    lst = []
    for q in rad:                                               #@unordered-ok (sorted below)
        x = rad[q]
        n = x[1] // x[3]
        c = nmul(c, (NUM, q ** n, 0, 1))
        if x[1] - n * x[3]:
            lst.append((x[3], x[1] - n * x[3], q))
    lst.sort()
    j = 0
    while j < len(lst):                                         # rule 11: one base per exponent
        x = lst[j]
        g = 1
        while j < len(lst) and lst[j][:2] == x[:2]:
            g *= lst[j][2]
            j += 1
        b = mk((NUM, g, 0, 1))
        e = mk((NUM, x[1], 0, x[0]))
        acc[b] = add_([acc[b], e]) if b in acc else e
    if inf:
        if not c[1] and not c[2]:
            return UNDEF                                        # 0 * oo
        if not c[2]:
            c = Q1 if c[1] > 0 else QM1
        acc[OO] = ONE
    if not c[1] and not c[2]:
        return ZERO
    lst = []
    for b in acc:                                               #@unordered-ok (sorted below)
        lst.append((H[b], b, acc[b]))
    if not lst:
        return mk(c)
    if len(lst) == 1 and lst[0][2] == ONE:
        b = lst[0][1]
        if c == Q1:
            return b
        if c == QM1 and N[b][0] == ADD:
            return neg_(b)
    lst.sort()
    tiefix(lst)
    out = [MUL, mk(c)]
    for r in lst:
        out.append(r[1])
        out.append(r[2])
    return mk(tuple(out))


def fn_(op, a):                                                 #@L 5
    # canonical op(a) for a function of one argument (6.3, 6.4)
    chk(a)
    if a == UNDEF:
        return UNDEF
    if op == ABS:
        return absn(a)
    g = 1                                    # g < 0: the result is negated (odd functions)
    if (op in ODDF or op in EVENF) and negfirst(a):
        a = neg_(a)
        g = -1 if op in ODDF else 1
    t = N[a]
    r = 0
    tb = None
    z = 1                                    # the sign of a table value
    if a == OO or isninf(a):
        if op == ATAN:
            r = mk((MUL, HALF, PI, ONE))
        elif op == TANH or op == SIGN:
            r = ONE if a == OO or op == TANH else MONE
        elif op == FLOOR or op == CEIL:
            r = a
        else:
            r = OO if a == OO and op in (LN, SINH, COSH, FACT) else UNDEF
    elif SIN <= op <= TAN and t[0] == op + 6:                    # sin(asin u) = u, ...
        r = t[1]
    elif SIN <= op <= COT:                                      # trig at multiples of pi/120
        q = Q0 if a == ZERO else Q1 if a == PI else None
        if t[0] == MUL and len(t) == 4 and t[2] == PI and t[3] == ONE:
            q = N[t[1]]
        if q is not None and q[0] == NUM and not q[2] and q[1] * 120 % q[3] == 0:
            m = q[1] * 120 // q[3] % 240
            if op == SIN or op == CSC or op == COT:
                m = (60 - m) % 240              # sin x = cos(pi/2 - x), cot x = tan(pi/2 - x)
            if op == TAN or op == COT:
                m %= 120
                if m > 60:
                    m = 120 - m
                    z = -1
                tb = TAN_T.get(m)
            else:
                if m > 120:
                    m = 240 - m
                if m > 60:
                    m = 120 - m
                    z = -1
                tb = (COS_T if op <= COS else SEC_T).get(m)
            if m == 60 and op != SIN and op != COS:
                raise Undefined()               # tan(pi/2), sec(pi/2), csc(0), cot(0)
    elif ASIN <= op <= ATAN and not V[a]:      # inverse trig of a (signed) table value
        m = (ATAN_H if op == ATAN else ASIN_H).get(H[a])
        if m is not None:
            z = -1 if m < 0 else 1
            tb = TAN_T[m * z] if op == ATAN else COS_T[60 - m * z]
    elif op == LN:
        if a == ZERO:
            raise Undefined()
        if a == ONE or a == E:
            r = ZERO if a == ONE else ONE
        elif t[0] == MUL and len(t) == 4 and t[1] == ONE and t[2] == E and (
                V[t[3]] or isreal(t[3])):
            r = t[3]                            # ln(e^u) = u for real u
        elif t[0] == NUM:                       # ln|z| + i*arg(z), with perfect powers split
            x = t[1]
            y = t[2]
            lst = []
            if not y:
                ns = ((x if x > 0 else -x, Q1), (t[3], QM1))
                if x < 0:
                    lst.append(mk((MUL, I, PI, ONE)))
            else:
                ns = ((x * x + y * y, QH), (t[3], QM1))
                k = 1 if y > 0 else -1
                if not x:
                    lst.append(mk((MUL, mk((NUM, 0, k, 2)), PI, ONE)))
                elif x == y or x == -y:
                    lst.append(mk((MUL, mk((NUM, 0, k * (1 if x > 0 else 3), 4)), PI, ONE)))
                else:
                    w = mk((ATAN, mk(nnorm(y if y > 0 else -y, 0, x if x > 0 else -x))))
                    lst.append(mk((MUL, mk((NUM, 0, 1 if x * y > 0 else -1, 1)), w, ONE)))
                    if x < 0:
                        lst.append(mk((MUL, mk((NUM, 0, k, 1)), PI, ONE)))
            for n, w in ns:
                if n > 1:
                    f = ifac(n)
                    p = 0
                    for j in range(1, len(f), 2):
                        h = f[j]
                        while h:
                            p, h = h, p % h
                    q = 1
                    for j in range(0, len(f), 2):
                        q *= f[j] ** (f[j + 1] // p)
                    w = nmul(w, (NUM, p, 0, 1))
                    x = mk((LN, mk((NUM, q, 0, 1))))
                    lst.append(x if w == Q1 else mk((MUL, mk(w), x, ONE)))
            r = add_(lst)
    elif a == ZERO and SINH <= op <= TANH:
        r = ONE if op == COSH else ZERO
    elif op == SIGN:
        x = csign(a)
        r = ZERO if a == ZERO else ONE if x > 0 else MONE if x < 0 else 0
    elif t[0] == NUM and not t[2] and (op == FLOOR or op == CEIL):
        r = mk((NUM, t[1] // t[3] if op == FLOOR else -(-t[1] // t[3]), 0, 1))
    elif op == FACT and t[0] == NUM and not t[2] and t[3] == 1 and t[1] <= 1000:
        if t[1] < 0:
            raise Undefined()
        x = 1
        for j in range(2, t[1] + 1):
            x *= j
        r = mk((NUM, x, 0, 1))
    if tb is not None:                                          # build a table value
        lst = []
        for v in tb:
            x = mk(nnorm(v[0] * z, 0, v[1]))
            if len(v) == 5:
                w = mk((ADD, mk((NUM, v[2], 0, 1)), mk((MUL, ONE, mk((NUM, v[4], 0, 1)), HALF)),
                        mk((NUM, v[3], 0, 1))))
                x = mk((MUL, x, w, HALF))
            elif v[2] > 1:
                x = mk((MUL, x, mk((NUM, v[2], 0, 1)), HALF))
            lst.append(x)
        r = add_(lst)
        if op >= ASIN:                                          # the angle, if it matches
            if op == ACOS:
                m = 60 - m                      # acos u = pi/2 - asin u
            x = nnorm(m, 0, 120)
            r = 0 if r != a else ZERO if not m else PI if x == Q1 else mk((MUL, mk(x), PI, ONE))
    if not r:
        r = mk((op, a))
    return neg_(r) if g < 0 else r


def rel_(op, a, b):                                             #@L 5
    # a relation (8.2); a numeric difference folds to TRUE or FALSE
    chk(a)
    chk(b)
    if op >= GT:
        a, b = b, a
        op -= GT - LT
    d = add_([a, neg_(b)])
    t = N[d]
    if d == UNDEF:
        return UNDEF
    if d == OO or isninf(d):
        s = 1 if d == OO else -1
    elif t[0] > FLT:
        return mk((op, a, b))
    elif op <= NE:
        s = 1 if t[1] or t[2] else 0
    else:
        s = nsign(t)
    if op == EQ or op == NE:
        return TRUE if (s == 0) == (op == EQ) else FALSE
    return TRUE if s < 0 or (s == 0 and op == LE) else FALSE
