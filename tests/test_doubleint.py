"""Bounded product quadrature for held inner definite integrals."""
import mpmath as M
import pytest

import alg as A
import node as K
import run as R
import cascheck as C
from test_diff import drive, nd


@pytest.fixture(autouse=True)
def session():
    C.fresh()
    R.need('def')


@pytest.mark.parametrize('inner,a,b,expected', [
    ('integrate(exp(x*y^2),y,0,1)', '0', '1',
     float(M.fsum(1/(M.factorial(j)*(j+1)*(2*j+1)) for j in range(30)))),
    ('integrate(exp(y^2),y,0,x)', '0', '1', .603510831677659),
    ('integrate(exp(y^2),y,0,x)', '1', '0', -.603510831677659),
    ('integrate(exp(y^2),y,x,0)', '0', '1', -.603510831677659),
    ('integrate(x*y,y,x,x^2)', '0', '1', -1/24),
    ('integrate(x+y,y,0,1)', '2', '3', 3),
])
def test_product_quadrature(inner, a, b, expected):
    result = drive(R.MODS['defb'].g_double(nd(inner), K.sym('x'), nd(a), nd(b)))
    assert result is not None and K.N[result][0] == K.FLT
    assert K.N[result][1] == pytest.approx(expected, abs=2e-8)


@pytest.mark.parametrize('inner,a,b', [
    ('x', '0', '1'),
    ('integrate(exp(x^2),x,0,1)', '0', '1'),
    ('integrate(exp(y^2),y,y,1)', '0', '1'),
    ('integrate(exp(y^2),y,0,z)', '0', '1'),
    ('integrate(f(y),y,0,1)', '0', '1'),
    ('integrate(sqrt(y-2),y,0,1)', '0', '1'),
    ('integrate(exp(y^2),y,0,1)', '0', 'oo'),
    ('integrate(1/(x-y)^2,y,0,1)', '0', '1'),
    ('integrate(exp(100*x*y^2),y,0,1)', '0', '1'),
    ('integrate(exp(-100000000*(x-1/10)^2-y^2),y,0,1)', '0', '1'),
])
def test_unavailable_or_unconverged_product_is_held(inner, a, b):
    assert drive(R.MODS['defb'].g_double(nd(inner), K.sym('x'), nd(a), nd(b))) is None


def test_product_evaluation_budget(monkeypatch):
    original, calls = A.nrun, [0]
    def counted(*args):
        calls[0] += 1
        return original(*args)
    monkeypatch.setattr(A, 'nrun', counted)
    result = drive(R.MODS['defb'].g_double(nd('integrate(exp(x*y^2),y,0,1)'),
                                         K.sym('x'), K.ZERO, K.ONE))
    assert result is not None
    assert calls[0] <= 170
