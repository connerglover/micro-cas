"""Token passes (DESIGN 7.1-7.5, 7.10): lex, ti_rewrite, ti_implicit, classify, untok.

The FlowCE port lives in tests/golden/tiinput.txt (every case of FlowCE's
tests/host/test_tiinput.cc, plus the cas-evo cases); its properties are checked here on the
golden cases and on seeded random lines, as FlowCE does.
"""
import os
import random
import re
import types

import pytest

import parse as P

CasError = P.K.CasError
HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, 'golden', 'tiinput.txt')
PI = 'π'
THETA = 'θ'

# -- classifier set-ups -------------------------------------------------------------------------

# FlowCE tests/host/test_tiinput.cc fake_classify
FLOWCE_FUN = ('sin cos tan asin acos atan sqrt exp ln log log10 abs simplify factor expand '
              'normal integrate int diff solve limit sum seq subst ans evalf approx tlin '
              'trigcos ratnormal iegcd smod resultant max min sec csc cot sinh cosh tanh asec '
              'acsc acot asinh acosh atanh').split()
FLOWCE_UFN = ['myf']
FLOWCE_VAL = 'pi e i infinity inf oo undef area v1'.split()
FLOWCE_KEY = ('if then else elif end for from to step do while repeat until return local and '
              'or not xor mod in of div od fi break continue').split()

# DESIGN 15.1
CMDS = dict.fromkeys('simplify expand factor together approx solve diff integrate limit taylor '
                     'partfrac sum riemann desolve grad'.split(), 1)
ALIAS = dict.fromkeys('int d deriv lim series ratnormal dsolve gradient evalf'.split(), 1)
MACROS = dict.fromkeys('polararea paramarea arclen'.split(), 1)


def session(vars=(), funcs=()):
    """A stand-in for the run module, as the classify hook sees it."""
    return types.SimpleNamespace(VARS=dict.fromkeys(vars, 'text'),
                                 FUNCS=dict.fromkeys(funcs, (('x',), 'x')),
                                 CMDS=CMDS, ALIAS=ALIAS, MACROS=MACROS)


def use_flowce(mp):
    mp.setattr(P, 'FNAMES', set(FLOWCE_FUN))
    mp.setattr(P, 'VNAMES', set(FLOWCE_VAL))
    mp.setattr(P, 'KWORDS', set(FLOWCE_KEY))
    mp.setattr(P, 'SESS', types.SimpleNamespace(VARS={}, FUNCS=dict.fromkeys(FLOWCE_UFN, 1),
                                                CMDS={}, ALIAS={}, MACROS={}))


REAL = (P.FNAMES, P.VNAMES, P.KWORDS)


def use_casevo(mp, vars=(), funcs=()):
    mp.setattr(P, 'FNAMES', REAL[0])
    mp.setattr(P, 'VNAMES', REAL[1])
    mp.setattr(P, 'KWORDS', REAL[2])
    mp.setattr(P, 'SESS', session(vars, funcs))


@pytest.fixture
def casevo(monkeypatch):
    use_casevo(monkeypatch)
    return monkeypatch


# -- helpers ------------------------------------------------------------------------------------

def user(s):
    """Stages 3-5, as text."""
    return P.untok(P.ti_implicit(P.ti_rewrite(P.lex(s))), s)


def kv(toks):
    return [(t[0], t[1]) for t in toks]


def stars_only(a, b):
    """b is a plus some '*' characters (FlowCE only_stars_added)."""
    i = 0
    for ch in b:
        if i < len(a) and ch == a[i]:
            i += 1
        elif ch != '*':
            return False
    return i == len(a)


def tok_text(toks, s):
    """The tokens' texts run together (numbers as typed, names by value)."""
    out = []
    for u in toks:
        out.append(s[u[2]:u[3]] if u[0] == P.K_NUM else u[1])
    return ''.join(out)


def only_stars_added(t_in, t_out, s):
    """Stage 5 inserted nothing but '*': on the token texts, and on the text with its blanks
    when there is no pi or theta glyph (untok writes those as names)."""
    if not stars_only(tok_text(t_in, s), tok_text(t_out, s)):
        return False
    if PI in s or THETA in s:
        return True
    return stars_only(P.untok(t_in, s), P.untok(t_out, s))


def run_mode(mode, s):
    try:
        t = P.lex(s)
        if mode == 'R':
            out = P.ti_rewrite(t)
        elif mode == 'I':
            out = P.ti_implicit(t)
        elif mode == 'i':
            out = P.ti_implicit(t, 0)
        elif mode == 'P':
            out = P.ti_implicit(P.ti_rewrite(t))
        else:
            raise ValueError('mode %r' % mode)
    except CasError as e:
        return '!' + e.args[0], None, None
    return P.untok(out, s), t, out


# -- the golden file ----------------------------------------------------------------------------

_ESC = {'\\': '\\', '|': '|', 't': '\t', 'n': '\n', 'r': '\r'}


def unesc(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\':
            d = s[i + 1]
            if d == 'u':
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(_ESC[d])
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def esc(s):
    out = []
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '|':
            out.append('\\|')
        elif ch == '\t':
            out.append('\\t')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ord(ch) > 126:
            out.append('\\u%04x' % ord(ch))
        else:
            out.append(ch)
    return ''.join(out)


def split_fields(line):
    out = []
    cur = []
    i = 0
    while i < len(line):
        c = line[i]
        if c == '\\':
            cur.append(line[i:i + 2])
            i += 2
            continue
        if c == '|':
            out.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append(''.join(cur))
    return out


def golden_cases():
    """[(lineno, line, directive, mode, input, expected)] in file order (other lines: None)."""
    rows = []
    directive = None
    with open(GOLDEN, encoding='ascii') as fh:
        for no, line in enumerate(fh.read().split('\n'), 1):
            if line.startswith('@'):
                directive = line
                rows.append((no, line, directive, None, None, None))
            elif not line.strip() or line.startswith('#'):
                rows.append((no, line, directive, None, None, None))
            else:
                f = split_fields(line)
                assert len(f) == 3 and f[0] in ('R', 'I', 'i', 'P'), 'bad golden line %d' % no
                rows.append((no, line, directive, f[0], unesc(f[1]), unesc(f[2])))
    return rows


def apply_directive(mp, directive):
    parts = directive[1:].split()
    if parts[0] == 'flowce':
        use_flowce(mp)
        return
    assert parts[0] == 'casevo', directive
    vs = ()
    fs = ()
    for p in parts[1:]:
        k, _, v = p.partition('=')
        if k == 'vars':
            vs = v.split(',')
        elif k == 'funcs':
            fs = v.split(',')
        else:
            raise AssertionError('bad directive %r' % directive)
    use_casevo(mp, vs, fs)


def test_golden_tiinput(monkeypatch, update_golden):
    rows = golden_cases()
    bad = []
    out_lines = []
    ncases = 0
    for no, line, directive, mode, s, want in rows:
        if line.startswith('@'):
            apply_directive(monkeypatch, directive)
        if mode is None:
            out_lines.append(line)
            continue
        ncases += 1
        got, toks, out = run_mode(mode, s)
        out_lines.append('%s|%s|%s' % (mode, esc(s), esc(got)))
        why = ''
        if got != want:
            why = 'expected %r' % want
        elif out is not None:
            # FlowCE checks two properties on every case: the pass is idempotent, and
            # ti_implicit_mult only inserts '*'
            if mode == 'R' and P.ti_rewrite(out) != out:
                why = 'ti_rewrite is not idempotent'
            elif mode in 'Ii':
                if P.ti_implicit(out, 1 if mode == 'I' else 0) != out:
                    why = 'ti_implicit is not idempotent'
                elif not only_stars_added(toks, out, s):
                    why = 'ti_implicit changed more than inserting *'
            elif mode == 'P' and P.ti_implicit(P.ti_rewrite(out)) != out:
                why = 'stages 4-5 twice differ from once'
        if why:
            bad.append('line %d: %s %r -> %r: %s' % (no, mode, s, got, why))
    assert ncases >= 266 + 150              # FlowCE's 67 + 199 cases, plus the cas-evo ones
    if update_golden:
        with open(GOLDEN, 'w', encoding='ascii', newline='\n') as fh:
            fh.write('\n'.join(out_lines))
        return
    assert not bad, '\n'.join(bad[:40])


def test_golden_has_every_flowce_case():
    """The FlowCE section keeps all 266 cases of test_tiinput.cc (67 rcases, 199 cases)."""
    rows = golden_cases()
    n = {'R': 0, 'I': 0, 'i': 0}
    for no, line, directive, mode, s, want in rows:
        if directive == '@ flowce' and mode is not None:
            n[mode] += 1
    assert n == {'R': 67, 'I': 190, 'i': 9}


# -- lex (stage 3) --------------------------------------------------------------------------------

def test_lex_kinds_and_offsets(casevo):
    t = P.lex('2x^2 + sin(y) != [a,b]=>c')
    assert t == [
        (P.K_NUM, (2, 1), 0, 1, 0), (P.K_NAME, 'x', 1, 2, 0), (P.K_OP, '^', 2, 3, 0),
        (P.K_NUM, (2, 1), 3, 4, 0), (P.K_OP, '+', 5, 6, 0),
        (P.K_NAME, 'sin', 7, 10, P.F_CALL), (P.K_LP, '(', 10, 11, 0),
        (P.K_NAME, 'y', 11, 12, 0), (P.K_RP, ')', 12, 13, 0), (P.K_OP, '!=', 14, 16, 0),
        (P.K_LB, '[', 17, 18, 0), (P.K_NAME, 'a', 18, 19, 0), (P.K_COMMA, ',', 19, 20, 0),
        (P.K_NAME, 'b', 20, 21, 0), (P.K_RB, ']', 21, 22, 0), (P.K_OP, '=>', 22, 24, 0),
        (P.K_NAME, 'c', 24, 25, 0)]


@pytest.mark.parametrize('s, kinds_values', [
    ('n!=1', [(1, 'n'), (2, '!='), (0, (1, 1))]),                  # != is one token (7.2)
    ('(n!)=1', [(3, '('), (1, 'n'), (8, '!'), (4, ')'), (2, '='), (0, (1, 1))]),
    ("y''+y'", [(1, "y''"), (2, '+'), (1, "y'")]),
    ("f'(x)", [(1, 'f'), (8, "'"), (3, '('), (1, 'x'), (4, ')')]),
    ("xy'", [(1, 'xy'), (8, "'")]),                                 # primes fold after y only
    ('a:=b', [(1, 'a'), (2, ':='), (1, 'b')]),
    ('a<=b>=c<d>e=f', [(1, 'a'), (2, '<='), (1, 'b'), (2, '>='), (1, 'c'), (2, '<'),
                       (1, 'd'), (2, '>'), (1, 'e'), (2, '='), (1, 'f')]),
    ('{1}', [(5, '{'), (0, (1, 1)), (6, '}')]),
    ('x->y', [(1, 'x'), (2, '-'), (2, '>'), (1, 'y')]),
    ('a==b', [(1, 'a'), (2, '='), (2, '='), (1, 'b')]),
    (PI + 'r' + THETA, [(1, 'pi'), (1, 'r'), (1, 'theta')]),
    ('007', [(0, (7, 1))]),
    ('', []),
    (' \t ', []),
])
def test_lex_tokens(casevo, s, kinds_values):
    assert kv(P.lex(s)) == kinds_values


@pytest.mark.parametrize('s, value', [
    ('12', (12, 1)), ('2.5', 2.5), ('3.', 3.0), ('.5', 0.5), ('2E10', 2e10), ('2E-3', 0.002),
    ('2E+3', 2000.0), ('3.E2', 300.0), ('.5E-1', 0.05), ('1E400', None),
    ('123456789012345678901234567890', (123456789012345678901234567890, 1)),
])
def test_lex_numbers(casevo, s, value):
    """Integers are exact; a '.' or an exponent makes a float (D8); only E starts an exponent
    (D14); inf is refused."""
    if value is None:
        with pytest.raises(CasError) as e:
            P.lex(s)
        assert e.value.args == ('number too large', 0)
        return
    t = P.lex(s)
    assert len(t) == 1 and t[0][0] == P.K_NUM and t[0][1] == value
    assert type(t[0][1]) is type(value)


@pytest.mark.parametrize('s, kinds_values', [
    ('2e', [(0, (2, 1)), (1, 'e')]),
    ('2e-1', [(0, (2, 1)), (1, 'e'), (2, '-'), (0, (1, 1))]),        # D14
    ('2E', [(0, (2, 1)), (1, 'E')]),
    ('2Ex', [(0, (2, 1)), (1, 'Ex')]),
    ('2E-', [(0, (2, 1)), (1, 'E'), (2, '-')]),
    ('1e5', [(0, (1, 1)), (1, 'e5')]),
    ('1.2.3', [(0, 1.2), (0, 0.3)]),
    ('1..5', [(0, 1.0), (0, 0.5)]),
    ('x.5', [(1, 'x'), (0, 0.5)]),
])
def test_lex_number_edges(casevo, s, kinds_values):
    assert kv(P.lex(s)) == kinds_values


@pytest.mark.parametrize('s, pos', [
    ('x_1', 1), ('_t', 0), ('a;b', 1), ('"x"', 0), ('x:y', 1), ('x$', 1), ('2x\n', 2),
    ('a\rb', 1), ('é', 0), ('x' + chr(0x2264) + 'y', 1), ('1 .', 2), ('a..', 1),
])
def test_lex_invalid_character(casevo, s, pos):
    """Underscore names are reserved (7.2); no strings, comments or statements."""
    with pytest.raises(CasError) as e:
        P.lex(s)
    assert e.value.args == ('invalid character', pos)


@pytest.mark.parametrize('s, calls', [
    ('sin(x)', ['sin']),
    ('sin (x)', ['sin']),                       # blanks do not matter (FlowCE skips them)
    ('f(x)+g(y)+h(z)', ['f', 'g', 'h']),
    ('x(y)', []),
    ('F(x)', []),
    ('e(x)', []),
    ('foo(x)', ['foo']),                        # an unknown name of 2+ letters before '('
    ('diff(x^2,x)', ['diff']),
    ('int(x,x)', ['int']),
    ('O(x^6)', ['O']),
    ('purge(x)', ['purge']),
    ('polararea(r,t,0,1)', ['polararea']),
    ('d(x^2,x)', ['d']),                        # D9: d with a top-level comma
    ('d(x+1)', []),
    ('d([x,y])', []),
    ('d((x,y))', []),
    ('d(f(x,y),x)', ['d', 'f']),
    ("y(0)+y'(0)", []),                        # y is a call letter only with desolve
    ("desolve([y'=y,y(0)=1,y'(0)=2,u(1)=0],y)", ['desolve', 'y', "y'", 'u']),
    ("dsolve(y''(0)=1)", ['dsolve', "y''"]),
    ('sin', []),
    ('sin x', []),
    ('mid(x)', []),                             # a VALUE before '(' is not a call
    ('true(x)', []),
])
def test_lex_sets_f_call(casevo, s, calls):
    t = P.lex(s)
    got = [x[1] for x in t if x[4] & P.F_CALL]
    assert got == calls
    for k in range(len(t)):
        if t[k][4] & P.F_CALL:
            assert t[k + 1][0] == P.K_LP


def test_lex_f_call_with_session(monkeypatch):
    use_casevo(monkeypatch, vars=('d', 'k', 'f'), funcs=('q',))
    t = P.lex('d(x^2,x)+k(2)+f(3)+q(1)+myf(2)')
    assert [x[1] for x in t if x[4] & P.F_CALL] == ['q', 'myf']


# -- classify -----------------------------------------------------------------------------------

def test_classify_real_tables(monkeypatch):
    use_casevo(monkeypatch, vars=('a', 'd'), funcs=('g', 'area'))
    C = P.classify
    for n in ('sin', 'asec', 'log10', 'surd', 'O', 'purge', 'diff', 'int', 'lim',
              'polararea', 'riemann', 'deriv', 'evalf'):
        assert C(n) == P.C_FN, n
    for n in ('pi', 'e', 'i', 'oo', 'inf', 'infinity', 'undef', 'theta', 'true', 'false',
              'left', 'right', 'mid', 'trap', 'a', 'd'):
        assert C(n) == P.C_VAL, n
    assert C('g') == P.C_UFN and C('area') == P.C_UFN
    for n in ('x', 'foo', 'E', 'pir', 'Sin', 'y', "y'"):
        assert C(n) == P.C_UNK, n


def test_classify_d_is_never_function(monkeypatch):
    """D9: the alias d is a call only through the comma rule (iscall), never by class."""
    use_casevo(monkeypatch)
    assert P.classify('d') == P.C_UNK
    assert P.classify('deriv') == P.C_FN


def test_classify_without_session(monkeypatch):
    use_casevo(monkeypatch)
    monkeypatch.setattr(P, 'SESS', None)
    assert P.classify('sin') == P.C_FN
    assert P.classify('pi') == P.C_VAL
    assert P.classify('diff') == P.C_UNK
    assert user('diff(x^2,x)') == 'diff(x^2,x)'     # still a call: an uncut unknown name


def test_classify_reads_the_session_at_call_time(monkeypatch):
    sess = session()
    use_casevo(monkeypatch)
    monkeypatch.setattr(P, 'SESS', sess)
    assert user('2ab') == '2*a*b'
    sess.VARS['ab'] = '3'
    assert user('2ab') == '2*ab'
    del sess.VARS['ab']
    sess.FUNCS['ab'] = (('x',), 'x')
    assert user('ab(2)') == 'ab(2)'


def test_keyword_hook(monkeypatch):
    use_casevo(monkeypatch)
    monkeypatch.setattr(P, 'KWORDS', {'mod'})
    assert user('2x mod 3') == '2*x mod 3'
    monkeypatch.setattr(P, 'KWORDS', set())
    assert user('2x mod 3') == '2*x* m*o*d* 3'


# -- ti_rewrite and ti_implicit: tokens and flags ----------------------------------------------

def test_implicit_marks_inserted_stars(casevo):
    s = '2x(x+1)y'
    out = P.ti_implicit(P.lex(s))
    stars = [t for t in out if t[4] & P.F_IMPL]
    assert len(stars) == 3
    for t in stars:
        assert t[:2] == (P.K_OP, '*') and t[2] == t[3]
    assert [t[2] for t in stars] == [1, 2, 7]       # right after the previous token
    assert P.untok(out, s) == '2*x*(x+1)*y'


def test_implicit_cut_offsets_and_flags(casevo):
    s = '2pir(x)+xsin(x)'
    out = P.ti_implicit(P.lex(s))
    names = [(t[1], t[2], t[3], t[4]) for t in out if t[0] == P.K_NAME]
    assert names == [('pi', 1, 3, 0), ('r', 3, 4, 0), ('x', 5, 6, 0), ('x', 8, 9, 0),
                     ('sin', 9, 12, P.F_CALL), ('x', 13, 14, 0)]


def test_implicit_sets_and_clears_f_call(casevo):
    s = 'ab(x)+foo(x)'
    t = P.lex(s)
    assert [x[1] for x in t if x[4] & P.F_CALL] == ['ab', 'foo']
    out = P.ti_implicit(t)
    assert [x[1] for x in out if x[4] & P.F_CALL] == ['foo']
    assert P.untok(out, s) == 'a*b*(x)+foo(x)'


def test_rewrite_flags(casevo):
    s = 'sinx+sin^2x+sin^-1(x)+sin x+xsin(y)'
    out = P.ti_rewrite(P.lex(s))
    assert P.untok(out, s) == 'sin(x)+sin(x)^2+asin(x)+sin(x)+x*sin(y)'
    assert [x[1] for x in out if x[4] & P.F_CALL] == ['sin', 'sin', 'asin', 'sin', 'sin']
    assert [x[1] for x in out if x[4] & P.F_IMPL] == ['*']
    for k in range(len(out)):
        if out[k][4] & P.F_CALL:
            assert out[k + 1][0] == P.K_LP


def test_rewrite_definition_token(casevo):
    s = 'f(x) = x^2'
    out = P.ti_rewrite(P.lex(s))
    assert (P.K_OP, ':=', 5, 6, 0) in out
    assert out[0] == (P.K_NAME, 'f', 0, 1, P.F_CALL)
    t = P.ti_rewrite(P.lex('a(x)=1'))               # a is no call letter: the def makes it one
    assert t[0][4] == P.F_CALL and P.ti_implicit(t)[0][4] == P.F_CALL
    assert user('a(x)=2x') == 'a(x):=2*x'


def test_rewrite_keeps_the_typed_number_text(casevo):
    s = 'sin2E5x+sin 0.50x'
    assert P.untok(P.ti_rewrite(P.lex(s)), s) == 'sin(2E5x)+sin(0.50x)'
    assert user(s) == 'sin(2E5*x)+sin(0.50*x)'
    t = P.ti_rewrite(P.lex('sin2E5x'))
    assert kv(t)[2:4] == [(P.K_NUM, 2e5), (P.K_NAME, 'x')]


def test_rewrite_number_too_large_inside_a_name(casevo):
    with pytest.raises(CasError) as e:
        P.ti_rewrite(P.lex('xsin1E999'))
    assert e.value.args == ('number too large', 4)


def test_implicit_without_cut(casevo):
    s = '2pir+xy(x)+abc'
    assert P.untok(P.ti_implicit(P.lex(s), 0), s) == '2*pir+xy(x)+abc'


def test_passes_do_not_change_their_input(casevo):
    t = P.lex('sin^2xcosx+2pir+f(x)=3')
    keep = list(t)
    P.ti_rewrite(t)
    P.ti_implicit(t)
    assert t == keep


# -- the review cases (DESIGN 7.10, 20.12 lexer row) ---------------------------------------------

def test_review_e_is_the_constant(casevo):
    assert user('2e-1') == '2*e-1'
    assert user('3e-2x') == '3*e-2*x'
    t = P.lex('2E-1')
    assert len(t) == 1 and t[0][1] == 0.2


def test_review_riemann_mid(casevo):
    assert user('riemann(x^2,x,0,1,4,mid)') == 'riemann(x^2,x,0,1,4,mid)'


def test_review_desolve_conditions(casevo):
    s = "desolve([y''+y=0,y(0)=1,y'(0)=0],y)"
    out = P.ti_implicit(P.ti_rewrite(P.lex(s)))
    assert P.untok(out, s) == s
    assert [t[1] for t in out if t[4] & P.F_CALL] == ['desolve', 'y', "y'"]


def test_review_big_o_after_implicit(casevo):
    out = P.ti_implicit(P.lex('O(x^6)'))
    assert out[0] == (P.K_NAME, 'O', 0, 1, P.F_CALL) and len(out) == 6


def test_review_sin_through_lex_and_rpn_alone(casevo):
    assert P.rpn(P.lex('sin(x)')) == [('s', 'x', 2), ('F', 'sin', 1, 3)]


# -- untok ----------------------------------------------------------------------------------------

@pytest.mark.parametrize('s', ['x y', '  2 x ', 'sin( x )\t+1', '1.2.3', '2 3', 'a = = b',
                               '2E5', '3.', '007x', "y''", '[1,2]', ''])
def test_untok_restores_the_source(casevo, s):
    assert P.untok(P.lex(s), s) == s


@pytest.mark.parametrize('toks, text', [
    ([(P.K_NAME, 'x', 0, 0, 0), (P.K_NAME, 'y', 0, 0, 0)], 'x y'),
    ([(P.K_NUM, (2, 1), 0, 0, 0), (P.K_NUM, (3, 1), 0, 0, 0)], '2 3'),
    ([(P.K_NUM, (2, 1), 0, 0, 0), (P.K_NUM, 0.5, 0, 0, 0)], '2 0.5'),
    ([(P.K_NUM, (2, 1), 0, 0, 0), (P.K_NAME, 'x', 0, 0, 0)], '2x'),
    ([(P.K_NUM, (2, 1), 0, 0, 0), (P.K_NAME, 'E5', 0, 0, 0)], '2 E5'),
    ([(P.K_NAME, 'x', 0, 0, 0), (P.K_NUM, (2, 1), 0, 0, 0)], 'x 2'),
    ([(P.K_POST, '!', 0, 0, 0), (P.K_OP, '=', 0, 0, 0)], '! ='),
    ([(P.K_OP, '=', 0, 0, 0), (P.K_OP, '>', 0, 0, 0)], '= >'),
    ([(P.K_OP, '<', 0, 0, 0), (P.K_OP, '=', 0, 0, 0)], '< ='),
    ([(P.K_OP, '=', 0, 0, 0), (P.K_OP, '=', 0, 0, 0)], '=='),
    ([(P.K_NUM, 1e20, 0, 0, 0)], '1E+20'),
    ([(P.K_NUM, (3, 4), 0, 0, 0)], '3/4'),
])
def test_untok_without_source_keeps_tokens_apart(toks, text):
    assert P.untok(toks) == text
    if text not in ('3/4',):
        assert kv(P.lex(text)) == kv(toks)


# -- properties on random lines (FlowCE test_tiinput.cc, random section) --------------------------

FRAGS = ('x', 'y', 'ab', 'pir', 'pi', 'e', 'i', 'f', 'g', 'h', 'sin', 'cos(', 'myf', 'area',
         'v1', 'oo', 'inf', 'xsin', '2', '3.5', '.5', '1E5', '2e', '0', '(', ')', '[', ']', '{',
         '}', ',', '+', '-', '*', '/', '^', '!', "'", ':=', '=>', '==', '!=', '<=', '>=', '**',
         '=', '<', '>', ' ', '  ', '\t', 'mod', 'if', 'then', 'and', 'in', THETA, PI,
         # cas-evo additions
         'E', '2E-3', "y'", "y''", 'desolve(', 'dsolve', 'd(', 'mid', 'sin^', '^-1', 'sinx',
         'ln', 'lnx', 'sqrt', '^2', '2x', 'cosx', 'sec', 'asin(', 'log10', 'O(', 'f(x)=',
         'g(x,y)=', 'u', 'abc', 'xy', 't', 'diff(', 'int', 'E5', '123', 'sinh', 'xcos')
NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*'*\Z")


class FakeClassify(object):
    """FlowCE fake_classify, also counting calls on anything that is not a name."""

    def __init__(self):
        self.bad = []
        self.calls = 0

    def __call__(self, name):
        self.calls += 1
        if not isinstance(name, str) or not NAME_RE.match(name):
            self.bad.append(name)
            return P.C_UNK
        if name in FLOWCE_KEY:
            return P.C_KEY
        if name in FLOWCE_FUN or name == 'desolve' or name == 'dsolve':
            return P.C_FN
        if name in FLOWCE_UFN:
            return P.C_UFN
        if name in FLOWCE_VAL or name == 'theta':
            return P.C_VAL
        return P.C_UNK


def random_lines(seed, n):
    r = random.Random(seed)
    for _ in range(n):
        yield ''.join(r.choice(FRAGS) for _ in range(1 + r.randrange(14)))


def check_line(s):
    """FlowCE's properties of stages 4 and 5 on one line; returns a failure text or ''."""
    try:
        t = P.lex(s)
    except CasError:
        return ''
    base = P.untok(t, s)
    if PI not in s and THETA not in s and base != s:
        return 'untok(lex(s), s) != s: %r' % base
    for cut in (1, 0):
        out = P.ti_implicit(t, cut)
        if not only_stars_added(t, out, s):
            return 'cut=%d: ti_implicit changed more than inserting *: %r' % (
                cut, P.untok(out, s))
        if P.ti_implicit(out, cut) != out:
            return 'cut=%d: ti_implicit is not idempotent' % cut
        for u in out:
            if u[4] & P.F_IMPL and u[:2] != (P.K_OP, '*'):
                return 'F_IMPL on %r' % (u,)
            if u[0] == P.K_OP and u[1] == '*' and u not in t and not u[4] & P.F_IMPL:
                return 'an inserted * without F_IMPL'
    try:
        r = P.ti_rewrite(t)
    except CasError:
        return ''
    if P.ti_rewrite(r) != r:
        return 'ti_rewrite is not idempotent: %r' % P.untok(r, s)
    once = P.ti_implicit(r)
    if P.ti_implicit(P.ti_rewrite(once)) != once:
        return 'stages 4-5 twice differ from once: %r' % P.untok(once, s)
    for k in range(len(once)):
        if once[k][4] & P.F_CALL and (k + 1 == len(once) or once[k + 1][0] != P.K_LP):
            return 'F_CALL not before (: %r' % (once[k],)
    text = P.untok(once, s)                  # re-lexing the text gives the same tokens
    if kv(P.lex(text)) != kv(once):
        return 'untok(..., s) does not re-lex: %r' % text
    bare = P.untok(once)
    if kv(P.lex(bare)) != kv(once):
        return 'untok(...) does not re-lex: %r' % bare
    return ''


def run_random(monkeypatch, seed, n):
    fake = FakeClassify()
    monkeypatch.setattr(P, 'classify', fake)
    fails = []
    for s in random_lines(seed, n):
        why = check_line(s)
        if why:
            fails.append('%r: %s' % (s, why))
    assert not fake.bad, 'classify called on non-names: %r' % fake.bad[:10]
    assert fake.calls > n
    assert not fails, '\n'.join(fails[:20])


def test_random_lines(monkeypatch):
    run_random(monkeypatch, 20261005, 2000)


@pytest.mark.slow
def test_random_lines_flowce_count(monkeypatch):
    """FlowCE's own count: 20,000 random lines."""
    run_random(monkeypatch, 7, 20000)


def test_classify_called_only_on_names_in_golden_cases(monkeypatch):
    fake = FakeClassify()
    monkeypatch.setattr(P, 'classify', fake)
    for no, line, directive, mode, s, want in golden_cases():
        if mode is not None:
            run_mode(mode, s)
    assert fake.calls > 1000
    assert not fake.bad, fake.bad[:10]
