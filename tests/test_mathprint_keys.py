"""MathPrint milestone B: the editor's keys (docs/notes/MATHPRINT.md sections 2-4, 6.5, 7.4, 8).

Two kinds of test. Editing tables drive ui.key directly from a (LINE, CUR) written with '|' as
the caret, with no engine (ui.R is None), as on the calculator before the first ENTER. Session
tests run the real entry program through tests/support/keyscript.py (ENTER, history, menus,
the picker, ENTRY recall, panic), and compare typed MathPrint input with the 1D text's answers.
"""
import importlib.util
import os
import random

import pytest

import draw as D
import keyscript as KS
import ti_draw as TD
import ti_system as TS
import ui as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECOND, DEL, LEFT, UP, RIGHT, DOWN = 21, 23, 24, 25, 26, 34
FRAC, POW, SQ, COMMA, LP, RP, DIV, MUL = 42, 51, 61, 62, 63, 64, 55, 65
MINUS, PLUS, STO, ENTER, CLEAR = 75, 85, 91, 105, 45

STATE = (('LINE', ''), ('CUR', 0), ('XOFF', 0), ('MOD', 0), ('MODE', 0), ('SEL', -1),
         ('HERO', True), ('DX', 0), ('ENTRYPOS', -1), ('LASTENTRY', ''), ('STATUS', ''),
         ('NOTE', ''), ('FULL', True), ('VIEW', None), ('EXOFF', 0), ('EH', 20),
         ('EDMAP', None), ('EMODEL', None), ('EFLAT', True), ('PENDING', None),
         ('ED1D', False), ('EFAIL', None), ('CLASSIC', False), ('VIEWEND', -1))


@pytest.fixture(autouse=True)
def editor(monkeypatch):
    """A fresh editor without the engine (every name must exist: raising=True)."""
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


# -- section 2: keys --------------------------------------------------------------------------

KEYS = [
    # plain inserts, the leave rule of => and the table texts that autoclose
    ('x|', [93], 'x2|'),
    ('x^(2|)', [STO], 'x^(2)=>|'),
    ('1|', [DIV], '1/|'),
    ('2|', [MUL], '2*|'),
    ('|', [104], '-|'),
    ('|', [SECOND, 104], 'ans()|'),
    ('|', [SECOND, 55], 'pi|'),
    ('x|', [32], 'xx|'),
    # 42, 51, 61 and the template keys
    ('x|', [FRAC], '(x)/(|)'),
    ('x|', [POW], 'x^(|)'),
    ('x^(2)|', [POW], '(x^(2))^(|)'),
    ('2x^(2)|', [POW], '2(x^(2))^(|)'),
    ('(a)/(b)|', [POW], '((a)/(b))^(|)'),
    ('x|', [SQ], 'x^(2)|'),
    ('sin(x|)', [SQ], 'sin(x^(2)|)'),
    ('x^(2)|', [SQ], '(x^(2))^(2)|'),
    ('|', [SECOND, SQ], 'sqrt(|)'),
    ('|', [SECOND, POW], 'surd(|,)'),
    ('|', [SECOND, 71], '10^(|)'),
    ('|', [SECOND, 81], 'e^(|)'),
    ('|', [71], 'log(|)'),
    ('|', [81], 'ln(|)'),
    ('|', [52], 'sin(|)'),
    ('|', [53], 'cos(|)'),
    ('|', [54], 'tan(|)'),
    ('|', [SECOND, 52], 'asin(|)'),
    ('2|', [52], '2sin(|)'),
    # openers: autoclose at the end of the current slot
    ('|x+1', [LP], '(|x+1)'),
    ('1/|4', [LP], '1/(|4)'),
    ('x+1|', [LP], 'x+1(|)'),
    ('|', [LP], '(|)'),
    ('x^(|)', [LP], 'x^(|)'),
    ('sin(|x)', [LP], 'sin((|x))'),
    ('(1)/(|2)', [LP], '(1)/((|2))'),
    ('|x', [SECOND, LP], '{|x}'),
    ('|x', [SECOND, MINUS], '[|x]'),
    # closers
    ('x^(2|)', [RP], 'x^(2)|'),
    ('sin(x|)', [RP], 'sin(x)|'),
    ('2(3|x+1)', [RP], '2(3)|x+1'),
    ('sin(a|+b)', [RP], 'sin(a)|+b'),
    ('x+1|', [RP], 'x+1)|'),
    ('integrate(f|,x)', [RP], 'integrate(f|,x)'),
    ('(a|)/(b)', [RP], '(a)/(|b)'),
    ('{a|}', [SECOND, RP], '{a}|'),
    ('[a|+b]', [SECOND, PLUS], '[a]|+b'),
    ('(x+1|', [RP], '(x+1)|'),
    # comma
    ('surd(8|,)', [COMMA], 'surd(8,|)'),
    ('integrate(x^(2|),x)', [COMMA], 'integrate(x^(2),|x)'),
    ('sin(x|)', [COMMA], 'sin(x,|)'),
    ('(1)/((2)/(3|))', [COMMA], '(1)/((2)/(3)),|'),
    # + and - leave a hidden slot only when it holds one visible group
    ('(1)/((x+1)|)', [PLUS], '(1)/((x+1))+|'),
    ('(1)/(x|)', [PLUS], '(1)/(x+|)'),
    ('x^((a)|)', [MINUS], 'x^((a))-|'),
    ('x^(2|)', [MINUS], 'x^(2-|)'),
    # home and end
    ('x+|1', [SECOND, LEFT], '|x+1'),
    ('x+|1', [SECOND, RIGHT], 'x+1|'),
    ('(a)/(|b)', [SECOND, RIGHT], '(a)/(b)|'),
    # keys with no entry
    ('x|', [33], 'x|'),
    ('x|', [SECOND, 93], 'x|'),
    ('x|', [SECOND, 91], 'x|'),
]


@pytest.mark.parametrize('before, keys, after', KEYS)
def test_keys(before, keys, after):
    assert ed(before, keys) == after
    assert U.R is None


def test_surd_comma_steps_to_the_index():
    assert ed('|', [SECOND, POW, 73, COMMA, 94]) == 'surd(8,3|)'


def test_clear_empties_then_clears_the_footer():
    setline('(1)/(2|)')
    U.key(CLEAR)
    assert (U.LINE, U.CUR, U.EXOFF, U.PENDING) == ('', 0, 0, None)
    assert U.HERO
    U.key(CLEAR)
    assert U.HERO is False and U.STATUS == ''


def test_unknown_key_changes_nothing():
    setline('(1)/(2|)')
    U.key(43)
    assert shown() == '(1)/(2|)'


# -- section 2.1: fraction term capture -------------------------------------------------------

TERMS = [
    ('x|', '(x)/(|)'),
    ('2sin(x)|', '(2sin(x))/(|)'),
    ('a+b|', 'a+(b)/(|)'),
    ('-x|', '-(x)/(|)'),
    ('(a+b)|', '(a+b)/(|)'),
    ('x^(2)|', '(x^(2))/(|)'),
    ('ans()|', '(ans())/(|)'),
    ('sqrt(x|)', 'sqrt((x)/(|))'),
    ('a+|', 'a+(|)/()'),
    ('|', '(|)/()'),
    ('ab|c', '(ab)/(|)c'),
    ('2(a+b)|', '(2(a+b))/(|)'),
    ('(a)/(b)|', '((a)/(b))/(|)'),
    ('x=3.5|', 'x=(3.5)/(|)'),
    ("f'|", "(f')/(|)"),
    ('3!|', '(3!)/(|)'),
    ('2+x^2|', '2+x^((2)/(|))'),
    ('(1+2)^(3)|', '((1+2)^(3))/(|)'),
    ('a*b|', 'a*(b)/(|)'),
]


@pytest.mark.parametrize('before, after', TERMS)
def test_fraction_term_capture(before, after):
    assert ed(before, [FRAC]) == after


def test_stale_map_capture_gives_the_same_text():
    # the leading-operator ans() insert makes the map stale before 42 runs; the flat scan
    # then treats every bracket as visible and gives the same text as the fresh map
    setline('(a)/(b)|')
    U.EDMAP = None
    U.EMODEL = (U.LINE, U.CLASSIC)
    U.key(FRAC)
    assert shown() == '((a)/(b))/(|)' or shown() == '(a)/(b)/(|)'
    for before, after in TERMS[:12]:
        setline(before)
        U.EDMAP = None
        U.EMODEL = (U.LINE, U.CLASSIC)
        U.key(FRAC)
        assert shown() == after, before


# -- section 4.2: left and right --------------------------------------------------------------

MOVES = [
    ('x^(2|)+1', RIGHT, 'x^(2)|+1'),
    ('(a|)/(b)', RIGHT, '(a)/(|b)'),
    ('(a)/(b|)', RIGHT, '(a)/(b)|'),
    ('|surd(8,3)', RIGHT, 'surd(8,|3)'),
    ('surd(8,3|)', RIGHT, 'surd(|8,3)'),
    ('sum(f,k,1,n|)', RIGHT, 'sum(|f,k,1,n)'),
    ('sum(f,k,|1,n)', LEFT, 'sum(f,k|,1,n)'),
    ('sin(|x)', LEFT, '|sin(x)'),
    ('|sin(x)', RIGHT, 'sin(|x)'),
    ('x^(2)|+1', LEFT, 'x^(2|)+1'),
    ('|', LEFT, '|'),
    ('x+1|', RIGHT, 'x+1|'),
    ('|x+1', LEFT, '|x+1'),
    ('xsqrt(|4)', LEFT, 'x|sqrt(4)'),
]


@pytest.mark.parametrize('before, k, after', MOVES)
def test_left_right(before, k, after):
    assert ed(before, [k]) == after


def test_non_stop_snaps_to_the_next_stop():
    U.LINE, U.CUR, U.EMODEL = 'sin(x)', 2, None
    U.key(33)
    assert U.CUR == 4
    U.LINE, U.CUR, U.EMODEL = '(a)/(b)', 3, None
    U.key(33)
    assert U.CUR == 5


@pytest.mark.parametrize('s', ['x^(2)+1', '(a)/(b)', 'surd(8,3)', 'sum(,k,,)', 'sum(f,k,1,n)',
                               'integrate(,x,,)', 'integrate(f,x)', 'log(u,b)', 'diff(f,x)',
                               'limit(f,x,a)', '(1+(x)/(2))/(3)', 'x^((a)/(b))+sqrt(abs(y))',
                               'sin(x)+cos(y)', '2+3'])
def test_walk_visits_every_stop_once_and_back(s):
    setline('|' + s)
    U.key(33)
    seen = [U.CUR]
    for _ in range(len(s) + 2):
        U.key(RIGHT)
        if U.CUR == seen[-1]:
            break
        seen.append(U.CUR)
    assert seen[-1] == len(s) and len(seen) == len(set(seen))
    if U.EDMAP is not None:
        assert seen == U.EDMAP[8]
    back = [U.CUR]
    for _ in range(len(seen) - 1):
        U.key(LEFT)
        back.append(U.CUR)
    assert back == seen[::-1]


# -- section 4.3: DEL -------------------------------------------------------------------------

DELS = [
    ('2ans()|', '2|'),
    ('2ans(|)', '2|'),
    ('sum(,k,|,)', '|'),
    ('(|)/()', '|'),
    ('integrate(|,x)', '|'),
    ('x^(|)', 'x|'),
    ('x^(|2)', 'x|^(2)'),
    ('(a)/(|)', 'a|'),
    ('(a+b)/(|)', 'a+b|'),
    ('2*(a+b)/(|)', '2*(a+b)|'),
    ('(a)/(|b)', '(a|)/(b)'),
    ('(|a)/()', '|a'),
    ('(|a)/(b)', '|(a)/(b)'),
    ('2sqrt(|x+1)', '2(|x+1)'),
    ('a-sqrt(|x+1)', 'a-(|x+1)'),
    ('sqrt(|x+1)', '|x+1'),
    ('sqrt(|x)', '|x'),
    ('sin(|x)', '|x'),
    ('sin(|)', '|'),
    ('f(|a,b)', '|f(a,b)'),
    ('surd(8,|3)', '|surd(8,3)'),
    ('f(a,|b)', 'f(a|b)'),
    ('integrate(f,x,0,|1)', 'integrate(f,x,0|,1)'),
    ('integrate(f,x,|0,1)', '|integrate(f,x,0,1)'),
    ('(|a+b)', '|a+b'),
    ('x+pi|', 'x+|'),
    ('12|', '1|'),
    ('sqrt()|', '|'),
    ('sqrt(x)|', 'sqrt(x|)'),
    ('x^(2)|', 'x^(2|)'),
    ('(a+b)|', '(a+b|)'),
    ('sin(x)|', 'sin(x|)'),
    ('x+1)|', 'x+1|'),
    # the undecided cases of section 4.3
    ('|x^(2)', '|x^(2)'),
    ('x|^(2)', '|^(2)'),
    ('(|)/(b)', '|()/(b)'),
    ('x^2|', 'x^|'),
    ('x^|', 'x|'),
    ('log(|,8)', 'log(,8|)'),
    ('sqrt(ans()|)', 'sqrt(|)'),
    # more of the same rules
    ('integrate(|x^(2),x)', '|x^(2)'),
    ('diff(f,|x)', '|diff(f,x)'),
    ('diff(|,x)', '|'),
    ('limit(,x,|)', '|'),
    ('(x+1)()|', '(x+1)|'),
    ('sin(x)+1|', 'sin(x)+|'),
    ('(1)/(2)+|', '(1)/(2)|'),
    ('xsqrt(|x+1)', 'x(|x+1)'),
    ('(|a+b', '|a+b'),
    ('riemann(,x,,,)|', '|'),
    ('2(|)', '2|'),
]


@pytest.mark.parametrize('before, after', DELS)
def test_del(before, after):
    assert ed(before, [DEL]) == after


def test_del_never_removes_one_hidden_character():
    rnd = random.Random(11)
    for s in ('(1)/(x^(2)+1)', 'surd(8,3)+sqrt(x)', 'integrate((x)/(2),x,0,1)', 'sum(k^(2),k,1,n)',
              'limit((sin(x))/(x),x,0)', 'abs(x)-log(8,2)', 'e^(x)+10^(y)', 'diff(x^(3),x)'):
        for _ in range(12):
            setline(s + '|')
            for _ in range(rnd.randint(1, 30)):
                U.key(rnd.choice((DEL, DEL, LEFT, RIGHT)))
                m = D.mlayout(U.LINE, 2) if U.LINE else None
                if U.LINE and not D.mflat(U.LINE):
                    assert m is not None, U.LINE
                    assert U.LINE.count('(') == U.LINE.count(')'), U.LINE


# -- section 4.4: up and down -----------------------------------------------------------------

VERT = [
    ('(a|)/(b)', DOWN, '(a)/(b|)'),
    ('(1+(x|)/(2))/(3)', DOWN, '(1+(x)/(2|))/(3)'),
    ('x^(2|)', DOWN, 'x|^(2)'),
    ('x|^(2)', DOWN, 'x|^(2)'),
    ('x|^(2)', UP, 'x^(|2)'),
    ('(a)/(b|)', UP, '(a|)/(b)'),
    ('sum(|f,k,1,n)', DOWN, 'sum(f,k,1|,n)'),
    ('x+1|', DOWN, 'x+1|'),
]


@pytest.mark.parametrize('before, k, after', VERT)
def test_up_down(before, k, after):
    assert ed(before, [k]) == after
    assert U.MODE == 0


def test_up_down_in_integral_and_sum():
    setline('integrate(f|,x,a,b)')
    U.key(DOWN)
    assert 14 <= U.CUR <= 15                    # in the lower bound a
    setline('integrate(f|,x,a,b)')
    U.key(UP)
    assert 16 <= U.CUR <= 17                    # in the upper bound b
    setline('sum(|f,k,1,n)')
    U.key(UP)
    assert 10 <= U.CUR <= 11                    # in b


@pytest.mark.parametrize('s, i', [('(a)/(b)', 2), ('x^(2)', 4), ('surd(8,3)', 6),
                                  ('integrate(f,x,a,b)', 11), ('sum(f,k,1,n)', 5)])
def test_down_then_up_returns_to_the_slot(s, i):
    setline(s[:i] + '|' + s[i:])
    m = U.EDMAP
    U.key(33)
    row = U.EDMAP[10][U.EDMAP[9][U.CUR]]
    U.key(DOWN)
    moved = U.CUR
    U.key(UP)
    if moved != i:
        back = U.EDMAP[10][U.EDMAP[9][U.CUR]]
        assert back[:2] == row[:2], (s, moved, U.CUR)
    del m


def test_up_without_a_candidate_and_no_history_does_nothing():
    assert ed('x^(2|)', [UP]) == 'x^(2|)' and U.MODE == 0


# -- section 3: templates, prefill and the picker ---------------------------------------------

PICKS = [
    ([SECOND, FRAC, ENTER], '(|)/()'),
    ([SECOND, FRAC, 92], '(|)/()'),
    ([SECOND, FRAC, 93], '^(|)'),
    ([SECOND, FRAC, 94], 'sqrt(|)'),
    ([SECOND, FRAC, 82], 'surd(|,)'),
    ([SECOND, FRAC, 83], 'e^(|)'),
    ([SECOND, FRAC, 84], '10^(|)'),
    ([SECOND, FRAC, 72], 'log(,|)'),
    ([SECOND, FRAC, RIGHT, 92], 'abs(|)'),
    ([SECOND, FRAC, RIGHT, 93], 'integrate(|,x)'),
    ([SECOND, FRAC, RIGHT, 94], 'integrate(,x,|,)'),
    ([SECOND, FRAC, RIGHT, 82], 'diff(|,x)'),
    ([SECOND, FRAC, RIGHT, 83], 'sum(,k,|,)'),
    ([SECOND, FRAC, RIGHT, 84], 'limit(,x,|)'),
    ([SECOND, FRAC, DOWN, DOWN, ENTER], 'sqrt(|)'),
    ([SECOND, FRAC, UP, ENTER], 'limit(,x,|)'),
    ([SECOND, FRAC] + [DOWN] * 7 + [ENTER], 'abs(|)'),
    ([SECOND, FRAC, RIGHT, LEFT, 92], '(|)/()'),
]


@pytest.mark.parametrize('keys, after', PICKS)
def test_picker_rows(keys, after):
    TS.load(keys[2:])
    U.key(SECOND)
    U.key(FRAC)
    assert shown() == after
    assert U.R is None and U.FULL is False


def test_picker_captures_a_term_and_closes():
    setline('x+2|')
    TS.load([92])
    U.key(SECOND)
    U.key(FRAC)
    assert shown() == 'x+(2)/(|)'
    for close in (CLEAR, 11, FRAC):
        setline('x|')
        TS.load([88, 95, 102, close])                   # ignored keys, digit 0, then close
        U.key(SECOND)
        U.key(FRAC)
        assert shown() == 'x|'
    TS.load([RIGHT, 72, 74, 92])                        # page 2 has no row 7; 9 is ignored
    setline('|')
    U.key(SECOND)
    U.key(FRAC)
    assert shown() == 'abs(|)'


def test_picker_screen_fits():
    TS.load([DOWN, RIGHT, CLEAR])
    U.key(SECOND)
    U.key(FRAC)
    assert TD.OFFSCREEN == [] and TD.OVERDRAW == []


def test_prefill_in_menub_insertion():
    import menub as MB
    import run as R
    U.R = R
    R.need('menu')
    cat = R.need('cat').CAT
    rows = {}
    for row in cat:
        rows[row[0]] = row
    for sig, text, offset in (('sin(x)', 'sin()', 4), ('surd(x,n)', 'surd(,)', 5),
                              ('purge(x,...)', 'purge()', 6),
                              ('paramarea(x,y,t,a,b)', 'paramarea(,,,,)', 10),
                              ('diff(f,x,[n])', 'diff(,x)', 5), ('sum(f,k,a,b)', 'sum(,k,,)', 4),
                              ('integrate(f,x,[a,b])', 'integrate(,x)', 10),
                              ('limit(f,x,a,[dir])', 'limit(,x,)', 6),
                              ('riemann(f,x,a,b,n,[method])', 'riemann(,x,,,)', 8),
                              ('arclen(f,x,a,b)', 'arclen(,x,,)', 7),
                              ('taylor(f,x=a,[n])', 'taylor(,)', 7),
                              ('solve(eq,[x])', 'solve()', 6)):
        if sig in rows:
            got = MB.insertion(rows[sig])
            assert got[0] == text and got[2] == offset, (sig, got)


# -- section 2.2: ENTER and the empty-slot check ----------------------------------------------

def test_enter_stage_one_needs_no_engine():
    for before, pos in (('(1)/(|)', 5), ('diff(,x)|', 5), ('sqrt()|', 5), ('x^()|', 3),
                        ('x^(2)+|', 6), ('sum(,k,,)|', 7), ('integrate(,x,,)|', 13)):
        setline(before)
        U.key(ENTER)
        assert U.CUR == pos and U.STATUS == 'fill in the empty slot', before
        assert U.R is None


def test_enter_on_a_degraded_line_reports_the_slot_without_layout():
    real = D.mlayout
    calls = []

    def counted(s, mode):
        calls.append(s)
        return real(s, mode)
    D.mlayout = counted
    try:
        for line, pos in (('x^()', 3), ('2/()', 3), ('()/(2)', 1), ('(1)/()+x^()', 5)):
            U.LINE, U.CUR, U.EFAIL, U.EMODEL, U.STATUS = line, len(line), line, None, ''
            U.key(ENTER)
            assert U.CUR == pos and U.STATUS == 'fill in the empty slot', line
            assert calls == [] and U.EFLAT and U.R is None
    finally:
        D.mlayout = real


def test_session_enter_cases():
    s = KS.run('diff(,x){enter}')
    assert 'run' not in s.mods and s.mods['ui'].CUR == 5 and not s.hist
    s = KS.run('1{frac}{enter}')
    assert 'run' not in s.mods and s.mods['ui'].CUR == 5
    s = KS.run('{2nd,frac}7{right}8{enter}')
    assert s.hist[0][0] == 'log(8)' and s.hist[0][2] == 'ans'
    s = KS.run('1{frac}4{right}+x^3+1{enter}')
    assert s.hist[0][0] == '1/4+x^3+1'


def test_log_base_skip_in_stage_two():
    for line, pos in (('log(8,)', -1), ('log(,8)', 4), ('log(8,)+f(,)', 10), ('sin(1,)', 6),
                      ('log(8,2,)', 8)):
        U.LINE = line
        assert U.empty_slot() == pos, line


# -- section 7.4: recall, paste and ENTRY ------------------------------------------------------

def test_entry_recall_restructures():
    s = KS.run('1{frac}4{enter}{2nd,enter}')
    u = s.mods['ui']
    assert s.hist[0][0] == '1/4' and u.LINE == '(1)/(4)' and u.CUR == 7
    s = KS.run('x^2+1{enter}2{enter}{2nd,enter}{2nd,enter}')
    assert s.mods['ui'].LINE == 'x^(2)+1'
    s = KS.run('2+3{enter}{2nd,enter}')
    assert s.mods['ui'].LINE == '2+3'


def test_history_paste():
    s = KS.run('2/3{enter}x^{up}{enter}')
    assert s.mods['ui'].LINE == 'x^(2/3)'
    s = KS.run('2/3{enter}x+{up}{enter}')
    assert s.mods['ui'].LINE == 'x+(2/3)'
    s = KS.run('1{frac}4{enter}{up}{2nd,enter}')
    u = s.mods['ui']
    assert u.LINE == '(1)/(4)' and u.MODE == 0
    s = KS.run('2/3{enter}{frac}{up}{enter}')       # bare into the empty numerator
    assert s.mods['ui'].LINE == '(2/3)/()' and s.mods['ui'].CUR == 4
    s = KS.run('2/3{enter}1{frac}{up}{up}{enter}')  # wrapped, at the numerator's start
    assert s.mods['ui'].LINE == '((2/3)1)/()'


def test_up_leaves_the_line_for_history_only_without_a_candidate():
    s = KS.run('5{enter}1{frac}2{up}')
    u = s.mods['ui']
    assert u.MODE == 0 and u.LINE == '(1)/(2)' and u.CUR == 2
    s = KS.run('5{enter}1{frac}2{up}{up}')
    assert s.mods['ui'].MODE == 1
    s = KS.run('5{enter}1{frac}2{2nd,up}')
    assert s.mods['ui'].MODE == 1


# -- menus: PENDING and the TEST leave rule ----------------------------------------------------

def test_menu_insertion_puts_the_caret_in_the_first_empty_slot():
    for script, line, cur in (('{math}{enter}', 'diff(,x)', 5),
                              ('{math}{down}{enter}', 'integrate(,x)', 10),
                              ('{math}{down}{down}{enter}', 'limit(,x,)', 9),
                              ('{2nd,0}su{enter}', 'sum(,k,,)', 7),
                              ('x^(2{math}{down}{enter}', 'x^(2integrate(,x))', 14),
                              ('{math}{down}{enter}x{2nd,right}', 'integrate(x,x)', 14),
                              ('{2nd,0}sin{enter}', 'sin()', 4)):
        s = KS.run(script)
        u = s.mods['ui']
        assert (u.LINE, u.CUR) == (line, cur), script
        assert u.PENDING is None


def test_test_relation_leaves_a_hidden_slot():
    s = KS.run('x^(2{2nd,math}1')
    assert s.mods['ui'].LINE == 'x^(2)='
    s = KS.run('1{frac}2=3')
    assert s.mods['ui'].LINE == '(1)/(2)=3'


# -- the 256 limit -----------------------------------------------------------------------------

def test_input_limit():
    for script in ('x' * 256 + '+', 'x' * 253 + '{frac}', 'x' * 254 + '{2nd,sq}',
                   'x' * 254 + '{x^n}', 'x' * 256 + '{(}'):
        s = KS.run(script)
        u = s.mods['ui']
        assert u.STATUS == 'Input limit: 256 characters', script
        assert len(u.LINE) <= 256 and u.LINE.startswith('x' * 250)
    s = KS.run('x' * 250 + '{frac}')
    assert s.mods['ui'].LINE == '(' + 'x' * 250 + ')/()'


# -- panic and the model -----------------------------------------------------------------------

def test_panic_resets_the_editor_and_never_retries_the_layout(monkeypatch):
    s = KS.run('1{frac}2{right}+x^3')
    u, d = s.mods['ui'], s.mods['draw']
    assert u.EDMAP is not None and u.EDMAP[0] == u.LINE
    line = u.LINE
    TD.reset()
    u.panic(0)
    assert u.EFAIL == line and u.EDMAP is None and u.EMODEL is None and u.EH == 20
    assert u.PENDING is None and u.EFLAT and u.LINE == line
    calls = []
    real = d.mlayout

    def failing(*a):
        calls.append(a)
        raise MemoryError('layout')
    monkeypatch.setattr(d, 'mlayout', failing)
    u.key(LEFT)                                  # the failing line is edited flat
    assert calls == [] and u.EFLAT and u.CUR == len(line) - 2
    u.key(93)                                    # a text change retries the layout once
    assert len(calls) == 1 and u.ED1D and u.EFLAT and u.EDMAP is None
    u.key(93)
    assert len(calls) == 2
    monkeypatch.setattr(d, 'mlayout', real)
    u.key(DEL)
    assert u.EDMAP is not None and not u.EFLAT and not u.ED1D


def test_panic_reason_one_keeps_the_layout():
    s = KS.run('1{frac}2')
    u = s.mods['ui']
    u.panic(1)
    assert u.EFAIL is None
    u.key(26)
    assert u.EDMAP is not None


def test_layout_caps_degrade_to_flat():
    U.LINE, U.CUR, U.EMODEL = '(1)/(2)+' * 20 + '1', 0, None
    U.key(33)
    assert len(U.LINE) > 160 and U.EFLAT and U.EDMAP is None
    U.key(RIGHT)
    assert U.CUR == 1


def test_model_is_fresh_after_every_key():
    rnd = random.Random(5)
    keys = [92, 93, PLUS, MINUS, FRAC, POW, SQ, LP, RP, COMMA, DEL, LEFT, RIGHT, UP, DOWN, 32]
    for _ in range(40):
        setline('|')
        for _ in range(25):
            U.key(rnd.choice(keys))
            assert U.EMODEL == (U.LINE, U.CLASSIC)
            assert U.EFLAT == (U.EDMAP is None)
            if U.EDMAP is not None:
                assert U.EDMAP[0] == U.LINE and U.EDMAP[5][U.CUR] >= 0
            else:
                assert D.mstop(U.LINE, U.CUR)
            assert U.MODE == 0 and len(U.LINE) <= 256


# -- section 8: Classic --------------------------------------------------------------------------

def test_classic_is_the_old_editor():
    U.CLASSIC = True
    assert ed('x|', [FRAC, 93]) == 'x/2|'
    assert ed('x|', [POW, 93]) == 'x^2|'
    assert ed('x|', [SQ]) == 'x^2|'
    assert ed('|', [52, 32]) == 'sin(x|'
    assert ed('(a)/(b|)', [RIGHT, DEL, DEL]) == '(a)/(|'
    assert ed('x|', [SECOND, POW]) == 'xsurd(|'
    assert ed('x|', [SECOND, FRAC]) == 'x|'
    assert U.EDMAP is None and U.EFLAT


def test_classic_toggle_rebuilds_the_model():
    setline('(1)/(2|)')
    U.key(33)
    assert U.EDMAP is not None
    U.CLASSIC = True
    U.key(33)
    assert U.EDMAP is None and U.EFLAT
    U.CLASSIC = False
    U.key(33)
    assert U.EDMAP is not None and not U.EFLAT


def test_setup_row_toggles_classic():
    s = KS.run('{f3}' + '{down}' * 5 + '{enter}{clear}1{frac}2')
    u = s.mods['ui']
    assert u.CLASSIC and u.LINE == '1/2'
    s = KS.run('{f3}6{right}{clear}1{frac}2')
    assert s.mods['ui'].CLASSIC is False and s.mods['ui'].LINE == '(1)/(2)'
    s = KS.run('{f3}' + '{down}' * 4 + '{enter}{snap:about}{clear}{clear}')
    assert 'Free heap' in s.snap('about') and s.mods['ui'].CLASSIC is False


# -- typed MathPrint input evaluates like the 1D text -------------------------------------------

def micro_cases():
    spec = importlib.util.spec_from_file_location('micro_smoke', os.path.join(ROOT, 'build',
                                                                               'micro_smoke.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.UI_CASES


def test_micro_smoke_stream_types_the_same_input():
    # the native ui_calculus suite's own key stream (build/micro_smoke.py, regenerated from
    # keyscript): every command is typed back to its text and gives the asserted answer
    cases = micro_cases()
    script = ''.join(command + '{enter}' for command, _ in cases) + '{2nd,mode}'
    s = KS.run(script)
    assert s.ended == 'quit'
    assert [e[0] for e in s.hist] == [c for c, _ in cases]
    assert [e[1] for e in s.hist] == [w for _, w in cases]


def test_typed_text_round_trips():
    rnd = random.Random(3)
    atoms = ['x', 'y', '2', '13', 'sin(x)', 'pi', '(x+1)', 'ln(2)', 'sqrt(5)', 'e^(x)']
    ops = ['+', '-', '*', '/', '=']
    for _ in range(60):
        parts = [rnd.choice(atoms)]
        for _ in range(rnd.randint(0, 4)):
            parts.append(rnd.choice(ops))
            a = rnd.choice(atoms)
            if rnd.random() < 0.3 and '^' not in a:
                a += '^' + rnd.choice(('2', '3', 'n', '(k+1)'))
            parts.append(a)
        text = ''.join(parts)
        s = KS.run(text)
        u = s.mods['ui']
        assert u.tidy(u.LINE) == u.tidy(text), (text, u.LINE)
        if '^' not in text:
            assert u.LINE == text


def test_arrows_do_no_layout():
    # section 10: caret moves reuse the caret map; only a text change lays the line out again
    s = KS.run('1{frac}2{right}+x^3')
    u, d = s.mods['ui'], s.mods['draw']
    calls = []
    real = (d.mlayout, d.mparse)

    def lay(*a):
        calls.append('mlayout')
        return real[0](*a)

    def parse(*a):
        calls.append('mparse')
        return real[1](*a)
    d.mlayout, d.mparse = lay, parse
    try:
        for k in (24, 26, 25, 34, 24, 24, 34, 25, 21, 24, 21, 26):
            u.key(k)
        assert calls == []
        u.key(92)
        assert calls == ['mlayout', 'mparse']
    finally:
        d.mlayout, d.mparse = real
