"""MathPrint milestone C: the screen (docs/notes/MATHPRINT.md sections 6, 7, 10, 12.7, 12.8).

The rows move with the entry height (EY = 190 - EH); the entry is painted by a full row (flat
lines), a 2 px caret strip (a caret move on a 2D line) or a dirty-region diff (a text change on
a 2D line), and each of them must leave exactly the pixels a full repaint leaves (12.7). The
status and hint rows repaint only when what they show changes. The history page draws every
input through the engine-free mode-1 layout, the result right-aligned, the selection as a band.
"""
import random

import pytest

import draw as D
import keyscript as KS
import ti_draw as TD
import ui as U

SECOND, DEL, LEFT, UP, RIGHT, DOWN = 21, 23, 24, 25, 26, 34
FRAC, POW, SQ, COMMA, LP, RP, DIV, MUL = 42, 51, 61, 62, 63, 64, 55, 65
MINUS, PLUS, ENTER, CLEAR = 75, 85, 105, 45

STATE = (('LINE', ''), ('CUR', 0), ('XOFF', 0), ('MOD', 0), ('MODE', 0), ('SEL', -1),
         ('HERO', True), ('DX', 0), ('ENTRYPOS', -1), ('LASTENTRY', ''), ('STATUS', ''),
         ('NOTE', ''), ('FULL', True), ('VIEW', None), ('EXOFF', 0), ('EH', 20),
         ('EDMAP', None), ('EMODEL', None), ('EFLAT', True), ('PENDING', None),
         ('ED1D', False), ('EFAIL', None), ('VIEWEND', -1),
         ('EDL', None), ('EKEY', None), ('STATVIEW', None), ('HINTVIEW', None),
         ('EDIFF', True), ('CARETC', 'INK'), ('PAGEMAX', 5))


@pytest.fixture
def editor(monkeypatch):
    """A fresh engine-free editor on a fully painted screen."""
    monkeypatch.setattr(D, 'P', None)
    monkeypatch.setattr(D, 'PR', None)
    monkeypatch.setattr(U, 'R', None)
    for name, value in STATE:
        monkeypatch.setattr(U, name, value)
    TD.reset()
    D.reset()
    D.clear_cache()
    U.emodel()
    U.redraw()
    return U


def fills():
    return [c for c in TD.CALLS if c[0] == 'fill_rect']


def count(name):
    return TD.COUNTS.get(name, 0)


def press(keys):
    for k in keys:
        U.key(k)


def entry_pixels():
    ey = 190 - U.EH
    return [list(TD.FB[y]) for y in range(ey, 190)]


def entry_texts():
    ey = 190 - U.EH
    return sorted(TD.texts_in(0, ey, 320, U.EH))


def repaint_entry():
    """The entry as a forced full entry repaint draws it (EDIFF off, no previous entry)."""
    U.EDIFF, U.EKEY = False, None
    U.redraw()
    U.EDIFF = True


# -- 6.1: rows and the entry height ----------------------------------------------------------

def test_rows_at_eh_20_are_todays(editor):
    TD.reset()
    U.FULL = True
    U.redraw()
    lines = [c for c in TD.CALLS if c[0] == 'draw_line']
    assert ('draw_line', 0, 19, 319, 19) in lines and ('draw_line', 0, 169, 319, 169) in lines
    assert ('draw_line', 9, 171, 9, 187) in lines              # the caret, as today
    press([93, PLUS, 94])
    assert ('draw_text', 10, 189, '2+3') in TD.CALLS           # the row at (10, 172)
    assert TD.CALLS[-1] == ('draw_line', 39, 171, 39, 187)


def test_entry_height_grows_by_class_and_costs_one_full_redraw(editor):
    TD.reset()
    press([92, FRAC])                                          # (1)/(|): two rows of text
    assert U.EH == 40
    assert fills().count(('fill_rect', -1, -1, 321, 211)) == 1
    assert ('draw_line', 0, 149, 319, 149) in TD.CALLS         # the rule at EY - 1
    TD.reset()
    press([93, RIGHT, PLUS, 94, 92])                           # linear typing: no full redraw
    assert ('fill_rect', -1, -1, 321, 211) not in fills()
    assert U.EH == 40
    press([DEL] * 4)                                           # never shrinks while non-empty
    assert U.LINE and U.EH == 40
    TD.reset()
    press([CLEAR])
    assert U.LINE == '' and U.EH == 20
    assert ('fill_rect', -1, -1, 321, 211) in fills()


@pytest.mark.parametrize('keys, eh', [
    ([92], 20),
    ([SECOND, SQ, 93], 20),
    ([92, FRAC, 93], 40),
    ([32, POW, 93], 40),
    ([92, FRAC, 92, FRAC, 93], 60),
])
def test_height_classes(editor, keys, eh):
    press(keys)
    assert U.EH == eh
    m = U.EDMAP
    h = 15 if m is None else m[3] + m[4]
    ey = 190 - eh
    ytop = ey + (eh - h) // 2
    assert ey <= ytop and ytop + h <= 190


def test_content_and_caret_are_centred_in_the_box(editor):
    press([92, FRAC, 93])                                      # (1)/(2|)
    m = U.EDMAP
    ey = 190 - U.EH
    ytop = ey + (U.EH - m[3] - m[4]) // 2
    cx = 10 + m[5][U.CUR] - U.EXOFF
    cy = ytop + m[6][U.CUR]
    assert TD.CALLS[-1] == ('draw_line', cx - 1, cy, cx - 1, cy + 14)   # clear of the bar
    assert TD.COLOR == D.COLORS['INK']                         # the caret is INK (CARETC)


# -- 6.3: horizontal scroll ------------------------------------------------------------------

def test_2d_scroll_keeps_the_caret_in_view_and_marks_the_sides(editor):
    for j in range(16):
        press([92, FRAC, 93 + j % 2, RIGHT, PLUS])
    assert U.EXOFF > 0
    x = U.EDMAP[5][U.CUR]
    assert 10 <= 9 + x - U.EXOFF <= 304
    assert any(t[2] == '<' and t[0] == 0 for t in entry_texts())
    press([SECOND, LEFT])
    assert U.EXOFF == 0 and any(t[2] == '>' and t[0] == 310 for t in entry_texts())
    assert not any(t[2] == '<' for t in entry_texts())
    press([SECOND, RIGHT])
    for j in range(40):
        press([DEL])
        if U.EDMAP is not None:
            assert U.EXOFF <= max(0, U.EDMAP[2] - 230)
        x = 9 + (U.EDMAP[5][U.CUR] if U.EDMAP else 10 * (U.CUR - U.XOFF)) - U.EXOFF
        assert 9 <= x <= 304


# -- 6.4: what each key repaints ---------------------------------------------------------------

def test_nothing_changed_draws_nothing(editor):
    press([92, FRAC, 93])
    TD.reset()
    U.redraw()
    assert TD.CALLS == []
    U.key(33)                                                  # a key with no entry
    assert TD.CALLS == []


def test_flat_typing_repaints_the_row_only(editor):
    press([92, PLUS])
    TD.reset()
    U.key(93)
    assert fills() == [('fill_rect', -1, 169, 321, 21)]
    assert count('set_color') <= 2 and count('draw_text') == 1 and count('draw_line') == 1


def test_modifier_repaints_the_status_row_only(editor):
    press([92, FRAC, 93])
    TD.reset()
    U.key(SECOND)               # the F-key row's labels follow the 2nd layer (0.13)
    assert fills() == [('fill_rect', -1, 192, 320, 16), ('fill_rect', -1, -1, 321, 20)]
    assert count('set_color') <= 4
    TD.reset()
    U.key(SECOND)
    assert fills() == [('fill_rect', -1, 192, 320, 16), ('fill_rect', -1, -1, 321, 20)]


def test_2d_typing_cost(editor):
    for k in (92, FRAC, 93, RIGHT, PLUS, 92, FRAC, 94, RIGHT, PLUS):
        U.key(k)
    for k in (82, 83, 84):
        TD.reset()
        U.key(k)
        assert count('set_color') <= 3 and count('fill_rect') == 1, TD.CALLS
        assert count('draw_text') <= 3, TD.CALLS


def test_caret_move_cost_is_flat(editor, monkeypatch):
    for j in range(4):
        press([LP, 92, RP, DIV, LP, (93, 94, 82, 83)[j], RP])
        if j < 3:
            press([PLUS])
    assert U.LINE == '(1)/(2)+(1)/(3)+(1)/(4)+(1)/(5)'
    calls = []
    real = D.mlayout
    monkeypatch.setattr(D, 'mlayout', lambda s, mode: calls.append(s) or real(s, mode))
    for j in range(10):
        del TD.CALLS[:]          # keep the framebuffer
        TD.COUNTS.clear()
        hv = U.HINTVIEW
        U.key(LEFT)
        # the hint row repaints (one fill, one text) only when the slot's help changes (QPL Q5)
        more = int(U.HINTVIEW != hv)
        assert count('fill_rect') == 1 + more, TD.CALLS
        assert count('draw_text') <= 2 + more and count('set_color') <= 3 + 2 * more, TD.CALLS
        pixels, texts = entry_pixels(), entry_texts()
        repaint_entry()
        assert entry_pixels() == pixels and entry_texts() == texts
    assert calls == []


def test_trailing_box_appears_when_the_caret_leaves_it(editor):
    press([92, PLUS])                                          # 1+| : flat, no box
    press([92, FRAC, 93, RIGHT, PLUS])                         # 1+(1)/(2)+|  (2D, box hidden)
    boxes = [i for i in KS.painted(U) if i[0] == 'b']
    assert boxes == []
    press([LEFT])
    assert [i for i in KS.painted(U) if i[0] == 'b']
    pixels, texts = entry_pixels(), entry_texts()
    repaint_entry()
    assert entry_pixels() == pixels and entry_texts() == texts
    press([RIGHT])
    assert not [i for i in KS.painted(U) if i[0] == 'b']
    pixels = entry_pixels()
    repaint_entry()
    assert entry_pixels() == pixels


# -- 12.7: the diff paint equals a full repaint, pixel for pixel ---------------------------------

KEYPOOL = (92, 93, 94, 82, 32, PLUS, MINUS, MUL, DIV, FRAC, POW, SQ, LP, RP, COMMA, DEL,
           LEFT, RIGHT, UP, DOWN, LEFT, RIGHT, DEL, (SECOND, LEFT), (SECOND, RIGHT),
           (SECOND, SQ), (SECOND, POW), 52, 103)
SEEDS = ('(1)/(2)+x^(2)', 'sqrt(x)+(a)/(b)', 'integrate(x,x,0,1)', 'sum(k,k,1,n)+1',
         '(1)/((2)/(3))', 'x^(2)+x^(3)-(1)/(4)', '')


@pytest.mark.parametrize('seed', range(200))
def test_diff_paint_equals_a_full_repaint(editor, seed):
    rnd = random.Random(seed)
    U.LINE = SEEDS[seed % len(SEEDS)]
    U.CUR = len(U.LINE)
    U.EMODEL = None
    U.FULL = True
    U.emodel()
    U.redraw()
    for step in range(16):
        k = rnd.choice(KEYPOOL)
        if isinstance(k, tuple):
            press(k)
        else:
            U.key(k)
        pixels, texts = entry_pixels(), entry_texts()
        repaint_entry()
        assert entry_pixels() == pixels, (seed, step, k, U.LINE, U.CUR)
        assert entry_texts() == texts, (seed, step, k, U.LINE, U.CUR)
    assert TD.OVERDRAW == [] and TD.OFFSCREEN == []


def test_kill_switch_always_repaints_the_whole_entry(editor, monkeypatch):
    monkeypatch.setattr(U, 'EDIFF', False)
    press([92, FRAC, 93, RIGHT, PLUS])
    TD.reset()
    U.key(LEFT)
    ey = 190 - U.EH
    assert ('fill_rect', -1, ey - 1, 321, U.EH + 1) in fills()


# -- 7: the history page ---------------------------------------------------------------------

def stage(s, top=20, bottom=150):
    return [t for t in s.texts if top <= t[1] and t[1] + 15 <= bottom]


def test_history_inputs_are_drawn_2d_and_results_right_aligned():
    s = KS.run('1/2+1/3{enter}x^3{enter}')
    d, u = s.mods['draw'], s.mods['ui']
    sub = d.COLORS['SUB']
    ink = d.COLORS['INK']
    inputs = [t for t in stage(s) if t[3] == sub]
    results = [t for t in stage(s) if t[3] == ink]
    # 1/2+1/3 is stacked: 1 over 2, 1 over 3, with + on the baseline between them
    assert ('1' in [t[2] for t in inputs]) and not any('/' in t[2] for t in inputs)
    assert any(t[2] == 'x' for t in inputs) and any(t[2] == '3' for t in inputs)
    # the answer 5/6 right-aligned: its rightmost cell ends at column 309
    assert max(t[0] + 10 * len(t[2]) for t in results) == 310
    assert len(d.ICACHE) == 2 and len(d.CACHE) == 2
    assert s.offscreen == [] and s.overdraw == []


def test_one_row_when_input_and_result_fit():
    s = KS.run('2+3{enter}')
    sub, ink = s.mods['draw'].COLORS['SUB'], s.mods['draw'].COLORS['INK']
    inp = [t for t in stage(s) if t[3] == sub and t[2] == '2+3'][0]
    res = [t for t in stage(s) if t[3] == ink and t[2] == '5'][0]
    assert inp[0] == 5 and res[0] == 300 and inp[1] == res[1]  # baselines aligned
    assert res[1] + 15 <= 150


def test_two_rows_when_the_result_is_wide():
    s = KS.run('expand((x+1)^6){enter}')
    sub, ink = s.mods['draw'].COLORS['SUB'], s.mods['draw'].COLORS['INK']
    inp = [t for t in stage(s) if t[3] == sub]
    res = [t for t in stage(s) if t[3] == ink]
    assert min(t[1] for t in res) >= max(t[1] for t in inp) + 15


def test_footer_is_in_the_hint_row_and_typing_repaints_only_that_row():
    # the decimal stays in the hint row; the form label is in the status row (top right)
    s = KS.run('sqrt(2){enter}')
    u, d = s.mods['ui'], s.mods['draw']
    assert ('exact' in s.screen) and ('~ 1.414213562' in s.screen) and 'F4' not in s.screen
    foot = [t for t in s.texts if t[2].startswith('~ 1.414')][0]
    assert foot[0] == 5 and foot[1] == 153
    lab = [t for t in s.texts if t[2] == 'exact'][0]
    assert lab[0] == 315 - 50 and lab[1] == 2
    TD.reset()
    u.key(92)
    assert all(c[2] >= 150 or c[2] == -1 and c[4] == 20 for c in fills())
    assert ('fill_rect', -1, 150, 321, 19) in fills()
    assert 'exact' not in TD.screen_text() and '~ 1.414' not in TD.screen_text()
    TD.reset()
    u.key(DEL)                                                  # empty again: the footer
    assert 'exact' in TD.screen_text() and '~ 1.414' in TD.screen_text()
    assert not [c for c in fills() if c[2] < 150 and c[2] != -1]


def test_selection_band_and_scrolling():
    s = KS.run(''.join('%d+%d{enter}' % (j, j) for j in range(1, 9)) + '{up}')
    u, d = s.mods['ui'], s.mods['draw']
    assert u.MODE and u.SEL == 7 and u.VIEWEND == 7
    band = d.COLORS['ACCSOFT']
    for j in range(7):
        TD.reset()
        u.key(UP)
        assert u.SEL == 6 - j
        shown = TD.screen_text(0, 20, 320, 130)
        assert ('%d+%d' % (u.SEL + 1, u.SEL + 1)) in shown
        assert u.SEL <= u.VIEWEND < 8
        # the band sits behind the selected entry's output cell, not its input (v1.0.0)
        sel = [t for t in TD.texts() if t[2] == '%d+%d' % (u.SEL + 1, u.SEL + 1)][0]
        res = [t for t in TD.texts() if t[2] == str(2 * (u.SEL + 1)) and t[1] == sel[1]][0]
        assert TD.pixel(res[0] - 2, res[1]) == band and TD.pixel(1, sel[1]) != band
    assert u.SEL == 0
    top = u.VIEWEND
    for j in range(7):
        u.key(DOWN)
    assert u.SEL == 7 and u.VIEWEND == 7 and top < 7
    u.key(DOWN)
    assert u.MODE == 0


def test_page_shows_at_most_pagemax_and_every_layout_is_cached():
    s = KS.run(''.join('%d/7{enter}' % j for j in range(1, 8)))
    u, d = s.mods['ui'], s.mods['draw']
    assert len(d.CACHE) <= 5 and len(d.ICACHE) <= 5
    misses = []
    real = d.tree
    d.tree = lambda code: misses.append(1) or real(code)
    reals = d.mparse
    d.mparse = lambda *a: misses.append(2) or reals(*a)
    try:
        TD.reset()
        u.FULL = True
        u.redraw()
        first = len(misses)
        TD.reset()
        u.FULL = True
        u.redraw()
        assert len(misses) == first == 0
    finally:
        d.tree, d.mparse = real, reals


def test_wide_focused_answer_scrolls_with_dx():
    s = KS.run('expand((x+1)^12){enter}' + '{right}' * 40)
    u = s.mods['ui']
    w = s.mods['draw'].layout(s.hist[-1][1], 300, 92)[1]
    assert u.DX == w - 300
    assert any(t[2] == '<' and t[0] == 0 for t in s.texts)
    assert not any(t[2] == '>' and t[0] == 310 for t in s.texts)
    assert s.offscreen == [] and s.overdraw == []


def test_tall_entry_shrinks_the_stage_and_the_welcome_text():
    s = KS.run('{2nd,frac}{down}{down}{down}{down}{down}{down}{down}{down}{down}{down}'
               '{down}{enter}1')
    u = s.mods['ui']
    assert u.EH >= 60
    ey = 190 - u.EH
    assert all(t[1] + 15 <= ey - 21 for t in s.texts if 20 <= t[1] < ey - 19)
    assert s.offscreen == [] and s.overdraw == []


def test_input_layout_failure_draws_the_input_1d(monkeypatch):
    s = KS.run('1/2{enter}')
    u, d = s.mods['ui'], s.mods['draw']

    def boom(text, mode):
        raise MemoryError('history input')

    monkeypatch.setattr(d, 'mlayout', boom)
    d.clear_cache()
    TD.reset()
    u.FULL = True
    u.redraw()
    assert '1/2' in TD.screen_text()


def test_panic_resets_the_row_views():
    s = KS.run('2/3{enter}x+1')
    u = s.mods['ui']
    u.panic(0)
    assert u.STATVIEW is None and u.HINTVIEW is None and u.EKEY is None and u.EDL is None
    TD.reset()
    u.key(CLEAR)
    assert ('fill_rect', -1, -1, 321, 211) in fills()


def test_status_draw_forces_the_status_row_back():
    s = KS.run('2+3')
    u = s.mods['ui']
    u.status('Calculating.')
    assert u.STATVIEW is None
    TD.reset()
    u.redraw()
    assert fills() == [('fill_rect', -1, -1, 321, 20)]
    assert 'Calculating' not in TD.screen_text()


def test_input_layout_bug_draws_the_input_1d_and_the_shell_keeps_working(monkeypatch):
    """A history input whose layout raises (a layout bug, not MemoryError) must not panic every
    later redraw: with the history on screen, no key could ever paint the shell again."""
    s = KS.run('1/2{enter}')
    u, d = s.mods['ui'], s.mods['draw']
    real = d.mlayout

    def bug(text, mode):
        if mode == 1:
            raise ValueError('layout bug')
        return real(text, mode)

    monkeypatch.setattr(d, 'mlayout', bug)
    d.clear_cache()
    TD.reset()
    u.FULL = True
    u.redraw()
    assert '1/2' in TD.screen_text()
    u.key(92)
    assert u.LINE == '1'


@pytest.mark.parametrize('k', [LEFT, RIGHT])
def test_scroll_key_on_a_narrow_answer_draws_nothing(k):
    """An answer that fits has nothing to scroll: <-/-> on the empty line is a no-op key
    (MATHPRINT.md 10), not a full redraw."""
    s = KS.run('2+3{enter}')
    u = s.mods['ui']
    TD.reset()
    u.key(k)
    u.key(k)
    assert u.DX == 0
    assert TD.CALLS == []


def test_empty_page_is_plain(editor):
    """No history: no title or tagline (the user asked for a plain page), only the gray hint
    line where to start."""
    TD.reset()
    U.FULL = True
    U.redraw()
    colors = dict((t[2], t[3]) for t in TD.texts())
    assert 'cas-evo' not in colors and 'Exact algebra and calculus' not in colors
    assert colors['Press math or menu'] == D.COLORS['SUB']
    assert TD.COUNTS['set_color'] <= 6
