"""T1.5 builders (DESIGN 7.1, 7.6, 7.8, 6.3, 6.5, 9.2): tokens, expand_names, tcode, inst,
g_eval, exact, approx.

Acceptance (section 21.4): arithmetic seeds (alg 6: 2.2, 2.3) through the user path; degree mode;
variables, functions and macros at token level; floats and approx. Plus: canonicity against the
frozen node API on random trees, commands through a stub session and a test trampoline, the
default result path, rule patterns and templates, and nesting invariance of the depth.
"""
import cmath
import math
import random
import types
from fractions import Fraction

import pytest

import gen
import parse as P

K = P.K
CasError = K.CasError

# -- a stub session (the run module's tables, DESIGN 15.1) and a test trampoline (10.4) -----------

NEED = []
SEEN = []


def g_twice(args, ctx):
    yield K.mul_(K.TWO, [(args[0], K.ONE)])


def g_nested(args, ctx):
    r = yield g_twice(args, ctx)          # a virtual call from a command (10.2)
    yield K.add_([r, K.ONE])


def g_fail(args, ctx):
    return
    yield


def g_soft(args, ctx):
    raise K.Undefined()
    yield


def g_seeargs(args, ctx):
    SEEN.append((args, list(ctx)))
    yield args[0]


def g_autosimp(e):
    SEEN.append(('autosimp', e))
    yield K.sym('simplified')


def g_autoid(e):
    """The default stub: the default result path runs, and keeps the value."""
    SEEN.append(('autosimp', e))
    yield e


def g_autonone(e):
    SEEN.append(('autosimp', e))
    return
    yield


FAKE = types.SimpleNamespace(g_twice=g_twice, g_nested=g_nested, g_fail=g_fail, g_soft=g_soft,
                             g_seeargs=g_seeargs)
NORM = types.SimpleNamespace(g_autosimp=g_autoid)


def session(vars=None, funcs=None):
    cmds = {
        'twice': ('fake', 'g_twice', 1, 1, 0, ()),
        'nested': ('fake', 'g_nested', 1, 1, 0, ()),
        'fail': ('fake', 'g_fail', 1, 1, 0, ()),
        'soft': ('fake', 'g_soft', 1, 1, 0, ()),
        'seeargs': ('fake', 'g_seeargs', 1, 3, 0, ()),
        'noauto': ('fake', 'g_seeargs', 1, 1, P.F_NOAUTO, ()),
        'always': ('fake', 'g_seeargs', 1, 1, P.F_ALWAYSAUTO, ()),
        'integrate': ('fake', 'g_seeargs', 1, 4, 0, ()),
        'diff': ('fake', 'g_seeargs', 1, 3, 0, ()),
        'sum': ('fake', 'g_seeargs', 2, 4, 0, ()),
        'riemann': ('fake', 'g_seeargs', 5, 6, 0, ()),
    }
    mods = {'fake': FAKE, 'norm': NORM}

    def need(key):
        NEED.append(key)
        return mods[key]

    return types.SimpleNamespace(
        VARS=dict(vars or {}), FUNCS=dict(funcs or {}), CMDS=cmds,
        ALIAS={'tw': 'twice', 'int': 'integrate', 'd': 'diff'},
        MACROS={'polararea': (4, 4, 'integrate((#1)^2/2,#2,#3,#4)'),
                'paramarea': (5, 5, 'integrate((#2)*diff(#1,#3),#3,#4,#5)'),
                'arclen': (4, 6, None)},
        MODS=mods, need=need)


@pytest.fixture(autouse=True)
def sess(monkeypatch):
    s = session()
    monkeypatch.setattr(P, 'SESS', s)
    del NEED[:]
    del SEEN[:]
    return s


def drive(g, soft=False):
    """The trampoline of DESIGN 10.4, cut down: generators nest on a list; CasSoft gives
    None (or propagates with soft=True)."""
    stack = [g]
    val = None
    while stack:
        try:
            y = stack[-1].send(val)
        except StopIteration:
            y = None
        except K.CasSoft:
            if soft:
                raise
            y = None
        else:
            if type(y) is types.GeneratorType:
                stack.append(y)
                val = None
                continue
        stack.pop()
        val = y
    return val


def ctx(deg=0, inert=0):
    return [deg, None, 0, inert]


def ev(s, deg=0, inert=0, ctxt=1, c=None, soft=True):
    """The user path (stages 3-7, then g_eval); ctxt=0 and inert=1 give the answer path."""
    c = ctx(deg, inert) if c is None else c
    return drive(P.g_eval(P.rpn(P.tokens(s, ctxt)), c), soft)


def short(s, deg=0, inert=0):
    """lex + rpn + g_eval (the explicit-'*' path of rule strings and answer text)."""
    return drive(P.g_eval(P.rpn(P.lex(s)), ctx(deg, inert)), True)


def text(toks):
    return P.untok(toks)


# small constructor helpers
def num(a, d=1):
    return K.num(a, 0, d)


def sym(n):
    return K.sym(n)


def mul(k, *pairs):
    return K.mul_(k if type(k) is tuple else K.N[k], list(pairs))


def times(*xs):
    return K.mul_(K.ONE, [(x, K.ONE) for x in xs])


def pw(b, e):
    return K.mul_(K.ONE, [(b, e)])


def add(*xs):
    return K.add_(list(xs))


def neg(x):
    return K.add_([x], K.MONE)


def q(a, d=1):
    return (K.NUM, a, 0, d)


# a numeric value of a node (exact numbers as complex), for spot checks
def val(n, env=None):
    t = K.N[n]
    op = t[0]
    if op == K.NUM:
        return complex(t[1], t[2]) / t[3]
    if op == K.FLT:
        return complex(t[1], t[2])
    if op == K.SYM:
        return env[t[1]]
    if n == K.PI:
        return complex(math.pi)
    if n == K.E:
        return complex(math.e)
    if op == K.ADD:
        v = val(t[1], env)
        for j in range(2, len(t), 2):
            v += val(t[j], env) * val(t[j + 1], env)
        return v
    if op == K.MUL:
        v = val(t[1], env)
        for j in range(2, len(t), 2):
            b = val(t[j], env)
            e = K.N[t[j + 1]]
            if e[0] == K.NUM and not e[2] and e[3] % 2 and b.imag == 0 and b.real < 0:
                v *= (-1) ** e[1] * (-b.real) ** (e[1] / e[3])
            else:
                v *= b ** val(t[j + 1], env)
        return v
    f = {K.SIN: cmath.sin, K.COS: cmath.cos, K.TAN: cmath.tan, K.ASIN: cmath.asin,
         K.ACOS: cmath.acos, K.ATAN: cmath.atan, K.LN: cmath.log, K.SINH: cmath.sinh,
         K.COSH: cmath.cosh, K.TANH: cmath.tanh, K.ABS: abs}[op]
    return complex(f(val(t[1], env)))


def close(a, b, tol=1e-12):
    return abs(a - b) <= tol * max(1.0, abs(b))


# -- arithmetic seeds (alg 6: 2.2, 2.3) and arithmetic ---------------------------------------------

def test_seeds_2_2_radicals():
    assert ev('sqrt(72)') == mul(q(6), (K.TWO, K.HALF))
    assert ev('sqrt(8/27)') == mul(q(2, 9), (num(6), K.HALF))
    assert ev('(-8)^(1/3)') == num(-2)
    assert ev('1/sqrt(2)') == mul(K.HALF, (K.TWO, K.HALF))
    assert ev('sqrt(-4)') == K.num(0, 2)
    r = ev('sqrt(3+2sqrt(2))')              # denesting is simplify's (T1.10): kept, same value
    assert r == pw(add(num(3), mul(q(2), (K.TWO, K.HALF))), K.HALF)
    assert close(val(r), 1 + math.sqrt(2))


def test_seeds_2_3_special_values():
    assert ev('cos(5pi/12)') == add(mul(q(1, 4), (num(6), K.HALF)),
                                    mul(q(-1, 4), (K.TWO, K.HALF)))
    assert ev('tan(pi/12)') == add(K.TWO, mul(q(-1), (num(3), K.HALF)))
    assert ev('cos(pi/5)') == add(num(1, 4), mul(q(1, 4), (num(5), K.HALF)))
    assert ev('sin(30)', deg=1) == K.HALF
    assert ev('atan(sqrt(3))') == mul(q(1, 3), (K.PI, K.ONE))


@pytest.mark.parametrize('s, want', [
    ('1/2+1/3', (5, 6)), ('2^10', (1024, 1)), ('2^-3', (1, 8)), ('-2^2', (-4, 1)),
    ('(-2)^2', (4, 1)), ('10/4', (5, 2)), ('5!', (120, 1)), ('0!', (1, 1)), ('0^0', (1, 1)),
    ('2^(1/2)*2^(1/2)', (2, 1)), ('surd(-8,3)', (-2, 1)), ('log(100)', (2, 1)),
    ('log(8,2)', (3, 1)), ('log10(1000)', (3, 1)), ('ln(e^2)', (2, 1)), ('exp(0)', (1, 1)),
    ('abs(3+4i)', (5, 1)), ('abs(-7/2)', (-7, -2)), ('2*3-4/2', (4, 1)),
    ('1-2-3', (-4, 1)), ('2^3^2', (512, 1)), ('-(-3)', (3, 1)), ('+5', (5, 1)),
    ('3!!', (720, 1)), ('floor(7/2)', (3, 1)), ('ceil(7/2)', (4, 1)), ('sign(-3)', (-1, 1)),
])
def test_arithmetic(s, want):
    assert ev(s) == num(want[0], want[1])


def test_gaussian_arithmetic():
    assert ev('i^2') == K.MONE
    assert ev('1/(1+i)') == K.num(1, -1, 2)
    assert ev('(2i)^3') == K.num(0, -8)
    assert ev('3+4i') == K.num(3, 4)
    assert ev('(1+i)(1-i)') == K.TWO


def test_symbolic_arithmetic():
    x = sym('x')
    assert ev('x-x') == K.ZERO
    assert ev('x/x') == K.ONE
    assert ev('2(x+1)+x') == add(times(num(3), x), K.TWO)
    assert ev('e^(ln(x))') == x
    assert ev('x^2*x^3') == pw(x, num(5))
    assert ev('-x^2') == mul(q(-1), (x, K.TWO))           # TI: -(x^2)
    assert ev('1/2x') == mul(K.HALF, (x, K.ONE))          # TI: (1/2)*x
    assert ev('2x^2+3x/2-sin(x)') == add(mul(q(2), (x, K.TWO)), mul(q(3, 2), (x, K.ONE)),
                                         neg(K.fn_(K.SIN, x)))


def test_functions():
    x = sym('x')
    assert ev('exp(x)') == pw(K.E, x)
    assert ev('sqrt(x)') == pw(x, K.HALF)
    assert ev('surd(x,3)') == pw(x, num(1, 3))
    assert ev('surd(x,n)') == pw(x, pw(sym('n'), K.MONE))
    assert ev('log(x)') == K.mul_(K.ONE, [(K.fn_(K.LN, x), K.ONE), (K.LN10, K.MONE)])
    assert ev('log10(x)') == ev('log(x)')
    assert ev('log(x,2)') == K.mul_(K.ONE, [(K.fn_(K.LN, x), K.ONE),
                                            (K.fn_(K.LN, K.TWO), K.MONE)])
    assert ev('asec(x)') == K.fn_(K.ACOS, pw(x, K.MONE))
    assert ev('acsc(x)') == K.fn_(K.ASIN, pw(x, K.MONE))
    assert ev('acot(x)') == K.fn_(K.ATAN, pw(x, K.MONE))
    assert ev('asec(2)') == mul(q(1, 3), (K.PI, K.ONE))
    for f in ('sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'asin', 'acos', 'atan', 'sinh', 'cosh',
              'tanh', 'ln', 'abs', 'sign', 'floor', 'ceil'):
        assert ev('%s(x)' % f) == K.fn_(P.ONEARG[f], x), f
    assert ev('O(x^6)') == K.mk((K.BIGO, pw(x, num(6))))
    assert ev('sin(1-x)') == neg(K.fn_(K.SIN, add(x, K.MONE)))     # D15


def test_inverse_hyperbolic_values():
    for f, ref, pts in (('asinh', cmath.asinh, (-2.5, -0.3, 0.7, 4.0)),
                        ('acosh', cmath.acosh, (1.2, 3.0, 9.5)),
                        ('atanh', cmath.atanh, (-0.9, -0.2, 0.4, 0.8))):
        r = ev('%s(x)' % f)
        for p in pts:
            assert close(val(r, {'x': complex(p)}), ref(p)), (f, p)
    assert ev('asinh(0)') == K.ZERO and ev('atanh(0)') == K.ZERO and ev('acosh(1)') == K.ZERO


@pytest.mark.parametrize('s', ['sin(x,y)', 'sin()', 'log(1,2,3)', 'surd(8)', 'sqrt(1,2)',
                               'exp()', 'O(x,2)', 'asec(1,2)'])
def test_function_argument_counts(s):
    with pytest.raises(CasError) as e:
        ev(s)
    assert e.value.args[0] == P.M_ARGS


def test_undefined_and_caps():
    for s in ('1/0', 'tan(pi/2)', 'ln(0)', '0^-1', '(-1)!'):
        with pytest.raises(K.Undefined):
            ev(s)
        assert ev(s, soft=False) is None             # the driver gives None (10.2)
    with pytest.raises(CasError) as e:
        ev('2^(10^6)')
    assert e.value.args[0] == K.M_BIG


def test_names_and_constants():
    for s, want in (('pi', K.PI), ('e', K.E), ('i', K.I), ('oo', K.OO), ('inf', K.OO),
                    ('infinity', K.OO), ('undef', K.UNDEF), ('true', K.TRUE),
                    ('false', K.FALSE)):
        assert ev(s) == want, s
    for s in ('theta', 'mid', 'left', 'right', 'trap', 'x'):
        assert ev(s, ctxt=0) == sym(s), s
    assert ev('abc') == times(sym('a'), sym('b'), sym('c'))     # stage 5 cuts it
    assert ev(chr(0x3b8)) == sym('theta')
    assert ev('-oo') == K.mul_(K.MONE, [(K.OO, K.ONE)])
    assert ev('1/oo') == K.ZERO


def test_relations():
    x = sym('x')
    assert ev('2<3') == K.TRUE
    assert ev('x-x=1') == K.FALSE
    assert ev('x+1=x+1') == K.TRUE
    assert ev('x>3') == K.mk((K.LT, num(3), x))
    assert ev('3>=x') == K.mk((K.LE, x, num(3)))
    assert ev('x!=1') == K.mk((K.NE, x, K.ONE))
    assert ev('x=2') == K.mk((K.EQ, x, K.TWO))
    # sentinels: relations take them as they are (7.8), arithmetic refuses them
    assert ev('(2<3)=true') == K.mk((K.EQ, K.TRUE, K.TRUE))
    assert ev('true>(1<0)') == K.mk((K.LT, K.FALSE, K.TRUE))
    for s in ('(2<3)+1', '2*(1>2)', 'sin(2<3)', '-(1<2)', '(1<2)^2'):
        with pytest.raises(CasError) as e:
            ev(s)
        assert e.value.args[0] == K.M_RESULT, s


def test_lists_and_calls():
    x = sym('x')
    assert ev('[1,2,x]') == K.mk((K.LST, K.ONE, K.TWO, x))
    assert ev('{1,2}') == K.mk((K.LST, K.ONE, K.TWO))
    assert ev('[]') == K.mk((K.LST,))
    assert ev('x=1,x=2') == K.mk((K.LST, K.mk((K.EQ, x, K.ONE)), K.mk((K.EQ, x, K.TWO))))
    assert ev('[[1],2]') == K.mk((K.LST, K.mk((K.LST, K.ONE)), K.TWO))
    assert ev('foo(x,2)') == K.mk((K.CALL, sym('foo'), x, K.TWO))
    assert ev('f(2)') == K.mk((K.CALL, sym('f'), K.TWO))
    y = "y'"
    eq = K.mk((K.EQ, add(sym(y), sym('y')), K.ZERO))
    assert ev("desolve(y'+y=0,y)") == K.mk((K.CALL, sym('desolve'), eq, sym('y')))
    assert ev("y'(0)", ctxt=0) == times(sym(y), K.ZERO)     # no desolve: y'*(0)
    assert ev("desolve([y''+y=0,y(0)=1],y)") is not None


def test_syntax_errors():
    with pytest.raises(CasError) as e:
        drive(P.g_eval(P.rpn(P.lex("x'")), ctx()), True)
    assert e.value.args[0] == P.M_PRIME
    for s in ('1+(2=>a)', '(a:=2)+1'):
        with pytest.raises(CasError) as e:
            ev(s, ctxt=0)
        assert e.value.args[0] == P.M_ASSIGN
    with pytest.raises(CasError) as e:
        ev('purge(x)+1')
    assert e.value.args[0] == P.M_PURGE
    with pytest.raises(CasError) as e:
        drive(P.g_eval([], ctx()), True)
    assert e.value.args[0] == P.M_SYNTAX
    with pytest.raises(CasError):
        drive(P.g_eval([('w', 1, 0)], ctx()), True)


# -- canonicity through the parser (the frozen node API, gen.build) --------------------------------

@pytest.mark.parametrize('seed', range(6))
def test_parse_equals_build(seed):
    """g_eval(text(t)) is the same id as gen.build(t), on random trees, on the user path and the
    answer path (inert, no stage 6); Undefined/CasError agree too."""
    g = gen.Gen(seed, syms=('x', 'y'))
    n = 0
    for _ in range(40):
        t = g.tree(3)
        s = gen.text(t)
        try:
            want = gen.build(t, K)
        except (K.Undefined, CasError) as e:
            with pytest.raises(type(e)):
                ev(s)
            continue
        assert ev(s) == want, s
        assert ev(s, ctxt=0, inert=1) == want, s
        for v in g.variants(t, 2):
            assert ev(gen.text(v)) == want, gen.text(v)
        n += 1
        K.reset()
    assert n > 20


# -- degree mode (6.5) -----------------------------------------------------------------------------

@pytest.mark.parametrize('s, want', [
    ('sin(30)', (1, 2)), ('cos(60)', (1, 2)), ('tan(45)', (1, 1)), ('sin(90)', (1, 1)),
    ('cos(180)', (-1, 1)), ('sin(-30)', (-1, 2)), ('cot(45)', (1, 1)), ('sec(60)', (2, 1)),
    ('asin(1/2)', (30, 1)), ('acos(0)', (90, 1)), ('atan(1)', (45, 1)), ('asin(-1)', (-90, 1)),
    ('acos(-1/2)', (120, 1)), ('asec(2)', (60, 1)), ('acot(1)', (45, 1)), ('acsc(2)', (30, 1)),
])
def test_degree_values(s, want):
    assert ev(s, deg=1) == num(want[0], want[1])


def test_degree_builder_is_the_constructor_map():
    x = sym('x')
    u = add(mul(q(1, 180), (x, K.ONE), (K.PI, K.ONE)), mul(q(1, 6), (K.PI, K.ONE)))
    assert ev('sin(x+30)', deg=1) == K.fn_(K.SIN, u)
    # the same node as the radian text pi*x/180+pi/6 (what expand gives): survives expand, F4
    assert ev('sin(x+30)', deg=1) == ev('sin(pi*x/180+pi/6)')
    assert ev('cos(2x)', deg=1) == ev('cos(pi*x/90)')
    assert ev('tan(2x+30)', deg=1) == ev('tan(pi*x/90+pi/6)')
    assert ev('tan(2(x+15))', deg=1) == ev('tan(pi*(x+15)/90)')   # a product: not distributed
    assert ev('asin(x)', deg=1) == K.mul_(num(180), [(K.fn_(K.ASIN, x), K.ONE),
                                                     (K.PI, K.MONE)])
    assert ev('asin(x)+30', deg=1) == add(ev('asin(x)', deg=1), num(30))
    assert ev('sin(asin(x))', deg=1) == x
    assert ev('sin(x+30)', deg=1, inert=1, ctxt=0) == ev('sin(x+30)', deg=1)
    for s in ('sinh(2)', 'ln(2)', 'exp(3)', 'sqrt(x)', 'sin(30)'):   # not angles; radians
        if s != 'sin(30)':
            assert ev(s, deg=1) == ev(s), s
    assert ev('sin(30)') == K.fn_(K.SIN, num(30))


def test_degree_numeric():
    for s, ref in (('sin(x)', lambda d: math.sin(math.radians(d))),
                   ('cos(3x+10)', lambda d: math.cos(math.radians(3 * d + 10))),
                   ('atan(x)', lambda d: math.degrees(math.atan(d))),
                   ('asin(x/9)', lambda d: math.degrees(math.asin(d / 9)))):
        r = ev(s, deg=1)
        for d in (-7.5, 1.25, 4.0):
            assert close(val(r, {'x': complex(d)}).real, ref(d)), (s, d)


# -- stage 6: variables, functions and macros at token level (7.6) ---------------------------------

def test_variables(sess):
    sess.VARS.update({'a': '3', 'b': 'c+1', 'c': '2', 'p': 'x^2+3*x'})
    assert text(P.tokens('a+1')) == '(3)+1'
    assert ev('a+1') == num(4)
    assert ev('2a') == num(6)
    assert ev('a^2') == num(9)
    assert ev('ab') == num(9)                            # cut into a*b: 3*(2+1)
    assert text(P.tokens('b')) == '((2)+1)'
    assert ev('b') == num(3)
    x = sym('x')
    assert ev('p') == add(pw(x, K.TWO), times(num(3), x))
    assert text(P.tokens('a+1', 0)) == 'a+1'            # the answer path: no stage 6
    assert ev('a', ctxt=0) == sym('a')
    for t in P.tokens('1+a'):                            # spliced tokens take a's offsets
        assert t[2:4] in ((0, 1), (1, 2), (2, 3)), t
    assert [t[2:4] for t in P.tokens('1+a')][2:] == [(2, 3)] * 3


def test_store_targets_are_not_expanded(sess):
    sess.VARS.update({'a': '3', 'x': '5'})
    assert text(P.tokens('7=>a')) == '7=>a'
    assert text(P.tokens('a+1=>a')) == '(3)+1=>a'
    assert text(P.tokens('a:=x+1')) == 'a:=(5)+1'
    assert text(P.tokens('purge(a,x)')) == 'purge(a,x)'
    assert text(P.tokens('purge(a)+a')) == 'purge(a)+(3)'


def test_user_functions(sess):
    sess.FUNCS.update({'f': (('x',), 'x^2+1'), 'g': (('x', 'y'), 'x*y'),
                       'h': (('x',), 'x+c'), 'r': (('x',), 'r(x)+1')})
    sess.VARS['c'] = '10'
    x = sym('x')
    assert text(P.tokens('f(3)')) == '((3)^2+1)'
    assert ev('f(3)') == num(10)
    assert ev('f(x+1)') == add(pw(add(x, K.ONE), K.TWO), K.ONE)
    assert ev('f(f(2))') == num(26)
    assert ev('2f(3)') == num(20)
    assert ev('f(2)+f(3)') == num(15)
    assert ev('g(2,3)') == num(6)
    assert ev('g(f(1),x-1)') == times(K.TWO, add(x, K.MONE))
    assert ev('h(1)') == num(11)                         # the body's names expand too
    for s in ('g(2)', 'f(1,2)', 'f()'):
        with pytest.raises(CasError) as e:
            ev(s)
        assert e.value.args[0] == P.M_ARGS, s
    with pytest.raises(CasError) as e:
        ev('r(1)')                                       # recursive: nesting cap
    assert e.value.args[0] == P.M_DEEP


def test_parameters_shadow_stored_names(sess):
    sess.FUNCS['f'] = (('x',), 'x^2')
    sess.VARS['x'] = '5'
    assert ev('f(3)') == num(9)
    assert ev('f(x)') == num(25)


def test_expansion_caps(sess):
    sess.VARS['a'] = '1'
    assert ev('+'.join(['a'] * P.MAXEXP)) == num(P.MAXEXP)
    with pytest.raises(CasError) as e:
        ev('+'.join(['a'] * (P.MAXEXP + 1)))
    assert e.value.args[0] == P.M_DEEP
    for i in range(P.MAXDEF + 1):                        # v0 -> v1 -> ... -> v16 -> 7
        sess.VARS['v%d' % i] = 'v%d' % (i + 1) if i < P.MAXDEF else '7'
    with pytest.raises(CasError) as e:
        ev('v0')
    assert e.value.args[0] == P.M_DEEP
    assert ev('v1') == num(7)                            # 16 nested expansions are fine


def test_macros(sess):
    assert text(P.tokens('polararea(2cos(t),t,0,pi)')) == \
        '(integrate(((2*cos(t)))^2/2,(t),(0),(pi)))'
    r = ev('polararea(2cos(t),t,0,pi)')
    a, c = SEEN[-1]
    t = sym('t')
    assert a == (mul(K.HALF, (pw(times(K.TWO, K.fn_(K.COS, t)), K.TWO), K.ONE)), t, K.ZERO,
                 K.PI) and r == a[0]
    assert text(P.tokens('paramarea(t^2,t^3,t,0,1)')) == \
        '(integrate(((t^3))*diff((t^2),(t)),(t),(0),(1)))'
    assert text(P.tokens('arclen(x^2,x,0,1)')) == \
        '(integrate(sqrt(1+diff((x^2),(x))^2),(x),(0),(1)))'
    assert text(P.tokens('arclen(cos(t),sin(t),t,0,pi)')) == \
        '(integrate(sqrt(diff((cos(t)),(t))^2+diff((sin(t)),(t))^2),(t),(0),(pi)))'
    for s in ('polararea(1,t,0)', 'arclen(x,0,1)', 'arclen(a,b,c,d,e,f)'):
        with pytest.raises(CasError) as e:
            P.tokens(s)
        assert e.value.args[0] == P.M_ARGS, s


def test_sum_index(sess):
    assert text(P.tokens('sum(i^2,i,1,n)')) == 'sum(k^2,k,1,n)'
    assert text(P.tokens('sum(i*k,i,1,n)')) == 'sum(j*k,j,1,n)'
    assert text(P.tokens('sum(i*k*j,i,1,n)')) == 'sum(m*k*j,m,1,n)'
    assert text(P.tokens('sum(i,i,1,10)+i')) == 'sum(k,k,1,10)+i'
    assert text(P.tokens('sum(i^2,k,1,n)')) == 'sum(i^2,k,1,n)'      # i: the imaginary unit
    assert text(P.tokens('sum(i,i=1,3)')) == 'sum(k,k=1,3)'
    assert text(P.tokens('riemann(i^2,i,0,1,4,mid)')) == 'riemann(k^2,k,0,1,4,mid)'
    sess.VARS['k'] = '2'
    assert text(P.tokens('sum(i^2,i,1,n)')) == 'sum(j^2,j,1,n)'      # k is stored
    assert text(P.tokens('sum(sum(i*j,i,1,n),j,1,n)')) == 'sum(sum(m*j,m,1,n),j,1,n)'


def test_stage6_without_session(monkeypatch):
    monkeypatch.setattr(P, 'SESS', None)
    assert text(P.tokens('a+1')) == 'a+1'
    assert text(P.tokens('sum(i^2,i,1,n)')) == 'sum(k^2,k,1,n)'
    assert ev('diff(x^2,x)') == K.mk((K.CALL, sym('diff'), pw(sym('x'), K.TWO), sym('x')))


# -- commands, the trampoline protocol and the default result path ---------------------------------

def test_commands(sess):
    x = sym('x')
    assert ev('twice(x)+1') == add(times(K.TWO, x), K.ONE)
    assert NEED == ['fake']
    assert ev('tw(3)') == num(6)                         # an alias
    assert ev('twice(twice(x))') == times(num(4), x)
    assert ev('nested(x)') == add(times(K.TWO, x), K.ONE)
    assert ev('fail(x)') is None
    assert ev('soft(x)+1', soft=False) is None
    assert ev('2*fail(x)') is None
    for s in ('twice(1,2)', 'twice()', 'seeargs(1,2,3,4)'):
        with pytest.raises(CasError) as e:
            ev(s)
        assert e.value.args[0] == P.M_ARGS, s
    c = ctx(deg=1)
    assert ev('seeargs(x,[1,2])', c=c) == x
    assert SEEN[-1] == ((x, K.mk((K.LST, K.ONE, K.TWO))), [1, None, 0, 0])


def test_inert_commands(sess):
    x = sym('x')
    assert ev('twice(x)', inert=1) == K.mk((K.CALL, sym('twice'), x))
    assert ev('tw(x)', inert=1) == K.mk((K.CALL, sym('twice'), x))
    assert ev('int(x,x)', inert=1, ctxt=0) == K.mk((K.CALL, sym('integrate'), x, x))
    assert ev('approx(x)', inert=1) == K.mk((K.CALL, sym('approx'), x))
    assert NEED == [] and SEEN == []


def test_default_result_path(sess, monkeypatch):
    x = sym('x')
    S = sym('simplified')
    cand = []
    monkeypatch.setattr(NORM, 'g_autosimp', g_autosimp)
    monkeypatch.setattr(P.A, 'simplify_candidate', lambda e: cand.append(e) or True)
    assert ev('x+1') == S
    assert NEED == ['norm'] and SEEN == [('autosimp', add(x, K.ONE))]
    assert ev('noauto(x)') == x                          # F_NOAUTO: skipped
    assert ev('(noauto(x))') == x                        # a group keeps the flags
    assert ev('noauto(x)+1') == S                        # the last item is +, not the command
    assert ev('x+1', inert=1) == add(x, K.ONE)           # inert: nothing is simplified
    monkeypatch.setattr(P.A, 'simplify_candidate', lambda e: False)
    del SEEN[:]
    assert ev('x+1') == add(x, K.ONE) and SEEN == []
    assert ev('always(x)') == S                          # F_ALWAYSAUTO: always
    monkeypatch.setattr(NORM, 'g_autosimp', g_autonone)
    assert ev('always(x)') == x                          # a failed simplify keeps r


def test_default_path_uses_simplify_candidate(sess):
    """With the real CVALG predicate (8.7): a plain non-candidate loads no lazy module (7.8);
    a candidate (tan, a sum with a negative power) goes through norm.g_autosimp."""
    assert ev('x^2+1') == add(pw(sym('x'), K.TWO), K.ONE)
    assert ev('sin(x)+sqrt(2)') is not None
    assert 'norm' not in NEED and SEEN == []
    x = sym('x')
    for s, want in (('tan(x)', K.fn_(K.TAN, x)), ('x+1/x', add(x, pw(x, K.MONE)))):
        assert ev(s) == want
        assert NEED[-1] == 'norm' and SEEN[-1] == ('autosimp', want)
    del SEEN[:]
    assert ev('noauto(tan(x))') == K.fn_(K.TAN, x) and SEEN[-1][0] != 'autosimp'


# -- floats: exact() and approx() (6.3, D8) ---------------------------------------------------------

@pytest.mark.parametrize('s', ['0.25', '0.1', '2.5E-3', '1E20', '123456789012345', '1.5E-10',
                               '3.14159265358979', '0.3', '9.99999999999999E307', '1E-300',
                               '4.94065645841247E-324', '2.2250738585072E-308', '1.1',
                               '0.000123', '7E22', '-0.5', '-1234.5678'])
def test_exact(s):
    f = Fraction(s)
    assert P.exact(float(s)) == K.num(f.numerator, 0, f.denominator)


def test_exact_random():
    r = random.Random(15)
    for _ in range(3000):
        digits = r.randint(1, 15)
        m = r.randint(10 ** (digits - 1), 10 ** digits - 1) * r.choice((1, -1))
        e = r.randint(-320, 300)
        s = '%dE%d' % (m, e)
        v = float(s)
        if v == 0.0 or v - v != 0:
            continue
        f = Fraction(s)
        if abs(v) < 2.2250738585072014e-308:
            continue                                     # subnormal: fewer than 15 digits
        assert P.exact(v) == K.num(f.numerator, 0, f.denominator), s
        K.reset()
    assert P.exact(0.0) == K.ZERO and P.exact(-0.0) == K.ZERO


def test_float_input_runs_exactly_then_approx(sess):
    x = sym('x')
    c = ctx()
    assert ev('0.5+x', c=c) == add(K.flt(0.5), x) and c[P.X_APPROX] == 1
    assert ev('0.1+0.2') == K.flt(0.3)
    assert ev('2.0*x') == times(K.flt(2.0), x)
    assert ev('x^0.5') == pw(x, K.HALF)                  # exact exponent: sqrt(x)
    assert ev('2.5E-3x') == times(K.flt(0.0025), x)
    c = ctx()
    assert ev('seeargs(0.25)', c=c) == K.flt(0.25)       # the command saw 1/4, the result 0.25
    assert SEEN[-1][0] == (num(1, 4),) and SEEN[-1][1][P.X_APPROX] == 1
    c = ctx(inert=1)
    assert ev('0.5', c=c, ctxt=0) == K.flt(0.5) and c[P.X_APPROX] == 0
    assert ev('1/2+x') == add(K.HALF, x)                 # no float: exact


def test_approx_forms():
    x = sym('x')
    y = sym('y')
    A = P.approx
    assert A(num(1, 3)) == K.flt(1 / 3)
    assert A(K.ONE) == K.flt(1.0)
    assert A(K.PI) == K.flt(math.pi)
    assert A(add(K.HALF, x)) == add(K.flt(0.5), x)
    assert A(add(x, K.ONE)) == add(x, K.flt(1.0))
    assert A(add(x, K.PI)) == add(x, K.flt(math.pi))
    assert A(neg(x)) == neg(x)                           # unit coefficients stay
    assert A(x) == x
    assert A(mul(K.HALF, (x, K.ONE))) == times(K.flt(0.5), x)
    assert A(mul(K.ONE, (K.TWO, K.HALF), (x, K.ONE))) == times(K.flt(math.sqrt(2)), x)
    assert A(mul(q(1, 3), (x, K.TWO))) == K.mul_(K.flt(1 / 3), [(x, K.TWO)])
    assert A(mul(q(2), (x, K.TWO), (y, K.ONE))) == K.mul_(K.flt(2.0), [(x, K.TWO), (y, K.ONE)])
    assert A(add(mul(q(2), (x, K.TWO)), times(K.TWO, y))) == \
        add(K.mul_(K.flt(2.0), [(x, K.TWO)]), times(K.flt(2.0), y))
    assert A(pw(K.E, x)) == pw(K.E, x)
    assert A(pw(K.TWO, x)) == pw(K.TWO, x)
    assert A(pw(x, K.PI)) == pw(x, K.flt(math.pi))
    assert A(pw(K.PI, x)) == pw(K.flt(math.pi), x)
    assert A(mul(K.HALF, (K.fn_(K.SIN, x), K.ONE))) == times(K.flt(0.5), K.fn_(K.SIN, x))
    assert A(K.fn_(K.SIN, mul(K.HALF, (x, K.ONE)))) == K.fn_(K.SIN, times(K.flt(0.5), x))
    r = A(K.fn_(K.LN, num(-2)))
    assert K.N[r][0] == K.FLT and close(complex(K.N[r][1], K.N[r][2]), cmath.log(-2))
    assert A(K.fn_(K.SIN, K.ONE)) == K.flt(math.sin(1))
    assert A(K.OO) == K.OO
    assert A(K.mul_(K.MONE, [(K.OO, K.ONE)])) == K.mul_(K.MONE, [(K.OO, K.ONE)])
    assert A(K.TRUE) == K.TRUE
    assert A(K.mk((K.LST, K.HALF, x))) == K.mk((K.LST, K.flt(0.5), x))
    assert A(K.rel_(K.EQ, x, K.HALF)) == K.mk((K.EQ, x, K.flt(0.5)))
    assert A(K.mk((K.CALL, sym('integrate'), x, x, K.ZERO, K.HALF))) == \
        K.mk((K.CALL, sym('integrate'), x, x, K.flt(0.0), K.flt(0.5)))
    big = K.num(10 ** 400)
    assert A(add(big, x)) == add(big, x)                 # does not evaluate: stays exact
    assert A(K.num(1, 1)) == K.flt(1.0, 1.0)
    e = add(times(K.TWO, x), mul(K.ONE, (num(3), K.HALF), (y, K.ONE)), K.PI)
    r = A(e)
    pt = {'x': 0.7 + 0j, 'y': -1.3 + 0j}
    assert close(val(r, pt), val(e, pt))


def test_approx_command(sess):
    x = sym('x')
    assert ev('approx(1/3)') == K.flt(1 / 3)
    assert ev('evalf(pi)') == K.flt(math.pi)
    assert ev('approx(sqrt(2)*x)') == times(K.flt(math.sqrt(2)), x)
    assert ev('approx(x^2/3)') == K.mul_(K.flt(1 / 3), [(x, K.TWO)])
    with pytest.raises(CasError):
        ev('approx(1,2)')


def exact_left(r):
    """The NUM nodes approx() may leave (its docstring): exponents of non-constant bases, the
    coefficients 1 and -1, a zero constant, a NUM base under a non-constant exponent."""
    bad = []
    st = [(r, 'root')]
    while st:
        n, pos = st.pop()
        t = K.N[n]
        if t[0] == K.NUM:
            if not (pos == 'exp' or pos == 'base' or (pos == 'coef' and n in (K.ONE, K.MONE))
                    or (pos == 'const' and n == K.ZERO)):
                bad.append((n, pos))
        elif t[0] == K.ADD:
            st.append((t[1], 'const'))
            for j in range(2, len(t), 2):
                st.append((t[j], 'term'))
                st.append((t[j + 1], 'coef'))
        elif t[0] == K.MUL:
            st.append((t[1], 'coef'))
            for j in range(2, len(t), 2):
                st.append((t[j], 'base' if K.V[t[j + 1]] else 'other'))
                st.append((t[j + 1], 'exp' if K.V[t[j]] else 'other'))
        elif t[0] >= K.COMP:
            for c in t[1:]:
                st.append((c, 'arg'))
    return bad


def test_approx_numeric_agreement():
    g = gen.Gen(7, syms=('x',), funcs=('sin', 'cos', 'exp', 'sqrt', 'ln', 'atan'))
    n = 0
    for _ in range(80):
        t = g.tree(3)
        try:
            e = gen.build(t, K)
            r = P.approx(e)
        except (K.Undefined, CasError):
            continue
        assert P.approx(r) == r, gen.text(t)             # idempotent
        assert exact_left(r) == [], gen.text(t)
        for p in (0.37, 1.9):
            try:
                a = val(e, {'x': complex(p)})
                b = val(r, {'x': complex(p)})
            except (ZeroDivisionError, OverflowError, ValueError):
                continue
            if abs(a) < 1e12:
                assert close(b, a, 1e-9), gen.text(t)
                n += 1
        K.reset()
    assert n > 60


# -- tcode and inst: templates and rule patterns (7.8, 9.2-9.6) -------------------------------------

def keep_patterns(m, ids):
    """Patterns live in RULECACHE (the invariant scan allows WILD only there)."""
    ids = K.keep(m, tuple(ids))
    K.RULECACHE['test'] = {0: tuple((p, '', '') for p in ids)}
    return ids


def wild(letter):
    s, c = P.WSLOT[letter]
    return K.mk((K.WILD, s, c))


def test_tcode_caches():
    c = P.tcode('L^(N+1)/(A*(N+1))')
    assert c == P.rpn(P.lex('L^(N+1)/(A*(N+1))'))
    assert P.tcode('L^(N+1)/(A*(N+1))') is c and K.TCACHE['L^(N+1)/(A*(N+1))'] is c
    K.reset()
    assert K.TCACHE == {}


def test_tcode_cache_retains_only_latest_template():
    for value in range(32):
        template = 'x^2+%d' % value
        code = P.tcode(template)
        assert list(K.TCACHE) == [template]
        assert K.TCACHE[template] is code
        assert P.tcode(template) is code


def test_tcode_eviction_preserves_previously_returned_program():
    previous = P.tcode('U^2+1')
    saved = list(previous)
    latest = P.tcode('V+2')
    env = [0] * P.NSLOT
    env[P.WSLOT['U'][0]] = K.num(3)
    env[P.WSLOT['V'][0]] = K.num(5)
    assert P.inst(previous, env) == K.TEN
    assert P.inst(latest, env) == K.num(7)
    assert previous == saved and list(K.TCACHE) == ['V+2']
    assert K.TCACHE['V+2'] is latest
    K.reset()
    env = [0] * P.NSLOT
    env[P.WSLOT['U'][0]] = K.num(4)
    assert P.inst(previous, env) == K.num(17)
    assert previous == saved and not K.TCACHE


def test_inst_patterns():
    m = K.NN
    pats = [P.inst(P.tcode(s), None) for s in ('L^N', 'cos(U)^2*R', 'x', 'sin(L)', 'e^L',
                                                 'ln(U)+ln(V)+R', 'K^L', 'sec(L)*tan(L)',
                                                 'Q^(-1)', 'T', 'P*M')]
    for c in 'UVWABCKMNPLQR':
        pats.append(wild(c))
    pats.append(K.fn_(K.COS, wild('U')))
    pats.append(K.fn_(K.LN, wild('U')))
    pats.append(K.fn_(K.LN, wild('V')))
    ids = keep_patterns(m, pats)
    N = K.N
    assert N[ids[0]] == (K.MUL, K.ONE, wild('L'), wild('N'))
    t = N[ids[1]]
    assert t[:2] == (K.MUL, K.ONE) and sorted(zip(t[2::2], t[3::2])) == \
        sorted([(K.fn_(K.COS, wild('U')), K.TWO), (wild('R'), K.ONE)])
    assert N[ids[2]] == (K.WILD, P.XSLOT, 0)
    assert N[ids[3]] == (K.SIN, wild('L'))
    assert N[ids[4]] == (K.MUL, K.ONE, K.E, wild('L'))
    t = N[ids[5]]
    assert t[:2] == (K.ADD, K.ZERO) and t[3::2] == (K.ONE,) * 3 and sorted(t[2::2]) == \
        sorted([K.fn_(K.LN, wild('U')), K.fn_(K.LN, wild('V')), wild('R')])
    assert N[ids[6]] == (K.MUL, K.ONE, wild('K'), wild('L'))
    assert N[ids[8]] == (K.MUL, K.ONE, wild('Q'), K.MONE)
    assert N[ids[9]] == (K.WILD, P.TSLOT, 0)
    assert {N[wild(c)][2] for c in 'UVW'} == {P.W_ANY}
    assert {N[wild(c)][2] for c in 'ABCK'} == {P.W_FREE}
    assert (N[wild('M')][2], N[wild('N')][2], N[wild('P')][2], N[wild('L')][2],
            N[wild('Q')][2], N[wild('R')][2]) == (P.W_NUMB, P.W_NUMB, P.W_INT, P.W_LIN,
                                                  P.W_QUAD, P.W_REST)
    assert sorted(s for s, c in P.WSLOT.values()) == list(range(P.NSLOT))


def test_inst_design_tables_build():
    """Every rule string of DESIGN 9.2 and 9.3 compiles and builds in pattern mode."""
    m = K.NN
    lhs = ('L^N', 'L^(-1)', 'e^L', 'K^L', 'sin(L)', 'cos(L)', 'sec(L)^2', 'sec(L)',
           'sec(L)*tan(L)', 'Q^(-1)', 'cos(U)^2*R', 'ln(U)+ln(V)+R')
    ids = keep_patterns(m, [P.inst(P.tcode(s), None) for s in lhs])
    assert len(set(ids)) == len(lhs)


def env_of(**kw):
    env = [0] * P.NSLOT
    for k, v in kw.items():
        env[P.WSLOT[k][0]] = v
    return env


def subst_text(s, kw):
    """s with each name token in kw replaced by (its text)."""
    out = []
    pe = 0
    for t in P.lex(s):
        out.append(s[pe:t[2]])
        out.append('(%s)' % kw[t[1]] if t[0] == P.K_NAME and t[1] in kw else s[t[2]:t[3]])
        pe = t[3]
    return ''.join(out)


TEMPLATES = (
    'L^(N+1)/(A*(N+1))', 'ln(abs(L))/A', 'e^L/A', 'K^L/(A*ln(K))', '-cos(L)/A', 'sin(L)/A',
    'tan(L)/A', 'ln(abs(sec(L)+tan(L)))/A', 'sec(L)/A',
    '2*atan((2*A*x+B)/sqrt(4*A*C-B^2))/sqrt(4*A*C-B^2)',
    'cos(U)', '-sin(U)', 'sec(U)^2', 'sec(U)*tan(U)', '-csc(U)*cot(U)', '-csc(U)^2',
    '1/sqrt(1-U^2)', '-1/sqrt(1-U^2)', '1/(1+U^2)', 'cosh(U)', 'sinh(U)', '1-tanh(U)^2',
    '1/U', 'abs(U)/U', '0', 'asin(T)', 'pi-asin(T)', 'acos(T)', '2*pi-acos(T)',
    'atan(T)+pi', 'e^T', '(1-sin(U)^2)*R', 'ln(U*V)+R', 'log(U)', 'U!', 'exp(U)',
)


@pytest.mark.parametrize('s', TEMPLATES)
def test_inst_templates_agree_with_g_eval(s, monkeypatch):
    """inst(tcode(s), env) is g_eval of s with each letter replaced by its value's text."""
    monkeypatch.setattr(P, 'SESS', None)
    kw = {'L': '2*x+1', 'N': '3', 'A': '2', 'B': '-1', 'C': '5', 'K': '3', 'U': 'sin(x)+1',
          'V': 'x^2', 'T': '1/2', 'R': 'y', 'x': 'x'}
    env = [0] * P.NSLOT
    for k, v in kw.items():
        env[P.WSLOT[k][0]] = short(v)
    r = P.inst(P.tcode(s), env)
    assert r == short(subst_text(s, kw)), s


def test_inst_template_values():
    x = sym('x')
    env = env_of(L=add(times(K.TWO, x), K.ONE), N=num(3), A=K.TWO, x=x)
    assert P.inst(P.tcode('L^(N+1)/(A*(N+1))'), env) == \
        mul(q(1, 8), (add(times(K.TWO, x), K.ONE), num(4)))
    assert P.inst(P.tcode('x'), env) == x
    assert P.inst(P.tcode('pi-asin(T)'), env_of(T=K.HALF)) == mul(q(5, 6), (K.PI, K.ONE))
    assert P.inst(P.tcode('integrate(U,x)'), env_of(U=K.TWO, x=x)) == \
        K.mk((K.CALL, sym('integrate'), K.TWO, x))
    assert P.inst(P.tcode('[U,y]=2'), env_of(U=K.TWO)) == \
        K.rel_(K.EQ, K.mk((K.LST, K.TWO, sym('y'))), K.TWO)
    assert P.inst(P.tcode('sin(30)'), env) == K.fn_(K.SIN, num(30))     # no angle mode
    with pytest.raises(CasError):
        P.inst(P.tcode('U+1'), env)                      # U is unbound


# -- depth: nesting invariance (20.7) ---------------------------------------------------------------

def run_line(s, deg=0):
    return drive(P.g_eval(P.rpn(P.tokens(s)), ctx(deg)), True)


@pytest.mark.parametrize('kind', ['sin', 'square', 'frac', 'paren', 'sum', 'prod', 'exp', 'ln'])
def test_nesting_invariance(kind, evodepth):
    depths = []
    for n in (1, 8, 32):
        r, d, _ = evodepth.measure(run_line, gen.nested(kind, n))
        assert r is not None
        depths.append(d)
        K.reset()
    assert depths[0] == depths[1] == depths[2], (kind, depths)


def test_nesting_invariance_stage6(evodepth, sess):
    sess.FUNCS['f'] = (('x',), 'x^2+1')
    depths = []
    for n in (1, 4, 12):
        r, d, _ = evodepth.measure(run_line, 'f(' * n + 'x' + ')' * n)
        assert r is not None
        depths.append(d)
        K.reset()
    assert depths[0] == depths[1] == depths[2], depths
    depths = []
    for n in (1, 8, 32):
        r, d, _ = evodepth.measure(run_line, gen.nested('sin', n), 1)
        depths.append(d)
        K.reset()
    assert depths[0] == depths[1] == depths[2], depths
