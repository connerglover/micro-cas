"""Modal menus use real keys and preserve session state until local confirmation."""
import pytest
import ti_draw as TD
import ti_system as TS
import draw as D
import run as R
import ui as U
import cascheck as C


@pytest.fixture(autouse=True)
def session(monkeypatch):
    C.fresh()
    # menu and menub read the engine from U.R (ui.engine() binds it in the application)
    monkeypatch.setattr(U, 'R', R)
    TD.reset()
    D.reset()


def menu(kind, keys, command=''):
    m = R.need('menu')
    TS.load(keys)
    return m.open(kind, '', 0, command)


def test_test_picker():
    assert menu('test', [93])[0] == '!='
    assert menu('test', [26, 26, 105])[0] == '<'
    assert menu('test', [45]) is None


def test_calculus_template():
    result = menu('calculus', [105])
    assert result[0].startswith('diff(') and result[1]
    assert result[0][result[2]] in ',)'


def test_vars_ans_and_variables():
    C.answer('2/3')
    R.VARS['a'] = '5'
    assert menu('vars', [105])[0] == 'ans()'
    assert menu('vars', [34, 105])[0] == 'a'
    R.HIST.append(['1+1', '2', R.R_ANS, None, 0, []])
    assert menu('vars', [34, 34, 45]) is None
    assert '1+1' not in TD.screen_text()              # history rows scroll on the page now


def test_setup_angle():
    menu('setup', [105, 26, 26, 45])
    assert R.SET == {'deg': 1}                        # ENTER, then the arrows toggle it twice
    menu('setup', [34, 26, 45])                       # arrows on another row do nothing
    assert R.SET == {'deg': 1} and 'Clear history?' not in TD.screen_text()


def test_help_example():
    result = menu('help', [105], 'diff')
    assert result[0].startswith('diff(') and not result[1]


def test_catalog_every_command_and_macro():
    cat = R.need('cat').CAT
    names = [row[1].rstrip('(') for row in cat]
    assert set(R.CMDS) | set(R.MACROS) <= set(names)
    assert all(len(row) == 5 and all(row) for row in cat)


@pytest.mark.parametrize('kind, keys, command', [
    ('algebra', [34, 34, 26, 31, 52, 45], ''), ('all', [34] * 8 + [45], ''),
    ('vars', [45], ''), ('setup', [34, 34, 34, 105, 45, 45], ''),
    ('setup', [34, 105, 45, 45], ''), ('setup', [34, 34, 105, 45, 45], ''),
    ('test', [45], ''), ('help', [45], 'integrate'), ('help', [45], 'riemann'),
    ('help', [45], ''), ('trig', [45], '')])
def test_menu_screens_fit_the_screen(kind, keys, command):
    C.answer('2/3')
    R.VARS['a'] = '5'
    menu(kind, keys, command)
    assert TD.OFFSCREEN == [] and TD.OVERDRAW == []
    for call in TD.CALLS:
        if call[0] == 'draw_text':
            assert len(call[3]) <= 31 and all(32 <= ord(ch) < 127 for ch in call[3]), call
    assert set(TD.COUNTS) <= {'set_color', 'fill_rect', 'draw_text', 'draw_line'}


def test_menu_shows_the_selected_explanation():
    TS.load([34, 45])
    R.need('menu').open('calculus')
    screen = TD.screen_text()
    row = [r for r in R.need('cat').CAT if 'C' in r[4]][1]
    assert '>2 ' + row[0] in screen and row[2][:20] in screen


def test_about_shows_boot_and_engine_times(monkeypatch):
    monkeypatch.setattr(U, 'BOOT_MS', 420)
    monkeypatch.setattr(U, 'ENGINE_MS', 3150)
    TS.load([34, 34, 34, 105])
    with pytest.raises(TS.StopScript):
        R.need('menu').open('setup')
    assert 'Boot 0.4s, engine 3.1s' in TD.screen_text()


def row(sig):
    """The catalog row of a command, by its signature's name (sin(x) is the row of sin()."""
    for r in R.need('cat').CAT:
        if r[1] == sig.split('(')[0] + '(':
            return r
    raise KeyError(sig)


def test_insertion_has_empty_boxes_and_no_prefill():
    # MATHPRINT.md 3 and 0.10: no parameter is prefilled; a command with a template inserts
    # the picker's text (all its boxes, optional ones too), any other one box per required one
    R.need('menu')
    mb = R.MODS['menub']
    assert mb.insertion(row('sin(x)')) == ('sin()', False, 4)
    assert mb.insertion(row('purge(x,...)'))[0] == 'purge()'
    assert mb.insertion(row('paramarea(x,y,t,a,b)'))[0] == 'paramarea(,,,,)'
    assert mb.insertion(row('diff(f,x,[n])'))[0] == 'diff(,)'
    assert mb.insertion(row('sum(f,k,a,b)'))[0] == 'sum(,,,)'
    assert mb.insertion(row('limit(f,x,a,[dir])'))[0] == 'limit(,,,)'
    assert mb.insertion(row('integrate(f,x,[a,b])'))[0] == 'integrate(,,,)'
    assert mb.insertion(row('log(x,[b])'))[0] == 'log(,)'
    assert mb.insertion(row('taylor(f,x=a,[n])'))[0] == 'taylor(,,)'     # QPL Q4: the order box
    assert mb.insertion(row('surd(x,n)'))[0] == 'surd(,)'


def test_setup_rows():
    TS.load([45])
    R.need('menu').open('setup')
    shown = TD.screen_text()
    assert 'Angle: RAD' in shown and 'About cas-evo' in shown
    assert 'Theme' not in shown and 'Entry' not in shown
    TS.load([34, 34, 34, 105])                        # row 4 opens About
    with pytest.raises(TS.StopScript):
        R.need('menu').open('setup')
    assert 'Free heap' in TD.screen_text() and 'cas-evo 1.0.0' in TD.screen_text()
