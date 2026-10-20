"""Acceptance of the packed calculator release itself (docs/notes/FASTBOOT.md).

The harness (build/check_release.py) imports the actual release packs with MicroPython's import
rules and the strict EVO depth model. A fake heap charges loaded packs their estimates, so the
loader's eviction, soft-pack and admission paths run as on the calculator.
"""
import ast
import builtins
import hashlib
import importlib.util
import json
import types
from pathlib import Path

import pytest
import cascheck as C


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('check_release', ROOT / 'build/check_release.py')


def load_release_module():
    meta = ROOT / 'dist/release.json'
    if not (ROOT / 'dist/CASEVO.py').is_file() or not meta.is_file():
        pytest.skip('packaged artifact absent; run python build/release.py')
    if json.loads(meta.read_text('ascii')).get('format') != 'packs-v1':
        pytest.skip('dist holds an older release format; run python build/release.py')
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def release_module():
    return load_release_module()


@pytest.fixture(scope='module')
def booted(release_module):
    return release_module.Release().boot()


@pytest.fixture
def app(booted):
    booted.total = None
    booted.fail = None
    booted.reset_session()
    return booted


def corpus():
    rows = []
    for tier in ('t1', 't2', 't3'):
        for line in (ROOT / 'tests/corpus' / (tier + '.tsv')).read_text().splitlines():
            if line and not line.startswith('#'):
                fields = line.split('\t')
                if tier == 't1':
                    command, kind, expected = fields[:3]
                else:
                    command, expected = fields
                    kind = 'eq'
                rows.append(pytest.param(command, kind, expected, id=tier + ':' + command))
    return rows


@pytest.mark.parametrize('command,kind,expected', corpus())
def test_packaged_corpora(app, command, kind, expected):
    result = app.go(command)
    assert result[0] == ('msg' if kind == 'msg' else 'ans'), (command, result)
    if kind in ('msg', 'text'):
        assert result[1] == expected
    elif kind == 'roots':
        ours = [part.split('=', 1)[1] for part in result[1].split(',')]
        wanted = expected.split(';')
        assert len(ours) == len(wanted)
        for actual, want in zip(ours, wanted):
            C.equivalent(actual, want)
    else:
        C.equivalent(result[1], expected)
    app.assert_clean()


def pack(app, src):
    return app.meta['owner'][app.device(src)]


def test_families_load_once_and_stay_while_memory_allows(app):
    del app.loads[:]
    for _ in range(3):
        assert app.go('simplify(sin(x)^2+cos(x)^2)')[1] == '1'
        assert app.go('diff(x^3,x)')[1] == '3*x^2'
    assert app.loads.count(pack(app, 'norm')) == 1, app.loads
    assert app.loads.count(pack(app, 'printer')) <= 1, app.loads
    assert 1 < app.max_depth <= 8
    app.assert_clean()


def test_failed_integral_strategies_remain_cached(app):
    app.loads.clear()
    assert app.go('integrate(sin(x)^21,x)')[:2] == ('ans', 'integrate(sin(x)^21,x)')
    for name in ('CASIN2', 'CASIN2B', 'CASIN3', 'CASIN3B'):
        assert app.loads.count(name) <= 1, app.loads
    assert len(app.loads) < 20
    app.assert_clean()


def test_giant_powers_load_their_aux_pack_only_when_met(app):
    """DESIGN 6.1: the code for powers too large to fold is an aux pack. node's constructors
    keep only a cheap test, so a plain session never loads it; a giant power loads it once and
    gives the same exact answers as the source tree."""
    big = pack(app, 'nodeb')
    assert app.meta['kinds'][big] == 'aux' and big not in app.modules, app.modules
    del app.loads[:]
    for command, want in (('2+3', '5'), ('diff(x^3,x)', '3*x^2'), ('2^1000', str(2 ** 1000)),
                          ('sqrt(8)/2', 'sqrt(2)'), ('factor(360)', '2^3*3^2*5'),
                          ('integrate(x^2,x,0,1)', '1/3'), ('expand((x+1)^3)', 'x^3+3*x^2+3*x+1'),
                          ('ln(8)', '3*ln(2)'), ('abs(x/2-1)', 'abs(x-2)/2')):
        assert app.go(command)[:2] == ('ans', want), command
        app.assert_clean()
    assert big not in app.loads, app.loads
    for command, want in (('3^(2^20)', '3^1048576'), ('2^100000*2', '2^100001'),
                          ('2^100000+2^100000', '2^100001'), ('sqrt(2^100001)', '2^(100001/2)'),
                          ('log(10^100000)', '100000'), ('abs(x/2+2^99999)', 'abs(x/2+2^99999)'),
                          ('2^100000*oo', 'oo')):
        assert app.go(command)[:2] == ('ans', want), command
        app.assert_clean()
    for command in ('expand((2^100000+x)^2)', '(3+4*i)^100000/(3+4*i)^99999',
                    '2*10^100000+3*10^100000-5*10^100000',
                    'solve((2*10^100000+3*10^100000-5*10^100000)*x=1,x)'):
        assert app.go(command)[:2] == ('msg', 'number too large')
        assert app.go('2+3')[:2] == ('ans', '5')
        app.assert_clean()
    assert app.loads.count(big) == 1, app.loads
    assert app.max_depth <= 8


def test_tight_heap_evicts_clears_and_reloads(app):
    commands = (('factor(x^4-1)', '(x-1)*(x+1)*(x^2+1)'), ('limit(sin(x)/x,x,0)', '1'),
                ('integrate(x^2,x,0,1)', '1/3'), ('solve(x^2-5*x+6=0,x)', 'x=2,x=3'),
                ('sum(k^2,k,1,10)', '385'))
    app.go('2+3')
    core = sum(app.cost(n) for n in app.modules if app.meta['kinds'][n] in ('core', 'ui'))
    app.total = core + 60000            # room for a family or two, never for all of them
    del app.loads[:]
    held = {}
    for _ in range(2):
        for command, want in commands:
            result = app.go(command)
            assert result[:2] == ('ans', want), (command, result)
            app.assert_clean()
            for name, module in app.modules.items():
                held.setdefault(name, module)
    assert len(app.loads) > len(set(app.loads)), app.loads     # something was evicted
    final = app.final('run', 'need')
    for name, module in held.items():
        if app.modules.get(name) is not module and app.meta['kinds'][name] not in ('core', 'ui'):
            # an evicted pack is cleared, so a stale stack word cannot keep its code alive
            assert all(getattr(module, k) is None for k in dir(module) if k[:2] != '__'), name
    assert getattr(app.module('run'), final) is not None


def test_out_of_memory_cleans_and_recovers(app):
    app.total = 0
    result = app.go('integrate(x^2,x,0,1)')
    assert result[:2] == ('msg', 'Out of memory'), result
    app.assert_clean()
    app.total = None
    assert app.go('integrate(x^2,x,0,1)')[1] == '1/3'
    app.assert_clean()


def test_a_pack_body_failing_with_memory_error_is_unloaded_and_retried(app):
    app.go('2+3')                       # the input and printer packs are loaded and idle
    target = pack(app, 'defint')
    app.fail = {target: MemoryError('pack body')}
    assert app.go('integrate(x^2,x,0,1)')[1] == '1/3'
    assert not app.fail                 # the failure happened, then a retry succeeded
    assert app.loads.count(target) >= 2
    app.assert_clean()


def test_a_failing_family_import_reports_and_does_not_poison_the_session(app):
    target = pack(app, 'diff')
    app.fail = {target: ImportError('missing pack')}
    with app.traced():
        result = app.get('run', 'go')(('eval', 'diff(x^3,x)'))
    assert result[:2] == ('msg', 'internal error: ImportError'), result
    assert target not in app.modules
    assert app.go('diff(x^3,x)')[1] == '3*x^2'
    app.assert_clean()


def test_view_packs_only_unload_while_computing(app):
    view = [p for p, k in app.meta['kinds'].items() if k == 'view']
    assert view
    for name in view:
        app._import(name)
    shed = app.get('run', 'shed')
    with app.traced():
        while shed():
            pass
    assert all(name in app.modules for name in view)        # menus may be running
    app.set('run', 'INGO', True)
    try:
        with app.traced():
            while shed():
                pass
    finally:
        app.set('run', 'INGO', False)
    assert not any(name in app.modules for name in view)


def test_arithmetic_keeps_the_layout_pack_and_family_commands_shed_it(app):
    view = [p for p, k in app.meta['kinds'].items() if k == 'view']
    app.go('2+3')
    for name in view:
        app._import(name)
    app.total = sum(app.cost(n) for n in app.modules) + 40000   # below SHEDAT after parsing
    assert app.go('3*4')[1] == '12'
    assert all(name in app.modules for name in view)      # no reload just to show 12
    assert app.go('diff(x^3,x)')[1] == '3*x^2'
    assert not any(name in app.modules for name in view)
    app.assert_clean()


def kind(app, wanted):
    return [p for p, k in app.meta['kinds'].items() if k == wanted]


def test_every_pack_ends_with_its_completion_marker(booted):
    for pack in booted.meta['kinds']:
        last = (booted.dist / (pack + '.py')).read_text('ascii').rstrip().splitlines()[-1]
        assert last.replace(' ', '') == '__ok__=1', pack


def test_soft_and_aux_packs_cut_short_are_imported_again(app):
    # MicroPython 1.12 keeps a module whose import ran out of memory; a later command would
    # fail on it with AttributeError for the rest of the session
    app.go('2+3')
    for name in kind(app, 'soft') + kind(app, 'aux'):
        app.modules[name] = types.ModuleType(name)
    assert app.go('sqrt(8)')[1] == '2*sqrt(2)'
    assert app.go('solve(x^2-5*x+6=0,x)')[1] == 'x=2,x=3'
    for name in kind(app, 'soft') + kind(app, 'aux'):
        assert name not in app.modules or getattr(app.modules[name], '__ok__', None) == 1
    app.assert_clean()


def test_out_of_memory_cleanup_never_raises_when_dir_runs_out(app):
    # unload's clearing loop calls dir(), which allocates: in go()'s Out-of-memory cleanup
    # (evict_all) that used to raise out of go(), which must never raise
    app.go('2+3')
    real, calls, state = builtins.dir, [], {'armed': False}

    def observe(frame):
        if frame.f_code.co_name == app.final('run', 'evict_all'):
            # Admission may already have shed every soft pack before this cleanup. Leave a
            # known auxiliary module for unload(), independent of pack sizes/cache policy,
            # so the allocation failure is actually injected rather than merely expected.
            name = pack(app, 'nodeb')
            app.modules[name] = types.ModuleType(name)
            state['armed'] = True

    def dir_(*args):
        if state['armed']:
            state['armed'] = False
            calls.append(1)
            raise MemoryError('dir')
        return real(*args)
    app.builtins['dir'] = dir_
    app.observer = observe
    app.total = 0
    try:
        result = app.go('integrate(x^2,x,0,1)')
    finally:
        app.builtins['dir'] = real
        app.observer = None
        app.total = None
    assert result[:2] == ('msg', 'Out of memory') and calls, result
    assert app.go('integrate(x^2,x,0,1)')[1] == '1/3'
    app.assert_clean()


def test_a_view_pack_cut_short_is_imported_again_after_a_command(release_module):
    app = release_module.Release()
    view = kind(app, 'view')[0]
    state = {'armed': True}

    def observe(frame):
        if state['armed'] and frame.f_code.co_name == app.final('run', 'go'):
            state['armed'] = False
            app.modules[view] = types.ModuleType(view)      # its reload ran out of memory
    app.observer = observe
    app.run('2+3{enter}3*4{enter}{2nd,mode}')
    app.observer = None
    assert app.ended == 'quit' and app.get('run', 'ANS') == '12'
    assert 'Display error' not in app.screen
    app.assert_clean()


def test_2nd_mode_quits_even_when_the_view_pack_cannot_load(release_module):
    app = release_module.Release()
    view = kind(app, 'view')[0]

    class Always(dict):
        def pop(self, key, *default):
            return self[key]

    def observe(frame):
        if frame.f_code.co_name == app.final('ui', 'key') and app.fail is None:
            app.fail = Always({view: MemoryError('view')})
            app.modules[view] = types.ModuleType(view)
    app.observer = observe
    app.run('2+3{enter}{2nd,mode}')
    app.observer = None
    app.fail = None
    assert app.ended == 'quit'


def test_a_menu_without_memory_shows_out_of_memory_and_the_session_goes_on(release_module):
    app = release_module.Release()
    state = {'armed': False}

    def observe(frame):
        name = frame.f_code.co_name
        if name == app.final('run', 'need') and state['armed'] and \
                not app.get('run', 'INGO'):
            state['armed'] = False
            app.total = 0
        elif name == app.final('ui', 'panic'):
            app.total = None
        elif name == app.final('ui', 'show'):
            state['armed'] = True
    app.observer = observe
    app.run('2+3{enter}{f1}{snap:low}{clear}{clear}6*7{enter}{2nd,mode}')
    app.observer = None
    assert 'Out of memory' in app.snaps['low']
    assert app.ended == 'quit' and app.get('run', 'ANS') == '42'
    app.assert_clean()


def test_session_globals_survive_eviction(app):
    assert app.go('2=>a')[1] == '2'
    assert app.go('f(x)=a*x+1')[:2] == ('msg', 'f(x) defined')
    with app.traced():
        app.get('run', 'evict_all')()
    assert app.go('f(3)')[1] == '7'
    assert app.go('ans()*2')[1] == '14'
    assert app.get('run', 'VARS') == {'a': '2'}
    assert app.get('run', 'FUNCS') == {'f': (('x',), 'a*x+1')}
    app.assert_clean()


def test_boot_loads_only_the_ui(release_module):
    app = release_module.Release().run('{snap:boot}')
    kinds = set(app.meta['kinds'][n] for n in app.loads)
    assert kinds <= {'ui', 'view'}, app.loads
    assert 'cas-evo' in app.snaps['boot'] or app.snaps['boot']


def test_first_enter_loads_the_engine_once(release_module):
    app = release_module.Release().run('2+3{enter}3*4{enter}{2nd,mode}')
    assert app.ended == 'quit'
    assert app.get('run', 'ANS') == '12'
    core = [n for n in app.loads if app.meta['kinds'][n] == 'core']
    assert sorted(core) == sorted(set(core)), app.loads
    app.assert_clean()


@pytest.mark.parametrize('script,answer', [
    ('2+3{enter}*2{enter}', '10'),
    ('2+3{enter}{2nd,enter}{enter}', '5'),
    ('x+1{f1}{down}{enter}{enter}', 'x+1'),
    ('sqrt(2){enter}{f4}{f3}{down}{enter}{clear}', '1.4142135623731'),
    ('2/3{enter}{f2}{enter}{enter}', '2/3'),
    ('expand((x+y)^20){enter}{clear@1}2+3{enter}', '5'),
    # the MathPrint editor in the packs (docs/notes/MATHPRINT.md 2-4, 8): the picker, the
    # fraction and power keys, DEL unwrapping a fraction, and the Classic setting
    ('{2nd,frac}316{right}+1{frac}2{right}*2^3{enter}', '8'),
    ('1{frac}2{del}{del}5{enter}', '15'),
    ('{f3}6{clear}1{frac}2+1{enter}', '3/2'),          # Classic: 1/2+1, not (1)/(2+1)
])
def test_actual_entry_editor_menus_forms_and_cancel(release_module, script, answer):
    app = release_module.Release().run(script)
    assert app.get('run', 'ANS') == answer
    assert 'Display error' not in app.screen and 'internal error' not in app.screen
    app.assert_clean()
    assert 1 < app.max_depth <= 8


def test_actual_entry_keyboard_interrupt_recovers(release_module):
    app = release_module.Release().run(
        'expand((x+y)^20){enter}{on@1}{snap:interrupted}{clear}2+3{enter}')
    assert 'Interrupted' in app.snaps['interrupted']
    assert app.get('run', 'ANS') == '5'
    assert release_module.TS.FIRED == [(1, release_module.TS.ON)]
    app.assert_clean()


def test_actual_entry_out_of_memory_shows_and_recovers(release_module):
    app = release_module.Release()
    state = {'armed': True}

    def observe(frame):
        if state['armed'] and frame.f_code.co_name == app.final('run', 'need'):
            state['armed'] = False
            app.total = 0
        elif not state['armed'] and frame.f_code.co_name == app.final('ui', 'panic'):
            app.total = None

    app.observer = observe
    app.run('2+3{enter}integrate(x^2,x,0,1){enter}{snap:low}{clear}2+3{enter}')
    app.observer = None
    assert 'Out of memory' in app.snaps['low']
    assert app.get('run', 'ANS') == '5'
    app.assert_clean()


def test_package_integrity_and_line_map(booted):
    meta = booted.meta
    assert meta['format'] == 'packs-v1'
    assert meta['transfer_check']['fits_converter_limit']
    assert meta['total_source_bytes'] < 3_500_000
    for name, info in meta['files'].items():
        content = (booted.dist / name).read_bytes()
        assert len(content) == info['bytes']
        assert hashlib.sha256(content).hexdigest() == info['sha256']
        ast.parse(content.decode('ascii'), feature_version=(3, 4))
    for name in meta['launchers']:
        assert meta['files'][name]['bytes'] < 65509
    kinds = set(meta['kinds'].values())
    assert {'ui', 'core', 'family', 'soft', 'view'} <= kinds
    for pack, size in meta['mpy_estimate'].items():
        assert size <= 60000, pack
        lines = meta['linemap'][pack]['lines']
        text = (booted.dist / (pack + '.py')).read_text('ascii').splitlines()
        assert len(lines) == len(text)
        mapped = [entry for entry in lines if entry]
        assert mapped, pack
        for first, last, src in mapped:
            assert src.startswith('src/') and 0 < first <= last, (pack, src)
    # every runtime key resolves to a pack that exists
    run = booted.module('run')
    for key, name in getattr(run, booted.final('run', 'DEV')).items():
        if name in meta['kinds']:
            assert (booted.dist / (name + '.py')).is_file()


def test_engine_load_failure_rolls_back_and_the_next_enter_loads_it(release_module):
    app = release_module.Release()
    run_pack = app.meta['owner'][app.device('run')]
    app.fail = {run_pack: MemoryError('engine')}
    app.run('2+3{enter}{snap:failed}{clear}2+3{enter}')
    assert 'Out of memory' in app.snaps['failed']
    assert app.loads.count(run_pack) == 2           # the half-run module was not reused
    assert app.get('run', 'ANS') == '5'
    app.assert_clean()
