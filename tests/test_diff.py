"""T2.1 and T3.5: exact derivative fold, FTC and gradient, through the real loader."""
import math
from pathlib import Path
import types

import pytest
import sympy as S

import alg as A
import node as K
import parse as P
import printer as PR
import run as R


@pytest.fixture(autouse=True)
def session(monkeypatch):
    for name, value in (('ANS', None), ('HIST', []), ('VARS', {}), ('FUNCS', {}),
                        ('MODS', {}), ('LOADED', []), ('USE', {}), ('PINNED', []),
                        ('LIVE', {}), ('NEEDED', []), ('CLOCK', [0])):
        monkeypatch.setattr(R, name, value)
    monkeypatch.setattr(R, 'SET', {'deg': 0})
    monkeypatch.setattr(P, 'SESS', R)
    R.need('diff')


def drive(g):
    stack, marks, value = [g], [-1], None
    while stack:
        try:
            result = stack[-1].send(value)
        except StopIteration:
            result = None
        if result is R.TICK:
            value = None
            continue
        if isinstance(result, types.GeneratorType):
            stack.append(result)
            marks.append(-1)
            value = None
            continue
        if type(result) is tuple and len(result) == 2 and result[0] is R.SCOPE:
            stack.append(result[1])
            marks.append(K.NN)
            value = None
            continue
        stack.pop()
        mark = marks.pop()
        value = K.keep(mark, result) if mark >= 0 else result
    return value


def nd(text, deg=0):
    return drive(P.g_eval(P.rpn(P.tokens(text, 0)), [deg, None, 0, 1]))


def deriv(text, order=1, deg=0, variable='x'):
    return drive(R.MODS['diff'].g_diff((nd(text, deg), K.sym(variable), K.num(order)),
                                     [deg, None, 0, 0]))


def numeric(node, point=0.37):
    return A.nrun(A.nprog(node, (K.sym('x'),)), (point,))


def symbolic(node):
    """Use the printer round trip for the SymPy oracle, with real symbols."""
    text = PR.text(node, (0, None, 0, 0)).replace('^', '**')
    names = {'ln': S.log, 'log': lambda a: S.log(a, 10), 'abs': S.Abs,
             'sign': S.sign, 'ceil': S.ceiling, 'pi': S.pi, 'e': S.E, 'i': S.I}
    for name in ('x', 'y', 'z', 't', 'a', 'b'):
        names[name] = S.Symbol(name, real=True)
    return S.sympify(text, locals=names)


@pytest.mark.oracle
@pytest.mark.parametrize('text', [
    'sin(x)', 'cos(x)', 'tan(x)', 'sec(x)', 'csc(x)', 'cot(x)',
    'asin(x)', 'acos(x)', 'atan(x)', 'sinh(x)', 'cosh(x)', 'tanh(x)',
    'ln(x)', 'log(x)', 'log(x,2)', 'exp(x)', 'sqrt(x)', 'abs(x)',
    'asinh(x)', 'acosh(x+2)', 'atanh(x)', 'asec(x+2)', 'acsc(x+2)', 'acot(x)',
    'sin(x^2+2x)', '(x+1)^3*(x-2)^4', 'x^x', '(x^2+1)^(sin(x))',
    'ln(sec(x)+tan(x))', 'ln(abs(x))', 'surd(x,3)', '1/(1+x^2)',
])
def test_elementary_oracle(text):
    original = nd(text)
    expect = S.diff(symbolic(original), S.Symbol('x', real=True))
    actual = drive(R.MODS['diff'].g_deriv(original, K.sym('x')))
    for point in (0.23, 0.61, 0.83):
        oracle = complex(expect.subs(S.Symbol('x', real=True), point).evalf())
        assert complex(numeric(actual, point)) == pytest.approx(oracle, rel=1e-9, abs=1e-9)


@pytest.mark.parametrize('name', ['sign', 'floor', 'ceil'])
def test_piecewise_constant_functions(name):
    assert deriv(name + '(x)') == K.ZERO


def test_nth_derivative_and_constant():
    result = deriv('sin(x)/x', 2)
    x = S.Symbol('x', real=True)
    assert S.simplify(symbolic(result) - S.diff(S.sin(x)/x, x, 2)) == 0
    assert deriv('x^20', 20) == K.num(math.factorial(20))
    assert deriv('x^3', 0) == nd('x^3')
    assert deriv('sin(y)+7') == K.ZERO


@pytest.mark.parametrize('order', ['-1', '21', '1/2', 'i', 'x'])
def test_invalid_order(order):
    with pytest.raises(K.CasError):
        drive(R.MODS['diff'].g_diff((nd('x^2'), K.sym('x'), nd(order)), [0, None, 0, 0]))


def test_invalid_variable():
    with pytest.raises(K.CasError):
        drive(R.MODS['diff'].g_diff((nd('x^2'), nd('x+1')), [0, None, 0, 0]))


@pytest.mark.parametrize('source,expected', [
    ('integrate(sin(t^2),t,0,x^2)', '2*x*sin(x^4)'),
    ('integrate(exp(t),t,x,2*x)', '2*exp(2*x)-exp(x)'),
    ('integrate(sin(x^2),x,0,x^2)', '2*x*sin(x^4)'),
    ('integrate(sin(x^2),x)', 'sin(x^2)'),
])
def test_fundamental_theorem(source, expected):
    result = drive(R.MODS['diff'].g_deriv(nd(source), K.sym('x')))
    assert S.simplify(symbolic(result) - symbolic(nd(expected))) == 0


def test_leibniz_preserves_partial_integrand():
    result = drive(R.MODS['diff'].g_deriv(nd('integrate(x*t,t,0,x)'), K.sym('x')))
    expected = nd('x^2+integrate(t,t,0,x)')
    assert result == expected


def test_unknown_functions_remain_derivatives():
    source = nd('f(x)')
    x = K.sym('x')
    result = drive(R.MODS['diff'].g_deriv(source, x))
    assert K.N[result] == (K.CALL, K.sym('diff'), source, x)
    assert drive(R.MODS['diff'].g_deriv(nd('f(y)'), x)) == K.ZERO


@pytest.mark.parametrize('text,point,expected', [
    ('sin(x)', 30, math.pi / 180 * math.cos(math.pi / 6)),
    ('asin(x)', 0.5, 180 / math.pi / math.sqrt(0.75)),
    ('cos(2*x)', 20, -2 * math.pi / 180 * math.sin(40 * math.pi / 180)),
])
def test_degree_mode_is_encoded_in_expression(text, point, expected):
    assert numeric(deriv(text, deg=1), point) == pytest.approx(expected)


def test_gradient():
    args = (nd('x*y^2+sin(z)'), nd('[x,y,z]'))
    result = drive(R.MODS['diff'].g_grad(args, [0, None, 0, 0]))
    assert K.N[result][0] == K.LST
    assert tuple(symbolic(i) for i in K.N[result][1:]) == tuple(
        symbolic(nd(s)) for s in ('y^2', '2*x*y', 'cos(z)'))


def test_default_variable_and_gradient():
    assert drive(R.MODS['diff'].g_diff((nd('y^2'),), [0, None, 0, 0])) == nd('2*y')
    result = drive(R.MODS['diff'].g_grad((nd('y+x^2'),), [0, None, 0, 0]))
    assert K.N[result] == (K.LST, nd('2*x'), K.ONE)


@pytest.mark.parametrize('source', ['diff(x^3,x)', 'deriv(x^3,x)', 'd(x^3,x)'])
def test_command_pipeline(source):
    assert R.go(('eval', source))[:2] == ('ans', '3*x^2')


def test_gradient_command_pipeline():
    assert R.go(('eval', 'grad(x*y,[x,y])'))[:2] == ('ans', '[y,x]')


def test_algorithm_gradient_seed():
    result = drive(R.MODS['diff'].g_grad((nd('x^2*y+sin(z)'),), [0, None, 0, 0]))
    assert K.N[result] == (K.LST, nd('2*x*y'), nd('x^2'), nd('cos(z)'))


@pytest.mark.parametrize('text', ['abs(x)', 'ln(abs(x))', 'surd(x,3)', 'x^(-2)', '(x-1)^3'])
def test_negative_real_domain(text):
    original = nd(text)
    result = drive(R.MODS['diff'].g_deriv(original, K.sym('x')))
    for point in (-2.7, -1.4, -0.43):
        h = 1e-5
        expected = (numeric(original, point+h)-numeric(original, point-h))/(2*h)
        assert numeric(result, point) == pytest.approx(expected, rel=1e-7, abs=1e-7)


def test_nested_derivative_keeps_fixed_call_depth():
    expression = K.sym('x')
    for _ in range(28):
        expression = K.fn_(K.SIN, expression)
    result = drive(R.MODS['diff'].g_deriv(expression, K.sym('x')))
    h = 1e-5
    expected = (numeric(expression, 0.4+h)-numeric(expression, 0.4-h))/(2*h)
    assert numeric(result, 0.4) == pytest.approx(expected, rel=1e-7)


def test_vector_derivative_preserves_constant_components():
    assert K.N[deriv('[3,y]')] == (K.LST, K.ZERO, K.ZERO)
    assert K.N[deriv('[x,x^2]')] == (K.LST, K.ONE, nd('2*x'))


@pytest.mark.parametrize('variables', ['x', '[x,2]', '[x,x+1]'])
def test_gradient_rejects_nonvariables(variables):
    with pytest.raises(K.CasError):
        drive(R.MODS['diff'].g_grad((nd('x^2'), nd(variables)), [0, None, 0, 0]))


def test_module_fits_lazy_part():
    from build.bundle import minify
    source = Path(__file__).resolve().parents[1] / 'src' / 'diff.py'
    assert len(minify(source.read_text(), 'diff').lines) <= 150
