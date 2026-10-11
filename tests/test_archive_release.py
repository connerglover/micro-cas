"""Apply the artifact's behavioral/depth tests to precompiled initializers too."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))

from test_release import (
    corpus, test_packaged_corpora, test_dynamic_function_frames_are_observed,
    test_phase_boundaries_during_math_and_output,
    test_memory_admission_failure_cleans_and_recovers,
    test_mid_phase_admission_failure_removes_already_loaded_definitions,
    test_session_globals_survive_phase_eviction,
    test_actual_entry_editor_menus_forms_and_cancel,
    test_actual_entry_loads_ui_before_interaction,
    test_actual_entry_keyboard_interrupt_recovers,
    test_actual_entry_repeated_ui_admission_failure_recovers,
    test_actual_entry_mode_exits_when_ui_cannot_load,
    test_failed_companion_load_does_not_poison_namespace,
    test_native_page_compile_failure_cleans_and_recovers,
)


@pytest.fixture(scope='module')
def release_module():
    from check_archive import ArchiveRelease, ROOT
    from check_release import TS
    archive = Path(os.environ.get('CAS_EVO_ARCHIVE', ROOT / 'dist/archive'))
    if not (archive / 'archive.json').exists():
        pytest.skip('build the archive package first')
    return SimpleNamespace(Release=lambda: ArchiveRelease(archive), TS=TS)


@pytest.fixture(scope='module')
def booted(release_module):
    return release_module.Release().boot()


@pytest.fixture
def app(booted):
    booted.reset_session()
    return booted
