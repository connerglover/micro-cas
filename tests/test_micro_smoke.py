"""A native harness must prove completion, including runtimes with broken exit codes."""
import importlib.util
import subprocess
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    'micro_smoke', Path(__file__).resolve().parents[1] / 'build/micro_smoke.py')
MS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MS)


@pytest.mark.parametrize('output', ['', 'Traceback (most recent call last):\nAssertionError\n',
                                    'UI PASS: wrong suite\n'])
def test_zero_exit_without_suite_completion_fails(monkeypatch, tmp_path, output):
    monkeypatch.setattr(MS, 'prepare', lambda *a: tmp_path)
    monkeypatch.setattr(MS.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 0, output, ''))
    with pytest.raises(SystemExit, match='did not complete'):
        MS.main(['--run', 'micropython', '--suite', 'ui_calculus'])


def test_complete_native_suite(monkeypatch, tmp_path):
    monkeypatch.setattr(MS, 'prepare', lambda *a: tmp_path)
    monkeypatch.setattr(MS.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 0, 'UI CALCULUS PASS: 7 commands\n', ''))
    MS.main(['--run', 'micropython', '--suite', 'ui_calculus'])
