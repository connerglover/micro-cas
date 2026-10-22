"""T1.12: solve (DESIGN 11.2; alg 2.10, D2, D3).

Acceptance (section 21.4): the alg section 6 seeds 2.10 (x^2-5x+6, x^2+1 with no real root,
2^x=8 -> 3, sin x = 1/2, sqrt(x+3)=x-3 -> 6 with the check rejecting 1, ln x = 2, a 3x3 linear
system); linear systems; root checks; the empty-list and TRUE sentinels; symbolic coefficients;
one-period trig (D2) in both angle modes; guards with radicals.

The modules under test are the real CVSOLVE family (solve.py, solveb.py, solvec.py) with the
real CVPOLY, CVNORM, CVRULE, CVIDENT and CVFACT families, loaded through run.need; end-to-end
cases go through run.go with the real parser and printer. Roots are checked against SymPy
(solveset over the reals, numerically) and by substitution.
"""
import math
import os
import random
import sys
import types

import pytest
import sympy

import alg as A
import node as K
import parse as P
import printer as PR
import run as R

import solve as SO
import solveb as SB
import solvec as SC
from test_node import arena  # noqa: F401 - the debug-arena fixture (DESIGN 20.4)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LAZYMAX = 150

FRESH = (('ANS', None), ('HIST', list), ('VARS', dict), ('FUNCS', dict), ('MODS', dict),
         ('LOADED', list), ('USE', dict), ('PINNED', list), ('LIVE', dict), ('NEEDED', list))

X = sympy.Symbol('x', real=True)


@pytest.fixture(autouse=True)
def sess(monkeypatch):
    """A fresh session and loader with the real lazy modules; P.SESS = R; the SOLVE closure
    loaded (R.MODS), so that direct calls into the solve family work."""
    for name, make in FRESH:
        monkeypatch.setattr(R, name, make() if make is not None else None)
    monkeypatch.setattr(R, 'SET', {'deg': 0})
    monkeypatch.setattr(R, 'CLOCK', [0])
    monkeypatch.setattr(P, 'SESS', R)
    R.need('solve')
    R.MODS['factb'].FACTBUG = 0
    yield
    assert R.MODS['factb'].FACTBUG == 0


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


def go(s, deg=0):
    R.SET['deg'] = deg
    return R.go(('eval', s))


def ans(s, deg=0):
    r = go(s, deg)
    assert r[0] == 'ans', (s, r)
    return r[1]


def msg(s, deg=0):
    r = go(s, deg)
    assert r[0] == 'msg', (s, r)
    return r[1]


def solve_node(s, v=None, deg=0):
    """solve(s, [v]) through g_solve on the node of s: the result node (or None)."""
    args = (nd(s, deg),) if v is None else (nd(s, deg), nd(v, deg))
    return drive(SO.g_solve(args, [deg, None, 0, 0]))


def roots(s, x='x', deg=0):
    """The checked roots (a tuple of ids, TRUE or None) of the expression s = 0."""
    return drive(SO.g_roots(nd(s), K.sym(x), deg))


def tx(e, deg=0):
    return PR.text(e, (deg, None, 0, 0))


FN = {K.SIN: sympy.sin, K.COS: sympy.cos, K.TAN: sympy.tan, K.LN: sympy.log,
      K.ABS: sympy.Abs, K.ATAN: sympy.atan, K.ASIN: sympy.asin, K.ACOS: sympy.acos,
      K.SEC: sympy.sec, K.CSC: sympy.csc, K.COT: sympy.cot}


def to_sympy(n):
    """The SymPy value of node n (symbols real; odd-denominator powers are real roots)."""
    vals = {}
    for i in A.postorder(n):
        t = K.N[i]
        op = t[0]
        if op == K.NUM:
            v = sympy.Rational(t[1], t[3]) + sympy.I * sympy.Rational(t[2], t[3])
        elif op == K.FLT:
            v = sympy.Float(t[1], 30) + sympy.I * sympy.Float(t[2], 30)
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
        elif K.EQ <= op <= K.LE:
            v = (op, vals[t[1]], vals[t[2]])
        else:
            raise ValueError('no SymPy value for %r' % (t,))
        vals[i] = v
    return vals[n]


def values(r):
    """The SymPy values of a solve result node (an LST of x=r), in order."""
    t = K.N[r]
    assert t[0] == K.LST, tx(r)
    out = []
    for c in t[1:]:
        q = K.N[c]
        assert q[0] == K.EQ, tx(r)
        out.append(to_sympy(q[2]))
    return out


def fl(v):
    return complex(sympy.N(v, 30))


def same_set(ours, theirs, tol=1e-9):
    """Two lists of numbers are the same set (numerically), ours ascending."""
    a = [fl(v) for v in ours]
    b = sorted((fl(v) for v in theirs), key=lambda z: (z.real, z.imag))
    if len(a) != len(b):
        return False
    for u, w in zip(a, b):
        if abs(u - w) > tol * (1 + abs(w)):
            return False
    for u, w in zip(a, a[1:]):
        assert u.real <= w.real + 1e-12, 'roots not ascending: %r' % a
    return True


def sympy_real_roots(expr):
    s = sympy.solveset(expr, X, domain=sympy.S.Reals)
    if s == sympy.S.EmptySet:
        return []
    assert isinstance(s, sympy.FiniteSet), s
    return list(s)


def substitutes_to_zero(f, r):
    """f (SymPy, in X) vanishes at r: exactly, else at 30 digits."""
    d = f.subs(X, r)
    if sympy.simplify(d) == 0:
        return True
    return abs(complex(sympy.N(d, 30))) < 1e-20


# -- acceptance: alg section 6 seeds 2.10 ---------------------------------------------------------

def test_seed_quadratic():
    assert ans('solve(x^2-5x+6=0)') == 'x=2,x=3'
    assert ans('solve(x^2-5x+6,x)') == 'x=2,x=3'
    assert ans('x^2-5x+6=0') == 'x=2,x=3'        # 7.9 rule 4: a lone equation
    assert same_set(values(solve_node('x^2-5*x+6')), [2, 3])
    K.reset()                       # direct nodes after a command: leave the table empty


def test_seed_no_real_root():
    """D3: real mode, x^2+1 = 0 has no solution (the empty list, a sentinel)."""
    r = solve_node('x^2+1')
    assert K.N[r] == (K.LST,)
    assert msg('solve(x^2+1=0)') == 'no solution'
    assert msg('x^2+1=0') == 'no solution'


def test_seed_exponential():
    assert ans('solve(2^x=8,x)') == 'x=3'
    assert ans('2^x=8') == 'x=3'
    assert ans('4^x=2') == 'x=1/2'
    assert ans('e^x=5') == 'x=ln(5)'
    assert ans('2^(x+1)=8') == 'x=2'


def test_seed_sin_half():
    assert ans('solve(sin(x)=1/2,x)') == 'x=pi/6,x=5*pi/6'


def test_seed_radical_check_rejects_one():
    """sqrt(x+3) = x-3: squaring gives x^2-7x+6 = 0 (1 and 6); the check rejects 1."""
    f = nd('sqrt(x+3)-(x-3)')
    x = K.sym('x')
    cand = drive(SO.g_eq(f, x, 0, 0))
    assert sorted(K.N[c][1] for c in cand if K.N[c][0] == K.NUM) == [1, 6]
    assert ans('sqrt(x+3)=x-3') == 'x=6'


def test_seed_ln():
    assert ans('ln(x)=2') == 'x=e^2'
    assert ans('log(x)=2') == 'x=100'
    assert ans('ln(x)=-1') == 'x=1/e'


def test_seed_linear_system_3x3():
    assert ans('solve([x+y+z=6,x-y=0,2x-z=1],[x,y,z])') == 'x=7/4,y=7/4,z=5/2'
    assert ans('solve([2x+y-z=8,-3x-y+2z=-11,-2x+y+2z=-3],[x,y,z])') == 'x=2,y=3,z=-1'


# -- the sentinels and messages (10.5, 8.2) -------------------------------------------------------

def test_true_and_false_sentinels():
    assert msg('x+1=x+1') == 'every x is a solution'
    assert msg('x-x=1') == 'no solution'
    assert msg('solve(0)') == 'every x is a solution'
    assert msg('solve(y-y,y)') == 'every y is a solution'
    assert msg('solve(5)') == 'no solution'
    assert solve_node('x+1=x+1') == K.TRUE
    assert K.N[solve_node('x-x=1')] == (K.LST,)
    K.reset()
    assert msg('solve((x-1)^2-x^2+2x-1=0)') == 'every x is a solution'


def test_identity_after_trig_rewrite():
    assert msg('solve(sin(x)^2+cos(x)^2=1)') == 'every x is a solution'


def test_no_solution_cases():
    for s in ('solve(sin(x)=2)', 'solve(sqrt(x)=-1)', 'solve(exp(x)=0)', 'solve(x/(x-1)=1)',
              'solve(sqrt(x^2+1)=x)', 'solve(x^4+1=0)', 'solve(abs(x)=-1)', 'solve(e^x=-2)',
              'solve(cos(x)=-3/2)', 'solve(x^2+x+1=0)'):
        assert msg(s) == 'no solution', s


def test_records_are_solutions():
    r = go('solve(x^2=4)')
    assert r[0] == 'ans' and r[1] == 'x=-2,x=2' and r[3] & R.F_SOLN
    assert R.ANS == 'x=-2,x=2'


# -- root checks: denominators, domains, extraneous roots --------------------------------------

def test_denominator_roots_are_dropped():
    assert msg('(x^2-1)/(x-1)=2') == 'no solution'
    assert ans('(x^2-1)/(x-1)=0') == 'x=-1'
    assert ans('1/(x-1)+1/(x+1)=0') == 'x=0'
    assert ans('1/x=2') == 'x=1/2'
    assert msg('1/x=0') == 'no solution'


def test_domain_roots_are_dropped():
    assert ans('x*ln(x)=0') == 'x=1'           # x = 0: ln(0) is undefined
    assert ans('x^2*ln(x)=0') == 'x=1'


def test_extraneous_radical_roots():
    assert ans('x-3*sqrt(x)+2=0') == 'x=1,x=4'
    assert ans('sqrt(x)+sqrt(x+1)=3') == 'x=16/9'
    assert ans('sqrt(2x+1)=x-1') == 'x=4'       # 0 is extraneous
    assert msg('sqrt(x)=-x-1') == 'no solution'
    assert ans('sqrt(x)=3') == 'x=9'
    assert ans('x^(1/3)=2') == 'x=8'
    assert ans('x^(1/3)=-2') == 'x=-8'        # real odd roots (6.2)
    assert ans('(x+1)^(2/3)=4') == 'x=-9,x=7'


def test_check_uses_g_iszero_not_text():
    """A root whose substitution is zero only after normal/ZBASIS is accepted; one that is
    not zero is rejected."""
    x = K.sym('x')
    f = nd('x-sqrt(2)')
    assert drive(R.MODS['solved'].g_ok((f,), (), (x,), (nd('sqrt(2)'),))) == 1
    assert drive(R.MODS['solved'].g_ok((f,), (), (x,), (nd('sqrt(3)'),))) == 0
    g = nd('sin(x)^2+cos(x)^2-1+x-2')
    assert drive(R.MODS['solved'].g_ok((g,), (), (x,), (nd('2'),))) == 1
    # a denominator that vanishes at the root
    assert drive(R.MODS['solved'].g_ok((nd('x-1'),), (nd('x^2-1'),), (x,), (nd('1'),))) == 0
    # an undefined substitution
    assert drive(R.MODS['solved'].g_ok((nd('ln(x)'),), (), (x,), (nd('0'),))) == 0


def test_abs_equations():
    assert ans('abs(x-1)=2') == 'x=-1,x=3'
    assert ans('abs(x-1)=abs(x+1)') == 'x=0'
    assert ans('abs(x-1)+abs(x+1)=4') == 'x=-2,x=2'
    assert msg('abs(x)=x-2') == 'no solution'
    assert ans('abs(2x-1)=x') == 'x=1/3,x=1'


# -- polynomials -----------------------------------------------------------------------------

def test_polynomial_cases():
    cases = {
        'x^3=8': 'x=2',
        'x^3+1=0': 'x=-1',
        '(x-1)^2=0': 'x=1',
        'x^2=x': 'x=0,x=1',
        'x^4-5x^2+4=0': 'x=-2,x=-1,x=1,x=2',
        'x^4-2=0': 'x=-2^(1/4),x=2^(1/4)',
        'x^2-2=0': 'x=-sqrt(2),x=sqrt(2)',
        'x^2+x-1=0': 'x=-(sqrt(5)+1)/2,x=(sqrt(5)-1)/2',
        'x^6-1=0': 'x=-1,x=1',
        '6x^3-11x^2+6x-1=0': 'x=1/3,x=1/2,x=1',
        '2x+3=0': 'x=-3/2',
        'x=(-x/2)^2': 'x=0,x=4',
        'x^4-10x^2+1=0': 'x=-sqrt(2)-sqrt(3),x=sqrt(2)-sqrt(3),x=sqrt(3)-sqrt(2),'
                         'x=sqrt(2)+sqrt(3)',
    }
    for s, want in cases.items():
        assert ans(s) == want, s


def test_numeric_roots_are_floats():
    r = go('x^5-x+1=0')
    assert r[0] == 'ans' and r[3] & R.F_APPROX, r
    want = sorted(float(v) for v in sympy.Poly(X ** 5 - X + 1).real_roots())
    got = [float(s.split('=')[1]) for s in r[1].split(',')]
    assert len(got) == len(want) and all(abs(a - b) < 1e-12 for a, b in zip(got, want))
    r = go('x^3-2x-5=0')
    assert r[0] == 'ans' and abs(float(r[1][2:]) - 2.0945514815423265) < 1e-12


def test_floats_in_the_input():
    """6.3: decimals are solved exactly, the answer approximated."""
    assert ans('x^2=0.25') == 'x=-0.5,x=0.5'
    assert ans('2.5x=5') == 'x=2.0'


@pytest.mark.parametrize('seed', range(12))
def test_random_polynomials_against_sympy(seed):
    """Products of rational linear factors and random quadratics (some irreducible, some
    with a negative discriminant): the root set equals sympy.solveset over the reals, and
    every root substitutes to zero."""
    rnd = random.Random(seed)
    f = sympy.Integer(rnd.choice([1, 2, -3]))
    for k in range(rnd.randint(1, 3)):
        if rnd.random() < 0.5:
            f *= rnd.randint(1, 4) * X - rnd.randint(-6, 6)
        else:
            f *= X ** 2 + rnd.randint(-5, 5) * X + rnd.randint(-6, 6)
    f = sympy.expand(f)
    s = str(f).replace('**', '^')
    r = solve_node(s + '=0')
    want = sympy_real_roots(f)
    if not want:
        assert K.N[r] == (K.LST,), (s, tx(r))
        return
    got = values(r)
    assert same_set(got, want), (s, tx(r), want)
    for v in got:
        assert substitutes_to_zero(f, v), (s, v)


@pytest.mark.parametrize('seed', range(6))
def test_random_biquadratics_against_sympy(seed):
    rnd = random.Random(100 + seed)
    a = rnd.randint(-6, 6)
    b = rnd.randint(-9, 9)
    f = X ** 4 + a * X ** 2 + b
    s = str(f).replace('**', '^')
    r = solve_node(s)
    want = sympy_real_roots(f)
    got = values(r) if K.N[r] != (K.LST,) else []
    assert same_set(got, want), (s, tx(r), want)


# -- symbolic coefficients (11.2: the generic solution, as giac) ----------------------------------

def test_symbolic_coefficients():
    assert ans('solve(x^2+a=0,x)') == 'x=-sqrt(-a),x=sqrt(-a)'
    assert ans('solve(a*x=b,x)') == 'x=b/a'
    assert ans('solve(x^2+a=0)') == 'x=-sqrt(-a),x=sqrt(-a)'      # x by default
    assert ans('solve(a*x-1=0,a)') == 'a=1/x'
    assert ans('solve(x^3+a*x=0,x)') == 'x=0,x=-sqrt(-a),x=sqrt(-a)'
    assert ans('solve(x^2-2x+1-a,x)') == 'x=1-sqrt(a),x=sqrt(a)+1'


def test_symbolic_quadratic_formula_against_sympy():
    a, b, c = sympy.symbols('a b c', real=True)
    r = solve_node('a*x^2+b*x+c=0', 'x')
    got = values(r)
    assert len(got) == 2
    for v in got:
        assert sympy.simplify(sympy.expand(a * v ** 2 + b * v + c)) == 0, v


def test_symbolic_kernels_are_generic():
    """Guards with symbols hold (the generic solution): sin(x) = a, e^x = a, ln(x) = a."""
    assert ans('solve(sin(x)=a,x)') == 'x=asin(a),x=pi-asin(a)'
    assert ans('solve(e^x=a,x)') == 'x=ln(a)'
    assert ans('solve(ln(x)=a,x)') == 'x=e^a'
    assert ans('solve(sqrt(x)=a,x)') == 'x=a^2'
    assert ans('solve(sin(x+y)=1/2,x)') == 'x=pi/6-y,x=5*pi/6-y'


def test_cannot_solve():
    assert msg('solve(x^5+a*x+1=0,x)') == 'cannot solve'
    assert msg('solve(x^2<4)') == 'cannot solve'
    assert msg('solve(floor(x)=2)') == 'cannot solve'


def test_invalid_variable():
    assert msg('solve(x^2=4,2)') == 'invalid argument'
    assert msg('solve(x^2=4,x+1)') == 'invalid argument'


# -- trig: one period (D2), both angle modes -------------------------------------------------------

TRIG_RAD = {
    'sin(x)=1/2': 'x=pi/6,x=5*pi/6',
    'sin(x)=-1/2': 'x=7*pi/6,x=11*pi/6',
    'sin(x)=0': 'x=0,x=pi',
    'sin(x)=1': 'x=pi/2',
    'cos(x)=0': 'x=pi/2,x=3*pi/2',
    'cos(x)=1': 'x=0',
    'cos(x)=-1': 'x=pi',
    'cos(x)=1/2': 'x=pi/3,x=5*pi/3',
    'tan(x)=1': 'x=pi/4,x=5*pi/4',
    'tan(x)=0': 'x=0,x=pi',
    'sec(x)=2': 'x=pi/3,x=5*pi/3',
    'csc(x)=2': 'x=pi/6,x=5*pi/6',
    'cot(x)=1': 'x=pi/4,x=5*pi/4',
    'cot(x)=0': 'x=pi/2,x=3*pi/2',
    'sin(2x)=1/2': 'x=pi/12,x=5*pi/12,x=13*pi/12,x=17*pi/12',
    'sin(3x)=0': 'x=0,x=pi/3,x=2*pi/3,x=pi,x=4*pi/3,x=5*pi/3',
    'sin(x/2)=1/2': 'x=pi/3,x=5*pi/3',
    'cos(x-pi/3)=1/2': 'x=0,x=2*pi/3',
    'sin(-x)=1/2': 'x=7*pi/6,x=11*pi/6',
    'tan(x)^2=3': 'x=pi/3,x=2*pi/3,x=4*pi/3,x=5*pi/3',
    'sin(x)^2=1/4': 'x=pi/6,x=5*pi/6,x=7*pi/6,x=11*pi/6',
    '2sin(x)^2-sin(x)-1=0': 'x=pi/2,x=7*pi/6,x=11*pi/6',
    'sin(x)+cos(x)=1': 'x=0,x=pi/2',
    'sin(x)=cos(x)': 'x=pi/4,x=5*pi/4',
    'sin(x)^2+cos(x)=1': 'x=0,x=pi/2,x=3*pi/2',
    'tan(x)=sin(x)': 'x=0,x=pi',
    'sin(x)*cos(x)=0': 'x=0,x=pi/2,x=pi,x=3*pi/2',
    'sin(x)+2*cos(x)=1': 'x=pi/2,x=2*pi-acos(4/5)',
    'sin(x)*cos(x)=1/4': 'x=pi/12,x=5*pi/12,x=13*pi/12,x=17*pi/12',
    '3*sin(x)+4*cos(x)=5': 'x=acos(4/5)',
    'sin(x)+sqrt(3)*cos(x)=1': 'x=pi/2,x=11*pi/6',
    '2*sin(x)*cos(x)=sin(x)': 'x=0,x=pi/3,x=pi,x=5*pi/3',
    'sin(x)^3+cos(x)^3=1': 'x=0,x=pi/2',
    'sin(x)+cos(x)=2': None,
}

TRIG_DEG = {
    'sin(x)=1/2': 'x=30,x=150',
    'sin(x)=-1/2': 'x=210,x=330',
    'cos(x)=1/2': 'x=60,x=300',
    'tan(x)=1': 'x=45,x=225',
    'sin(x+30)=1/2': 'x=0,x=120',
    'sin(2x)=0': 'x=0,x=90,x=180,x=270',
    'cos(x)=0': 'x=90,x=270',
    'sin(x)+cos(x)=1': 'x=0,x=90',
}


@pytest.mark.parametrize('s', sorted(TRIG_RAD))
def test_trig_one_period_radians(s):
    if TRIG_RAD[s] is None:
        assert msg(s) == 'no solution'
        return
    assert ans(s) == TRIG_RAD[s]
    r = solve_node(s)
    f = to_sympy(nd(s))
    g = f[1] - f[2] if isinstance(f, tuple) else f
    for v in values(r):
        assert 0 <= float(v) < 2 * math.pi + 1e-12
        assert abs(complex(sympy.N(g.subs(X, v), 30))) < 1e-20, (s, v)
    K.reset()


@pytest.mark.parametrize('s', sorted(TRIG_DEG))
def test_trig_one_period_degrees(s):
    assert ans(s, deg=1) == TRIG_DEG[s]
    r = solve_node(s, deg=1)
    for v in values(r):
        assert 0 <= float(v) < 360
    K.reset()


def test_trig_period_against_sympy():
    """sin(kx) = c in [0, 2pi): the same set as sympy.solveset on Interval.Ropen(0, 2pi)."""
    for k, c in ((1, '1/3'), (2, '-1'), (3, '1/2'), (4, '0'), (1, 'sqrt(3)/2')):
        s = 'sin(%d*x)=%s' % (k, c)
        r = solve_node(s)
        cs = sympy.sympify(c)
        want = sympy.solveset(sympy.sin(k * X) - cs, X, sympy.Interval.Ropen(0, 2 * sympy.pi))
        assert same_set(values(r), list(want)), (s, tx(r), want)


def test_trig_without_special_values():
    assert ans('sin(x)=1/3') == 'x=asin(1/3),x=pi-asin(1/3)'
    assert ans('cos(x)=1/3') == 'x=acos(1/3),x=2*pi-acos(1/3)'
    assert ans('sin(x)=1/3', deg=1) == 'x=asin(1/3),x=180-asin(1/3)'


def test_inverse_trig_kernels():
    assert ans('asin(x)=pi/6') == 'x=1/2'
    assert ans('atan(x)=pi/4') == 'x=1'
    assert ans('acos(x)=pi/3') == 'x=1/2'
    assert msg('asin(x)=2') == 'no solution'
    assert ans('asin(x)=30', deg=1) == 'x=1/2'


def test_too_many_solutions():
    assert ans('sin(12x)=0').count('x=') == 24
    assert msg('sin(13x)=0') == 'too many solutions'


# -- guards with radicals (9.2, 20.12) -------------------------------------------------------------

def test_guards_with_radicals():
    assert ans('solve(sin(x)=sqrt(2)/2)') == 'x=pi/4,x=3*pi/4'
    assert ans('cos(x)=sqrt(3)/2') == 'x=pi/6,x=11*pi/6'
    assert ans('cos(x)=(sqrt(6)-sqrt(2))/4') == 'x=5*pi/12,x=19*pi/12'
    assert msg('sin(x)=sqrt(3)') == 'no solution'           # sqrt(3) > 1
    assert msg('cos(x)=-sqrt(5)/2') == 'no solution'
    assert ans('sin(x)=(sqrt(5)-1)/4') == 'x=pi/10,x=9*pi/10'
    assert ans('sin(x)=sqrt(2)/2', deg=1) == 'x=45,x=135'


def test_guard_equal_to_the_bound():
    """|T| = 1 exactly, and a radical that equals 1 only after normal."""
    assert ans('sin(x)=sqrt(2)*sqrt(2)/2') == 'x=pi/2'
    assert ans('cos(x)=(sqrt(3)+1)^2/(4+2*sqrt(3))') == 'x=0'


def test_inv_table_shape():
    """The table holds the design's rows (9.3) in its format; test_rules.py runs the 9.8
    check f(template) = T under the guard on solvee.INV too."""
    assert set(R.MODS['solvee'].INV) >= {K.SIN, K.COS, K.TAN, K.LN, K.ABS}
    for op, (tmpls, guard) in R.MODS['solvee'].INV.items():
        for s in tmpls + ((guard,) if guard else ()):
            for ch in s:
                assert not ch.isupper() or ch == 'T', s


# -- exponentials, logs, other kernels ------------------------------------------------------------

def test_exponential_kernels():
    assert ans('e^(2x)-3e^x+2=0') == 'x=0,x=ln(2)'
    assert ans('e^(-x)=2') == 'x=-ln(2)'
    assert ans('1/(1+e^x)=1/3') == 'x=ln(2)'
    assert ans('e^(2x)=4') == 'x=ln(2)'
    assert ans('x*e^x=0') == 'x=0'
    assert ans('10^x=1000') == 'x=3'


def test_hyperbolic_kernels():
    assert ans('sinh(x)=1') == 'x=ln(sqrt(2)+1)'
    assert ans('tanh(x)=1/2') == 'x=ln(3)/2'
    assert msg('tanh(x)=2') == 'no solution'
    r = go('cosh(x)=2')                     # no inverse template (D3 guard): numeric
    got = [float(t.split('=')[1]) for t in r[1].split(',')]
    assert r[3] & R.F_APPROX and [round(v, 12) for v in got] == [
        round(-math.acosh(2), 12), round(math.acosh(2), 12)]


def test_complex_coefficients():
    """With i in the equation, complex roots are kept (D3 applies to real equations)."""
    assert ans('solve(x^2+2*i*x-1=0)') == 'x=-i'
    assert ans('solve(x-i)') == 'x=i'


def test_unknown_functions_cannot_be_solved():
    assert msg('solve(f(x)=2)') == 'cannot solve'
    assert msg('solve(x+f(x)=2)') == 'cannot solve'


def test_numeric_fallback():
    r = go('x=cos(x)')
    assert r[0] == 'ans' and r[3] & R.F_APPROX
    assert abs(float(r[1][2:]) - 0.7390851332151607) < 1e-12
    r = go('x*e^x=1')
    assert abs(float(r[1][2:]) - 0.5671432904097838) < 1e-12
    r = go('x^x=4')
    assert abs(float(r[1][2:]) - 2.0) < 1e-12
    r = go('cos(2x)=cos(x)')
    got = [float(t.split('=')[1]) for t in r[1].split(',')]
    assert [round(v, 9) for v in got] == [0.0, round(2 * math.pi / 3, 9),
                                         round(4 * math.pi / 3, 9)]


def test_nsolve_drops_poles():
    x = K.sym('x')
    vs = R.MODS['solved'].nsolve(nd('tan(x)-x'), x, 0.5, 10.0)
    for v in vs:
        assert abs(math.tan(v) - v) < 1e-8
    assert len(vs) == 2     # 4.4934, 7.7253; the poles pi/2, 3pi/2, 5pi/2 are not roots
    assert R.MODS['solved'].nsolve(nd('1/(x-1)'), x, -3.0, 3.0) == []


# -- linear systems and elimination (11.2) ---------------------------------------------------------

def test_linear_systems():
    assert ans('solve([x+y=3,x-y=1],[x,y])') == 'x=2,y=1'
    assert ans('solve([x+y=3,x-y=1])') == 'x=2,y=1'           # unknowns: the symbols
    assert msg('solve([x+y=1,x+y=2],[x,y])') == 'no solution'   # inconsistent
    assert ans('solve([x+y=1],[x,y])') == 'x=1-y'                # y free
    assert ans('solve([x+y+z=1,x-y=0],[x,y,z])') == 'x=-(z-1)/2,y=-(z-1)/2'
    assert ans('solve([x+y=a,x-y=b],[x,y])') == 'x=(a+b)/2,y=(a-b)/2'
    assert msg('solve([x+y=x+y],[x,y])') == 'every x is a solution'


def test_linear_system_against_sympy():
    rnd = random.Random(7)
    xs = sympy.symbols('x y z w', real=True)
    for n in (2, 3, 4):
        for trial in range(4):
            M = sympy.Matrix(n, n, lambda i, j: rnd.randint(-5, 5))
            if M.det() == 0:
                continue
            sol = [sympy.Rational(rnd.randint(-9, 9), rnd.randint(1, 4)) for i in range(n)]
            b = M * sympy.Matrix(sol)
            eqs = []
            for i in range(n):
                lhs = sum(M[i, j] * xs[j] for j in range(n))
                eqs.append('%s=%s' % (str(lhs).replace('**', '^'), b[i]))
            s = 'solve([%s],[%s])' % (','.join(eqs), ','.join(str(v) for v in xs[:n]))
            r = drive(SO.g_solve((nd('[%s]' % ','.join(eqs)),
                                  nd('[%s]' % ','.join(str(v) for v in xs[:n]))),
                                 [0, None, 0, 0]))
            got = values(r)
            assert got == sol, (s, tx(r), sol)
            K.reset()


def test_lsys_shapes():
    x, y = K.sym('x'), K.sym('y')
    NO = R.MODS['norm']
    assert SC.lsys((NO.normal(nd('x+y-3')), NO.normal(nd('x-y-1'))), (x, y)) == \
        [(nd('2'), nd('1'))]
    assert SC.lsys((NO.normal(nd('x*y-1')),), (x, y)) is None             # not linear
    assert SC.lsys((NO.normal(nd('a*x-1')),), (x,)) is None                # symbolic coefficient
    assert SC.lsys((NO.normal(nd('x+y-1')), NO.normal(nd('x+y-2'))), (x, y)) == []
    assert SC.lsys((NO.normal(nd('1/x-1')),), (x,)) is None                # x in a denominator


def test_nonlinear_systems():
    assert ans('solve([x+y=3,x*y=2],[x,y])') == '[x=1,y=2],[x=2,y=1]'
    assert ans('solve([x^2+y^2=5,x+y=3])') == '[x=1,y=2],[x=2,y=1]'
    assert ans('solve([a*x+y=1,x-y=0],[x,y])') == 'x=1/(a+1),y=1/(a+1)'
    assert ans('solve([y=x^2,y=x+2],[x,y])') == '[x=-1,y=1],[x=2,y=4]'
    assert msg('solve([x^2+y^2=1,x+y=5],[x,y])') == 'no solution'
    assert ans('solve([x^2=y,x=2],[x,y])') == 'x=2,y=4'


def test_systems_with_kernels_and_floats():
    assert ans('solve([sin(x)=y,y=1/2],[x,y])') == '[x=pi/6,y=1/2],[x=5*pi/6,y=1/2]'
    assert ans('solve([0.5x+y=1,x-y=2])') == 'x=2.0,y=0.0'
    assert ans('solve([e^x=y,y=2],[x,y])') == 'x=ln(2),y=2'


def test_system_solutions_check_every_equation():
    """An elimination candidate that fails another equation is dropped."""
    assert ans('solve([x^2=4,x+y=0,y=2],[x,y])') == 'x=-2,y=2'


def test_one_equation_with_a_variable_list():
    assert ans('solve(x^2=4,[x])') == 'x=-2,x=2'
    assert ans('solve([x^2=4],x)') == 'x=-2,x=2'


# -- printing and the round trip (12.1, 20.12) -----------------------------------------------------

def test_solution_text_round_trips():
    """x=a,x=b is a bare top-level list that re-parses to the same node (Ans is safe)."""
    for s in ('solve(x^2=1)', 'solve(x^2+x-1=0)', 'solve(sin(x)=1/2)', 'x^2=2',
              'solve([x+y=3,x*y=2],[x,y])', 'solve([x+y=3,x-y=1])', 'solve(x^5-x+1=0)'):
        t = ans(s)
        e = nd(t)
        assert PR.text(e, None) == t, (s, t)
    assert ans('solve(x^2=1)') == 'x=-1,x=1'
    assert ans('ans()') == 'x=-1,x=1'


def test_degree_mode_round_trip():
    t = ans('sin(x)=1/3', deg=1)
    e = nd(t, deg=1)
    assert PR.text(e, (1, None, 0, 0)) == t
    K.reset()


# -- invariants, regions, depth --------------------------------------------------------------------

def test_roots_leave_no_garbage():
    """Every sub-solve runs in a region: after g_roots only the roots (and what they need)
    and the per-command caches survive above the mark."""
    x = K.sym('x')
    f = nd('x^4-10*x^2+1')
    m = K.NN
    r = K.keep(m, drive(SO.g_roots(f, x, 0)))
    assert len(r) == 4 and K.NN - m <= 30, K.NN - m


def test_solve_under_the_debug_arena(arena):
    for s in ('x^2-5x+6=0', 'sqrt(x+3)=x-3', 'sin(x)+cos(x)=1', 'sin(x)^2+cos(x)=1',
              'solve([x+y=3,x*y=2],[x,y])', 'x^4-10x^2+1=0', 'e^(2x)-3e^x+2=0',
              'x=cos(x)', 'solve([x+y+z=6,x-y=0,2x-z=1],[x,y,z])'):
        assert go(s)[0] == 'ans', s


def test_commands_leave_the_table_empty():
    for s in ('x^2-5x+6=0', 'solve([x+y=3,x*y=2],[x,y])', 'sin(x)=1/2', 'x^2+1=0'):
        go(s)
        assert K.NN == K.BASE
        assert not R.LIVE and not R.NEEDED


def test_g_roots_contract():
    x = K.sym('x')
    assert drive(SO.g_roots(nd('x-x'), x, 0)) == K.TRUE
    assert drive(SO.g_roots(nd('y+1'), x, 0)) == ()
    assert drive(SO.g_roots(nd('x^5+y*x+1'), x, 0)) is None
    r = drive(SO.g_roots(nd('(x-3)*(x+1)*(x-1/2)'), x, 0))
    assert [tx(v) for v in r] == ['-1', '1/2', '3']


def nested(kind, n):
    if kind == 'lin':
        s = 'x'
        for i in range(n):
            s = '(%s+1)' % s if i % 2 else '2*%s' % s
        return s + '=1'
    if kind == 'sin':
        s = 'x'
        for i in range(n):
            s = '(%s+1/7)' % s
        return 'sin(%s)=1/2' % s
    s = 'x'
    for i in range(n):
        s = '(%s+x)' % s if i % 2 else '3*(%s)' % s
    return 'sqrt(%s)=4' % s


@pytest.mark.parametrize('kind', ('lin', 'sin', 'rad'))
def test_nesting_invariance(kind, evodepth):
    depths = []
    for n in (1, 8, 30):
        s = nested(kind, n)
        r, d, _ = evodepth.measure(go, s)
        assert r[0] == 'ans', (s, r)
        depths.append(d)
    assert depths[0] == depths[1] == depths[2], depths


@pytest.mark.strict_depth
def test_strict_depth_mode():
    for s in ('x^2-5x+6=0', 'sqrt(x+3)=x-3', 'sin(x)+cos(x)=1', 'x=cos(x)',
              'solve([x+y=3,x*y=2],[x,y])', 'solve([x+y+z=6,x-y=0,2x-z=1],[x,y,z])',
              'sin(x)^2+cos(x)=1', 'e^(2x)-3e^x+2=0', 'x^5-x+1=0'):
        assert go(s)[0] == 'ans', s


def test_cancel_in_numeric_search(monkeypatch):
    n = [0]

    def esc():
        n[0] += 1
        return n[0] > 3
    monkeypatch.setattr(K, 'ESC', esc)
    assert msg('x=cos(x)') == 'Interrupted'


# -- size (4.3, 19.2) ------------------------------------------------------------------------------

def code_lines(name):
    sys.path.insert(0, os.path.join(ROOT, 'build'))
    try:
        import bundle
    finally:
        sys.path.pop(0)
    with open(os.path.join(ROOT, 'src', name + '.py'), encoding='utf-8') as fh:
        return len(bundle.minify(fh.read(), name).lines)


def test_parts_fit_lazymax():
    assert max(code_lines(n) for n in ('solve', 'solveb', 'solvec', 'solved', 'solvee')) <= LAZYMAX


def test_parts_size_is_bounded():
    assert sum(code_lines(n) for n in ('solve', 'solveb', 'solvec', 'solved', 'solvee')) <= 700
