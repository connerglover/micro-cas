"""T1.10: normal, expand, together, the zero test and simplify (DESIGN 8.1, 8.5-8.7, 14).

Acceptance (section 21.4): the expand cap; normal with the gcd; g_iszero YES/NO/LIKELY;
simplify candidates with numeric verification and SIMPBUG == 0; the alg section 6 seeds 2.4
and 2.5: (x+1)^2-x^2-2x = 1, x/x = 1, expand((x+y)^3), normal((x^2-1)/(x-1)) = x+1.

The modules under test are the real CVNORM family (norm.py, normb.py) with the real CVPOLY,
CVRULE and CVIDENT families, loaded through run.need; end-to-end cases go through run.go with
the real parser and printer. Results are checked against SymPy (equivalence) and, where the
form is the point, against the canonical node of the expected text.
"""
import os
import random
import sys
import types

import mpmath
import pytest
import sympy

import alg as A
import gen
import node as K
import parse as P
import printer as PR
import run as R
from test_node import arena  # noqa: F401 - the debug-arena fixture (DESIGN 20.4)

import norm as NO
import normb as NB

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LAZYMAX = 150

FRESH = (('ANS', None), ('HIST', list), ('VARS', dict), ('FUNCS', dict), ('MODS', dict),
         ('LOADED', list), ('USE', dict), ('PINNED', list), ('LIVE', dict), ('NEEDED', list))


@pytest.fixture(autouse=True)
def sess(monkeypatch):
    """A fresh session and loader with the real lazy modules; P.SESS = R; the NORM closure
    loaded (R.MODS), so that plain calls into norm/normb work."""
    for name, make in FRESH:
        monkeypatch.setattr(R, name, make() if make is not None else None)
    monkeypatch.setattr(R, 'SET', {'deg': 0})
    monkeypatch.setattr(R, 'CLOCK', [0])
    monkeypatch.setattr(P, 'SESS', R)
    R.need('norm')
    # A previous calculus command (test_defint) may have evicted and reloaded the norm family:
    # patch and inspect the loaded instances, not the collection-time imports (as test_factor).
    for alias, key in (('NO', 'norm'), ('NB', 'normb')):
        monkeypatch.setattr(sys.modules[__name__], alias, R.MODS[key])
    yield


# -- helpers ---------------------------------------------------------------------------------

def drive(g):
    """The trampoline of DESIGN 10.4 (regions, TICK, CasSoft -> None), without the runner."""
    stack = [g]
    marks = [-1]
    val = None
    while stack:
        try:
            y = stack[-1].send(val)
        except StopIteration:
            y = None
        except K.CasSoft:
            y = None
        else:
            if y is R.TICK:
                val = None
                continue
            if isinstance(y, types.GeneratorType):
                stack.append(y)
                marks.append(-1)
                val = None
                continue
            if type(y) is tuple and len(y) == 2 and y[0] is R.SCOPE:
                stack.append(y[1])
                marks.append(K.NN)
                val = None
                continue
        stack.pop()
        m = marks.pop()
        if m >= 0:
            y = K.keep(m, y)
        val = y
    return val


def nd(s, deg=0):
    """The node of s, built as typed (the answer path: no commands run, floats stay)."""
    return drive(P.g_eval(P.rpn(P.tokens(s, 0)), [deg, None, 0, 1]))


def tx(e):
    return PR.text(e, None)


def expand(s):
    return NO.normal(nd(s), 1)


def normal(s):
    return NO.normal(nd(s))


def go(s):
    return R.go(('eval', s))


def ans(s):
    r = go(s)
    assert r[0] == 'ans', (s, r)
    return r[1]


def iszero(e):
    return drive(NB.g_iszero(e))


def simp(e, full=1):
    return drive(NB.g_simp(e, full))


FN = {K.SIN: sympy.sin, K.COS: sympy.cos, K.TAN: sympy.tan, K.SEC: sympy.sec,
      K.CSC: sympy.csc, K.COT: sympy.cot, K.ASIN: sympy.asin, K.ACOS: sympy.acos,
      K.ATAN: sympy.atan, K.SINH: sympy.sinh, K.COSH: sympy.cosh, K.TANH: sympy.tanh,
      K.LN: sympy.log, K.ABS: sympy.Abs, K.SIGN: sympy.sign, K.FLOOR: sympy.floor,
      K.CEIL: sympy.ceiling, K.FACT: sympy.factorial}


def to_sympy(n):
    """The SymPy value of node n (symbols real); odd-denominator powers are real roots."""
    vals = {}
    for i in A.postorder(n):
        t = K.N[i]
        op = t[0]
        if op == K.NUM:
            v = sympy.Rational(t[1], t[3]) + sympy.I * sympy.Rational(t[2], t[3])
        elif op == K.FLT:
            v = sympy.Float(t[1]) + sympy.I * sympy.Float(t[2])
        elif op == K.SYM:
            v = sympy.Symbol(t[1], real=True)
        elif i == K.PI:
            v = sympy.pi
        elif i == K.E:
            v = sympy.E
        elif op == K.ADD:
            v = vals[t[1]]
            for j in range(2, len(t), 2):
                v = v + vals[t[j]] * vals[t[j + 1]]
        elif op == K.MUL:
            v = vals[t[1]]
            for j in range(2, len(t), 2):
                e = K.N[t[j + 1]]
                if e[0] == K.NUM and not e[2] and e[3] % 2 and e[3] > 1:
                    v = v * sympy.real_root(vals[t[j]], e[3]) ** e[1]
                else:
                    v = v * vals[t[j]] ** vals[t[j + 1]]
        elif op >= K.FN0:
            v = FN[op](vals[t[1]])
        elif op == K.LST:
            v = tuple(vals[c] for c in t[1:])
        else:
            raise ValueError('no SymPy value for %r' % (t,))
        vals[i] = v
    return vals[n]


def num_equal(a, b, pts=4, seed=7):
    """a == b at random real points (both sides real there, or both complex and equal)."""
    d = a - b
    syms = sorted(d.free_symbols, key=lambda s: s.name)
    r = random.Random(seed)
    ok = 0
    for k in range(pts * 4):
        sub = {}
        for s in syms:
            v = r.uniform(0.3, 2.7)
            sub[s] = sympy.Float(-v if k % 3 == 2 else v, 30)
        try:
            va = complex(a.subs(sub).evalf(30))
            vb = complex(b.subs(sub).evalf(30))
        except (TypeError, ZeroDivisionError, ValueError):
            continue
        if any(map(lambda z: z != z or abs(z) == float('inf'), (va, vb))):
            continue
        if abs(va - vb) > 1e-9 * max(1.0, abs(va), abs(vb)):
            return False
        ok += 1
        if ok >= pts:
            break
    return ok > 0


def equiv(x, y):
    """Nodes x and y have the same value: SymPy, else numerically."""
    a = to_sympy(x)
    b = to_sympy(y)
    try:
        if sympy.simplify(sympy.expand(a - b)) == 0:
            return True
    except Exception:                                   # noqa: BLE001 - SymPy edge cases
        pass
    return num_equal(a, b)


def is_expanded(e):
    """No product holds a sum to a positive integer power, so nothing is left to multiply."""
    for m in A.postorder(e):
        t = K.N[m]
        if t[0] == K.MUL:
            sums = 0
            for j in range(2, len(t), 2):
                w = K.N[t[j + 1]]
                if K.N[t[j]][0] == K.ADD and w[0] == K.NUM and not w[2] and w[3] == 1 \
                        and w[1] > 0:
                    sums += 1
            if sums:
                return False
    return True


def sy(x):
    """SymPy text in the input language."""
    return str(x).replace('**', '^')


def reachable(roots):
    """Ids reachable from roots and from every RULECACHE pattern."""
    st = list(roots)
    for nm in K.RULECACHE:
        for b in K.RULECACHE[nm].values():
            for p in b:
                st.append(p[0])
    out = set()
    while st:
        i = st.pop()
        if i in out:
            continue
        out.add(i)
        t = K.N[i]
        if t[0] >= K.COMP:
            st.extend(t[1:])
    return out


def numden(e):
    """SymPy numerator and denominator of a normal form."""
    return sympy.fraction(sympy.together(to_sympy(e)))


# -- the API and the parts --------------------------------------------------------------------

def test_api():
    for f in ('normal', 'pmul', 'ppow', 'g_expand', 'g_together',
              'g_simplify', 'g_autosimp', 'MAXTERMS', 'KRONMAX', 'GAVEUP'):
        assert hasattr(NO, f), f
    for f in ('g_iszero', 'g_simp', 'g_one', 'SIMPBUG', 'YES'):
        assert hasattr(NB, f), f
    assert (A.NO, A.LIKELY, NB.YES) == (0, 1, 2)
    assert NO.MAXTERMS == 400 and NO.KRONMAX == 64
    for name in ('simplify', 'expand', 'together'):          # the registry reaches them
        ent = R.CMDS[name]
        assert ent[0] == 'norm' and hasattr(NO, ent[1])
    assert R.PARTS['norm'][:3] == ('norm', 'normb', 'normc')


def code_lines(name):
    sys.path.insert(0, os.path.join(ROOT, 'build'))
    try:
        import bundle
    finally:
        sys.path.pop(0)
    with open(os.path.join(ROOT, 'src', name + '.py'), encoding='utf-8') as fh:
        return len(bundle.minify(fh.read(), name).lines)


@pytest.mark.parametrize('part', ['norm', 'normb', 'normc'])
def test_parts_fit_lazymax(part):
    assert code_lines(part) <= LAZYMAX


@pytest.mark.parametrize('part', ['norm', 'normb', 'normc'])
def test_parts_size_is_bounded(part):
    assert code_lines(part) <= 210      # the documented overrun (T1.10 notes), not more


# -- expand (8.5) ------------------------------------------------------------------------------

def test_seed_expand_cube():
    e = expand('(x+y)^3')
    assert e == nd('x^3+3*x^2*y+3*x*y^2+y^3')
    assert ans('expand((x+y)^3)') == 'x^3+3*x^2*y+3*x*y^2+y^3'


def test_seed_expand_cancels():
    assert expand('(x+1)^2-x^2-2x') == K.ONE
    assert ans('expand((x+1)^2-x^2-2*x)') == '1'


@pytest.mark.parametrize('src, want', [
    ('(x+1)*(x-1)', 'x^2-1'),
    ('(2x+3)^2', '4x^2+12x+9'),
    ('(x+y+z)^2', 'x^2+y^2+z^2+2x*y+2x*z+2y*z'),
    ('(a+b)*(c+d)', 'a*c+a*d+b*c+b*d'),
    ('3(x+1)/2', '3x/2+3/2'),
    ('(x/2+1/3)^2', 'x^2/4+x/3+1/9'),
    ('sin(2(x+1))', 'sin(2x+2)'),
    ('e^(2(x+1))', 'e^(2x+2)'),
    ('ln((x+1)^2)', 'ln(x^2+2x+1)'),
    ('(1+sqrt(2))^2', '3+2sqrt(2)'),
    ('(1+sqrt(2))^3', '7+5sqrt(2)'),
    ('(sqrt(2)+sqrt(3))^2', '5+2sqrt(6)'),
    ('(x+i)^2', 'x^2+2i*x-1'),
    ('(1+i)^5', '-4-4i'),
    ('(x+1)^2/(x-1)', 'x^2/(x-1)+2x/(x-1)+1/(x-1)'),
    ('x*(1/x+1)', '1+x'),
    ('sqrt(x+1)*(x+2)', 'x*sqrt(x+1)+2sqrt(x+1)'),
    ('(x+1)^(3/2)*(x+1)', '(x+1)^(5/2)'),
    ('2^(x+1)*(x+1)', 'x*2^(x+1)+2^(x+1)'),
    ('(sin(x)+cos(x))^2', 'sin(x)^2+2sin(x)*cos(x)+cos(x)^2'),
    ('(x^(1/3)+1)^3', 'x+3x^(2/3)+3x^(1/3)+1'),
    ('(sqrt(x)+1)*(sqrt(x)-1)', 'x-1'),
    ('[(x+1)^2, (x-1)^2]', '[x^2+2x+1, x^2-2x+1]'),
    ('(x+1)^2=4', 'x^2+2x+1=4'),
    ('f((x+1)^2)', 'f(x^2+2x+1)'),
    ('7', '7'),
    ('x', 'x'),
])
def test_expand_cases(src, want):
    e = expand(src)
    assert e == nd(want), (src, tx(e))
    assert is_expanded(e)


def test_expand_floats_stay_floats():
    e = expand('0.5*(x+1)^2')
    assert equiv(e, nd('0.5*x^2+x+0.5'))
    assert is_expanded(e)


def test_expand_matches_sympy_on_random_trees():
    n = 0
    for seed in range(60):
        g = gen.Gen(seed, syms=('x', 'y'), funcs=('sin', 'exp', 'sqrt', 'ln'), maxint=4)
        t = g.tree(3)
        try:
            e = gen.build(t, K)
        except (K.CasSoft, K.CasError):
            continue
        try:
            r = NO.normal(e, 1)
        except K.CasError as x:
            assert x.args[0] in (NO.M_LARGE, K.M_BIG)
            continue
        except K.CasSoft:
            continue
        assert is_expanded(r), (gen.text(t), tx(r))
        assert equiv(e, r), (gen.text(t), tx(r))
        n += 1
        K.reset()
    assert n > 30


def test_expand_cap(monkeypatch):
    seen = []
    pmul = NO.pmul

    def spy(a, b, rl):
        r = pmul(a, b, rl)
        seen.append(len(r))
        return r
    monkeypatch.setattr(NO, 'pmul', spy)
    with pytest.raises(K.CasError) as x:
        expand('(a+b+c+d)^12')                          # 455 terms > MAXTERMS
    assert x.value.args[0] == 'Too many terms'
    assert max(seen) <= NO.MAXTERMS                     # no polynomial ever held more
    with pytest.raises(K.CasError):
        expand('(a+b+c+d+f+g+h)^3*(j+k+l+m+n+p+q)^3')   # 84 * 84 terms
    monkeypatch.setattr(NO, 'pmul', pmul)
    assert go('expand((a+b+c+d)^12)') == ('msg', 'Too many terms', None, 0)


def test_expand_cap_lets_big_expansions_through():
    e = expand('(x+y+z)^20')                            # 231 terms
    assert len(K.N[e]) == 2 + 2 * 231
    K.reset()
    e = expand('(x+1)^150')                             # 151 terms, big coefficients
    assert len(K.N[e]) == 2 + 2 * 150
    assert equiv(e, nd('(x+1)^150'))
    K.reset()
    with pytest.raises(K.CasError) as x:                # 400 terms: the node table (NMAX)
        expand('(x+1)^399')                             # is the limit before MAXTERMS
    assert x.value.args[0] == K.M_COMPLEX


def test_expand_memory_model_two_thousand_terms(monkeypatch):
    # 20.12: a 2,000-term expansion is refused by the cap: no dict ever holds more than
    # MAXTERMS + 64 terms (the check runs every 64), about 33 KB at 70 B per term
    big = [0]
    pmul = NO.pmul

    def spy(a, b, rl):
        big[0] = max(big[0], len(a), len(b))
        return pmul(a, b, rl)
    monkeypatch.setattr(NO, 'pmul', spy)
    with pytest.raises(K.CasError):
        expand('(a+b+c+d+f)^10')                        # C(14,4) = 1001 terms
    with pytest.raises(K.CasError):
        expand('(a+b+c+d+f+g)^10')                      # C(15,5) = 3003 terms
    assert big[0] <= NO.MAXTERMS


def test_expand_big_numbers_fail_fast():
    with pytest.raises(K.CasError) as x:
        expand('(1+sqrt(2))^1000000')
    assert x.value.args[0] == K.M_BIG
    assert go('expand((1+sqrt(2))^1000000)')[1] == K.M_BIG


def test_expand_polls_cancel(monkeypatch):
    calls = [0]

    def esc():
        calls[0] += 1
        return calls[0] > 3
    monkeypatch.setattr(K, 'ESC', esc)
    with pytest.raises(K.Cancel):
        expand('(x+y+z)^12')


def test_expand_low_memory(monkeypatch):
    monkeypatch.setattr(K, 'MEMFREE', lambda: 100)
    with pytest.raises(K.CasMemory):
        expand('(x+y+z)^10')


def test_expand_undefined_propagates():
    with pytest.raises(K.CasSoft):
        expand('((sqrt(2)+1)^2-2*sqrt(2)-3)^(-1)')


# -- normal (8.6) ------------------------------------------------------------------------------

def test_seed_normal():
    assert normal('(x^2-1)/(x-1)') == nd('x+1')
    assert normal('x/x') == K.ONE
    assert normal('(x+1)^2-x^2-2x') == K.ONE
    assert ans('together((x^2-1)/(x-1))') == 'x+1'


@pytest.mark.parametrize('src, want', [
    ('(x^2-y^2)/(x-y)', 'x+y'),
    ('(x^2*y+x*y^2)/(x*y)', 'x+y'),
    ('x*(x+y)/(y*(x+y))', 'x/y'),
    ('(x^3-1)/(x^2-1)', '(x^2+x+1)/(x+1)'),
    ('(2x+2)/(4x^2-4)', '1/(2(x-1))'),
    ('1/(x+1)+1/(x-1)', '2x/(x^2-1)'),
    ('x/2+1/2', '(x+1)/2'),
    ('(x^2+2x*y+y^2)/(x+y)^3', '1/(x+y)'),
    ('(a*x+a*y)/(b*x+b*y)', 'a/b'),
    ('(sin(x)^2-1)/(sin(x)-1)', 'sin(x)+1'),
    ('sin((x^2-1)/(x-1))', 'sin(x+1)'),
    ('e^((x^2-1)/(x-1))', 'e^(x+1)'),
    ('(1+sqrt(2))^2-3-2sqrt(2)', '0'),
    ('1/(1+sqrt(2))-(sqrt(2)-1)', '0'),
    ('1/(x+i)-(x-i)/(x^2+1)', '0'),
    ('(1+i)^2/(2i)', '1'),
    ('(x^(1/3))^3', 'x'),
    ('(x-1)/(1-x)', '-1'),
    ('[(x^2-1)/(x-1), x/x]', '[x+1, 1]'),
    ('(x^2-1)/(x-1)=0', 'x+1=0'),
])
def test_normal_cases(src, want):
    e = normal(src)
    assert e == nd(want), (src, tx(e))
    assert not NO.GAVEUP[0]


def test_normal_is_canonical_on_random_rational_functions():
    r = random.Random(11)
    x, y = sympy.symbols('x y')
    for k in range(40):
        vs = (x,) if k % 2 else (x, y)

        def poly(deg):
            s = 0
            for i in range(deg + 1):
                for v in vs:
                    s += r.randint(-3, 3) * v ** r.randint(0, deg)
            return s + r.randint(1, 3)
        p, q, c = poly(2), poly(2), poly(1)
        if q == 0 or c == 0 or p == 0:
            continue
        a = nd('(%s)*(%s)/((%s)*(%s))' % (sy(p), sy(c), sy(q), sy(c)))
        b = nd('(%s)/(%s)' % (sy(sympy.expand(p)), sy(sympy.expand(q))))
        na = NO.normal(a)
        nb = NO.normal(b)
        assert na == nb, (k, tx(na), tx(nb))
        assert equiv(na, a)
        n_, d_ = numden(na)
        assert sympy.degree(sympy.gcd(n_, d_), x) <= 0 or len(vs) > 1, (k, tx(na))
        K.reset()


def test_normal_matches_sympy_on_random_trees():
    n = 0
    for seed in range(60):
        g = gen.Gen(seed + 100, syms=('x', 'y'), funcs=('sin', 'exp', 'ln'), maxint=5,
                    consts=('pi',))
        t = g.tree(3)
        try:
            e = gen.build(t, K)
            r = NO.normal(e)
        except (K.CasSoft, K.CasError):
            continue
        assert equiv(e, r), (gen.text(t), tx(r))
        n += 1
        K.reset()
    assert n > 30


def test_normal_univariate_gcd_is_complete():
    r = random.Random(5)
    x = sympy.Symbol('x')
    for k in range(25):
        g = sum(r.randint(-4, 4) * x ** i for i in range(r.randint(1, 3))) + x ** 3
        p = sum(r.randint(-4, 4) * x ** i for i in range(3)) + 1
        q = sum(r.randint(-4, 4) * x ** i for i in range(3)) + x ** 3
        e = nd('(%s)/(%s)' % (sy(sympy.expand(g * p)), sy(sympy.expand(g * q))))
        res = NO.normal(e)
        n_, d_ = numden(res)
        assert sympy.degree(sympy.gcd(n_, d_), x) <= 0, (k, tx(res))
        assert equiv(res, e)
        K.reset()


def test_normal_kronecker_cap_three_variables_of_degree_20(monkeypatch):
    seen = []
    PO = R.MODS['poly']
    pgcd = PO.pgcd

    def spy(a, b):
        seen.append(max(len(a), len(b)))
        return pgcd(a, b)
    monkeypatch.setattr(PO, 'pgcd', spy)
    e = nd('(x^20*y^20*z^20-1)/(x*y*z-1)')
    r = NO.normal(e)                                    # 21^3 > KRONMAX: content only
    assert equiv(r, e)
    assert not NO.GAVEUP[0]
    assert not seen or max(seen) <= NO.KRONMAX
    assert NO.normal(nd('(x^7*y^7-1)/(x*y-1)')) == nd(
        '1+x*y+x^2*y^2+x^3*y^3+x^4*y^4+x^5*y^5+x^6*y^6')   # 8*8 = KRONMAX: the full gcd
    assert max(seen) <= NO.KRONMAX


def test_near_guards_with_the_real_normal(monkeypatch):
    # 9.2/9.7: a guard whose constant difference is exactly 0 is settled by normal
    RU = R.MODS['rules']
    sets = types.SimpleNamespace(
        NEARZ=(('size',), 'sin(U)', 'cos(U)', '(1+sqrt(2))^2=3+2*sqrt(2)'),
        NEARLE=(('size',), 'sin(U)', 'cos(U)', '(sqrt(2)+sqrt(3))^2<=5+2*sqrt(6)'),
        NEARNZ=(('size',), 'sin(U)', 'cos(U)', 'e^(pi*sqrt(163))=640320^3+744'))
    monkeypatch.setitem(R.MODS, 'tst', sets)
    w = dict(RU.WHERE)
    w.update({'nearz': 'tst', 'nearle': 'tst', 'nearnz': 'tst'})
    monkeypatch.setattr(RU, 'WHERE', w)
    x = K.sym('x')
    s = K.fn_(K.SIN, x)
    assert drive(RU.g_rewrite(s, 'nearz', 0, 10)) == K.fn_(K.COS, x)
    assert drive(RU.g_rewrite(s, 'nearle', 0, 10)) == K.fn_(K.COS, x)
    assert drive(RU.g_rewrite(s, 'nearnz', 0, 10)) == s


def test_normal_gives_up_and_says_so():
    for s in ('x+oo', '(x+1)*oo'):
        e = nd(s)
        assert NO.normal(e) == e and NO.GAVEUP[0] == 1
    e = nd('(a+b+c+d)^12/(a+1)')
    assert NO.normal(e) == e and NO.GAVEUP[0] == 1        # the term cap
    e = nd('1/((sqrt(2)+1)^2-2*sqrt(2)-3)')               # 1/0 found by normal: no raise
    assert NO.normal(e) == e and NO.GAVEUP[0] == 1
    assert NO.normal(nd('x+1')) == nd('x+1') and NO.GAVEUP[0] == 0


def test_normal_near_protocol_contract():
    # rules.g_rewrite settles a NEAR guard with normal(d) == ZERO (docs/notes/T1.9.md):
    # exactly 0 gives ZERO, a nonzero constant never does, and no constant raises
    for s in ('(1+sqrt(2))^2-(3+2sqrt(2))', '(sqrt(2)+sqrt(3))^2-5-2sqrt(6)',
              '(2^(1/3))^3-2', 'sqrt(8)-2sqrt(2)', '(1+i)^4+4'):
        assert NO.normal(nd(s)) == K.ZERO, s
    for s in ('e^(pi*sqrt(163))-(640320^3+744)', 'sqrt(2)-1414213/1000000', 'pi-355/113',
              'ln(6)-ln(2)-ln(3)+1/10^20', 'abs(sqrt(2)/2)-1'):
        assert NO.normal(nd(s)) != K.ZERO, s


def test_normal_leaves_and_sentinels():
    for e in (K.ZERO, K.ONE, K.PI, K.E, K.I, K.TRUE, K.FALSE, K.sym('x'), K.flt(0.5)):
        assert NO.normal(e) == e
        assert NO.normal(e, 1) == e


# -- together and the factored denominator (14) ------------------------------------------------

@pytest.mark.parametrize('src, want', [
    ('together(1/(x+1)+1/(x-1))', '2*x/(x^2-1)'),
    ('together(x/(x+1)^2+1/(x+1)^2)', '1/(x+1)'),
    ('together(1/(x^2+2*x+1))', '1/(x+1)^2'),
    ('together(1/(x^4+2*x^2+1))', '1/(x^2+1)^2'),
    ('together(1/(2*x+2)+1/(x+1)^2)', '(x+3)/(2*(x+1)^2)'),
    ('together(1/x+1/x^2)', '(x+1)/x^2'),
    ('together(1/(x^2-1))', '1/(x^2-1)'),
    ('together(a/b+c/d)', '(a*d+b*c)/(b*d)'),
])
def test_together(src, want):
    assert ans(src) == want


def test_dfac_on_normal_forms():
    r = R.MODS['normc'].dfac(NO.normal(nd('1/(x^3-3*x^2+3*x-1)')))
    assert r == nd('1/(x-1)^3')
    r = R.MODS['normc'].dfac(NO.normal(nd('x/(x^2-4*x+4)')))
    assert r == nd('x/(x-2)^2')
    r = R.MODS['normc'].dfac(NO.normal(nd('1/(sin(x)^2+2*sin(x)+1)')))
    assert r == nd('1/(sin(x)+1)^2')
    for s in ('x+1', '1/(x*y+1)', '1/(x^2+y)', '(x+1)/2'):  # nothing to factor
        e = NO.normal(nd(s))
        assert R.MODS['normc'].dfac(e) == e


# -- the zero test (8.6) -----------------------------------------------------------------------

@pytest.mark.parametrize('s', [
    '0', '(x+1)^2-x^2-2x-1', 'x/x-1', '(x^2-1)/(x-1)-x-1',
    'sin(x)^2+cos(x)^2-1', 'tan(x)-sin(x)/cos(x)', 'sec(x)^2-tan(x)^2-1',
    'sin(x)*(sin(x)+1)-1+cos(x)^2-sin(x)', 'ln(6)-ln(2)-ln(3)', 'ln(12)-2ln(2)-ln(3)',
    '(1+sqrt(2))^2-3-2sqrt(2)', '1/(1+sqrt(2))-sqrt(2)+1', '1/(x+i)-(x-i)/(x^2+1)',
    'e^(2x)-(e^x)^2', '(e^x+1)^2-e^(2x)-2e^x-1', '(sqrt(x)+1)^2-x-2sqrt(x)-1',
])
def test_iszero_yes(s):
    assert iszero(nd(s)) == NB.YES, s


@pytest.mark.parametrize('s', [
    '1', 'x', 'x^2+1', '1/x', 'sin(x)', 'x-y', '(x+1)^2-x^2', '1+sqrt(2)-sqrt(3)',
    'sqrt(x^2)-x', 'pi-355/113', 'e^x-1-x', 'sin(x)^2-cos(x)^2', '0.5',
    'sin(x)^2+cos(x)^2-1+1/10^12',
])
def test_iszero_no(s):
    assert iszero(nd(s)) == A.NO, s


@pytest.mark.parametrize('s', [
    'sin(2x)-2sin(x)cos(x)',            # multiple angles: T2 (8.6 step 2)
    'ln(x^2)-2ln(x)',                   # not real at x < 0: points skipped
    'sqrt(-1-x^2)',                     # never real: no usable point
    'asin(sin(x/9))-x/9',
])
def test_iszero_likely(s):
    assert iszero(nd(s)) == A.LIKELY, s


def test_iszero_leaves():
    assert iszero(K.ZERO) == NB.YES and iszero(K.flt(0.0)) == NB.YES
    for e in (K.ONE, K.I, K.PI, K.E, K.OO, K.UNDEF, K.sym('x'), K.flt(1e-30)):
        assert iszero(e) == A.NO


def test_iszero_leaves_no_nodes():
    e = nd('sin(x)^2+cos(x)^2-1+(x+1)^2/(x+2)')
    m = K.NN
    v = iszero(e)
    assert v in (A.NO, A.LIKELY)
    live = reachable(())                                # only rule patterns may stay
    assert all(i in live for i in range(m, K.NN))


def test_iszero_through_a_scoped_call():
    def g_parent(e):
        v = yield R.scoped(NB.g_iszero(e))
        yield v
    assert drive(g_parent(nd('tan(x)*cos(x)-sin(x)'))) == NB.YES


# -- simplify (8.7) ----------------------------------------------------------------------------

def test_seed_simplify():
    assert ans('simplify((x+1)^2-x^2-2x)') == '1'
    assert ans('simplify(x/x)') == '1'
    assert ans('x/x') == '1'


@pytest.mark.parametrize('src, want', [
    ('simplify((x^2-1)/(x-1))', 'x+1'),
    ('simplify(sin(x)^2+cos(x)^2)', '1'),
    ('simplify(tan(x)*cos(x))', 'sin(x)'),
    ('simplify(1-sin(x)^2)', 'cos(x)^2'),
    ('simplify(sin(x)^4-cos(x)^4)', '-cos(2*x)'),
    ('simplify(2*sin(x)*cos(x))', 'sin(2*x)'),
    ('simplify(sin(x)/tan(x))', 'cos(x)'),
    ('simplify(1/(1+sqrt(2)))', 'sqrt(2)-1'),
    ('simplify(2/(sqrt(3)-1))', 'sqrt(3)+1'),
    ('simplify(sqrt(3+2*sqrt(2)))', 'sqrt(2)+1'),
    ('simplify(ln(2)+ln(3))', 'ln(6)'),
    ('simplify(2^x*3^x)', '6^x'),
    ('simplify(1/(x-1)-1/(x+1)+sin(x))', '2/(x^2-1)+sin(x)'),
    ('simplify(x/(x+1)+1/(x+1))', '1'),
    ('simplify(2*(x+1)*(x-1))', '2*(x-1)*(x+1)'),
    ('simplify((x^2-2)/(x-sqrt(2)))', 'x+sqrt(2)'),
    ('simplify((x-1)/(sqrt(x)-1))', 'sqrt(x)+1'),
    ('simplify((e^(2*x)-1)/(e^x-1))', 'e^x+1'),
    ('simplify(x^2/(x^3+x))', 'x/(x^2+1)'),
    ('simplify(1/sin(x)^2-1/tan(x)^2)', '1'),
    ('simplify(sec(x)*cos(x))', '1'),
    ('simplify(ln(x)+ln(y))', 'ln(x*y)'),
    ('simplify(sin(x)/cos(x))', 'sin(x)/cos(x)'),
    ('simplify((x+1)^2)', '(x+1)^2'),
    ('simplify(x+1)', 'x+1'),
    ('simplify(sin(x))', 'sin(x)'),
])
def test_simplify_cases(src, want):
    assert ans(src) == want


def test_default_path():
    assert ans('1/(x+1)+1/(x-1)') == '2*x/(x^2-1)'       # a sum with a negative power
    assert ans('tan(x)*cos(x)') == 'sin(x)'              # tan
    assert ans('1/(x+1)+1') == '1/(x+1)+1'               # one fraction is not smaller
    assert ans('ln(2)+ln(3)') == 'ln(2)+ln(3)'           # lncollect is explicit only
    assert ans('(x+1)^2-x^2-2x') == '-x^2-2*x+(x+1)^2'   # not a candidate (8.7)


def test_default_path_skips_big_results():
    e = nd('+'.join('1/(x+%d)' % i for i in range(1, 25)))
    assert A.size(e) >= NB.AUTOMAX
    assert simp(e, 0) == e


def test_explicit_only_candidates():
    for s in ('ln(2)+ln(3)', '2^x*3^x', 'sqrt(3+2*sqrt(2))'):
        e = nd(s)
        assert simp(e, 0) == e
        assert simp(e, 1) != e


def test_simplify_maps_lists_and_relations():
    e = nd('[(x^2-1)/(x-1), tan(x)*cos(x)]')
    assert simp(e) == nd('[x+1, sin(x)]')
    e = nd('y=(x^2-1)/(x-1)')
    assert simp(e) == nd('y=x+1')
    e = nd('[x=2^(1/3), x=1/(1+sqrt(2))]')
    assert simp(e) == nd('[x=2^(1/3), x=sqrt(2)-1]')


def test_simplify_sentinels_untouched():
    for e in (K.TRUE, K.FALSE, K.mk((K.LST,)), K.mk((K.DNE, K.ONE, K.TWO)), K.UNDEF, K.OO):
        assert simp(e) == e


def test_simplify_matches_sympy_and_never_grows():
    n = 0
    for seed in range(50):
        g = gen.Gen(seed + 300, syms=('x',), funcs=('sin', 'cos', 'tan', 'sqrt', 'ln'),
                    maxint=4)
        t = g.tree(3)
        try:
            e = gen.build(t, K)
        except (K.CasSoft, K.CasError):
            continue
        r = simp(e)
        assert A.size(r, True) <= A.size(e, True)
        assert r == e or equiv(r, e), (gen.text(t), tx(r))
        assert NB.SIMPBUG == 0
        n += 1
        K.reset()
    assert n > 30


def test_high_degree_denominators_are_not_factored():
    # dfac's factoring is cubic in the degree: past 64 it would take minutes on the calculator
    import signal
    import time

    def hang(*a):
        raise AssertionError('no answer within 5 s')
    old = signal.signal(signal.SIGALRM, hang)
    signal.alarm(5)
    try:
        for s in ('1/(x^500-1)', '1/(x^2000+1)'):
            t0 = time.perf_counter()
            r = R.go(('eval', s))
            assert r[:2] == ('ans', s) and time.perf_counter() - t0 < 0.5, (s, r)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_verification_rejects_a_wrong_candidate(monkeypatch):
    real = NO.normal

    def wrong(e, ex=0):
        r = real(e, ex)
        return K.add_([r, K.ONE]) if not ex and K.V[r] else r   # off by one
    monkeypatch.setattr(NO, 'normal', wrong)
    e = nd('(x^2-1)/(x-1)')
    assert simp(e) == e                                 # x+2 is smaller, but wrong
    assert NB.SIMPBUG >= 1
    NB.SIMPBUG = 0


def test_verification_without_a_real_point_discards(monkeypatch):
    real = NO.normal

    def other(e, ex=0):
        return K.sym('zz') if not ex else real(e, ex)
    monkeypatch.setattr(NO, 'normal', other)
    e = nd('sqrt(-1-x^2)*(x^2-1)/(x-1)')                # never real: nprobe is UNKNOWN
    assert simp(e) == e
    assert NB.SIMPBUG == 0


def test_simplify_regions_release_candidates():
    e = nd('(x^2-1)/(x-1)+sin(x)^2+cos(x)^2')
    m = K.NN
    r = simp(e)
    live = reachable((r,))
    leak = [i for i in range(m, K.NN) if i not in live]
    assert not leak, [K.N[i] for i in leak]
    assert r == nd('x+2')


def test_simplify_under_the_debug_arena(arena):
    for s in ('simplify(sin(x)^4-cos(x)^4)', 'simplify(1/(1+sqrt(2)))',
              'together(1/(x+1)+1/(x-1))', 'expand((x+y)^3)', '1/(x+1)+1/(x-1)'):
        assert go(s)[0] == 'ans', s


def test_commands_leave_the_table_empty():
    for s in ('simplify((x^2-1)/(x-1))', 'expand((x+1)^5)', 'together(1/x+1/y)'):
        go(s)
        assert K.NN == K.BASE
        assert not R.LIVE and not R.NEEDED


# -- depth -------------------------------------------------------------------------------------

def nested(kind, n):
    """Built with the constructors (the parser caps nesting at 32 brackets)."""
    x = K.sym('x')
    e = x
    for i in range(n):
        if kind == 'frac':                              # 1/(1+1/(1+...))
            e = K.mul_(K.ONE, [(K.add_([K.ONE, e]), K.MONE)])
        elif kind == 'lin':                             # 2*(2*(x+1)+2)+3 ... (factored)
            e = K.mul_(K.TWO, [(K.add_([e, K.num(i % 3 + 1)]), K.ONE)])
        else:                                           # sin(sin(...)) of a tan: trig
            e = K.fn_(K.SIN if i else K.TAN, K.add_([e, K.ONE]))
    if kind == 'lin':
        e = K.add_([K.mul_(K.ONE, [(e, K.TWO)]), K.mul_(K.ONE, [(e, K.MONE)])])
    return e


@pytest.mark.parametrize('kind', ['frac', 'lin', 'trig'])
def test_nesting_invariance(kind, evodepth):
    depths = []
    for n in (1, 8, 32 if kind != 'trig' else 20):
        e = nested(kind, n)
        _, d1, _ = evodepth.measure(NO.normal, e)
        _, d2, _ = evodepth.measure(NO.normal, e, 1)
        _, d3, _ = evodepth.measure(drive, NB.g_simp(e, 1))
        depths.append((d1, d2, d3))
        K.reset()
    assert depths[0] == depths[1] == depths[2], depths


@pytest.mark.strict_depth
def test_commands_in_strict_depth_mode():
    for s in ('simplify(sin(x)^4-cos(x)^4)', 'expand((x+y)^3)', 'together(1/(x+1)+1/(x-1))',
              'simplify(1/(1+sqrt(2)))'):
        assert go(s)[0] == 'ans', s
