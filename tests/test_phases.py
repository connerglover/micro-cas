"""Build-time phase packing preserves device namespaces without wrapper functions."""
import gc
import importlib
import importlib.util
import sys
import weakref
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('phase_builder', ROOT / 'build' / 'phases.py')


def builder():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


@pytest.fixture
def install(tmp_path, monkeypatch):
    made = []

    def run(sources, groups, target_lines=120, free=10 ** 9):
        facades, extras, metadata = builder().pack(sources, groups, target_lines)
        for name, source in dict(facades, **extras).items():
            (tmp_path / (name + '.py')).write_text(source, encoding='ascii')
            made.append(name)
            sys.modules.pop(name, None)
        monkeypatch.syspath_prepend(str(tmp_path))
        importlib.invalidate_caches()
        controller = importlib.import_module('CVPH')
        controller.MEMFREE = lambda: free
        return controller, facades, extras, metadata

    yield run
    for name in made:
        sys.modules.pop(name, None)


def test_shared_globals_and_explicit_phases(install):
    controller, _, _, metadata = install({'CVDEMO':
        'N=2\ndef get():\n return N\ndef inc():\n global N\n N+=1\n return N\n'},
        {'CVDEMO': {'input': ['inc', 'get']}})
    module = importlib.import_module('CVDEMO')
    assert not hasattr(module, 'get')
    controller.load('input')
    assert module.get.__globals__ is module.__dict__
    assert module.inc() == module.get() == module.N == 3
    controller.load('input')
    assert module.get() == 3
    assert not any(name in sys.modules for name in metadata['payloads'])
    controller.unload('input')
    assert module.N == 3 and not hasattr(module, 'inc')
    controller.load('input')
    assert module.inc() == 4


def test_eviction_leaves_no_controller_function_references(install):
    controller, _, _, _ = install({'CVDEMO': 'def get():\n return 5\n'},
                                 {'CVDEMO': {'output': ['get']}})
    module = importlib.import_module('CVDEMO')
    controller.load('output')
    ref = weakref.ref(module.get)
    controller.unload('output')
    gc.collect()
    assert ref() is None
    assert controller.ACTIVE == {}
    controller.unload('output')


def test_resident_chunks_preserve_original_statement_and_default_order(install):
    source = ('MAX=7\ndef first(x=MAX):\n return x\n'
              'TABLE=(first,)\nMAX=11\ndef second(x=first()):\n return x+MAX\n'
              'VALUE=second()\ndef later():\n return VALUE\n')
    controller, facades, _, metadata = install({'CVDEMO': source},
        {'CVDEMO': {'resident': ['later', 'second', 'first']}}, target_lines=20)
    module = importlib.import_module('CVDEMO')
    assert module.TABLE[0] is module.first
    assert module.first() == 7 and module.second() == 18
    assert module.later() == module.VALUE == 18
    assert len(metadata['payloads']) == 3
    assert facades['CVDEMO'].count('CVPH.part(') == 3
    assert 'resident' not in controller.PHASES


def test_explicit_definition_defaults_follow_source_order(install):
    controller, _, _, _ = install({'CVDEMO':
        'MAX=6\ndef a():\n return MAX\ndef b(value=a()):\n return value\n'},
        {'CVDEMO': {'input': ['b', 'a']}}, target_lines=2)
    module = importlib.import_module('CVDEMO')
    controller.load('input')
    assert module.b() == 6


def test_metadata_reports_real_oversize_and_source_locations(install):
    source = 'X=1\ndef big():\n a=2\n b=3\n return a+b\ndef small():\n return X\n'
    _, _, extras, metadata = install({'CVDEMO': source},
        {'CVDEMO': {'input': ['big', 'small']}}, target_lines=3)
    records = list(metadata['payloads'].values())
    assert [r['source_lines'] for r in records] == [4, 2]
    assert records[0]['oversize'] and not records[1]['oversize']
    assert records[0]['functions'] == [{'name': 'big', 'source_first_line': 2,
        'source_last_line': 5, 'payload_first_line': 1}]
    for name, record in metadata['payloads'].items():
        payload = {}
        exec(extras[name], payload)
        assert record['source_bytes'] == len(payload['CODE'].encode('ascii'))
        assert record['required_free'] == (record['source_lines'] * 80 +
                                           record['source_bytes'] * 2 + 3072)
        assert len(name) <= 8
        assert len(extras[name].splitlines()) == 1


def test_heap_guard_rejects_before_import_or_partial_phase(install, monkeypatch):
    controller, _, _, _ = install({'CVDEMO':
        'def a():\n return 1\ndef b():\n return 2\n'},
        {'CVDEMO': {'input': ['a', 'b']}}, target_lines=2, free=0)
    module = importlib.import_module('CVDEMO')
    seen = []
    original = __import__

    def watch(name, *args, **kwargs):
        seen.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(controller, '__import__', watch, raising=False)
    with pytest.raises(MemoryError):
        controller.load('input')
    assert seen == [] and controller.ACTIVE == {}
    assert not hasattr(module, 'a') and not hasattr(module, 'b')


def test_later_chunk_failure_rolls_back_and_cleans_imports(install):
    controller, _, _, metadata = install({'CVDEMO':
        'def a():\n return 1\ndef b(value=missing):\n return value\n'},
        {'CVDEMO': {'input': ['a', 'b']}}, target_lines=2)
    module = importlib.import_module('CVDEMO')
    with pytest.raises(NameError):
        controller.load('input')
    assert not hasattr(module, 'a') and not hasattr(module, 'b')
    assert controller.ACTIVE == {} and controller.CURRENT is None
    assert not any(name in sys.modules for name in metadata['payloads'])
    module.missing = 42
    controller.load('input')
    assert module.a() == 1 and module.b() == 42


def test_heap_is_checked_again_after_each_chunk(install):
    controller, _, _, metadata = install({'CVDEMO':
        'def a():\n return 1\ndef b():\n return 2\n'},
        {'CVDEMO': {'input': ['a', 'b']}}, target_lines=2)
    module = importlib.import_module('CVDEMO')
    available = iter((10 ** 9, 10 ** 9, 0))
    controller.MEMFREE = lambda: next(available)
    with pytest.raises(MemoryError):
        controller.load('input')
    assert not hasattr(module, 'a') and not hasattr(module, 'b')
    assert controller.ACTIVE == {}
    assert not any(name in sys.modules for name in metadata['payloads'])


def test_failed_resident_import_drops_registered_namespace(install):
    controller, _, _, metadata = install({'CVDEMO':
        'def a():\n return 1\ndef b():\n return 2\n'},
        {'CVDEMO': {'resident': ['a', 'b']}}, target_lines=2)
    available = iter((10 ** 9, 0))
    controller.MEMFREE = lambda: next(available)
    with pytest.raises(MemoryError):
        importlib.import_module('CVDEMO')
    assert 'CVDEMO' not in controller.REG and 'CVDEMO' not in sys.modules
    assert not any(name in sys.modules for name in metadata['payloads'])


def test_phase_preflights_all_registered_modules_before_loading(install):
    controller, _, _, _ = install({
        'CVFIRST': 'def a():\n return 1\n',
        'CVSECOND': 'def b():\n return 2\n'}, {
        'CVFIRST': {'input': ['a']}, 'CVSECOND': {'input': ['b']}})
    first = importlib.import_module('CVFIRST')
    with pytest.raises(KeyError, match='CVSECOND'):
        controller.load('input')
    assert not hasattr(first, 'a')
    second = importlib.import_module('CVSECOND')
    controller.load('input')
    assert first.a() == 1 and second.b() == 2
    controller.unload('input')
    assert not hasattr(first, 'a') and not hasattr(second, 'b')


def test_partial_payload_failure_cleans_earlier_definitions(install):
    controller, _, _, _ = install({'CVDEMO':
        'def a():\n return 1\ndef b(value=missing):\n return value\n'},
        {'CVDEMO': {'input': ['a', 'b']}})
    module = importlib.import_module('CVDEMO')
    with pytest.raises(NameError):
        controller.load('input')
    assert not hasattr(module, 'a') and controller.ACTIVE == {}


def test_custom_exec_has_payload_identity_and_shared_namespace(install, monkeypatch):
    controller, _, _, metadata = install({'CVDEMO': 'def a():\n return 3\n'},
                                        {'CVDEMO': {'input': ['a']}})
    module = importlib.import_module('CVDEMO')
    seen = []

    def named_exec(source, namespace):
        key, name = controller.CURRENT
        seen.append((key, name))
        exec(compile(source, name + '.py', 'exec'), namespace)

    monkeypatch.setattr(controller, 'exec', named_exec, raising=False)
    controller.load('input')
    name = next(iter(metadata['payloads']))
    assert seen == [('CVDEMO', name)]
    assert module.a.__code__.co_filename == name + '.py'


@pytest.mark.parametrize('groups, message', [
    ({'MISSING': {'input': ['a']}}, 'unknown module'),
    ({'CVDEMO': {'input': ['missing']}}, 'unknown function'),
    ({'CVDEMO': {'input': ['a'], 'output': ['a']}}, 'multiple phases'),
])
def test_invalid_groups_rejected(groups, message):
    with pytest.raises(ValueError, match=message):
        builder().pack({'CVDEMO': 'def a():\n return 1\n'}, groups)


def test_pack_is_deterministic_and_keeps_unselected_source():
    module = builder()
    sources = {'CVSECOND': 'def b():\n return 2\n',
               'CVFIRST': 'X=3\ndef a():\n return X\ndef keep():\n return 4\n'}
    groups = {'CVFIRST': {'input': ['a']}, 'CVSECOND': {'output': ['b']}}
    a = module.pack(sources, groups)
    b = module.pack(dict(reversed(list(sources.items()))),
                    dict(reversed(list(groups.items()))))
    assert a == b and 'def keep():' in a[0]['CVFIRST']


def test_module_future_import_stays_first(install):
    controller, facades, _, _ = install({'CVDEMO':
        'from __future__ import division\ndef a():\n return 3/2\n'},
        {'CVDEMO': {'input': ['a']}})
    module = importlib.import_module('CVDEMO')
    controller.load('input')
    assert facades['CVDEMO'].startswith('from __future__ import division\n')
    assert module.a() == 1.5
