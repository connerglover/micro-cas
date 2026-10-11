"""CVTEST is the module-level device driver, executed against production modules."""
import ast
import runpy
import sys
from pathlib import Path

import pytest

import alg as A
import node as K
import parse as P
import printer as PR
import run as R
import ti_system as TS
import cascheck as C


SOURCE = Path(__file__).resolve().parents[1] / 'probe' / 'CVTEST.py'


def test_probe_is_ascii_python34():
    source = SOURCE.read_bytes().decode('ascii')
    tree = ast.parse(source, feature_version=(3, 4))
    assert not any(isinstance(n, (ast.AsyncFunctionDef, ast.Await, ast.JoinedStr)) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Import) and any(a.name in ('sympy', 'pytest') for a in n.names) for n in ast.walk(tree))


def test_device_probe_passes_desktop(monkeypatch, capsys):
    C.fresh()
    for name, module in (('CVNODE', K), ('CVALG', A), ('CVPARSE', P), ('CVPRINT', PR), ('CVRUN', R)):
        monkeypatch.setitem(sys.modules, name, module)
    TS.load([105] * 100)
    state = runpy.run_path(str(SOURCE), init_globals={'PAUSE': True})
    output = capsys.readouterr().out
    assert state['TOTAL'] >= 50
    assert state['PASSED'] == state['TOTAL'], state['FAILURES']
    assert not state['FAILURES']
    assert len(state['RESULTS']) == state['TOTAL']
    assert all(len(row) == 5 and row[1] for row in state['RESULTS'])
    assert state['DEPTHS'] == [(3, True), (6, True), (8, True)]
    assert len(state['MATH_RESULTS']) >= 6
    assert len(state['ENGINE_MATH']) == 6
    assert all(not record[1].startswith('internal error') for name, record in state['ENGINE_MATH'])
    assert 'CVTEST: %d/%d PASS' % (state['TOTAL'], state['TOTAL']) in output
    assert all(len(line) <= 30 for line in output.splitlines())
    for page in output.split('-- p'):
        assert len(page.splitlines()) <= 10
    assert TS.KEYS_READ and K.NN == K.BASE
