"""Regression tests for the 2026-11 audit (docs/STATUS.md): wrong limits, solver answers,
numeric fallbacks, the Ans/store/+C rules and the leaner internals. Each case was a confirmed
wrong answer or failure before the fix named beside it."""
import math

import pytest
import sympy as S

import alg as A
import cascheck as C
import node as K
import run as R


@pytest.fixture(autouse=True)
def session():
    C.fresh()
    yield


def go(text):
    rec = R.go(('eval', text))
    return rec[1], rec[0], rec[3]


def ans(text):
    rec = R.go(('eval', text))
    assert rec[0] == 'ans', (text, rec)
    return rec[1]


def msg(text):
    rec = R.go(('eval', text))
    assert rec[0] == 'msg', (text, rec)
    return rec[1]


# -- a held infinity is no finite value (limitb.held) ---------------------------------------------

@pytest.mark.parametrize('text, want', [
    ('limit(2^x/x,x,oo)', 'oo'),
    ('limit(x^2/2^x,x,oo)', '0'),
    ('limit((sqrt(2)*x+1)/(x+1),x,oo)', 'sqrt(2)'),
    ('limit((pi*e^x+x)/(e^x+1),x,oo)', 'pi'),
    ('limit(ln(3)*x,x,oo)', 'oo'),
    ('limit(pi*x-x,x,oo)', 'oo'),
    ('limit(-sqrt(2)*x,x,oo)', '-oo'),
    ('limit(tanh(pi*x),x,oo)', '1'),
    ('integrate(1/(x^2+2),x,0,oo)', 'sqrt(2)*pi/4'),
    ('integrate(e^(-pi*x),x,0,oo)', '1/pi'),
])
def test_irrational_times_infinity(text, want):
    assert ans(text) == want


@pytest.mark.parametrize('text', [
    'limit(ln(2^x+3^x)/x,x,oo)', 'limit((2^x+3^x)^(1/x),x,oo)', 'limit(x*(pi/2-atan(x)),x,oo)',
])
def test_no_wrong_value_where_no_method_applies(text):
    assert ans(text) not in ('0', '1')  # the wrong answers before the fix


@pytest.mark.parametrize('text', [
    'integrate(x*2^(-x),x,0,oo)', 'sum(k^2/2^k,k,1,oo)', 'sum((k+1)/2^k,k,0,oo)',
    'sum(k/pi^k,k,1,oo)',
])
def test_convergent_is_not_called_divergent(text):
    r = go(text)
    assert 'Diverges' not in r[0], r


# -- floor and ceil in limits ---------------------------------------------------------------------

@pytest.mark.parametrize('text, want', [
    ('limit(floor(x)/x,x,oo)', '1'), ('limit(floor(2*x)/x,x,oo)', '2'),
    ('limit(ceil(x)/x,x,oo)', '1'), ('limit(floor(x^2)/x,x,oo)', 'oo'),
    ('limit(floor(x),x,5/2)', '2'), ('limit(floor(x),x,2,1)', '2'),
])
def test_floor_limits(text, want):
    assert ans(text) == want


@pytest.mark.parametrize('text', [
    'limit(x-floor(x),x,oo)', 'limit(floor(x)-x,x,oo)', 'limit(1/(2+cos(2*pi/x)),x,0)',
])
def test_oscillation_has_no_numeric_value(text):
    assert ans(text).startswith('limit(')       # sampled at powers of ten these passed for 0.0


def test_numeric_limit_keeps_only_agreed_digits():
    assert ans('limit(sqrt(x)*(sqrt(x+1)-sqrt(x)),x,oo)') == '0.5'
    assert ans('limit((2*x+cos(x))/(x+1),x,oo)') == '2.0'
    assert ans('integrate(1/(x*(x+1)),x,1,oo)') == 'ln(2)'      # was ln(2)+8.07E-15


# -- solve ----------------------------------------------------------------------------------------

@pytest.mark.parametrize('text', [
    'solve(abs(x)=x,x)', 'solve(abs(x)/x=1,x)', 'solve(sqrt(x^2)=x,x)',
    'solve(abs(x)+abs(x-1)=1,x)', 'solve(sin(x)=sqrt(1-cos(x)^2),x)',
])
def test_part_of_the_line_is_not_every_x(text):
    assert msg(text) == 'Cannot solve'


def test_identities_still_say_every_x():
    assert msg('solve(sin(x)^2+cos(x)^2=1)') == 'Every x is a solution'
    assert msg('solve(2*x=x+x,x)') == 'Every x is a solution'


@pytest.mark.parametrize('text, want', [
    ('solve([x*y=0,x^2+y^2=1],[x,y])', '[x=-1,y=0],[x=0,y=-1],[x=0,y=1],[x=1,y=0]'),
    ('solve([x*y=0,x+y=1],[x,y])', '[x=0,y=1],[x=1,y=0]'),
    ('solve([x+y=1,x*y=0],[x,y])', '[x=0,y=1],[x=1,y=0]'),
    ('solve([x*y=x,x+y=3],[x,y])', '[x=0,y=3],[x=2,y=1]'),
    ('solve([x*(y-1)=0,y*(x-1)=0],[x,y])', '[x=0,y=0],[x=1,y=1]'),
    ('solve([x+y=3,x-y=1],[x,y])', 'x=2,y=1'),
])
def test_systems_keep_every_branch(text, want):
    assert ans(text) == want


@pytest.mark.parametrize('text, want', [
    ('solve((x-1)*sqrt(x-2)=0,x)', 'x=2'),
    ('solve((x^2-1)*ln(x)=0,x)', 'x=1'),
    ('solve((x+2)*ln(x+1)=0,x)', 'x=0'),
    ('solve(sqrt(x^2-2)=0,x)', 'x=-sqrt(2),x=sqrt(2)'),     # rounding beside the branch point
])
def test_roots_where_a_subexpression_is_not_real(text, want):
    assert ans(text) == want


def test_no_root_where_both_sides_are_imaginary():
    assert msg('solve(sqrt(x-5)=sqrt(3-x),x)') == 'No solution'


@pytest.mark.parametrize('text, roots', [
    ('solve(x*ln(x)=100,x)', [29.5365990543293]),
    ('solve(x+ln(x)=20,x)', [17.1575610462156]),
    ('solve(sqrt(x)+ln(x)=10,x)', [39.8710193565767]),
    ('solve(e^x=x+20,x)', [-19.9999999979388, 3.14163330280104]),
    ('solve(e^(x-1/3)-x-2/3=0,x)', [1 / 3]),                 # a touching root: no sign change
])
def test_numeric_roots_outside_the_old_window(text, roots):
    got = [float(p.split('=')[1]) for p in ans(text).split(',')]
    assert len(got) == len(roots)
    for a, b in zip(got, roots):
        assert abs(a - b) < 1e-7 * (1 + abs(b))


def test_an_empty_numeric_search_claims_nothing():
    assert msg('solve(e^x=x,x)').startswith('No root found')
    assert msg('solve(x^2+1=0,x)') == 'No solution'         # exact: still a proof


def test_huge_degrees_fail_softly():
    assert ans('factor(x^(2^64)-1)') == 'x^18446744073709551616-1'
    assert msg('solve(x^(2^64)=1,x)') == 'Cannot solve'


# -- ODE equilibria -------------------------------------------------------------------------------

def test_equilibria_of_a_cubic_right_side():
    assert ans("desolve([y'=y^3-y,y(0)=1],y)") == 'y=1'
    assert ans("desolve([y'+y=y^3,y(0)=-1],y)") == 'y=-1'
    r = ans("desolve(y'=y*(y-1)*(y-2),y)")
    assert r.endswith(',y=0,y=1,y=2')


# -- numbers --------------------------------------------------------------------------------------

@pytest.mark.parametrize('text, want', [
    ('1.000001^10000', 1.0100501620), ('1.0001^7000', 2.0136822321),
    ('(1+0.05/365)^(365*30)', 4.4812286885), ('approx((1001/1000)^10000)', 21916.681340),
])
def test_products_whose_factors_overflow(text, want):
    assert abs(float(ans(text)) - want) < 2e-8 * want


def test_float_powers_have_no_polar_noise():
    # MicroPython 1.12 computes complex ** int in polar form: -2.5 ** 1 was -2.5+3.06e-16j
    assert K.npowi((K.FLT, -2.5, 0.0), 1) == (K.FLT, -2.5, 0.0)
    assert K.npowi((K.FLT, -2.0, 0.0), 2) == (K.FLT, 4.0, 0.0)
    assert K.npowi((K.FLT, 2.0, 0.0), -2) == (K.FLT, 0.25, 0.0)
    assert K.npowi((K.FLT, 0.0, 1.0), 2) == (K.FLT, -1.0, 0.0)
    z = K.npowi((K.FLT, 1.0, 1.0), -3)
    assert abs(complex(z[1], z[2]) - (1 + 1j) ** -3) < 1e-15
    assert ans('approx(-2)^2') == '4.0'


def test_rational_arithmetic_by_small_gcds():
    import random
    from fractions import Fraction
    rnd = random.Random(7)
    for i in range(3000):
        a = Fraction(rnd.randrange(-10 ** 12, 10 ** 12), rnd.randrange(1, 10 ** 9))
        b = Fraction(rnd.randrange(-10 ** 6, 10 ** 6), rnd.randrange(1, 10 ** 12))
        x = (K.NUM, a.numerator, 0, a.denominator)
        y = (K.NUM, b.numerator, 0, b.denominator)
        s, p = a + b, a * b
        assert K.nadd(x, y) == (K.NUM, s.numerator, 0, s.denominator)
        assert K.nmul(x, y) == (K.NUM, p.numerator, 0, p.denominator)


def test_isprime_is_a_proof():
    R.need('fact')
    FD = R.MODS['form']
    assert not FD.isprime(318665857834031151167461)     # passes the first 12 prime bases
    assert FD.isprime(2 ** 61 - 1) and not FD.isprime(2 ** 61 + 1)
    assert not FD.isprime(2 ** 89 - 1)                  # a prime, but beyond the proven range
    for n in range(2, 3000):
        assert FD.isprime(n) == S.isprime(n), n
    assert ans('factor(999999999989)') == '999999999989'
    assert R.MODS['fact'].COMPLETE[0] == 1


# -- quadrature -----------------------------------------------------------------------------------

def test_quadrature_shows_the_digits_it_has():
    r = ans('integrate(1/(x*sqrt(x^2-1)),x,1,2)')
    assert len(r) <= 10 and abs(float(r) - math.pi / 3) < 1e-6      # was 1.04719755530957
    r = ans('integrate(e^(-x^2),x,0,1)')
    assert abs(float(r) - 0.746824132812427) < 1e-13                # smooth: every digit


# -- the session ----------------------------------------------------------------------------------

@pytest.mark.parametrize('text, plus_c', [
    ('integrate(x,x)', 1), ('integrate(x,x)=3', 0), ('integrate(x,x),5', 0),
    ('integrate(1,x)^2', 0),
])
def test_plus_c_only_for_a_whole_line_integral(text, plus_c):
    assert go(text)[2] & R.F_PLUSC == plus_c


def test_a_form_of_an_older_entry_leaves_ans():
    ans('1/2+x')
    ans('7')
    R.go(('form', 0))
    assert R.ANS == '7'


def test_a_store_that_keeps_nothing_says_so():
    assert msg('x=1<2') == 'Not stored' and 'x' not in R.VARS
    assert msg('a=1000!*1000!') == 'Not stored' and 'a' not in R.VARS
    assert msg('1000!*1000!') == 'Done'


def test_a_variable_used_many_times():
    ans('y=2')
    assert ans('+'.join(['y'] * 70)) == '140'


def test_steps_are_not_offered_where_they_would_not_repeat():
    assert go('diff(x^2,x)')[2] & R.F_STEPS
    assert not go('diff(x^2.5,x)')[2] & R.F_STEPS            # a decimal: the walk is exact
    assert not go('integrate(x,x,0,2)=>z')[2] & R.F_STEPS    # a store: z has changed
    msg('integrate(1/x,x,-1,1)')
    rec = R.go(('steps', len(R.HIST) - 1))                   # a message entry
    assert rec[0] == 'msg' and R.STEPS == []


def test_together_leaves_a_series():
    assert 'O(x^6)' in ans('together(series(sin(x),x,0,5))')
    assert ans('together(1/x+1/y)') == '(x+y)/(x*y)'


def test_sum_that_cannot_fit_stays_formal():
    assert ans('sum(sin(k),k,1,1000)') == 'sum(sin(k),k,1,1000)'
    assert ans('sum(k^2,k,1,1000)') == '333833500'


# -- internals ------------------------------------------------------------------------------------

def test_keep_rebuilds_only_moved_tuples():
    x = K.sym('x')
    m = K.NN
    a = K.fn_(K.SIN, x)
    t = K.N[a]
    assert K.keep(m, a) == a and K.N[a] is t            # nothing moved: the same tuple object


def test_leftreal_flags_only_real_departures():
    x = K.sym('x')
    e = K.mul_(K.ONE, [(K.add_([x, K.num(-2)]), K.HALF)])     # sqrt(x-2)
    A.nrun(A.nprog(e, (x,)), (1.0,))
    assert A.LEFTREAL == [1, 1]
    A.nrun(A.nprog(e, (x,)), (2.0 - 1e-15,))
    assert A.LEFTREAL == [1, 0]                         # rounding beside the branch point
    A.nrun(A.nprog(e, (x,)), (3.0,))
    assert A.LEFTREAL == [0, 0]
