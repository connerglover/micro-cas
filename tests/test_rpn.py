"""The shunting-yard (DESIGN 7.7): the RPN table, precedence, lists, calls, errors, and two
properties: random token lines give well-formed RPN or a CasError, and the RPN of a random
expression's text has the expression's value."""
import cmath
import random
import types

import pytest

import gen
import parse as P

CasError = P.K.CasError

CMDS = dict.fromkeys('simplify expand factor together approx solve diff integrate limit taylor '
                     'partfrac sum riemann desolve grad'.split(), 1)
ALIAS = dict.fromkeys('int d deriv lim series ratnormal dsolve gradient evalf'.split(), 1)
MACROS = dict.fromkeys('polararea paramarea arclen'.split(), 1)


@pytest.fixture(autouse=True)
def session(monkeypatch):
    monkeypatch.setattr(P, 'SESS', types.SimpleNamespace(VARS={}, FUNCS={}, CMDS=CMDS,
                                                         ALIAS=ALIAS, MACROS=MACROS))


def show(items):
    """RPN as in the DESIGN 7.7 table: calls as name/n, lists as L/n (L/n* at top level),
    groups as ()."""
    out = []
    for it in items:
        k = it[0]
        if k == 'n':
            v = it[1]
            out.append(('%d' % v[0] if v[1] == 1 else '%d/%d' % v) if type(v) is tuple
                       else repr(v))
        elif k in 'so':
            out.append(it[1])
        elif k == 'F':
            out.append('%s/%d' % (it[1], it[2]))
        elif k == 'L':
            out.append('L/%d%s' % (it[1], '*' if it[2] == -1 else ''))
        elif k == 'P':
            out.append('()')
        else:
            raise AssertionError(it)
    return ' '.join(out)


def user(s):
    """Stages 3-5 and 7 (the user path without context expansion)."""
    return show(P.rpn(P.ti_implicit(P.ti_rewrite(P.lex(s)))))


def short(s):
    """Stages 3 and 7 (templates, answer text, the 2D layout)."""
    return show(P.rpn(P.lex(s)))


# -- the DESIGN 7.7 table -------------------------------------------------------------------------

@pytest.mark.parametrize('s, want', [
    ('-x^2', 'x 2 ^ neg'),
    ('2^-3', '2 3 neg ^'),
    ('1/2x', '1 2 / x *'),
    ('a^b^c', 'a b c ^ ^'),
    ('diff(sin(x)^2,x,2)', 'x sin/1 2 ^ x 2 diff/3'),
])
def test_design_table(s, want):
    assert user(s) == want


# -- precedence and associativity -----------------------------------------------------------------

@pytest.mark.parametrize('s, want', [
    ('a+b*c', 'a b c * +'),
    ('a*b+c', 'a b * c +'),
    ('a-b-c', 'a b - c -'),
    ('a/b/c', 'a b / c /'),
    ('a/b*c', 'a b / c *'),
    ('a-b+c', 'a b - c +'),
    ('-a*b', 'a neg b *'),
    ('-a+b', 'a neg b +'),
    ('a+-b', 'a b neg +'),
    ('a--b', 'a b neg -'),
    ('+a', 'a'),
    ('a*+b', 'a b *'),
    ('2*-3^2', '2 3 2 ^ neg *'),
    ('a^-b^c', 'a b c ^ neg ^'),
    ('--a', 'a neg neg'),
    ('-a^-b', 'a b neg ^ neg'),
    ('a<b+c', 'a b c + <'),
    ('a+b=c*d', 'a b + c d * ='),
    ('a=b<c', 'a b = c <'),                     # relations are left-associative
    ('a!=b', 'a b !='),
    ('a<=b', 'a b <='),
    ('a>=-b', 'a b neg >='),
    ('3!', '3 !'),
    ('3!^2', '3 ! 2 ^'),
    ('2^3!', '2 3 ! ^'),
    ('-x!', 'x ! neg'),
    ('n!!', 'n ! !'),
    ("x'", "x '"),
    ("y'", "y'"),
    ("y''+y", "y'' y +"),
    ('x=>b', 'x b =>'),
    ('a=>b=>c', 'a b c => =>'),                 # => is right-associative
    ('x+1=>b', 'x 1 + b =>'),
    ('a=b=>c', 'a b = c =>'),
    ('f(x):=x^2', 'x f/1 x 2 ^ :='),
    ('a:=b:=c', 'a b c := :='),
    ('(a+b)*c', 'a b + () c *'),
    ('a*(b+c)', 'a b c + () *'),
    ('((a))', 'a () ()'),
    ('-(a)', 'a () neg'),
    ('(-a)^2', 'a neg () 2 ^'),
    ('2(x+1)', '2 x 1 + () *'),
    ('(x+1)(x-1)', 'x 1 + () x 1 - () *'),
    ('x^2y', 'x 2 ^ y *'),
    ('2pir^2', '2 pi * r 2 ^ *'),
    ('-xy', 'x neg y *'),
    ('3!x', '3 ! x *'),
    ('sin x^2', 'x 2 ^ sin/1'),
    ('sin^2x', 'x sin/1 2 ^'),
    ('2E-1x', '0.2 x *'),
])
def test_precedence(s, want):
    assert user(s) == want


# -- lists, calls, groups -------------------------------------------------------------------------

@pytest.mark.parametrize('s, want', [
    ('x=1,x=2', 'x 1 = x 2 = L/2*'),
    ('x=-1,x=1', 'x 1 neg = x 1 = L/2*'),
    ('a,b,c', 'a b c L/3*'),
    ('[]', 'L/0'),
    ('[1]', '1 L/1'),
    ('[1,2]', '1 2 L/2'),
    ('{1,2}', '1 2 L/2'),
    ('[[1,2],[3]]', '1 2 L/2 3 L/1 L/2'),
    ('(1,2)', '1 2 L/2'),
    ('(x)', 'x ()'),
    ('f()', 'f/0'),
    ('f(x)', 'x f/1'),
    ('g(x,y)', 'x y g/2'),
    ('f(g(x),h(y,z))', 'x g/1 y z h/2 f/2'),
    ('max(1,2,3)', '1 2 3 max/3'),
    ('sin(x)cos(x)', 'x sin/1 x cos/1 *'),
    ('solve([x+y=1,x-y=3],[x,y])', 'x y + 1 = x y - 3 = L/2 x y L/2 solve/2'),
    ('limit(1/x,x,0,1)', '1 x / x 0 1 limit/4'),
    ('d(x^2,x)', 'x 2 ^ x d/2'),
    ('d(x+1)', 'd x 1 + () *'),
    ('1+x+x^2/2+O(x^3)', '1 x + x 2 ^ 2 / + x 3 ^ O/1 +'),
    ("desolve([y''+y=0,y(0)=1,y'(0)=0],y)",
     "y'' y + 0 = 0 y/1 1 = 0 y'/1 0 = L/3 y desolve/2"),
    ('riemann(x^2,x,0,1,4,mid)', 'x 2 ^ x 0 1 4 mid riemann/6'),
    ('taylor(e^x,x=0,6)', 'e x ^ x 0 = 6 taylor/3'),
    ('f(x,[1,2])', 'x 1 2 L/2 f/2'),
])
def test_lists_calls_groups(s, want):
    assert user(s) == want


def test_item_token_indices():
    toks = P.ti_implicit(P.ti_rewrite(P.lex('2f(x,[y])+(z)')))
    items = P.rpn(toks)
    # every item keeps its token index (DESIGN 13.8): the number, the name, the closing
    # bracket of a call/list/group, the operator
    assert items == [('n', (2, 1), 0), ('s', 'x', 4), ('s', 'y', 7), ('L', 1, 8),
                     ('F', 'f', 2, 9), ('o', '*', 1), ('s', 'z', 12), ('P', 13), ('o', '+', 10)]
    for it in items:
        ti = it[-1]
        assert 0 <= ti < len(toks)


def test_review_sin_through_lex_and_rpn_alone():
    assert short('sin(x)') == 'x sin/1'
    assert short('integrate(f(x),x)') == 'x f/1 x integrate/2'
    assert short('foo(x)') == 'x foo/1'          # an unknown call in an answer
    assert short('O(x^6)') == 'x 6 ^ O/1'


def test_short_path_answer_text():
    """Printer text parses through lex and rpn alone (DESIGN 12.1, 13.1)."""
    assert short('x=-1,x=1') == 'x 1 neg = x 1 = L/2*'
    assert short('2*sqrt(3)*i') == '2 3 sqrt/1 * i *'
    assert short('e^(x^2)') == 'e x 2 ^ () ^'
    assert short('-oo') == 'oo neg'
    assert short('x>3') == 'x 3 >'
    assert short('true') == 'true'
    assert short("y'=3*y") == "y' 3 y * ="
    assert short('[]') == 'L/0'
    assert short('') == ''


# -- errors ---------------------------------------------------------------------------------------

@pytest.mark.parametrize('s, msg, pos', [
    ('f(a,,b)', 'Empty argument', 4),
    ('(a]', 'Mismatched bracket', 2),
    ('[a)', 'Mismatched bracket', 2),
    ('{a]', 'Mismatched bracket', 2),
    ('()', 'Empty ()', 1),
    ('x+', 'Missing operand', 2),
    ('(a+)', 'Missing operand', 3),
    ('f(a,)', 'Empty argument', 4),
    ('[a,]', 'Empty argument', 3),
    ('a)', 'Unbalanced brackets', 1),
    ('a]', 'Unbalanced brackets', 1),
    ('(a', 'Missing )', 2),
    ('f(a', 'Missing )', 3),
    ('*a', 'Missing operand', 0),
    ('a**b', 'Missing operand', 2),
    ('a==b', 'Missing operand', 2),
    (',a', 'Empty argument', 0),
    ('a,', 'Missing operand', 2),
    ('a,,b', 'Empty argument', 2),
    ('!', 'Missing operand', 0),
    ('2+!', 'Missing operand', 2),
    ('-', 'Missing operand', 1),
    ('x y', 'Missing operator', 2),           # no stage 5 on this path
    ('2 3', 'Missing operator', 2),
    ('2(x)', 'Missing operator', 1),
    ('(a)(b)', 'Missing operator', 3),
    ('l[2]', 'Missing operator', 1),           # no indexing in v1
    ('sin x', 'Missing operator', 4),
    ('{1,2}x', 'Missing operator', 5),
    ('f(x)(y)', 'Missing operator', 4),
])
def test_errors(s, msg, pos):
    with pytest.raises(CasError) as e:
        P.rpn(P.lex(s))
    assert e.value.args == (msg, pos)


def test_call_name_without_paren():
    toks = [(P.K_NAME, 'f', 0, 1, P.F_CALL), (P.K_NAME, 'x', 1, 2, 0)]
    with pytest.raises(CasError) as e:
        P.rpn(toks)
    assert e.value.args == ('Missing (', 1)


def test_nesting_cap():
    assert show(P.rpn(P.lex('(' * 32 + 'x' + ')' * 32))) == 'x' + ' ()' * 32
    with pytest.raises(CasError) as e:
        P.rpn(P.lex('(' * 33 + 'x' + ')' * 33))
    assert e.value.args == ('Too deeply nested', 32)
    s = 'sin(' * 32 + 'x' + ')' * 32             # calls count too
    assert P.rpn(P.lex(s))[-1][:3] == ('F', 'sin', 1)
    with pytest.raises(CasError):
        P.rpn(P.lex('sin(' * 33 + 'x' + ')' * 33))


def test_empty_input():
    assert P.rpn([]) == []


# -- properties -----------------------------------------------------------------------------------

ARITY = {'neg': 1, '!': 1, "'": 1}


def check_rpn(items, ntok):
    """The RPN is well formed: no stack underflow, one value at the end, valid indices."""
    depth = 0
    for it in items:
        k = it[0]
        ti = it[-1]
        assert ti == -1 and k == 'L' or 0 <= ti < ntok, it
        if k in 'ns':
            depth += 1
        elif k == 'o':
            need = ARITY.get(it[1], 2)
            assert depth >= need, it
            depth += 1 - need
        elif k == 'F':
            assert depth >= it[2], it
            depth += 1 - it[2]
        elif k == 'L':
            assert depth >= it[1], it
            depth += 1 - it[1]
        else:
            assert k == 'P' and depth >= 1, it
    assert depth == (1 if ntok else 0), items


FRAGS = ('x', 'y', '2', '3.5', 'pi', 'e', 'i', 'sin', 'f', 'd', 'mid', 'ab', '(', ')', '[',
         ']', '{', '}', ',', '+', '-', '*', '/', '^', '!', "'", '=', '!=', '<', '<=', '>',
         '>=', '=>', ':=', ' ', 'E5', "y'", 'sin^2', 'diff(', 'O(', 'xsin', 'f(x)=')


def test_random_lines_give_rpn_or_cas_error():
    r = random.Random(77)
    ok = err = 0
    for _ in range(3000):
        s = ''.join(r.choice(FRAGS) for _ in range(1 + r.randrange(12)))
        for path in (0, 1):
            try:
                toks = P.lex(s)
                if path:
                    toks = P.ti_implicit(P.ti_rewrite(toks))
                items = P.rpn(toks)
            except CasError as e:
                assert isinstance(e.args[0], str) and isinstance(e.args[1], int)
                err += 1
                continue
            check_rpn(items, len(toks))
            ok += 1
    assert ok > 300 and err > 300


def _sec(z):
    return 1 / cmath.cos(z)


FN = {'sin': cmath.sin, 'cos': cmath.cos, 'tan': cmath.tan, 'sec': _sec,
      'csc': lambda z: 1 / cmath.sin(z), 'cot': lambda z: 1 / cmath.tan(z),
      'asin': cmath.asin, 'acos': cmath.acos, 'atan': cmath.atan, 'sinh': cmath.sinh,
      'cosh': cmath.cosh, 'tanh': cmath.tanh, 'ln': cmath.log, 'log': cmath.log10,
      'exp': cmath.exp, 'sqrt': cmath.sqrt, 'abs': abs}
ENV = {'x': 0.7 + 0.0j, 'y': -1.3 + 0.0j, 'pi': complex(cmath.pi), 'e': complex(cmath.e),
       'i': 1j}


def ev_tree(t):
    k = t[0]
    if k == 'num':
        return complex(t[1] / t[2])
    if k == 'flt':
        return complex(float(t[1]))
    if k in ('sym', 'con'):
        return ENV[t[1]]
    # the same operations, in the same order, as the RPN: a 0j or 1+0j seed could turn a -0.0
    # imaginary part into 0.0, and a later fractional power would then take the other branch
    if k == 'add':
        v = ev_tree(t[1][0])
        for c in t[1][1:]:
            v = v + ev_tree(c)
        return v
    if k == 'mul':
        v = ev_tree(t[1][0])
        for c in t[1][1:]:
            v = v * ev_tree(c)
        return v
    if k == 'neg':
        return 0j - ev_tree(t[1])       # as ev_rpn: no -0.0 imaginary parts
    if k == 'sub':
        return ev_tree(t[1]) - ev_tree(t[2])
    if k == 'div':
        return ev_tree(t[1]) / ev_tree(t[2])
    if k == 'pow':
        return ev_tree(t[1]) ** ev_tree(t[2])
    if k == 'fn':
        return FN[t[1]](ev_tree(t[2]))
    raise AssertionError(t)


BIN = {'+': lambda a, b: a + b, '-': lambda a, b: a - b, '*': lambda a, b: a * b,
       '/': lambda a, b: a / b, '^': lambda a, b: a ** b}


def ev_rpn(items):
    st = []
    for it in items:
        k = it[0]
        if k == 'n':
            v = it[1]
            st.append(complex(v[0] / v[1]) if type(v) is tuple else complex(v))
        elif k == 's':
            st.append(ENV[it[1]])
        elif k == 'o' and it[1] == 'neg':
            st[-1] = 0j - st[-1]        # not -z or 0 - z: -(4+0j) has a -0.0 imaginary part,
                                        # and (-4-0j)**1.5 is on the other side of the cut
        elif k == 'o':
            b = st.pop()
            st[-1] = BIN[it[1]](st[-1], b)
        elif k == 'F':
            assert it[2] == 1
            st[-1] = FN[it[1]](st[-1])
        elif k == 'P':
            pass
        else:
            raise AssertionError(it)
    assert len(st) == 1
    return st[0]


def close(a, b):
    if cmath.isnan(a) or cmath.isnan(b) or cmath.isinf(a) or cmath.isinf(b):
        return True
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


@pytest.mark.parametrize('seed', range(4))
def test_rpn_has_the_value_of_the_expression(seed):
    """gen.text writes explicit '*' and parenthesized compound operands; the RPN of that text
    (stages 3 and 7, and the user path) evaluates to the tree's value."""
    g = gen.Gen(seed, floats=True, consts=('pi', 'e', 'i'))
    n = 0
    for _ in range(300):
        t = g.tree(4)
        s = gen.text(t)
        try:
            want = ev_tree(t)
        except (ZeroDivisionError, OverflowError, ValueError):
            continue
        for items in (P.rpn(P.lex(s)), P.rpn(P.ti_implicit(P.ti_rewrite(P.lex(s))))):
            try:
                got = ev_rpn(items)
            except (ZeroDivisionError, OverflowError, ValueError):
                continue
            assert close(got, want), (s, show(items), got, want)
            n += 1
    assert n > 300
