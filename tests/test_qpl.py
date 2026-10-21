"""The QPL changes Q3-Q5 (docs/notes/MATHPRINT.md 3.3, 3.4, 7.5): Nspire-style command names in
the menus, the catalog, the template picker and help; an empty box for each empty argument of a
plain call in the MathPrint entry line; and the hint row's explanation of the argument (slot)
the caret is in, with whether it is required."""
import pytest

import draw as D
import keyscript as KS
import ti_draw as TD
import ti_system as TS
import ui as U

SECOND, DEL, LEFT, UP, RIGHT, DOWN = 21, 23, 24, 25, 26, 34
COMMA, ENTER, CLEAR = 62, 105, 45

STATE = (('LINE', ''), ('CUR', 0), ('XOFF', 0), ('MOD', 0), ('MODE', 0), ('SEL', -1),
         ('HERO', True), ('DX', 0), ('ENTRYPOS', -1), ('LASTENTRY', ''), ('STATUS', ''),
         ('NOTE', ''), ('FULL', True), ('VIEW', None), ('EXOFF', 0), ('EH', 20),
         ('EDMAP', None), ('EMODEL', None), ('EFLAT', True), ('PENDING', None),
         ('ED1D', False), ('EFAIL', None), ('CLASSIC', False), ('VIEWEND', -1),
         ('EDL', None), ('EKEY', None), ('STATVIEW', None), ('HINTVIEW', None),
         ('EDIFF', True), ('CARETC', 'INK'), ('PAGEMAX', 5), ('HKEY', None), ('HTEXT', ''))


@pytest.fixture(autouse=True)
def editor(monkeypatch):
    """A fresh engine-free editor (every name must exist: raising=True)."""
    monkeypatch.setattr(D, 'P', None)
    monkeypatch.setattr(D, 'PR', None)
    monkeypatch.setattr(U, 'R', None)
    for name, value in STATE:
        monkeypatch.setattr(U, name, value)
    TD.reset()
    D.reset()
    D.clear_cache()
    D.theme(0)


def setline(before):
    i = before.index('|')
    U.LINE = before[:i] + before[i + 1:]
    U.CUR = i
    U.EMODEL = None
    U.emodel()


def shown():
    return U.LINE[:U.CUR] + '|' + U.LINE[U.CUR:]


def hint():
    """The hint row's text for the caret (what redraw shows), engine-free."""
    k = U.argpos()
    return U.arghelp(k[0], k[1], k[2]) if k is not None else ''


@pytest.fixture
def engine(monkeypatch):
    import cascheck as C
    import parse as P
    import run as R
    C.fresh()
    monkeypatch.setattr(U, 'R', R)
    monkeypatch.setattr(U, 'P', P)
    R.need('menu')
    return R


# -- Q3: names -----------------------------------------------------------------------------------

NAMES = {'simplify(': 'Simplify', 'expand(': 'Expand', 'factor(': 'Factor', 'solve(': 'Solve',
         'together(': 'Common Denominator', 'partfrac(': 'Partial Fractions',
         'diff(': 'Derivative', 'integrate(': 'Integral', 'limit(': 'Limit',
         'taylor(': 'Taylor Polynomial', 'sum(': 'Sum', 'riemann(': 'Riemann Sum',
         'desolve(': 'Differential Equation Solver', 'grad(': 'Gradient',
         'polararea(': 'Polar Area', 'paramarea(': 'Parametric Area', 'arclen(': 'Arc Length',
         'approx(': 'Convert to Decimal', 'purge(': 'Delete Variable', 'sin(': 'sin',
         'asin(': 'sin^-1', 'atanh(': 'tanh^-1', 'ln(': 'ln', 'log(': 'Logarithm', 'exp(': 'e^x',
         'sqrt(': 'Square Root', 'surd(': 'Nth Root', 'abs(': 'Absolute Value', 'sign(': 'Sign',
         'floor(': 'Floor', 'ceil(': 'Ceiling', 'pi': 'pi', 'oo': 'oo (infinity)'}


def test_catalog_rows_show_nspire_names_and_insert_the_same_text(engine):
    cat = engine.need('cat').CAT
    by = dict((row[1], row) for row in cat)
    for prefix, name in NAMES.items():
        assert by[prefix][0] == name, prefix
    for row in cat:
        assert len(row) == 5 and all(row) and len(row[0]) <= 28, row
        assert all(32 <= ord(c) < 127 for c in row[0]), row
        assert row[1] in ('pi', 'e', 'i', 'oo') or row[1].endswith('('), row
    # every command and macro has a row, found by its insertion text
    names = set(row[1].rstrip('(') for row in cat)
    assert set(engine.CMDS) | set(engine.MACROS) <= names


def menu(kind, keys, command=''):
    import run as R
    TS.load(keys)
    return R.need('menu').open(kind, '', 0, command)


def test_menus_list_the_names(engine):
    menu('algebra', [45])
    screen = TD.screen_text()
    assert '>1 Simplify' in screen and '4 Solve' in screen and 'simplify(' not in screen
    menu('calculus', [45])
    assert '>1 Derivative' in TD.screen_text() and '2 Integral' in TD.screen_text()
    assert menu('calculus', [105])[0] == 'diff(,)'          # the inserted text is unchanged


def test_find_matches_the_name_or_the_command_and_all_is_sorted_by_name(engine):
    mb = engine.MODS['menub']
    cat = engine.need('cat').CAT
    assert [r[0] for r in mb.entries(cat, 4, 'deri')] == ['Derivative']
    assert [r[0] for r in mb.entries(cat, 4, 'diff')] == ['Differential Equation Solver',
                                                           'Derivative']
    assert [r[0] for r in mb.entries(cat, 4, 'toge')] == ['Common Denominator']
    # name matches first, then command-only matches: su is Sum, then surd's Nth Root
    assert [r[0] for r in mb.entries(cat, 4, 'su')] == ['Sum', 'Nth Root']
    rows = [r[0] for r in mb.entries(cat, 4, '')]
    assert rows == sorted(rows, key=str.lower) and len(rows) == len(cat)
    assert menu('all', [31, 31, 51, 52, 75, 105])[0] == 'diff(,)'    # find "der": by name


def test_help_shows_the_name_explanation_and_example(engine):
    TS.load([45])
    engine.need('menu').open('help', '', 0, 'diff')
    screen = TD.screen_text()
    assert 'Derivative' in screen and 'diff(x^3,x,2)' in screen and 'Differentiate' in screen
    assert menu('help', [105], 'diff')[0] == 'diff(x^3,x,2)'
    assert menu('help', [105], 'd')[0] == 'diff(x^3,x,2)'                # the alias
    assert menu('help', [105], 'pi')[0] == 'pi'


def test_template_picker_uses_the_nspire_template_names():
    assert [U.tmpl(j)[0] for j in range(U.TN)] == [
        'Fraction', 'Exponent', 'Square root', 'Nth root', 'e exponent', '10 exponent',
        'Log base b', 'Absolute value', 'Integral', 'First derivative', 'Nth derivative',
        'Sum', 'Limit']
    assert [U.tmpl(j)[1] for j in range(U.TN)] == [
        '', '', 'sqrt()', 'surd(,)', 'e^()', '10^()', 'log(,)', 'abs()', 'integrate(,,,)',
        'diff(,)', 'diff(,,)', 'sum(,,,)', 'limit(,,,)']
    s = KS.run('{2nd,frac}{snap:p}')
    assert '>1 Fraction' in s.snap('p') and '7 Log base b' in s.snap('p')


# -- Q4: boxes for plain-call arguments ----------------------------------------------------------

@pytest.mark.parametrize('line, flat', [
    ('solve(,)', False), ('sin()', False), ('riemann(,,,,,)', False), ('f(a,,b)', False),
    ('simplify()', False), ('solve(x=1,)', False), ('(,1)', False),
    ('2*()', False), ('solve(x=1,x)', True), ('sin(x)', True), ('x+1', True), ('2*(x)', True)])
def test_a_line_with_an_empty_argument_is_2d(line, flat):
    assert D.mflat(line) is flat


def test_plain_call_boxes_are_slots_the_caret_visits():
    setline('solve(|,)')
    M = U.EDMAP
    assert M is not None and not U.EFLAT
    assert [e[0] for e in M[12]] == [6, 7]                    # one box per empty argument
    assert [it for it in M[1] if it[0] == 't'] == [('t', 0, 0, 'solve('), ('t', 70, 0, ','),
                                                   ('t', 90, 0, ')')]
    U.key(RIGHT)
    assert shown() == 'solve(,|)'
    U.key(RIGHT)
    assert shown() == 'solve(,)|'
    U.key(LEFT)
    U.key(LEFT)
    assert shown() == 'solve(|,)'
    U.key(92)                                                 # typing fills the box
    assert shown() == 'solve(1|,)' and not U.EFLAT
    U.key(RIGHT)
    U.key(93)
    assert shown() == 'solve(1,2|)' and U.EFLAT                # no empty box: flat again
    setline('riemann(|,,,,,)')
    assert len(U.EDMAP[12]) == 6


def test_del_in_an_empty_call_removes_it():
    setline('x+solve(|,)')
    U.key(DEL)
    assert shown() == 'x+|'


def test_filling_the_last_box_keeps_the_text_in_place(monkeypatch):
    for name, value in (('FULL', True),):
        monkeypatch.setattr(U, name, value)
    setline('sin(|)')
    U.redraw()
    y2 = [c for c in TD.CALLS if c[0] == 'draw_text' and c[3].startswith('sin(')]
    assert U.EH == 20
    TD.reset()
    U.key(92)
    assert U.EFLAT and U.EH == 20
    y1 = [c for c in TD.CALLS if c[0] == 'draw_text' and c[3].startswith('sin(')]
    assert y1 and y2 and y1[-1][1:3] == y2[-1][1:3]       # same x and baseline


@pytest.mark.parametrize('before, after', [
    ('solve(x=1,)', 'solve(x=1)'), ('taylor(f,x=0,)', 'taylor(f,x=0)'),
    ('f(a,,b)', 'f(a,,b)'), ('purge(x,,)', 'purge(x)'), ('riemann(f,x,0,1,4,)', 'riemann(f,x,0,1,4)'),
    ('desolve(y\'=y,)', 'desolve(y\'=y)'), ('factor(x^2-1,)', 'factor(x^2-1)'),
    ('solve(,x)', 'solve(,x)'), ('sum(k,k,1,)', 'sum(k,k,1,)'), ('sin()', 'sin()')])
def test_optional_trailing_arguments_are_dropped(before, after):
    assert U.tidy(before) == after


def test_menu_insertion_boxes_and_the_first_box(engine):
    mb = engine.MODS['menub']
    by = dict((row[1], row) for row in engine.need('cat').CAT)
    want = {'simplify(': 'simplify()', 'factor(': 'factor()', 'solve(': 'solve(,)',
            'taylor(': 'taylor(,,)', 'riemann(': 'riemann(,,,,,)', 'desolve(': 'desolve(,)',
            'grad(': 'grad()', 'polararea(': 'polararea(,,,)', 'paramarea(': 'paramarea(,,,,)',
            'arclen(': 'arclen(,,,)', 'purge(': 'purge()', 'sin(': 'sin()', 'ln(': 'ln()',
            'sign(': 'sign()', 'diff(': 'diff(,)', 'integrate(': 'integrate(,,,)',
            'limit(': 'limit(,,,)', 'log(': 'log(,)', 'sum(': 'sum(,,,)', 'pi': 'pi'}
    classic = {'solve(': 'solve()', 'taylor(': 'taylor(,)', 'riemann(': 'riemann(,,,,)',
               'desolve(': 'desolve()', 'diff(': 'diff(,)', 'integrate(': 'integrate(,)',
               'limit(': 'limit(,,)', 'log(': 'log()', 'sum(': 'sum(,,,)'}
    for prefix, text in want.items():
        got = mb.insertion(by[prefix])
        assert got[0] == text and got[2] == len(prefix), prefix
    U.CLASSIC = True
    for prefix, text in classic.items():
        assert mb.insertion(by[prefix])[0] == text, prefix
    U.CLASSIC = False
    setline('|')
    mb.apply(mb.insertion(by['solve(']))
    U.emodel()
    assert shown() == 'solve(|,)'
    setline('x^(2)=4|')
    mb.apply(mb.insertion(by['solve(']))                     # the action wraps the line
    U.emodel()
    assert shown() == 'solve(x^(2)=4,|)'


def test_menu_insertion_by_keys():
    s = KS.run('{f1}{down}{down}{down}{enter}{snap:a}')
    u = s.mods['ui']
    assert (u.LINE, u.CUR) == ('solve(,)', 6) and not u.EFLAT
    s = KS.run('{2nd,0}sin{enter}')
    assert (s.mods['ui'].LINE, s.mods['ui'].CUR) == ('sin()', 4)


def test_enter_needs_the_required_boxes_and_drops_the_optional_ones():
    s = KS.run('{f1}{down}{down}{down}{enter}{enter}')
    u = s.mods['ui']
    assert u.STATUS == 'fill in the empty slot' and u.CUR == 6 and not s.hist
    s = KS.run('{f1}{down}{down}{down}{enter}x^2=4{enter}')
    assert [tuple(e[:2]) for e in s.hist] == [('solve(x^2=4)', 'x=-2,x=2')]
    s = KS.run('{f1}{enter}{enter}')                                   # Simplify, empty
    assert s.mods['ui'].STATUS == 'fill in the empty slot' and not s.hist
    s = KS.run('{2nd,0}sin{enter}{enter}')
    assert s.mods['ui'].STATUS == 'fill in the empty slot' and not s.hist


def test_engine_empty_slot_check_on_a_flat_line(engine):
    for line, pos in (('solve(x=1,)', -1), ('simplify()', 9), ('sin()', 4), ('purge(x,,)', -1),
                      ('riemann(x,x,0,1,4,)', -1), ('riemann(x,x,0,1,,)', 16)):
        U.LINE, U.CUR, U.EDMAP = line, len(line), None
        assert U.empty_slot() == pos, line


def test_classic_stays_1d():
    U.CLASSIC = True
    setline('solve(|,)')
    assert U.EFLAT and U.EDMAP is None


# -- Q5: the argument help in the hint row ---------------------------------------------------------

@pytest.mark.parametrize('name, j, n, text', [
    ('simplify', 0, 1, 'Expr. to simplify (required)'),
    ('solve', 0, 2, 'Equation or system (required)'),
    ('solve', 1, 2, 'Unknown(s), e.g. x (optional)'),
    ('factor', 1, 2, 'Variable (optional)'),
    ('diff', 1, 2, 'With respect to (required)'),
    ('diff', 2, 3, 'Order (optional: empty = 1)'),
    ('integrate', 2, 4, 'Lower bound (opt; empty=indef)'),
    ('limit', 3, 4, 'Side + or - (opt; empty=both)'),
    ('limit', 1, 2, 'Point, e.g. x=0 (required)'),
    ('taylor', 1, 3, 'Center, e.g. x=0 (required)'),
    ('taylor', 1, 4, 'Variable (required)'),
    ('taylor', 3, 4, 'Order (optional: empty = 5)'),
    ('sum', 3, 4, 'End value, oo ok (required)'),
    ('riemann', 5, 6, 'left/mid/trap (opt: right)'),
    ('desolve', 1, 2, 'Function, e.g. y (optional)'),
    ('desolve', 1, 3, 'Independent var. (optional)'),
    ('arclen', 1, 4, 'Variable (required)'),
    ('arclen', 1, 5, 'y(t) (required)'),
    ('purge', 0, 1, 'Variable to delete (required)'),
    ('purge', 3, 4, 'More variables (optional)'),
    ('log', 1, 2, 'Base (optional: empty = 10)'),
    ('surd', 1, 2, 'Root index (required)'),
    ('sin', 0, 1, 'Angle (required)'),
    ('ln', 0, 1, 'Argument (required)'),
    ('tanh', 0, 1, 'Argument (required)'),
    ('floor', 0, 1, 'Argument (required)'),
    ('/', 0, 2, 'Numerator (required)'),
    ('/', 1, 2, 'Denominator (required)'),
    ('^', 0, 1, 'Exponent (required)'),
    ('exp', 0, 1, 'Exponent (required)'),
    ('f', 0, 1, ''),
    ('simplify', 1, 2, '')])
def test_argument_help(name, j, n, text):
    assert U.arghelp(name, j, n) == text


def test_every_argument_text_fits_the_hint_row():
    S = D.ARGS
    seen = 0
    for entry in S.strip(';').split(';'):
        name, spec = entry.split(':')
        n = int(name.split('#')[1]) if '#' in name else len(spec) - 2
        for j in range(len(spec.replace('*', '')) - 2 + spec.count('*')):
            t = U.arghelp(name.split('#')[0], j, n if '#' in name else max(n, j + 1))
            assert t and len(t) <= 31 and all(32 <= ord(c) < 127 for c in t), (entry, j, t)
            seen += 1
    assert seen > 70
    assert U.ARGPH.endswith('|') and U.ARGPH.count('|') <= 62


@pytest.mark.parametrize('before, text', [
    ('simplify(|)', 'Expr. to simplify (required)'),
    ('solve(x=1,|)', 'Unknown(s), e.g. x (optional)'),          # 2D: the box's slot row
    ('solve(x|=1,x)', 'Equation or system (required)'),         # flat: the back-scan
    ('solve(x=1,x|)', 'Unknown(s), e.g. x (optional)'),
    ('(1)/(|)', 'Denominator (required)'),
    ('(|)/(2)', 'Numerator (required)'),
    ('x^(|)', 'Exponent (required)'),
    ('e^(2|)', 'Exponent (required)'),
    ('integrate(x,x,|,)', 'Lower bound (opt; empty=indef)'),
    ('integrate(x^(2),|)', 'Integration var. (required)'),
    ('diff(x^(3),x,|)', 'Order (optional: empty = 1)'),
    ('sum(k,k,1,|)', 'End value, oo ok (required)'),
    ('limit(x,x,0,|)', 'Side + or - (opt; empty=both)'),
    ('limit(sin(x)/x,x=0|)', 'Point, e.g. x=0 (required)'),
    ('log(8,|)', 'Base (optional: empty = 10)'),
    ('surd(8,|)', 'Root index (required)'),
    ('sqrt(|)', 'Radicand (required)'),
    ('solve([x+y=1,|],)', 'Equation or system (required)'),     # a list in a call (2D)
    ('solve([x+y=1,x|],x)', 'Equation or system (required)'),   # (flat)
    ('solve((x|),x)', 'Equation or system (required)'),
    ('arclen(a,|,t,0,1)', 'y(t) (required)'),                   # the 5-argument form
    ('arclen(a,|,0,1)', 'Variable (required)'),
    ('taylor(f,x,|0,5)', 'Center point (required)'),
    ('int(x|)', 'Integrand (required)'),                        # an alias
    ('2sin(|)', 'Angle (required)'),
    ('1+|2', ''), ('|', ''), ('f(x|)', ''), ('sin(x)+|', '')])
def test_hint_for_the_slot_at_the_caret(before, text):
    setline(before)
    assert hint() == text


def test_classic_hint_uses_the_back_scan():
    U.CLASSIC = True
    for before, text in (('x^(2+|)', 'Exponent (required)'), ('solve(x=1,|)',
                                                               'Unknown(s), e.g. x (optional)'),
                         ('diff(x,|)', 'With respect to (required)')):
        setline(before)
        assert hint() == text, before


def test_hint_row_on_screen_before_the_engine_loads():
    s = KS.run('int(x')
    assert 'run' not in s.mods
    assert 'Integrand (required)' in s.screen
    s = KS.run('{2nd,frac}{down}{down}{down}{down}{down}{down}{down}{down}{enter}{snap:lower}')
    assert 'Lower bound (opt; empty=indef)' in s.snap('lower')
    assert 'run' not in s.mods


def test_the_hint_row_repaints_only_when_the_slot_changes(monkeypatch):
    monkeypatch.setattr(U, 'FULL', True)
    setline('simplify(abc|)')
    U.redraw()
    ey = 190 - U.EH
    row = ('fill_rect', -1, ey - 20, 321, 19)
    for k in (LEFT, LEFT, LEFT):
        TD.reset()
        U.key(k)
        assert row not in TD.CALLS, TD.CALLS                 # the same slot: no hint paint
    assert shown() == 'simplify(|abc)'
    TD.reset()
    U.key(LEFT)                                               # out of the call: the row clears
    assert row in TD.CALLS and hint() == ''
    calls = []
    real = U.arghelp
    monkeypatch.setattr(U, 'arghelp', lambda *a: calls.append(a) or real(*a))
    for k in (RIGHT, RIGHT, RIGHT, LEFT):
        U.key(k)
    assert calls == [('simplify', 0, 1)]                      # looked up once per slot change
