"""Giant numbers stay written as powers (DESIGN 5.3, 6.1).

A prime power q^n folds into an exact number when its weight 4*|n|*hexlen(q) is at most MAXBITS
(the npowi size estimate, prime by prime); otherwise q keeps its whole exponent as a MUL pair
(and if the folding weights over MAXBITS/16 total more than MAXFOLD, those primes stay whole
too). Primes with equal exponents share one base (rule 11), and no coefficient holds a factor
of a kept base. So 2^16384 is still an integer while 2^16385,
3^(2^20), 7^7^7 and 10^100000 are exact powers instead of 'number too large', and products,
quotients and sums of them stay canonical. A power has no float value: no decimal line, and
approx keeps it exact. The conftest invariant scan checks every node these tests build.
"""
import random
import time
import types
from fractions import Fraction

import pytest

import alg as A
import node as K
import nodeb as KB
import normb as NB
import parse as P
import printer as PR
import run as R

FRESH = (('ANS', None), ('HIST', list), ('VARS', dict), ('FUNCS', dict), ('MODS', dict),
         ('LOADED', list), ('USE', dict), ('PINNED', list), ('LIVE', dict), ('NEEDED', list))


@pytest.fixture(autouse=True)
def sess(monkeypatch):
    """A fresh session with the real lazy modules; P.SESS = R (as tests/test_norm.py)."""
    for name, make in FRESH:
        monkeypatch.setattr(R, name, make() if make is not None else None)
    monkeypatch.setattr(R, 'SET', {'deg': 0, 'theme': 0})
    monkeypatch.setattr(R, 'CLOCK', [0])
    monkeypatch.setattr(P, 'SESS', R)
    R.need('norm')
    yield


def drive(g):
    """The trampoline of DESIGN 10.4 without the runner (regions, TICK, CasSoft -> None)."""
    stack = [g]
    marks = [-1]
    val = None
    while stack:
        try:
            y = stack[-1].send(val)
        except StopIteration:
            y = None
        except K.CasSoft:
            y = None
        else:
            if y is R.TICK:
                val = None
                continue
            if isinstance(y, types.GeneratorType):
                stack.append(y)
                marks.append(-1)
                val = None
                continue
            if type(y) is tuple and len(y) == 2 and y[0] is R.SCOPE:
                stack.append(y[1])
                marks.append(K.NN)
                val = None
                continue
        stack.pop()
        m = marks.pop()
        if m >= 0:
            y = K.keep(m, y)
        val = y
    return val


def nd(s):
    """The node of s as typed: the answer path (stages 3-5 and 7, g_eval inert)."""
    return drive(P.g_eval(P.rpn(P.tokens(s, 0)), [0, None, 0, 1]))


def go(s):
    t0 = time.perf_counter()
    r = R.go(('eval', s))
    assert time.perf_counter() - t0 < 1.0, (s, 'slow')
    return r


def ans(s):
    r = go(s)
    assert r[0] == 'ans', (s, r)
    return r[1]


def num(n, d=1):
    return K.num(n, 0, d)


# -- the task's cases ------------------------------------------------------------------------------

def test_giant_powers_are_exact_powers_at_once():
    assert ans('2^10000') == str(2 ** 10000)                   # 3,011 digits, as before
    assert ans('2^100') == str(2 ** 100)
    for s, want in (('3^(2^20)', '3^1048576'), ('7^7^7', '7^823543'),
                    ('2^100000*x', '2^100000*x'), ('2^(10^6)', '2^1000000'),
                    ('2^(10^100)', '2^' + str(10 ** 100)), ('10^100000', '10^100000'),
                    ('-3^100000', '-3^100000'), ('1/2^100000', '1/2^100000')):
        assert ans(s) == want, s


def test_the_fold_limit_is_the_old_npowi_limit():
    """b^n of a prime b folds exactly when npowi folded it: 4*n*hexlen(b) <= MAXBITS."""
    for b, n in ((2, 16384), (3, 16384), (13, 16384), (17, 8192), (257, 5461)):
        e = nd('%d^%d' % (b, n))
        assert K.N[e] == (K.NUM, b ** n, 0, 1), b
        e = nd('%d^%d' % (b, n + 1))
        assert K.N[e] == (K.MUL, K.ONE, num(b), num(n + 1)), b
    assert K.N[nd('10^16384')][1] == 10 ** 16384               # 2 and 5 decide alike
    assert K.N[nd('10^16385')] == (K.MUL, K.ONE, num(10), num(16385))
    assert go('2^16384') == ('msg', 'Done', None, 0)           # an integer of 4,933 digits
    assert ans('2^16385') == '2^16385'


# -- canonical form ---------------------------------------------------------------------------------

SAME = [
    ('2^100000*2', '2^100001'), ('2^100000/2', '2^99999'), ('2^100000/2^99999', '2'),
    ('2*2^100000-2^100001', '0'), ('2^100000-2^100000', '0'), ('4^50000', '2^100000'),
    ('6^100000', '2^100000*3^100000'), ('2^100000*3', '3*2^100000'),
    ('2^100000+2^100000', '2^100001'), ('3^100000+3^100000+3^100000', '3^100001'),
    ('x*2^100000+x*2^100000', 'x*2^100001'), ('2*(2^100000+1)+x', 'x+2^100001+2'),
    ('2^10000*2^10000', '2^20000'), ('16^5000', '2^20000'), ('(4^8193)', '2^16386'),
    ('(2^100000)^(1/2)', '2^50000'), ('(2^100000*3^100000)^(1/2)', '6^50000'),
    ('sqrt(2)*2^100000', '2^(200001/2)'), ('sqrt(2^100001)', '2^(100001/2)'),
    ('(2/3)^100000', '2^100000/3^100000'), ('(-2)^100001', '-2^100001'),
    ('(-2)^100000', '2^100000'), ('12^100000/3^100000', '4^100000'),
    ('10^16000*10^14000', '10^30000'), ('(257^2)^3000', '257^6000'),
    ('(2*i)^100000', '2^100000'), ('0^100000', '0'), ('1^(10^100)', '1'),
    ('(-1)^(10^100+1)', '-1'), ('i^(10^100+1)', 'i'), ('(1/3)^(1/100000)', '3^(99999/100000)/3'),
    ('2^x*2^100000', '2^(x+100000)'), ('(3+4*i)^100000/(3+4*i)^99999', '3+4*i'),
]


@pytest.mark.parametrize('a, b', SAME)
def test_equal_values_are_the_same_node(a, b):
    assert nd(a) == nd(b), (a, b)


def test_too_large_but_folding_rationals_fold():
    """Every intermediate stays small: (u/v)^(p/s) is rationalized prime by prime."""
    assert nd('(1/3)^(1/100000)') == K.mul_(num(1, 3), [(num(3), num(99999, 100000))])
    assert nd('2^(16384*2)/2^16384') == nd('2^16384')          # back under the limit: folds
    assert K.N[nd('2^(16384*2)/2^16384')][0] == K.NUM


TEXT = [
    ('2^100000*sqrt(3)/5', '2^100000*sqrt(3)/5'), ('-3*2^100000', '-3*2^100000'),
    ('2^(-200001/2)', '1/2^(200001/2)'), ('6^100000*x^2/7', '6^100000*x^2/7'),
    ('12^100000', '2^200000*3^100000'), ('(3+4*i)^100000', '(3+4*i)^100000'),
    ('(1+i)^100000*x', '(1+i)^100000*x'), ('x/2+2^99999', 'x/2+2^99999'),
    ('30030^16384', '30030^16384'), ('30^16385', '30^16385'),
    ('sqrt(-2^100001)', 'sqrt(-2^100001)'), ('(-3*2^100001)^(1/3)', '(-3*2^100001)^(1/3)'),
]


@pytest.mark.parametrize('s, want', TEXT)
def test_text_and_round_trip(s, want):
    """DESIGN 12.5: the text re-parses (answer path) to the same node."""
    e = nd(s)
    t = PR.text(e, None)
    assert t == want, s
    assert nd(t) == e, s


def test_fold_total_cap():
    """30030^16384: every prime folds by itself, but the total is over MAXFOLD, so the whole
    power is kept (bounded memory); 30^8192 is still an integer."""
    e = nd('30030^16384')
    assert K.N[e] == (K.MUL, K.ONE, num(30030), num(16384))
    assert K.N[nd('30^8192')] == (K.NUM, 30 ** 8192, 0, 1)


def test_kernels():
    """The giant-power code lives in nodeb (an aux pack on the calculator, DESIGN 6.1)."""
    assert KB.nval((K.NUM, 48, 0, 5), 2) == (4, (K.NUM, 3, 0, 5))
    assert KB.nval((K.NUM, 3, 0, 40), 2) == (-3, (K.NUM, 3, 0, 5))
    assert KB.nval((K.NUM, 6, 4, 7), 2) == (1, (K.NUM, 3, 2, 7))
    assert KB.nval((K.NUM, 2 ** 5000 * 3, 0, 1), 2) == (5000, (K.NUM, 3, 0, 1))
    assert KB.nval(K.Q0, 2) == (0, K.Q0)
    # A base over 4,000 bits is factored only below 256 and the rest stays one cofactor (hpow):
    # 257 comes out alone, 257*263 stays one base.
    big = 2 ** 5000 * 3 ** 7
    n = 5462                                    # every prime power is kept whole
    e = K.mul_(K.ONE, [(num(big * 257), num(n))])
    assert K.N[e][0] == K.MUL and len(K.N[e]) == 8
    assert e == K.mul_(K.ONE, [(num(2), num(5000 * n)), (num(3), num(7 * n)), (num(257), num(n))])
    e = K.mul_(K.ONE, [(num(big * 257 * 263), num(n))])
    assert e == K.mul_(K.ONE, [(num(2), num(5000 * n)), (num(3), num(7 * n)),
                               (num(257 * 263), num(n))])
    two = num(2)
    assert KB.huge(two, num(16385)) and KB.huge(two, num(-200001, 2))
    assert KB.huge(two, num(200001, 2)) and KB.huge(K.num(3, 4), num(100000))
    assert not KB.huge(two, num(1, 2)) and not KB.huge(two, K.sym('x'))
    assert not KB.huge(K.num(3, 4), num(1, 2))
    assert not KB.huge(two, num(3)) and not KB.huge(two, num(-5, 2))  # a HOLD's 2^3: small


def test_hold_display_product_still_evaluates():
    """factor(360) = 2^3*3^2*5 is a HOLD of numeric powers that are not kept whole."""
    m = K.mk((K.MUL, K.ONE, num(2), num(3), num(3), num(2), num(5), K.ONE))
    assert A.nev(K.mk((K.HOLD, m))) == 360.0
    K.reset()
    assert ans('factor(360)') == '2^3*3^2*5'


# -- arithmetic, decimals, commands ----------------------------------------------------------------

def test_no_decimal_line_and_approx_stays_exact():
    for s in ('2^(-100000)', '3*2^100000/7', '2^(200001/2)', '1+2^(-100000)'):
        assert go(s)[2] is None, s                             # no float value at all
    assert ans('approx(2^100000)') == '2^100000'
    assert ans('approx(2^100000*x+1/3)') == '2^100000*x+0.333333333333333'
    assert ans('1/2^10000')                                    # unchanged: an exact rational
    assert go('1/2^10000')[2] == '5.012372749E-3011'


def test_commands_on_giant_powers():
    for s, want in (
            ('expand((2^100000+x)^2)', 'x^2+2^100001*x+2^200000'),
            ('expand((2^100000+1)*(2^100000-1))', '2^200000-1'),
            ('expand(2^100000*(x+1))', '2^100000*x+2^100000'),
            ('expand((x+1/2^100000)^2)', 'x^2+x/2^99999+1/2^200000'),
            ('factor(2^100000*x^2-2^100000)', '2^100000*(x-1)*(x+1)'),
            ('factor(12^100000)', '2^200000*3^100000'),
            ('together(1/2^100000+1/x)', '(x+2^100000)/(2^100000*x)'),
            ('together((2^100000*x+2^100000)/(x+1))', '2^100000'),
            ('diff(2^100000*x^2,x)', '2^100001*x'),
            ('integrate(2^100000*x,x)', '2^99999*x^2'),
            ('integrate(2^100000,x,0,1)', '2^100000'),
            ('solve(2^100000*x=1,x)', 'x=1/2^100000'),
            ('solve(x^2=2^100000,x)', 'x=-2^50000,x=2^50000'),
            ('limit(2^100000*x,x,1)', '2^100000'),
            ('taylor(2^100000*e^x,x,0,2)', '2^100000+2^100000*x+2^99999*x^2+O(x^3)'),
            ('sum(2^100000*k,k,1,3)', '2^100001+2^100002')):
        assert ans(s) == want, s


def test_quotients_by_giant_sums_answer_at_once():
    # normc.dfac once took the base 2 of 2^100000+1 as a polynomial variable of degree 100000;
    # the alarm turns such a hang into a failure (the calculator is about 75 times slower).
    import signal

    def hang(*a):
        raise AssertionError('no answer within 5 s')
    old = signal.signal(signal.SIGALRM, hang)
    signal.alarm(5)
    try:
        for s, want in (
                ('1/(2^100000+1)', '1/(2^100000+1)'),
                ('2^100000/(2^100000+1)', '2^100000/(2^100000+1)'),
                ('(2^100000+1)/(2^100000-1)', '(2^100000+1)/(2^100000-1)'),
                ('1/(1-2^100000)', '-1/(2^100000-1)'),
                ('1/(2^100000+i)', '1/(2^100000+i)'),
                ('1/(3^(2^20)+1)', '1/(3^1048576+1)'),
                ('1/(2^100000+3^50000)', '1/(3^50000+2^100000)'),
                ('1/(2^16385+1)', '1/(2^16385+1)')):
            assert ans(s) == want, s
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_simplify_keeps_what_it_cannot_verify():
    """simplify's candidates must pass the float probe (8.7), which a giant power cannot
    enter: the input stays as built, with no SIMPBUG."""
    assert ans('simplify((2^100000*x+2^100000)/(x+1))') == '(2^100000*x+2^100000)/(x+1)'
    assert ans('simplify(2^100001-2^100000)') == '2^100001-2^100000'


def test_comparisons_and_functions():
    assert ans('2^100000=4^50000') == 'true'
    assert ans('2^100000>0') == '0<2^100000'                   # kept, as sqrt(2)>0 is
    assert ans('2^100000=2^100001') == '2^100000=2^100001'
    assert ans('sign(2^100000)') == '1' and ans('sign(-3^100000)') == '-1'
    assert ans('abs(-2^100000)') == '2^100000'
    assert ans('abs(x/2+2^99999)') == 'abs(x/2+2^99999)'       # the content stays (5.3)


def test_logarithms_split_like_numbers():
    """ln(b^k) = k*ln(b) for a perfect power (6.4), numerator and denominator apart, also for
    powers kept whole; so log(10^100000) = 100000 and ln(2^100000) has a decimal line."""
    for s, want in (('ln(2^100000)', '100000*ln(2)'), ('log(10^100000)', '100000'),
                    ('ln(12^100000)', '100000*ln(12)'), ('ln(2^100000/3)', '100000*ln(2)-ln(3)'),
                    ('ln(1/2^100000)', '-100000*ln(2)'),
                    ('ln(3*2^100000)', 'ln(3*2^100000)'),           # 3*2^100000: not a power
                    ('ln(2^(200001/2))', 'ln(2^(200001/2))'),       # as ln(sqrt(2))
                    ('ln(x*2^100000)', 'ln(2^100000*x)')):
        assert ans(s) == want, s
    assert go('ln(2^100000)')[2] == '69314.71806'
    assert ans('approx(log(2^100000))') == '30102.9995663981'


def test_zero_test_is_exact():
    def iszero(s):
        return drive(NB.g_iszero(nd(s)))
    assert iszero('2^100001-2*2^100000') == NB.YES
    assert iszero('(2^100000+1)^2-2^200000-2^100001-1') == NB.YES
    assert iszero('2^100000+1') == 0                           # A.NO: exact, no probe
    assert iszero('2^(200001/2)-1') == 0


# -- what still raises -----------------------------------------------------------------------------

def test_hard_ceilings():
    t0 = time.perf_counter()
    assert go('(2^(10^16000))^(10^16000)') == ('msg', K.M_BIG, None, 0)   # exponent > MAXBITS
    assert go('expand((1+sqrt(2))^1000000)') == ('msg', K.M_BIG, None, 0)  # no power form
    assert go('2^(10^16000)') == ('msg', 'Done', None, 0)      # kept; the exponent is unprintable
    assert go('(10^16000+1)^3') == ('msg', 'Done', None, 0)    # a 53,000-bit base, kept
    assert time.perf_counter() - t0 < 1.0
    assert go('0^(-100000)') == ('msg', PR.M_UNDEF, None, 0)
    assert go('2.0^100000')[1] == '2^100000'   # exact input path; approx cannot evaluate it
    assert go('approx(2^100000)')[1] == '2^100000'


# -- exact values at the fold boundary -------------------------------------------------------------

def value(e):
    """The exact Fraction of a constant node whose exponents are integers."""
    memo = {}
    for m in A.postorder(e):
        t = K.N[m]
        if t[0] == K.NUM:
            assert not t[2]
            memo[m] = Fraction(t[1], t[3])
        elif t[0] == K.ADD:
            memo[m] = memo[t[1]] + sum(memo[t[j]] * memo[t[j + 1]] for j in range(2, len(t), 2))
        elif t[0] == K.MUL:
            v = memo[t[1]]
            for j in range(2, len(t), 2):
                x = memo[t[j + 1]]
                assert x.denominator == 1
                v *= memo[t[j]] ** int(x)
            memo[m] = v
        else:
            raise AssertionError(t)
    return memo[e]


def term_text(terms, split):
    """k*b^n*... + ...; split: each power as two halves, factors and terms in reverse order."""
    out = []
    for k, fs in terms:
        f = ['(%s)' % k]
        for b, n in fs:
            if split:
                f.append('(%s)^(%d)*(%s)^(%d)' % (b, n // 2, b, n - n // 2))
            else:
                f.append('(%s)^(%d)' % (b, n))
        out.append('*'.join(reversed(f) if split else f))
    return '+'.join(reversed(out) if split else out)


@pytest.mark.parametrize('seed', [0, 1] + [pytest.param(s, marks=pytest.mark.slow)
                                    for s in range(2, 12)])
def test_random_products_and_sums_at_the_limit(seed):
    """Sums of products k*b1^e1*b2^e2 with exponents around the fold limit, where powers fold,
    stay whole, or fall back on MAXFOLD: the node has the exact value, and the same value built
    another way (each power split in two, factors and terms reordered) is the same node.
    (80 seeds were run when this was written; 2 are fast, 10 more are marked slow.)"""
    rng = random.Random(seed)
    bases = (2, 3, 4, 5, 6, 10, 12, 17, Fraction(2, 3), Fraction(5, 2))
    for _ in range(25):
        terms = []
        want = Fraction(0)
        for _ in range(rng.randint(1, 3)):
            k = Fraction(rng.choice((1, -1, 2, 3, 6, 7, -12)), rng.choice((1, 1, 2, 5, 9)))
            fs = []
            v = k
            for _ in range(rng.randint(1, 3)):
                b = rng.choice(bases)
                n = rng.choice((1, -1)) * rng.randint(8180, 8200) * rng.choice((1, 2))
                fs.append((b, n))
                v *= Fraction(b) ** n
            terms.append((k, fs))
            want += v
        a = nd(term_text(terms, False))
        b = nd(term_text(terms, True))
        assert value(a) == want
        assert a == b, (term_text(terms, False), PR.text(a, None), PR.text(b, None))
        K.reset()
