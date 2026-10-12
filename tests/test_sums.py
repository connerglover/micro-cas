"""Finite/symbolic/infinite sums and exact Riemann sums against independent oracles."""
import pytest
import sympy

import node as K
import parse as P
import run as R
import sums as SU
from test_norm import drive, nd, to_sympy


@pytest.fixture(autouse=True)
def session(monkeypatch):
    for name, value in (('ANS', None), ('HIST', []), ('VARS', {}), ('FUNCS', {}),
                        ('MODS', {}), ('LOADED', []), ('USE', {}), ('PINNED', []),
                        ('LIVE', {}), ('NEEDED', []), ('CLOCK', [0])):
        monkeypatch.setattr(R, name, value)
    monkeypatch.setattr(R, 'SET', {'deg': 0, 'theme': 0})
    monkeypatch.setattr(P, 'SESS', R)
    R.need('sum')


@pytest.mark.oracle
@pytest.mark.parametrize('text,expected', [
    ('sum(k^2,k,1,10)', '385'), ('sum(k,k,-3,3)', '0'),
    ('sum(k^2,k,5,2)', '0'), ('sum(1/k,k,1,4)', '25/12'),
    ('sum((-1)^k/k!,k,0,8)', '14833/40320'),
    ('sum(k^2,k,1,n)', 'n*(n+1)*(2*n+1)/6'),
    ('sum(k,k,a,b)', '(b*(b+1)-a*(a-1))/2'),
    ('sum(k^3,k,1,n)', 'n^2*(n+1)^2/4'),
    ('sum(k^4,k,1,n)', 'n*(n+1)*(2*n+1)*(3*n^2+3*n-1)/30'),
    ('sum(2^k,k,0,n)', '2^(n+1)-1'),
    ('sum(k*2^k,k,1,n)', '(n-1)*2^(n+1)+2'),
    ('sum(k^2*2^k,k,0,n)', '(n^2-2*n+3)*2^(n+1)-6'),
    ('sum(1/(k*(k+1)),k,1,n)', 'n/(n+1)'),
    ('sum(1/(k*(k+2)),k,1,n)', '3/4-1/(2*(n+1))-1/(2*(n+2))'),
    ('sum(1/k-1/(k+1),k,1,n)', 'n/(n+1)'),
    ('sum(k,k,1,10000)', '50005000'),
    ('sum(i^2,i,1,5)', '55'),
])
def test_sum_oracle(text, expected):
    result = R.go(('eval', text))
    assert result[0] == 'ans', result
    actual, want = to_sympy(nd(result[1])), to_sympy(nd(expected))
    assert sympy.simplify(actual - want) == 0, result
    K.reset()


@pytest.mark.parametrize('text,expected', [
    ('sum(1/k^2,k,1,oo)', 'pi^2/6'), ('sum(1/k^4,k,1,oo)', 'pi^4/90'),
    ('sum(1/k^6,k,1,oo)', 'pi^6/945'), ('sum(1/k^8,k,1,oo)', 'pi^8/9450'),
    ('sum(1/k^2,k,3,oo)', 'pi^2/6-5/4'),
    ('sum((-1)^k/k,k,1,oo)', '-ln(2)'),
    ('sum((-1)^k/(2*k+1),k,0,oo)', 'pi/4'),
    ('sum(1/k!,k,0,oo)', 'e'), ('sum(x^k/k!,k,0,oo)', 'e^x'),
    ('sum(2^k/k!,k,2,oo)', 'e^2-3'),
    ('sum((1/2)^k,k,3,oo)', '1/4'),
    ('sum(k*(1/2)^k,k,1,oo)', '2'),
    ('sum((1/2)^k/k,k,1,oo)', 'ln(2)'),
    ('sum(0,k,1,oo)', '0'),
    ('sum(1/(k*(k+1)),k,1,oo)', '1'),
    ('sum(1/(k*(k+2)),k,1,oo)', '3/4'),
])
def test_known_infinite(text, expected):
    result = R.go(('eval', text))
    assert result[0] == 'ans', result
    actual, want = to_sympy(nd(result[1])), to_sympy(nd(expected))
    assert sympy.simplify(actual - want) == 0, result
    K.reset()


@pytest.mark.parametrize('text', ['sum(1/k,k,1,oo)', 'sum(1/sqrt(k),k,1,oo)'])
def test_p_series_diverges(text):
    result = R.go(('eval', text))
    assert result[0] == 'ans' and result[1] in ('oo', 'infinity'), result


@pytest.mark.parametrize('text', ['sum(2^k,k,0,oo)', 'sum((-1)^k,k,0,oo)',
                                 'sum(1,k,0,oo)', 'sum(k/(k+1),k,1,oo)',
                                 'sum(k^2,k,1,oo)'])
def test_terms_do_not_vanish(text):
    result = R.go(('eval', text))
    assert 'diverges' in result[1] and 'terms' in result[1], result


@pytest.mark.parametrize('text,expected', [
    ('sum((-1)^k/k^2,k,1,oo)', -sympy.pi**2/12),
    ('sum((-1)^k/k^3,k,1,oo)', -3*sympy.zeta(3)/4),
    ('sum((-1)^k/(k^2+1),k,0,oo)', (1+sympy.pi/sympy.sinh(sympy.pi))/2),
])
def test_tiny_approximate_term_limit_cannot_prove_divergence(text, expected):
    result = R.go(('eval', text))
    assert result[0] == 'ans', result
    if 'sum(' not in result[1]:
        assert float(to_sympy(nd(result[1]))) == pytest.approx(float(expected), abs=1e-9)
        K.reset()


@pytest.mark.parametrize('summand', ['sin(pi*k)', 'cos(2*pi*k)-1'])
def test_continuous_oscillation_cannot_prove_integer_term_divergence(summand):
    result = R.go(('eval', 'sum(' + summand + ',k,0,oo)'))
    assert result[0] == 'ans', result
    assert 'sum(' in result[1] or result[1] == '0', result


def test_certified_numeric_p_series():
    result = R.go(('eval', 'sum(1/k^3,k,1,oo)'))
    assert result[0] == 'ans', result
    assert result[3] & R.F_APPROX
    assert abs(float(result[1]) - float(sympy.zeta(3))) < 1e-9


@pytest.mark.parametrize('method,expected', [
    ('right', '15/32'), ('left', '7/32'), ('mid', '21/64'), ('trap', '11/32')])
def test_riemann_numeric(method, expected):
    result = R.go(('eval', 'riemann(x^2,x,0,1,4,' + method + ')'))
    assert result[0] == 'ans', result
    assert nd(result[1]) == nd(expected)
    K.reset()


@pytest.mark.parametrize('method,expected', [
    ('right', '(n+1)*(2*n+1)/(6*n^2)'), ('left', '(n-1)*(2*n-1)/(6*n^2)'),
    ('mid', '(4*n^2-1)/(12*n^2)'), ('trap', '(2*n^2+1)/(6*n^2)')])
def test_riemann_symbolic_and_limit(method, expected):
    result = R.go(('eval', 'riemann(x^2,x,0,1,n,' + method + ')'))
    assert result[0] == 'ans', result
    actual, want = to_sympy(nd(result[1])), to_sympy(nd(expected))
    assert sympy.simplify(actual - want) == 0, result
    n = sympy.Symbol('n', real=True)
    assert sympy.limit(actual, n, sympy.oo) == sympy.Rational(1, 3)
    K.reset()


@pytest.mark.parametrize('text', ['sum(k,k,1/2,3)', 'sum(k,k,1,k)',
                                  'riemann(x,x,0,1,0)', 'riemann(x,x,0,1,3/2)',
                                  'riemann(x,x,0,1,2,bad)', 'sum(x,2,0,4)'])
def test_invalid_arguments(text):
    result = R.go(('eval', text))
    assert result[0] == 'msg' and not result[1].startswith('internal error'), result


def test_unsupported_stays_unevaluated():
    result = R.go(('eval', 'sum(sin(k^2),k,1,n)'))
    assert result[0] == 'ans' and result[1].startswith('sum('), result


def test_long_loop_cancels(monkeypatch):
    monkeypatch.setattr(K, 'ESC', lambda: True)
    result = R.go(('eval', 'sum(sin(k),k,1,1000)'))
    assert result[0] == 'msg' and result[1] == 'Interrupted', result


def test_loop_region_keeps_bounded_arena():
    f, k = nd('k^2+2*k+1'), K.sym('k')
    mark = K.NN
    out = drive(R.MODS['sumb'].g_loop(f, k, 1, 1000))
    assert to_sympy(out) == sum((i + 1) ** 2 for i in range(1, 1001))
    assert K.NN - mark < 5


@pytest.mark.parametrize('text', [
    'sum(1/k!,k,0,999)', 'sum(1/(k^2+1),k,1,1000)',
    'sum(1/(k^2+1)+x,k,1,1000)', 'riemann(1/(1+x^2),x,0,1,1000)'])
def test_large_exact_accumulators_stay_formal_and_recover(text, monkeypatch):
    import signal
    import time

    def timeout(*args):
        raise AssertionError('exact accumulation exceeded its work budget')

    polls = []
    monkeypatch.setattr(K, 'ESC', lambda: polls.append(time.monotonic()) or False)
    old = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(5)
    try:
        result = R.go(('eval', text))
        assert result[0] == 'ans' and text.split('(')[0] + '(' in result[1], result
        assert not result[3] & R.F_APPROX
        assert len(polls) > 10
        assert max(b - a for a, b in zip(polls, polls[1:])) < 0.1
        assert R.go(('eval', '2+3'))[1] == '5'
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
