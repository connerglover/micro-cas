"""MathPrint templates as on the TI-Nspire CX II CAS (docs/notes/MATHPRINT.md 0.10, 2.2, 3, 3.2,
7.1), the user's rules applied to every template:

R1  nothing is prefilled: every parameter is a visible empty box (picker, menus, catalog,
    the menu's wrap of the line); Classic keeps its old texts;
R2  each 2D command is entered and drawn as its template, the caret starting in the first box in
    drawn order on every path (key, picker, menu, catalog, recall);
R3  optional parameters are optional boxes: left empty they take the engine default (log base,
    derivative order, limit direction, both integral bounds), tidy drops them, and ENTER stops
    only on an empty required box or a half-filled pair of bounds;
R4  the + C of an antiderivative is drawn on the answer's row, right after the answer.

Editing tables drive ui.key with no engine (ui.R is None); session tests run the real entry
program through tests/support/keyscript.py.
"""
import pytest

import draw as D
import keyscript as KS
import ti_draw as TD
import ti_system as TS
import ui as U

SECOND, DEL, LEFT, UP, RIGHT, DOWN = 21, 23, 24, 25, 26, 34
FRAC, POW, COMMA, PLUS, MINUS, CLEAR_KEY, ENTER = 42, 51, 62, 85, 75, 45, 105
CLASSIC = '{f3}' + '{down}' * 5 + '{enter}{clear}'  # F3 setup row 6 (Entry): Classic

STATE = (('LINE', ''), ('CUR', 0), ('XOFF', 0), ('MOD', 0), ('MODE', 0), ('SEL', -1),
         ('HERO', True), ('DX', 0), ('ENTRYPOS', -1), ('LASTENTRY', ''), ('STATUS', ''),
         ('NOTE', ''), ('FULL', True), ('VIEW', None), ('EXOFF', 0), ('EH', 20),
         ('EDMAP', None), ('EMODEL', None), ('EFLAT', True), ('PENDING', None),
         ('ED1D', False), ('EFAIL', None), ('CLASSIC', False), ('VIEWEND', -1))

# the picker's digit keys: page 1 (1-7) and page 2 (after RIGHT, 1-6)
P1 = {'sqrt': 94, 'root': 82, 'e^': 83, '10^': 84, 'log': 72}
P2 = {'abs': 92, 'int': 93, 'diff': 94, 'nth': 82, 'sum': 83, 'lim': 84}


@pytest.fixture(autouse=True)
def editor(monkeypatch):
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


def shown():
    return U.LINE[:U.CUR] + '|' + U.LINE[U.CUR:]


def ed(before, keys):
    setline(before)
    for k in keys:
        U.key(k)
    return shown()


def pick(row):
    TS.load([P1[row]] if row in P1 else [RIGHT, P2[row]])
    U.key(SECOND)
    U.key(FRAC)
    return shown()


def line(s):
    u = s.mods['ui']
    return u.LINE, u.CUR


def script(row):
    """The key script that picks a template picker row."""
    if row in P1:
        return '{2nd,frac}{' + str(P1[row]) + '}'
    return '{2nd,frac}{right}{' + str(P2[row]) + '}'


def walk(s):
    """The stops of LINE s from its start to its end with RIGHT."""
    setline('|' + s)
    U.key(33)
    seen = [U.CUR]
    for _ in range(len(s) + 2):
        U.key(RIGHT)
        if U.CUR == seen[-1]:
            break
        seen.append(U.CUR)
    return seen


# -- R1, R2: insertion from every path, no prefill, the caret in the first box in drawn order ----

PICKS = [
    ('sqrt', 'sqrt(|)'),
    ('root', 'surd(,|)'),                   # the index: drawn first
    ('e^', 'e^(|)'),
    ('10^', '10^(|)'),
    ('log', 'log(,|)'),                     # the base: drawn first
    ('abs', 'abs(|)'),
    ('int', 'integrate(,,|,)'),             # the lower bound
    ('diff', 'diff(,|)'),                   # d/d[]: the variable box
    ('nth', 'diff(,|,)'),                   # d^n/d[]^n: the variable box
    ('sum', 'sum(,|,,)'),                   # the index variable
    ('lim', 'limit(,|,,)'),                 # the variable under lim
]


@pytest.mark.parametrize('row, after', PICKS)
def test_picker_rows_start_in_the_first_box(row, after):
    assert pick(row) == after
    assert U.R is None and U.PENDING is None


def test_picker_table_has_one_integral_and_no_prefill():
    assert U.TN == 13
    texts = [U.tmpl(j)[1] for j in range(U.TN)]
    assert texts == ['', '', 'sqrt()', 'surd(,)', 'e^()', '10^()', 'log(,)', 'abs()',
                     'integrate(,,,)', 'diff(,)', 'diff(,,)', 'sum(,,,)', 'limit(,,,)']
    for j in range(U.TN):
        assert len(U.tmpl(j)) == 2 and len(U.tmpl(j)[0]) <= 28
    TS.load([UP, ENTER])                                # the last row wraps to the limit
    U.key(SECOND)
    U.key(FRAC)
    assert shown() == 'limit(,|,,)'


def test_picker_page_two_lists_six_rows():
    TS.load([RIGHT])
    U.key(SECOND)
    with pytest.raises(TS.StopScript):                  # the keys run out inside the picker
        U.key(FRAC)
    texts = [t.text for t in TD.TEXTS]
    assert '1-6 pick  <> page  CLEAR back' in texts
    assert ' 4 d^n/dx^n  nth derivative' in texts
    assert TD.OFFSCREEN == [] and TD.OVERDRAW == []


def test_nth_root_key_starts_in_the_index():
    assert ed('2+|', [SECOND, POW]) == '2+surd(,|)'
    assert ed('|', [SECOND, POW, 93, COMMA, 94, 92]) == 'surd(31|,2)'


def test_menu_insertions_in_mathprint():
    for keys, want in (('{math}{enter}', ('diff(,)', 6)),
                       ('{math}{down}{enter}', ('integrate(,,,)', 12)),
                       ('{math}{down}{down}{enter}', ('limit(,,,)', 7)),
                       ('{2nd,0}su{enter}', ('sum(,,,)', 5)),
                       ('{2nd,0}sur{enter}', ('surd(,)', 6)),
                       ('{2nd,0}log{enter}', ('log(,)', 5)),
                       ('{2nd,0}ri{enter}', ('riemann(,,,,)', 8)),
                       ('{2nd,0}ar{enter}', ('arclen(,,,)', 7))):
        s = KS.run(keys)
        assert line(s) == want, keys
        assert s.mods['ui'].PENDING is None


def test_menu_wraps_the_line_into_the_template():
    s = KS.run('x^(2{math}{down}{enter}')
    assert line(s) == ('integrate(x^(2),,,)', 17)      # lower bound, then upper, f, dx
    s = KS.run('x^(3{math}{enter}')
    assert line(s) == ('diff(x^(3),)', 11)              # the variable box
    s = KS.run('x^(3{math}{enter}x{enter}')
    assert s.hist[0][:2] == ['diff(x^3,x)', '3*x^2']


def test_menub_insertion_has_no_prefill():
    import menub as MB
    import run as R
    U.R = R
    R.need('menu')
    rows = {}
    for row in R.need('cat').CAT:
        rows[row[0]] = row
    want = {'diff(f,x,[n])': ('diff(,)', 5), 'sum(f,k,a,b)': ('sum(,,,)', 4),
            'integrate(f,x,[a,b])': ('integrate(,,,)', 10),
            'limit(f,x,a,[dir])': ('limit(,,,)', 6), 'log(x,[b])': ('log(,)', 4),
            'surd(x,n)': ('surd(,)', 5), 'sqrt(x)': ('sqrt()', 5), 'abs(x)': ('abs()', 4),
            'exp(x)': ('exp()', 4),
            'riemann(f,x,a,b,n,[method])': ('riemann(,,,,)', 8),
            'arclen(f,x,a,b)': ('arclen(,,,)', 7), 'taylor(f,x=a,[n])': ('taylor(,)', 7),
            'polararea(r,t,a,b)': ('polararea(,,,)', 10),
            'paramarea(x,y,t,a,b)': ('paramarea(,,,,)', 10),
            'purge(x,...)': ('purge()', 6), 'sin(x)': ('sin()', 4)}
    for sig, (text, offset) in want.items():
        got = MB.insertion(rows[sig])
        assert (got[0], got[2]) == (text, offset), sig
    U.CLASSIC = True                                    # Classic: as before MathPrint
    assert MB.insertion(rows['integrate(f,x,[a,b])'])[0] == 'integrate(,)'
    assert MB.insertion(rows['diff(f,x,[n])'])[0] == 'diff(,)'
    assert MB.insertion(rows['limit(f,x,a,[dir])'])[0] == 'limit(,,)'
    assert MB.insertion(rows['log(x,[b])'])[0] == 'log()'


# -- R2: drawn order, the visiting order of the arrows ------------------------------------------

WALKS = [
    ('integrate(,,,)', [0, 12, 13, 10, 11, 14]),       # lower, upper, integrand, d[] variable
    ('diff(,)', [0, 6, 5, 7]),                          # d/d[]: variable, then the expression
    ('diff(,,)', [0, 6, 7, 5, 8]),                      # variable, order, expression
    ('sum(,,,)', [0, 5, 6, 7, 4, 8]),                   # k, a, b, f
    ('limit(,,,)', [0, 7, 8, 9, 6, 10]),                # x, a, direction, f
    ('surd(,)', [0, 6, 5, 7]),                          # index, radicand
    ('log(,)', [0, 5, 4, 6]),                           # base, operand
]


@pytest.mark.parametrize('s, stops', WALKS)
def test_arrows_follow_the_drawn_order(s, stops):
    assert walk(s) == stops
    assert U.EDMAP[8] == stops


@pytest.mark.parametrize('s', ['diff(x^(3),x,2)', 'diff(f,x,n+1)', 'limit(f,x,a,+)',
                               'limit(f,x,a,-)', 'limit(f,x,a,)', 'integrate(f,x,a,b)',
                               'integrate(f,x,,)', 'log(u,)', 'diff(f,x,)'])
def test_walk_visits_every_stop_once_and_back(s):
    seen = walk(s)
    assert seen[-1] == len(s) and len(seen) == len(set(seen))
    assert seen == U.EDMAP[8]
    back = [U.CUR]
    for _ in range(len(seen) - 1):
        U.key(LEFT)
        back.append(U.CUR)
    assert back == seen[::-1]


def test_derivative_variable_then_expression():
    pick('diff')
    U.key(32)                                           # x into the d/d[] box
    assert shown() == 'diff(,x|)'
    U.key(RIGHT)
    assert shown() == 'diff(|,x)'                       # the expression box
    setline('diff(,x|)')
    U.key(UP)                                           # the expression is above the bar's foot
    assert shown() == 'diff(|,x)'


# -- C9: the comma steps through a full template in drawn order ---------------------------------

COMMAS = [
    ('surd(,3|)', 'surd(|,3)'),                         # index -> radicand
    ('surd(8|,3)', 'surd(8,3)|'),                       # the last box: after the template
    ('log(,2|)', 'log(|,2)'),
    ('integrate(,,0|,)', 'integrate(,,0,|)'),
    ('integrate(,,0,1|)', 'integrate(|,,0,1)'),
    ('integrate(x|,,0,1)', 'integrate(x,|,0,1)'),
    ('integrate(x,x|,0,1)', 'integrate(x,x,0,1)|'),
    ('diff(,x|,)', 'diff(,x,|)'),
    ('diff(,x,2|)', 'diff(|,x,2)'),
    ('sum(,k|,,)', 'sum(,k,|,)'),
    ('limit(,x,0|,)', 'limit(,x,0,|)'),
    ('limit(,x,0,+|)', 'limit(|,x,0,+)'),
    # below the largest form a comma still adds an argument (typed text keeps working)
    ('diff(,x|)', 'diff(,x,|)'),
    ('integrate(x^(2|),x)', 'integrate(x^(2),|x)'),
    ('integrate(x,x|)', 'integrate(x,x,|)'),
    ('sin(x|)', 'sin(x,|)'),
]


@pytest.mark.parametrize('before, after', COMMAS)
def test_comma_in_templates(before, after):
    assert ed(before, [COMMA]) == after


# -- DEL: an empty template goes in one DEL ----------------------------------------------------

DELS = [
    ('integrate(,,|,)', '|'),
    ('integrate(,,,|)', '|'),                           # any slot of an empty template
    ('integrate(,,,)|', '|'),
    ('diff(,|)', '|'),
    ('diff(,x|)', 'diff(,|)'),
    ('diff(,)|', '|'),
    ('diff(,|,)', '|'),
    ('diff(,,|)', '|'),
    ('diff(,x,|)', 'diff(,x|,)'),                       # a later slot: like left
    ('diff(,,)|', '|'),
    ('sum(,|,,)', '|'),
    ('sum(,,,)|', '|'),
    ('limit(,|,,)', '|'),
    ('limit(,,,)|', '|'),
    ('limit(,,,|)', '|'),
    ('limit(,x,,|)', 'limit(,x,|,)'),
    ('limit(,x,0,+|)', 'limit(,x,0,|)'),
    ('surd(,|)', '|'),
    ('log(,|)', '|'),
    ('integrate(x^(2),x,|,)', '|integrate(x^(2),x,,)'),  # other slots hold text: to the start
    ('2+integrate(,,|,)', '2+|'),
]


@pytest.mark.parametrize('before, after', DELS)
def test_del_in_the_templates(before, after):
    assert ed(before, [DEL]) == after


# -- R3: optional boxes at ENTER ----------------------------------------------------------------

STAGES = [
    # (line, stage-1 caret on the 2D line, stage-2 caret on the text)
    ('integrate(x^(2),x,,)', -1, -1),
    ('integrate(x^(2),x,0,)', 20, 20),
    ('integrate(x^(2),x,,1)', 18, 18),
    ('integrate(x^(2),,,)', 16, 16),                    # the variable: both bounds optional
    ('integrate(,x,,)', 10, 10),
    ('diff(x,x,)', -1, -1),
    ('diff(x,,)', 7, 7),
    ('diff(x,,2)', 7, 7),
    ('diff(,x,)', 5, 5),
    ('limit(x,x,0,)', -1, -1),
    ('limit(x,x,0,+)', -1, -1),
    ('limit(x,x,0,-)', -1, -1),
    ('limit(x,x,,)', 10, 10),
    ('limit(x,x,0,2+)', 14, 14),
    ('log(8,)', -1, -1),
    ('log(,8)', 4, 4),
    ('2integrate(x,x,,)+log(8,)', -1, -1),
    ('integrate(x,x,,)+f(,)', 19, 19),
    ('sin(1,)', -1, 6),                                 # flat: stage 2 finds it
    ('surd(8,)', 7, 7),
]


@pytest.mark.parametrize('text, one, two', STAGES)
def test_optional_boxes_at_enter(text, one, two):
    setline(text + '|')
    U.emodel()
    assert (U.EDMAP is None) == (text == 'sin(1,)')
    assert U.empty_map() == one
    U.EDMAP = None                                      # stage 2 on the text alone
    assert U.empty_slot() == two
    U.EMODEL = None
    U.emodel()
    assert U.empty_slot() == two                        # the same with a fresh map


def test_stage_two_on_a_line_too_long_for_the_layout():
    text = '1+' * 80 + 'integrate(x,x,,)'              # 176 characters: drawn flat (5.3)
    setline(text + '|')
    U.emodel()
    assert U.EFLAT and U.EDMAP is None and U.empty_map() == -1
    assert U.empty_slot() == -1                         # the bounds are still optional
    U.LINE = '1+' * 80 + 'integrate(x,x,0,)'
    assert U.empty_slot() == len(U.LINE) - 1
    U.EFAIL = U.LINE = text                             # a line a panic ran on is not parsed:
    assert U.empty_slot() == len(text) - 2              # every box counts


def test_classic_keeps_the_old_stage_two():
    U.CLASSIC = True
    for text, pos in (('integrate(x^2,x,,)', 16), ('log(8,)', 6), ('limit(x,x,0,)', 12)):
        U.LINE = text
        assert U.empty_slot() == pos, text


TIDY = [
    ('integrate(x^(2),x,,)', 'integrate(x^2,x)'),
    ('integrate(x^(2),x,0,1)', 'integrate(x^2,x,0,1)'),
    ('integrate((1)/(x),t,,)+1', 'integrate(1/x,t)+1'),
    ('integrate(x,x,0,)', 'integrate(x,x,0,)'),
    ('log(x,)', 'log(x)'),
    ('log(x,2)', 'log(x,2)'),
    ('diff(x^(3),x,)', 'diff(x^3,x)'),
    ('diff(x^(3),x,2)', 'diff(x^3,x,2)'),
    ('limit(x,x,0,)', 'limit(x,x,0)'),
    ('limit(x,x,0,+)', 'limit(x,x,0,1)'),
    ('limit(x,x,0,-)', 'limit(x,x,0,-1)'),
    ('limit(x,x,0,1)', 'limit(x,x,0,1)'),
    ('2limit((1)/(x),x,0,-)+1', '2limit(1/x,x,0,-1)+1'),
]


@pytest.mark.parametrize('before, after', TIDY)
def test_tidy_drops_the_empty_optional_boxes(before, after):
    assert U.tidy(before) == after


STRUCTURE = [
    ('integrate(x^2,x)', 'integrate(x^(2),x,,)'),       # the one integral template
    ('integrate(x^2,x,0,1)', 'integrate(x^(2),x,0,1)'),
    ('limit(x,x,0)', 'limit(x,x,0,)'),                  # an empty direction box
    ('limit(x,x,0,1)', 'limit(x,x,0,+)'),
    ('limit(x,x,0,-1)', 'limit(x,x,0,-)'),
    ('limit(1/x,x=0,1)', 'limit((1)/(x),x=0,1)'),     # x=a: a plain call
    ('diff(x^3,x)', 'diff(x^(3),x)'),
    ('diff(x^3,x,2)', 'diff(x^(3),x,2)'),
    ('log(8)', 'log(8)'),
]


@pytest.mark.parametrize('before, after', STRUCTURE)
def test_structure_shows_the_templates(before, after):
    assert U.tidy(before, 1) == after
    if before != 'limit(1/x,x=0,1)':
        assert U.tidy(after) == before


def test_limit_with_x_equals_a_is_a_plain_call():
    M = D.mlayout('limit((1)/(x),x=0,1)', 2)
    assert 'T' not in [c[3] for c in M[11]]
    M = D.mlayout('limit((1)/(x),x,0,1)', 2)
    assert 'T' in [c[3] for c in M[11]]


def test_history_input_draws_the_direction_as_a_sign():
    for text, sign in (('limit(1/x,x,0,1)', '+'), ('limit(1/x,x,0,-1)', '-')):
        dl = D.mlayout(text, 1)[0]
        texts = [it[3] for it in dl if it[0] == 't']
        assert sign in texts and '1' in texts and '-1' not in texts, text


# -- sessions: ENTER results with optional boxes empty and filled --------------------------------

def test_derivative_session():
    s = KS.run(script('diff') + 'x{right}x^3{enter}')
    assert s.hist[0][:2] == ['diff(x^3,x)', '3*x^2']
    s = KS.run(script('diff') + 't{up}t^2{enter}')
    assert s.hist[0][:2] == ['diff(t^2,t)', '2*t']


def test_nth_derivative_session():
    s = KS.run(script('nth') + 'x{right}2{right}x^3{enter}')
    assert s.hist[0][:2] == ['diff(x^3,x,2)', '6*x']
    s = KS.run(script('nth') + 'x{right}{right}x^3{enter}')      # the order left empty: 1
    assert s.hist[0][:2] == ['diff(x^3,x)', '3*x^2']
    s = KS.run(script('nth') + '{right}2{right}x^3{enter}')      # the variable is required
    assert line(s) == ('diff(x^(3),,2)', 11) and not s.hist
    assert s.mods['ui'].STATUS == 'fill in the empty slot' and 'run' not in s.mods


def test_derivative_with_an_empty_variable_box():
    s = KS.run(script('diff') + '{right}x^3{enter}')
    assert line(s) == ('diff(x^(3),)', 11) and not s.hist
    assert s.mods['ui'].STATUS == 'fill in the empty slot' and 'run' not in s.mods


def test_integral_with_empty_bounds_is_an_antiderivative():
    s = KS.run(script('int') + '{right}{right}x^2{right}x{enter}')
    h = s.hist[0]
    assert h[:3] == ['integrate(x^2,x)', 'x^3/3', 'ans'] and h[4] & s.mods['run'].F_PLUSC


def test_definite_integral():
    s = KS.run(script('int') + '0{right}1{right}x^2{right}x{enter}')
    assert s.hist[0][:2] == ['integrate(x^2,x,0,1)', '1/3']
    assert not s.hist[0][4] & s.mods['run'].F_PLUSC


def test_one_empty_bound_is_an_empty_slot():
    s = KS.run(script('int') + '0{right}{right}x^2{right}x{enter}')
    assert line(s) == ('integrate(x^(2),x,0,)', 20) and not s.hist
    assert s.mods['ui'].STATUS == 'fill in the empty slot'
    s = KS.run(script('int') + '{right}1{right}x^2{right}x{enter}')
    assert line(s) == ('integrate(x^(2),x,,1)', 18) and not s.hist
    assert s.mods['ui'].STATUS == 'fill in the empty slot'


def test_integral_with_an_empty_variable_box():
    s = KS.run(script('int') + '{right}{right}x^2{enter}')
    assert line(s) == ('integrate(x^(2),,,)', 16) and not s.hist
    assert s.mods['ui'].STATUS == 'fill in the empty slot' and 'run' not in s.mods


def test_log_base_box():
    s = KS.run(script('log') + '{right}100{enter}')              # empty base: base 10
    assert s.hist[0][:2] == ['log(100)', '2']
    s = KS.run(script('log') + '2{right}8{enter}')
    assert s.hist[0][:2] == ['log(8,2)', '3']


def test_limit_direction_box():
    f = 'x{right}0{right}{right}abs(x{right}/x{enter}'          # two-sided: no limit
    s = KS.run(script('lim') + f)
    assert s.hist[0][0] == 'limit(abs(x)/x,x,0)'
    two = s.hist[0][1]
    s = KS.run(script('lim') + 'x{right}0{right}+{right}abs(x{right}/x{enter}')
    assert s.hist[0][:2] == ['limit(abs(x)/x,x,0,1)', '1']
    s = KS.run(script('lim') + 'x{right}0{right}-{right}abs(x{right}/x{enter}')
    assert s.hist[0][:2] == ['limit(abs(x)/x,x,0,-1)', '-1']
    assert two not in ('1', '-1')
    s = KS.run(script('lim') + 'x{right}0{right}{right}sin(x{right}/x{enter}')
    assert s.hist[0][:2] == ['limit(sin(x)/x,x,0)', '1']


def test_limit_and_sum_need_their_variable():
    s = KS.run(script('lim') + '{right}0{right}{right}sin(x{right}/x{enter}')
    assert line(s)[1] == 15 and not s.hist              # the empty variable box
    s = KS.run(script('sum') + 'k{right}1{right}n{right}k{enter}')
    assert s.hist[0][0] == 'sum(k,k,1,n)'
    s = KS.run(script('sum') + '{right}1{right}n{right}k{enter}')
    assert line(s)[1] == 6 and not s.hist


def test_nth_root_session():
    assert KS.run('{2nd,x^n}3,8{enter}').ans == '2'      # index 3, then the radicand 8
    assert KS.run(script('root') + '3{right}8{enter}').ans == '2'


# -- recall, ENTRY and paste round trips --------------------------------------------------------

def test_recall_shows_the_templates():
    s = KS.run('integrate(x^2,x){enter}{2nd,enter}')
    assert s.mods['ui'].LINE == 'integrate(x^(2),x,,)'
    s = KS.run('integrate(x^2,x){enter}{2nd,enter}{enter}')
    assert s.hist[1][:2] == ['integrate(x^2,x)', 'x^3/3']
    s = KS.run('integrate(x^2,x,0,1){enter}{2nd,enter}{enter}')
    assert s.hist[1][:2] == ['integrate(x^2,x,0,1)', '1/3']
    s = KS.run('integrate(x^2,x){enter}{up}{2nd,enter}')
    assert s.mods['ui'].LINE == 'integrate(x^(2),x,,)'
    s = KS.run(script('lim') + 'x{right}0{right}+{right}abs(x{right}/x{enter}{2nd,enter}')
    assert s.mods['ui'].LINE == 'limit((abs(x))/(x),x,0,+)'
    s = KS.run(script('nth') + 'x{right}2{right}x^3{enter}{2nd,enter}{enter}')
    assert s.hist[1][:2] == ['diff(x^3,x,2)', '6*x']


# -- R4: + C on the answer's row -----------------------------------------------------------------

def answer_texts():
    """The texts drawn in the history stage, as (text, x, top)."""
    return [(t.text, t.x, t.y) for t in TD.TEXTS if 20 <= t.y < 150]


def test_plus_c_is_drawn_inline_and_right_aligned():
    s = KS.run('integrate(x^2,x){enter}')
    texts = answer_texts()
    plus = [t for t in texts if t[0] == '+']
    c = [t for t in texts if t[0] == 'C']
    assert len(plus) == 1 and len(c) == 1
    assert c[0][1] + 10 == 310                          # the answer, + C included, ends at 309
    assert plus[0][2] == c[0][2] and c[0][1] - plus[0][1] == 12   # spaced like an operator
    w = s.mods['draw'].layout('x^3/3', 300, 92)[1]
    assert plus[0][1] == 310 - 24 + 2                   # 2 px after the answer's box
    assert min(t[1] for t in texts if t[0] == '3') == 310 - 24 - w + (w - 10) // 2
    footer = [t.text for t in TD.TEXTS if t.y == 153]
    assert footer == ['exact  F4']                      # no + C in the hint row any more
    assert s.hist[0][1] == 'x^3/3'                      # the history text is unchanged
    assert TD.OFFSCREEN == [] and TD.OVERDRAW == []


def test_plus_c_sits_on_the_answer_baseline():
    KS.run('integrate(x^2,x){enter}')
    texts = answer_texts()
    c = [t for t in texts if t[0] == 'C'][0]
    den = [t for t in texts if t[0] == '3' and t[1] < c[1]]
    num = [t for t in texts if t[0] == 'x' and t[1] < c[1]]
    assert min(t[2] for t in num) < c[2] < max(t[2] for t in den)   # between the operands


def test_plus_c_on_a_one_line_answer():
    KS.run('integrate(2,x){enter}')
    texts = answer_texts()
    ans = [t for t in texts if t[0] in ('2*x', '2', 'x')]
    c = [t for t in texts if t[0] == 'C']
    assert c and ans and all(t[2] == c[0][2] for t in ans)


def test_no_plus_c_for_other_answers():
    KS.run('integrate(x^2,x,0,1){enter}diff(x^3,x){enter}')
    assert 'C' not in [t[0] for t in answer_texts()]


def test_paste_recall_and_forms_have_no_plus_c():
    s = KS.run('integrate(x^2,x){enter}{up}{enter}')
    assert s.mods['ui'].LINE == '(x^3/3)'
    s = KS.run('integrate(x^2,x){enter}{f4}')
    assert all('C' not in str(f) for f in s.hist[0][5])
    assert [t[0] for t in answer_texts()].count('C') == 1


def test_plus_c_scrolls_with_a_wide_answer():
    text = 'integrate(' + '+'.join('x^%d' % k for k in range(1, 9)) + ',x){enter}'
    s = KS.run(text)
    assert s.hist[0][4] & s.mods['run'].F_PLUSC
    span = s.mods['ui'].VIEW[7]
    assert span > 0
    assert 'C' not in [t[0] for t in answer_texts()]   # beyond the view
    s = KS.run(text + '{right}' * (span // 24 + 2))
    assert s.mods['ui'].DX == span
    c = [t for t in answer_texts() if t[0] == 'C']
    assert c and c[0][1] + 10 == 310                    # scrolled fully: + C at the right edge
    assert TD.OFFSCREEN == [] and TD.OVERDRAW == []


def test_plus_c_on_older_entries_and_the_selection():
    s = KS.run('integrate(x^2,x){enter}2+3{enter}integrate(cos(x),x){enter}{up}{up}{up}')
    assert s.mods['ui'].MODE == 1 and s.mods['ui'].SEL == 0
    assert [t[0] for t in answer_texts()].count('C') == 2
    assert TD.OFFSCREEN == [] and TD.OVERDRAW == []


def test_plus_c_on_the_panic_screen():
    # the plain screen after an exception shows the answer as 1D text: + C stays with it
    s = KS.run('integrate(x^2,x){enter}')
    TD.reset()
    s.mods['ui'].panic(0)
    assert 'x^3/3 + C' in TD.screen_text()
    s = KS.run('2/3{enter}')
    TD.reset()
    s.mods['ui'].panic(0)
    assert '+ C' not in TD.screen_text()


# -- Classic -------------------------------------------------------------------------------------

def test_classic_is_unchanged():
    s = KS.run(CLASSIC + '{math}{down}{enter}')
    assert s.mods['ui'].CLASSIC and line(s) == ('integrate(,)', 10)
    s = KS.run(CLASSIC + '{math}{down}{enter}x^2{right}x{enter}')
    assert s.hist[0][:2] == ['integrate(x^2,x)', 'x^3/3']
    s = KS.run(CLASSIC + '{2nd,frac}')
    assert line(s) == ('', 0)                           # no picker in Classic
    s = KS.run(CLASSIC + '{2nd,x^n}')
    assert line(s) == ('surd(', 5)
    s = KS.run(CLASSIC + 'integrate(x^2,x){enter}{2nd,enter}')
    assert line(s) == ('integrate(x^2,x)', 16)          # recall: the text as typed
