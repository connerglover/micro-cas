"""Archive initializers must preserve live state without calculator-side exec."""
import ast
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
import archive_modules as A
import function_pages as F


def init(source, namespace=None):
    bindings = F._bindings(ast.parse(source))
    emitted = A.initializer(source, bindings)
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in ('exec', 'eval') for n in ast.walk(ast.parse(emitted)))
    module, namespace = {}, {} if namespace is None else namespace
    exec(compile(emitted, '<archive>', 'exec'), module)
    module['init'](namespace)
    return namespace, module


def test_defaults_exports_and_mutation_follow_statement_order():
    ns, module = init('N=2\ndef first(x=N):\n return x\nTABLE=(first,)\n'
        'N=7\ndef second(x=first()):\n global N\n N+=1\n return x+N\n'
        'VALUE=second()\ndef read():\n return N\n')
    assert ns['VALUE'] == 10
    assert ns['first']() == 2 and ns['TABLE'][0] is ns['first']
    assert ns['read']() == 8
    ns['N'] = 40
    assert ns['second']() == 43 and ns['read']() == 41
    assert ns['first'].__closure__ is None
    assert module['_S'] is ns


def test_suspended_generator_reads_live_state_without_new_call_arguments():
    ns, _ = init('N=2\ndef generate(step):\n global N\n N+=step\n yield N\n yield N\n')
    gen = ns['generate'](3)
    assert next(gen) == ns['N'] == 5
    ns['N'] = 100
    assert next(gen) == 100


def test_native_imports_classes_and_namespace_registration():
    ns, _ = init('import math as M\nclass Stop(Exception):\n pass\nSELF=globals()\n'
                 'def f(x):\n if x<0:\n  raise Stop("bad")\n return M.sqrt(x)\n')
    assert ns['SELF'] is ns
    assert ns['f'](4) == 2
    with pytest.raises(ns['Stop'], match='bad'):
        ns['f'](-1)


def test_phase_reloads_share_globals_and_remove_function_references():
    source = 'def f():\n return N\n'
    emitted = A.initializer(source, {'f', 'N'})
    ns = {'N': 1}
    for n in range(3):
        module = {}
        exec(emitted, module)
        module['init'](ns)
        ns['N'] = n
        assert ns['f']() == n
        del ns['f']
        assert module.keys() == {'__builtins__', '_S', 'init'}


@pytest.mark.parametrize('source', [
    'def outer():\n def inner():\n  return 1\n return inner\n',
    'def outer():\n return lambda: 1\n',
    'class Thing:\n value=1\n',
    'exec("N=1")\n',
])
def test_unreviewed_scope_or_dynamic_compilation_is_rejected(source):
    with pytest.raises(ValueError):
        init(source)


def test_actual_release_transforms_every_carrier_without_dynamic_compilation():
    import json
    import zipfile
    root = Path(__file__).resolve().parents[1]
    path = root / 'dist/cas-evo-v1.zip'
    if not path.exists():
        pytest.skip('build release first')
    with zipfile.ZipFile(path) as package:
        meta = json.loads(package.read('release.json'))
        files = {name: package.read(name) for name in meta['files']}
    result = A.transform(files, meta)
    assert result.keys() == files.keys()
    for name, data in result.items():
        tree = ast.parse(data, feature_version=(3, 4))
        assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id in ('exec', 'eval') for n in ast.walk(tree)), name
        if name[:-3] in meta['function_pages']:
            assert data == files[name]
