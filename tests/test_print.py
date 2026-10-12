"""T1.7: the 1D printer (DESIGN 12.1-12.6): text, items, the display-order keys, record.

Acceptance (section 21.4): the fmt section 1 ordering cases; the section 12.4 names, including
relations and HOLD; the sentinel messages; MAXTEXT; the decimal-line rules. The golden cases
live in tests/golden/print_t1.txt (input -> text through the user path); the round trip is
tests/test_roundtrip.py.
"""
import math
import os
import time

import pytest

import gen
import parse as P
import printer as PR

K = P.K
HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, 'golden', 'print_t1.txt')


@pytest.fixture(autouse=True)
def nosess(monkeypatch):
    monkeypatch.setattr(P, 'SESS', None)


def drive(g):
    """The trampoline of DESIGN 10.4, cut down (no session: no commands)."""
    stack = [g]
    val = None
    while stack:
        try:
            y = stack[-1].send(val)
        except StopIteration:
            y = None
        else:
            if type(y).__name__ == 'generator':
                stack.append(y)
                val = None
                continue
        stack.pop()
        val = y
    return val


def ev(s, deg=0, inert=0):
    """The value of the input s on the user path (stages 3-7, g_eval)."""
    ctx = [deg, None, 0, inert]
    return drive(P.g_eval(P.rpn(P.tokens(s)), ctx)), ctx


def show(s, deg=0):
    e, ctx = ev(s, deg)
    return PR.text(e, ctx)


def num(a, b=0, d=1):
    return K.num(a, b, d)


def sym(n):
    return K.sym(n)


def mul(*pairs, k=None):
    return K.mul_(K.ONE if k is None else k, list(pairs))


def hold(k, *pairs):
    t = [K.MUL, k]
    for b, e in pairs:
        t.append(b)
        t.append(e)
    return K.mk((K.HOLD, K.mk(tuple(t))))


# -- the API -------------------------------------------------------------------------------------

def test_api_names():
    for f in ('text', 'items', 'record', 'dec10', 'fdec10', 'xpow', 'pkey', 'sorder', 'pdisp',
              'dline', 'mainv'):
        assert callable(getattr(PR, f)), f
    assert PR.MAXTEXT == 4000
    assert (PR.R_ANS, PR.R_MSG) == ('ans', 'msg')
    assert (PR.F_PLUSC, PR.F_PURGEHINT, PR.F_APPROX, PR.F_DEG, PR.F_SOLN) == (1, 2, 4, 8, 16)
    assert PR.F_SOLN == P.F_SOLN


# -- golden: input -> canonical text ---------------------------------------------------------------

def golden_cases():
    out = []
    with open(GOLDEN, encoding='utf-8') as fh:
        for no, line in enumerate(fh.read().split('\n'), 1):
            if not line.strip() or line.startswith('#'):
                continue
            f = line.split('|')
            assert len(f) == 3 and f[0] in ('R', 'D'), 'bad golden line %d: %r' % (no, line)
            out.append((no, f[0], f[1], f[2]))
    return out


def golden_out(mode, s):
    try:
        e, ctx = ev(s, 1 if mode == 'D' else 0)
    except K.CasError as x:
        return '!' + str(x.args[0])
    r = PR.text(e, ctx)
    K.reset()
    return r


def test_golden_print(update_golden):
    rows = golden_cases()
    assert len(rows) >= 200
    bad = []
    got = {}
    for no, mode, s, want in rows:
        r = golden_out(mode, s)
        got[no] = r
        if r != want:
            bad.append('line %d %s|%s: want %r got %r' % (no, mode, s, want, r))
    if update_golden:
        with open(GOLDEN, encoding='utf-8') as fh:
            lines = fh.read().split('\n')
        for no, mode, s, want in rows:
            lines[no - 1] = '%s|%s|%s' % (mode, s, got[no])
        with open(GOLDEN, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('\n'.join(lines))
        return
    assert not bad, '\n'.join(bad)


# -- 12.3 display order: the keys ----------------------------------------------------------------

def test_xpow_keys():
    x = sym('x')
    y = sym('y')
    assert PR.xpow(x, x) == 60
    assert PR.xpow(y, x) == 0
    assert PR.xpow(mul((x, num(3, 0, 2))), x) == 90
    assert PR.xpow(mul((x, K.HALF)), x) == 30
    assert PR.xpow(mul((x, num(1, 0, 3))), x) == 20
    assert PR.xpow(mul((x, num(-1))), x) == -60
    assert PR.xpow(mul((x, num(-1, 0, 7))), x) == -9          # floor(-60/7)
    assert PR.xpow(mul((x, K.TWO), (K.E, x)), x) == 120
    assert PR.xpow(mul((x, y)), x) == 0                       # a symbolic exponent
    assert PR.xpow(K.fn_(K.SIN, x), x) == 0
    assert PR.xpow(x, 0) == 0
    assert PR.xpow(mul((x, K.flt(2.5))), x) == 150


def test_pkey():
    x = sym('x')
    y = sym('y')
    p = K.add_([mul((x, K.TWO)), num(-4)])
    assert PR.pkey(p) == ('x', 2, -4, 1)
    assert PR.pkey(K.add_([x, num(1, 0, 2)])) == ('x', 1, 1, 2)
    assert PR.pkey(K.add_([x, y])) is None
    assert PR.pkey(K.add_([x, K.fn_(K.SIN, x)])) is None
    assert PR.pkey(K.add_([x, K.PI])) is None
    assert PR.pkey(K.add_([mul((x, K.HALF)), K.ONE])) is None
    assert PR.pkey(K.add_([x, K.I])) is None


def test_sorder_descending_and_series():
    x = sym('x')
    p = K.add_([K.ONE, x, mul((x, K.TWO)), mul((x, num(3)))])
    o = PR.sorder(p, x)
    assert [K.N[t][0] if t else None for t, k in o][-1] is None   # the constant last
    assert [PR.xpow(t, x) if t else 0 for t, k in o] == [180, 120, 60, 0]
    s = K.add_([K.ONE, x, K.mk((K.BIGO, mul((x, K.TWO))))])
    o = PR.sorder(s, x)
    assert o[0][0] == 0 and K.N[o[-1][0]][0] == K.BIGO          # ascending, O last


def test_mainvar():
    for s, want in (('y+x', 'x'), ('y+t', 't'), ('theta+y', 'theta'), ('b+a', 'a'),
                    ('z*w+q', 'q'), ('2', None)):
        e, ctx = ev(s)
        m = PR.mainv(e, ctx)
        assert (K.N[m][1] if m else None) == want, s
    e, ctx = ev('y^2+x')
    ctx[P.X_MV] = sym('y')                  # the command's variable wins
    assert PR.text(e, ctx) == 'y^2+x'
    ctx[P.X_MV] = None
    assert PR.text(e, ctx) == 'x+y^2'


def test_mainvar_overflow_symbols():
    names = ['v%d' % j for j in range(31)] + ['zz', 'aa']
    e = K.add_([sym(n) for n in names])
    assert K.V[e] & K.OVF
    m = PR.mainv(e, None)
    assert K.N[m][1] == 'aa'


# -- 12.4 names and special printing ------------------------------------------------------------

def test_hold():
    h = hold(K.ONE, (num(2), num(3)), (num(3), K.TWO), (num(5), K.ONE))
    assert PR.text(h, None) == '2^3*3^2*5'
    h = hold(K.MONE, (num(2), num(2)), (num(3), K.ONE))
    assert PR.text(h, None) == '-2^2*3'
    assert PR.text(hold(K.ONE, (num(7), K.ONE)), None) == '7'
    assert PR.text(hold(K.ONE, (num(2), num(10))), None) == '2^10'
    lst = K.mk((K.LST, hold(K.ONE, (num(2), K.TWO), (num(3), K.ONE)), K.ONE))
    assert PR.text(lst, None) == '[2^2*3,1]'


def test_relation_operands_and_swaps():
    x = sym('x')
    y = sym('y')
    three = num(3)
    assert PR.text(K.rel_(K.LT, three, x), None) == 'x>3'
    assert PR.text(K.rel_(K.LE, three, x), None) == 'x>=3'
    assert PR.text(K.rel_(K.LT, x, three), None) == 'x<3'
    assert PR.text(K.rel_(K.GT, x, y), None) == 'x>y'
    assert PR.text(K.rel_(K.LT, x, y), None) == 'x<y'
    ctx = [0, y, 0, 0]
    assert PR.text(K.rel_(K.LT, x, y), ctx) == 'y>x'
    assert PR.text(K.rel_(K.NE, x, three), None) == 'x!=3'
    assert PR.text(K.rel_(K.EQ, three, x), None) == '3=x'     # never swapped (round trip)
    r = K.mk((K.EQ, K.mk((K.EQ, x, three)), y))
    assert PR.text(r, None) == '(x=3)=y'
    assert PR.text(K.TRUE, None) == 'true'
    assert PR.text(K.FALSE, None) == 'false'


def test_factorial_before_equals_relexes():
    n = sym('n')
    r = K.rel_(K.EQ, K.fn_(K.FACT, n), K.ONE)
    s = PR.text(r, None)
    assert s == 'n! =1'
    toks = P.lex(s)
    assert [t[1] for t in toks] == ['n', '!', '=', (1, 1)]
    r = K.rel_(K.EQ, mul((K.fn_(K.FACT, n), K.ONE), k=K.TWO), K.ONE)
    assert PR.text(r, None) == '2*n! =1'
    assert PR.text(K.rel_(K.NE, K.fn_(K.FACT, n), K.ONE), None) == 'n!!=1'


def test_calls_lists_bigo_and_nested_sentinels():
    x = sym('x')
    c = K.mk((K.CALL, sym('integrate'), mul((x, K.TWO)), x))
    assert PR.text(c, None) == 'integrate(x^2,x)'
    c = K.mk((K.CALL, sym('limit'), K.add_([x, K.ONE]), x, K.OO, K.ONE))
    assert PR.text(c, None) == 'limit(x+1,x,oo,1)'
    assert PR.text(K.mk((K.CALL, sym('f'))), None) == 'f()'
    l = K.mk((K.LST, K.mk((K.LST,)), x))
    assert PR.text(l, None) == '[[],x]'
    assert PR.text(K.mk((K.BIGO, mul((x, num(6))))), None) == 'O(x^6)'
    dne = K.mk((K.DNE, K.MONE, K.ONE))
    assert PR.text(K.mk((K.LST, dne, K.mk((K.DIVG, K.ZERO)))), None) == '[undef,undef]'


@pytest.mark.invariants_skip('wild')
def test_wild_prints_without_crashing():
    w = K.mk((K.WILD, 3, 1))
    assert PR.text(w, None) == '_w3'


def test_float_text():
    for v, want in ((0.5, '0.5'), (2.0, '2.0'), (-2.0, '-2.0'), (1e10, '1E10'),
                    (1.5e-5, '1.5E-5'), (0.1 + 0.2, '0.3'), (1 / 3, '0.333333333333333'),
                    (123456789012345678.0, '1.23456789012346E17'), (1e300, '1E300'),
                    (0.0, '0.0')):
        assert PR.text(K.flt(v), None) == want, v
    assert PR.text(K.flt(0.5, 1.5), None) == '0.5+1.5*i'
    assert PR.text(K.flt(0.0, 1.0), None) == '1.0*i'
    assert PR.text(K.flt(0.0, -2.0), None) == '-2.0*i'
    assert PR.text(K.flt(-1.0, -2.0), None) == '-1.0-2.0*i'
    x = sym('x')
    assert PR.text(mul((x, K.ONE), k=K.flt(1.0)), None) == '1.0*x'
    assert PR.text(mul((x, K.ONE), k=K.flt(-1.0)), None) == '-1.0*x'
    assert PR.text(mul((x, K.ONE), k=K.flt(0.5, -1.5)), None) == '(0.5-1.5*i)*x'
    assert PR.text(mul((x, K.flt(-2.0))), None) == '1/x^2.0'
    assert PR.text(mul((K.flt(0.5), x)), None) == '0.5^x'
    assert PR.text(mul((K.flt(-0.5), x)), None) == '(-0.5)^x'


def test_gaussian_text():
    for (a, b, d), want in (((0, 1, 1), 'i'), ((0, -1, 1), '-i'), ((3, 4, 1), '3+4*i'),
                            ((3, -4, 1), '3-4*i'), ((-3, 4, 1), '-3+4*i'),
                            ((1, 1, 2), '1/2+i/2'), ((0, 3, 2), '3*i/2'), ((0, -1, 2), '-i/2'),
                            ((-1, -3, 5), '-1/5-3*i/5')):
        assert PR.text(num(a, b, d), None) == want, (a, b, d)
    x = sym('x')
    assert PR.text(mul((x, K.ONE), k=num(0, -2, 3)), None) == '-2*i*x/3'
    assert PR.text(mul((x, num(1, 1))), None) == 'x^(1+i)'
    assert PR.text(mul((num(1, 1), x)), None) == '(1+i)^x'


def test_degree_mode_text():
    x = sym('x')
    ctx = [1, None, 0, 0]
    # the builder's sin(x+30) is sin(pi*x/180+pi/6)
    v = K.add_([mul((x, K.ONE), (K.PI, K.ONE), k=num(1, 0, 180)), mul((K.PI, K.ONE),
                                                                       k=num(1, 0, 6))])
    assert PR.text(K.fn_(K.SIN, v), ctx) == 'sin(x+30)'
    assert PR.text(K.fn_(K.SIN, v), None) == 'sin(pi*x/180+pi/6)'
    assert PR.text(K.fn_(K.SIN, x), ctx) == 'sin(180*x/pi)'
    a = K.fn_(K.ASIN, x)
    assert PR.text(a, ctx) == 'pi*asin(x)/180'
    assert PR.text(a, None) == 'asin(x)'
    d = K.mul_(num(180), [(a, K.ONE), (K.PI, K.MONE)])
    assert PR.text(d, ctx) == 'asin(x)'
    # the derivative of sin in degrees picks up pi/180 (6.5)
    dd = mul((K.PI, K.ONE), (K.fn_(K.COS, mul((x, K.ONE), (K.PI, K.ONE),
                                              k=num(1, 0, 180))), K.ONE), k=num(1, 0, 180))
    assert PR.text(dd, ctx) == 'pi*cos(x)/180'


# -- MAXTEXT and big numbers ---------------------------------------------------------------------

def test_maxtext_long_sum_gives_none_and_done():
    x = sym('x')
    terms = []
    for j in range(1, 151):                 # about 35 characters a term, 450 nodes
        terms.append(mul((x, num(j)), k=num(10 ** 30 + j)))
    e = K.add_(terms)
    assert PR.text(e, None) is None
    r = PR.record(e, ('eval', 'long'))
    assert r == ('msg', 'Done', None, 0)


def test_maxtext_boundary():
    big = 10 ** 3999                         # exactly 4000 digits
    assert len(PR.text(num(big), None)) == 4000
    assert PR.text(num(-big), None) is None  # 4001 characters
    assert PR.text(num(10 ** 4000), None) is None


def test_huge_integer_never_converted():
    n = 1 << 100000                          # about 30,000 digits
    e = num(n)
    assert PR.items(e, 0, (0, 0)) is None
    t0 = time.perf_counter()
    r = PR.record(e, ('eval', '2^100000'))
    assert time.perf_counter() - t0 < 0.5
    assert r == ('msg', 'Done', None, 0)
    x = sym('x')
    # n + 1 is odd: a power of 2 in the coefficient would be kept whole by mul_ (DESIGN 6.1)
    assert PR.text(mul((x, K.ONE), k=num(1, 0, n + 1)), None) is None
    assert PR.text(mul((x, K.ONE), k=num(1, 0, n)), None) == 'x/2^100000'
    assert PR.text(mul((x, num(n))), None) is None
    assert PR.text(num(3, n), None) is None


def test_review_cases_printing():
    """DESIGN 20.12 'printing': x>3, log(8,2), 2^(10^6) at once (kept as a power, 6.1), a
    30,000-digit Done."""
    assert show('x>3') == 'x>3'
    assert show('log(8,2)') == '3'
    t0 = time.perf_counter()
    assert show('2^(10^6)') == '2^1000000'
    assert time.perf_counter() - t0 < 0.5
    assert show('10^16000*10^14000') == '10^30000'      # a product of folded powers too
    e, ctx = ev('(10^16000+1)*(10^14000+1)')            # 30,001 digits, no prime power kept
    assert K.N[e][1] == (10 ** 16000 + 1) * (10 ** 14000 + 1)
    t0 = time.perf_counter()
    assert PR.record(e, ('eval', 's', ctx, 0)) == ('msg', 'Done', None, 0)
    assert time.perf_counter() - t0 < 0.5


# -- record: answers, sentinel messages, flags --------------------------------------------------

def test_record_answer_shape():
    e, ctx = ev('x^2+1')
    r = PR.record(e, ('eval', 'x^2+1', ctx, 0))
    assert r == ('ans', 'x^2+1', None, 0)
    e, ctx = ev('1/3')
    r = PR.record(e, ('eval', '1/3', ctx, PR.F_PLUSC | PR.F_DEG))
    assert r == ('ans', '1/3', '0.3333333333', PR.F_PLUSC | PR.F_DEG)
    assert PR.record(e, ('eval', '1/3')) == ('ans', '1/3', '0.3333333333', 0)
    assert PR.record(e, ('form', '', ctx, 0)) == ('ans', '1/3', None, 0)


def test_record_sentinel_messages():
    x = sym('x')
    soln = ('eval', 'solve(...)', [0, None, 0, 0], PR.F_SOLN)
    assert PR.record(K.mk((K.LST,)), soln) == ('msg', 'no solution', None, 0)
    assert PR.record(K.FALSE, soln) == ('msg', 'no solution', None, 0)
    assert PR.record(K.TRUE, soln) == ('msg', 'every x is a solution', None, 0)
    y = sym('y')
    assert PR.record(K.TRUE, ('eval', 's', [0, y, 0, 0], PR.F_SOLN)) == \
        ('msg', 'every y is a solution', None, 0)
    # without F_SOLN they are answers
    plain = ('eval', 'x', [0, None, 0, 0], 0)
    assert PR.record(K.mk((K.LST,)), plain) == ('ans', '[]', None, 0)
    assert PR.record(K.TRUE, plain) == ('ans', 'true', None, 0)
    assert PR.record(K.FALSE, plain) == ('ans', 'false', None, 0)
    # DNE and DIVG are messages anywhere at the top level
    ninf = K.mul_(K.MONE, [(K.OO, K.ONE)])
    assert PR.record(K.mk((K.DNE, ninf, K.OO)), plain) == \
        ('msg', 'does not exist: -oo from the left, oo from the right', None, 0)
    assert PR.record(K.mk((K.DNE, K.MONE, K.add_([x, K.ONE]))), plain)[1] == \
        'does not exist: -1 from the left, x+1 from the right'
    assert PR.record(K.mk((K.DNE, K.UNDEF, K.ONE)), plain) == \
        ('msg', 'no limit (it oscillates)', None, 0)
    assert PR.record(K.mk((K.DNE, K.ONE, K.UNDEF)), plain)[1] == 'no limit (it oscillates)'
    for w, want in ((0, 'diverges (the improper integral does not converge)'),
                    (1, 'diverges (the integrand is unbounded on the interval)'),
                    (2, 'diverges (the terms do not go to 0)')):
        assert PR.record(K.mk((K.DIVG, num(w))), plain) == ('msg', want, None, 0)
    # a long side is cut
    long = K.add_([mul((x, num(j))) for j in range(1, 30)])
    m = PR.record(K.mk((K.DNE, long, K.OO)), plain)[1]
    assert m.startswith('does not exist: ') and '...' in m and len(m) < 120


def test_record_solutions_text():
    x = sym('x')
    l = K.mk((K.LST, K.rel_(K.EQ, x, K.MONE), K.rel_(K.EQ, x, K.ONE)))
    soln = ('eval', 'solve(x^2=1)', [0, x, 0, 0], PR.F_SOLN)
    assert PR.record(l, soln) == ('ans', 'x=-1,x=1', None, PR.F_SOLN)
    one = K.mk((K.LST, K.rel_(K.EQ, x, num(2))))
    assert PR.record(one, soln)[1] == 'x=2'


def test_record_none_is_undefined():
    assert PR.record(None, ('eval', '1/0')) == ('msg', 'undefined', None, 0)


def test_record_hold_has_no_decimal_line():
    h = hold(K.ONE, (num(2), num(3)), (num(3), K.TWO), (num(5), K.ONE))
    assert PR.record(h, ('eval', 'factor(360)')) == ('ans', '2^3*3^2*5', None, 0)


def test_record_approx_flag():
    e, ctx = ev('approx(pi)')
    r = PR.record(e, ('eval', 'approx(pi)', ctx, 0))
    assert r == ('ans', '3.14159265358979', None, PR.F_APPROX)
    e, ctx = ev('0.5x')                      # a typed float: approximate, not a fallback
    assert ctx[P.X_APPROX] == 1
    assert PR.record(e, ('eval', '0.5x', ctx, 0)) == ('ans', '0.5*x', None, 0)
    assert PR.record(e, ('form', '', [0, None, 0, 0], 0))[3] == 0


def test_record_degree_mode_from_ctx_or_flag():
    e, ctx = ev('asin(x)+30', 1)
    assert PR.record(e, ('eval', 's', ctx, PR.F_DEG))[1] == 'asin(x)+30'
    assert PR.record(e, ('eval', 's', None, PR.F_DEG))[1] == 'asin(x)+30'


# -- 12.6 the decimal line ----------------------------------------------------------------------

DEC = (
    ('1/3', '0.3333333333'), ('22/7', '3.142857143'), ('pi', '3.141592654'),
    ('1/100000', '1E-5'), ('-1/3', '-0.3333333333'), ('sqrt(2)', '1.414213562'),
    ('sqrt(2)/2', '0.7071067812'), ('e', '2.718281828'), ('2pi', '6.283185307'),
    ('ln(2)', '0.6931471806'), ('(1+i)/2', '0.5+0.5i'), ('(1-3i)/2', '0.5-1.5i'),
    ('i/3', '0.3333333333i'), ('-i/3', '-0.3333333333i'), ('i*sqrt(2)', '1.414213562i'),
    ('ln(-1)', '3.141592654i'), ('e^(i*pi/3)', '0.5+0.8660254038i'),
    ('1+i*sqrt(3)', '1+1.732050808i'), ('sqrt(3)/3+i', '0.5773502692+i'),
    ('10^20/3', '3.333333333E19'), ('2^(1/3)', '1.25992105'), ('(-8)^(1/3)*sqrt(2)', '-2.828427125'),
    ('sin(pi/5)', '0.5877852523'), ('atan(2)', '1.107148718'), ('log(2)', '0.3010299957'),
    ('cos(5pi/12)', '0.2588190451'), ('abs(1-pi)', '2.141592654'), ('pi^20', '8769956796'),
    ('pi^21', '2.755163184E10'), ('1/pi^9', '3.354680357E-5'),
)
NODEC = ('7', '-12', '3+4i', '2i', 'x', 'x+1', 'oo', '-oo', 'undef', '2<3', 'pi<x', '[1/2]',
         '0.5', 'pi*1.0', 'f(1/2)', 'O(1/2)', 'x=1/2', 'true', '1001!',
         'e^(e^(e^(e^2)))')


@pytest.mark.parametrize('s, want', DEC)
def test_decimal_line(s, want):
    e, ctx = ev(s)
    assert PR.dline(e) == want
    assert PR.record(e, ('eval', s, ctx, 0))[2] == want


@pytest.mark.parametrize('s', NODEC)
def test_no_decimal_line(s):
    e, ctx = ev(s)
    assert PR.dline(e) is None
    r = PR.record(e, ('eval', s, ctx, 0))
    assert r[2] is None


def test_no_decimal_line_cases_by_node():
    h = hold(K.ONE, (num(2), num(3)), (num(3), K.ONE))
    assert PR.dline(h) is None
    assert PR.dline(K.mk((K.DNE, K.ONE, K.TWO))) is None
    assert PR.dline(K.mk((K.CALL, sym('sum'), K.HALF))) is None
    x = sym('x')
    assert PR.dline(K.rel_(K.LT, K.PI, K.E)) is None
    big = K.add_([mul((num(p), K.HALF)) for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31,
                                                  37, 41, 43, 47, 53, 59, 61, 67, 71, 73,
                                                  79)])
    assert gen is not None and K.N[big][0] == K.ADD
    import alg as A
    assert A.size(big) >= 64
    assert PR.dline(big) is None
    small = K.add_([mul((num(p), K.HALF)) for p in (2, 3, 5)])
    assert PR.dline(small) == '5.382332347'
    assert PR.dline(x) is None


def test_decimal_line_never_raises(monkeypatch):
    import alg as A

    def boom(prog, vals, r=None):
        raise OverflowError('x')
    monkeypatch.setattr(A, 'nrun', boom)
    e, ctx = ev('pi')
    assert PR.dline(e) is None
    assert PR.record(e, ('eval', 'pi', ctx, 0)) == ('ans', 'pi', None, 0)


def test_decimal_line_tiny_imaginary_noise_dropped():
    # (1+i)^4 = -4, built as a radical product that nev evaluates through complex powers
    e, ctx = ev('sqrt(1+i)^8/sqrt(3)')
    d = PR.dline(e)
    assert d is not None and 'i' not in d and d.startswith('-2.309401077')


# -- depth: nesting invariance (20.7) and the levels --------------------------------------------

@pytest.mark.parametrize('kind', ('sin', 'square', 'frac', 'prod', 'exp', 'ln', 'sum'))
def test_nesting_invariance(evodepth, kind):
    depths = []
    for n in (1, 8, 32):
        e, ctx = ev(gen.nested(kind, n))
        r, d, st = evodepth.measure(PR.record, e, ('eval', 's', ctx, 0))
        assert r[0] in ('ans', 'msg')
        depths.append(d)
        K.reset()
    assert depths[0] == depths[1] == depths[2], depths


def test_nesting_invariance_degree(evodepth):
    depths = []
    for n in (1, 8, 32):
        e, ctx = ev(gen.nested('sin', n).replace('sin', 'asin'), 1)
        r, d, st = evodepth.measure(PR.text, e, ctx)
        depths.append(d)
        K.reset()
    assert depths[0] == depths[1] == depths[2], depths


@pytest.mark.strict_depth
def test_strict_depth_print_and_record():
    for s in ('x^2+3x/2-sin(x)', '(2-x^2)*sin(x)/(x+1)', 'log(x)^2+e^(2x)', '1/3', 'x=1,x=2',
              'sin(pi/5)+i'):
        e, ctx = ev(s)
        PR.record(e, ('eval', s, ctx, 0))
        K.reset()
    e, ctx = ev('asin(x)+sin(x+30)', 1)
    PR.record(e, ('eval', 's', ctx, PR.F_DEG))


# -- robustness on random trees -----------------------------------------------------------------

@pytest.mark.parametrize('seed', range(6))
def test_random_trees_print(seed):
    g = gen.Gen(seed, syms=('x', 'y', 'theta'), floats=True, consts=('pi', 'e', 'i'))
    for _ in range(60):
        t = g.tree(3)
        try:
            e = gen.build(t, K)
        except (K.CasSoft, K.CasError):
            continue
        for deg in (0, 1):
            s = PR.text(e, [deg, None, 0, 0])
            assert s is not None and s and ' ' not in s.replace('! =', '')
            r = PR.record(e, ('eval', 's', [deg, None, 0, 0], 0))
            assert r[0] == 'ans'
        K.reset()


@pytest.fixture
def scan_display(monkeypatch):
    """Run the invariant scan over the display-only nodes that text builds, just before it
    releases them (they never reach the end-of-test scan)."""
    import invariants
    real = K.release
    seen = []

    def release(m):
        if K.NN > m:
            errs = invariants.scan(K)
            assert not errs, '\n'.join(errs[:10])
            seen.append(K.NN - m)
        real(m)
    monkeypatch.setattr(K, 'release', release)
    return seen


def test_temporary_nodes_are_canonical(scan_display):
    # the display passes build nodes (flips, sum content, degree conversions, the long-
    # polynomial expansion); scan_display checks them before text releases them
    for s in ('(-x^2+x+1)^3*y', '2x*cos(x)-(2-x^2)*sin(x)', '(1-x)^5*(2-x^3-x)',
              'y*(2x+2)+z*(x/2-1/3)', '(x+2)(2x+4)*sin(y*(4x-6))', '1+i+(2+3i)*x',
              '(x^12+3x^11+5x^10+7x^9+9x^8+11x^7+13x^6+15x^5+17x^4+19x^3+21x^2+23x)/182'):
        e, ctx = ev(s)
        assert PR.text(e, ctx)
        K.reset()
    e, ctx = ev('asin(x)+sin(2x+60)+acos(sin(x))+y*(2asin(x)+180)', 1)
    assert PR.text(e, ctx)
    assert len(scan_display) >= 4


@pytest.mark.parametrize('seed', range(3))
def test_random_trees_display_nodes(scan_display, seed):
    g = gen.Gen(50 + seed, syms=('x', 'y'), consts=('pi', 'e', 'i'))
    for _ in range(40):
        try:
            e = gen.build(g.tree(3), K)
        except (K.CasSoft, K.CasError):
            continue
        for deg in (0, 1):
            PR.text(e, [deg, None, 0, 0])
        K.reset()


def test_text_releases_its_nodes():
    for s, deg in (('(-x^2+x+1)^3*y', 0), ('y*(2x+2)', 0), ('asin(x)+sin(x+30)', 1),
                   ('1+i+x', 0)):
        e, ctx = ev(s, deg)
        n = K.NN
        assert PR.text(e, ctx)
        assert K.NN == n, s
        r = PR.record(e, ('eval', s, ctx, 0))
        assert r[0] == 'ans' and K.NN == n, s
        K.reset()


def test_scont():
    x = sym('x')
    y = sym('y')
    assert PR.scont(K.add_([mul((x, K.TWO), k=num(2)), num(4)])) == (2, 1)
    assert PR.scont(K.add_([mul((x, K.ONE), k=num(2, 0, 13)), K.mul_(num(-3, 0, 13),
                                                                       [(K.fn_(K.SIN, x),
                                                                         K.ONE)])])) == (1, 13)
    assert PR.scont(K.add_([x, num(1, 0, 2)])) == (1, 2)
    assert PR.scont(K.add_([mul((x, K.ONE), k=num(-6)), num(-9, 0, 2)])) == (3, 2)
    assert PR.scont(K.add_([x, K.ONE])) is None
    assert PR.scont(K.add_([x, y])) is None
    assert PR.scont(K.add_([mul((x, K.ONE), k=num(2)), K.flt(4.0)])) is None
    assert PR.scont(K.add_([mul((x, K.ONE), k=num(2)), num(0, 4)])) is None
    assert PR.scont(K.add_([mul((x, K.ONE), k=num(4)), mul((y, K.ONE), k=num(6))])) == (2, 1)


def test_main_variable_skips_call_names():
    # a call's name is not a variable: asin(y) in degree mode prints through CALL('asin', y)
    e, ctx = ev('asin(y)<y', 1)
    assert PR.text(e, ctx) == 'asin(y)<y'
    f = K.mk((K.CALL, sym('a'), sym('z')))
    assert K.N[PR.pickmv(K.add_([f, sym('b')]))][1] == 'b'


def test_flip_value_is_preserved():
    # every flipped display re-parses to the same node (the round trip covers this too)
    for s in ('(-x^2+x+1)^3*y', '(x^3-x^2-1)*(1-x)', '(2-x^2)*(3-x^3-x)^2'):
        e, ctx = ev(s)
        t = PR.text(e, ctx)
        e2 = drive(P.g_eval(P.rpn(P.tokens(t, 0)), [0, None, 0, 1]))
        assert e2 == e, (s, t)
