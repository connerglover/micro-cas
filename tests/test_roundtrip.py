"""T1.7: the round-trip invariant (DESIGN 12.5, MUST).

For every corpus result and every fuzz case, in both angle modes, re-parsing text(e) through
the answer path of section 7.1 (stages 3-5 and 7, then g_eval in inert mode with the answer's
angle mode) gives e again, in the same table. Floats compare within 1e-14 relative. The
exceptions (docs/notes/T1.7.md): HOLD re-parses to its value, and a one-element top-level
solution list prints as its element (FlowCE's `x=2`).
"""
import pytest

import gen


def seeds(fast, total):
    """Seeds 0..total-1; those from fast on are marked slow (the fast loop keeps a subset)."""
    out = []
    for s in range(total):
        out.append(s if s < fast else pytest.param(s, marks=pytest.mark.slow))
    return out
import parse as P
import printer as PR

from test_print import drive, ev, golden_cases

K = P.K


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


def expected(e):
    """What the text of e re-parses to: e, except for the two documented exceptions."""
    t = K.N[e]
    if t[0] == K.HOLD:
        m = K.N[t[1]]
        pairs = []
        for j in range(2, len(m), 2):
            pairs.append((m[j], m[j + 1]))
        return K.mul_(m[1], pairs)
    if t[0] == K.LST and len(t) == 2 and K.EQ <= K.N[t[1]][0] <= K.LE:
        return t[1]
    return e


def roundtrip(e, deg):
    s = PR.text(e, [deg, None, 0, 0])
    assert s is not None
    e2 = reparse(s, deg)
    want = expected(e)
    assert same(e2, want), 'deg=%d: %r re-parses to %r, not %r' % (
        deg, s, PR.text(e2, [deg, None, 0, 0]), PR.text(want, [deg, None, 0, 0]))
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
