"""Semantics of the native function-page transform, independent of arithmetic."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
import function_pages as F


def emit(tree):
    return compile(ast.fix_missing_locations(tree), '<page-test>', 'exec')


def test_known_page_evaluates_namespace_once_and_keeps_arguments():
    source = "R=_load('CVRUN')\ndef work():\n return R['need']('part')['f'](3, scale=2)\n"
    tree = ast.parse(source)
    meta = {'names': {}, 'runtime_modules': {'part': 'CVPART'}}
    resolver = F.Resolver(tree, 'CVMAIN', meta)
    tree.body[1] = F.Calls('CVMAIN', resolver.local(tree.body[1]),
        {'CVPART': {'f': True}}, {('CVPART', 'f'): 'CVF00001'}, False).visit(tree.body[1])
    calls, namespace = [], {'base': 7}

    def need(key):
        calls.append(key)
        return namespace

    def load(name):
        assert name == 'CVF00001'
        return SimpleNamespace(f=lambda ns, x, scale: ns['base'] + x * scale)

    env = {'_load': lambda name: {'need': need}, '__import__': load}
    exec(emit(tree), env)
    assert env['work']() == 13
    assert calls == ['part']


def test_dynamic_page_rejects_repeated_namespace_side_effects():
    tree = ast.parse("R=_load('CVRUN')\ndef work(key, name):\n return R['need'](key)[name]()\n")
    resolver = F.Resolver(tree, 'CVMAIN', {'names': {}, 'runtime_modules': {}})
    with pytest.raises(ValueError, match='bound namespace'):
        F.Calls('CVMAIN', resolver.local(tree.body[1]), {}, {}, False).visit(tree.body[1])


def test_namespace_globals_stay_live_across_generator_suspension():
    tree = ast.parse('flag=0\nitems=[1]\ndef work(value):\n global flag\n flag=value\n yield items[0]\n yield flag\n')
    fn = F.Globals(tree.body[-1], F._bindings(tree)).visit(tree.body[-1])
    fn.args.args.insert(0, ast.arg(arg='_S'))
    env = {}
    exec(emit(ast.Module(body=[fn], type_ignores=[])), env)
    namespace = {'flag': 0, 'items': [9]}
    work = env['work'](namespace, 3)
    assert next(work) == 9
    assert namespace['flag'] == 3
    namespace['flag'] = 17
    assert next(work) == 17


def test_local_namespace_aliases_do_not_leak_between_functions():
    tree = ast.parse("R=_load('CVRUN')\ndef one():\n m=R['MODS']['one']\n return m['f']()\ndef two():\n m=R['MODS']['two']\n return m['f']()\n")
    resolver = F.Resolver(tree, 'CVMAIN', {'names': {}, 'runtime_modules': {'one': 'CVONE', 'two': 'CVTWO'}})
    first, second = (resolver.local(fn) for fn in tree.body[1:])
    assert first(ast.Name(id='m')) == 'CVONE'
    assert second(ast.Name(id='m')) == 'CVTWO'
    assert resolver(ast.Name(id='m')) is None


def test_rewritten_statement_maps_to_its_original_source_span():
    old = ast.parse('x=1\ndef f():\n return x\n')
    mapping = {'src': 'src/example.py', 'lines': [[10, 10], [20, 20], [22, 23]]}
    result = F._statement_map('x=1\ndef f():\n pass\n return x\n', old.body, mapping)
    assert result['lines'] == [[10, 10], [20, 23], [20, 23], [20, 23]]
    assert mapping['lines'] == [[10, 10], [20, 20], [22, 23]]


def test_only_immutable_defaults_can_be_copied_into_a_native_page():
    assert F._immutable((None, False, 400, 'x', (1, 2)))
    assert not F._immutable((1, []))
    assert not F._immutable({'x': 1})
