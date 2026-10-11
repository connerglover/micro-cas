"""Advanced integration: exact rational reconstruction and independent derivatives."""
import pytest
import sympy as S
import run as R
import integ as IN
import cascheck as C


@pytest.fixture(autouse=True)
def session(monkeypatch):
    C.fresh()


@pytest.mark.parametrize('f', [
    '(x^3+2)/(x^2-1)', '1/(x*(x+1))', '(2*x+3)/((x-1)^2*(x+2))',
    '(x+3)/(x^2+1)', '1/(x^2+1)^2', '(x+1)/(x^2+2*x+2)^3',
    '1/((x^2+1)*(x^2+4))', '1/(2*x+1)^3', '1/(x^2-2)',
    '(3*x^2+5)/(2*x^2+3*x+4)',
])
def test_partial_fractions_reconstruct(f):
    result = C.answer('partfrac(' + f + ',x)')
    assert 'partfrac(' not in result
    assert S.cancel(C.sx(result) - C.sx(f)) == 0


@pytest.mark.parametrize('f', [
    '1/(x*(x+1))', '(2*x+3)/((x-1)^2*(x+2))', '(x^3+2)/(x^2-1)',
    '(x+3)/(x^2+1)', '1/(x^2+1)^2', '(x+1)/(x^2+2*x+2)^3',
    '1/((x^2+1)*(x^2+4))', '1/(x^2-2)',
    'x^3*e^(2*x)', '(x^2+2*x+1)*sin(3*x)', 'x^2*cos(2*x+1)',
    'e^(2*x)*sin(3*x)', 'x^2*e^(2*x)*cos(3*x)',
    'sin(x)^4', 'sin(x)^3*cos(x)^2', 'sin(2*x)*cos(3*x)',
    'cos(x)^6', 'sin(x)^2*cos(x)^2', 'tan(x)^4',
])
def test_advanced_primitive(f):
    result = C.answer('integrate(' + f + ',x)')
    assert 'integrate(' not in result, (f, result)
    x = S.Symbol('x', real=True)
    delta = S.diff(C.sx(result), x) - C.sx(f)
    for point in (S.Rational(2, 7), S.Rational(3, 8), S.Rational(4, 9)):
        assert abs(complex(delta.subs(x, point).evalf(30))) < 1e-8, (f, result, delta)


def test_unsupported_stays_an_integral():
    assert 'integrate(' in C.answer('integrate(1/(x^5+x+1),x)')


def test_partial_fraction_shape():
    result = C.answer('partfrac(1/(x*(x+1)),x)')
    assert '+' in result or '-' in result
    assert result != '1/(x*(x+1))'
