"""Acceptance of the compressed, single-file calculator artifact itself."""
import ast
import hashlib
import importlib.util
from pathlib import Path

import pytest
import cascheck as C


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('check_release', ROOT / 'build/check_release.py')


@pytest.fixture(scope='module')
def release_module():
    if not (ROOT / 'dist/CASEVO.py').is_file() or not (ROOT / 'dist/release.json').is_file():
        pytest.skip('single-file artifact absent; run python build/release.py')
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def booted(release_module):
    return release_module.Release().boot()


@pytest.fixture
def app(booted):
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
def test_single_file_corpora(app, command, kind, expected):
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


def test_dynamic_function_frames_are_observed(app):
    assert app.go('diff(x^3,x)')[1] == '3*x^2'
    assert any(Path(path).stem in app.meta['payloads'] and name == app.name('g_eval')
               for path, name in app.seen)
    assert any(Path(path).stem == 'CVDIFF' and name == app.name('g_deriv')
               for path, name in app.seen)
    assert 1 < app.max_depth <= 8
    assert not any(name.startswith('CV') for name in app.imports)


def test_phase_boundaries_during_math_and_output(app):
    events = []

    def observe(frame, phase):
        if frame.f_code.co_name in (app.name('g_eval'), app.name('record')):
            events.append((frame.f_code.co_name, phase))

    app.observer = observe
    try:
        assert app.go('2+3')[1] == '5'
    finally:
        app.observer = None
    assert any(name == app.name('g_eval') and phase == () for name, phase in events)
    assert any(name == app.name('record') and phase == ('print',) for name, phase in events)
    assert app.module('CVPH')['ACTIVE'] == {}
    for module, groups in app.meta['groups'].items():
        namespace = app.env.get(module, {})
        for phase in ('input', 'print'):
            assert all(name not in namespace for name in groups.get(phase, ()))


def test_memory_admission_failure_cleans_and_recovers(app):
    app.free_memory = 0
    try:
        result = app.go('2+3')
        assert result[:2] == ('msg', 'Out of memory'), result
        app.assert_clean()
        assert app.module('CVPH')['ACTIVE'] == {}
    finally:
        app.free_memory = 175 * 1024
    assert app.go('2+3')[1] == '5'


def test_mid_phase_admission_failure_removes_already_loaded_definitions(app):
    chunks = []

    def observe(frame, phase):
        if frame.f_code.co_name == 'part':
            chunks.append(frame.f_locals['name'])
            if len(chunks) == 2:
                app.free_memory = 0

    app.observer = observe
    try:
        assert app.go('2+3')[:2] == ('msg', 'Out of memory')
        assert len(chunks) == 2
        for module, groups in app.meta['groups'].items():
            assert all(name not in app.env.get(module, {}) for name in groups.get('input', ()))
        assert app.module('CVPH')['ACTIVE'] == {}
        assert app.module('CVPH')['CURRENT'] is None
        app.assert_clean()
    finally:
        app.observer = None
        app.free_memory = 175 * 1024
    assert app.go('2+3')[1] == '5'


def test_session_globals_survive_phase_eviction(app):
    assert app.go('2=>a')[1] == '2'
    assert app.go('f(x)=a*x+1')[:2] == ('msg', 'f(x) defined')
    assert app.go('f(3)')[1] == '7'
    assert app.go('ans()*2')[1] == '14'
    assert app.get('run', 'VARS') == {'a': '2'}
    assert app.get('run', 'FUNCS') == {'f': (('x',), 'a*x+1')}
    assert len(app.get('run', 'HIST')) == 4
    app.assert_clean()


@pytest.mark.parametrize('script,answer', [
    ('2+3{enter}*2{enter}', '10'),
    ('2+3{enter}{2nd,enter}{enter}', '5'),
    ('x+1{f1}{down}{enter}{enter}', 'x+1'),
    ('sqrt(2){enter}{f4}{f3}{down}{enter}{clear}', '1.4142135623731'),
    ('2/3{enter}{f2}{enter}{enter}', '2/3'),
    ('expand((x+y)^20){enter}{clear@1}2+3{enter}', '5'),
])
def test_actual_entry_editor_menus_forms_and_cancel(release_module, script, answer):
    app = release_module.Release().run(script)
    assert app.get('run', 'ANS') == answer
    assert 'Display error' not in app.screen and 'internal error' not in app.screen
    assert app.module('CVPH')['ACTIVE'] == {'ui': True}
    app.assert_clean()
    assert 1 < app.max_depth <= 8


def test_actual_entry_loads_ui_before_interaction(release_module):
    app = release_module.Release()
    states = []

    def observe(frame, phase):
        if frame.f_code.co_name == app.name('key'):
            states.append(phase)

    app.observer = observe
    app.run('2+3{enter}{f1}{clear}')
    assert states and all(state == ('ui',) for state in states)


def test_actual_entry_keyboard_interrupt_recovers(release_module):
    app = release_module.Release().run(
        'expand((x+y)^20){enter}{on@1}{snap:interrupted}{clear}2+3{enter}')
    assert 'Interrupted' in app.snaps['interrupted']
    assert app.get('run', 'ANS') == '5'
    assert app.module('CVPH')['ACTIVE'] == {'ui': True}
    assert release_module.TS.FIRED == [(1, release_module.TS.ON)]
    app.assert_clean()


def test_actual_entry_repeated_ui_admission_failure_recovers(release_module):
    app = release_module.Release()
    state = {'armed': True, 'panics': []}

    def observe(frame, phase):
        name = frame.f_code.co_name
        if name == app.name('finish') and state['armed']:
            state['armed'] = False
            app.free_memory = 0
        elif name == app.name('panic'):
            state['panics'].append(phase)
            if len(state['panics']) == 2:
                app.free_memory = 175 * 1024

    app.observer = observe
    app.run('2+3{enter}{snap:low}1{snap:low-again}{clear}2+3{enter}')
    assert state['panics'] == [(), ()]
    assert 'Out of memory' in app.snaps['low']
    assert 'Out of memory' in app.snaps['low-again']
    assert '2+3' in app.snaps['low-again']
    assert app.get('run', 'ANS') == '5'
    assert app.module('CVPH')['ACTIVE'] == {'ui': True}
    app.assert_clean()


def test_actual_entry_mode_exits_when_ui_cannot_load(release_module):
    app = release_module.Release()

    def observe(frame, phase):
        if frame.f_code.co_name == app.name('finish'):
            app.free_memory = 0

    app.observer = observe
    app.run('2+3{enter}{mode}')
    assert app.ended == 'quit'
    assert 'Out of memory' in app.screen
    assert app.module('CVPH')['ACTIVE'] == {}
    app.assert_clean()


def test_archive_integrity_compatibility_and_single_file_contract(booted):
    data = booted.path.read_bytes()
    assert len(data) == booted.meta['file_bytes'] < 3_500_000
    assert hashlib.sha256(data).hexdigest() == booted.meta['sha256']
    ast.parse(data.decode('ascii'), feature_version=(3, 4))
    with booted.traced():
        for name, records in booted.globals['_data'].items():
            source = booted.globals['_decode'](records)
            assert len(source.encode('ascii')) == booted.meta['sources'][name]
            assert source == (booted.dist / 'blocks' / (name + '.py')).read_text('ascii')
            tree = ast.parse(source, feature_version=(3, 4))
            for node in ast.walk(tree):
                imports = ([a.name for a in node.names] if isinstance(node, ast.Import)
                           else [node.module] if isinstance(node, ast.ImportFrom) else [])
                assert not any(name.startswith('CV') or name == 'CASEVO' for name in imports)


def test_corrupt_compressed_payload_is_rejected(booted):
    records = next(iter(booted.globals['_data'].values()))
    assert isinstance(records, bytes)
    corrupt = bytearray(records)
    corrupt[9] ^= 1  # First chunk header's bit count; preserve the payload bytes.
    with booted.traced(), pytest.raises(ValueError, match='corrupt source'):
        booted.globals['_decode'](bytes(corrupt))
