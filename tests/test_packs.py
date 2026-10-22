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


def test_a_global_never_captures_a_builtin_another_module_of_the_pack_calls(tmp_path, monkeypatch):
    src = {'node': '', 'run': RUN,
           'fa': 'def total(xs):\n    return sum(xs)\n',
           'fb': 'def sum(a, b=0):\n    return "fb.sum"\ndef both():\n    return sum(1)\n'}
    out, clients, meta = merged(src, CORE)
    assert meta['renames'].get('CVFB.sum')
    load(out, tmp_path, monkeypatch)
    import CASF
    assert CASF.total([1, 2, 3]) == 6 and CASF.both() == 'fb.sum'


def test_mutable_or_rebound_literals_are_never_shared(tmp_path, monkeypatch):
    src = {'node': '', 'run': RUN,
           'fa': 'CACHE = {}\nLIMIT = 8\ndef fa_get(x):\n    CACHE[x] = x * 2\n    return CACHE[x]\n'
                 'def fa_limit():\n    return LIMIT\n',
           'fb': 'CACHE = {}\nLIMIT = 8\ndef fb_get(x):\n    CACHE[x] = x * 3\n    return CACHE[x]\n'
                 'def fb_raise():\n    global LIMIT\n    LIMIT = 100\n'}
    out, clients, meta = merged(src, CORE)
    load(out, tmp_path, monkeypatch)
    import CASF
    assert CASF.fa_get(5) == 10 and CASF.fb_get(5) == 15
    CASF.fb_raise()
    assert CASF.fa_get(5) == 10 and CASF.fa_limit() == 8


def test_a_computed_upper_case_key_may_not_name_a_renamed_table():
    src = {'node': '', 'run': RUN + 'def rset(name):\n    return getattr(MODS["fb"], name.upper())\n'
                                      'SETS = ("trig",)\n',
           'fa': 'TRIG = ("fa table",)\n', 'fb': 'TRIG = ("fb table",)\n'}
    with pytest.raises(packs.PackError, match='computed'):
        merged(src, CORE)


def test_a_tight_pack_aliases_resident_packs_inlines_ints_and_binds_hot_builtins(tmp_path,
                                                                                  monkeypatch):
    rows = (('CASK', ('node', 'run'), 'core'), ('CASV', ('fa',), 'view'),
            ('CASF', ('fb',), 'family'))
    src = {'node': '''
              N = 7
              S = 'x'
              X = 1
              def bump():
                  global X
                  X += 1
              ''',
           'run': RUN,
           'fa': '''
              import CVNODE as K
              def f(d=K.N):
                  K.X = K.X + 1
                  return K.X + K.N + d + len([K.X for _ in range(2)])
              def g():
                  return K.S + str(K.N)
              ''',
           'fb': 'import CVNODE as K\ndef h():\n    return K.N + K.X\n'}
    man = Man(['node', 'run', 'fa', 'fb'], rows)
    man.TIGHT, man.HOTBUILTINS = ('CASV',), ('len', 'range', 'min')
    device = dict(('CV' + k.upper(), _d(v)) for k, v in src.items())
    out, _, _ = packs.merge(device, man)
    tree = ast.parse(out['CASV'])
    f = [s for s in tree.body if isinstance(s, ast.FunctionDef) and s.name == 'f'][0]
    assert ast.unparse(f.body[0]) == 'CASK_ = CASK'      # three reads and stores of CASK
    assert ast.unparse(f.args.defaults[0]) == '7'        # node.N, bound once, is a literal
    assert '[CASK.X for _ in range(2)]' in out['CASV']   # a comprehension keeps the global
    g = [s for s in tree.body if isinstance(s, ast.FunctionDef) and s.name == 'g'][0]
    assert ast.unparse(g.body[0]) == "return CASK.S + str(7)"
    assert 'len = len' in out['CASV'] and 'range = range' in out['CASV']
    assert 'min = min' not in out['CASV']               # unused: not bound
    assert 'CASK.N' in out['CASF'] and 'len = len' not in out['CASF']   # not TIGHT
    load(out, tmp_path, monkeypatch)
    import CASK
    import CASV
    import CASF
    assert CASV.f() == 2 + 7 + 7 + 2 and CASK.X == 2 and CASV.g() == 'x7' and CASF.h() == 9


def test_tight_needs_known_packs():
    man = Man(['node', 'run', 'fa', 'fb'], CORE)
    man.TIGHT = ('CASX',)
    device = {'CVNODE': '', 'CVRUN': RUN, 'CVFA': '', 'CVFB': ''}
    with pytest.raises(packs.PackError, match='TIGHT'):
        packs.merge(device, man)


# -- int constants as literals in the engine packs (manifest INLINE) ------------------------------

INLINE_ROWS = (('CASK', ('node', 'run'), 'core'), ('CASP', ('printer',), 'soft'),
               ('CASF', ('fa', 'fb'), 'family'))


def inlined(sources, rows=INLINE_ROWS, kinds=('core', 'family', 'soft', 'aux'), clients=()):
    mods = sorted(set(m.split('.')[0] for _, ms, _ in rows for m in ms))
    man = Man(mods, rows)
    man.INLINE = kinds
    device = dict(('CV' + k.upper(), _d(v)) for k, v in sources.items())
    return packs.merge(device, man, dict((k, _d(v)) for k, v in clients))


def _fn(source, name):
    return ast.unparse([s for s in ast.parse(source).body
                        if isinstance(s, ast.FunctionDef) and s.name == name][0])


def test_engine_packs_read_module_ints_as_literals(tmp_path, monkeypatch):
    src = {'node': 'NUM = 3\nMUL = 5\ndef kind(e):\n    return NUM if e else MUL\n',
           'run': RUN + 'def f():\n    return K.NUM + K.MUL\n',
           'printer': 'import CVNODE as K\ndef p(e):\n    return K.MUL * e\n',
           'fa': 'import CVNODE as K\nimport CVPRINTER as P\ndef g(d=K.NUM):\n'
                 '    return P.p(K.MUL) + d\n',
           'fb': ''}
    out, _, meta = inlined(src)
    assert _fn(out['CASK'], 'kind') == 'def kind(e):\n    return 3 if e else 5'
    assert _fn(out['CASK'], 'f') == 'def f():\n    return 3 + 5'
    assert _fn(out['CASP'], 'p') == 'def p(e):\n    return 5 * e'
    assert _fn(out['CASF'], 'g') == "def g(d=3):\n    return __import__('CASP').p(5) + d"
    assert 'NUM = 3' in out['CASK'] and 'MUL = 5' in out['CASK']     # bindings stay: getattr
    for pack, spans in meta['statements'].items():   # build/linemap.py: one span per statement
        assert len(spans) == len(ast.parse(out[pack]).body)
    load(out, tmp_path, monkeypatch)
    import CASK
    import CASF
    assert CASK.f() == 8 and CASK.kind(0) == 5 and CASF.g() == 28
    assert getattr(CASK, 'NUM') == 3


def test_inlining_follows_the_manifest_kinds():
    src = {'node': 'NUM = 3\n', 'run': RUN + 'def f():\n    return K.NUM\n',
           'printer': '', 'fa': 'import CVNODE as K\ndef g():\n    return K.NUM\n', 'fb': ''}
    out, _, _ = inlined(src, kinds=('family',))
    assert 'return 3' in out['CASF'] and 'return NUM' in out['CASK']
    out, _, _ = inlined(src, kinds=())
    assert 'return CASK.NUM' in out['CASF']
    with pytest.raises(packs.PackError, match='INLINE'):
        inlined(src, kinds=('engine',))


def test_patched_loader_tables_are_never_inlined(tmp_path, monkeypatch):
    """merge and the release write these run tables after bundling: EVDICT is 0 in run.py but 1
    on the calculator, so a literal 0 would switch the eviction clearing off."""
    run = RUN.replace('FRAG=0', 'FRAG=0\nEVDICT=0\nSHEDAT=0\nPEAKB=80\nLINES={}\nCOST={}\nROOM={}')
    src = {'node': '', 'printer': '', 'fb': '',
           'run': run + 'KEEP = 7\ndef cfg():\n    return (EVDICT, SHEDAT, PEAKB, FRAG, KEEP)\n',
           'fa': 'import CVRUN as R\ndef h():\n    return R.EVDICT + R.FRAG\n'}
    out, _, _ = inlined(src)
    assert _fn(out['CASK'], 'cfg') == \
        'def cfg():\n    return (EVDICT, SHEDAT, PEAKB, FRAG, 7)'
    assert 'CASK.EVDICT + CASK.FRAG' in out['CASF']
    out['CASK'] = packs.loader_tables(out['CASK'], {'SHEDAT': 65536})
    load(out, tmp_path, monkeypatch)
    import CASK
    import CASF
    assert CASK.cfg() == (1, 65536, 0, 2048, 7) and CASF.h() == 2049
    for name in packs.PATCHED:
        assert name in packs.PATCHED
    with pytest.raises(packs.PackError, match='PATCHED'):
        packs.loader_tables(out['CASK'], {'KEEP': 8})


@pytest.mark.parametrize('where, code', [
    ('fa', 'def w():\n    K.X = 2\n'),                    # another module stores it
    ('fa', 'def w():\n    K.X += 1\n'),                   # augmented attribute store
    ('fa', 'def w():\n    del K.X\n'),
    ('fa', "def w():\n    setattr(K, 'X', 2)\n"),
    ('fa', "def w():\n    delattr(K, 'X')\n"),
    ('node', 'def w():\n    global X\n    X = 2\n'),     # its own module, in a function
    ('fb', 'def w():\n    global X\n    X = 2\n'),       # any module's global X
    ('node', 'X = 4\n'),                                  # bound twice
    ('node', 'X += 1\n'),
    ('node', 'for X in (1, 2):\n    pass\n'),
    ('node', 'try:\n    pass\nexcept ValueError as X:\n    pass\n'),
    ('client', 'K.X = 2\n'),                              # an entry program stores it
])
def test_a_name_assigned_anywhere_else_is_no_constant(where, code):
    src = {'node': 'X = 1\n', 'run': RUN + 'def f():\n    return K.X\n',
           'printer': '', 'fa': 'import CVNODE as K\n', 'fb': ''}
    clients = ()
    if where == 'client':
        clients = (('CLIENT', 'import CVNODE as K\n' + code),)
    else:
        src[where] += code
    out, _, _ = inlined(src, clients=clients)
    assert 'return X' in out['CASK']


@pytest.mark.parametrize('code', [
    'def w(n):\n    setattr(K, n, 2)\n',
    'def w(n):\n    delattr(K, n)\n',
    'def w():\n    globals()["X"] = 2\n',
    'def w():\n    K.__dict__["X"] = 2\n',
    'def w():\n    vars(K)["X"] = 2\n',
])
def test_a_computed_store_fails_an_inlining_build(code):
    src = {'node': 'X = 1\n', 'run': RUN + 'def f():\n    return K.X\n',
           'printer': '', 'fa': 'import CVNODE as K\n' + code, 'fb': ''}
    with pytest.raises(packs.PackError, match='computed'):
        inlined(src)
    merged(dict(src, printer=''), (('CASK', ('node', 'run', 'printer'), 'core'),
                                   ('CASF', ('fa', 'fb'), 'family')))   # no inlining: built


def test_the_eviction_clearing_and_reflective_reads_keep_working(tmp_path, monkeypatch):
    """run.unload's setattr(m, k, None) (EVDICT) clears an evicted pack, whose code no longer
    runs; getattr and loader lookups by name still find the binding."""
    run = RUN + _d('''
        import sys
        def unload(n):
            m = sys.modules[n]
            del sys.modules[n]
            for k in dir(m):
                if not k.startswith('__'):
                    setattr(m, k, None)
        def peek(name):
            return getattr(K, name) + getattr(need('fa'), 'LIM')
        ''')
    src = {'node': 'X = 1\n', 'run': run, 'printer': '',
           'fa': 'LIM = 64\ndef g():\n    return LIM\n', 'fb': ''}
    out, _, _ = inlined(src)
    assert _fn(out['CASF'], 'g') == 'def g():\n    return 64'
    load(out, tmp_path, monkeypatch)
    import CASK
    assert CASK.peek('X') == 65
    CASK.unload('CASF')
    assert CASK.need('fa').g() == 64 and CASK.peek('X') == 65


def test_only_small_ints_become_literals(tmp_path, monkeypatch):
    src = {'node': _d('''
               B = True
               F = 1.5
               S = 'x'
               N = None
               NEG = -1
               LO = -1073741824
               HI = 1073741823
               BIG = 1073741824
               NBIG = -1073741825
               HEX = 0x7f
               def mk(x):
                   return x
               ZERO = mk(0)
               '''),
           'run': RUN + _d('''
               def f():
                   return (K.B, K.F, K.S, K.N, K.LO, K.HI, K.BIG, K.NBIG, K.HEX, K.ZERO)
               def neg():
                   return (K.NEG ** 2, -K.NEG, K.NEG.bit_length(), 2 - K.NEG, K.HEX.bit_length())
               def same(x):
                   return x is K.HI or x is not K.NEG
               '''),
           'printer': '', 'fa': '', 'fb': ''}
    out, _, _ = inlined(src)
    assert _fn(out['CASK'], 'f') == \
        'def f():\n    return (B, F, S, N, -1073741824, 1073741823, BIG, NBIG, 127, ZERO)'
    assert _fn(out['CASK'], 'same') == 'def same(x):\n    return x is HI or x is not NEG'
    load(out, tmp_path, monkeypatch)
    import CASK
    assert CASK.neg() == (1, 1, 1, 3, 7)
    assert CASK.f() == (True, 1.5, 'x', None, -2 ** 30, 2 ** 30 - 1, 2 ** 30, -2 ** 30 - 1, 127, 0)


def test_a_comprehension_in_a_default_binds_its_own_names(tmp_path, monkeypatch):
    """A default runs at module scope, where a comprehension's target is its own local: the
    module int of that name is not the value the comprehension reads."""
    src = {'node': 'X = 1\ndef g(a=[X for X in (5, 6)], b=X):\n    return a + [b]\n',
           'run': RUN, 'printer': '', 'fa': '', 'fb': ''}
    out, _, _ = inlined(src)
    assert _fn(out['CASK'], 'g') == 'def g(a=[X for X in (5, 6)], b=1):\n    return a + [b]'
    load(out, tmp_path, monkeypatch)
    import CASK
    assert CASK.g() == [5, 6, 1]


@pytest.mark.parametrize('code', ['def f(*, X=5):\n    return X\n',
                                  'def f(X, /):\n    return X\n'])
def test_parameters_the_rewrite_cannot_scope_fail_the_build(code):
    """Keyword-only and positional-only parameters are locals the rewrite would not see (the
    device lint rejects them too): a read of one must not become a module int."""
    src = {'node': 'X = 1\n' + code, 'run': RUN, 'printer': '', 'fa': '', 'fb': ''}
    with pytest.raises(packs.PackError, match='parameters'):
        inlined(src)


def test_only_the_loader_may_clear_a_module_by_a_computed_name():
    """setattr(m, k, None) is run.unload's eviction clearing; elsewhere it could set a live
    module's int to None behind a literal."""
    src = {'node': 'X = 1\n', 'run': RUN + 'def f():\n    return K.X\n', 'printer': '',
           'fa': 'import CVNODE as K\ndef w(n):\n    setattr(K, n, None)\n', 'fb': ''}
    with pytest.raises(packs.PackError, match='computed'):
        inlined(src)
