"""Calculator entry-loop acceptance using the actual key map and graphics shim."""
import pytest
import keyscript as KS
import ti_graphics as G


def test_evaluate_chain_and_negative_key():
    s = KS.run('2+3{enter}*2{enter}')
    assert s.ans == '10'
    s = KS.run('2+3{enter}_2{enter}')
    assert s.ans == '-2'


def test_entry_and_repeat():
    s = KS.run('2+3{enter}{enter}{2nd,enter}')
    assert len(s.hist) == 2
    assert s.mods['ui'].LINE == '2+3'


def test_atomic_ans_delete():
    s = KS.run('2{enter}{2nd,(-)}{del}')
    assert s.mods['ui'].LINE == ''


def test_empty_slot_never_evaluates():
    s = KS.run('diff(,x){enter}')
    assert len(s.hist) == 0
    assert 'empty slot' in s.screen


def test_history_fraction_paste_is_parenthesized():
    s = KS.run('2/3{enter}x^{up}{enter}')
    assert s.mods['ui'].LINE == 'x^(2/3)'


def test_test_picker_and_definition():
    s = KS.run('a=3{enter}a+2{enter}')
    assert s.ans == '5' and s.mods['run'].VARS['a'] == '3'


def test_forms_recall_and_theme():
    s = KS.run('sqrt(2){enter}{f4}{f3}{down}{enter}{clear}')
    assert s.ans.startswith('1.414213562')
    assert s.mods['run'].SET['theme'] == 1


def test_help_example_paste():
    s = KS.run('diff({f5}{enter}')
    assert 'diff(x^3,x,2)' in s.mods['ui'].LINE


def test_recover_from_interruption():
    s = KS.run('expand((x+y)^20){enter}{clear@1}2+3{enter}')
    assert s.ans == '5'


def test_quit():
    s = KS.run('{2nd,mode}')
    assert s.hist == []


def test_clear_history_while_selected():
    s = KS.run('2{enter}{up}{f3}{down}{down}{enter}{enter}{clear}{enter}')
    assert s.hist == [] and s.mods['ui'].MODE == 0
    assert 'Display error' not in s.screen


def test_action_wrap_limit_preserves_original_input_and_caret():
    original = 'x' * 256
    s = KS.run(original + '{f1}{enter}')
    u = s.mods['ui']
    assert u.LINE == original and u.CUR == len(original)
    assert u.STATUS == 'Input limit: 256 characters'
    assert not s.hist


def test_action_wrap_exact_limit_still_succeeds():
    original = 'x' * 246
    s = KS.run(original + '{f1}{enter}')
    u = s.mods['ui']
    assert u.LINE == 'simplify(' + original + ')'
    assert len(u.LINE) == 256 and u.CUR == 255
    assert u.STATUS == ''


@pytest.mark.parametrize('name', ('sin', 'sqrt', 'abs', 'exp', 'log', 'surd', 'd'))
def test_empty_builtin_or_alias_keeps_editor_and_moves_caret(name):
    original = name + '()'
    s = KS.run(original + '{enter}')
    u = s.mods['ui']
    assert not s.hist and u.LINE == original
    assert u.CUR == len(name) + 1
    assert u.STATUS == 'fill in the empty slot'


def test_ans_without_arguments_remains_valid():
    s = KS.run('2{enter}{2nd,(-)}{enter}')
    assert s.ans == '2' and len(s.hist) == 2


def test_decimal_form_hides_approximation_until_exact_returns():
    s = KS.run('sqrt(2){enter}{snap:exact}{f4}{snap:decimal}{f4}{snap:restored}')
    assert '~ 1.414213562' in s.snap('exact')
    assert 'decimal  F4' in s.snap('decimal') and '~ ' not in s.snap('decimal')
    assert 'exact  F4' in s.snap('restored') and '~ 1.414213562' in s.snap('restored')


@pytest.mark.parametrize('reason, message', ((0, 'Out of memory'), (1, 'Interrupted'),
    (2, 'Expression too complex'), (3, 'Display error')))
def test_panic_works_without_ui_or_layout_phase(monkeypatch, reason, message):
    s = KS.run('2/3{enter}x+1')
    u, d = s.mods['ui'], s.mods['draw']
    before = (u.LINE, u.CUR, s.ans, tuple(s.hist[0]))
    with monkeypatch.context() as patch:
        for module, names in ((u, ('redraw', 'enclosing', 'wrapped', 'empty_slot')),
                              (d, ('layout', 'paint', 'tree', 'measure', 'place', 'render'))):
            for name in names:
                patch.delattr(module, name)
        G.reset()
        u.panic(reason)
    assert (u.LINE, u.CUR, s.ans, tuple(s.hist[0])) == before
    assert message in G.screen_text() and '2/3' in G.screen_text()
    assert not d.CACHE and not G.OVERDRAW
    # Once the entry loop restores the UI phase, the next key works normally.
    u.key(45)
    assert u.LINE == '' and u.STATUS == ''


def test_panic_never_retries_failing_layout(monkeypatch):
    s = KS.run('2/3{enter}')
    u, d = s.mods['ui'], s.mods['draw']

    def failure(*args, **kwargs):
        raise MemoryError('persistent layout failure')

    monkeypatch.setattr(d, 'layout', failure)
    u.panic(0)
    assert 'Out of memory' in G.screen_text() and '2/3' in G.screen_text()
