"""T1.1 node core: the table, hashing, regions, canonicity and the constructors (DESIGN 5, 8.2).

Shared helpers for test_numbers.py, test_radicals.py and test_special.py live here too:
``ev`` (the numeric value of a node), ``TreeEval`` (the value of a gen.py tree with the same
conventions), the builders ``q pw prod sm pimul``, ``struct`` and the ``arena`` fixture.
Conventions (DESIGN 6.2, 8.3): a rational power p/q with q odd of a negative real is the real
root; every other power is the principal value.
"""
import cmath
import math
import os
import random

import pytest

import gen
import invariants
import node as K

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, 'golden', 'nodes.txt')
NMAXDBG = 8192


# -- builders ------------------------------------------------------------------------------------

def q(p, d=1, b=0):
    """The number (p + b*i)/d."""
    return K.num(p, b, d)


def x_():
    return K.sym('x')


def pw(b, p, d=1):
    """b^(p/d)."""
    return K.mul_(K.ONE, [(b, K.num(p, 0, d))])


def pwe(b, e):
    return K.mul_(K.ONE, [(b, e)])


def prod(*fs):
    return K.mul_(K.ONE, [(f, K.ONE) for f in fs])


def sm(*ts):
    return K.add_(list(ts))


def sub(a, b):
    return K.add_([a, K.neg_(b)])


def div(a, b):
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.MONE)])


def pimul(p, d=1):
    """(p/d)*pi."""
    return K.mul_(K.num(p, 0, d), [(K.PI, K.ONE)])


def sqrt(u):
    return pw(u, 1, 2)


def struct(e):
    """An id-free text of node e: the structural identity used by the region tests."""
    t = K.N[e]
    if t[0] < K.COMP:
        return repr(t)
    return '(%d %s)' % (t[0], ' '.join(struct(c) for c in t[1:]))


# -- numeric evaluation (test side; nev is CVALG's, T1.8) ----------------------------------------

def cre(z):
    """Round away a float-noise imaginary part."""
    z = complex(z)
    if abs(z.imag) <= 1e-11 * max(1.0, abs(z.real)):
        return complex(z.real, 0.0)
    return z


def rpow(b, p, d):
    """b^(p/d): the real root of a negative real b for odd d, else the principal value."""
    b = cre(b)
    if b == 0:
        if p > 0:
            return 0j
        raise ZeroDivisionError('0 to a negative power')
    if d == 1:
        return cre(b ** p)
    if b.imag == 0 and b.real < 0 and d % 2:
        r = (-b.real) ** (p / d)
        return complex(-r if p % 2 else r, 0.0)
    return cre(b ** (p / d))


def _sign(z):
    if z.imag:
        raise ValueError('sign of a non-real')
    return complex((z.real > 0) - (z.real < 0))


FNS = {
    K.SIN: cmath.sin, K.COS: cmath.cos, K.TAN: cmath.tan,
    K.SEC: lambda z: 1 / cmath.cos(z), K.CSC: lambda z: 1 / cmath.sin(z),
    K.COT: lambda z: 1 / cmath.tan(z), K.ASIN: cmath.asin, K.ACOS: cmath.acos,
    K.ATAN: cmath.atan, K.SINH: cmath.sinh, K.COSH: cmath.cosh, K.TANH: cmath.tanh,
    K.LN: cmath.log, K.ABS: lambda z: complex(abs(z)), K.SIGN: _sign,
    K.FLOOR: lambda z: complex(math.floor(z.real)), K.CEIL: lambda z: complex(math.ceil(z.real)),
    K.FACT: lambda z: complex(math.gamma(z.real + 1)),
}


def ev(e, env=None):
    """The complex value of node e; symbols take their values from env."""
    env = env or {}
    memo = {}

    def go(i):
        if i in memo:
            return memo[i]
        t = K.N[i]
        op = t[0]
        if op == K.NUM:
            v = complex(t[1], t[2]) / t[3]
        elif op == K.FLT:
            v = complex(t[1], t[2])
        elif op == K.SYM:
            v = complex(env[t[1]])
        elif op == K.CON:
            if t[1] > 1:
                raise ValueError('no finite value: %r' % (t,))
            v = complex(math.pi if t[1] == 0 else math.e)
        elif op == K.ADD:
            v = go(t[1])
            for j in range(2, len(t), 2):
                v += go(t[j + 1]) * go(t[j])
        elif op == K.MUL:
            v = go(t[1])
            for j in range(2, len(t), 2):
                b = go(t[j])
                x = K.N[t[j + 1]]
                if x[0] == K.NUM and x[2] == 0:
                    v *= rpow(b, x[1], x[3])
                else:
                    w = go(t[j + 1])
                    if b == 0:
                        raise ZeroDivisionError('0^w')
                    v *= b ** w
        elif op >= K.FN0:
            v = FNS[op](go(t[1]))
        else:
            raise ValueError('cannot evaluate %r' % (t,))
        v = cre(v)
        memo[i] = v
        return v
    return go(e)


def close(a, b, tol=1e-8):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


class Skip(Exception):
    """A tree value that depends on a branch convention the constructors need not keep."""


class TreeEval(object):
    """The value of a gen.py tree, with the conventions of ev(). ``nonreal`` is set when some
    subexpression is not real (DESIGN 8.3: such points are not compared for symbolic trees).
    Skip is raised for values that depend on branch conventions the design leaves open: inverse
    trig off its real domain, and fractional powers of a negative non-rational constant
    (docs/notes/T1.1.md, known gaps)."""

    def __init__(self, env, numonly):
        self.env = env
        self.numonly = numonly
        self.nonreal = False

    def go(self, t):
        v = cre(self._go(t))
        if v.imag:
            self.nonreal = True
        return v

    def _go(self, t):
        k = t[0]
        if k == 'num':
            return complex(t[1]) / t[2]
        if k == 'flt':
            return complex(float(t[1]))
        if k == 'sym':
            return complex(self.env[t[1]])
        if k == 'con':
            return {'pi': complex(math.pi), 'e': complex(math.e), 'i': 1j}[t[1]]
        if k == 'add':
            v = 0j
            for c in t[1]:
                v += self.go(c)
            return v
        if k == 'mul':
            v = 1 + 0j
            for c in t[1]:
                v *= self.go(c)
            return v
        if k == 'neg':
            return -self.go(t[1])
        if k == 'sub':
            return self.go(t[1]) - self.go(t[2])
        if k == 'div':
            return self.go(t[1]) / self.go(t[2])
        if k == 'pow':
            b = self.go(t[1])
            p, d = t[2][1], t[2][2]
            if self.numonly and d > 1 and t[1][0] != 'num' and b.imag == 0 and b.real < 0:
                raise Skip('fractional power of a negative constant')
            return rpow(b, p, d)
        if k == 'fn':
            a = self.go(t[2])
            f = t[1]
            if f in ('asin', 'acos') and (a.imag or abs(a.real) > 1):
                raise Skip('inverse trig off its domain')
            if f == 'atan' and a.imag:
                raise Skip('atan of a non-real')
            if f in ('sin', 'cos', 'tan', 'sec', 'csc', 'cot') and abs(a) > 1e3:
                raise Skip('no float precision left in a huge trig argument')
            if f == 'sqrt':
                return rpow(a, 1, 2)
            if f == 'exp':
                return cmath.exp(a)
            if f == 'log':
                return cmath.log(a) / math.log(10)
            if f == 'abs':
                return complex(abs(a))
            return FNS[getattr(K, gen.FNOPS[f])](a)
        raise ValueError(t)


def has_syms(t):
    if t[0] == 'sym':
        return True
    if t[0] in ('add', 'mul'):
        return any(has_syms(c) for c in t[1])
    return any(has_syms(c) for c in t[1:] if isinstance(c, tuple))


# -- fixtures ------------------------------------------------------------------------------------

@pytest.fixture
def arena():
    """The debug arena of DESIGN 20.4: released ids are never reused; NMAX is raised."""
    K.reset()
    n = len(K.N)
    extra = NMAXDBG - n
    for a in (K.N, K.H, K.NX, K.V):
        a.extend([None if a is K.N else 0] * extra)
    old = K.NMAX
    K.NMAX = NMAXDBG
    K.DEBUG_ARENA = True
    yield
    K.reset()
    K.DEBUG_ARENA = False
    for a in (K.N, K.H, K.NX, K.V):
        del a[n:]
    K.NMAX = old


# -- the table -----------------------------------------------------------------------------------

API = ('NUM FLT SYM CON WILD COMP ADD MUL CALL LST EQ NE LT LE BIGO DNE DIVG HOLD FN0 SIN COS TAN '
       'SEC CSC COT ASIN ACOS ATAN SINH COSH TANH LN ABS SIGN FLOOR CEIL FACT ZERO ONE MONE TWO '
       'HALF I PI E OO UNDEF TEN LN10 TRUE FALSE BASE N H V NN NMAX mk num flt sym add_ mul_ fn_ '
       'rel_ neg_ absn negfirst nadd nmul ninv npowi nneg nsign ncmp free_of keep release reset '
       'CasError CasSoft Undefined Cancel CasMemory ESC MEMFREE').split()


def test_frozen_api_names_exist():
    missing = [n for n in API if not hasattr(K, n)]
    assert missing == []
    assert issubclass(K.Undefined, K.CasSoft) and issubclass(K.CasSoft, Exception)
    assert issubclass(K.Cancel, BaseException) and not issubclass(K.Cancel, Exception)
    assert issubclass(K.CasMemory, BaseException) and not issubclass(K.CasMemory, Exception)


def test_preallocated_ids_and_literal_tables():
    want = [(K.NUM, 0, 0, 1), (K.NUM, 1, 0, 1), (K.NUM, -1, 0, 1), (K.NUM, 2, 0, 1),
            (K.NUM, 1, 0, 2), (K.NUM, 0, 1, 1), (K.CON, 0), (K.CON, 1), (K.CON, 2), (K.CON, 3),
            (K.NUM, 10, 0, 1), (K.LN, 11), (K.CON, 4), (K.CON, 5)]
    assert K.N[1:15] == want and K.BASE == 15 and K.NN == K.BASE
    names = 'ZERO ONE MONE TWO HALF I PI E OO UNDEF TEN LN10 TRUE FALSE'.split()
    assert [getattr(K, n) for n in names] == list(range(1, 15))
    for i in range(1, 15):                  # the literal H/NX/B agree with mk's own hashing
        assert K.H[i] == invariants.ref_hash(K.N[i], K.H)
        assert K.mk(K.N[i]) == i
    assert len(K.N) == len(K.H) == len(K.NX) == len(K.V) == K.NMAX == 768
    assert invariants.scan(K) == []
    assert K.mk((K.NUM, 7, 0, 1)) == K.BASE


def test_mk_interns_and_hashes_per_section_5_7():
    x = K.mk((K.SYM, 'x'))
    assert K.mk((K.SYM, 'x')) == x and K.NN == K.BASE + 1
    h = 5381
    for ch in 'x':
        h = ((h << 5) ^ (h >> 20) ^ ord(ch)) & 0x1FFFFFF
    assert K.H[x] == h == 0x2a0d8 + 0                       # the 5.6 dump: H=002a0d8
    f = K.mk((K.FLT, 0.25, -1.5))
    assert K.H[f] == invariants.ref_hash(K.N[f], K.H)
    s = K.mk((K.SIN, x))
    assert K.H[s] == ((((K.SIN << 5) ^ (K.SIN >> 20) ^ K.H[x]) & 0x1FFFFFF))
    assert K.V[s] == K.V[x] == 1
    big = K.mk((K.NUM, 10 ** 40 + 7, -3, 10 ** 30))
    assert K.H[big] < (1 << 25)


def test_symbol_masks_and_overflow_bit():
    ids = [K.sym('s%d' % j) for j in range(31)]
    assert [K.V[i] for i in ids[:29]] == [1 << j for j in range(29)]
    assert K.V[ids[29]] == K.V[ids[30]] == K.OVF
    assert K.SYMN[:2] == ['s0', 's1'] and K.SYMI['s30'] == 30
    e = sm(ids[0], prod(ids[29], ids[3]))
    assert K.V[e] == 1 | 8 | K.OVF
    assert not K.free_of(e, ids[29]) and K.free_of(e, ids[30])
    assert not K.free_of(e, ids[3]) and K.free_of(e, ids[4])
    K.reset()
    assert K.SYMN == [] and K.SYMI == {} and K.NN == K.BASE


def test_free_of_masks_constants_and_subterms():
    x, y = K.sym('x'), K.sym('y')
    e = sm(K.fn_(K.SIN, x), prod(K.PI, y))
    assert not K.free_of(e, x) and not K.free_of(e, y) and K.free_of(e, K.sym('z'))
    assert not K.free_of(e, K.PI) and K.free_of(e, K.E)
    assert not K.free_of(e, K.fn_(K.SIN, x)) and K.free_of(e, K.fn_(K.COS, x))
    assert not K.free_of(e, prod(K.PI, y)) and K.free_of(x, e)


def test_table_cap_raises_expression_too_complex():
    with pytest.raises(K.CasError) as ei:
        for j in range(K.NMAX):
            K.num(j + 100)
    assert ei.value.args[0] == 'expression too complex'
    assert K.NN == K.NMAX


def test_low_memory_collects_then_raises_casmemory(monkeypatch):
    calls = []
    monkeypatch.setattr(K, 'MEMFREE', lambda: calls.append(1) or 0)
    with pytest.raises(K.CasMemory):
        for j in range(400):
            K.num(j + 100)
    assert K.NN == 256 and len(calls) == 2          # checked every 256 ids, after gc.collect


def test_reset_truncates_and_clears_caches():
    K.sym('x')
    K.RULECACHE['r'] = {}
    K.TCACHE['t'] = 1
    K.ifac(360)
    K.reset()
    assert K.NN == K.BASE and K.N[K.BASE] is None and not K.RULECACHE and not K.TCACHE
    assert not K.FCACHE and invariants.scan(K) == []


def test_sentinels_and_released_ids_are_rejected():
    dne = K.mk((K.DNE, K.ONE, K.MONE))
    x = K.sym('x')
    for bad in (K.TRUE, K.FALSE, dne, K.mk((K.HOLD, K.mk((K.MUL, K.TWO, K.TEN, K.TWO))))):
        with pytest.raises(K.CasError) as ei:
            K.add_([x, bad])
        assert ei.value.args[0] == 'invalid use of a result'
        for f in (lambda: K.mul_(K.ONE, [(bad, K.ONE)]), lambda: K.mul_(K.ONE, [(x, bad)]),
                  lambda: K.fn_(K.SIN, bad), lambda: K.neg_(bad), lambda: K.absn(bad),
                  lambda: K.rel_(K.EQ, bad, x)):
            with pytest.raises(K.CasError):
                f()
    m = K.NN
    y = K.sym('y')
    K.release(m)
    with pytest.raises(AssertionError):
        K.add_([y])


# -- canonical order, tiefix ---------------------------------------------------------------------

def _symhash(s):
    h = 5381
    for ch in s:
        h = ((h << 5) ^ (h >> 20) ^ ord(ch)) & 0x1FFFFFF
    return h


def _colliding_names():
    names = ['eaaaa', 'adlo']                   # found by brute force: equal 25-bit SYM hashes
    assert _symhash(names[0]) == _symhash(names[1])
    return names


def test_tiefix_orders_equal_hashes_by_structure():
    names = _colliding_names()
    orders = []
    for perm in ((0, 1), (1, 0)):
        K.reset()
        syms = [K.sym(names[j]) for j in perm]           # creation order changes the ids
        e = sm(*[K.fn_(K.SIN, s) for s in syms] + syms)
        t = K.N[e]
        orders.append([struct(c) for c in t[2::2]])
        assert len({K.H[c] for c in t[2::2] if K.N[c][0] == K.SYM}) == 1
    assert orders[0] == orders[1]


@pytest.mark.parametrize('seed', range(12))
def test_canonicity_permutations_and_regroupings(seed):
    g = gen.Gen(seed)
    n = 0
    for _ in range(40):
        t = g.tree(3)
        try:
            e = gen.build(t, K)
        except K.Undefined:
            K.reset()
            continue
        for v in g.variants(t, 4):
            assert gen.build(v, K) == e, (gen.text(t), gen.text(v))
        n += 1
        K.reset()
    assert n > 25


@pytest.mark.parametrize('seed', range(6))
def test_rebuilding_a_node_from_its_children_gives_the_same_id(seed):
    g = gen.Gen(100 + seed)
    for _ in range(25):
        try:
            gen.build(g.tree(3), K)
        except K.Undefined:
            pass
    top = K.NN
    for i in range(K.BASE, top):
        t = K.N[i]
        op = t[0]
        if op == K.ADD:
            r = K.add_([t[1]] + [K.mul_(t[j + 1], [(t[j], K.ONE)]) for j in range(2, len(t), 2)])
        elif op == K.MUL:
            r = K.mul_(t[1], [(t[j], t[j + 1]) for j in range(2, len(t), 2)])
        elif op == K.ABS:
            r = K.absn(t[1])
        elif op >= K.FN0:
            r = K.fn_(op, t[1])
        else:
            continue
        assert r == i, (i, t, r, K.N[r])


def test_worked_example_5_6_and_its_region():
    x = K.sym('x')
    a = sm(pw(x, 2), div(prod(q(3), x), q(2)), K.neg_(K.fn_(K.SIN, x)))
    b = sm(K.neg_(K.fn_(K.SIN, x)), prod(q(3, 2), x), prod(x, x))
    assert a == b
    t = K.N[a]
    assert t[0] == K.ADD and t[1] == K.ZERO and len(t) == 8
    pairs = sorted((struct(t[j]), K.N[t[j + 1]]) for j in range(2, 8, 2))
    assert pairs == sorted([(struct(x), (K.NUM, 3, 0, 2)), (struct(K.fn_(K.SIN, x)), K.N[K.MONE]),
                            (struct(pw(x, 2)), K.N[K.ONE])])
    s = struct(a)
    r = K.keep(K.BASE, a)
    assert K.NN - K.BASE == 5 and r == K.BASE + 4 and struct(r) == s
    assert invariants.scan(K) == []
    assert sm(K.neg_(K.fn_(K.SIN, x)), prod(q(3, 2), x), prod(x, x)) == r


# -- regions -------------------------------------------------------------------------------------

def _random_region_run(rng, g):
    base_trees = [g.tree(2) for _ in range(3)]
    old = []
    for t in base_trees:
        try:
            old.append(gen.build(t, K))
        except K.Undefined:
            pass
    olds = [struct(i) for i in old]
    m = K.NN
    trees = []
    ids = []
    for _ in range(rng.randint(1, 6)):
        t = g.tree(3)
        try:
            ids.append(gen.build(t, K))
            trees.append(t)
        except K.Undefined:
            pass
    keepn = rng.randint(0, len(ids))
    y = tuple(ids[:keepn]) if rng.random() < 0.7 else (ids[0] if ids else None)
    want = None if y is None else [struct(i) for i in (y if type(y) is tuple else (y,))]
    r = K.keep(m, y)
    assert [struct(i) for i in old] == olds              # below the mark: untouched
    if y is None:
        assert r is None
    else:
        rr = r if type(r) is tuple else (r,)
        assert [struct(i) for i in rr] == want
        kt = trees[:keepn] if type(y) is tuple else trees[:1]
        for t, i in zip(kt, rr):
            assert gen.build(t, K) == i                   # re-interning finds the survivor
    assert invariants.scan(K) == []


@pytest.mark.parametrize('seed', range(8))
def test_keep_and_release_random_regions(seed):
    rng = random.Random(seed)
    g = gen.Gen(200 + seed)
    for _ in range(12):
        _random_region_run(rng, g)
        if rng.random() < 0.3:
            m = rng.randint(K.BASE, K.NN)
            K.release(m)
            assert K.NN == m and invariants.scan(K) == []
        if K.NN > 600:
            K.reset()


@pytest.mark.parametrize('seed', range(4))
def test_keep_random_regions_under_the_debug_arena(seed, arena):
    rng = random.Random(seed)
    g = gen.Gen(300 + seed)
    for _ in range(12):
        _random_region_run(rng, g)


def test_debug_arena_catches_a_leaked_id(arena):
    x = K.sym('x')
    m = K.NN
    leaked = sm(x, q(1))
    kept = K.keep(m, prod(x, q(2)))
    assert K.N[leaked] == K.DEADT and kept >= m and K.NN > m + 1   # fresh ids, never reused
    with pytest.raises(AssertionError):
        K.add_([leaked, x])
    with pytest.raises(AssertionError):
        K.mul_(K.ONE, [(x, leaked)])
    with pytest.raises(AssertionError):
        K.mk((K.SIN, leaked))
    m2 = K.NN
    y = K.fn_(K.COS, x)
    K.release(m2)
    assert K.N[y] == K.DEADT and K.NN == m2 + 1
    with pytest.raises(AssertionError):
        K.fn_(K.SIN, y)


def test_keep_remaps_rulecache_ids():
    x = K.sym('x')
    m = K.NN
    junk = sm(x, q(5))
    w = K.mk((K.WILD, 0, 0))
    lhs = prod(K.fn_(K.SIN, w), x)
    K.RULECACHE['t'] = {K.MUL: ((lhs, 'L', ''),), 99: ((lhs, 'L', 'g'), (K.ONE, 'x', ''))}
    s = struct(lhs)
    r = K.keep(m, None)
    assert r is None
    rs = K.RULECACHE['t']
    assert struct(rs[K.MUL][0][0]) == s and rs[K.MUL][0][1:] == ('L', '')
    assert rs[99][0][0] == rs[K.MUL][0][0] and rs[99][1] == (K.ONE, 'x', '')
    assert K.NN == m + 3 and junk >= m                    # w, sin(w), lhs survive
    assert invariants.scan(K) == []
    K.reset()                                  # clears RULECACHE after the reset-time scan
    assert K.RULECACHE == {}


def test_keep_tuple_with_old_ids_and_none():
    x = K.sym('x')
    m = K.NN
    a = K.fn_(K.SIN, x)
    sm(a, q(3))
    r = K.keep(m, (x, a, None))
    assert r == (x, m, None) and K.NN == m + 1


# -- add_ and neg_ -------------------------------------------------------------------------------

def test_add_flattens_collects_distributes_and_collapses():
    x, y = K.sym('x'), K.sym('y')
    xp1 = sm(x, q(1))
    assert sm(prod(q(2), xp1), x) == sm(prod(q(3), x), q(2))        # 2(x+1)+x = 3x+2
    assert sm(x, K.neg_(x)) == K.ZERO
    assert sm(x, x) == prod(q(2), x)
    assert sm(x) == x and sm() == K.ZERO and sm(q(2), q(3)) == q(5)
    assert sm(sm(x, y), sm(y, K.neg_(x))) == prod(q(2), y)
    assert K.add_([x, y], (K.NUM, 3, 0, 1)) == sm(prod(q(3), x), prod(q(3), y))
    assert K.add_([x, q(1)], K.MONE) == K.neg_(xp1)
    t = K.N[sm(prod(q(2), x, y), prod(q(3), y, x))]
    assert t[0] == K.MUL and K.N[t[1]] == (K.NUM, 5, 0, 1)


def test_neg_matches_add_and_double_negation():
    x, y = K.sym('x'), K.sym('y')
    for e in (x, q(3, 4, 1), sm(x, q(-2)), prod(q(-3), x, y), K.fn_(K.SIN, x), sm(x, y, q(1)),
              K.flt(2.5), K.OO):
        n = K.neg_(e)
        assert K.neg_(n) == e
        assert n == K.add_([e], K.N[K.MONE]) or e == K.OO
    assert K.neg_(K.UNDEF) == K.UNDEF
    assert K.neg_(K.OO) == K.mk((K.MUL, K.MONE, K.OO, K.ONE))


def test_negfirst():
    x = K.sym('x')
    assert K.negfirst(q(-1)) and not K.negfirst(q(1)) and K.negfirst(q(0, 1, -1))
    assert K.negfirst(sub(q(1), x)) and not K.negfirst(sub(x, q(1)))
    assert K.negfirst(prod(q(-2), x)) and not K.negfirst(x) and not K.negfirst(K.PI)
    assert K.negfirst(K.flt(-0.5))


def test_add_with_infinity():
    x = K.sym('x')
    ninf = K.neg_(K.OO)
    assert sm(K.OO, q(1)) == K.OO and sm(K.OO, x) == K.OO and sm(ninf, q(5)) == ninf
    assert sm(K.OO, ninf) == K.UNDEF and sm(K.OO, K.OO) == K.OO
    assert sm(x, K.UNDEF) == K.UNDEF
    xo = prod(x, K.OO)
    e = sm(xo, K.OO)                                       # x*oo + oo is kept as a sum
    assert K.N[e][0] == K.ADD


def test_float_contagion_in_sums_and_products():
    x = K.sym('x')
    h = K.flt(0.5)
    assert sm(h, q(1, 2)) == K.flt(1.0)
    e = sm(prod(h, x), div(x, q(2)))
    assert K.N[e] == (K.MUL, K.flt(1.0), x, K.ONE)
    assert prod(h, q(3)) == K.flt(1.5)
    assert pw(K.flt(4.0), 1, 2) == K.flt(2.0)
    assert pw(K.flt(-8.0), 1, 3) == K.flt(-2.0)          # the real odd root
    assert pwe(q(2), K.flt(0.5)) == K.flt(math.sqrt(2))
    assert sm(K.flt(0.1), K.flt(-0.1)) == K.flt(0.0) and prod(K.flt(0.0), x) == K.ZERO


# -- mul_ rules (8.2) ----------------------------------------------------------------------------

def test_mul_rules_1_2_folding_and_zero_powers():
    x = K.sym('x')
    assert pw(x, 0) == K.ONE and pw(q(0), 0) == K.ONE                # 0^0 = 1
    assert pw(q(2), 10) == q(1024) and pw(q(2, 3), -2) == q(9, 4)
    with pytest.raises(K.Undefined):
        pw(q(0), -1)
    with pytest.raises(K.Undefined):
        div(x, sub(x, x))
    assert prod(q(0), x) == K.ZERO and div(q(0), x) == K.ZERO
    assert div(x, x) == K.ONE


def test_mul_rule_5_distributes_integer_powers_of_products():
    x, y = K.sym('x'), K.sym('y')
    assert pw(prod(x, y), 2) == prod(pw(x, 2), pw(y, 2))
    assert pw(prod(q(2), x), 3) == prod(q(8), pw(x, 3))
    assert pw(sqrt(x), 2) == x and pw(pw(x, 1, 3), 3) == x
    assert pw(pwe(x, y), 2) == pwe(x, prod(q(2), y))
    assert pw(div(q(1), prod(x, y)), -1) == prod(x, y)


def test_mul_rule_6_pulls_out_a_positive_coefficient():
    x = K.sym('x')
    assert sqrt(prod(q(4), x)) == prod(q(2), sqrt(x))
    assert sqrt(div(x, q(4))) == div(sqrt(x), q(2))
    assert K.N[sqrt(prod(q(-4), x))][2] == prod(q(-4), x)      # a negative one is kept
    y = K.sym('y')
    assert pwe(prod(q(2), x), y) == prod(pwe(q(2), y), pwe(x, y))


def test_mul_rule_7_even_powers_under_roots():
    x = K.sym('x')
    ax = K.fn_(K.ABS, x)
    assert sqrt(pw(x, 2)) == ax
    assert sqrt(pw(x, 4)) == pw(x, 2)
    assert pw(pw(x, 2), 3, 2) == pw(ax, 3)
    assert pw(pw(x, 6), 1, 3) == pw(x, 2)
    assert pw(pw(x, 4), 1, 4) == ax
    xp1 = sm(x, q(1))
    assert sqrt(pw(K.neg_(xp1), 2)) == sqrt(pw(xp1, 2)) == K.fn_(K.ABS, xp1)
    assert K.N[pw(pw(x, 2), 1, 3)][2] == pw(x, 2)                 # (x^2)^(1/3) is kept


def test_mul_rules_8_9_exp_ln_and_abs_powers():
    x = K.sym('x')
    lx = K.fn_(K.LN, x)
    assert pwe(K.E, lx) == x
    assert pwe(K.E, prod(q(2), lx)) == pw(x, 2)
    assert pwe(K.E, prod(q(-1), lx)) == pw(x, -1)
    assert K.N[pwe(K.E, div(lx, q(2)))][2] == K.E                 # e^(ln(x)/2) is kept
    ax = K.fn_(K.ABS, x)
    assert pw(ax, 2) == pw(x, 2) and pw(ax, -4) == pw(x, -4)
    assert K.N[pw(ax, 3)][2] == ax
    assert prod(pwe(K.E, x), pwe(K.E, prod(q(2), x))) == pwe(K.E, prod(q(3), x))


def test_mul_rule_10_merges_and_rechecks():
    x, y = K.sym('x'), K.sym('y')
    assert prod(sqrt(x), pw(x, 1, 3)) == pw(x, 5, 6)
    assert prod(sqrt(x), sqrt(x)) == x
    assert prod(sqrt(prod(x, y)), sqrt(prod(x, y))) == prod(x, y)
    assert prod(K.fn_(K.ABS, x), K.fn_(K.ABS, x)) == pw(x, 2)
    assert prod(pwe(q(2), x), pwe(q(2), y)) == pwe(q(2), sm(x, y))
    assert prod(pwe(q(2), x), sqrt(q(2))) == pwe(q(2), sm(x, q(1, 2)))
    assert prod(pw(x, 2), pw(x, -2)) == K.ONE


def test_mul_rule_13_assembly_and_sum_signs():
    x, y = K.sym('x'), K.sym('y')
    xp1 = sm(x, q(1))
    assert prod(q(-1), xp1) == sm(K.neg_(x), q(-1))                # -(x+1) = -x-1
    t = K.N[prod(q(2), xp1)]
    assert t == (K.MUL, K.TWO, xp1, K.ONE)                        # 2(x+1) is kept
    omx = sub(q(1), x)
    assert prod(q(2), omx) == prod(q(-2), sub(x, q(1)))           # one sign per sum (6.4)
    assert prod(omx, sub(x, q(1))) == K.neg_(pw(sub(x, q(1)), 2))
    assert prod(prod(q(-1), sub(y, q(1))), prod(q(2), x)) == prod(q(-1), sub(y, q(1)), q(2), x)
    assert prod(q(1), x) == x and prod() == K.ONE


def test_mul_with_infinity():
    x = K.sym('x')
    oo, ninf = K.OO, K.neg_(K.OO)
    assert prod(q(3), oo) == oo and prod(q(-2), oo) == ninf and prod(ninf, ninf) == oo
    assert prod(q(0), oo) == K.UNDEF and pw(oo, -1) == K.ZERO and prod(oo, pw(oo, -1)) == K.UNDEF
    assert pw(oo, 2) == oo and pw(oo, 1, 2) == oo
    assert pwe(q(2), oo) == oo and pwe(q(1, 2), oo) == K.ZERO and pwe(q(2), ninf) == K.ZERO
    assert pwe(q(1, 2), ninf) == oo and pwe(q(0), ninf) == oo and pwe(q(0), oo) == K.ZERO
    assert pwe(q(1), oo) == K.UNDEF and pwe(q(-1), oo) == K.UNDEF and pwe(q(-3), oo) == K.UNDEF
    assert pwe(q(-1, 2), oo) == K.ZERO and pwe(q(-1, 2), ninf) == K.UNDEF
    assert pwe(q(-3), ninf) == K.ZERO
    assert pwe(K.E, oo) == oo and pwe(K.E, ninf) == K.ZERO and pwe(K.PI, oo) == oo
    assert pwe(K.I, oo) == K.UNDEF
    assert prod(x, K.UNDEF) == K.UNDEF and pw(K.UNDEF, 2) == K.UNDEF
    t = K.N[prod(q(-5), x, oo)]
    assert t[1] == K.MONE and sorted(t[2::2]) == sorted([x, oo]) and t[3::2] == (K.ONE, K.ONE)


# -- rel_ ----------------------------------------------------------------------------------------

def test_relations_fold_numeric_differences():
    x = K.sym('x')
    assert K.rel_(K.LT, q(2), q(3)) == K.TRUE and K.rel_(K.LT, q(3), q(2)) == K.FALSE
    assert K.rel_(K.EQ, sub(x, x), q(1)) == K.FALSE
    assert K.rel_(K.EQ, sm(x, q(1)), sm(x, q(1))) == K.TRUE
    assert K.rel_(K.NE, q(1), q(2)) == K.TRUE and K.rel_(K.LE, q(2), q(2)) == K.TRUE
    assert K.rel_(K.GT, q(3), q(2)) == K.TRUE and K.rel_(K.GE, q(1), q(2)) == K.FALSE
    assert K.rel_(K.EQ, K.I, K.I) == K.TRUE and K.rel_(K.NE, K.I, q(1)) == K.TRUE
    with pytest.raises(K.Undefined):
        K.rel_(K.LT, K.I, q(1))
    assert K.N[K.rel_(K.GT, x, q(3))] == (K.LT, q(3), x)
    assert K.N[K.rel_(K.GE, x, q(3))] == (K.LE, q(3), x)
    assert K.N[K.rel_(K.EQ, x, q(3))] == (K.EQ, x, q(3))
    assert K.rel_(K.LT, q(5), K.OO) == K.TRUE and K.rel_(K.EQ, K.OO, q(1)) == K.FALSE
    assert K.rel_(K.LT, K.OO, K.OO) == K.UNDEF
    assert K.rel_(K.LT, K.flt(0.5), q(1)) == K.TRUE


# -- soundness against tree values (the oracle-style property) -----------------------------------

POINTS = ({'x': 0.73, 'y': 1.61}, {'x': -1.37, 'y': 0.42}, {'x': 2.21, 'y': -0.88},
          {'x': -0.55, 'y': -2.03})


@pytest.mark.parametrize('seed', range(16))
def test_constructors_agree_with_tree_values(seed):
    g = gen.Gen(1000 + seed, consts=('pi', 'e', 'i'))
    compared = 0
    for _ in range(30):
        t = g.tree(3)
        try:
            e = gen.build(t, K)
        except K.Undefined:
            K.reset()
            continue
        numonly = not has_syms(t)
        for env in ({},) if numonly else POINTS:
            te = TreeEval(env, numonly)
            try:
                want = te.go(t)
            except (Skip, ZeroDivisionError, ValueError, OverflowError):
                continue
            if (te.nonreal and not numonly) or abs(want) > 1e8:
                continue
            try:
                got = ev(e, env)
            except (ZeroDivisionError, ValueError, OverflowError):
                if abs(want) > 1e8:
                    continue
                raise
            assert close(got, want, 1e-7), (gen.text(t), env, got, want)
            compared += 1
        K.reset()
    assert compared > 40


# -- depth: nesting invariance (20.7) ------------------------------------------------------------

def test_constructor_depth_does_not_grow_with_nesting(evodepth):
    def build(n):
        K.reset()
        x = K.sym('x')
        e = x
        for _ in range(n):
            e = K.fn_(K.SIN, sm(pw(e, 2), q(1)))
        return e
    depths = []
    for n in (1, 8, 32):
        _, d, _ = evodepth.measure(build, n)
        depths.append(d)
    assert depths[0] == depths[1] == depths[2] <= 7


# -- golden node dumps (20.6) --------------------------------------------------------------------

def _golden_cases():
    x, y = K.sym, K.sym
    return (
        ('x^2+3x/2-sin(x)', lambda: sm(pw(x('x'), 2), div(prod(q(3), x('x')), q(2)),
                                       K.neg_(K.fn_(K.SIN, x('x'))))),
        ('sqrt(72)', lambda: sqrt(q(72))),
        ('sqrt(8/27)', lambda: sqrt(q(8, 27))),
        ('(-8)^(1/3)', lambda: pw(q(-8), 1, 3)),
        ('sqrt(-4)', lambda: sqrt(q(-4))),
        ('(-4)^(1/4)', lambda: pw(q(-4), 1, 4)),
        ('2^(1/2)*3^(1/3)*x^(2/3)*y', lambda: prod(sqrt(q(2)), pw(q(3), 1, 3), pw(x('x'), 2, 3),
                                                   y('y'))),
        ('cos(5pi/12)', lambda: K.fn_(K.COS, pimul(5, 12))),
        ('tan(pi/12)', lambda: K.fn_(K.TAN, pimul(1, 12))),
        ('cos(pi/5)', lambda: K.fn_(K.COS, pimul(1, 5))),
        ('sin(3pi/8)', lambda: K.fn_(K.SIN, pimul(3, 8))),
        ('atan(sqrt(3))', lambda: K.fn_(K.ATAN, sqrt(q(3)))),
        ('ln(1+i)', lambda: K.fn_(K.LN, q(1, 1, 1))),
        ('ln(-8/3)', lambda: K.fn_(K.LN, q(-8, 3))),
        ('abs(-2x-2)', lambda: K.fn_(K.ABS, sm(prod(q(-2), x('x')), q(-2)))),
        ('sin(1-x)', lambda: K.fn_(K.SIN, sub(q(1), x('x')))),
        ('e^(i*pi/3)', lambda: pwe(K.E, prod(q(0, 3, 1), K.PI))),
        ('-oo', lambda: K.neg_(K.OO)),
        ('0.5*x+1.25', lambda: sm(prod(K.flt(0.5), x('x')), K.flt(1.25))),
        ('2(1-x)', lambda: prod(q(2), sub(q(1), x('x')))),
        ('x>3', lambda: K.rel_(K.GT, x('x'), q(3))),
    )


def _golden_text():
    out = ['# T1.1 node-table dumps (DESIGN 20.6): id H V tuple, ids from BASE; regenerate with',
           '# pytest tests/test_node.py --update-golden and review the diff', '']
    for name, f in _golden_cases():
        K.reset()
        r = f()
        out.append('== %s -> %d' % (name, r))
        out.extend(invariants.dump(K, K.BASE))
        out.append('')
    K.reset()
    return '\n'.join(out)


def test_golden_node_dumps(update_golden):
    text = _golden_text()
    if update_golden or not os.path.exists(GOLDEN):
        with open(GOLDEN, 'w', encoding='ascii', newline='\n') as fh:
            fh.write(text)
        if update_golden:
            return
    with open(GOLDEN, encoding='ascii') as fh:
        want = fh.read()
    assert text == want
