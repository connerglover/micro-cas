"""T1.11: factor (DESIGN 11.2; alg 2.8).

Acceptance (section 21.4): the alg section 6 seeds 2.8 (x^4+4, x^6-1, 6x^3-11x^2+6x-1, x^2-y^2,
2x^3-4x^2-6x, and x^5-x+1 with no false claim: its search is complete, nothing is claimed in
the answer); the product check (every factorization multiplies back exactly; FACTBUG == 0);
the budgets (Kronecker, recombination and cyclotomic caps stop the search with a correct
partial factorization and COMPLETE == 0).

The modules under test are the real CVFACT family (factor.py through factord.py) with the real CVPOLY,
CVNORM, CVRULE and CVIDENT families, loaded through run.need; end-to-end cases go through run.go
with the real parser and printer. Results are checked against SymPy: the value (the product
expands to the input) and the factor degrees against sympy.factor_list over Q.
"""
import os
import random
import sys
import time
import types

import pytest
import sympy

import alg as A
import node as K
import parse as P
import printer as PR
import run as R

import factor as FA
import factorb as FB
import factord as FD
import poly as PO

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LAZYMAX = 150

FRESH = (('ANS', None), ('HIST', list), ('VARS', dict), ('FUNCS', dict), ('MODS', dict),
         ('LOADED', list), ('USE', dict), ('PINNED', list), ('LIVE', dict), ('NEEDED', list))

X = sympy.Symbol('x', real=True)


def seeds(fast, total):
    """Seeds 0..total-1; those from fast on are marked slow (the fast loop keeps a subset)."""
    out = []
    for s in range(total):
        out.append(s if s < fast else pytest.param(s, marks=pytest.mark.slow))
    return out


@pytest.fixture(autouse=True)
def sess(monkeypatch):
    """A fresh session and loader with the real lazy modules; P.SESS = R; the FACT closure
    loaded (R.MODS), so that plain calls into factor/factorb work. After the test: no failed
    product check (FACTBUG == 0)."""
    for name, make in FRESH:
        monkeypatch.setattr(R, name, make() if make is not None else None)
    monkeypatch.setattr(R, 'SET', {'deg': 0})
    monkeypatch.setattr(R, 'CLOCK', [0])
    monkeypatch.setattr(P, 'SESS', R)
    R.need('fact')
    # A previous calculus command may have evicted/reloaded the factor family.
    # Patch and inspect the actual loaded instances, not collection-time imports.
    for alias, key in (('FA', 'fact'), ('FB', 'factb'), ('FD', 'factd'), ('PO', 'poly')):
        monkeypatch.setattr(sys.modules[__name__], alias, R.MODS[key])
    FB.FACTBUG = 0
    yield
    assert R.MODS['factb'].FACTBUG == 0, 'a factorization failed its product check'


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


def fac(s, ctx=None):
    """factor(s) through g_factor on the node of s."""
    return drive(R.MODS['fact'].g_factor((nd(s),), ctx or [0, None, 0, 0]))


def tx(e):
    return PR.text(e, None)


def go(s):
    return R.go(('eval', s))


def ans(s):
    r = go(s)
    assert r[0] == 'ans', (s, r)
    return r[1]


FN = {K.SIN: sympy.sin, K.COS: sympy.cos, K.TAN: sympy.tan, K.LN: sympy.log,
      K.ABS: sympy.Abs, K.ATAN: sympy.atan, K.ASIN: sympy.asin, K.ACOS: sympy.acos}


def to_sympy(n):
    """The SymPy value of node n (symbols real); odd-denominator powers are real roots; a
    HOLD is its product."""
    vals = {}
    for i in A.postorder(n):
        t = K.N[i]
        op = t[0]
        if op == K.NUM:
            v = sympy.Rational(t[1], t[3]) + sympy.I * sympy.Rational(t[2], t[3])
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
        elif op == K.HOLD:
            v = vals[t[1]]
        elif op >= K.FN0:
            v = FN[op](vals[t[1]])
        elif op == K.LST:
            v = tuple(vals[c] for c in t[1:])
        elif K.EQ <= op <= K.LE:
            v = (op, vals[t[1]], vals[t[2]])
        else:
            raise ValueError('no SymPy value for %r' % (t,))
        vals[i] = v
    return vals[n]


def same_value(a, b):
    """SymPy expressions a and b are equal (expanded, else cancelled)."""
    d = sympy.expand(a - b)
    return d == 0 or sympy.cancel(sympy.together(d)) == 0


def degs(e):
    """The sorted (total degree, multiplicity) of the non-constant factors of our node e (its
    top-level product pairs)."""
    t = K.N[e]
    prs = t[2:] if t[0] == K.MUL else (e, K.ONE)
    out = []
    for j in range(0, len(prs), 2):
        b = to_sympy(prs[j])
        if b.free_symbols:
            m = K.N[prs[j + 1]]
            out.append((sympy.Poly(b, *sorted(b.free_symbols, key=str)).total_degree(),
                        m[1] // m[3]))
    return sorted(out)


def sympy_degs(s):
    """The same list from sympy.factor_list over Q."""
    out = []
    for b, m in sympy.factor_list(s)[1]:
        if b.free_symbols:
            out.append((sympy.Poly(b, *sorted(b.free_symbols, key=str)).total_degree(), m))
    return sorted(out)


def parts(t):
    """The top-level factors of a text, sorted: (numerator, denominator); a parenthesized
    denominator is split too (the display order is the printer's)."""
    num = []
    den = []
    cur = ['', num]
    d = 0
    for ch in t + '*':
        d += (ch == '(') - (ch == ')')
        if ch in '*/' and d == 0:
            cur[1].append(cur[0])
            cur = ['', den if ch == '/' else cur[1]]
        else:
            cur[0] += ch
    if len(den) == 1 and den[0][:1] == '(' and den[0][-1:] == ')':
        sub = parts(den[0][1:-1])
        if not sub[1]:
            den = sub[0]
    return (sorted(num), sorted(den))


def check(s, text=None, complete=None):
    """factor(s): its factors as text (if given; in any order), its value, and its factor
    degrees against SymPy (when the search was complete); returns the text."""
    e = fac(s)
    t = tx(e)
    if text is not None:
        assert parts(t) == parts(text), (s, t)
    v = to_sympy(e)
    src = sympy.sympify(s.replace('^', '**'), locals=SYMS)
    assert same_value(v, src), (s, t)
    if complete is not None:
        assert FA.COMPLETE[0] == complete, (s, FA.COMPLETE[0])
    if FA.COMPLETE[0] and K.N[e][0] != K.HOLD and src.is_polynomial(*src.free_symbols):
        assert degs(e) == sympy_degs(src), (s, t)
    return t


SYMS = {n: sympy.Symbol(n, real=True) for n in ('x', 'y', 'z', 'a', 'b', 'c', 't')}
SYMS.update({'e': sympy.E, 'pi': sympy.pi, 'sqrt': sympy.sqrt, 'sin': sympy.sin,
             'cos': sympy.cos, 'ln': sympy.log, 'i': sympy.I})


# -- acceptance: the alg section 6 seeds 2.8 ---------------------------------------------------

@pytest.mark.parametrize('src, text', [
    ('x^4+4', '(x^2-2*x+2)*(x^2+2*x+2)'),
    ('x^6-1', '(x-1)*(x+1)*(x^2-x+1)*(x^2+x+1)'),
    ('6*x^3-11*x^2+6*x-1', '(x-1)*(2*x-1)*(3*x-1)'),
    ('x^2-y^2', '(x-y)*(x+y)'),
    ('2*x^3-4*x^2-6*x', '2*x*(x-3)*(x+1)'),
])
def test_seeds(src, text):
    check(src, text, complete=1)


def test_seed_irreducible_quintic_no_false_claim():
    """x^5-x+1: the answer is the polynomial itself, with no claim in it; internally the
    search was complete (degree 5: no rational root and no quadratic factor)."""
    t = check('x^5-x+1', 'x^5-x+1', complete=1)
    assert 'irreducible' not in t
    r = go('factor(x^5-x+1)')
    assert r[:2] == ('ans', 'x^5-x+1')


# -- integers and rationals: HOLD (5.2, 11.2, 12.4) ----------------------------------------------

@pytest.mark.parametrize('src, text', [
    ('360', '2^3*3^2*5'), ('-12', '-2^2*3'), ('6', '2*3'), ('2^20', '2^20'), ('7', '7'),
    ('-7', '-7'), ('1', '1'), ('0', '0'), ('-1', '-1'), ('2/3', '2/3'), ('1000003', '1000003'),
    ('999999999989', '999999999989'),
])
def test_integers(src, text):
    e = fac(src)
    assert tx(e) == text
    assert to_sympy(e) == sympy.Rational(sympy.sympify(src))
    assert FA.COMPLETE[0] == 1


def test_integer_hold_structure_and_record():
    e = fac('360')
    t = K.N[e]
    assert t[0] == K.HOLD
    m = K.N[t[1]]
    assert m == (K.MUL, K.ONE, K.num(2), K.num(3), K.num(3), K.num(2), K.num(5), K.ONE)
    r = go('factor(360)')
    assert r[:3] == ('ans', '2^3*3^2*5', None)          # no decimal line for an integer
    assert ans('approx(factor(360))') == '2^3*3^2*5'     # approx does not enter a HOLD


@pytest.mark.parametrize('src, text', [
    ('360/7', '2^3*3^2*5/7'), ('-6/5', '-2*3/5'), ('1/4', '1/2^2'),
    ('-1/4', '-1/2^2'), ('12/35', '2^2*3/(5*7)'), ('1/36', '1/(2^2*3^2)'),
])
def test_rational_hold_value(src, text):
    e = fac(src)
    assert K.N[e][0] == K.HOLD
    assert to_sympy(e) == sympy.Rational(sympy.sympify(src))
    assert tx(e) == text
    assert to_sympy(nd(text)) == to_sympy(e)


def test_integer_cofactor_above_the_bound_is_not_claimed_prime():
    """1000003 and 1000033 are primes above TDIV = 10^6: their product stays one base and
    COMPLETE is 0; 2*1000003^2 keeps 1000003^2 as one base."""
    n = 1000003 * 1000033
    e = fac(str(n))
    assert tx(e) == str(n) and FA.COMPLETE[0] == 0
    e = fac('2*1000003^2')
    assert tx(e) == '2*%d' % (1000003 ** 2) and FA.COMPLETE[0] == 0


def test_random_integers():
    r = random.Random(11)
    for k in range(200):
        K.release(K.BASE)
        n = r.choice((1, -1)) * r.randrange(2, 10 ** r.randrange(2, 10))
        e = fac(str(n))
        assert to_sympy(e) == n
        t = K.N[e]
        if t[0] == K.HOLD:
            m = K.N[t[1]]
            ps = [K.N[m[j]][1] for j in range(2, len(m), 2)]
            assert ps == sorted(ps)
            assert all(sympy.isprime(p) for p in ps), n
        else:
            assert sympy.isprime(abs(n)) or abs(n) < 2


# -- univariate polynomials ------------------------------------------------------------------

def expanded(s):
    """The text of expand(s)."""
    return tx(R.MODS['norm'].normal(nd(s), 1))


@pytest.mark.parametrize('src, text', [
    ('x', 'x'), ('x^2', 'x^2'), ('2*x', '2*x'), ('-x-1', '-x-1'), ('x^2-2', 'x^2-2'),
    ('-x^2+1', '-(x-1)*(x+1)'), ('12*x^2-12', '12*(x-1)*(x+1)'), ('(x+1)^3', '(x+1)^3'),
    ('x^3-3*x^2+3*x-1', '(x-1)^3'), ('x^4-2*x^2+1', '(x-1)^2*(x+1)^2'),
    ('x^2+x+1/4', '(2*x+1)^2/4'), ('x^2/4-1', '(x-2)*(x+2)/4'),
    ('x^12-5*x^6+6', '(x^6-2)*(x^6-3)'), ('x^4+x^2+1', '(x^2-x+1)*(x^2+x+1)'),
    ('x^10+x^5+1', '(x^2+x+1)*(x^8-x^7+x^5-x^4+x^3-x+1)'), ('x^4-10*x^2+1', 'x^4-10*x^2+1'),
    ('x^6+1', '(x^2+1)*(x^4-x^2+1)'), ('x^5+32', '(x+2)*(x^4-2*x^3+4*x^2-8*x+16)'),
    ('16*x^4-81', '(2*x-3)*(2*x+3)*(4*x^2+9)'), ('x^6-8', '(x^2-2)*(x^4+2*x^2+4)'),
    ('x^8+4', '(x^4-2*x^2+2)*(x^4+2*x^2+2)'), ('4*x^4+1', '(2*x^2-2*x+1)*(2*x^2+2*x+1)'),
    ('3*x^4+12', '3*(x^2-2*x+2)*(x^2+2*x+2)'),
    ('x^3-x', 'x*(x-1)*(x+1)'), ('x^7-x^5', 'x^5*(x-1)*(x+1)'),
    ('(x^3+2*x+5)*(x^3-x+7)', '(x^3-x+7)*(x^3+2*x+5)'),
    ('(x^2+3)^2*(x-2)^3*(2*x+1)', '(x-2)^3*(2*x+1)*(x^2+3)^2'),
])
def test_univariate(src, text):
    check(expanded(src), text, complete=1)


def rpoly(r, deg, cmax):
    while True:
        p = [r.randint(-cmax, cmax) for i in range(deg + 1)]
        if p[-1]:
            return p


def ptext(p, v='x'):
    out = []
    for i in range(len(p) - 1, -1, -1):
        if p[i]:
            out.append('(%d)*%s^%d' % (p[i], v, i))
    return '+'.join(out) or '0'


@pytest.mark.parametrize('seed', seeds(1, 6))
def test_random_univariate_products(seed):
    """Random products of small factors (degrees 1-4, multiplicities 1-2): the factorization
    multiplies back exactly (FACTBUG == 0) and, when COMPLETE, its factor degrees are
    SymPy's over Q. Most of these are complete."""
    r = random.Random(seed)
    done = 0
    tried = 0
    for k in range(25):
        f = [1]
        for j in range(r.randint(1, 3)):
            f = PO.pmul(f, PO.ppow(rpoly(r, r.randint(1, 4), 6), r.randint(1, 2)))
        if len(f) > 13:
            continue
        check(ptext(f))
        done += FA.COMPLETE[0]
        tried += 1
    assert done >= tried * 2 // 3


def test_ufac_against_sympy():
    """ufac on dense lists: exactly the factor lists of sympy.factor_list (primitive, lc > 0)
    whenever ufac says complete."""
    r = random.Random(5)
    for k in range(150):
        f = [1]
        for j in range(r.randint(1, 3)):
            f = PO.pmul(f, PO.ppow(rpoly(r, r.randint(1, 3), 9), r.randint(1, 3)))
        c, fs, comp = FB.ufac(f)
        g = [c]
        for h, m in fs:
            assert h[-1] > 0 and PO.pcont(h) == 1 and len(h) > 1
            g = PO.pmul(g, PO.ppow(h, m))
        assert g == f
        if comp:
            ours = sorted((tuple(h), m) for h, m in fs)
            sp = sympy.factor_list(sympy.Poly(list(reversed(f)), X))
            theirs = sorted((tuple(int(a) for a in reversed(b.all_coeffs())), m)
                            for b, m in sp[1])
            assert ours == theirs, f


# -- binomials: cyclotomic, Sophie Germain, Capelli ------------------------------------------

def test_binomials_against_sympy():
    """a*x^n + b for n <= 12: binom's split multiplies back, and (None, 1) (Capelli) means
    that SymPy finds no factor either."""
    for n in range(2, 13):
        for a, b in ((1, -1), (1, 1), (1, -4), (1, 4), (4, 1), (8, -27), (1, -64), (1, 64),
                     (16, -81), (2, 1), (3, -2), (1, 9), (81, 4), (1, -2), (4, 81)):
            g = [b] + [0] * (n - 1) + [a]
            fs, ok = FD.binom(g)
            sp = sympy.factor_list(sympy.Poly(list(reversed(g)), X))[1]
            if fs is None:
                assert ok == 1 and len(sp) == 1 and sp[0][1] == 1, (a, b, n)
            else:
                p = [1]
                for h in fs:
                    p = PO.pmul(p, h)
                assert p == g, (a, b, n)


def test_cyclotomic_large_and_capped(monkeypatch):
    check('x^100-1', complete=1)
    check('x^30-1', '(x-1)*(x+1)*(x^2-x+1)*(x^2+x+1)*(x^4-x^3+x^2-x+1)*(x^4+x^3+x^2+x+1)'
          '*(x^8-x^7+x^5-x^4+x^3-x+1)*(x^8+x^7-x^5-x^4-x^3+x+1)', complete=1)
    monkeypatch.setattr(FB, 'CYMAX', 8)                 # x^11-1 cannot use Phi_11 now:
    t = check('x^11-1', complete=1)                     # x = 1, then Kronecker proves Phi_11
    assert '(x-1)' in parts(t)[0]
    monkeypatch.setattr(FB, 'KBUD', 10)
    t = check('x^11-1', complete=0)                     # ... unless its budget is too small
    assert '(x-1)' in parts(t)[0]


# -- multivariate and kernels ------------------------------------------------------------------

@pytest.mark.parametrize('src, text', [
    ('x^3+y^3', '(x+y)*(x^2-x*y+y^2)'), ('x^4-y^4', '(x-y)*(x+y)*(x^2+y^2)'),
    ('x^8-y^8', '(x-y)*(x+y)*(x^2+y^2)*(x^4+y^4)'), ('a*x^2-a', 'a*(x-1)*(x+1)'),
    ('x*y+x+y+1', '(x+1)*(y+1)'), ('x^2+2*x*y+y^2-1', '(x+y-1)*(x+y+1)'),
    ('x^2*y^2-1', '(x*y-1)*(x*y+1)'), ('x^2+x*y+x*z+y*z', '(x+y)*(x+z)'),
    ('x^3*y-x*y^3', 'x*y*(x-y)*(x+y)'), ('x^2+y^2', 'x^2+y^2'), ('x*y', 'x*y'),
    ('x^2+2*x*y+y^2', '(x+y)^2'), ('4*x^2-9*y^2', '(2*x-3*y)*(2*x+3*y)'),
    ('x^2*y+x*y^2+x+y', '(x+y)*(x*y+1)'),
])
def test_multivariate(src, text):
    check(src, text, complete=1)


@pytest.mark.parametrize('seed', seeds(1, 4))
def test_random_bivariate_products(seed):
    r = random.Random(100 + seed)
    for k in range(12):
        fs = []
        for j in range(r.randint(2, 3)):
            ts = []
            for t in range(r.randint(2, 3)):
                ts.append('(%d)*x^%d*y^%d' % (r.choice((-3, -2, -1, 1, 2, 3)), r.randint(0, 2),
                                             r.randint(0, 2)))
            fs.append('(' + '+'.join(ts) + ')')
        src = expanded('*'.join(fs))
        if K.N[nd(src)][0] == K.NUM:
            continue
        check(src)


@pytest.mark.parametrize('src, text', [
    ('sin(x)^2-cos(x)^2', '(sin(x)-cos(x))*(sin(x)+cos(x))'),
    ('x^2*sin(x)+2*x*sin(x)+sin(x)', '(x+1)^2*sin(x)'), ('x*e^x+e^x', 'e^x*(x+1)'),
    ('pi*x+pi', 'pi*(x+1)'), ('sqrt(2)*x+sqrt(2)', 'sqrt(2)*(x+1)'),
    ('x^(1/2)+x^(3/2)', 'sqrt(x)*(x+1)'), ('ln(x)^2-1', '(ln(x)-1)*(ln(x)+1)'),
])
def test_kernels(src, text):
    check(src, text)


@pytest.mark.parametrize('src, text', [
    ('(x^2-1)/(x^2+2*x+1)', '(x-1)/(x+1)'), ('1/(x^3-x)', '1/(x*(x-1)*(x+1))'),
    ('(x^2-1)/(4*x^2-9)', '(x-1)*(x+1)/((2*x-3)*(2*x+3))'), ('3/(2*x+4)', '3/(2*(x+2))'),
    ('(x^2-y^2)/(x*y)', '(x-y)*(x+y)/(x*y)'), ('x/(x^2-1)+1/(x+1)', '(2*x-1)/((x-1)*(x+1))'),
])
def test_rational_functions(src, text):
    check(src, text, complete=1)


def test_left_alone():
    """Gaussian coefficients, floats in inert mode, oo: the input (or its normal form)
    comes back."""
    for src in ('i*x+i', 'x^2+1+i'):
        assert same_value(to_sympy(fac(src)), sympy.sympify(src.replace('^', '**'),
                                                           locals=SYMS))
    e = nd('x^2-0.25')                                  # inert: the float stays
    assert drive(R.MODS['fact'].g_factor((e,), [0, None, 0, 1])) == e
    assert fac('x+oo') == nd('x+oo')


# -- the command: approx mode, lists, relations, the variable ----------------------------------

def test_approx_mode_monic_factors():
    r = go('factor(x^2-0.25)')
    assert r[0] == 'ans' and parts(r[1]) == parts('(x-0.5)*(x+0.5)')
    r = go('factor(2*x^2-0.5)')
    assert r[0] == 'ans' and parts(r[1]) == parts('2.0*(x-0.5)*(x+0.5)')


def test_lists_relations_and_the_variable():
    assert ans('factor([x^2-1,x^3-1,12])') == '[(x-1)*(x+1),(x-1)*(x^2+x+1),2^2*3]'
    assert ans('factor(x^2-1=0)') == '(x-1)*(x+1)=0'
    assert ans('factor(x^2-1,x)') == '(x-1)*(x+1)'
    ctx = [0, None, 0, 0]
    x = nd('x')
    drive(R.MODS['fact'].g_factor((nd('x^2-y^2'), x), ctx))
    assert ctx[P.X_MV] == x
    r = go('factor(x^2-1,2)')
    assert r[:2] == ('msg', FA.M_ARG)
    r = go('factor(x^2-1,x,y)')
    assert r[0] == 'msg'


def test_round_trip():
    """The text of a factored result re-parses (inert) to the same node (12.5); a HOLD to its
    value."""
    for src in ('x^4+4', 'x^6-1', '6*x^3-11*x^2+6*x-1', 'x^2-y^2', '2*x^3-4*x^2-6*x',
                'x^2+x+1/4', '(x^2-1)/(4*x^2-9)', '-x^2+1', 'x^2*sin(x)+2*x*sin(x)+sin(x)',
                '12*x^2-12', 'x^3*y-x*y^3'):
        e = fac(src)
        assert nd(tx(e)) == e, src
    e = fac('360')
    assert nd(tx(e)) == K.num(360)


@pytest.mark.strict_depth
def test_commands_in_strict_depth_mode():
    for s in ('factor(x^4+4)', 'factor(x^2-y^2)', 'factor(360)', 'factor((x^2-1)/(x^3-x))',
              'factor(x^2+2*x*y+y^2-1)', 'factor(x^5-x+1)', 'factor(x^2-0.25)'):
        assert go(s)[0] == 'ans'


# -- budgets -----------------------------------------------------------------------------------

def test_budget_kronecker_partial_and_honest():
    """Two quintics multiplied: the quintic search needs far more than KBUD odometer steps.
    The answer is the (correct) unfactored product, COMPLETE is 0, the time is bounded."""
    f = PO.pmul([11, -3, 0, 0, 2, 1], [13, 1, -7, 0, 0, 1])
    t0 = time.perf_counter()
    c, fs, comp = FB.ufac(f)
    dt = time.perf_counter() - t0
    assert (c, fs, comp) == (1, [(f, 1)], False)
    assert FB.STEPS[0] > FB.KBUD and dt < 2.0
    check(ptext(f), complete=0)


def test_budget_small_kbud(monkeypatch):
    """With a tiny budget even a quartic's quadratic search stops: nothing is claimed
    (COMPLETE 0) and the product stays exact."""
    src = expanded('(x^2+3*x+5)*(x^2-7*x+11)')
    monkeypatch.setattr(FB, 'KBUD', 2)
    check(src, src, complete=0)
    monkeypatch.setattr(FB, 'KBUD', 6000)
    check(src, '(x^2-7*x+11)*(x^2+3*x+5)', complete=1)


def test_budget_recombination_and_image_cap(monkeypatch):
    monkeypatch.setattr(FB, 'MBUD', 0)
    check('x^2+2*x*y+y^2-1', 'x^2+2*x*y+y^2-1', complete=0)
    monkeypatch.setattr(FB, 'MBUD', 2000)
    monkeypatch.setattr(FB, 'FKMAX', 4)
    check('x^2+2*x*y+y^2-1', 'x^2+2*x*y+y^2-1', complete=0)


def test_kron_unit():
    f = PO.pmul([5, 3, 1], [11, -7, 1])                 # (x^2+3x+5)(x^2-7x+11)
    FB.STEPS[0] = 0
    h, ok = FB.kron(f, 2)
    assert ok and h in ([5, 3, 1], [11, -7, 1])
    FB.STEPS[0] = 0
    assert FB.kron([1, -1, 0, 0, 0, 1], 2) == (None, True)          # x^5-x+1
    assert FB.kron([-6, 1, 1], 1) == ([-2, 1], True)                 # a root at a sample point


def test_cancel_polls(monkeypatch):
    n = [0]

    def esc():
        n[0] += 1
        return n[0] > 3
    monkeypatch.setattr(K, 'ESC', esc)
    with pytest.raises(K.Cancel):
        FB.ufac(PO.pmul([11, -3, 0, 0, 2, 1], [13, 1, -7, 0, 0, 1]))
    n[0] = 0
    with pytest.raises(K.Cancel):
        FD.ifactor((K.NUM, 1000003 * 1000033, 0, 1))
    n[0] = -10 ** 9
    assert go('factor(x^4+4)')[0] == 'ans'
    n[0] = 0
    assert go('factor(' + ptext(PO.pmul([11, -3, 0, 0, 2, 1], [13, 1, -7, 0, 0, 1])) + ')')[:2] \
        == ('msg', 'Interrupted')


# -- the product check ---------------------------------------------------------------------------

def test_product_check_catches_a_bad_factorization(monkeypatch):
    """A spurious factor from ufac: in several variables the recombination tests divisibility
    and ignores it; in one variable the product check catches it (FACTBUG) and P comes back
    unfactored, with COMPLETE 0."""
    real = FB.ufac

    def spurious(f):
        c, fs, comp = real(f)
        return c, ([([1, 1], 1)] if len(f) > 1 else []) + fs, comp      # x+1: not a factor
    monkeypatch.setattr(FB, 'ufac', spurious)
    check('x^2+2*x*y+y^2-1', '(x+y-1)*(x+y+1)')
    assert FB.FACTBUG == 0
    e = fac('x^2-4')
    assert tx(e) == 'x^2-4' and FB.FACTBUG == 1 and FA.COMPLETE[0] == 0
    FB.FACTBUG = 0


# -- numeric real roots ------------------------------------------------------------------------

@pytest.mark.parametrize('seed', seeds(1, 3))
def test_nroots_against_sympy(seed):
    r = random.Random(3 + seed)
    for k in range(20):
        f = [1]
        for j in range(r.randint(1, 4)):
            f = PO.pmul(f, rpoly(r, r.randint(1, 3), 9))
        g = [1]
        for h, m in FB.ufac(f)[1]:
            g = PO.pmul(g, h)                           # square-free
        if len(g) < 2:
            continue
        ours = FD.nroots(g)
        theirs = [float(v) for v in sympy.Poly(list(reversed(g)), X).real_roots()]
        assert len(ours) == len(theirs), g
        for a, b in zip(ours, theirs):
            assert abs(a - b) <= 1e-9 * max(1.0, abs(b)), (g, ours, theirs)


def test_nroots_edges():
    assert FD.nroots([-2, 0, 1]) == pytest.approx([-2 ** 0.5, 2 ** 0.5], rel=1e-14)
    assert FD.nroots([1, 0, 1]) == []
    assert FD.nroots([0, 1]) == [0.0]
    assert FD.nroots([-1, 0, 0, 1]) == pytest.approx([1.0])
    assert FD.nroots([1] + [0] * 99 + [10 ** 400]) == []            # floats overflow


def test_incomplete_divisors_use_numeric_roots(monkeypatch):
    """A root whose numerator has a prime factor beyond trial division: ratroots still finds
    it (complete False); with ratroots forced incomplete and empty, the numeric real roots
    rounded to p/q find it."""
    p = 1000000007
    f = PO.pmul([-p, 3], [1, 0, 1])                     # (3x - p)(x^2+1)
    c, fs, comp = FB.ufac(f)
    assert sorted(h for h, m in fs) == [[-p, 3], [1, 0, 1]]
    PB = R.MODS['polyb']
    monkeypatch.setattr(PB, 'ratroots', lambda a: ([], a, False))
    c, fs, comp = FB.ufac(PO.pmul([-7, 3], [1, 0, 1]))
    assert sorted(h for h, m in fs) == [[-7, 3], [1, 0, 1]]


# -- the module ----------------------------------------------------------------------------------

def test_registry_and_api():
    ent = R.CMDS['factor']
    assert ent[0] == 'fact' and ent[1] == 'g_factor' and ent[2:4] == (1, 2)
    assert R.PARTS['fact'][:4] == ('fact', 'factb', 'factc', 'factd')
    assert R.MODS['fact'] is FA and R.MODS['factb'] is FB
    assert FB.KBUD > 0 and FB.MBUD > 0 and FA.TDIV == 10 ** 6


def code_lines(name):
    sys.path.insert(0, os.path.join(ROOT, 'build'))
    try:
        import bundle
    finally:
        sys.path.pop(0)
    if name.startswith('CV'):
        name = next(row[0] for row in bundle.load_manifest().MODULES if row[1] == name)
    with open(os.path.join(ROOT, 'src', name + '.py'), encoding='utf-8') as fh:
        return len(bundle.minify(fh.read(), name).lines)


def test_parts_fit_lazymax():
    for key in R.PARTS['fact']:
        name = R.DEV[key]
        assert code_lines(name) <= LAZYMAX, name


def test_parts_size_is_bounded():
    keys = [key for key in R.PARTS['fact'] if key[:4] == 'fact']    # forms shares the pack
    assert sum(code_lines(R.DEV[key]) for key in keys) <= 520
