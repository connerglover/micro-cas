"""T1.7: the round-trip invariant (DESIGN 12.5, MUST).

For every corpus result and every fuzz case, in both angle modes, re-parsing text(e) through
the answer path of section 7.1 (stages 3-5 and 7, then g_eval in inert mode with the answer's
angle mode) gives e again, in the same table. Floats compare within 1e-14 relative.

The documented exceptions (docs/notes/T1.7.md) are display rewrites that FlowCE makes and the
constructors do not; each re-parses to a precise normal form, computed here independently:

- HOLD re-parses to its value (DESIGN 12.5);
- a one-element top-level solution list prints as its element (FlowCE's `x=2`);
- sum_content (DESIGN 12.3, fmt 1.3): the rational content of every factor S^1 of a product,
  S a sum, moves to the product's coefficient (`cnorm` below; `y*(2x+2)` prints `2*y*(x+1)`);
- the long polynomial over an integer (fmt 1.4): a top-level `(sum)/q` whose text is over
  `PR.LONGPOLY` characters prints, and re-parses, as its expansion.

So text(e) re-parses to expected(e) exactly in radian mode. In degree mode the content is that
of the degree-mode display (`asin(x)+90`, not of its radian node), so there the test compares
cnorm of both sides. In every mode the text is a fixed point: text(reparse(text(e))) == text(e)
(except HOLD).
"""
import math
from fractions import Fraction

import pytest

import alg as A
import gen
import parse as P
import printer as PR

from test_print import drive, ev, golden_cases

K = P.K


def seeds(fast, total):
    """Seeds 0..total-1; those from fast on are marked slow (the fast loop keeps a subset)."""
    out = []
    for s in range(total):
        out.append(s if s < fast else pytest.param(s, marks=pytest.mark.slow))
    return out


@pytest.fixture(autouse=True)
def nosess(monkeypatch):
    monkeypatch.setattr(P, 'SESS', None)


def reparse(s, deg):
    """The answer path: stages 3-5 and 7 (no context expansion), g_eval inert."""
    return drive(P.g_eval(P.rpn(P.tokens(s, 0)), [deg, None, 0, 1]))


def close(a, b):
    return a == b or abs(a - b) <= 1e-14 * max(abs(a), abs(b))


def same(a, b):
    """Structural equality of two nodes, floats within 1e-14 relative."""
    st = [(a, b)]
    while st:
        x, y = st.pop()
        if x == y:
            continue
        tx = K.N[x]
        ty = K.N[y]
        if tx[0] != ty[0] or len(tx) != len(ty):
            return False
        if tx[0] == K.FLT:
            if not (close(tx[1], ty[1]) and close(tx[2], ty[2])):
                return False
        elif tx[0] < K.COMP:
            if tx != ty:
                return False
        else:
            for j in range(1, len(tx)):
                st.append((tx[j], ty[j]))
    return True


def content(b):
    """The rational content of the sum b (FlowCE sum_content) as a Fraction; None when it is 1
    or when a coefficient is not a real rational."""
    t = K.N[b]
    g = 0
    l = 1
    for j in range(1, len(t), 2):
        w = K.N[t[j]]
        if w[0] != K.NUM or w[2]:
            return None
        g = math.gcd(g, abs(w[1]))
        l = l * w[3] // math.gcd(l, w[3])
    c = Fraction(g, l)
    return None if c == 1 else c


def cnorm(e):
    """e with the content of every factor S^1 (S a sum) of every product moved into that
    product's coefficient, bottom-up through the constructors. (A HOLD inside e folds to its
    value, as its text re-parses.)"""
    new = {}
    for m in A.postorder(e):
        t = K.N[m]
        if t[0] == K.MUL:
            k = K.N[t[1]]
            ps = []
            for j in range(2, len(t), 2):
                b = new.get(t[j], t[j])
                x = new.get(t[j + 1], t[j + 1])
                if x == K.ONE and K.N[b][0] == K.ADD:
                    c = content(b)
                    if c is not None:
                        b = K.add_([b], (K.NUM, c.denominator, 0, c.numerator))
                        k = K.nmul(k, (K.NUM, c.numerator, 0, c.denominator))
                ps.append((b, x))
            r = K.mul_(k, ps)
        else:
            r = A.rebuild(m, new)
        if r != m:
            new[m] = r
    return new.get(e, e)


def longpoly(e, deg):
    """The expansion that a long top-level (sum)/q prints as (fmt 1.4), or None."""
    c = cnorm(e)
    t = K.N[c]
    if t[0] != K.MUL or len(t) != 4 or t[3] != K.ONE or K.N[t[2]][0] != K.ADD:
        return None
    q = K.N[t[1]]
    u = K.N[t[2]]
    if q[0] != K.NUM or q[2] or q[3] == 1:
        return None
    if any(K.N[u[j]][0] == K.BIGO for j in range(2, len(u), 2)):
        return None
    keep = PR.LONGPOLY
    PR.LONGPOLY = 10 ** 9
    try:
        s = PR.text(e, [deg, None, 0, 0])
    finally:
        PR.LONGPOLY = keep
    return K.add_([t[2]], q) if len(s) > keep else None


def expected(e, deg=0):
    """What the text of e re-parses to (radian mode): the documented normal form."""
    t = K.N[e]
    if t[0] == K.HOLD:
        m = K.N[t[1]]
        pairs = []
        for j in range(2, len(m), 2):
            pairs.append((m[j], m[j + 1]))
        return K.mul_(m[1], pairs)
    if t[0] == K.LST and len(t) == 2 and K.EQ <= K.N[t[1]][0] <= K.LE:
        return cnorm(t[1])
    x = longpoly(e, deg)
    return cnorm(e) if x is None else x


def roundtrip(e, deg):
    ctx = [deg, None, 0, 0]
    s = PR.text(e, ctx)
    assert s is not None
    e2 = reparse(s, deg)
    want = expected(e, deg)
    if deg:                                  # the content of the degree-mode display
        got = cnorm(e2)
        want = cnorm(want)
    else:
        got = e2
    assert same(got, want), 'deg=%d: %r re-parses to %r, not %r' % (
        deg, s, PR.text(e2, ctx), PR.text(want, ctx))
    if K.N[e][0] != K.HOLD:
        assert PR.text(e2, ctx) == s, 'deg=%d: %r is not a fixed point' % (deg, s)
    return s


# -- the golden corpus ------------------------------------------------------------------------

def test_roundtrip_golden_corpus():
    n = 0
    for no, mode, s, want in golden_cases():
        deg = 1 if mode == 'D' else 0
        try:
            e, ctx = ev(s, deg)
        except K.CasError:
            continue
        roundtrip(e, deg)
        n += 1
        K.reset()
    assert n >= 200


def test_roundtrip_golden_corpus_other_mode():
    """The radian results re-parse in degree mode too (and back), as Ans does after F3."""
    for no, mode, s, want in golden_cases():
        deg = 1 if mode == 'D' else 0
        try:
            e, ctx = ev(s, deg)
        except K.CasError:
            continue
        roundtrip(e, 1 - deg)
        K.reset()


# -- random trees (20.7), both angle modes ------------------------------------------------------

@pytest.mark.parametrize('seed', seeds(4, 16))
def test_roundtrip_random_trees(seed):
    g = gen.Gen(seed, syms=('x', 'y'), consts=('pi', 'e', 'i'))
    done = 0
    for _ in range(80):
        t = g.tree(4)
        try:
            e = gen.build(t, K)
        except (K.CasSoft, K.CasError):
            continue
        roundtrip(e, seed & 1)
        roundtrip(e, 1 - (seed & 1))
        done += 1
        K.reset()
    assert done > 40


@pytest.mark.parametrize('seed', seeds(2, 8))
def test_roundtrip_random_trees_with_floats(seed):
    g = gen.Gen(100 + seed, syms=('x', 'theta'), floats=True, consts=('pi', 'e', 'i'))
    for _ in range(80):
        t = g.tree(3)
        try:
            e = gen.build(t, K)
        except (K.CasSoft, K.CasError):
            continue
        roundtrip(e, seed & 1)
        K.reset()


@pytest.mark.parametrize('seed', seeds(2, 8))
def test_roundtrip_polynomial_products(seed):
    """Products of random polynomials (the factor and flip paths) and their powers."""
    g = gen.Gen(200 + seed)
    for _ in range(40):
        ps = []
        for _ in range(g.r.randint(1, 3)):
            ps.append(('pow', g.poly('x', g.r.randint(1, 3), 5),
                       gen.num(g.r.randint(-2, 3))))
        ps.append(('fn', g.r.choice(('sin', 'cos', 'ln', 'exp')), ('sym', 'x')))
        t = ('mul', tuple(ps))
        if g.r.random() < 0.5:
            t = ('add', (t, g.poly('x', 2, 4)))
        try:
            e = gen.build(t, K)
        except (K.CasSoft, K.CasError):
            continue
        roundtrip(e, 0)
        roundtrip(e, 1)
        K.reset()


def scaled(g, var='x'):
    """A sum with rational content: a random polynomial, each term times one rational."""
    while True:
        p = g.poly(var, g.r.randint(1, 3), 4)
        if p[0] == 'add':
            break
    c = gen.num(g.r.choice((1, -1, 2, -3, 6)), g.r.choice((1, 2, 5, 13)))
    return ('add', tuple(('mul', (c, t)) for t in p[1]))


@pytest.mark.parametrize('seed', seeds(3, 10))
def test_roundtrip_sum_content(seed):
    """Products with contentful sum factors (sum_content), nested in sums, powers, function
    arguments, relations and lists, in both angle modes."""
    g = gen.Gen(400 + seed, syms=('x', 'y'))
    others = (('sym', 'y'), ('fn', 'sin', ('sym', 'x')), ('fn', 'exp', ('sym', 'x')),
              ('fn', 'asin', ('sym', 'x')), ('pow', ('sym', 'x'), gen.num(-1)),
              ('fn', 'ln', ('sym', 'x')), gen.num(3, 7))
    done = 0
    for _ in range(40):
        f = [scaled(g)]
        for _ in range(g.r.randint(0, 2)):
            f.append(g.r.choice(others + (scaled(g, 'y'),)))
        t = ('mul', tuple(f))
        k = g.r.random()
        if k < 0.25:
            t = ('add', (t, ('mul', (scaled(g), ('sym', 'y')))))
        elif k < 0.4:
            t = ('fn', g.r.choice(('sin', 'cos', 'exp')), t)
        elif k < 0.5:
            t = ('pow', t, gen.num(g.r.choice((2, -1, 3))))
        elif k < 0.6:
            t = ('add', (t, g.poly('x', 2, 3)))
        try:
            e = gen.build(t, K)
        except (K.CasSoft, K.CasError):
            continue
        if g.r.random() < 0.2:
            e = K.mk((K.LST, K.rel_(K.EQ, K.sym('x'), e), e))
        roundtrip(e, 0)
        roundtrip(e, 1)
        done += 1
        K.reset()
    assert done > 25


def test_roundtrip_sum_content_named():
    for s, want in (('y*(2x+2)', '2*y*(x+1)'), ('2(x/2+1/2)', 'x+1'), ('-2(x/2+1/2)', '-x-1'),
                    ('(x+2)(2x+4)', '2*(x+2)^2'), ('(x+1)/(2x+2)', '(x+1)/(2*x+2)'),
                    ('y*(2x+2)+1', '2*y*(x+1)+1'), ('z*(y*(2x+2)+2w)', '2*z*(w+y*(x+1))'),
                    ('e^(2x)*(2sin(3x)/13-3cos(3x)/13)', 'e^(2*x)*(2*sin(3*x)-3*cos(3*x))/13'),
                    ('[x=y*(2x+2)]', 'x=2*y*(x+1)'), ('sin(y*(4x-6))', 'sin(2*y*(2*x-3))')):
        e, ctx = ev(s)
        assert roundtrip(e, 0) == want, s
        K.reset()
    e, ctx = ev('y*(2asin(x)+180)', 1)
    assert roundtrip(e, 1) == '2*y*(asin(x)+90)'
    e, ctx = ev('y*(asin(x)+90)', 1)
    assert roundtrip(e, 1) == 'y*(asin(x)+90)'
    e2 = reparse('y*(asin(x)+90)', 1)
    assert e2 == e                             # no content in the degree-mode display


def test_roundtrip_long_polynomial():
    p = 'x^12+3x^11+5x^10+7x^9+9x^8+11x^7+13x^6+15x^5+17x^4+19x^3+21x^2+23x+25'
    for s, expanded in (('(%s)/182' % p, True), ('(2*(%s))/91' % p, True),
                        ('2(%s)' % p, False), ('(%s+O(x^13))/182' % p, False),
                        ('(x^3+x+1)/182', False)):
        e, ctx = ev(s)
        for deg in (0, 1):
            r = roundtrip(e, deg)
            assert ('(' not in r[:3]) == expanded, (s, r)
        K.reset()


def wrap(g, e):
    """A random answer shape around e: relations, lists, calls, O(), solutions."""
    x = K.sym('x')
    k = g.r.random()
    if k < 0.2:
        return K.mk((K.CALL, K.sym(g.r.choice(('integrate', 'limit', 'sum', 'f'))), e, x))
    if k < 0.35:
        return K.mk((K.LST, e, x))
    if k < 0.5:
        r = K.rel_(g.r.choice((K.EQ, K.NE, K.LT, K.LE, K.GT, K.GE)), e, x)
        return r
    if k < 0.6:
        return K.mk((K.LST, K.rel_(K.EQ, x, e), K.rel_(K.EQ, x, K.add_([e, K.ONE]))))
    if k < 0.7:
        return K.add_([e, K.mk((K.BIGO, K.mul_(K.ONE, [(x, num(g.r.randint(1, 6)))])))])
    if k < 0.8:
        return K.fn_(K.FACT, e)
    return e


def num(a):
    return K.num(a)


@pytest.mark.parametrize('seed', seeds(3, 12))
def test_roundtrip_answer_shapes(seed):
    g = gen.Gen(300 + seed, syms=('x', 'y'), consts=('pi', 'e', 'i'))
    for _ in range(60):
        t = g.tree(3)
        try:
            e = wrap(g, gen.build(t, K))
        except (K.CasSoft, K.CasError):
            continue
        if e in (K.TRUE, K.FALSE):
            continue
        roundtrip(e, seed & 1)
        K.reset()


# -- named cases (20.12) -------------------------------------------------------------------------

def test_roundtrip_solutions_and_series():
    x = K.sym('x')
    two = K.mk((K.LST, K.rel_(K.EQ, x, K.MONE), K.rel_(K.EQ, x, K.ONE)))
    assert roundtrip(two, 0) == 'x=-1,x=1'
    sq = K.mul_(K.ONE, [(K.TWO, K.HALF)])
    r = K.mk((K.LST, K.rel_(K.EQ, x, K.neg_(sq)), K.rel_(K.EQ, x, sq)))
    assert roundtrip(r, 0) == 'x=-sqrt(2),x=sqrt(2)'
    e, ctx = ev('1+x+x^2/2+x^3/6+x^4/24+x^5/120+O(x^6)')
    assert roundtrip(e, 0) == '1+x+x^2/2+x^3/6+x^4/24+x^5/120+O(x^6)'
    one = K.mk((K.LST, K.rel_(K.EQ, x, K.TWO)))
    assert roundtrip(one, 0) == 'x=2'          # the documented exception


def test_roundtrip_nested_lists_and_gaussians():
    x = K.sym('x')
    y = K.sym('y')
    sys1 = K.mk((K.LST, K.rel_(K.EQ, x, K.ONE), K.rel_(K.EQ, y, K.TWO)))
    assert roundtrip(K.mk((K.LST, sys1)), 0) == '[[x=1,y=2]]'
    two = K.mk((K.LST, sys1, K.mk((K.LST, K.rel_(K.EQ, x, K.TWO), K.rel_(K.EQ, y, K.ONE)))))
    assert roundtrip(two, 0) == '[x=1,y=2],[x=2,y=1]'
    assert roundtrip(K.mk((K.LST, K.mk((K.LST,)))), 0) == '[[]]'
    assert roundtrip(K.mk((K.LST, x, K.rel_(K.EQ, x, K.ONE))), 0) == '[x,x=1]'
    for a, b, d in ((3, -4, 1), (-3, 4, 1), (1, -1, 2), (-1, -3, 5), (0, -1, 3), (2, 1, 7)):
        z = K.num(a, b, d)
        roundtrip(z, 0)
        roundtrip(K.mul_(K.ONE, [(z, x)]), 0)
        roundtrip(K.mul_(K.ONE, [(x, z)]), 1)
        roundtrip(K.rel_(K.EQ, x, z), 0)
        roundtrip(K.mk((K.CALL, K.sym('f'), z, z)), 0)
        roundtrip(K.mk((K.LST, z)), 0)
    roundtrip(K.flt(-1.5, -2.0), 0)
    roundtrip(K.mul_(K.ONE, [(x, K.flt(0.5, -2.0))]), 0)


def test_roundtrip_hold_compares_values():
    m = K.mk((K.MUL, K.ONE, K.TWO, K.num(3), K.num(3), K.TWO, K.num(5), K.ONE))
    h = K.mk((K.HOLD, m))
    assert roundtrip(h, 0) == '2^3*3^2*5'
    assert reparse('2^3*3^2*5', 0) == K.num(360)


def test_roundtrip_degree_mode_named():
    for s in ('sin(x+30)', 'asin(x)+30', 'cos(2(x+15))', 'sin(asin(x)/2+x)', 'atan(1/x)*2',
              'sin(x)^2+asin(1/3)', 'sin(x-30)', 'sin(30-x)', 'cos(-x-1)', 'tan(x/2)',
              'sin(0.5x)'):
        e, ctx = ev(s, 1)
        roundtrip(e, 1)
        K.reset()


def test_roundtrip_relations_and_factorials():
    x = K.sym('x')
    n = K.sym('n')
    for e in (K.rel_(K.LT, K.num(3), x), K.rel_(K.LE, x, K.num(3)),
              K.rel_(K.EQ, K.fn_(K.FACT, n), K.ONE),
              K.rel_(K.NE, K.fn_(K.FACT, n), K.ONE),
              K.rel_(K.EQ, K.mul_(K.TWO, [(K.fn_(K.FACT, n), K.ONE)]), K.ONE),
              K.mk((K.EQ, K.rel_(K.EQ, x, K.ONE), K.TWO)),
              K.fn_(K.FACT, K.fn_(K.FACT, n)),
              K.mul_(K.ONE, [(K.fn_(K.FACT, n), K.TWO)])):
        roundtrip(e, 0)
