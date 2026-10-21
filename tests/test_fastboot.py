"""Fast boot (docs/notes/FASTBOOT.md): the UI draws without the engine, loads it once on first
use, draws only through ti_draw's verified calls inside the 320 x 210 screen, keeps set_color
calls few, records boot and engine times, and recovers with or without the engine."""
import ast
import json
import os
import re
import subprocess
import sys

import pytest

import keyscript as KS
import ti_draw as TD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
SHIM = os.path.join(ROOT, 'shim')
SUPPORT = os.path.join(ROOT, 'tests', 'support')
UI_SIDE = ('ui', 'draw', 'casevo')                  # src modules that load before the engine
ON_EVO = {'set_color', 'fill_rect', 'draw_text', 'draw_line'}


def src_modules():
    return sorted(f[:-3] for f in os.listdir(SRC) if f.endswith('.py'))


def top_imports(name):
    with open(os.path.join(SRC, name + '.py'), encoding='utf-8') as fh:
        tree = ast.parse(fh.read())
    return [a.name for st in tree.body if isinstance(st, ast.Import) for a in st.names]


def child(code):
    """Run code in a fresh interpreter with src/, shim/ and tests/support on the path; the last
    printed line is JSON."""
    pre = 'import sys\nsys.path[:0] = %r\n' % [SUPPORT, SHIM, SRC]
    r = subprocess.run([sys.executable, '-c', pre + code], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# -- (a) the UI boots without the engine ------------------------------------------------------

def test_entry_and_ui_modules_import_no_engine_module():
    assert set(top_imports('casevo')) <= {'ti_system', 'time', 'gc', 'ui'}
    for name in ('ui', 'draw', 'menu', 'menub'):
        for m in top_imports(name):
            # sys: ui.engine removes a half-imported engine module from sys.modules
            assert m in ('ti_system', 'ti_draw', 'time', 'gc', 'sys', 'ui', 'draw'), (name, m)
    for name in src_modules():
        with open(os.path.join(SRC, name + '.py'), encoding='utf-8') as fh:
            assert 'ti_graphics' not in fh.read(), name


def test_boot_and_editing_leave_the_engine_unloaded():
    got = child('''
import json
import ti_system as TS
import ui as U
ENGINE = %r
U.boot()
booted = sorted(m for m in ENGINE if m in sys.modules)
for k in (93, 85, 94, 24, 23, 26, 21, 26, 31, 41, 45, 92, 85, 93, 25, 34, 24, 26):
    assert U.key(k) is None
edited = sorted(m for m in ENGINE if m in sys.modules)
line = U.LINE
job = U.key(105)
print(json.dumps({'booted': booted, 'edited': edited, 'line': line, 'job': job,
                  'loaded': [m for m in ('node', 'alg', 'parse', 'printer', 'run')
                             if m in sys.modules], 'R': U.R is sys.modules['run']}))
''' % [m for m in src_modules() if m not in UI_SIDE])
    assert got['booted'] == [] and got['edited'] == []
    assert got['line'] == '1+2' and got['job'] == ['eval', '1+2']
    assert got['loaded'] == ['node', 'alg', 'parse', 'printer', 'run'] and got['R']


def test_keyscript_session_without_enter_never_loads_the_engine():
    s = KS.run('2+3{left}{del}{2nd,left}{right}*x{clear}sin(x{snap:typed}')
    assert 'run' not in s.mods and 'node' not in s.mods and 'parse' not in s.mods
    # MathPrint autocloses sin( (MATHPRINT.md 11.2), so the unclosed text is typed closed
    assert s.mods['ui'].R is None and s.mods['ui'].LINE == 'sin(x)'
    assert not any(c[0] == 'draw_text' and c[3] == 'Loading engine...' for c in s.calls)


def test_hint_line_works_before_the_engine_loads():
    s = KS.run('int(x')
    assert 'run' not in s.mods
    assert 'Integrand (required)' in s.screen             # the argument help (QPL Q5)
    import ui as U
    assert all(len(h) <= 31 for h in U.ARGPH.split('|'))  # the hint line has 31 columns


# -- (b) the first ENTER loads the engine; later commands reuse it -----------------------------

def test_first_enter_loads_the_engine_once():
    s = KS.run('2+3{snap:typed}{enter}{snap:first}4*5{enter}{f1}{clear}{2nd,(-)}+1{enter}')
    assert [e[1] for e in s.hist] == ['5', '20', '21']
    loads = [i for i, c in enumerate(s.calls)
             if c[0] == 'draw_text' and c[3] == 'Loading engine...']
    assert len(loads) == 1
    typed = [n for label, text, n in s.snaps if label == 'typed'][0]
    first = [n for label, text, n in s.snaps if label == 'first'][0]
    assert typed < loads[0] < first
    u = s.mods['ui']
    assert u.R is s.mods['run'] and s.mods['run'].BUSY == u.busy
    assert s.mods['parse'].SESS is s.mods['run'] and s.mods['draw'].P is s.mods['parse']
    assert s.mods['node'].ESC is not None


def test_a_menu_loads_the_engine_when_it_needs_it():
    s = KS.run('{f2}{snap:recall}{clear}1+1{enter}')
    assert 'Recall' in s.snap('recall')
    assert sum(1 for c in s.calls if c[0] == 'draw_text' and c[3] == 'Loading engine...') == 1
    assert s.ans == '2'


# -- (c) every call is a verified ti_draw call, on the screen --------------------------------

SCREENS = [
    '',
    '2/3{enter}',
    'expand((x+1)^12){enter}' + '{right}' * 14 + '{left}',
    '1{enter}2{enter}3{enter}4{enter}5{enter}6',
    'integrate(x^2,x,0,1){enter}sum(k^2,k,1,n){enter}limit(sin(x)/x,x,0){enter}x',
    'x+' * 40 + '{left}' * 5 + '{2nd,left}{2nd,right}',
    '{f1}{right}' + '{down}' * 8 + '{alpha}s{del}{clear}',
    '{2nd,0}{snap}{clear}{2nd,math}{clear}diff({f5}{clear}{f5}{clear}',
    '{f3}{down}{down}{down}{down}{enter}{clear}{clear}',
    '{f3}{down}{enter}{clear}2/3{enter}x^2{enter}{up}',
    '2{enter}sqrt(8){enter}{up}{up}{f4}{f4}{down}{down}{down}',
    'sqrt(2){enter}{f4}',
    '1/0{enter}solve(x^2+1,x){enter}',
    'expand((x+y)^20){enter}{clear@1}',
    '{alpha}{alpha}abc{2nd}de{alpha}{2nd}',
    'a=3{enter}x=2{enter}',
    'integrate(x*sin(x),x){enter}',
    '9' * 250 + '{enter}{right}{right}{2nd,enter}',
    'x' * 256 + '+{alpha}{alpha}{enter}',        # a long status, then the engine loads
    # MathPrint (MATHPRINT.md 10): 2D entries, history inputs, the picker, scroll, EH growth
    '1{frac}2{enter}',
    '{2nd,frac}{down}{down}{enter}x^2',
    '{2nd,frac}' + '{down}' * 8 + '{enter}',
    '{2nd,frac}{snap:picker}{down}{right}{snap:page2}{clear}',
    '(1)/(2)+' * 12 + '{2nd,left}{right}{2nd,right}',
    '{2nd,frac}' + '{down}' * 11 + '{enter}1{frac}2{frac}3{right}{right}{right}+4{clear}5',
    '1/2{enter}x^(3)/(4){enter}{2nd,frac}{down}{down}{down}{down}{down}{down}{down}{down}'
    '{down}{enter}x^2{right},x,0,1{enter}{up}{up}{up}{down}',
]


@pytest.mark.parametrize('script', SCREENS, ids=[str(i) for i in range(len(SCREENS))])
def test_every_call_stays_on_screen(script):
    s = KS.run(script)
    assert s.offscreen == []
    assert s.overdraw == []
    assert set(s.counts) <= ON_EVO
    assert s.counts.get('fill_rect', 0) == sum(1 for c in s.calls if c[0] == 'fill_rect')
    for c in s.calls:
        if c[0] == 'fill_rect':
            assert c[3] >= 2 and c[4] >= 2
        elif c[0] == 'draw_text':
            assert c[3] and len(c[3]) <= 32 and all(32 <= ord(ch) < 127 for ch in c[3]), c
    for text in [s.screen] + [snap[1] for snap in s.snaps]:
        assert 'Display error' not in text


def test_loading_and_busy_status_replace_a_long_status():
    s = KS.run('x' * 256 + '+{alpha}{alpha}{enter}')
    assert any(c[0] == 'draw_text' and c[3] == 'Loading engine...' for c in s.calls)
    assert s.overdraw == [] and s.offscreen == []
    s = KS.run('x' * 256 + '+{alpha}{alpha}')
    u = s.mods['ui']
    assert u.STATUS == 'Input limit: 256 characters' and u.MOD == 3
    u.busy(1024)                                    # what R.go calls every 512 steps
    top = TD.screen_text().splitlines()[0]
    assert top == 'RAD Calculating... a-lock' and TD.OVERDRAW == [] and TD.OFFSCREEN == []
    s = KS.run('x' * 256 + '+')                     # no chip: the status reaches column 314
    s.mods['ui'].busy(512)
    assert TD.screen_text().splitlines()[0] == 'RAD Calculating..' and TD.OVERDRAW == []


# -- (d) set_color is called rarely ----------------------------------------------------------

def test_full_redraw_uses_few_colors():
    s = KS.run('2/3{enter}x^2+1{enter}sqrt(2){enter}12')
    u, d = s.mods['ui'], s.mods['draw']
    TD.reset()
    u.FULL = True
    u.redraw()
    assert TD.COUNTS['set_color'] <= 6
    TD.reset()
    u.redraw()                                      # nothing changed: no ti_draw call at all
    assert TD.CALLS == []
    u.key(92)                                       # a flat edit key: the entry row only
    assert [c for c in TD.CALLS if c[0] == 'fill_rect'] == [('fill_rect', -1, 169, 321, 21)]
    assert TD.COUNTS['set_color'] <= 2
    assert TD.COUNTS['draw_text'] == 1 and TD.COUNTS['draw_line'] == 1
    d.theme(1)
    TD.reset()
    u.FULL = True
    u.redraw()
    assert TD.COUNTS['set_color'] <= 6


def test_typing_costs_few_colors_per_key():
    keys = KS.parse('2/3{enter}' + 'x+1' * 6)
    s = KS.run(keys)
    assert s.colors <= 6 * len(keys)
    typing = KS.run('x+1' * 10)
    assert typing.colors <= 2 * 30 + 6 * 2          # MATHPRINT.md 10 (was 4 * 31 + 6 * 2)


def test_first_key_after_answer_keeps_stage():
    s = KS.run('2/3{enter}')
    u = s.mods['ui']
    TD.reset()
    u.key(92)
    assert [c for c in TD.CALLS if c[0] == 'fill_rect' and c[2] < 150 and c[2] != -1] == []
    assert ('fill_rect', -1, -1, 321, 211) not in TD.CALLS


def test_modifier_repaints_status_only():
    s = KS.run('2/3{enter}1+')
    u = s.mods['ui']
    TD.reset()
    u.key(21)
    assert [c for c in TD.CALLS if c[0] == 'fill_rect'] == [('fill_rect', -1, -1, 321, 20)]
    assert TD.COUNTS['set_color'] <= 3


def _counting(monkeypatch, d):
    calls = []
    for name in ('mlayout', 'mparse'):
        real = getattr(d, name)

        def wrapper(*a, _real=real, _name=name):
            calls.append(_name)
            return _real(*a)
        monkeypatch.setattr(d, name, wrapper)
    return calls


def test_arrows_do_no_layout(monkeypatch):
    s = KS.run('1{frac}2{right}+x^3')
    u, d = s.mods['ui'], s.mods['draw']
    calls = _counting(monkeypatch, d)
    for keys in ((24,), (26,), (25,), (34,), (21, 24)):
        for k in keys:
            u.key(k)
    assert calls == []


def test_caret_move_cost_is_flat(monkeypatch):
    s = KS.run('(1)/(2)+(1)/(3)+(1)/(4)+(1)/(5)')
    u, d = s.mods['ui'], s.mods['draw']
    assert u.LINE == '(1)/(2)+(1)/(3)+(1)/(4)+(1)/(5)' and u.EDMAP is not None
    calls = _counting(monkeypatch, d)
    ey = 190 - u.EH
    for j in range(10):
        del TD.CALLS[:]          # keep the framebuffer
        TD.COUNTS.clear()
        hv = u.HINTVIEW
        u.key(24)
        more = int(u.HINTVIEW != hv)    # the hint row, only when the slot's help changes
        assert TD.COUNTS['fill_rect'] == 1 + more, TD.CALLS
        assert TD.COUNTS.get('draw_text', 0) <= 2 + more, TD.CALLS
        assert TD.COUNTS['set_color'] <= 3 + 2 * more, TD.CALLS
        rows = [list(TD.FB[y]) for y in range(ey, 190)]
        u.EDIFF, u.EKEY = False, None
        u.redraw()
        u.EDIFF = True
        assert rows == [list(TD.FB[y]) for y in range(ey, 190)]
    assert calls == []


def test_2d_typing_cost():
    s = KS.run('1{frac}2{right}+1{frac}3{right}+')
    u = s.mods['ui']
    for k in (82, 83, 84):
        TD.reset()
        u.key(k)
        assert TD.COUNTS['set_color'] <= 3 and TD.COUNTS['fill_rect'] == 1, TD.CALLS
        assert TD.COUNTS.get('draw_text', 0) <= 3, TD.CALLS


# -- (e) panic with and without the engine -----------------------------------------------------

def test_panic_without_the_engine():
    s = KS.run('1+2')
    u = s.mods['ui']
    assert u.R is None
    TD.reset()
    u.panic(0)
    assert 'Out of memory' in TD.screen_text() and '1+2' in TD.screen_text()
    assert TD.OFFSCREEN == [] and TD.OVERDRAW == []
    u.key(45)
    assert u.LINE == '' and u.STATUS == '' and 'menu' in TD.screen_text()
    assert u.R is None


def test_panic_with_the_engine_and_a_long_answer():
    s = KS.run('expand((x+1)^12){enter}')
    u = s.mods['ui']
    TD.reset()
    u.panic(3)
    screen = TD.screen_text()
    assert 'Display error' in screen and 'expand((x+1)^12)' in screen and '...' in screen
    assert TD.OFFSCREEN == []


def test_entry_loop_recovers_before_the_engine(monkeypatch):
    # a drawing failure before the engine exists: casevo's handler calls U.panic, and the
    # next key redraws normally, still without the engine
    real = TD.draw_text

    def flaky(x, y, s):
        if s.startswith('Integrand'):
            raise MemoryError('the hint line')
        real(x, y, s)

    monkeypatch.setattr(TD, 'draw_text', flaky)
    s = KS.run('int({snap:panic}{clear}{snap:after}')
    assert 'Out of memory' in s.snap('panic') and 'int(' in s.snap('panic')
    assert 'menu' in s.snap('after') and 'Out of memory' not in s.snap('after')
    assert 'run' not in s.mods and s.offscreen == []


# -- timing ------------------------------------------------------------------------------------

def test_boot_and_engine_times_are_recorded_and_shown():
    s = KS.run('{snap:boot}1+1{enter}{snap:answer}2{enter}{snap:later}')
    u = s.mods['ui']
    assert isinstance(u.BOOT_MS, int) and u.BOOT_MS >= 0
    assert isinstance(u.ENGINE_MS, int) and u.ENGINE_MS >= 0
    assert re.search(r'ready \d+\.\ds', s.snap('boot').splitlines()[0])
    assert ('engine ' + u.secs(u.ENGINE_MS)) in s.snap('answer').splitlines()[0]
    assert 'engine' not in s.snap('later').splitlines()[0]
    assert u.secs(3150) == '3.1s' and u.secs(None) == '?' and u.secs(-1) == '?'


def test_timing_without_any_clock():
    got = child('''
import json
import time
del time.monotonic
import keyscript as KS
s = KS.run('{snap:boot}1+1{enter}{snap:answer}')
u = s.mods['ui']
print(json.dumps([u.BOOT_MS, u.ENGINE_MS, s.snap('boot').splitlines()[0],
                  s.snap('answer').splitlines()[0], s.ans]))
''')
    assert got[:2] == [None, None]
    assert got[2] == 'RAD ready' and got[3] == 'RAD engine loaded' and got[4] == '2'


def test_timing_with_ticks_ms_only():
    got = child('''
import json
import time
del time.monotonic
TICK = [1000]
def ticks_ms():
    TICK[0] += 7
    return TICK[0]
time.ticks_ms = ticks_ms
time.ticks_diff = lambda a, b: a - b
import keyscript as KS
s = KS.run('{snap:boot}1+1{enter}')
u = s.mods['ui']
print(json.dumps([u.BOOT_MS, u.ENGINE_MS, s.snap('boot').splitlines()[0]]))
''')
    assert got == [7, 7, 'RAD ready 0.0s']
