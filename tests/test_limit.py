"""T2.3: exact limits, one-sided discontinuities, growth, and honest fallbacks."""
import pytest
import sympy as S

import alg as A
import node as K
import parse as P
import run as R
from test_diff import drive, nd, symbolic


@pytest.fixture(autouse=True)
def session(monkeypatch):
    for name, value in (('ANS', None), ('HIST', []), ('VARS', {}), ('FUNCS', {}),
                        ('MODS', {}), ('LOADED', []), ('USE', {}), ('PINNED', []),
                        ('LIVE', {}), ('NEEDED', []), ('CLOCK', [0])):
        monkeypatch.setattr(R, name, value)
    monkeypatch.setattr(R, 'SET', {'deg': 0, 'theme': 0})
    monkeypatch.setattr(P, 'SESS', R)
    R.need('lim')


def limit(text, center='0', side=0):
    return drive(R.MODS['lim'].g_lim(nd(text), K.sym('x'), nd(center), side))


@pytest.mark.oracle
@pytest.mark.parametrize('source,center,side,expected', [
    ('x^2+3*x', '2', 0, '10'),
    ('sin(x)/x', '0', 0, '1'),
    ('(1-cos(x))/x^2', '0', 0, '1/2'),
    ('(exp(x)-1-x)/x^2', '0', 0, '1/2'),
    ('(sin(x)-x)/x^3', '0', 0, '-1/6'),
    ('(x^2-1)/(x-1)', '1', 0, '2'),
    ('x*ln(x)', '0', 1, '0'),
    ('x^x', '0', 1, '1'),
    ('x^(1/ln(x))', '0', 1, 'e'),
    ('x^(1/ln(x))', 'oo', 0, 'e'),
    ('(1+1/x)^x', 'oo', 0, 'e'),
    ('(1+2/x)^x', 'oo', 0, 'e^2'),
    ('(1+x)^(1/x)', '0', 0, 'e'),
    ('x^3/exp(x)', 'oo', 0, '0'),
    ('exp(x)/x^3', 'oo', 0, 'oo'),
    ('exp(x)*x^3', '-oo', 0, '0'),
    ('ln(x)/x', 'oo', 0, '0'),
    ('ln(x)^3/x', 'oo', 0, '0'),
    ('ln(x^2)/ln(x)', 'oo', 0, '2'),
    ('ln(x^3)^2/ln(x)^2', 'oo', 0, '9'),
    ('x/ln(x)', 'oo', 0, 'oo'),
    ('sqrt(x^2+x)-x', 'oo', 0, '1/2'),
    ('sqrt(x^2+x)-x', '-oo', 0, 'oo'),
    ('(3*x^3+x)/(2*x^3-7)', 'oo', 0, '3/2'),
    ('(x^2+1)/(x^3-4)', '-oo', 0, '0'),
    ('x^3', '-oo', 0, '-oo'),
    ('1/x', '0', -1, '-oo'),
    ('1/x', '0', 1, 'oo'),
    ('1/x^2', '0', 0, 'oo'),
    ('1/x^3', '0', -1, '-oo'),
    ('exp(-1/x^2)', '0', 0, '0'),
    ('exp(-1/x)', '0', 1, '0'),
    ('exp(-1/x)', '0', -1, 'oo'),
    ('sin(1/x)*x', '0', 0, '0'),
    ('sin(x)/x', 'oo', 0, '0'),
    ('atan(x)', 'oo', 0, 'pi/2'),
    ('atan(x)', '-oo', 0, '-pi/2'),
    ('tanh(x)', '-oo', 0, '-1'),
    ('ln(x)', '0', 1, '-oo'),
    ('floor(x)', '1', -1, '0'),
    ('floor(x)', '1', 1, '1'),
    ('ceil(x)', '1', -1, '1'),
    ('ceil(x)', '1', 1, '2'),
    ('floor(x^2)', '0', 0, '0'),
    ('ceil(x^2)', '0', 0, '1'),
    ('floor(-x^2)', '0', 0, '-1'),
    ('sign(x^2)', '0', 0, '1'),
    ('abs(x)/x', '0', -1, '-1'),
    ('abs(x)/x', '0', 1, '1'),
    ('abs(x-1)/(x-1)', '1', -1, '-1'),
])
def test_exact_limits(source, center, side, expected):
    actual = limit(source, center, side)
    assert actual is not None, source
    want = nd(expected)
    assert K.N[actual][0] != K.FLT, (source, actual)
    if want == K.OO or K.isninf(want):
        assert actual == want, source
    else:
        assert S.simplify(symbolic(actual) - symbolic(want)) == 0, source


@pytest.mark.parametrize('source,left,right', [
    ('1/x', '-oo', 'oo'), ('abs(x)/x', '-1', '1'),
    ('floor(x)', '-1', '0'), ('ceil(x)', '0', '1'), ('sign(x)', '-1', '1'),
])
def test_two_sided_disagreement(source, left, right):
    result = limit(source)
    assert K.N[result] == (K.DNE, nd(left), nd(right))


@pytest.mark.parametrize('source,center', [('sin(1/x)', '0'), ('cos(x)', 'oo'), ('sin(x)^2', 'oo')])
def test_oscillation(source, center):
    result = limit(source, center)
    assert K.N[result] == (K.DNE, K.UNDEF, K.UNDEF)


@pytest.mark.parametrize('source', [
    'limit(sin(x)/x,x,0)', 'lim(sin(x)/x,x=0)', 'limit(sin(x)/x,x=0,1)',
])
def test_command_forms(source):
    assert R.go(('eval', source))[:2] == ('ans', '1')


def test_dne_message():
    record = R.go(('eval', 'limit(1/x,x,0)'))
    assert record[0] == 'msg'
    assert 'left' in record[1] and 'right' in record[1]


def test_oscillation_message():
    assert 'oscillates' in R.go(('eval', 'limit(sin(1/x),x,0)'))[1]


@pytest.mark.parametrize('source', [
    'limit(x,x+1,0)', 'limit(x,x,x)', 'limit(x,x,0,2)', 'limit(x,x,0,i)', 'limit(x,x)',
])
def test_invalid_arguments(source):
    assert R.go(('eval', source))[0] == 'msg'


def test_unknown_limit_stays_unevaluated():
    result = limit('f(x)')
    assert K.N[result] == (K.CALL, K.sym('limit'), nd('f(x)'), K.sym('x'), K.ZERO)


def test_numeric_fallback_is_approximate(monkeypatch):
    def unavailable(*args):
        yield None
    monkeypatch.setattr(R.MODS['ser'], 'g_series', unavailable)
    monkeypatch.setattr(R.MODS['lim'], 'MAXLH', 0)
    result = limit('sin(x)/x')
    assert K.N[result][0] == K.FLT
    assert K.N[result][1] == pytest.approx(1.0, abs=1e-10)
    record = R.go(('eval', 'limit(sin(x)/x,x,0)'))
    assert record[0] == 'ans' and record[3] & R.F_APPROX


@pytest.mark.parametrize('source', ['ln(x)', 'x^x'])
def test_unavailable_real_side_is_not_a_real_answer(source):
    result = limit(source, '0', -1)
    assert K.N[result][0] == K.CALL


def test_degree_mode_limit():
    R.SET['deg'] = 1
    record = R.go(('eval', 'limit(sin(x)/x,x,0)'))
    assert record[:2] == ('ans', 'pi/180')


@pytest.mark.parametrize('source,center,expected', [
    ('exp(ln(x)/2)/x', 'oo', '0'),
    ('exp(sqrt(ln(x)))/x', 'oo', '0'),
    ('exp(-sqrt(ln(x)))*x', 'oo', 'oo'),
    ('exp(2*ln(x))/x', 'oo', 'oo'),
    ('exp(ln(x)/2)/sqrt(x)', 'oo', '1'),
    ('exp(sqrt(ln(-x)))/(-x)', '-oo', '0'),
    ('exp(-sqrt(ln(-x)))*(-x)', '-oo', 'oo'),
    ('exp(x)/x^100', 'oo', 'oo'),
    ('exp(-x)*x^100', 'oo', '0'),
])
def test_exponential_dominance_is_proven(source, center, expected):
    result = limit(source, center)
    if K.N[result][0] == K.CALL:
        assert K.N[result][1] == K.sym('limit')
    else:
        want = nd(expected)
        if want == K.OO or K.isninf(want):
            assert result == want
        else:
            assert float(symbolic(result)) == pytest.approx(float(symbolic(want)), abs=1e-10)

