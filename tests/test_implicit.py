"""Implicit differentiation: diff of an equation (docs/STATUS.md).

diff(l=r, x, [y or n]) is dy/dx of the curve l=r, -F_x/F_y with F = l-r; an order above 1
differentiates the last one again along the curve. SymPy's idiff is the oracle.
"""
import pytest
import sympy as S

import cascheck as C
import node as K
import run as R

X, Y, T, RR = S.symbols('x y t r')
NAMES = {'x': X, 'y': Y, 't': T, 'r': RR, 'e': S.E}


@pytest.fixture(autouse=True)
def session():
    C.fresh()
    del R.STEPS[:]
    yield


def ans(text):
    rec = R.go(('eval', text))
    assert rec[0] == 'ans', (text, rec)
    return rec[1]


def expr(text):
    return S.sympify(text.replace('^', '**'), locals=NAMES)


@pytest.mark.parametrize('eq, order', [
    ('2*y+6*x=0', 1), ('x^2+y^2=25', 1), ('x^2+y^2=25', 2), ('x^3+y^3=6*x*y', 1),
    ('sin(x*y)=x', 1), ('e^y=x', 2), ('x*y=1', 3), ('y=x^2', 1), ('y^2=x^3+x', 2),
    ('x^2+y^2=r^2', 1), ('cos(y)+x*y=x^2', 1)])
def test_matches_the_implicit_derivative(eq, order):
    left, right = eq.split('=')
    want = S.idiff(expr(left) - expr(right), Y, X, order)
    got = expr(ans('diff(' + eq + ',x' + (',%d' % order if order > 1 else '') + ')'))
    assert S.simplify(got - want) == 0, (eq, order, got, want)


def test_the_users_example():
    assert ans('diff(2y+6x=0,x)') == '-3'
    assert ans('diff(x^2+y^2=25,x)') == '-x/y'


def test_the_dependent_variable():
    assert ans('diff(x^2+y^2=25)') == '-x/y'            # x is the default variable
    assert ans('diff(x^2+y^2=25,y)') == '-y/x'          # the only other one depends on y
    assert ans('diff(x^2+t^2=r^2,x,t)') == '-x/t'       # named
    assert ans('diff(x^2+y^2=r^2,x)') == '-x/y'         # several others: y
    assert ans('diff(x^2+y^2=25,x,y)') == '-x/y'


@pytest.mark.parametrize('text, message', [
    ('diff(x^2+t^2=r^2,x)', 'Which variable? diff(eq,x,y)'),    # t or r?
    ('diff(x^2=4,x)', 'Which variable? diff(eq,x,y)'),          # nothing depends on x
    ('diff(x^2+y^2=25,x,x)', 'Invalid argument'),
    ('diff(x^2+y^2=25,x,0)', 'Invalid argument'),
    ('diff(x^2+y^2=25,x,1/2)', 'Invalid argument'),
    ('diff(x^2+r^2=25,x,y)', 'Invalid argument'),               # F_y = 0
    ('diff(sin(y)^2+cos(y)^2=x,x)', 'Invalid argument')])       # F_y = 0 after simplifying
def test_no_derivative_is_a_message(text, message):
    assert R.go(('eval', text))[:2] == ('msg', message)
    assert K.NN == K.BASE


def test_other_relations_and_expressions_are_unchanged():
    assert ans('diff(x^2+y^2<25,x)') == 'diff(x^2+y^2<25,x)'
    assert ans('diff(x^2+y^2,x)') == '2*x'
    assert ans('diff(x^3,x,2)') == '6*x'


def steps(text):
    ans(text)
    rec = R.go(('steps', len(R.HIST) - 1))
    assert rec[0] == 'ans', rec
    out = R.STEPS[1:]
    del R.STEPS[:]
    return out


def test_steps_differentiate_both_sides_and_solve():
    assert steps('diff(x^2+y^2=25,x)') == [
        ('Differentiate both sides', 'diff(x^2+y^2,x)=diff(25,x)'),
        ('Chain rule: y depends on x', '2*x+2*y*diff(y,x)=0'),
        ('Solve for the derivative', 'diff(y,x)=-x/y'),
        ('Answer', 'diff(y,x)=-x/y')]
    got = steps('diff(x^2+y^2=25,x,2)')
    assert [s[0] for s in got] == ['Differentiate both sides', 'Chain rule: y depends on x',
                                   'Solve for the derivative', 'Differentiate again', 'Answer']
    assert got[-1][1] == 'diff(diff(y,x),x)=-(x^2+y^2)/y^3'
    assert steps('diff(x^2+t^2=r^2,x,t)')[1][0] == 'Chain rule: t depends on x'
