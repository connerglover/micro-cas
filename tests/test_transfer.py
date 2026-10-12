"""Boundaries reproduced with TI Connect Evo 7.1.0.792's actual converter."""
import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('transfer', ROOT / 'build/transfer.py')
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)


@pytest.mark.parametrize('name,last_accepted', [
    ('A.py', 65516), ('CASEVO.py', 65511), ('CVTEST.py', 65511),
    ('ABCDEFGH.py', 65509),
])
def test_observed_converter_boundaries(name, last_accepted):
    accepted = transfer.inspect_source(b'#' + b'x' * (last_accepted - 2) + b'\n', name)
    assert accepted['fits_converter_limit']
    assert accepted['max_source_bytes'] == last_accepted
    assert accepted['python_object_bytes'] == 65535
    rejected = transfer.inspect_source(b'#' + b'x' * (last_accepted - 1) + b'\n', name)
    assert not rejected['fits_converter_limit']
    assert rejected['python_object_bytes'] == 65536


def test_storage_budget_does_not_override_program_limit():
    with pytest.raises(ValueError, match='262679.*65511'):
        transfer.require_transferable({'CASEVO.py': b'x' * 262679})


def test_both_app_and_optional_probe_must_fit():
    with pytest.raises(ValueError, match='CVTEST.py'):
        transfer.require_transferable({'CASEVO.py': b'print(5)\n',
                                       'CVTEST.py': b'x' * 267644})


def test_line_wrapping_does_not_evade_limit():
    assert not transfer.inspect_source(b'x=1\n' * 20000, 'CASEVO.py')['fits_converter_limit']


def test_lowercase_name_uses_same_object_overhead():
    assert transfer.inspect_source(b'pass\n', 'casevo.py')['name'] == 'CASEVO'


@pytest.mark.parametrize('name', ['1BAD.py', 'TOOLONG99.py', 'BAD_NAME.py', 'CASEVO.zip'])
def test_build_requires_valid_calculator_name(name):
    with pytest.raises(ValueError, match='name'):
        transfer.inspect_source(b'pass\n', name)


def test_generated_source_must_be_ascii():
    with pytest.raises(UnicodeDecodeError):
        transfer.inspect_source('x="\u03b8"\n'.encode(), 'CASEVO.py')


def test_cli_rejects_oversize_and_accepts_small_file(tmp_path, capsys):
    path = tmp_path / 'CASEVO.py'
    path.write_bytes(b'x' * 262679)
    assert transfer.main([str(path)]) == 1
    assert 'REJECTED' in capsys.readouterr().out
    path.write_bytes(b'print(5)\n')
    assert transfer.main([str(path)]) == 0
    assert 'within converter size limit' in capsys.readouterr().out


def test_gate_reports_all_failed_files():
    with pytest.raises(ValueError) as failure:
        transfer.require_transferable({'CASEVO.py': b'x' * 65512, 'CVTEST.py': b'x' * 65512})
    assert 'CASEVO.py' in str(failure.value) and 'CVTEST.py' in str(failure.value)


@pytest.mark.parametrize('stale', [False, True])
def test_release_gate_runs_before_artifact_write(tmp_path, monkeypatch, stale):
    sys.path.insert(0, str(ROOT / 'build'))
    try:
        import release
    finally:
        sys.path.pop(0)
    monkeypatch.setattr(release, 'prepare', lambda path, man=None:
                        ({'CASEVO.py': 'pass\n', 'CVTEST.py': '#' + 'x' * 70000,
                          'CASK1.py': 'pass\n'},
                         {'names': {}, 'launchers': ['CASEVO.py', 'CVTEST.py']}))
    if stale:
        for name in ('CASEVO.py', 'CVTEST.py', 'cas-evo-v1.zip', 'cas-evo-development.zip',
                     'cas-evo-packs.zip', 'SHA256SUMS', 'INSTALL.md', 'CVOLD.py'):
            (tmp_path / name).write_text('old')
        (tmp_path / 'release.json').write_text('{"files":{"CVOLD.py":{}}}')
    with pytest.raises(ValueError, match='Not transferable'):
        release.build(tmp_path)
    assert (tmp_path / 'transfer-check.json').exists()
    assert not (tmp_path / 'CASEVO.py').exists()
    assert not (tmp_path / 'CVTEST.py').exists()
    assert not (tmp_path / 'cas-evo-v1.zip').exists()
    assert not (tmp_path / 'cas-evo-packs.zip').exists()
    assert not (tmp_path / 'CASK1.py').exists()
    assert not (tmp_path / 'cas-evo-development.zip').exists()
    assert not (tmp_path / 'CVOLD.py').exists()
    assert not (tmp_path / 'SHA256SUMS').exists()
