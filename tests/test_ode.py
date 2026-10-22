"""ODE residuals, independent exact solutions, resonance and initial conditions."""
import pytest
import sympy

import node as K
import parse as P
import run as R
import ode as OD
from test_norm import drive, nd, to_sympy


@pytest.fixture(autouse=True)
def session(monkeypatch):
    for name, value in (('ANS', None), ('HIST', []), ('VARS', {}), ('FUNCS', {}),
                        ('MODS', {}), ('LOADED', []), ('USE', {}), ('PINNED', []),
                        ('LIVE', {}), ('NEEDED', []), ('CLOCK', [0])):
        monkeypatch.setattr(R, name, value)
    monkeypatch.setattr(R, 'SET', {'deg': 0})
    monkeypatch.setattr(P, 'SESS', R)
    R.need('ode')


X, Y, YP, YPP = sympy.symbols("x y y' y''", real=True)


def residual(equation, sol):
    """Verify either an explicit solution or a first-order implicit solution."""
    eq = nd(equation)
    t = K.N[eq]
    f = to_sympy(t[1]) - to_sympy(t[2]) if t[0] == K.EQ else to_sympy(eq)
    t = K.N[sol]
    assert t[0] == K.EQ, t
    lhs, rhs = to_sympy(t[1]), to_sympy(t[2])
    if lhs == Y:
        value = rhs
        delta = f.subs({Y: value, YP: sympy.diff(value, X), YPP: sympy.diff(value, X, 2)}, simultaneous=True)
    else:
        implicit = lhs - rhs
        # On each domain interval d(log|u|)=u'/u; equilibrium zeros are separate answers.
        implicit = implicit.replace(
            lambda z: z.func == sympy.log and z.args[0].func == sympy.Abs,
            lambda z: sympy.log(z.args[0].args[0]))
        slope = -sympy.diff(implicit, X) / sympy.diff(implicit, Y)
        delta = f.subs(YP, slope)
    assert sympy.simplify(sympy.expand_trig(delta)) == 0, (f, lhs, rhs, delta)


@pytest.mark.oracle
@pytest.mark.parametrize('equation', [
    "y'=x*y", "y'+y=exp(x)", "y'+2*y=x", "y'=x", "y'=0",
    "y'+2*y/x=x^2", "y'=x*y^2", "y'=x*(1+y^2)", "y'+y=x*y^2",
    "y'=y*(1-y)", "y'=y^3", "y*y'=y",
    "y''+y=0", "y''-3*y'+2*y=0", "y''+2*y'+y=0", "y''=0",
    "y''-3*y'+2*y=exp(3*x)", "y''+y=sin(x)", "y''+y=cos(x)",
    "y''-2*y'+y=exp(x)", "y''+4*y=x^2", "y''=x^2",
    "y''+2*y'+5*y=exp(x)*cos(2*x)", "y''+y=x*sin(x)",
    "y''+y=cos(2*x+1)", "y''+y=sin(2*x+1)",
    "2*y''+3*y'+y=x^2+sin(x)", "y''+y=exp(x)+x+cos(2*x)",
])
def test_general_solution_residual(equation):
    result = R.go(('eval', 'desolve(' + equation + ',y)'))
    assert result[0] == 'ans' and 'desolve(' not in result[1], result
    out = nd(result[1])
    sols = K.N[out][1:] if K.N[out][0] == K.LST else (out,)
    assert sols
    for sol in sols:
        residual(equation, sol)
    K.reset()


@pytest.mark.parametrize('text,expected', [
    ("desolve([y'=x*y,y(0)=2],y)", '2*exp(x^2/2)'),
    ("desolve([y'+y=exp(x),y(0)=1],y)", '(exp(x)+exp(-x))/2'),
    ("desolve([y''+y=0,y(0)=1,y'(0)=0],y)", 'cos(x)'),
    ("desolve([y''+4*y=0,y(0)=0,y'(0)=2],y)", 'sin(2*x)'),
    ("desolve([y''+2*y'+y=0,y(0)=1,y'(0)=0],y)", '(1+x)*exp(-x)'),
    ("desolve([y''+y=sin(x),y(0)=0,y'(0)=0],y)", '(sin(x)-x*cos(x))/2'),
    ("desolve([y''=2,y(1)=3,y'(1)=4],y)", 'x^2+2*x'),
    ("desolve([y'=y^2,y(0)=0],y)", '0'),
    ("desolve([y'+y=x*y^2,y(0)=0],y)", '0'),
    ("desolve([y'=y*(1-y),y(0)=1],y)", '1'),
])
def test_initial_conditions(text, expected):
    result = R.go(('eval', text))
    assert result[0] == 'ans', result
    out = nd(result[1])
    assert K.N[out][0] == K.EQ, result
    assert sympy.simplify(to_sympy(K.N[out][2]) - to_sympy(nd(expected))) == 0, result
    K.reset()


def test_implicit_initial_condition():
    result = R.go(('eval', "desolve([y'=x*y^2,y(0)=1],y)"))
    assert result[0] == 'ans' and 'C1' not in result[1], result
    out = nd(result[1])
    residual("y'=x*y^2", out)
    lhs, rhs = K.N[out][1:]
    value = (to_sympy(lhs) - to_sympy(rhs)).subs({X: 0, Y: 1})
    assert sympy.simplify(value) == 0
    K.reset()


def test_inconsistent_initial_conditions():
    result = R.go(('eval', "desolve([y'=y,y(0)=1,y(0)=2],y)"))
    assert result[0] == 'msg' and result[1] == 'No solution', result


def test_independent_variable_three_argument_form():
    result = R.go(('eval', "desolve([y'=t*y,y(0)=1],t,y)"))
    assert result[0] == 'ans', result
    out = nd(result[1])
    assert sympy.simplify(to_sympy(K.N[out][2]) - to_sympy(nd('exp(t^2/2)'))) == 0
    K.reset()


@pytest.mark.parametrize('text', ["desolve(y''+x*y=0,y)", "desolve(y'^2+y=0,y)",
                                  "desolve(y''+y=exp(x^2),y)", "desolve(y'''+y=0,y)",
                                  "desolve(y'''+y'=0,y)"])
def test_unsupported_is_held(text):
    result = R.go(('eval', text))
    assert result[0] == 'ans' and result[1].startswith('desolve('), result


def test_invalid_condition():
    result = R.go(('eval', "desolve([y'=y,y(x)=1],y)"))
    assert result[0] == 'msg' and not result[1].startswith('Internal error'), result


@pytest.mark.parametrize('equation', ["y'=y^3", "y*y'=y"])
def test_division_does_not_lose_equilibrium(equation):
    result = R.go(('eval', 'desolve([' + equation + ',y(0)=0],y)'))
    assert result[0] == 'ans', result
    out = nd(result[1])
    sols = K.N[out][1:] if K.N[out][0] == K.LST else (out,)
    assert nd('y=0') in sols
    K.reset()


@pytest.mark.oracle
@pytest.mark.parametrize('equation, zero', [
    ("y'+y=x*y^3", True),
    ("y'+y=(x+1)*y^3", True),
    ("y'+y=x/y", False),
    ("y'+y=x*y^(1/2)", True),
    ("y'+y=x*y^2", True),
])
def test_bernoulli_rational_exponents(equation, zero):
    result = R.go(('eval', 'desolve(' + equation + ',y)'))
    assert result[0] == 'ans' and 'desolve(' not in result[1], result
    out = nd(result[1])
    sols = K.N[out][1:] if K.N[out][0] == K.LST else (out,)
    assert (nd('y=0') in sols) == zero
    for sol in sols:
        residual(equation, sol)
    if '^2' in equation:
        assert all(K.N[sol][1] == nd('y') for sol in sols)
    else:
        assert any(K.N[sol][1] != nd('y') for sol in sols)
    K.reset()


@pytest.mark.parametrize('initial', ('1', '-1'))
def test_cubic_bernoulli_initial_condition_keeps_both_real_branches(initial):
    equation = "y'+y=x*y^3"
    result = R.go(('eval', 'desolve([' + equation + ',y(0)=' + initial + '],y)'))
    assert result[0] == 'ans' and 'desolve(' not in result[1] and 'C1' not in result[1], result
    out = nd(result[1])
    assert K.N[out][0] == K.EQ, result
    residual(equation, out)
    lhs, rhs = K.N[out][1:]
    assert sympy.simplify((to_sympy(lhs) - to_sympy(rhs)).subs({X: 0, Y: int(initial)})) == 0
    K.reset()


def test_cubic_bernoulli_zero_initial_condition_retains_equilibrium():
    result = R.go(('eval', "desolve([y'+y=x*y^3,y(0)=0],y)"))
    assert result[0] == 'ans' and nd(result[1]) == nd('y=0'), result
    K.reset()


@pytest.mark.parametrize('equation', ("y'+y=x*y^3+x^2*y^2", "y'+y=x*y^a"))
def test_non_bernoulli_exponents_remain_held(equation):
    result = R.go(('eval', 'desolve(' + equation + ',y)'))
    assert result[0] == 'ans' and result[1].startswith('desolve('), result
