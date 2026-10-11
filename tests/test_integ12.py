"""T2.4 table and substitution acceptance through the real command dispatcher."""
import pytest
import sympy as S
import run as R
import cascheck as C


@pytest.fixture(autouse=True)
def session(monkeypatch):
    C.fresh()
    yield


@pytest.mark.parametrize('integrand', [
    'x^2', '1/x', 'e^(3*x)', 'sec(2*x)^2', 'sec(x)^3',
    'sin(3*x+1)', 'cos(2*x)', 'tan(x)', 'csc(x)', 'cot(x)',
    '2*x*cos(x^2)', 'cos(3*x)*(2+sin(3*x))^4', 'x/(x^2+1)',
    'ln(x)', 'asin(x)', 'acos(x)', 'atan(x)', 'sinh(x)', 'cosh(x)',
    'pi^x', 'x^n', 'abs(2*x-1)',
])
def test_antiderivative(integrand):
    result = C.answer('integrate(' + integrand + ',x)')
    assert 'integrate(' not in result, (integrand, result)
    x = S.Symbol('x', real=True)
    delta = S.diff(C.sx(result), x) - C.sx(integrand)
    for pt in (S.Rational(2, 5), S.Rational(3, 5), S.Rational(4, 5)):
        env = {v: pt if v == x else S.Rational(5, 2) for v in delta.free_symbols}
        assert abs(complex(delta.subs(env).evalf(30))) < 1e-9, (integrand, result, delta)


def test_failure_stays_unevaluated():
    assert 'integrate(' in C.answer('integrate(e^(x^2),x)')


def test_constant_and_sum():
    C.equivalent(C.answer('integrate(3*x^2+2*x+7,x)'), 'x^3+x^2+7*x')


def test_degree_mode():
    R.SET['deg'] = 1
    result = C.answer('integrate(cos(x),x)')
    assert 'integrate(' not in result
    assert '180' in result and 'pi' in result
