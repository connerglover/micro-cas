"""Invariant scan over the node table (DESIGN.md section 8.9).

``scan(K)`` reads the node module ``K`` (``node.py``: ``N H V NN``, op codes, preallocated ids,
``SYMI``, ``B``/``NX``, ``RULECACHE``, ``negfirst``) and returns a list of violation strings.
It runs after every test, outside the depth checker, so it costs the code under test nothing.
It is an independent reference: hashes, masks and the canonical pair order are recomputed
here from the definitions in DESIGN sections 5.2-5.8, 6.1-6.4 and 8.2, not taken from K.

Checks (names usable with ``skip=`` and the ``invariants_skip(...)`` marker):

    slots     N[1:NN] are flat tuples; N[NN:] are None; NN <= len(N)
    prealloc  ZERO .. FALSE hold their section 5.5 tuples
    topo      children are older (smaller ids) than parents
    unique    no two ids hold equal tuples (hash-consing)
    hash      H[i] equals the section 5.7 recomputation
    mask      V[i] equals the section 5.8 recomputation
    buckets   every id is on exactly its bucket's chain, newest first
    num       NUM (a, b, d): ints, d >= 1, gcd(a, b, d) == 1; FLT finite, no -0.0
    arity     composite shapes (ADD/MUL pair counts, relations, functions, CALL, HOLD)
    add       section 5.3 ADD invariants
    mul       section 5.3 MUL invariants, radicals (6.2) and constructor rules 5-9 (8.2)
    order     ADD/MUL pairs in (H, tiefix) order (5.7)
    special   fn_ normal forms (6.4): sin(0), ln(1), ln(e), ln(e^u), trig at k*pi/12,
              inverse cancellation, ln of non-prime-power arguments, numbers in sign/floor/
              ceil/fact, functions of +-oo
    sign      no odd/even function or abs has an argument u with K.negfirst(u) (D15)
    abs       abs of a number, oo, a provably positive constant, a numeric coefficient,
              a sum with rational content != 1, or w^(2k)
    sentinel  TRUE, FALSE, DNE, DIVG and HOLD never inside an ADD, MUL or function node
    undef     UNDEF never inside an ADD, MUL or function node ("undef absorbs everything")
    wild      every node containing a WILD is reachable from RULECACHE

A MUL that is the child of a HOLD is display-only and exempt from add/mul/order.
"""
import math
from functools import cmp_to_key

M25 = 0x1FFFFFF
OVF = 1 << 29

OPS = {
    'NUM': 0, 'FLT': 1, 'SYM': 2, 'CON': 3, 'WILD': 4, 'COMP': 8,
    'ADD': 8, 'MUL': 9, 'CALL': 10, 'LST': 11, 'EQ': 12, 'NE': 13, 'LT': 14, 'LE': 15,
    'BIGO': 16, 'DNE': 17, 'DIVG': 18, 'HOLD': 19, 'FN0': 24,
    'SIN': 24, 'COS': 25, 'TAN': 26, 'SEC': 27, 'CSC': 28, 'COT': 29, 'ASIN': 30,
    'ACOS': 31, 'ATAN': 32, 'SINH': 33, 'COSH': 34, 'TANH': 35, 'LN': 36, 'ABS': 37,
    'SIGN': 38, 'FLOOR': 39, 'CEIL': 40, 'FACT': 41,
}
# name -> (default id, op name, payload) per section 5.5
PREALLOC = (
    ('ZERO', 1, ('NUM', 0, 0, 1)), ('ONE', 2, ('NUM', 1, 0, 1)),
    ('MONE', 3, ('NUM', -1, 0, 1)), ('TWO', 4, ('NUM', 2, 0, 1)),
    ('HALF', 5, ('NUM', 1, 0, 2)), ('I', 6, ('NUM', 0, 1, 1)), ('PI', 7, ('CON', 0)),
    ('E', 8, ('CON', 1)), ('OO', 9, ('CON', 2)), ('UNDEF', 10, ('CON', 3)),
    ('TEN', 11, ('NUM', 10, 0, 1)), ('LN10', 12, ('LN', 'TEN')),
    ('TRUE', 13, ('CON', 4)), ('FALSE', 14, ('CON', 5)),
)
ODD = ('SIN', 'TAN', 'CSC', 'COT', 'ASIN', 'ATAN', 'SINH', 'TANH')
EVEN = ('COS', 'SEC', 'COSH')
TRIG = ('SIN', 'COS', 'TAN', 'SEC', 'CSC', 'COT')
INVERSE = (('SIN', 'ASIN'), ('COS', 'ACOS'), ('TAN', 'ATAN'))
INF_FOLD = ('LN', 'ATAN', 'TANH', 'ABS', 'SIGN', 'SIN', 'COS', 'TAN', 'FLOOR', 'CEIL')

CHECKS = ('slots', 'prealloc', 'topo', 'unique', 'hash', 'mask', 'buckets', 'num', 'arity',
          'add', 'mul', 'order', 'special', 'sign', 'abs', 'sentinel', 'undef', 'wild')


class Ctx(object):
    """The node module's tables and constants, with section 5 defaults."""

    def __init__(self, K):
        self.K = K
        self.op = {}
        for k in OPS:
            self.op[k] = getattr(K, k, OPS[k])
        self.N = K.N
        self.H = K.H
        self.V = K.V
        self.NN = K.NN
        self.id = {}
        for name, default, _ in PREALLOC:
            self.id[name] = getattr(K, name, default)
        self.dead = getattr(K, 'DEAD', None)
        self.SYMI = getattr(K, 'SYMI', None)


# -- reference computations ------------------------------------------------------------------

def ref_hash(t, H, op=OPS):
    """The section 5.7 structural hash of tuple t, given the children's hashes H."""
    o = t[0]
    if o >= op['COMP']:
        h = o
        for c in t[1:]:
            h = ((h << 5) ^ (h >> 20) ^ H[c]) & M25
        return h
    if o == op['NUM']:
        return (((t[1] % 33554393) << 3) ^ ((t[2] % 1048573) << 1) ^ (t[3] % 65521)) & M25
    if o == op['SYM']:
        h = 5381
        for ch in t[1]:
            h = ((h << 5) ^ (h >> 20) ^ ord(ch)) & M25
        return h
    if o == op['FLT']:
        h = o
        for v in (t[1], t[2]):
            m, x = math.frexp(v)
            h = ((h << 5) ^ (h >> 20) ^ (int(m * 1048576) & M25) ^ ((x & 255) << 17)) & M25
        return h
    return ((o << 12) ^ (t[1] << 4) ^ t[-1]) & M25          # CON, WILD


def iroot(n, k):
    """floor(n ** (1/k)) for n >= 0, by integer Newton."""
    if n < 2:
        return n
    x = 1 << ((len('%x' % n) * 4 + k - 1) // k)
    while True:
        y = ((k - 1) * x + n // x ** (k - 1)) // k
        if y >= x:
            break
        x = y
    while x ** k > n:
        x -= 1
    while (x + 1) ** k <= n:
        x += 1
    return x


def rootsplit_free(n, s):
    """True if n is s-th-power-free as far as K.rootsplit can tell (DESIGN 6.2, step 3):
    trial division up to min(10^4, n^(1/3)), then a perfect s-th power test of the cofactor."""
    bound = min(10 ** 4, iroot(n, 3))
    c = n
    p = 2
    while p <= bound:
        if c % (p ** s) == 0:
            return False
        while c % p == 0:
            c //= p
        p += 1
    if c > 1 and iroot(c, s) ** s == c:
        return False
    return True


def is_perfect_power(n):
    if n < 4:
        return False
    k = 2
    while (1 << k) <= n:
        r = iroot(n, k)
        if r ** k == n:
            return True
        k += 1
    return False


def _payload(t, op):
    o = t[0]
    if o == op['NUM']:
        return (t[1], t[2], t[3])
    if o == op['FLT']:
        return (t[1], t[2])
    return tuple(t[1:])


def _cmp(a, b):
    return (a > b) - (a < b)


def struct_cmp(a, b, N, H, op=OPS):
    """The id-independent tie-break of section 5.7 for two nodes with equal H."""
    if a == b:
        return 0
    ta = N[a]
    tb = N[b]
    c = _cmp((ta[0], len(ta)), (tb[0], len(tb)))
    if c:
        return c
    if ta[0] < op['COMP']:
        return _cmp(_payload(ta, op), _payload(tb, op))
    ha = []
    hb = []
    for x in ta[1:]:
        ha.append(H[x])
    for x in tb[1:]:
        hb.append(H[x])
    c = _cmp(tuple(ha), tuple(hb))
    if c:
        return c
    st = [(a, b)]
    while st:
        x, y = st.pop()
        if x == y:
            continue
        tx = N[x]
        ty = N[y]
        c = _cmp((tx[0], len(tx)), (ty[0], len(ty)))
        if c:
            return c
        if tx[0] < op['COMP']:
            c = _cmp(_payload(tx, op), _payload(ty, op))
            if c:
                return c
            continue
        for j in range(len(tx) - 1, 0, -1):
            st.append((tx[j], ty[j]))
    return 0


def canonical_order(ids, N, H, op=OPS):
    """The section 5.7 canonical order of distinct ids (H, then the structural tie-break)."""
    def cmp(a, b):
        c = _cmp(H[a], H[b])
        return c if c else struct_cmp(a, b, N, H, op)
    return sorted(ids, key=cmp_to_key(cmp))


# -- the scan ------------------------------------------------------------------------------

def scan(K, skip=()):
    """Return a list of invariant violations of the live node table of module K."""
    c = Ctx(K)
    op = c.op
    N, H, V, NN = c.N, c.H, c.V, c.NN
    errs = []
    on = {}
    for k in CHECKS:
        on[k] = k not in skip

    def bad(check, i, msg):
        errs.append('[%s] id %d %r: %s' % (check, i, N[i] if 0 <= i < len(N) else None, msg))

    def isnum(i):
        return N[i][0] in (op['NUM'], op['FLT'])

    def iszero(i):
        t = N[i]
        if t[0] == op['NUM']:
            return t[1] == 0 and t[2] == 0
        if t[0] == op['FLT']:
            return t[1] == 0.0 and t[2] == 0.0
        return False

    def realnum(i):          # a real NUM tuple, or None
        t = N[i]
        if t[0] == op['NUM'] and t[2] == 0:
            return t
        return None

    def isint(i):
        t = N[i]
        return t[0] == op['NUM'] and t[2] == 0 and t[3] == 1

    def neginf(i):
        t = N[i]
        return t[0] == op['MUL'] and len(t) == 4 and t[2] == c.id['OO'] and \
            t[3] == c.id['ONE'] and realnum(t[1]) is not None and N[t[1]][1] < 0

    if NN > len(N):
        errs.append('[slots] NN=%d exceeds len(N)=%d' % (NN, len(N)))
        return errs
    live = []
    for i in range(1, NN):
        t = N[i]
        if c.dead is not None and type(t) is tuple and len(t) == 1 and t[0] == c.dead:
            continue
        if type(t) is not tuple or not t or type(t[0]) is not int:
            if on['slots']:
                errs.append('[slots] id %d holds %r, not a node tuple' % (i, t))
            continue
        live.append(i)
    if on['slots']:
        for i in range(NN, len(N)):
            if N[i] is not None:
                errs.append('[slots] id %d >= NN=%d still holds %r' % (i, NN, N[i]))
                break
    if errs:
        return errs
    # HOLD-exempt MULs
    held = set()
    for i in live:
        if N[i][0] == op['HOLD'] and len(N[i]) == 2:
            held.add(N[i][1])
    if on['prealloc'] and NN > max(c.id.values()):
        for name, _, (oname, *pay) in PREALLOC:
            i = c.id[name]
            if oname == 'LN':
                want = (op['LN'], c.id['TEN'])
            else:
                want = (op[oname],) + tuple(pay)
            if N[i] != want:
                bad('prealloc', i, '%s should be %r' % (name, want))
    fn_ops = set()
    for k in OPS:
        if OPS[k] >= OPS['FN0'] and k != 'FN0':
            fn_ops.add(op[k])
    seen = {}
    for i in live:
        t = N[i]
        o = t[0]
        comp = o >= op['COMP']
        # -- shape and topology
        if comp:
            for x in t[1:]:
                if type(x) is not int or x < 1 or x >= i:
                    if on['topo']:
                        bad('topo', i, 'child %r is not an older id' % (x,))
                    break
        if on['unique']:
            j = seen.get(t)
            if j is not None:
                bad('unique', i, 'same tuple as id %d' % j)
            else:
                seen[t] = i
        if comp and any(type(x) is not int or x < 1 or x >= i for x in t[1:]):
            continue                                    # the rest would read garbage
        if on['hash']:
            h = ref_hash(t, H, op) if o != op['FLT'] or _flt_ok(t) else None
            if h is not None and H[i] != h:
                bad('hash', i, 'H=%#x, recomputed %#x' % (H[i], h))
        if on['mask']:
            want = 0
            if comp:
                for x in t[1:]:
                    want |= V[x]
            elif o == op['SYM'] and c.SYMI is not None:
                bit = c.SYMI.get(t[1])
                if bit is None:
                    bad('mask', i, 'symbol %r is not in SYMI' % (t[1],))
                    want = V[i]
                else:
                    want = (1 << bit) if bit < 29 else OVF
            elif o == op['SYM']:
                want = V[i]
            if V[i] != want:
                bad('mask', i, 'V=%#x, recomputed %#x' % (V[i], want))
        # -- leaves
        if o == op['NUM'] and on['num']:
            if len(t) != 4 or any(type(x) is not int for x in t[1:]):
                bad('num', i, 'NUM must be (NUM, a, b, d) with ints')
            elif t[3] < 1:
                bad('num', i, 'denominator < 1')
            elif math.gcd(math.gcd(t[1], t[2]), t[3]) != 1:
                bad('num', i, 'gcd(a, b, d) != 1')
        elif o == op['FLT'] and on['num']:
            if len(t) != 3 or type(t[1]) is not float or type(t[2]) is not float:
                bad('num', i, 'FLT must be (FLT, re, im) with floats')
            elif not _flt_ok(t):
                bad('num', i, 'FLT must be finite with no -0.0')
        elif o == op['SYM'] and on['num']:
            if len(t) != 2 or type(t[1]) is not str or not t[1] or \
                    any(ord(ch) > 126 or ord(ch) < 33 for ch in t[1]):
                bad('num', i, 'SYM must be (SYM, ascii name)')
        elif o == op['CON'] and on['num']:
            if len(t) != 2 or t[1] not in (0, 1, 2, 3, 4, 5):
                bad('num', i, 'CON k must be 0..5')
        if not comp:
            continue
        # -- arity
        if on['arity']:
            n = len(t)
            if o in (op['ADD'], op['MUL']) and (n < 4 or n % 2):
                bad('arity', i, 'ADD/MUL need a head slot and >= 1 pair')
                continue
            if o in (op['EQ'], op['NE'], op['LT'], op['LE'], op['DNE']) and n != 3:
                bad('arity', i, 'needs exactly 2 children')
            if o in (op['BIGO'], op['DIVG'], op['HOLD']) and n != 2:
                bad('arity', i, 'needs exactly 1 child')
            if o in fn_ops and n != 2:
                bad('arity', i, 'a function node has exactly 1 argument')
            if o == op['CALL'] and (n < 2 or N[t[1]][0] != op['SYM']):
                bad('arity', i, 'CALL needs a SYM head')
            if o == op['HOLD'] and n == 2 and N[t[1]][0] != op['MUL']:
                bad('arity', i, 'HOLD holds a MUL')
        # -- sentinels and undef inside ADD / MUL / functions
        if o in (op['ADD'], op['MUL']) or o in fn_ops:
            for x in t[1:]:
                tx = N[x]
                if on['sentinel'] and (x == c.id['TRUE'] or x == c.id['FALSE'] or
                                       tx[0] in (op['DNE'], op['DIVG'], op['HOLD'])):
                    bad('sentinel', i, 'contains the sentinel id %d %r' % (x, tx))
                if on['undef'] and x == c.id['UNDEF']:
                    bad('undef', i, 'contains UNDEF')
        if o == op['ADD'] and on['add'] and i not in held:
            _check_add(c, i, t, bad, isnum, iszero)
        if o == op['MUL'] and on['mul'] and i not in held:
            _check_mul(c, i, t, bad, isnum, iszero, realnum, isint)
        if o in (op['ADD'], op['MUL']) and on['order'] and i not in held:
            ts = list(t[2::2])
            if len(set(ts)) == len(ts):
                want = canonical_order(ts, N, H, op)
                if want != ts:
                    bad('order', i, 'pairs not in (H, tiefix) order; want terms %r' % (want,))
        if o in fn_ops:
            u = t[1]
            name = _opname(c, o)
            if on['special']:
                _check_special(c, i, name, u, bad, realnum, isint, neginf)
            if on['sign'] and (name in ODD or name in EVEN or name == 'ABS'):
                nf = getattr(K, 'negfirst', None)
                if nf is not None and nf(u):
                    bad('sign', i, '%s argument should be sign-normalized (negfirst)' % name)
            if on['abs'] and name == 'ABS':
                _check_abs(c, i, u, bad, isnum, realnum, isint, neginf)
    if on['buckets'] and not getattr(K, 'DEBUG_ARENA', False):
        _check_buckets(c, errs)
    if on['wild']:
        _check_wild(c, live, errs)
    return errs


def _flt_ok(t):
    for v in t[1:3]:
        if type(v) is not float or v != v or v in (float('inf'), float('-inf')):
            return False
        if v == 0.0 and math.copysign(1.0, v) < 0:
            return False
    return True


def _opname(c, o):
    for k in OPS:
        if c.op[k] == o and OPS[k] >= OPS['FN0'] and k != 'FN0':
            return k
    return '?'


def _check_add(c, i, t, bad, isnum, iszero):
    op = c.op
    N = c.N
    if not isnum(t[1]):
        bad('add', i, 'constant is not a number')
    terms = t[2::2]
    coefs = t[3::2]
    for k in coefs:
        if not isnum(k):
            bad('add', i, 'coefficient %d is not a number' % k)
        elif iszero(k):
            bad('add', i, 'zero coefficient')
    for x in terms:
        tx = N[x]
        if tx[0] in (op['NUM'], op['FLT']):
            bad('add', i, 'term %d is a number' % x)
        elif tx[0] == op['ADD']:
            bad('add', i, 'term %d is a nested ADD' % x)
        elif tx[0] == op['MUL'] and tx[1] != c.id['ONE']:
            bad('add', i, 'term %d is a MUL whose coefficient is not 1' % x)
    if len(set(terms)) != len(terms):
        bad('add', i, 'like terms not collected')
    if len(terms) == 1 and t[1] == c.id['ZERO']:
        bad('add', i, 'one pair and a zero constant: should be the product k*t')


def _check_mul(c, i, t, bad, isnum, iszero, realnum, isint):
    op = c.op
    N = c.N
    k = t[1]
    if not isnum(k):
        bad('mul', i, 'coefficient is not a number')
    elif iszero(k):
        bad('mul', i, 'zero coefficient')
    bases = t[2::2]
    exps = t[3::2]
    if len(set(bases)) != len(bases):
        bad('mul', i, 'equal bases not merged')
    for b, e in zip(bases, exps):
        tb = N[b]
        te = N[e]
        if iszero(e):
            bad('mul', i, 'zero exponent on base %d' % b)
            continue
        enum = te[0] in (op['NUM'], op['FLT'])
        if tb[0] in (op['NUM'], op['FLT']):
            if not enum:
                continue                                       # 2^x
            if tb[0] == op['FLT'] or te[0] == op['FLT']:
                bad('mul', i, 'float base or exponent with a numeric partner: should fold')
                continue
            ea, eb, ed = te[1], te[2], te[3]
            if eb != 0:
                continue                                       # a non-real exponent: kept
            if ed == 1:
                bad('mul', i, 'number %d under an integer exponent: should fold' % b)
            elif tb[2] != 0:
                continue                                       # non-real base, rule 4
            elif tb[3] == 1 and tb[1] >= 2:
                if not (0 < ea < ed):
                    bad('mul', i, 'radical exponent %d/%d not in (0, 1)' % (ea, ed))
                elif not rootsplit_free(tb[1], ed):
                    bad('mul', i, 'radicand %d is not %d-th-power-free' % (tb[1], ed))
            elif tb[3] == 1 and tb[1] < 0 and ed % 2 == 0 and ed >= 4 and 0 < ea < ed:
                continue                                       # even root >= 4 of a negative
            else:
                bad('mul', i, 'numeric base %r under %d/%d is not a canonical radical'
                    % (tb, ea, ed))
            continue
        if tb[0] == op['MUL'] and isint(e):
            bad('mul', i, 'a MUL base under an integer exponent: should be flattened')
        if tb[0] == op['MUL'] and enum and not isint(e) and te[0] == op['NUM']:
            kc = realnum(tb[1])
            if kc is not None and kc[1] > 0 and tb[1] != c.id['ONE']:
                bad('mul', i, 'positive coefficient of a MUL base under a non-integer '
                              'exponent: should be pulled out (rule 6)')
            if tb[1] == c.id['ONE'] and len(tb) == 4 and isint(tb[3]) and \
                    N[tb[3]][1] % 2 == 0 and te[2] == 0 and \
                    (N[tb[3]][1] * te[1]) % te[3] == 0:
                bad('mul', i, '(u^even)^r with an integer product: should be abs (rule 7)')
        if b == c.id['E']:
            if te[0] == op['LN']:
                bad('mul', i, 'e^ln(u): should be u (rule 8)')
            elif te[0] == op['MUL'] and len(te) == 4 and N[te[2]][0] == op['LN'] and \
                    te[3] == c.id['ONE'] and isint(te[1]):
                bad('mul', i, 'e^(n*ln(u)): should be u^n (rule 8)')
        if tb[0] == op['ABS'] and isint(e) and N[e][1] % 2 == 0:
            bad('mul', i, 'abs(u)^even: should be u^even (rule 9)')
    if len(bases) == 1 and exps[0] == c.id['ONE']:
        if k == c.id['ONE']:
            bad('mul', i, 'k == 1 with one pair (b, 1): should be b')
        elif N[bases[0]][0] == op['ADD'] and k == c.id['MONE']:
            bad('mul', i, '-(sum): should be distributed')


def _check_special(c, i, name, u, bad, realnum, isint, neginf):
    op = c.op
    N = c.N
    tu = N[u]
    if u == c.id['OO'] or neginf(u):
        if name in INF_FOLD:
            bad('special', i, '%s of an infinity should fold (section 6.3)' % name)
        return
    if name in TRIG:
        q = None
        if u == c.id['ZERO']:
            q = (0, 1)
        elif u == c.id['PI']:
            q = (1, 1)
        elif tu[0] == op['MUL'] and len(tu) == 4 and tu[2] == c.id['PI'] and \
                tu[3] == c.id['ONE'] and realnum(tu[1]) is not None:
            q = (N[tu[1]][1], N[tu[1]][3])
        if q is not None and (12 * q[0]) % q[1] == 0:
            bad('special', i, '%s at a multiple of pi/12 should fold' % name)
    for f, inv in INVERSE:
        if name == f and tu[0] == op[inv]:
            bad('special', i, '%s(%s(u)) should cancel' % (f.lower(), inv.lower()))
    if name == 'LN':
        if u == c.id['ONE'] or u == c.id['E']:
            bad('special', i, 'ln(1) / ln(e) should fold')
        elif tu[0] == op['MUL'] and len(tu) == 4 and tu[1] == c.id['ONE'] and \
                tu[2] == c.id['E']:
            bad('special', i, 'ln(e^u) should be u')
        elif tu[0] == op['NUM']:
            if not (tu[2] == 0 and tu[3] == 1 and tu[1] >= 2) or is_perfect_power(tu[1]):
                bad('special', i, 'ln of a number: only primes and other non-powers >= 2')
    if name in ('SIGN', 'FLOOR', 'CEIL') and realnum(u) is not None:
        bad('special', i, '%s of a real number should fold' % name.lower())
    if name == 'FACT' and isint(u) and tu[1] <= 1000:
        bad('special', i, 'n! of an integer n <= 1000 should fold')


def _pos_const(c, u, isint):
    """Provably positive constant, narrowly (DESIGN 6.4): positive numbers, pi, e, positive
    radicals, and sums and products of these with positive integer powers."""
    op = c.op
    N = c.N
    t = N[u]

    def atom_pos(x):
        tx = N[x]
        if tx[0] == op['NUM']:
            return tx[2] == 0 and tx[1] > 0
        return x == c.id['PI'] or x == c.id['E']

    def prod_pos(x):
        if atom_pos(x):
            return True
        tx = N[x]
        if tx[0] != op['MUL']:
            return False
        if not atom_pos(tx[1]):
            return False
        for j in range(2, len(tx), 2):
            b, e = tx[j], tx[j + 1]
            tb, te = N[b], N[e]
            if b == c.id['PI'] or b == c.id['E']:
                if not (isint(e) and te[1] > 0):
                    return False
            elif tb[0] == op['NUM'] and tb[2] == 0 and tb[3] == 1 and tb[1] >= 2:
                if not (te[0] == op['NUM'] and te[2] == 0 and 0 < te[1] < te[3]):
                    return False
            else:
                return False
        return True

    if c.V[u] != 0:
        return False
    if prod_pos(u):
        return True
    if t[0] == op['ADD']:
        k0 = N[t[1]]
        if not (k0[0] == op['NUM'] and k0[2] == 0 and k0[1] >= 0):
            return False
        for j in range(2, len(t), 2):
            kj = N[t[j + 1]]
            if not (kj[0] == op['NUM'] and kj[2] == 0 and kj[1] > 0 and prod_pos(t[j])):
                return False
        return True
    return False


def _check_abs(c, i, u, bad, isnum, realnum, isint, neginf):
    op = c.op
    N = c.N
    tu = N[u]
    if isnum(u):
        bad('abs', i, 'abs of a number should be its modulus')
        return
    if u == c.id['OO'] or neginf(u):
        return                                                 # reported by 'special'
    if _pos_const(c, u, isint):
        bad('abs', i, 'abs of a provably positive constant should be the constant')
    if tu[0] == op['MUL']:
        if realnum(tu[1]) is not None and tu[1] != c.id['ONE']:
            bad('abs', i, 'abs(c*w) with a real coefficient: should be |c|*abs(w)')
        if tu[1] == c.id['ONE'] and len(tu) == 4 and isint(tu[3]) and N[tu[3]][1] % 2 == 0:
            bad('abs', i, 'abs(w^(2k)) should be w^(2k)')
    if tu[0] == op['ADD']:
        nums = []
        dens = []
        for j in range(1, len(tu), 2):
            q = realnum(tu[j])
            if q is None:
                return
            if q[1]:
                nums.append(abs(q[1]))
                dens.append(q[3])
        g = 0
        for x in nums:
            g = math.gcd(g, x)
        L = 1
        for x in dens:
            L = L * x // math.gcd(L, x)
        if nums and (g != 1 or L != 1):
            bad('abs', i, 'abs of a sum with rational content %d/%d: should be pulled out'
                % (g, L))


def _check_buckets(c, errs):
    K = c.K
    B = getattr(K, 'B', None)
    NX = getattr(K, 'NX', None)
    if B is None or NX is None:
        return
    NB = len(B)
    N, H, NN = c.N, c.H, c.NN
    seen = set()
    for b in range(NB):
        i = B[b]
        prev = NN
        steps = 0
        while i:
            steps += 1
            if i >= prev or i >= NN or steps > NN:
                errs.append('[buckets] bucket %d: chain is not strictly decreasing below NN '
                            'at id %d' % (b, i))
                break
            if H[i] & (NB - 1) != b:
                errs.append('[buckets] id %d is on bucket %d but hashes to %d'
                            % (i, b, H[i] & (NB - 1)))
            if i in seen:
                errs.append('[buckets] id %d is on two chains' % i)
                break
            seen.add(i)
            prev = i
            i = NX[i]
    for i in range(1, NN):
        if i not in seen and N[i] is not None and not (
                c.dead is not None and len(N[i]) == 1 and N[i][0] == c.dead):
            errs.append('[buckets] id %d %r is on no bucket chain (mk cannot find it)'
                        % (i, N[i]))
            break


def _check_wild(c, live, errs):
    op = c.op
    N = c.N
    rc = getattr(c.K, 'RULECACHE', None)
    roots = []
    st = [rc] if rc is not None else []
    while st:
        x = st.pop()
        if isinstance(x, dict):
            for k in x:                       # values only: keys are names and op codes
                st.append(x[k])
        elif isinstance(x, (tuple, list)):
            for y in x:
                if isinstance(y, int) and not isinstance(y, bool):
                    roots.append(y)
                elif isinstance(y, (tuple, list, dict)):
                    st.append(y)
        elif isinstance(x, int) and not isinstance(x, bool):
            roots.append(x)
    ok = set()
    st = [r for r in roots if 0 < r < c.NN]
    while st:
        x = st.pop()
        if x in ok:
            continue
        ok.add(x)
        t = N[x]
        if type(t) is tuple and t and t[0] >= op['COMP']:
            for y in t[1:]:
                if type(y) is int and 0 < y < x:
                    st.append(y)
    haswild = set()
    for i in live:
        t = N[i]
        w = t[0] == op['WILD']
        if not w and t[0] >= op['COMP']:
            for y in t[1:]:
                if y in haswild:
                    w = True
                    break
        if w:
            haswild.add(i)
            if i not in ok:
                errs.append('[wild] id %d %r contains a WILD but is not reachable from '
                            'RULECACHE' % (i, t))


def check(K, skip=()):
    """Raise AssertionError listing every violation (at most 20 lines)."""
    errs = scan(K, skip)
    if errs:
        more = '' if len(errs) <= 20 else '\n... and %d more' % (len(errs) - 20)
        raise AssertionError('node-table invariants violated:\n' + '\n'.join(errs[:20]) + more)


def dump(K, lo=1, hi=None):
    """Lines 'id H V tuple' for ids lo..hi-1 (the golden nodes.txt format of section 5.6)."""
    hi = K.NN if hi is None else hi
    out = []
    for i in range(lo, hi):
        out.append('%4d  H=%07x  V=%x  %r' % (i, K.H[i], K.V[i], K.N[i]))
    return out
