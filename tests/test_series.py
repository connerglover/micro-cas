"""Taylor and Laurent coefficients, cancellation, centers and command contracts."""
import pytest
import sympy

import node as K
import parse as P
import run as R
import series as SE
from test_norm import drive, nd, to_sympy


@pytest.fixture(autouse=True)
def session(monkeypatch):
    for name, value in (('ANS', None), ('HIST', []), ('VARS', {}), ('FUNCS', {}),
                        ('MODS', {}), ('LOADED', []), ('USE', {}), ('PINNED', []),
                        ('LIVE', {}), ('NEEDED', []), ('CLOCK', [0])):
        monkeypatch.setattr(R, name, value)
    monkeypatch.setattr(R, 'SET', {'deg': 0})
    monkeypatch.setattr(P, 'SESS', R)
    R.need('ser')


@pytest.mark.oracle
@pytest.mark.parametrize('source,center,order', [
    ('sin(x)', '0', 7), ('cos(x)', '0', 8), ('tan(x)', '0', 7),
    ('exp(x)', '0', 7), ('ln(1+x)', '0', 7), ('sqrt(1+x)', '0', 7),
    ('1/sqrt(1-x)', '0', 7), ('ln(x)', '1', 6), ('sin(x)', 'pi/2', 6),
    ('1/sin(x)', '0', 5), ('(sin(x)-x)/x^3', '0', 4),
    ('(exp(x)-1-x-x^2/2)/x^3', '0', 4), ('1/(1-x)', '0', 6),
    ('sin(x)^2+cos(x)^2', '0', 5), ('atan(x)', '0', 7),
    ('asin(x)', '0', 7), ('acos(x)', '0', 6), ('sinh(x)', '0', 7),
    ('cosh(x)', '0', 6), ('tanh(x)', '0', 7), ('sec(x)', '0', 6),
    ('cot(x)', '0', 5), ('exp(sin(x))', '0', 5), ('x^x', '1', 4),
    ('(1+x)^(1/x)', '0', 3), ('1/(exp(x)-1)', '0', 4),
    ('ln(2+x)', '0', 5), ('sqrt(2+x)', '0', 5),
    ('sin(x)', '1', 6), ('ln(1+x*x)', '0', 8), ('asin(x*x)', '0', 8),
    ('sin(sin(x))', '0', 7), ('(1-cos(x))/x^2', '0', 6),
    ('x^2/(1-cos(x))', '0', 5), ('ln(1+x)/x', '0', 7),
])
def test_oracle_coefficients(source, center, order):
    f, x, a = nd(source), K.sym('x'), nd(center)
    original = to_sympy(f)
    point = to_sympy(a)
    s = drive(SE.g_series(f, x, a, order))
    assert s is not None, source
    h = sympy.Symbol('h', real=True)
    expected = sympy.series(original.subs(to_sympy(x), point + h), h, 0, order + 1).removeO()
    actual = 0
    for j in range(1, len(s)):
        power = s[0] + j - 1
        if power <= order:
            actual += to_sympy(s[j]) * h ** power
    assert sympy.simplify(sympy.expand(actual - expected)) == 0, (source, actual, expected)


@pytest.mark.parametrize('source,center,expected', [
    ('x/(x+1)', 'oo', [1, -1, 1, -1]),
    ('x/(x+1)', '-oo', [1, 1, 1, 1]),
    ('sin(1/x)', 'oo', [0, 1, 0, sympy.Rational(-1, 6)]),
])
def test_infinity(source, center, expected):
    s = drive(SE.g_series(nd(source), K.sym('x'), nd(center), 3))
    assert s is not None
    actual = [sympy.Integer(0)] * 4
    for j in range(1, len(s)):
        p = s[0] + j - 1
        if 0 <= p <= 3:
            actual[p] = to_sympy(s[j])
    assert actual == expected


@pytest.mark.parametrize('text', [
    'taylor(sin(x),x,0,7)', 'series(sin(x),x,0,7)',
    'taylor(sin(x),x=0,7)', 'taylor(sin(x),x=0)', 'taylor(sin(x))',
    'taylor(ln(x),x=1,5)', 'taylor(1/sin(x),x,0,5)',
    'taylor(sin(x),x,0,0)', 'taylor(1,x,0,0)',
])
def test_command_formats(text):
    result = R.go(('eval', text))
    assert result[0] == 'ans', result
    assert 'O(' in result[1]
    assert 'taylor(' not in result[1]


@pytest.mark.parametrize('source', ['sqrt(x)', 'ln(x)', 'sin(1/x)', 'f(x)'])
def test_nonanalytic_is_unevaluated(source):
    result = R.go(('eval', 'taylor(' + source + ',x,0,5)'))
    assert result[0] == 'ans', result
    assert result[1].startswith('taylor('), result


@pytest.mark.parametrize('text', ['taylor(x,x,0,-1)', 'taylor(x,x,0,21)',
                                  'taylor(x,x,0,1/2)', 'taylor(x,2,0,3)',
                                  'taylor(x,x=0,3,4)'])
def test_invalid_arguments(text):
    result = R.go(('eval', text))
    assert result[0] == 'msg', result
    assert not result[1].startswith('internal error')


def test_zero_series_and_requested_precision():
    assert len(drive(SE.g_series(K.ZERO, K.sym('x'), K.ZERO, 5))) == 1
    s = drive(SE.g_series(nd('(sin(x)-x+x^3/6)/x^5'), K.sym('x'), K.ZERO, 3))
    assert to_sympy(s[1]) == sympy.Rational(1, 120)
    assert s[0] == 0 and s[0] + len(s) - 2 >= 3


def test_order_twenty_rational():
    s = drive(SE.g_series(nd('1/(1-x)'), K.sym('x'), K.ZERO, 20))
    assert s[:22] == tuple([0] + [K.ONE] * 21)


def test_repeated_series_calls_retain_input_nodes():
    f, x = nd('sin(x)/x'), K.sym('x')
    for _ in range(3):
        s = drive(SE.g_series(f, x, K.ZERO, 5))
        assert s[0] == 0 and s[1] == K.ONE
    assert K.N[f][0] == K.MUL
