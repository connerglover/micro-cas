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


def test_mathprint_menu_templates_keep_the_prefill():
    assert line(KS.run('{41}{105}')) == ('diff(,x)', 5)


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
        assert u.structure('1/4') == '1/4'
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
