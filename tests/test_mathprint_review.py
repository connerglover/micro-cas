"""MathPrint review regressions (docs/notes/MATHPRINT.md 0.8): each test pins one finding of the
post-implementation review, through the real entry program (tests/support/keyscript.py)."""
import keyscript as KS

CLASSIC = '{f3}' + '{down}' * 5 + '{enter}{clear}'


def line(s):
    u = s.mods['ui']
    return u.LINE, u.CUR


# -- Classic is the old editor ------------------------------------------------------------------

def test_classic_left_moves_into_a_call_name():
    s = KS.run(CLASSIC + '{52}{32}{24}{24}')
    assert s.mods['ui'].CLASSIC and line(s) == ('sin(x', 3)
    assert line(KS.run(CLASSIC + '{52}{32}{24}{24}{24}{23}')) == ('sn(x', 1)
    assert line(KS.run(CLASSIC + '{85}{52}{32}{24}{24}{24}{23}')) == ('+sn(x', 2)


def test_classic_menu_templates_have_no_prefill():
    s = KS.run(CLASSIC + '{41}{105}')
    assert line(s) == ('diff(,)', 5)
    s = KS.run(CLASSIC + '{41}{105}t^2{right}t{enter}')
    assert s.hist[0][:2] == ['diff(t^2,t)', '2*t']


def test_mathprint_menu_templates_have_empty_boxes():
    assert line(KS.run('{41}{105}')) == ('diff(,)', 6)  # d/d[]([]): the variable box first


# -- ENTER's empty-slot check inside autoclosed brackets ----------------------------------------

def test_enter_catches_an_operator_before_an_autoclosed_closer():
    for script, want in (('sin(2+{enter}', ('sin(2+)', 6)), ('(2*{enter}', ('(2*)', 3)),
                         ('2*({enter}', ('2*()', 3))):
        s = KS.run(script)
        assert line(s) == want, script
        assert s.mods['ui'].STATUS == 'fill in the empty slot' and not s.hist, script


def test_enter_still_allows_the_empty_log_base():
    s = KS.run('log(8,{enter}')
    assert s.hist and s.hist[0][0] == 'log(8)'


# -- menu actions wrap the whole line when only closers follow the caret ------------------------

def test_menu_action_wraps_a_line_ending_in_an_autoclosed_call():
    s = KS.run('{52}{32}{11}{105}')
    assert line(s) == ('simplify(sin(x))', 15)
    s = KS.run('{52}{32}{11}{105}{105}')
    assert s.hist[0][:2] == ['simplify(sin(x))', 'sin(x)']


def test_menu_action_wraps_a_line_ending_in_a_fraction_slot():
    s = KS.run('{32}{85}{92}{42}{32}{75}{92}{11}' + '{34}' * 5 + '{105}{105}')
    assert s.hist[0][0] == 'partfrac(x+1/(x-1))'


# -- a MemoryError in the engine-free parse degrades to the 1D text ------------------------------

def test_parse_memory_error_degrades_tidy_structure_and_paste():
    s = KS.run('1{frac}4{enter}')
    u, d = s.mods['ui'], s.mods['draw']
    real = d.mparse

    def failing(t, tk, mode):
        if mode == 1:
            raise MemoryError('parse')
        return real(t, tk, mode)
    d.mparse = failing
    try:
        assert u.tidy('(1)/(4)') == '(1)/(4)'
        assert u.tidy('1/4', 1) == '1/4'
        d.ICACHE[:] = []
        u.LINE, u.CUR, u.MODE, u.SEL, u.EMODEL = '', 0, 1, 0, None
        u.key(21)
        u.key(105)                      # 2nd ENTER in MODE: paste the input
        assert u.LINE == '1/4' and u.MODE == 0
        u.LINE, u.CUR, u.EMODEL = '', 0, None
        u.key(21)
        u.key(105)                      # ENTRY recall
        assert u.LINE == '1/4'
    finally:
        d.mparse = real


# -- tidy and the fraction key keep an E-number whole --------------------------------------------

def test_tidy_keeps_the_parens_after_an_exponent_sign():
    s = KS.run('')
    u = s.mods['ui']
    assert u.tidy('2E+(3)/(4)') == '2E+(3)/4'
    assert u.tidy('5E-(1)/(2)') == '5E-(1)/2'
    assert u.tidy('x+(3)/(4)') == 'x+3/4'
    assert u.tidy('E+(3)/(4)') == 'E+3/4'


def test_fraction_key_captures_a_whole_e_number():
    s = KS.run('2{2nd,62}+3{frac}4')
    assert line(s) == ('(2E+3)/(4)', 9)
    s = KS.run('2{2nd,62}+3{frac}4{enter}')
    assert s.hist[0][1] == '500.0'
    s = KS.run('2{2nd,62}{(-)}3{frac}4{enter}')
    assert s.hist[0][1] == '0.0005'


def test_fraction_after_an_exponent_sign_is_what_is_drawn():
    s = KS.run('2{2nd,62}+{frac}3{down}4{enter}')
    assert s.hist[0][0] != '2E+3/4'
    assert s.hist[0][1] != '500.0'


# -- ! and ' after a power or fraction box apply to the whole box --------------------------------

def test_postfix_after_a_power_wraps_it():
    s = KS.run('3{51}2{right}{2nd,math}7')
    assert line(s) == ('(3^(2))!', 8)
    s = KS.run('3{51}2{right}{2nd,math}7{enter}')
    assert s.hist[0][1] == '362880'
    assert line(KS.run('3{61}{2nd,math}7')) == ('(3^(2))!', 8)


def test_postfix_after_a_fraction_wraps_it():
    s = KS.run('{frac}3{down}2{right}{2nd,math}7')
    u = s.mods['ui']
    assert line(s) == ('((3)/(2))!', 10) and not u.EFLAT


def test_prime_after_a_power_wraps_it():
    assert line(KS.run('x{51}2{right}{alpha}.')) == ("(x^(2))'", 8)


def test_postfix_inside_a_box_stays_inside():
    assert line(KS.run('3{51}2{2nd,math}7')) == ('3^(2!)', 5)


# -- the fraction key's capture ----------------------------------------------------------------

def test_fraction_key_after_a_list_or_matrix_stacks():
    s = KS.run('{2nd,(}1,2{2nd,)}{frac}3')
    assert line(s) == ('({1,2})/(3)', 10) and not s.mods['ui'].EFLAT
    assert line(KS.run('{2nd,-}1,2{2nd,+}{frac}')) == ('([1,2])/()', 9)


def test_fraction_key_after_an_inline_division_takes_the_term():
    s = KS.run('1/2{frac}3')
    u = s.mods['ui']
    assert line(s) == ('(1/2)/(3)', 8) and not u.EFLAT
    assert any(it[0] == 'l' for it in u.EDMAP[1])           # a fraction bar
    assert line(KS.run('a*b/c{frac}')) == ('a*(b/c)/()', 9)
    assert line(KS.run('1+2/3{frac}')) == ('1+(2/3)/()', 9)


def test_power_and_fraction_keys_at_the_stop_after_a_base():
    assert line(KS.run('x{51}2{down}{51}3')) == ('(x^(2))^(3)', 10)
    assert line(KS.run('x{51}2{down}{61}')) == ('(x^(2))^(2)', 11)
    assert line(KS.run('x{51}2{down}{frac}')) == ('(x^(2))/()', 9)


# -- per-key paint cost on long 2D lines (section 10) --------------------------------------------

import ti_draw as TD                    # noqa: E402


def _key_cost(u, k):
    del TD.CALLS[:]                     # keep the framebuffer
    TD.COUNTS.clear()
    u.key(k)
    full = [c for c in TD.CALLS if c[0] == 'fill_rect' and c[1] == -1]
    return full, TD.COUNTS.get('draw_text', 0), TD.COUNTS.get('draw_line', 0)


def test_caret_moves_past_index_29_of_a_2d_line_are_strips():
    s = KS.run('(1)/(2)+(1)/(3)+(1)/(4)+(1)/(5)+(1)/(6)+(1)/(7)+{2nd,left}')
    u = s.mods['ui']
    assert u.CUR == 0 and u.EDMAP is not None and len(u.LINE) > 40
    while u.CUR < len(u.LINE):
        full, texts, lines = _key_cost(u, 26)
        assert not full and texts <= 2 and lines <= 3, (u.CUR, TD.CALLS)


def test_typing_at_the_end_of_a_long_2d_line_is_a_diff_paint():
    s = KS.run('(1)/(2)+(1)/(3)+(1)/(4)+(1)/(5)+(1)/(6)+(1)/(7)+(1)/(8)+(1)/(9)+')
    u = s.mods['ui']
    assert u.CUR > 29 and u.EXOFF == 0
    for k in (92, 93, 94):
        full, texts, lines = _key_cost(u, k)
        assert not full and texts <= 2 and lines <= 2, TD.CALLS


def test_typing_past_the_scroll_repaints_once_per_jump():
    s = KS.run('(1)/(2)+(1)/(3)+(1)/(4)+(1)/(5)+(1)/(6)+(1)/(7)+(1)/(8)+(1)/(9)+')
    u = s.mods['ui']
    fulls = 0
    for j in range(8):
        for k in (92, 93, 94, 85):
            full, texts, lines = _key_cost(u, k)
            fulls += texts > 3          # the whole visible entry painted again
    assert u.EXOFF > 0
    assert fulls <= 4, fulls


def test_history_page_move_lays_out_one_new_entry(monkeypatch):
    cmds = ['1/2+x^3', 'x^2+1', 'x^3/3', 'sqrt(x)+1', 'e^x', '2/x', 'x^4-1', 'sin(x)/x',
            '1/x^2', 'ln(x)+x^2', 'x^5', 'limit(sin(x)/x,x,0)']
    s = KS.run(''.join(c + '{enter}' for c in cmds) + '{up}' * 12)
    u, d = s.mods['ui'], s.mods['draw']
    parse = s.mods['parse']
    calls = []
    real_m, real_r = d.mparse, parse.rpn

    def m(*a):
        calls.append('m')
        return real_m(*a)

    def r(*a):
        calls.append('r')
        return real_r(*a)
    monkeypatch.setattr(d, 'mparse', m)
    monkeypatch.setattr(parse, 'rpn', r)
    for j in range(11):
        del calls[:]
        u.key(34)
        assert calls.count('m') <= 1 and calls.count('r') <= 1, (j, u.SEL, calls)


def test_a_failed_history_layout_is_not_retried(monkeypatch):
    s = KS.run('1{frac}2{right}+x^3{enter}')
    u, d = s.mods['ui'], s.mods['draw']
    real = d.mparse
    calls = []

    def failing(t, tk, mode):
        if mode == 1:
            calls.append(t)
            raise MemoryError('layout')
        return real(t, tk, mode)
    monkeypatch.setattr(d, 'mparse', failing)
    d.clear_cache()
    for j in range(3):
        u.FULL = True
        u.redraw()
    assert len(calls) == 1
    assert '1/2+x^3' in TD.screen_text()


def test_focused_answer_is_not_cut_when_the_entry_grows():
    tmpl = '{2nd,frac}' + '{down}' * 8 + '{enter}'    # the integral; its d[] box is typed too
    s = KS.run(tmpl + '0{right}1{right}x{pow}1{frac}2{right}{right}{right}x{enter}' + tmpl)
    u = s.mods['ui']
    assert u.EH >= 40 and s.hist[0][1] == '2/3'
    last = max(j for j in range(len(TD.CALLS)) if TD.CALLS[j] == ('fill_rect', -1, -1, 321, 211))
    texts = [c for c in TD.CALLS[last:] if c[0] == 'draw_text' and c[1] > 280 and
             c[2] < 190 - u.EH]
    assert any(c[3] == '2' for c in texts) and any(c[3] == '3' for c in texts), texts


# -- looks: layout extents, the large operators, strokes, slots, caret, picker ------------------

def _extent(m):
    """The rows the display list of an mlayout result reaches, from its top-left corner."""
    lo, hi = 10 ** 6, -10 ** 6
    for it in m[1]:
        if it[0] == 't':
            a, b = it[2], it[2] + 14
        elif it[0] == 'l':
            a, b = min(it[2], it[4]), max(it[2], it[4])
        elif it[0] == 'g':
            a, b = it[2], it[2] + it[5] - 1
        else:
            a, b = it[2], it[2] + it[4] - 1
        lo, hi = min(lo, a), max(hi, b)
    return lo, hi


def test_integral_variable_slot_counts_in_the_height():
    s = KS.run('')
    d = s.mods['draw']
    for t in ('integrate(1,(1)/(2))', 'integrate(1,xsum(,k,,))', 'integrate(x,x)'):
        m = d.mlayout(t, 2)
        lo, hi = _extent(m)
        assert 0 <= lo and hi < m[3] + m[4], (t, lo, hi, m[3], m[4])


def test_caret_stays_in_the_entry_box_with_a_tall_variable_slot():
    for script in ('{2nd,frac}{right}2{right}{right}{del}{frac}{frac}',
                   '{2nd,frac}{right}2{right}{right}{2nd,frac}{right}5'):
        s = KS.run(script)
        u = s.mods['ui']
        ey = 190 - u.EH
        caret = [c for c in TD.CALLS if c[0] == 'draw_line'][-1]
        assert ey <= caret[2] and caret[4] <= 189, (script, caret, ey)


def test_large_operators_with_one_fraction_level_stay_2d():
    s = KS.run('')
    d = s.mods['draw']
    for t in ('sum(1,k,1,(n)/(2))', 'sum(1,k,(1)/(2),n)', '(sum(1,k,1,n))/(2)',
              'integrate(1,x,(1)/(2),(3)/(2))', 'sum((1)/(k^(2)),k,1,n)'):
        m = d.mlayout(t, 2)
        assert m is not None, t
        lo, hi = _extent(m)
        assert 0 <= lo and hi < m[3] + m[4] <= 80, (t, lo, hi)
    assert d.mlayout('sum(,k,,)', 2)[3] + d.mlayout('sum(,k,,)', 2)[4] <= 56
    assert not KS.run('{frac}{2nd,frac}{right}5').mods['ui'].EFLAT


def test_no_orphan_strokes_at_the_scroll_edges():
    script = '1{frac}2{right}' + ''.join('+1{frac}%d{right}' % n for n in range(3, 14))
    for tail in ('', '{2nd,left}'):
        s = KS.run(script + tail)
        u = s.mods['ui']
        ey = 190 - u.EH
        bars = set()
        for it in KS.painted(u):
            if it[0] == 'l':
                bars.add(it[1:])
        last = max(j for j in range(len(TD.CALLS)) if TD.CALLS[j][0] == 'fill_rect' and
                   TD.CALLS[j][2] <= ey)
        for c in TD.CALLS[last:]:
            if c[0] == 'draw_line' and c[2] == c[4] and ey <= c[2] < 190:
                assert c[1:] in bars, (tail, c)          # never a cut-off bar


def _contrast(a, b):
    def lum(c):
        out = []
        for v in c:
            v = v / 255.0
            out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    x, y = sorted((lum(a), lum(b)))
    return (y + 0.05) / (x + 0.05)


def test_empty_slots_are_visible_in_both_themes():
    for pre in ('', '{f3}{down}{enter}{clear}'):
        s = KS.run(pre + '{frac}')
        u, d = s.mods['ui'], s.mods['draw']
        bg = d.COLORS['BG']
        boxes = [it for it in KS.painted(u) if it[0] == 'b']
        assert len(boxes) == 2
        colors = set()
        color = None
        for c in TD.CALLS:
            if c[0] == 'set_color':
                color = c[1:]
            elif c[0] in ('fill_rect', 'draw_line') and color != bg:
                for b in boxes:
                    if b[1] <= c[1] < b[1] + b[3] and b[2] <= c[2] < b[2] + b[4]:
                        colors.add(color)
        assert colors and min(_contrast(c, bg) for c in colors) >= 3, (pre, colors)


def test_fraction_bar_keeps_clear_of_its_neighbours():
    s = KS.run('1{frac}2{right}+1{frac}3{enter}')
    m = s.mods['draw'].mlayout('1/2+1/3', 1)
    bars = sorted(it for it in m[0] if it[0] == 'l')
    plus = [it for it in m[0] if it[0] == 't' and it[3] == '+'][0]
    assert bars[0][3] <= plus[1] - 3 and bars[1][1] >= plus[1] + 10 + 2, (bars, plus)
    m = s.mods['draw'].mlayout('2+(1)/(x)', 2)
    bar = [it for it in m[1] if it[0] == 'l'][0]
    assert bar[1] >= 20 + 2, m[1]                                 # '2+' is 20 px


def test_caret_in_an_empty_slot_is_inside_its_box_and_clear_of_the_bar():
    for script in ('{frac}', '{frac}{down}', '{frac}12'):
        s = KS.run(script)
        caret = [c for c in TD.CALLS if c[0] == 'draw_line'][-1]
        bar = [it for it in KS.painted(s.mods['ui']) if it[0] == 'l'][0]
        assert caret[2] > bar[2] + 1 or caret[4] < bar[2] - 1, (script, caret, bar)
        if script != '{frac}12':
            box = [it for it in KS.painted(s.mods['ui']) if it[0] == 'b'][0 if script == '{frac}' else 1]
            assert box[1] < caret[1] < box[1] + box[3], (script, caret, box)


def test_picker_footer_follows_the_page():
    s = KS.run('{2nd,frac}{snap:a}' + '{down}' * 8 + '{snap:b}')
    a, b = s.snap('a'), s.snap('b')
    assert '1/2' in a and '1-7 pick' in a and '<> page' in a
    assert '2/2' in b and '1-6 pick' in b and '1-7' not in b


def test_nested_radicals_have_two_clear_overbars():
    s = KS.run('')
    m = s.mods['draw'].mlayout('sqrt(sqrt(2))', 2)
    bars = sorted(set(it[2] for it in m[1] if it[0] == 'l' and it[2] == it[4]))
    assert len(bars) == 2 and bars[1] - bars[0] >= 3, m[1]
    m = s.mods['draw'].mlayout('sqrt(2)', 2)
    assert m[3] + m[4] <= 18


# -- memory: a 2D layout that runs out of memory frees the idle engine packs first ----------

def test_layout_memory_error_frees_idle_soft_packs_and_retries(monkeypatch):
    s = KS.run('2+3{enter}1{frac}2')
    u, d, r = s.mods['ui'], s.mods['draw'], s.mods['run']
    real = d.mlayout
    calls = []
    fails = [1]

    def flaky(t, mode):
        calls.append(mode)
        if mode == 2 and fails[0]:
            fails[0] -= 1
            raise MemoryError('layout')
        return real(t, mode)
    freed = []
    monkeypatch.setattr(d, 'mlayout', flaky)
    def shed(keep=None, packs=None):
        freed.append(1)
        return False
    monkeypatch.setattr(r, 'shed', shed)
    u.key(93)
    assert freed == [1, 1] and calls.count(2) == 2          # soft, then aux packs
    assert u.EDMAP is not None and not u.ED1D and not u.EFLAT
    fails[0] = 5                        # out of memory for good: one retry, then flat
    u.key(94)
    assert len(freed) == 4 and u.ED1D is True and u.EFLAT
    u.key(24)                           # the same text is not laid out again
    assert len(freed) == 4 and calls.count(2) == 4


def test_boot_block_is_released_when_the_view_pack_boots():
    """CASUI allocates the block before CASUX is imported, so the view pack loads above it;
    boot() lets it go at once (MATHPRINT.md 0.8): free-heap readings after boot are true."""
    s = KS.run('1+2')
    u = s.mods['ui']
    u.BALLAST = bytearray(16)           # the device allocates it (mem_free > 144000)
    u.boot()
    assert u.BALLAST is None and u.R is None
    u.key(105)
    assert u.R is not None


def test_layout_memory_error_before_the_engine_goes_flat_without_a_retry(monkeypatch):
    s = KS.run('1{frac}2')
    u, d = s.mods['ui'], s.mods['draw']
    assert u.R is None and u.BALLAST is None
    real = d.mlayout
    calls = []

    def failing(t, mode):
        if mode == 2:
            calls.append(t)
            raise MemoryError('layout')
        return real(t, mode)
    monkeypatch.setattr(d, 'mlayout', failing)
    u.key(93)
    assert len(calls) == 1 and u.ED1D and u.EFLAT and u.R is None     # drawn 1D
