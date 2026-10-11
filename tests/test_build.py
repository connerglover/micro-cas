"""M0.4: the build skeleton (DESIGN.md section 19; docs/notes/M0.4.md).

build/manifest.py (the name map), build/bundle.py (phase 1: strip, re-indent, rename imports,
rewrite the run.py tables; lint, name, line and size checks), build/linemap.py.
"""
import ast
import io
import json
import os
import subprocess
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, 'build')
if BUILD not in sys.path:
    sys.path.insert(0, BUILD)

import bundle  # noqa: E402
import framelint  # noqa: E402
import linemap  # noqa: E402
import lint  # noqa: E402


def _d(s):
    return textwrap.dedent(s).lstrip('\n')


# -- the minifier ------------------------------------------------------------------------------

def test_minify_strips_comments_docstrings_annotations_and_blank_lines():
    src = _d('''
        #@L 5
        """Module docstring."""
        import gc

        # a comment


        def f(x):  #@L 4
            """Function docstring."""
            if x:
                return x * 2  # trailing
            else:
                "only a string: dropped, so the block gets a pass"
            return 0


        class E(Exception):
            """A docstring-only body."""
        ''')
    m = bundle.minify(src)
    assert m.lines == [
        'import gc',
        'def f(x):',
        ' if x:',
        '  return x*2',
        ' else:',
        '  pass',
        ' return 0',
        'class E(Exception):',
        ' pass',
    ]
    assert m.text == '\n'.join(m.lines) + '\n'
    # line map: device line i+1 -> (first, last) source line of its logical line
    assert m.spans[0] == (3, 3)
    assert m.spans[1] == (8, 8)
    assert m.spans[3] == (11, 11)
    assert m.spans[5] == (12, 12)          # the inserted pass maps to its header (else:)
    assert m.spans[8] == (17, 17)
    assert '#' not in m.text


def test_minify_joins_continuation_lines_and_keeps_their_span():
    src = _d('''
        T = (1,
             2,   # comment inside brackets
             3)
        x = 1 + \\
            2
        y = [T,
             x]
        ''')
    m = bundle.minify(src)
    assert m.lines == ['T=(1,2,3)', 'x=1+2', 'y=[T,x]']
    assert m.spans == [(1, 3), (4, 5), (6, 7)]


def test_minify_spacing_keeps_every_token():
    src = _d('''
        a = 1 if b else 2
        c = not a in [1, 2] and a is not None or -a
        d = 'x' 'y' if a else'z'
        e = 1 .real
        f = 1. .real
        g = a - -1
        h = x[:-1] if x else x[1:]
        for i in range(3): pass
        while 0: break
        del a
        k = lambda: 0
        def p(*args, **kw): return args, kw
        q = {1: -2, 'a': (3,)}
        r = 0x1f + 1e3 + 2j + 0o7 + 0b1
        s = a<-b
        t = b'\\x00' + rb'\\d'
        ''')
    m = bundle.minify(src)
    assert ast.dump(ast.parse(m.text)) == ast.dump(ast.parse(src))
    # identifier-like neighbours are separated, everything else is packed
    assert m.lines[0] == 'a=1 if b else 2'
    assert m.lines[2] == "d='x' 'y' if a else 'z'"
    assert m.lines[3] == 'e=1 .real'


def test_minify_multiline_string_becomes_one_line():
    src = _d('''
        HELP = """line one
        line 'two'\\tand "three"
        """
        R = r"""a\\b
        c"""
        ''')
    m = bundle.minify(src)
    assert len(m.lines) == 2
    ns_src, ns_min = {}, {}
    exec(compile(src, '<src>', 'exec'), ns_src)
    exec(compile(m.text, '<min>', 'exec'), ns_min)
    assert ns_min['HELP'] == ns_src['HELP']
    assert ns_min['R'] == ns_src['R']
    assert m.spans == [(1, 3), (4, 5)]
    for ln in m.lines:
        assert ln.isascii()


def test_minify_rejects_fstrings_and_bad_source():
    with pytest.raises(bundle.BundleError):
        bundle.minify('x = 1\ny = f"{x}"\n')
    with pytest.raises(bundle.BundleError):
        bundle.minify('def f(:\n')


def _strip_docstrings(tree):
    """What the minifier does to the AST: every string-only statement goes, empty bodies
    get a pass."""
    for node in ast.walk(tree):
        for field in ('body', 'orelse', 'finalbody'):
            body = getattr(node, field, None)
            if not isinstance(body, list) or not body or not isinstance(body[0], ast.stmt):
                continue
            keep = []
            for st in body:
                if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and \
                        isinstance(st.value.value, (str, bytes)):
                    continue
                keep.append(st)
            if not keep and (field == 'body' or body):
                keep = [ast.Pass()]
            setattr(node, field, keep)
    return ast.dump(tree)


def _corpus():
    out = []
    for d in ('probe', 'shim', os.path.join('tests', 'support'),
              os.path.join('tests', 'depth_shapes'), 'build', 'src'):
        full = os.path.join(ROOT, d)
        if os.path.isdir(full):
            for name in sorted(os.listdir(full)):
                if name.endswith('.py'):
                    out.append(os.path.join(full, name))
    return out


def test_minify_preserves_the_ast_on_the_repo_corpus():
    """Every Python file of the repo minifies to the same AST (docstrings aside)."""
    n = 0
    for path in _corpus():
        with open(path, encoding='utf-8', errors='replace') as fh:
            src = fh.read()
        try:
            ref = ast.parse(src)
        except SyntaxError:
            continue                       # a file another task is still writing
        try:
            m = bundle.minify(src, path)
        except bundle.BundleError:
            if os.path.basename(os.path.dirname(path)) == 'src':
                continue                   # src work in progress (the src lint reports it)
            raise
        got = ast.parse(m.text)
        assert _strip_docstrings(got) == _strip_docstrings(ref), path
        assert len(m.lines) == len(m.spans), path
        for ln in m.lines:
            assert not ln.endswith(' '), path
        n += 1
    assert n >= 20


# -- import rewriting --------------------------------------------------------------------------

NAMES = {'node': 'CVNODE', 'run': 'CVRUN', 'poly': 'CVPOLY'}


def test_rewrite_imports_to_device_names():
    src = _d('''
        import gc
        import node as K
        import gc, node as K2, sys
        import run


        def need(key):
            import poly as PO
            return PO
        ''')
    m = bundle.minify(src)
    errs = bundle.rewrite_imports(m, NAMES, entry='casevo')
    assert errs == []
    assert m.lines == [
        'import gc',
        'import CVNODE as K',
        'import gc,CVNODE as K2,sys',
        'import CVRUN as run',
        'def need(key):',
        ' import CVPOLY as PO',
        ' return PO',
    ]


@pytest.mark.parametrize('line,frag', [
    ('from node import mk\n', 'from node import'),
    ('import casevo as C\n', 'entry module'),
    ('import node.x as Y\n', 'dotted'),
    ("M = __import__('poly')\n", 'string'),
    ("M = sys.modules['node']\n", 'string'),
])
def test_rewrite_imports_rejects(line, frag):
    m = bundle.minify(line)
    errs = bundle.rewrite_imports(m, NAMES, entry='casevo')
    assert len(errs) == 1 and frag in errs[0], errs


# -- the manifest -------------------------------------------------------------------------------

def test_manifest_is_consistent_with_the_design_and_the_lint_map():
    man = bundle.load_manifest()
    assert bundle.check_manifest(man) == []
    assert man.ENTRY == ('casevo', 'CASEVO')
    rows = dict((r[0], r) for r in man.MODULES)
    # every module of the lint/framelint map (DESIGN 4.1) has a row, and the reverse
    for mod in lint.ALIASES:
        assert mod in rows
    for mod in rows:
        assert lint.alias_for(mod) is not None
    # parts (DESIGN 4.3)
    for src in ('rulesb', 'polyb', 'polyc', 'normb', 'factorb', 'solveb', 'solvec', 'seriesb',
                'limitb', 'limitc', 'integ2b', 'integ3b', 'defintb', 'sumsb', 'odeb', 'odec',
                'menub', 'catalogb'):
        assert rows[src][2] in ('L', 'U')
    assert rows['node'][1] == 'CVNODE' and rows['integ2b'][1] == 'CVINT2B'
    assert rows['solvec'][1] == 'CVSOLVEC'
    # the runtime keys agree with FRAMELINT's
    assert man.KEYS == framelint.KEYS
    # families (DESIGN 4.3, 15.1)
    assert man.PARTS['poly'] == ('poly', 'polyb', 'polyc')
    assert 'int' not in man.PARTS and 'int2' not in man.PARTS
    assert man.PARTS['menu'] == ('menu', 'menub')
    assert man.FAMILY['menub'] == 'menu' and man.FAMILY['polyc'] == 'poly'
    # the memory numbers are the M0.5 gate's to set (DESIGN 18.7); only their shape is pinned
    assert isinstance(man.LAZYMAX, int) and man.PEAKB > 0 and man.FACTOR > 0
    for r in man.MODULES:
        if r[2] != 'R':
            assert r[3] <= man.LAZYMAX


def _bad_manifest(**changes):
    man = bundle.load_manifest()
    ns = dict(vars(man))
    ns.update(changes)
    return bundle.Manifest(ns)


def _with_row(src, row):
    man = bundle.load_manifest()
    rows = [r for r in man.MODULES if r[0] != src]
    if row is not None:
        rows.append(row)
    return tuple(rows)


@pytest.mark.parametrize('changes,frag', [
    ({'ENTRY': ('casevo', 'casevo')}, 'bad device name'),
    ({'ENTRY': ('casevo', 'CASEVOLONG')}, 'bad device name'),
    ({'MODULES': _with_row('node', ('node', 'CVALG', 'R', 520, 12))}, 'duplicate device name'),
    ({'MODULES': _with_row('node', ('node', 'NODE', 'R', 520, 12))}, 'CV plus'),
    ({'MODULES': _with_row('node', ('node', 'CVNODE', 'L', 150, 4))}, 'resident'),
    ({'MODULES': _with_row('node', ('node', 'CVNODE', 'X', 520, 12))}, 'class'),
    ({'MODULES': _with_row('node', ('node', 'CVNODE', 'R', 0, 12))}, 'budget'),
    ({'MODULES': _with_row('node', None)}, 'no manifest row'),
    ({'MODULES': _with_row('foo', ('foo', 'CVFOO', 'L', 150, 3))}, 'module map'),
    ({'MODULES': _with_row('math', ('math', 'CVMATH', 'L', 150, 3))}, 'native'),
    ({'KEYS': {'fact': 'factor'}}, 'framelint'),
    ({'PARTS': {'poly': ('poly', 'polyb')}}, 'no family'),
    ({'FAMILY': {'polyb': 'poly'}}, 'FAMILY'),
    ({'LAZYMAX': 0}, 'LAZYMAX'),
])
def test_manifest_name_checks_catch_errors(changes, frag):
    errs = bundle.check_manifest(_bad_manifest(**changes))
    assert errs, changes
    assert any(frag in e for e in errs), errs


# -- derived tables -----------------------------------------------------------------------------

DEPS_15_1 = {'norm': ('poly', 'rules', 'ident'), 'fact': ('poly', 'norm'),
             'solve': ('poly', 'norm', 'fact', 'rules'),
             'diff': ('norm', 'poly', 'rules', 'ident'),
             'int': ('itab', 'rules', 'diff', 'norm', 'poly'),
             'lim': ('ser', 'diff', 'norm', 'poly'), 'ser': ('norm', 'poly'),
             'int2': ('poly', 'norm'), 'int2b': ('poly', 'norm', 'fact'),
             'int3': ('diff', 'norm', 'poly'), 'int3b': ('norm', 'poly'), 'def': ('int',),
             'sum': ('poly', 'norm', 'lim'), 'ode': ('int', 'poly', 'norm')}


def test_closure_is_leaf_first_and_ends_with_the_family():
    man = bundle.load_manifest()
    fams = bundle.families(man)
    cl = bundle.closure(DEPS_15_1, fams, man.FAMILY)
    assert cl['poly'] == ('poly',)
    assert cl['norm'] == ('poly', 'rules', 'ident', 'norm')
    assert cl['solve'] == ('poly', 'rules', 'ident', 'norm', 'fact', 'solve')
    assert cl['def'] == ('itab', 'rules', 'poly', 'ident', 'norm', 'diff', 'int', 'def')
    for fam, c in cl.items():
        assert c[-1] == fam
        seen = set()
        for f in c:
            for dep in DEPS_15_1.get(f, ()):
                assert dep in seen, (fam, f, dep)
            seen.add(f)
        assert len(set(c)) == len(c)
    assert set(cl) == set(fams)


def test_desktop_tables_for_run_py(tmp_path):
    man = bundle.load_manifest()
    t = bundle.desktop_tables(man, DEPS_15_1)
    assert t['DEV']['int'] == 'integ' and t['DEV']['polyb'] == 'polyb'
    assert t['DEV']['catb'] == 'catalogb' and 'node' not in t['DEV']
    assert t['PARTS'] == man.PARTS and t['FAMILY'] == man.FAMILY
    assert t['CLOSURE']['solve'] == ('poly', 'rules', 'ident', 'norm', 'fact', 'solve')
    assert 'CLOSURE' not in bundle.desktop_tables(man)
    # the command line reads DEPS from src/run.py
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'run.py').write_text("#@L 3\nDEPS = {'norm': ('poly', 'rules', 'ident'),  # hard\n"
                                "        'fact': ('poly', 'norm')}\n", encoding='ascii')
    p = subprocess.run([sys.executable, os.path.join(BUILD, 'bundle.py'), '--tables', '--src',
                        str(src)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    ns = {}
    exec(p.stdout, ns)
    assert ns['CLOSURE']['fact'] == ('poly', 'rules', 'ident', 'norm', 'fact')
    assert ns['DEV'] == t['DEV'] and ns['PARTS'] == man.PARTS


def test_closure_rejects_cycles_and_unknown_keys():
    fams = ('a', 'b', 'c')
    with pytest.raises(bundle.BundleError, match='cycle'):
        bundle.closure({'a': ('b',), 'b': ('c',), 'c': ('a',)}, fams, {})
    with pytest.raises(bundle.BundleError, match='unknown'):
        bundle.closure({'a': ('zz',)}, fams, {})
    # a part key in DEPS means its family
    assert bundle.closure({'a': ('bb',)}, fams, {'bb': 'b'})['a'] == ('b', 'a')


# -- bundling a sample tree --------------------------------------------------------------------

SAMPLE = {
    'node': '''
        #@L 7
        """Sample node module (bundler test)."""
        import gc

        # a comment
        SCALE = 3
        TABLE = {'a': 1, 'b': 2}


        class CasError(Exception):
            """A docstring-only body becomes pass."""


        def mk(t):
            """Docstring."""
            if t:
                return t * SCALE  # trailing comment
            else:
                "dropped"
            return 0


        def half(x):  #@L 6
            return x / 2  #@float-ok


        def total():  #@L 6
            s = 0
            for k in TABLE:  #@unordered-ok
                s = s + TABLE[k]
            return s
        ''',
    'alg': '''
        #@L 5
        import node as K


        def twice(x):
            return K.mk(x) + K.mk(x)
        ''',
    'poly': '''
        #@L 5
        import node as K


        def padd(a, b):
            """Add two dense coefficient lists."""
            n = len(a)
            if len(b) > n:
                n = len(b)
            out = []
            i = 0
            while i < n:
                x = 0
                if i < len(a):
                    x = x + a[i]
                if i < len(b):
                    x = x + b[i]
                out.append(x)
                i = i + 1
            return out
        ''',
    'polyb': '''
        #@L 4
        import run as R


        def pdouble(a):
            return R.MODS['poly'].padd(a, a)
        ''',
    'polyc': '''
        #@L 5
        def pneg(a):
            out = []
            for x in a:
                out.append(-x)
            return out
        ''',
    'run': '''
        #@L 3
        """Sample runner: the lazy loader of DESIGN 18.4, cut down."""
        import node as K

        DEV = {'poly': 'poly', 'polyb': 'polyb', 'polyc': 'polyc'}
        PARTS = {'poly': ('poly', 'polyb', 'polyc')}
        FAMILY = {'polyb': 'poly', 'polyc': 'poly'}
        DEPS = {}
        CLOSURE = {'poly': ('poly',)}
        COST = {'poly': 1, 'polyb': 1, 'polyc': 1}
        LINES = {'poly': 1, 'polyb': 1, 'polyc': 1}
        PEAKB = 1
        FRAG = 0
        MODS = {}
        LOADED = []


        def need(key):
            fam = FAMILY.get(key, key)
            for f in CLOSURE[fam]:
                if f in LOADED:
                    continue
                for p in PARTS.get(f, (f,)):
                    MODS[p] = __import__(DEV[p])
                LOADED.append(f)
            return MODS[key]


        def go(text):  #@L 1
            M = need('polyb')
            r = M.pdouble([1, 2, 3])
            return '%s %s %d %d' % (text, r, K.mk(2), PEAKB)
        ''',
    'casevo': '''
        """Entry: imports leaf-first, then the event loop at depth 0."""
        import node as K
        import alg as A
        import run as R

        print(R.go('ok'), A.twice(1), K.half(3), K.total())
        ''',
}


def _write_tree(tmp_path, files=None, extra=None):
    src = tmp_path / 'src'
    src.mkdir(parents=True)
    files = dict(SAMPLE if files is None else files)
    if extra:
        files.update(extra)
    for name, text in files.items():
        (src / (name + '.py')).write_text(_d(text), encoding='ascii', newline='\n')
    return str(src), str(tmp_path / 'dist')


def _run(cwd, mod):
    p = subprocess.run([sys.executable, '-B', '-c', 'import ' + mod], cwd=cwd,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_bundle_sample_tree_end_to_end(tmp_path):
    src, dist = _write_tree(tmp_path)
    res = bundle.bundle(src, dist, sizer=None)
    assert res.errors == [], res.errors
    dev = os.path.join(dist, 'device')
    names = sorted(os.listdir(dev))
    assert names == ['CASEVO.py', 'CVALG.py', 'CVNODE.py', 'CVPOLY.py', 'CVPOLYB.py',
                     'CVPOLYC.py', 'CVRUN.py']
    with open(os.path.join(dev, 'CVNODE.py'), encoding='ascii', newline='') as fh:
        node = fh.read()
    assert node == ('import gc\n'
                    'SCALE=3\n'
                    "TABLE={'a':1,'b':2}\n"
                    'class CasError(Exception):\n'
                    ' pass\n'
                    'def mk(t):\n'
                    ' if t:\n'
                    '  return t*SCALE\n'
                    ' else:\n'
                    '  pass\n'
                    ' return 0\n'
                    'def half(x):\n'
                    ' return x/2\n'
                    'def total():\n'
                    ' s=0\n'
                    ' for k in TABLE:\n'
                    '  s=s+TABLE[k]\n'
                    ' return s\n')
    with open(os.path.join(dev, 'CVRUN.py'), encoding='ascii') as fh:
        run = fh.read().splitlines()
    assert 'import CVNODE as K' in run
    assert "DEV={'poly':'CVPOLY','polyb':'CVPOLYB','polyc':'CVPOLYC'}" in run
    assert "PARTS={'poly':('poly','polyb','polyc')}" in run
    assert "FAMILY={'polyb':'poly','polyc':'poly'}" in run
    assert "CLOSURE={'poly':('poly',)}" in run
    man = bundle.load_manifest()
    assert 'PEAKB=' + bundle._lit(man.PEAKB) in run and 'FRAG=' + bundle._lit(man.FRAG) in run
    lines = res.lines
    assert "LINES={'poly':%d,'polyb':%d,'polyc':%d}" % (
        lines['CVPOLY'], lines['CVPOLYB'], lines['CVPOLYC']) in run
    cost = [ln for ln in run if ln.startswith('COST=')]
    assert len(cost) == 1
    cost = ast.literal_eval(cost[0][5:])
    assert cost['poly'] == int(lines['CVPOLY'] * man.MPYB * man.FACTOR)
    with open(os.path.join(dev, 'CVPOLYB.py'), encoding='ascii') as fh:
        assert fh.read().startswith('import CVRUN as R\n')
    with open(os.path.join(dev, 'CASEVO.py'), encoding='ascii') as fh:
        assert fh.read().splitlines()[:3] == ['import CVNODE as K', 'import CVALG as A',
                                              'import CVRUN as R']
    # the bundle runs, lazy family and all, and gives the desktop's answer (with the
    # device PEAKB, which the bundler wrote)
    want = _run(src, 'casevo')
    assert want == 'ok [2, 4, 6] 6 1 6 1.5 3\n'
    got = _run(dev, 'CASEVO')
    assert got == want.replace(' 6 1 ', ' 6 %d ' % man.PEAKB)
    # every output file compiles and passes the subset lint (markers honoured)
    for n in names:
        with open(os.path.join(dev, n), encoding='ascii') as fh:
            compile(fh.read(), n, 'exec')
    # side files
    with open(os.path.join(dist, 'levels.json'), encoding='ascii') as fh:
        levels = json.load(fh)
    assert levels['CVNODE'] == {'half': 6, 'mk': 7, 'total': 6}
    assert levels['CVRUN'] == {'go': 1, 'need': 3}
    assert levels['CVPOLYB'] == {'pdouble': 4}
    with open(os.path.join(dist, 'sizes.txt'), encoding='ascii') as fh:
        sizes = fh.read()
    for n in ('CVNODE', 'CVRUN', 'CVPOLYB', 'CASEVO', 'mpy-cross'):
        assert n in sizes
    with open(os.path.join(dist, 'linemap.json'), encoding='ascii') as fh:
        lm = json.load(fh)
    assert set(lm) == set(n[:-3] for n in names)
    assert lm['CVNODE']['src'].endswith('node.py')
    assert res.warnings and any('mpy-cross' in w for w in res.warnings)


def test_bundle_line_map_points_at_the_source(tmp_path):
    src, dist = _write_tree(tmp_path)
    res = bundle.bundle(src, dist, sizer=None)
    assert res.errors == []
    table = linemap.load(os.path.join(dist, 'linemap.json'))
    srcnode = _d(SAMPLE['node']).splitlines()
    devnode = open(os.path.join(dist, 'device', 'CVNODE.py'), encoding='ascii').read()
    for i, dl in enumerate(devnode.splitlines()):
        path, a, b = linemap.lookup(table, 'CVNODE', i + 1)
        assert path.endswith('node.py')
        chunk = ''.join(srcnode[a - 1:b]).replace(' ', '')
        if dl.strip() == 'pass':
            assert chunk.endswith(':')            # the header of the emptied block
        else:
            assert dl.strip().replace(' ', '') in chunk.replace('#@float-ok', '')
    # the run.py tables map to their source assignment
    run_src = _d(SAMPLE['run']).splitlines()
    run_dev = open(os.path.join(dist, 'device', 'CVRUN.py'), encoding='ascii').read()
    for i, dl in enumerate(run_dev.splitlines()):
        if dl.startswith('DEV='):
            _, a, b = linemap.lookup(table, 'cvrun', i + 1)
            assert run_src[a - 1].startswith('DEV = ')
    # the command-line tool and the traceback translation
    out = io.StringIO()
    rc = linemap.main(['--map', os.path.join(dist, 'linemap.json'), 'CVNODE', '8'], out)
    assert rc == 0
    assert 'node.py:17' in out.getvalue() and 'return t * SCALE' in out.getvalue()
    out = io.StringIO()
    assert linemap.main(['--map', os.path.join(dist, 'linemap.json'), 'CVNODE:8'], out) == 0
    assert 'node.py:17' in out.getvalue()
    tb = ('Traceback (most recent call last):\n'
          '  File "CASEVO.py", line 4, in <module>\n'
          '  File "CVNODE", line 8, in mk\n'
          'ZeroDivisionError: divide by zero\n')
    t = linemap.translate(tb, table)
    assert 'File "CVNODE", line 8, in mk  [' in t and 'node.py:17]' in t
    assert 'casevo.py:6]' in t
    out = io.StringIO()
    assert linemap.main(['--map', os.path.join(dist, 'linemap.json'), 'CVNODE', '999'],
                        out) == 1
    assert linemap.main(['--map', os.path.join(dist, 'linemap.json'), 'CVNOPE', '1'],
                        out) == 1


def test_bundle_cli(tmp_path):
    src, dist = _write_tree(tmp_path)
    env = dict(os.environ)
    env['MPY_CROSS'] = os.path.join(str(tmp_path), 'no-such-mpy-cross')
    p = subprocess.run([sys.executable, os.path.join(BUILD, 'bundle.py'), '--src', src,
                        '--dist', dist], capture_output=True, text=True, timeout=120, env=env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'CVNODE' in p.stdout and 'warning' in p.stdout
    assert os.path.exists(os.path.join(dist, 'device', 'CVNODE.py'))


def test_bundle_clears_stale_device_files(tmp_path):
    src, dist = _write_tree(tmp_path)
    dev = os.path.join(dist, 'device')
    os.makedirs(dev)
    with open(os.path.join(dev, 'CVOLD.py'), 'w') as fh:
        fh.write('x=1\n')
    assert bundle.bundle(src, dist, sizer=None).errors == []
    assert not os.path.exists(os.path.join(dev, 'CVOLD.py'))


def test_bundle_stops_on_src_lint_errors(tmp_path):
    bad = dict(SAMPLE)
    bad['alg'] = '''
        #@L 5
        import node as K


        def twice(x):
            return [K.mk(y) for y in x]
        '''
    src, dist = _write_tree(tmp_path, bad)
    res = bundle.bundle(src, dist, sizer=None)
    assert any('comprehension' in e for e in res.errors)
    assert not os.path.exists(os.path.join(dist, 'device', 'CVNODE.py'))


def test_bundle_stops_on_framelint_errors(tmp_path):
    bad = dict(SAMPLE)
    bad['alg'] = '''
        #@L 7
        import node as K


        def twice(x):
            return K.mk(x)
        '''
    src, dist = _write_tree(tmp_path, bad)
    res = bundle.bundle(src, dist, sizer=None)
    assert any('callee must be > 7' in e for e in res.errors), res.errors


@pytest.mark.parametrize('extra,frag', [
    ({'foo': 'X = 1\n'}, 'not in build/manifest.py'),
    ({'node': 'import casevo as C\n'}, 'entry module'),
    ({'polyb': None}, 'family poly'),
])
def test_bundle_src_name_checks(tmp_path, extra, frag):
    files = dict(SAMPLE)
    for k, v in extra.items():
        if v is None:
            del files[k]
        else:
            files[k] = v
    src, dist = _write_tree(tmp_path, files)
    res = bundle.bundle(src, dist, sizer=None, lint=False)
    assert any(frag in e for e in res.errors), res.errors


def test_bundle_output_lint_reports_unmarked_errors_with_the_source_line(tmp_path):
    """Without the src lint, the output lint still catches device bans, and reports the
    source line; a marker in the source silences only its own kind of error."""
    files = dict(SAMPLE)
    files['alg'] = '''
        #@L 5
        import node as K


        def twice(x):
            return [K.mk(y) for y in x]
        '''
    files['run'] = SAMPLE['run'].replace('    return MODS[key]',
                                         '    return MODS[key + "" / 1]  #@unordered-ok')
    src, dist = _write_tree(tmp_path, files)
    res = bundle.bundle(src, dist, sizer=None, lint=False)
    comp = [e for e in res.errors if 'comprehension' in e]
    assert len(comp) == 1 and 'CVALG.py:3 (' in comp[0] and 'alg.py:6)' in comp[0], comp
    div = [e for e in res.errors if "'/' in an exact module" in e]
    assert len(div) == 1 and 'CVRUN.py' in div[0], res.errors   # the wrong marker


def test_bundle_warnings(tmp_path):
    files = dict(SAMPLE)
    files['run'] = _d(SAMPLE['run']).replace(
        "DEV = {'poly': 'poly', 'polyb': 'polyb', 'polyc': 'polyc'}\n", '').replace(
        '__import__(DEV[p])', '__import__(p)')
    src, dist = _write_tree(tmp_path, files)
    res = bundle.bundle(src, dist, sizer=None, lint=False)
    assert res.errors == []
    assert any('no literal DEV' in w for w in res.warnings), res.warnings
    empty = tmp_path / 'empty'
    empty.mkdir()
    res = bundle.bundle(str(empty), str(tmp_path / 'd3'), sizer=None)
    assert res.errors == [] and any('no src files' in w for w in res.warnings)


def test_bundle_run_tables_must_agree_with_the_manifest(tmp_path):
    files = dict(SAMPLE)
    files['run'] = SAMPLE['run'].replace("('poly', 'polyb', 'polyc')}", "('poly', 'polyb')}")
    src, dist = _write_tree(tmp_path, files)
    res = bundle.bundle(src, dist, sizer=None, lint=False)
    assert any('PARTS' in e and 'manifest' in e for e in res.errors), res.errors
    files['run'] = SAMPLE['run'].replace("'polyc': 'polyc'", "'polyc': 'poly'")
    src2, dist2 = _write_tree(tmp_path / 'b', files)
    res = bundle.bundle(src2, dist2, sizer=None, lint=False)
    assert any('DEV' in e for e in res.errors), res.errors


def test_bundle_line_budgets(tmp_path):
    man = bundle.load_manifest()
    ns = dict(vars(man))
    ns['LAZYMAX'] = 10
    small = bundle.Manifest(ns)
    src, dist = _write_tree(tmp_path)
    res = bundle.bundle(src, dist, man=small, sizer=None)
    assert any('CVPOLY' in e and 'LAZYMAX' in e for e in res.errors), res.errors
    ns = dict(vars(man))
    rows = []
    for r in man.MODULES:
        rows.append((r[0], r[1], r[2], 5, r[4]) if r[0] == 'node' else r)
    ns['MODULES'] = tuple(rows)
    src2, dist2 = _write_tree(tmp_path / 'b')
    res = bundle.bundle(src2, dist2, man=bundle.Manifest(ns), sizer=None)
    assert any('CVNODE' in e and 'line budget' in e for e in res.errors), res.errors


def test_bundle_size_gate(tmp_path):
    src, dist = _write_tree(tmp_path)
    seen = []

    def big(path):
        seen.append(os.path.basename(path))
        return 10 ** 6 if path.endswith('CVNODE.py') else 100
    res = bundle.bundle(src, dist, sizer=big)
    assert 'CVNODE.py' in seen and 'CVPOLY.py' in seen
    assert any('CVNODE' in e and 'KB' in e for e in res.errors), res.errors
    assert not any('mpy-cross' in w for w in res.warnings)
    # COST uses the .mpy size when there is one
    res = bundle.bundle(src, os.path.join(str(tmp_path), 'd2'), sizer=lambda p: 100)
    assert res.errors == []
    man = bundle.load_manifest()
    run = open(os.path.join(str(tmp_path), 'd2', 'device', 'CVRUN.py'),
               encoding='ascii').read()
    assert "COST={'poly':%d," % int(100 * man.FACTOR) in run


def test_bundle_with_real_mpy_cross_if_installed(tmp_path):
    sizer = bundle.mpy_sizer()
    if sizer is None:
        pytest.skip('mpy-cross is not installed (set MPY_CROSS or pip install mpy-cross)')
    src, dist = _write_tree(tmp_path)
    res = bundle.bundle(src, dist, sizer=sizer)
    assert res.errors == [], res.errors
    assert res.mpy['CVNODE'] > 0
