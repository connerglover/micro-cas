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


# Integrals that came back unevaluated up to 1.1.0 (the user's report, 2026-11-16): no strategy
# reached them. The points are the x at which the integrand is real; the primitive must
# differentiate to it at each one, on either side of 0 where the integrand lives there.
CHANGES = [
    # t = (a*x+b)^(1/n)
    ('e^sqrt(x)', (2, 5)), ('sin(sqrt(x))', (2, 5)), ('sqrt(x)/(1+x)', (2, 5)),
    ('1/(sqrt(x)+1)', (2, 5)), ('sqrt(1+sqrt(x))', (2, 5)), ('atan(sqrt(x))', (2, 5)),
    ('1/(x^(1/3)+sqrt(x))', (2, 5)), ('1/(1+x^(1/3))', (2, 5)),
    # t = x^n
    ('x^3*e^(x^2)', (-2, 3)), ('x^5*sqrt(x^3+1)', (2, 3)), ('x/(x^4+1)', (-2, 3)),
    ('x^2/(1+x^6)', (-2, 3)), ('x*sqrt(1-x^4)', (-3, 4)), ('1/(x*sqrt(x^2-1))', (-9, 8)),
    ('sqrt(x^2-9)/x', (-29, 31)), ('sqrt(x^2+1)/x', (-2, 3)), ('1/(x^3*sqrt(x^2-1))', (-9, 8)),
    # t = e^(a*x)
    ('e^x/(e^(2*x)+1)', (-2, 3)), ('1/(e^x+e^(-x))', (-2, 3)), ('sqrt(e^x+1)', (-2, 3)),
    ('e^(3*x)/(e^x+1)', (-2, 3)), ('1/(e^(x/2)+1)', (-2, 3)), ('1/sqrt(e^x-1)', (2, 3)),
    # t = ln(x)
    ('sin(ln(x))', (2, 5)),
    # t = 1/x under a square root of a quadratic
    ('1/(x^2*sqrt(x^2+4))', (-2, 3)), ('1/(1-x^2)^(3/2)', (-3, 4)),
    ('1/(x^2+1)^(3/2)', (-2, 3)), ('sqrt(4-x^2)/x^2', (-3, 4)), ('sqrt(1-x^2)/x^4', (-3, 4)),
    ('1/(x^2*sqrt(9-x^2))', (-3, 4)), ('x^2/(x^2+4)^(3/2)', (-2, 3)),
    ('sqrt(x^2+1)/x^2', (-2, 3)),
    # hyperbolic functions, as exponentials
    ('sinh(x)^2', (-2, 3)), ('x*cosh(x)', (-2, 3)), ('cosh(x)^3', (-2, 3)),
    ('e^x*sinh(x)', (-2, 3)),
    # multiplied out
    ('x*(e^x+e^(-x))/2', (-2, 3)), ('(e^x-e^(-x))^2/4', (-2, 3)),
    # a quadratic that the canonical form keeps with a sign: -(-x^2+x-1)
    ('1/(x^3+1)', (2, 3)), ('(x-2)/(x^2-x+1)', (-2, 3)),
    # u = x beside a factor of the table
    ('x*sec(x)^2', (-2, 3)),
]


@pytest.mark.parametrize('f,points', CHANGES)
def test_change_of_variable(f, points):
    result = C.answer('integrate(' + f + ',x)')
    assert 'integrate(' not in result, (f, result)
    assert '_w' not in result, (f, result)              # no private variable in an answer
    x = S.Symbol('x', real=True)
    delta = S.diff(C.sx(result), x) - C.sx(f)
    for p in points:
        point = S.Rational(p, 7 if abs(p) < 9 else 8)
        assert abs(complex(delta.subs(x, point).evalf(30))) < 1e-8, (f, result, point)


def test_a_change_valid_for_positive_x_keeps_no_abs():
    # t = x^2 and t = 1/x hold for x > 0; the primitive is written in x and the roots of the
    # integrand, never with sqrt(x^2) = abs(x), which is wrong left of 0
    for f in ('1/(1-x^2)^(3/2)', 'sqrt(1-x^2)/x^4', '1/(x^2*sqrt(x^2+4))'):
        assert 'abs(' not in C.answer('integrate(' + f + ',x)'), f


@pytest.mark.parametrize('f', ['e^(-x^2)', 'sin(x)/x', 'x^x', 'sqrt(1+x^3)', 'e^x/x',
                               '1/ln(x)', 'cos(x^2)', 'sqrt(sin(x))', 'x*tan(x)'])
def test_no_elementary_primitive_stays_an_integral(f):
    assert 'integrate(' in C.answer('integrate(' + f + ',x)')


def test_unsupported_stays_an_integral():
    assert 'integrate(' in C.answer('integrate(1/(x^5+x+1),x)')


def test_partial_fraction_shape():
    result = C.answer('partfrac(1/(x*(x+1)),x)')
    assert '+' in result or '-' in result
    assert result != '1/(x*(x+1))'
