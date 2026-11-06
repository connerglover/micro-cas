"""T2.7/T3.1/T3.6: definite, improper and nested integrals through the commands."""
import math

import pytest
import sympy as S

import alg as A
import node as K
import parse as P
import run as R
import cascheck as C
from test_diff import drive, nd


@pytest.fixture(autouse=True)
def session(monkeypatch):
    C.fresh()
    R.need('def')


@pytest.mark.parametrize('source,expected', [
    ('integrate(x^2,x,0,1)', '1/3'),
    ('integrate(sin(x),x,0,pi)', '2'),
    ('integrate(sqrt(1-x^2),x,0,1)', 'pi/4'),
    ('integrate(1/(2+cos(x)),x,0,2*pi)', '2*pi/sqrt(3)'),
    ('integrate(1/x^2,x,1,oo)', '1'),
    ('integrate(1/sqrt(x),x,0,1)', '2'),
    ('integrate(exp(-x),x,0,oo)', '1'),
    ('integrate(exp(x),x,-oo,0)', '1'),
    ('integrate(1/(1+x^2),x,-oo,oo)', 'pi'),
    ('integrate(ln(x),x,0,1)', '-1'),
    ('integrate(abs(x),x,-1,1)', '1'),
    ('integrate(x^2,x,1,0)', '-1/3'),
    ('integrate(x^2,x,1,1)', '0'),
    ('integrate(x^3,x,-2,2)', '0'),
    ('integrate(x*y,y,0,x)', 'x^3/2'),
    ('integrate(integrate(x*y,y,0,x),x,0,1)', '1/8'),
    ('polararea(2*cos(t),t,0,pi)', 'pi'),
    ('paramarea(t-sin(t),1-cos(t),t,0,2*pi)', '3*pi'),
    ('arclen(x^(3/2),x,0,4)', '8*(10^(3/2)-1)/27'),
])
def test_exact_definite_integrals(source, expected):
    record = R.go(('eval', source))
    assert record[0] == 'ans', (source, record)
    assert not record[3] & R.F_APPROX, (source, record)
    C.equivalent(record[1], expected)


@pytest.mark.parametrize('source,reason', [
    ('integrate(1/x,x,1,oo)', 0),
    ('integrate(1/x^2,x,-1,1)', 1),
    ('integrate(1/x,x,-1,1)', 1),
    ('integrate(1/(x-1)^2,x,0,2)', 1),
    ('integrate(1/x^2,x,0,1)', 1),
    ('integrate(x,x,0,oo)', 0),
    ('integrate(exp(x^2),x,0,oo)', 0),
    ('integrate(1/(x-1)^2,x,0,oo)', 1),
])
def test_divergence_sentinels(source, reason):
    args = P.rpn(P.tokens(source, 0))
    result = drive(P.g_eval(args, [0, None, 0, 0]))
    assert K.N[result] == (K.DIVG, K.num(reason))


def test_phase_drop_releases_integration_but_keeps_the_norm_family():
    # diff is a part of the norm family: dropping it would evict the largest family pack
    # mid-command, only for the evaluation phase to import it again.
    norm = R.MODS['norm']
    args = P.rpn(P.tokens('integrate(x^2,x,0,1)', 0))
    assert drive(P.g_eval(args, [0, None, 0, 0])) == nd('1/3')
    assert 'norm' in R.LOADED and R.MODS['norm'] is norm
    assert 'int' not in R.LOADED


def test_divergence_message_and_nested_propagation():
    for source in ('integrate(1/x,x,1,oo)',
                   'integrate(integrate(1/x^2,x,-1,1),y,0,1)'):
        record = R.go(('eval', source))
        assert record[0] == 'msg' and record[1].startswith('Diverges')


@pytest.mark.parametrize('source,expected', [
    ('integrate(exp(x^2),x,0,1)', 1.4626517459071816),
    ('integrate(sqrt(1+sin(x)^4*cos(x)^6),x,0,2)', 2.009271279500827),
    ('integrate(exp(-x^2),x,-oo,oo)', math.sqrt(math.pi)),
])
def test_numeric_integrals(source, expected):
    record = R.go(('eval', source))
    assert record[0] == 'ans' and record[3] & R.F_APPROX, (source, record)
    assert float(C.sx(record[1])) == pytest.approx(expected, rel=1e-6, abs=1e-7)


def test_degree_mode():
    R.SET['deg'] = 1
    C.equivalent(C.answer('integrate(sin(x),x,0,180)'), '360/pi')


def test_unhandled_symbolic_integral_remains_formal():
    result = C.answer('integrate(exp(x^2),x,0,a)')
    assert 'integrate(' in result


@pytest.mark.parametrize('source', ['integrate(x,x+1,0,1)', 'integrate(x,x,x,1)'])
def test_invalid_arguments(source):
    assert R.go(('eval', source))[0] == 'msg'


def test_quadrature_budget(monkeypatch):
    module = R.MODS['defb']
    calls = [0]
    original = A.nrun
    def counted(*args):
        calls[0] += 1
        return original(*args)
    monkeypatch.setattr(A, 'nrun', counted)
    f, x, a, b = nd('exp(x^2)'), K.sym('x'), K.ZERO, K.ONE
    result = drive(module.g_quad(f, x, a, b))
    assert result is not None and K.N[result][0] == K.FLT
    assert calls[0] <= R.MODS['def'].MAXEVAL + 2


def test_crosscheck_rejects_bad_primitive(monkeypatch):
    def wrong_primitive(f, x, depth=0):
        yield (K.ZERO, K.ZERO)
    monkeypatch.setattr(R.need('int'), 'g_int', wrong_primitive)
    record = R.go(('eval', 'integrate(x^2,x,0,1)'))
    assert record[0] == 'ans' and record[3] & R.F_APPROX
    assert float(C.sx(record[1])) == pytest.approx(1/3, abs=1e-8)


def test_unknown_numeric_integral_remains_formal():
    assert C.answer('integrate(f(x),x,0,1)') == 'integrate(f(x),x,0,1)'


@pytest.mark.parametrize('center', ['1/10', '1/3'])
def test_missed_narrow_peak_is_not_reported_as_zero(center):
    command = 'integrate(exp(-1000000*(x-' + center + ')^2),x,0,1)'
    result = C.answer(command)
    assert 'integrate(' in result or abs(float(C.sx(result)) - 0.00177245385090552) < 1e-8


@pytest.mark.parametrize('baseline,value', [('1', 1), ('x', .5)])
def test_narrow_peak_above_nonzero_baseline(baseline, value):
    command = 'integrate(' + baseline + '+exp(-1000000*(x-1/10)^2),x,0,1)'
    record = R.go(('eval', command))
    if record[0] == 'ans' and 'integrate(' not in record[1]:
        assert float(C.sx(record[1])) == pytest.approx(value + .00177245385090552, abs=1e-8)


@pytest.mark.parametrize('periods', [20, 50])
def test_primitive_jump_capacity_never_silently_truncates(periods):
    command = 'integrate(1/(2+cos(x)),x,0,' + str(2*periods) + '*pi)'
    record = R.go(('eval', command))
    if record[0] == 'ans' and 'integrate(' not in record[1]:
        assert float(C.sx(record[1])) == pytest.approx(2*periods*math.pi/math.sqrt(3), rel=1e-7)


def test_quadratic_rational_peak_remains_accurate():
    result = C.answer('integrate(1+1/(1000000*(x-1/10)^2+1),x,0,1)')
    assert 'integrate(' in result or float(C.sx(result)) == pytest.approx(
        1+(math.atan(100)+math.atan(900))/1000, abs=1e-8)


@pytest.mark.parametrize('peak', ['exp(-1000000000000*(x-1/10)^4)', '1/(1+1000000000000*(x-1/10)^4)'])
def test_unresolved_higher_order_peak_is_held(peak):
    record = R.go(('eval', 'integrate(1+' + peak + ',x,0,1)'))
    assert record[0] == 'msg' or 'integrate(' in record[1]


@pytest.mark.parametrize('command,value', [
    ('integrate(integrate(exp(-x^2-y^2),y,0,1),x,0,1)', .5577462853510337),
    ('integrate(integrate(exp(y^2),y,0,x),x,0,1)', .603510831677659),
    ('integrate(integrate(exp(x*y^2),y,0,1),x,1,0)', -1.207021663355318)])
def test_whole_double_integral_numeric_fallback(command, value):
    record = R.go(('eval', command))
    assert record[0] == 'ans' and record[3] & R.F_APPROX
    assert float(C.sx(record[1])) == pytest.approx(value, abs=2e-8)


# -- step functions and gaps: an approximation, an exact primitive or a message, never the input -

def pieces(g, cuts):
    """The exact integral of g, constant between the sorted cuts, from its midpoint values."""
    return sum(g((p + q) / 2) * (q - p) for p, q in zip(cuts, cuts[1:]))


@pytest.mark.parametrize('command, value', [
    ('integrate(floor(x),x,0,5/2)', 2),
    ('integrate(ceil(x),x,0,5/2)', 4.5),
    ('integrate(floor(x),x,5/2,0)', -2),
    ('integrate(1/floor(x),x,1,7/2)', 1 + 1 / 2 + 1 / 6),
    ('integrate(floor(x),x,0,25)', 300),
    ('integrate(x*floor(x),x,0,17)', 1564),
    ('integrate(x*floor(x),x,0,2)', 1.5),
    ('integrate(floor(x)^2,x,1/2,5/2)', 1 + 2),
    ('integrate(floor(x^2),x,0,2)', pieces(lambda x: math.floor(x * x),
                                           [0, 1, 2 ** .5, 3 ** .5, 2])),
    ('integrate(floor(1/x),x,1/10,1)', pieces(lambda x: math.floor(1 / x),
                                              [1 / k for k in range(10, 0, -1)])),
    ('integrate(sign(sin(x)),x,0,4)', 2 * math.pi - 4),
    ('integrate(sign(x-1/3)*x^2,x,0,1)', (1 - 2 / 27) / 3),
    ('integrate(sqrt(x)*sign(x-1/2),x,0,1)', 2 / 3 * (1 - 2 * .5 ** 1.5)),
    ('integrate(1/sqrt(abs(x)),x,-1,1)', 4),
])
def test_integrals_across_jumps_are_flagged_approximations(command, value):
    r = R.go(('eval', command))
    assert r[0] == R.R_ANS and r[3] & R.F_APPROX, r
    assert float(r[1]) == pytest.approx(value, abs=1e-7), r


@pytest.mark.parametrize('command, value', [('integrate(floor(x),x,0,1)', 0),
                                            ('integrate(floor(x),x,3/2,7/4)', .25)])
def test_step_function_without_a_jump_on_the_interval(command, value):
    r = R.go(('eval', command))
    assert r[0] == R.R_ANS and float(r[1]) == pytest.approx(value), r


@pytest.mark.parametrize('command, text', [
    ('integrate(sign(x),x)', 'abs(x)'),
    ('integrate(sign(2*x+1),x)', 'abs(2*x+1)/2'),
    ('integrate(sign(x),x,-1,2)', '1'),
])
def test_sign_has_an_exact_primitive(command, text):
    r = R.go(('eval', command))
    assert r[:2] == (R.R_ANS, text) and not r[3] & R.F_APPROX


@pytest.mark.parametrize('command', [
    'integrate(floor(x),x)', 'integrate(ceil(x),x)', 'integrate(x*sign(x),x)',
    'integrate(x+floor(x),x)', 'integrate(x!,x)', 'diff(x!,x)', 'diff(x*x!,x)',
    'integrate(floor(x),x,a,b)', 'integrate(floor(x)*y,x,0,5/2)',
    'integrate(sign(x-1)*e^(-x^2),x,-oo,oo)'])
def test_a_gap_without_a_value_is_a_message(command):
    r = R.go(('eval', command))
    assert r[:2] == (R.R_MSG, 'No closed form: the function has jumps or gaps'), r
    assert R.go(('eval', '1+1'))[1] == '2'              # the next command runs


@pytest.mark.parametrize('command, text', [
    ('integrate(1/abs(x),x,-1,1)', 'No result: the integrand is not continuous'),
    ('integrate(sin(1/x),x,0,1)', 'No result: the integrand is not continuous'),
    ('integrate(floor(x),x,0,26)', 'Too many break points'),
    ('integrate(floor(x),x,0,1000)', 'Too many break points'),
    ('integrate(floor(1/x),x,0,1)', 'Too many break points'),
])
def test_a_failed_approximation_is_a_message(command, text):
    assert R.go(('eval', command))[:2] == (R.R_MSG, text)


@pytest.mark.parametrize('command, text', [
    ('integrate(e^(-x^2),x)', 'integrate(e^(-x^2),x)'),
    ('integrate(x^x,x)', 'integrate(x^x,x)'),
    ('diff(g(x),x)', 'diff(g(x),x)'),
    ('diff(integrate(floor(x),x),x)', 'floor(x)'),
])
def test_formal_results_of_other_functions_stay(command, text):
    assert R.go(('eval', command))[:2] == (R.R_ANS, text)
