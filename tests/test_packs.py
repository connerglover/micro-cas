"""The pack compiler (build/packs.py): merged modules keep their meaning, or the build fails."""
import ast
from pathlib import Path
import sys
import textwrap
import types

import pytest

BUILD = Path(__file__).resolve().parents[1] / 'build'
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))
import packs


def _d(text):
    return textwrap.dedent(text).lstrip('\n')


class Man(object):
    """A manifest stand-in: rows map src names to device names CV + upper-case src."""

    def __init__(self, mods, pack_rows, frag=2048):
        self.MODULES = tuple((m, 'CV' + m.upper(), 'R', 500, 20) for m in mods)
        self.PACKS = pack_rows
        self.PACKFRAG = frag

    def rows(self):
        return dict((r[0], r) for r in self.MODULES)


RUN = _d('''
    import CVNODE as K
    DEV={'fa':'CVFA','fb':'CVFB'}
    MODS={}
    SOFT=()
    VIEW=()
    AUX=()
    FRAG=0
    def need(key):
        MODS[key]=__import__(DEV[key])
        return MODS[key]
''')


def merged(sources, rows, clients=()):
    mods = sorted(set(m.split('.')[0] for _, ms, _ in rows for m in ms))
    man = Man(mods, rows)
    device = dict(('CV' + k.upper(), _d(v)) for k, v in sources.items())
    return packs.merge(device, man, dict((k, _d(v)) for k, v in clients))


def load(pack_sources, tmp_path, monkeypatch, client=None):
    for name, text in pack_sources.items():
        (tmp_path / (name + '.py')).write_text(text)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in pack_sources:
        sys.modules.pop(name, None)
    if client is not None:
        namespace = {'__name__': 'client'}
        exec(compile(client, 'client.py', 'exec'), namespace)
        return namespace
    return None


CORE = (('CASK', ('node', 'run'), 'core'), ('CASF', ('fa', 'fb'), 'family'))


def test_same_pack_attributes_become_globals_and_stores_declare_them(tmp_path, monkeypatch):
    src = {'node': '''
              X = 1
              def bump():
                  global X
                  X += 1
              ''',
           'run': RUN + _d('''
              def total():
                  K.X = K.X + 10
                  return K.X
              '''),
           'fa': '''
              import CVNODE as K
              def f():
                  return K.X
              ''',
           'fb': '''
              import CVRUN as R
              def g():
                  return R.MODS['fa'].f() + 1
              '''}
    out, clients, meta = merged(src, CORE)
    assert 'K.X' not in out['CASK'] and 'global X' in out['CASK']
    assert out['CASF'].count('import CASK\n') == 1 and 'CASK.X' in out['CASF']
    load(out, tmp_path, monkeypatch)
    import CASK
    assert CASK.total() == 11
    CASK.bump()
    import CASF
    assert CASF.f() == 12
    CASK.need('fa')
    assert CASF.g() == 13
    assert meta['dev'] == {'fa': 'CASF', 'fb': 'CASF'}


def test_colliding_names_are_renamed_and_shared_literals_kept():
    src = {'node': 'Y = 2\n', 'run': RUN,
           'fa': 'import CVNODE as K\nC = 5\ndef h():\n    return 1\n',
           'fb': 'import CVRUN as R\nC = 5\ndef h():\n    return 2\n'
                 'def use():\n    return R.MODS["fb"].h() + R.MODS["fa"].h()\n'}
    out, clients, meta = merged(src, CORE)
    assert meta['renames'] == {'CVFB.h': 'h_fb'}
    tree = ast.parse(out['CASF'])
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert names.count('h') == 1 and 'h_fb' in names
    assert 'h_fb() + h()' in out['CASF']           # same-pack loader lookups: plain globals


def test_dynamic_access_to_a_renamed_name_fails_the_build():
    src = {'node': '', 'run': RUN,
           'fa': 'def h():\n    return 1\n',
           'fb': 'import CVRUN as R\ndef h():\n    return 2\n'
                 'def use(k):\n    return R.need(k).h()\n'}
    with pytest.raises(packs.PackError, match='renamed'):
        merged(src, CORE)


def test_compiler_keyword_const_is_renamed():
    src = {'node': '', 'run': RUN, 'fa': 'def const(c):\n    return c\n',
           'fb': 'import CVRUN as R\ndef use():\n    return R.MODS["fa"].const(3)\n'}
    out, clients, meta = merged(src, CORE)
    assert 'const(' not in out['CASF'].replace('const_fa(', '')


def test_placed_functions_reach_their_home_and_soft_packs_are_never_held(tmp_path, monkeypatch):
    rows = (('CASK', ('node', 'run'), 'core'), ('CASS', ('run.helper',), 'soft'),
            ('CASF', ('fa', 'fb'), 'family'))
    src = {'node': '', 'run': RUN + _d('''
              COUNT = 0
              def helper(n):
                  global COUNT
                  COUNT += n
                  return COUNT
              def call():
                  return helper(2)
              '''),
           'fa': 'import CVRUN as R\ndef f():\n    return R.helper(5)\n', 'fb': ''}
    out, clients, meta = merged(src, rows)
    assert "__import__('CASS').helper(2)" in out['CASK']
    assert 'CASK.COUNT' in out['CASS'] and 'import CASK' in out['CASS']
    load(out, tmp_path, monkeypatch)
    import CASK
    import CASF
    assert CASK.call() == 2 and CASF.f() == 7 and CASK.COUNT == 7
    del sys.modules['CASS']                       # evicted: the next call reloads it
    assert CASK.call() == 9


def test_module_code_may_not_hold_a_soft_function():
    rows = (('CASK', ('node', 'run'), 'core'), ('CASS', ('run.helper',), 'soft'),
            ('CASF', ('fa', 'fb'), 'family'))
    src = {'node': '', 'run': RUN + 'def helper():\n    return 1\nTABLE = (helper,)\n',
           'fa': '', 'fb': ''}
    with pytest.raises(packs.PackError, match='keep'):
        merged(src, rows)


def test_lazy_aliases_bind_at_run_time_and_soft_ones_are_never_stored(tmp_path, monkeypatch):
    rows = (('CASUI', ('ui',), 'ui'), ('CASK', ('node', 'run'), 'core'),
            ('CASP', ('printer',), 'soft'), ('CASF', ('fa', 'fb'), 'family'))
    src = {'ui': '''
              R = None
              PR = None
              def engine():
                  global R, PR
                  import run as R
                  import printer as PR
                  return R
              def show():
                  return R.ANSWER + PR.fmt()
              ''',
           'node': '', 'run': RUN + 'ANSWER = 40\n', 'printer': 'def fmt():\n    return 2\n',
           'fa': '', 'fb': ''}
    src['ui'] = src['ui'].replace('import run as R', 'import CVRUN as R').replace(
        'import printer as PR', 'import CVPRINTER as PR')
    out, clients, meta = merged(src, rows)
    assert 'import CASK' not in out['CASUI'].split('def ')[0]   # no engine at boot
    assert "__import__('CASP').fmt()" in out['CASUI']
    load(out, tmp_path, monkeypatch)
    import CASUI
    assert 'CASK' not in sys.modules
    CASUI.engine()
    assert CASUI.show() == 42 and CASUI.PR is None


def test_aux_code_may_not_reach_the_loader():
    rows = (('CASK', ('node', 'run'), 'core'), ('CASX', ('fa.f',), 'aux'),
            ('CASF', ('fa', 'fb'), 'family'))
    src = {'node': '', 'run': RUN, 'fa': 'import CVRUN as R\ndef f():\n    return 1\n', 'fb': ''}
    with pytest.raises(packs.PackError, match='reaches run'):
        merged(src, rows)


BACKREF = {
    'node': '''
        import CVNB as KB
        KB.K = __import__(__name__)
        FLAG = 0
        def mk(x):
            return x + 1
        def go(x):
            return KB.big(x) if x > 9 else mk(x)
        ''',
    'nb': '''
        K = None
        def big(x):
            K.FLAG = 1
            return K.mk(x) * 100
        ''',
    'run': RUN, 'fa': '', 'fb': ''}


def test_a_back_reference_reads_its_module_pack(tmp_path, monkeypatch):
    """node imports nb, so nb reaches node through K = None, bound by node's body: in the packs
    both statements go, nb reads CASK by name, and node loads CASN only when it calls it."""
    rows = (('CASK', ('node', 'run'), 'core'), ('CASN', ('nb',), 'aux'),
            ('CASF', ('fa', 'fb'), 'family'))
    out, _, meta = merged(BACKREF, rows)
    assert '__import__(__name__)' not in out['CASK'] and 'CVNB' not in out['CASK']
    assert "__import__('CASN').big" in out['CASK']
    assert 'K = None' not in out['CASN'] and 'CASK.mk' in out['CASN']
    load(out, tmp_path, monkeypatch)
    import CASK
    assert CASK.go(3) == 4 and 'CASN' not in sys.modules
    assert CASK.go(10) == 1100 and CASK.FLAG == 1 and 'CASN' in sys.modules
    del sys.modules['CASN']                       # evicted: the next call reloads it
    assert CASK.go(11) == 1200


def test_a_back_reference_needs_a_soft_pack_and_a_none_binding():
    rows = (('CASK', ('node', 'run'), 'core'), ('CASN', ('nb',), 'core'),
            ('CASF', ('fa', 'fb'), 'family'))
    with pytest.raises(packs.PackError, match='not a soft pack'):
        merged(BACKREF, rows)
    rows = (('CASK', ('node', 'run'), 'core'), ('CASN', ('nb',), 'aux'),
            ('CASF', ('fa', 'fb'), 'family'))
    src = dict(BACKREF, nb='K = 1\ndef big(x):\n    return x\n')
    with pytest.raises(packs.PackError, match='back-reference'):
        merged(src, rows)


def test_a_whole_aux_module_may_not_reach_the_loader():
    rows = (('CASK', ('node', 'run'), 'core'), ('CASN', ('nb',), 'aux'),
            ('CASF', ('fa', 'fb'), 'family'))
    src = dict(BACKREF, nb='import CVRUN as R\nK = None\ndef big(x):\n    return x\n')
    with pytest.raises(packs.PackError, match='reaches run'):
        merged(src, rows)


def test_loader_tables_and_clients(tmp_path, monkeypatch):
    rows = (('CASK', ('node', 'run'), 'core'), ('CASS', ('run.helper',), 'soft'),
            ('CASV', ('run.view',), 'view'), ('CASF', ('fa', 'fb'), 'family'))
    src = {'node': 'V = 3\n', 'run': RUN + 'def helper():\n    return 1\ndef view():\n    return 2\n',
           'fa': '', 'fb': ''}
    out, clients, meta = merged(src, rows, (('CLIENT', 'import CVNODE as K\nX = K.V\n'),))
    tree = ast.parse(out['CASK'])
    tables = dict((s.targets[0].id, ast.literal_eval(s.value)) for s in tree.body
                  if isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Name) and
                  s.targets[0].id in ('SOFT', 'VIEW', 'AUX', 'FRAG'))
    assert tables == {'SOFT': ('CASS',), 'VIEW': ('CASV',), 'AUX': (), 'FRAG': 2048}
    assert 'import CASK as K' in clients['CLIENT']
    namespace = load(out, tmp_path, monkeypatch, clients['CLIENT'])
    assert namespace['X'] == 3
