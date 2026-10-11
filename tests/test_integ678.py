"""T2.6 parts, quadratic radicals and rational substitutions."""
import pytest
import sympy as S
import run as R
import cascheck as C


@pytest.fixture(autouse=True)
def session(monkeypatch):
    C.fresh()
    m = R.need('int')


@pytest.mark.parametrize('f', [
    'x*ln(x)', 'x^3*ln(x)', 'ln(x)^2', 'x*atan(x)',
    'e^x*sin(x)', 'e^(2*x)*cos(3*x)',
    'sqrt(1-x^2)', 'x*sqrt(x+1)', '1/sqrt(x^2+4)',
    'x^2/sqrt(1-x^2)', 'sqrt(4-x^2)', 'x^3/sqrt(x^2+1)',
    '1/(2+cos(x))', '1/(3+sin(2*x))', 'e^x/(1+e^x)',
])
def test_primitive(f):
    out = C.answer('integrate(' + f + ',x)')
    assert 'integrate(' not in out, out
    x = S.Symbol('x', real=True)
    d = S.diff(C.sx(out), x) - C.sx(f)
    for v in (S.Rational(1, 5), S.Rational(2, 5), S.Rational(4, 5)):
        assert abs(complex(d.subs(x, v).evalf(30))) < 1e-9, (f, out, d)
