"""v1.0.0: the F-key row and its 2nd layer (docs/notes/MATHPRINT.md 0.13, docs/notes/UI.md).

Plain F1-F4 open the catalog on the Algebra, Calculus, Trig and More tabs; F5 cycles the
focused answer's forms (as the < > key 95). With the 2nd chip lit the row relabels to the 2nd
layer: 2nd F1 the All tab, 2nd F2 the template picker, 2nd F3 the TEST picker, 2nd F4 Setup,
2nd F5 the help of the command at the caret. The row repaints only when the layer changes.
The math key opens the catalog on the last tab used (Algebra at first); tabs switched inside
the menu count. The history scrolls with UP from the entry (F2 no longer enters it).
"""
import pytest

import keyscript as KS
import ti_draw as TD

PLAIN = ['Alg', 'Calc', 'Trig', 'More', 'Forms']
SECOND = ['All', 'Tmpl', 'Test', 'Setup', 'Help']


def ui(s):
    return s.mods['ui']


def row(texts):
    """The F-key labels drawn at y 193, left to right."""
    return [t[2] for t in sorted(t for t in texts if t[1] == 193)]


def title(snap):
    return snap.split('\n')[0].strip()


def tabfills(calls):
    return [c for c in calls if c[0] == 'fill_rect' and c[2] >= 190]


# -- the labels ----------------------------------------------------------------------------------

def test_plain_row_labels():
    s = KS.run('')
    assert row(s.texts) == PLAIN
    assert all(len(t) <= 6 for t in PLAIN + SECOND)        # 63 px tabs, 10 px a character
    for t in s.texts:
        if t[1] == 193:
            i = t[0] // 64
            assert t[0] == 64 * i + (63 - 10 * len(t[2])) // 2


def test_second_relabels_the_row_and_toggles_back():
    s = KS.run('{2nd}')
    assert ui(s).MOD == 1 and row(s.texts) == SECOND
    s = KS.run('{2nd}{2nd}')
    assert row(s.texts) == PLAIN
    s = KS.run('{2nd}{right}')                              # the 2nd key is used up
    assert ui(s).MOD == 0 and row(s.texts) == PLAIN
    assert s.overdraw == [] and s.offscreen == []


@pytest.mark.parametrize('keys', ['{alpha}', '{alpha}{alpha}', '{2nd}{alpha}',
                                  '{2nd}{alpha}{2nd}'])
def test_alpha_modes_keep_the_plain_row(keys):
    s = KS.run(keys)
    assert ui(s).MOD >= 2 and row(s.texts) == PLAIN


def test_row_repaints_only_when_the_layer_changes():
    s = KS.run('2/3{enter}1+')
    u = ui(s)
    TD.reset()
    u.key(92)                                               # typing: no tab repaint
    assert tabfills(TD.CALLS) == [] and row(TD.texts()) == []
    TD.reset()
    u.key(21)                                               # 2nd: one fill and the labels
    assert tabfills(TD.CALLS) == [('fill_rect', -1, 192, 320, 16)]
    assert row(TD.texts()) == SECOND
    assert sum(1 for c in TD.CALLS if c[0] == 'draw_line') == 4  # the gaps between tabs
    assert TD.OVERDRAW == []
    TD.reset()
    u.key(31)                                               # 2nd -> alpha: back to plain
    assert len(tabfills(TD.CALLS)) == 1 and row(TD.texts()) == PLAIN
    TD.reset()
    u.key(31)                                               # alpha -> a-lock: same layer
    assert tabfills(TD.CALLS) == [] and row(TD.texts()) == []
    assert TD.OVERDRAW == []


def test_gaps_between_tabs_stay_background():
    s = KS.run('{2nd}')
    bg = s.mods['draw'].COLORS['BG']
    soft = s.mods['draw'].COLORS['ACCSOFT']
    for x in (63, 127, 191, 255, 319):
        assert TD.pixel(x, 200) == bg
        assert TD.pixel(x - 1, 200) == soft
        assert x == 319 or TD.pixel(x + 1, 200) == soft


# -- plain F1-F4: the catalog tabs ------------------------------------------------------------

@pytest.mark.parametrize('key, name', [('f1', 'Algebra'), ('f2', 'Calculus'), ('f3', 'Trig'),
                                       ('f4', 'More')])
def test_plain_f1_to_f4_open_the_catalog_tabs(key, name):
    s = KS.run('{' + key + '}{snap:menu}{clear}')
    assert title(s.snap('menu')) == name
    assert ui(s).TAB == ['Algebra', 'Calculus', 'Trig', 'More'].index(name)
    assert ui(s).MODE == 0 and row(s.texts) == PLAIN


def test_alpha_f_key_acts_on_the_plain_layer():
    s = KS.run('{alpha}{f2}{snap:menu}{clear}')
    assert title(s.snap('menu')) == 'Calculus'


# -- 2nd F1-F5 ------------------------------------------------------------------------------------

def test_second_f1_opens_the_all_tab_with_alpha_find():
    s = KS.run('{2nd,f1}{snap:all}{alpha}s{snap:find}{clear}')
    assert title(s.snap('all')) == 'All'
    assert title(s.snap('find')) == 'All / s'


def test_second_f2_is_the_template_picker():
    s = KS.run('{2nd,f2}{snap:picker}{clear}')
    assert title(s.snap('picker')).startswith('Templates')
    assert 'run' not in s.mods                              # engine-free, as 2nd + fraction
    a = KS.run('{2nd,f2}{down}{down}{enter}x')
    b = KS.run('{2nd,frac}{down}{down}{enter}x')
    assert ui(a).LINE == ui(b).LINE == 'sqrt(x)'


def test_second_f3_is_the_test_picker():
    s = KS.run('x{2nd,f3}{snap:test}{down}{enter}2')
    assert title(s.snap('test')) == 'TEST'
    assert ui(s).LINE == 'x!=2'


def test_second_f4_is_setup():
    s = KS.run('{2nd,f4}{snap:setup}{clear}')
    assert title(s.snap('setup')) == 'Setup'
    s = KS.run('{2nd,f4}{enter}{clear}')
    assert s.mods['run'].SET['deg'] == 1


def test_second_f5_is_help_for_the_command_at_the_caret():
    s = KS.run('diff({2nd,f5}{snap:help}{enter}')
    assert title(s.snap('help')) == 'Help'
    assert 'diff(x^3,x,2)' in ui(s).LINE
    s = KS.run('{2nd,f5}{snap:tips}{clear}')
    assert 'F1-F4 menu tabs, F5 forms' in s.snap('tips')


# -- F5 and < >: the answer's forms --------------------------------------------------------------

def test_f5_cycles_the_answer_forms_like_the_switch_key():
    a, b = KS.run('1{frac}4{enter}{<>}'), KS.run('1{frac}4{enter}{f5}')
    assert a.mods['run'].HIST == b.mods['run'].HIST
    assert b.mods['run'].HIST[0][5][-1] == ('decimal', '0.25')
    s = KS.run('sqrt(2){enter}{f5}{f5}')
    assert s.mods['run'].HIST[0][5] == [] or s.mods['run'].HIST[0][5][-1][0] == 'exact'


def test_f5_acts_on_the_selected_answer():
    s = KS.run('1{frac}4{enter}1{frac}2{enter}{up}{up}{f5}')
    h = s.mods['run'].HIST
    assert h[0][5][-1] == ('decimal', '0.25') and not h[1][5]


def test_f5_without_an_answer_does_nothing():
    s = KS.run('{f5}')
    assert 'run' not in s.mods and 'menu' not in s.mods
    assert ui(s).LINE == '' and ui(s).MODE == 0
    s = KS.run('x+1{f5}')
    assert ui(s).LINE == 'x+1' and 'run' not in s.mods
    s = KS.run('{<>}')
    assert 'run' not in s.mods and ui(s).LINE == ''


# -- math: the last tab used -----------------------------------------------------------------------

def test_math_opens_algebra_first():
    s = KS.run('{math}{snap:menu}{clear}')
    assert title(s.snap('menu')) == 'Algebra'


def test_math_remembers_the_f_key_tab():
    s = KS.run('{f3}{clear}{math}{snap:menu}{clear}')
    assert title(s.snap('menu')) == 'Trig'


def test_math_remembers_a_tab_switched_inside_the_menu():
    s = KS.run('{math}{right}{right}{clear}{math}{snap:menu}{clear}')
    assert title(s.snap('menu')) == 'Trig' and ui(s).TAB == 2
    s = KS.run('{f1}{left}{clear}{math}{snap:menu}{clear}')    # wraps to All
    assert title(s.snap('menu')) == 'All'
    s = KS.run('{f2}{right}{enter}')                          # a pick from the switched tab
    assert ui(s).TAB == 2


def test_second_math_vars_mode_and_second_zero_are_unchanged():
    assert title(KS.run('{2nd,math}{snap:m}{clear}').snap('m')) == 'TEST'
    assert title(KS.run('{vars}{snap:m}{clear}').snap('m')) == 'Vars'
    assert title(KS.run('{mode}{snap:m}{clear}').snap('m')) == 'Setup'
    assert title(KS.run('{2nd,0}{snap:m}{clear}').snap('m')) == 'All'
    assert KS.run('{2nd,mode}').ended == 'quit'


# -- the history scrolls with UP, not F2 ------------------------------------------------------------

def test_up_scrolls_the_history_and_clear_or_down_leaves():
    s = KS.run('1+1{enter}2+3{enter}{up}')
    assert ui(s).MODE == 1 and ui(s).SEL == 1 and ui(s).SELC == 1
    s = KS.run('1+1{enter}2+3{enter}{up}{up}')
    assert ui(s).SEL == 0
    assert ui(KS.run('1+1{enter}{up}{clear}')).MODE == 0
    assert ui(KS.run('1+1{enter}{up}{down}')).MODE == 0


def test_f2_no_longer_enters_the_history():
    s = KS.run('1+1{enter}{f2}{snap:menu}{clear}')
    assert title(s.snap('menu')) == 'Calculus' and ui(s).MODE == 0


# -- review: the partial repaint leaves the screen a full redraw would draw -------------------------

@pytest.mark.parametrize('keys, extra', [
    ('', (21,)), ('', (21, 21)), ('1+1{enter}', (21,)), ('1+1{enter}', (21, 31)),
    ('1+1{enter}{up}', (21,)), ('1+1{enter}{up}', (21, 25)), ('{2nd,f1}{clear}', (21,)),
    ('{2nd,f2}{clear}', (21, 21)), ('x', (21, 24)), ('{alpha}{alpha}', (21, 21)),
    ('1+1{enter}', (21, 45))])
def test_partial_tab_repaint_matches_a_full_redraw(keys, extra):
    s = KS.run(keys)
    u = ui(s)
    for k in extra:
        u.key(k)
    fb, texts = [r[:] for r in TD.FB], sorted(TD.texts())
    assert row(texts) == (SECOND if u.MOD == 1 else PLAIN) and TD.OVERDRAW == []
    u.FULL = True
    u.redraw()
    assert TD.FB == fb and sorted(TD.texts()) == texts
