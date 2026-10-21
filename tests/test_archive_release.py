"""Apply the release's behavioral and depth tests to the exact inputs of the EVO compiler.

Native build/micro_smoke.py --archive separately executes the compiled MPY v5 bytecode.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_release
from test_release import (                                   # noqa: F401  (reused tests)
    corpus, test_packaged_corpora, test_families_load_once_and_stay_while_memory_allows,
    test_tight_heap_evicts_clears_and_reloads, test_out_of_memory_cleans_and_recovers,
    test_a_pack_body_failing_with_memory_error_is_unloaded_and_retried,
    test_a_failing_family_import_reports_and_does_not_poison_the_session,
    test_view_packs_only_unload_while_computing, test_session_globals_survive_eviction,
    test_boot_loads_only_the_ui, test_first_enter_loads_the_engine_once,
    test_actual_entry_editor_menus_forms_and_cancel,
    test_actual_entry_keyboard_interrupt_recovers,
    test_actual_entry_out_of_memory_shows_and_recovers,
    test_soft_and_aux_packs_cut_short_are_imported_again,
    test_out_of_memory_cleanup_never_raises_when_dir_runs_out,
    test_a_view_pack_cut_short_is_imported_again_after_a_command,
    test_2nd_mode_quits_even_when_the_view_pack_cannot_load,
    test_a_menu_without_memory_shows_out_of_memory_and_the_session_goes_on,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path(os.environ.get('CAS_EVO_ARCHIVE', ROOT / 'dist/archive'))


def verified_sources():
    manifest = json.loads((ARCHIVE / 'archive.json').read_text('ascii'))
    meta = json.loads((ARCHIVE / 'source/release.json').read_text('ascii'))
    names = set()
    for info in manifest['files']:
        name = info['module'] + '.py'
        data = (ARCHIVE / 'source' / name).read_bytes()
        assert len(data) == info['sourceBytes'], name
        assert hashlib.sha256(data).hexdigest() == info['sourceSha256'], name
        assert meta['files'][name]['sha256'] == info['sourceSha256'], name
        names.add(name)
    assert names == set(meta['files']), 'archive module set differs from its release'
    return ARCHIVE / 'source'


@pytest.fixture(scope='module')
def release_module():
    if not (ARCHIVE / 'archive.json').exists():
        pytest.skip('build the archive package first: python build/archive.py --mpy-cross ...')
    module = test_release.load_release_module()
    source = verified_sources()
    return SimpleNamespace(Release=lambda: module.Release(source), TS=module.TS)


@pytest.fixture(scope='module')
def booted(release_module):
    return release_module.Release().boot()


@pytest.fixture
def app(booted):
    booted.total = None
    booted.fail = None
    booted.reset_session()
    return booted


def test_archive_holds_only_packs_and_launchers():
    if not (ARCHIVE / 'archive.json').exists():
        pytest.skip('build the archive package first')
    manifest = json.loads((ARCHIVE / 'archive.json').read_text('ascii'))
    assert manifest['runtimeCompilation'] is False
    for info in manifest['files']:
        data = (ARCHIVE / info['name']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info['sha256']
        if info['kind'] == 'bytecode':
            assert data[:4] == b'M\x05\x03\x1f' and len(data) <= 60000, info['name']
            assert info['destination'] == 'archive'
        else:
            assert info['module'] == 'CAS' and info['destination'] == 'ram'
    # One launcher; the developer probe CVTEST never ships (QPL Q1).
    assert [f['module'] for f in manifest['files'] if f['destination'] == 'ram'] == ['CAS']
    assert not any(f['module'] in ('CVTEST', 'CASEVO') for f in manifest['files'])
    assert len(manifest['files']) == 22
