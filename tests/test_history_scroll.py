"""v1.0.0: history scrolling and the status row (docs/notes/MATHPRINT.md 7.2, 7.3, 6.1).

UP from the entry enters the history page's scroll mode (MODE), as on the TI-Nspire
CX II CAS: UP/DOWN move between entries, LEFT selects the input (left column), RIGHT the output
(right column), with the band behind the chosen cell only; ENTER copies the selected cell into
the entry at the caret and the editor is active again. An output wider than the view scrolls
(DX) with RIGHT/LEFT before LEFT switches to the input. The answer's form label sits at the
top right of the status row, left of the modifier chip; a status message that needs the room
hides it until the message clears.
"""
import keyscript as KS
import ti_draw as TD

SECOND, LEFT, UP, RIGHT, DOWN, ENTER, CLEAR = 21, 24, 25, 26, 34, 105, 45
WIDE = 'expand((x+1)^12){enter}'


def ui(s):
    return s.mods['ui']


def band(s):
    """The ACCSOFT fills on the stage (the tabs at y 191 excluded): (x, y, w, h)."""
    c = s.mods['draw'].COLORS['ACCSOFT']
    out = []
    color = None
    for call in TD.CALLS:
        if call[0] == 'set_color':
            color = tuple(call[1:4])
        elif call[0] == 'fill_rect' and color == c and 19 < call[2] < 190:
            out.append(call[1:5])
    return out


# -- UP enters the scroll mode (F2 is the Calculus tab since the F-key row of 0.13) ------------

def test_up_enters_history_scroll_on_the_last_output():
    s = KS.run('1+1{enter}2+3{enter}{up}')
    u = ui(s)
    assert u.MODE == 1 and u.SEL == 1 and u.SELC == 1
    s = KS.run('1+1{enter}2+3{enter}{up}{down}')
    assert ui(s).MODE == 0                                  # DOWN past the last leaves it
    s = KS.run('1+1{enter}{up}{clear}')                     # CLEAR deletes the only entry
    assert ui(s).MODE == 0 and ui(s).LINE == '' and not s.hist


def test_up_without_history_is_engine_free_and_opens_no_menu():
    s = KS.run('{up}')
    assert 'run' not in s.mods and 'menu' not in s.mods
    assert ui(s).MODE == 0 and 'Recall' not in s.screen


def test_up_from_the_entry_selects_the_last_output():
    s = KS.run('1+1{enter}{up}')
    assert ui(s).MODE == 1 and ui(s).SELC == 1


def test_tabs_are_the_catalog_tabs_and_forms():
    s = KS.run('')
    assert 'recall' not in s.screen and 'hist' not in s.screen
    tabs = [t for t in s.texts if t[1] == 193]
    assert [t[2] for t in sorted(tabs)] == ['Alg', 'Calc', 'Trig', 'More', 'Forms']


def test_vars_key_lists_variables_without_history():
    s = KS.run('a=3{enter}2+5{enter}{vars}{snap:vars}{enter}')
    shown = s.snap('vars')
    assert 'Vars' in shown and 'a = 3' in shown and 'Ans' in shown
    assert '2+5' not in shown                               # the history scrolls instead
    assert ui(s).LINE == 'ans()'


# -- LEFT, RIGHT and ENTER ---------------------------------------------------------------------

def test_left_selects_the_input_right_the_output():
    s = KS.run('1{frac}4{enter}{up}{left}')
    assert ui(s).SELC == 0 and ui(s).MODE == 1
    s = KS.run('1{frac}4{enter}{up}{left}{right}')
    assert ui(s).SELC == 1


def test_enter_copies_the_input_as_2d_text():
    s = KS.run('1{frac}4{enter}{up}{left}{enter}')
    u = ui(s)
    assert u.LINE == '(1)/(4)' and u.CUR == 7 and u.MODE == 0


def test_enter_copies_the_output():
    s = KS.run('2/3{enter}x+{up}{enter}')
    assert ui(s).LINE == 'x+(2/3)' and ui(s).MODE == 0
    s = KS.run('2/3{enter}x^{up}{enter}')
    assert ui(s).LINE == 'x^(2/3)'
    s = KS.run('2/3{enter}{frac}{up}{enter}')               # bare into the empty numerator
    assert ui(s).LINE == '(2/3)/()' and ui(s).CUR == 4


def test_column_is_kept_while_moving_between_entries():
    s = KS.run('1+1{enter}2+3{enter}{up}{left}{up}{enter}')
    assert ui(s).LINE == '1+1'
    s = KS.run('1+1{enter}2+3{enter}{up}{left}{up}{down}{enter}')
    assert ui(s).LINE == '2+3'
    s = KS.run('1+1{enter}2+3{enter}{up}{up}{enter}')
    assert ui(s).LINE == '2'


def test_output_copy_never_includes_plus_c():
    s = KS.run('integrate(x^2,x){enter}{up}{enter}')
    assert 'C' not in ui(s).LINE and ui(s).LINE.startswith('(')
    s = KS.run('integrate(x^2,x){enter}{up}{left}{enter}')
    assert ui(s).LINE.startswith('integrate(')


def test_a_message_entry_selects_its_input():
    s = KS.run('1/0{enter}{up}{snap:sel}{enter}')
    h = s.hist[0]
    assert h[2] != s.mods['run'].R_ANS
    assert ui(s).LINE == '(1)/(0)'                       # the input, 2D again


def test_2nd_up_and_down_take_five_steps_and_forms_act_on_the_selection():
    s = KS.run(''.join('sqrt(%d){enter}' % j for j in (2, 3, 5, 6, 7, 8, 10)) +
               '{up}{2nd,up}')
    assert ui(s).SEL == 1
    s = KS.run('sqrt(2){enter}sqrt(3){enter}{up}{up}{f5}')
    assert s.hist[0][5][-1][0] == 'decimal' and not s.hist[1][5]
    assert ui(s).MODE == 1 and ui(s).SEL == 0


# -- the selection band marks one cell ---------------------------------------------------------

def test_band_covers_the_selected_cell_only():
    s = KS.run('2+3{enter}{up}')
    TD.reset()
    u = ui(s)
    u.key(LEFT)
    bands = band(s)
    assert len(bands) == 1
    x, y, w, h = bands[0]
    inp = [t for t in TD.texts() if t[2] == '2+3'][0]
    res = [t for t in TD.texts() if t[2] == '5'][0]
    assert x <= inp[0] and inp[0] + 30 <= x + w <= res[0]   # the input, not the result
    assert y <= inp[1] and inp[1] + 15 <= y + h
    TD.reset()
    u.key(RIGHT)
    x, y, w, h = band(s)[0]
    assert inp[0] + 30 <= x <= res[0] and x + w >= res[0] + 10
    assert TD.pixel(1, inp[1] + 5) != s.mods['draw'].COLORS['ACCSOFT']


# -- a wide output scrolls before the column changes --------------------------------------------

def test_wide_output_scrolls_then_left_selects_the_input():
    s = KS.run(WIDE + '{up}{right}')
    u = ui(s)
    assert u.SELC == 1 and u.DX == 24
    span = u.VIEW[-1]
    assert span > 48
    for _ in range(40):
        u.key(RIGHT)
    assert u.DX == span and u.SELC == 1                     # at its end: nothing more
    while u.DX:
        u.key(LEFT)
        assert u.SELC == 1
    u.key(LEFT)
    assert u.SELC == 0 and u.DX == 0
    u.key(RIGHT)
    assert u.SELC == 1 and u.DX == 0


def test_narrow_output_left_switches_at_once():
    s = KS.run('2+3{enter}{up}{left}')
    assert ui(s).SELC == 0 and ui(s).DX == 0


def test_empty_line_still_scrolls_the_last_answer():
    s = KS.run(WIDE + '{right}')
    u = ui(s)
    assert u.MODE == 0 and u.DX == 24


# -- the form label at the top right ------------------------------------------------------------

def test_form_label_is_at_the_top_right_without_f4():
    s = KS.run('sqrt(2){enter}')
    assert 'F4' not in s.screen
    lab = [t for t in s.texts if t[2] == 'exact']
    assert lab and lab[0][1] == 2 and lab[0][0] == 315 - 50
    assert '~ 1.414213562' in s.screen                      # the decimal stays in the footer
    s = KS.run('sqrt(2){enter}{f5}')
    lab = [t for t in s.texts if t[2] == 'decimal']
    assert lab and lab[0][1] == 2 and lab[0][0] == 315 - 70


def test_form_label_sits_left_of_the_modifier_chip():
    s = KS.run('sqrt(2){enter}{2nd}')
    texts = dict((t[2], t) for t in s.texts if t[1] == 2)
    assert texts['2nd'][0] == 315 - 30
    assert texts['exact'][0] + 50 + 10 <= texts['2nd'][0]
    s = KS.run('sqrt(2){enter}{alpha}{alpha}')
    texts = dict((t[2], t) for t in s.texts if t[1] == 2)
    assert 'A-LOCK' in texts or 'a-lock' in texts
    chip = texts.get('A-LOCK') or texts.get('a-lock')
    assert texts['exact'][0] + 50 <= chip[0] - 10


def test_status_message_hides_the_label_until_it_clears():
    s = KS.run('sqrt(2)=>x{enter}')
    u = ui(s)
    assert u.STATUS == 'Stored; purge(name) clears'
    assert 'exact' not in [t[2] for t in s.texts if t[1] == 2]
    u.STATUS = 'Stored; purge(name) clears'
    u.FULL = True
    TD.reset()
    u.redraw()
    row = [t for t in TD.texts() if t[1] == 2]
    assert any(t[2].startswith('Stored; purge(name)') for t in row)
    xs = [t[0] + 10 * len(t[2]) for t in row]
    assert max(xs) <= 315
    for a in row:                                           # nothing overlaps
        for b in row:
            if a is not b:
                assert a[0] + 10 * len(a[2]) <= b[0] or b[0] + 10 * len(b[2]) <= a[0]


def test_label_and_message_share_the_row_when_both_fit():
    s = KS.run('sqrt(2){enter}')
    u = ui(s)
    u.STATUS = 'engine 1.2s'
    u.FULL = True
    TD.reset()
    u.redraw()
    row = dict((t[2], t) for t in TD.texts() if t[1] == 2)
    assert 'engine 1.2s' in row and 'exact' in row


def test_status_row_repaints_only_when_the_label_changes():
    s = KS.run('sqrt(2){enter}')
    u = ui(s)
    TD.reset()
    u.key(92)                                               # typing: the label goes away
    assert 'exact' not in TD.screen_text(0, 0, 320, 19)
    assert [c for c in TD.CALLS if c[0] == 'fill_rect' and c[2] == -1]
    TD.reset()
    u.key(93)                                               # the row is unchanged: no repaint
    assert not [c for c in TD.CALLS if c[0] == 'fill_rect' and c[2] < 19]
    assert not [t for t in TD.texts() if t[1] == 2]


def test_empty_page_reads_press_math_or_menu():
    s = KS.run('')
    assert 'Press math or menu' in s.screen
    assert 'Type math' not in s.screen


# -- v1.0.1: CLEAR deletes the selected entry (MATHPRINT.md 0.14) ------------------------------

def test_clear_deletes_the_selected_entry_and_selects_the_older_one():
    s = KS.run('1+1{enter}2+3{enter}3+4{enter}{up}{up}{clear}')
    u = ui(s)
    assert [h[0] for h in s.hist] == ['1+1', '3+4']
    assert u.MODE == 1 and u.SEL == 0 and u.SELC == 1
    assert s.mods['run'].ANS == '7'                         # Ans is unchanged
    assert '2+3' not in s.screen and '1+1' in s.screen and '3+4' in s.screen


def test_clear_on_the_input_cell_deletes_the_whole_pair():
    s = KS.run('1+1{enter}2+3{enter}{up}{left}{clear}')
    u = ui(s)
    assert [h[0] for h in s.hist] == ['1+1']
    assert u.MODE == 1 and u.SEL == 0 and u.SELC == 0
    assert '5' not in [t[2] for t in s.texts]


def test_clear_on_the_oldest_selects_the_newer_one():
    s = KS.run('1+1{enter}2+3{enter}3+4{enter}{up}{up}{up}{clear}')
    u = ui(s)
    assert [h[0] for h in s.hist] == ['2+3', '3+4']
    assert u.MODE == 1 and u.SEL == 0
    s = KS.run('1+1{enter}2+3{enter}{up}{up}{clear}{enter}')   # ENTER copies the new selection
    assert ui(s).LINE == '5' and ui(s).MODE == 0


def test_clear_keeps_ans_and_variables_and_leaves_when_empty():
    s = KS.run('a=3{enter}2+5{enter}{up}{clear}{clear}')
    u = ui(s)
    assert not s.hist and u.MODE == 0 and u.SEL == -1
    assert s.mods['run'].VARS == {'a': '3'} and s.mods['run'].ANS == '7'
    assert 'Press math' in s.screen
    s = KS.run('a=3{enter}2+5{enter}{up}{clear}{clear}{clear}')   # the entry's CLEAR again
    assert ui(s).MODE == 0 and not s.hist


def test_clear_outside_the_mode_still_clears_the_line():
    s = KS.run('1+1{enter}2+3{clear}')
    assert ui(s).LINE == '' and len(s.hist) == 1


def test_clear_resets_the_2nd_enter_recall():
    s = KS.run('1+1{enter}2+3{enter}3+4{enter}{2nd,enter}{up}{clear}{down}{2nd,enter}')
    u = ui(s)
    assert [h[0] for h in s.hist] == ['1+1', '2+3']
    assert u.MODE == 0 and u.LINE == '2+3'                 # from the newest entry again


def test_clear_keeps_the_page_and_the_forms_of_the_others():
    s = KS.run(''.join('sqrt(%d){enter}' % j for j in (2, 3, 5, 6, 7, 8, 10)) +
               '{up}{up}{f5}{2nd,up}{clear}')
    u = ui(s)
    assert len(s.hist) == 6 and u.MODE == 1
    assert [h[0] for h in s.hist][u.SEL] == 'sqrt(3)'
    assert s.hist[4][5][-1][0] == 'decimal'                # sqrt(8) keeps its form
    assert 0 <= u.SEL <= u.VIEWEND < len(s.hist)
    u.key(15)                                               # F5 acts on the new selection
    assert u.MODE == 1
    TD.reset()
    u.FULL = True
    u.redraw()
    assert u.VIEW[5] == 6
