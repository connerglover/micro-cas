"""M0.5 memory gate (DESIGN 18.7): build/genprobe.py and the generated probe/PRBL*.py modules.

- The generator: exact line counts, determinism, prefix-consistent 100-line blocks with a
  balanced mix, per-module names.
- The committed probe modules: fresh, ASCII/LF, inside the device subset (the src lint),
  bodies that only define, importable, and accepted by MicroPython's own compiler (mpy-cross,
  when found) with the recorded .mpy sizes.
- The gate: PRBMEM transcripts (typed from screenshots, or from a desktop dry run) parse; the
  derivation of FACTOR, PEAKB, LAZYMAX, NMAX, the eviction mechanism and the CVDRAW residency
  follows DESIGN 18.7 on hand-checked numbers; the provisional model reproduces the DESIGN
  18.1 ledger; --apply rewrites only the gate's constants of build/manifest.py.
"""
import ast
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, 'build')
PROBE = os.path.join(ROOT, 'probe')
if BUILD not in sys.path:
    sys.path.insert(0, BUILD)

import bundle  # noqa: E402
import genprobe  # noqa: E402
import lint  # noqa: E402

NAMES = ('PRBL100', 'PRBL200', 'PRBL300')
HEAD_NAMES = {'K', 'R', 'A', 'MAXSTEP'}


def _probe_text(name):
    """The file's bytes with CRLF read as LF (a checkout with core.autocrlf; MicroPython reads
    both)."""
    with open(os.path.join(PROBE, name + '.py'), 'rb') as fh:
        return fh.read().replace(b'\r\n', b'\n')


def _toplevel_names(src):
    out = set()
    for st in ast.parse(src).body:
        if isinstance(st, ast.FunctionDef):
            out.add(st.name)
        elif isinstance(st, ast.Assign):
            for t in st.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out.add(n.id)
    return out


# -- the generator ----------------------------------------------------------------------------

@pytest.mark.parametrize('n', (2, 3, 37, 99, 100, 101, 150, 199, 200, 250, 300, 301, 450))
def test_generate_gives_exactly_n_device_lines(n):
    text = genprobe.generate(n)
    assert len(bundle.minify(text).lines) == n
    compile(text, 'PRBL%d.py' % n, 'exec')
    assert text == genprobe.generate(n)                  # deterministic


def test_generate_rejects_tiny_modules():
    with pytest.raises(ValueError):
        genprobe.generate(1)


def test_blocks_are_prefixes():
    # PRBL200 is PRBL100 plus a second block, PRBL300 adds a third (same tag)
    a100 = bundle.minify(genprobe.module_source(100, 'a')).lines
    a200 = bundle.minify(genprobe.module_source(200, 'a')).lines
    a300 = bundle.minify(genprobe.module_source(300, 'a')).lines
    assert a200[:100] == a100
    assert a300[:200] == a200


def test_groups_cover_every_template_once_and_are_balanced():
    used = [k for g in genprobe.GROUPS for k in g]
    assert sorted(used) == sorted(genprobe.TEMPLATES)
    sizes = genprobe.template_lines()
    head = len(bundle.minify(genprobe.HEAD).lines)
    dens = []
    for k, g in enumerate(genprobe.GROUPS):
        room = genprobe.BLOCK - (head if k == 0 else 0)
        lines = sum(sizes[t] for t in g)
        assert room - 3 <= lines <= room, (g, lines)    # at most 3 padding lines
        src = '\n'.join(genprobe.TEMPLATES[t].replace('@', '0') for t in g)
        dens.append(genprobe.stats(src)['nodes_per_line'])
    mean = sum(dens) / len(dens)
    for d in dens:                                      # similar parse density per block
        assert abs(d - mean) <= 0.1 * mean, dens


def test_module_names_are_per_module():
    names = {}
    for n in genprobe.SIZES:
        names[n] = _toplevel_names(genprobe.generate(n)) - HEAD_NAMES
    assert names[100] and names[200] and names[300]
    assert not names[100] & names[200]
    assert not names[100] & names[300]
    assert not names[200] & names[300]
    for n in genprobe.SIZES:
        assert all(re.search(genprobe.TAGS[n] + r'\d+$', s) for s in names[n]), names[n]


def test_probe_code_is_shaped_like_ours():
    # parse density (the compile peak scales with it) near the real src/ code (8.5-11 AST
    # nodes per line at hand-off), slightly denser so PEAKB errs high; every module has an
    # explicit-stack loop and string tables, PRBL200 and PRBL300 also generators
    for n in genprobe.SIZES:
        s = genprobe.stats(genprobe.generate(n))
        assert 10.0 <= s['nodes_per_line'] <= 12.5, (n, s)
        assert s['strings'] >= 25 and s['defs'] >= 6
        if n >= 200:
            assert s['generators'] == 2


# -- the committed probe modules ------------------------------------------------------------

def test_probe_files_are_fresh():
    assert genprobe.stale() == [], 'run: python build/genprobe.py'
    assert genprobe.main(['--check']) == 0


@pytest.mark.parametrize('name', NAMES)
def test_probe_file_is_device_python(name):
    raw = _probe_text(name)
    src = raw.decode('ascii')                           # ASCII only
    assert b'\r' not in raw                             # no stray CR
    assert re.fullmatch(r'[A-Z][A-Z0-9]{0,7}', name)    # a device module name
    assert lint.lint(src, name + '.py', device_names=True) == []
    n = int(name[4:])
    assert len(bundle.minify(src).lines) == n
    # the body only defines functions and literal tables (no call at import, so the module
    # imports at any depth: PROBE6 imp6 imports PRBL300 from depth 6)
    for st in ast.parse(src).body:
        if isinstance(st, ast.FunctionDef):
            continue
        assert isinstance(st, ast.Assign), ast.dump(st)
        ast.literal_eval(st.value)
    for nd in ast.walk(ast.parse(src)):
        assert not isinstance(nd, (ast.Lambda, ast.ListComp, ast.GeneratorExp, ast.SetComp,
                                   ast.DictComp, ast.ClassDef, ast.With, ast.Import,
                                   ast.ImportFrom))


@pytest.mark.parametrize('name', NAMES)
def test_probe_file_imports_and_defines(name):
    src = _probe_text(name).decode('ascii')
    ns = {}
    exec(compile(src, name + '.py', 'exec'), ns)
    fns = [v for k, v in ns.items() if callable(v) and not k.startswith('__')]
    assert len(fns) == sum(isinstance(s, ast.FunctionDef) for s in ast.parse(src).body)
    assert ns['K'] is None and ns['MAXSTEP'] == 400


def test_mpy_cross_accepts_the_probes_with_the_recorded_sizes():
    sizer = bundle.mpy_sizer()
    if sizer is None:
        pytest.skip('mpy-cross is not installed (set MPY_CROSS or pip install mpy-cross)')
    for name in NAMES:
        got = sizer(os.path.join(PROBE, name + '.py'))
        assert got == genprobe.MPY_BYTES[name], (name, got)


# -- reading PRBMEM transcripts -----------------------------------------------------------------

# As typed from the screenshots: page prompts, framing, PRBMEM's 3-line module records.
TRANSCRIPT = '''PRBMEM v1
start 151234
tup2 16
tup3 32
tup4 32
tup5 32
tup7 48
tup9 48
-- p1: screenshot, key --
list3 48
dict2 80
inst2 64
float 16
int64 32
str20 48
clos 32
gen 80
-- p2: screenshot, key --
slot 4
arr 4
dent 12
sys.modules yes
delmod ok reimport new
dictclr ok
PRBMOD cost 600 ms 40
 kept 300 k2 20 kD 16
-- p3: screenshot, key --
 peak 2100
PRBL100 cost 3100 ms 210
 kept 900 k2 120 kD 100
 peak 11000
PRBL200 cost 5800 ms 400
 kept 700 k2 150 kD 120
 peak 20000
PRBL300 cost 8500 ms 600
-- p4: screenshot, key --
 kept 800 k2 180 kD 140
 peak 29500
end 140000
== PRBMEM end, p5 ==
'''


def _set(text, **repl):
    for k, v in repl.items():
        text = re.sub(r'(?m)^%s .*$' % re.escape(k.replace('_', '.')), v, text)
    return text


def test_parse_prbmem_device_transcript():
    r = genprobe.parse_prbmem(TRANSCRIPT)
    assert r['unparsed'] == []
    assert r['start'] == 151234 and r['end'] == 140000
    assert r['shapes']['tup4'] == 32 and r['shapes']['slot'] == 4 and r['shapes']['dent'] == 12
    assert set(r['shapes']) == set(genprobe.SHAPES)
    assert r['sysmod'] is True and r['delmod'] == 'ok' and r['reimport'] == 'new'
    assert r['dictclr'] == 'ok'
    assert r['mods']['PRBL300'] == {'cost': 8500, 'ms': 600, 'kept': 800, 'k2': 180,
                                    'kD': 140, 'peak': 29500}
    assert r['mods']['PRBMOD']['peak'] == 2100


def test_parse_prbmem_hand_typed_variants():
    # CRLF, tabs instead of the leading space, a record typed on one line, errors
    text = ('PRBL100 cost 3100 ms 210\r\n\tkept 900 k2 120 kD 100\r\n peak E:MemoryError\r\n'
            'PRBL200 cost 5800 ms 400 kept 700 k2 150 kD 120 peak 20000\n'
            'PRBL300 missing\n'
            'PRBMOD MemoryError\n'
            'delmod E:KeyError\n'
            'something odd\n')
    r = genprobe.parse_prbmem(text)
    assert r['mods']['PRBL100'] == {'cost': 3100, 'ms': 210, 'kept': 900, 'k2': 120,
                                    'kD': 100, 'peak_error': 'E:MemoryError'}
    assert r['mods']['PRBL200']['peak'] == 20000
    assert r['mods']['PRBL300'] == {'status': 'missing'}
    assert r['mods']['PRBMOD'] == {'status': 'MemoryError'}
    assert r['delmod'] == 'E:KeyError'
    assert r['unparsed'] == ['something odd']


# -- the derivation (DESIGN 18.7) -------------------------------------------------------------

def test_fit():
    assert genprobe.fit([(1, 3), (2, 5), (3, 7)]) == pytest.approx((1.0, 2.0))
    assert genprobe.fit([(100, 5), (100, 6)]) is None


def test_derive_hand_checked_numbers():
    g = genprobe.derive(genprobe.parse_prbmem(TRANSCRIPT))
    # FACTOR = (3100 + 5800 + 8500) / (1498 + 2856 + 4205) = 2.0329, rounded up
    assert sum(genprobe.MPY_BYTES.values()) == 8559
    assert g['FACTOR'] == 2.04
    assert g['BPL'] == pytest.approx(2.04 * 12.5)
    # transient = peak - cost + (kept1 - kept2): 8680, 14750, 21620 -> 86.8 B/line at worst
    tr = dict((r['name'], r['transient']) for r in g['modules'])
    assert tr == {'PRBL100': 8680, 'PRBL200': 14750, 'PRBL300': 21620}
    assert g['PEAKB'] == 87
    assert g['LAZYMAX'] == 140                          # floor(12288 / 87) to a multiple of 10
    assert g['reserve150'] == 150 * 87
    assert any('LAZYMAX 140 < 150' in w for w in g['warnings'])
    assert g['NMAX'] == 768                             # 36864 / (32 + 4 x 4)
    assert g['EVICT'] == 'modules'
    assert g['leak'] == 168                             # k2 120 scaled to a 140-line part
    a, b = g['fits']['transient']
    assert b == pytest.approx(64.7, abs=0.01) and a == pytest.approx(2076.7, abs=0.1)
    # the ledger and the rows use the measured numbers
    items, lazy = genprobe.ledger(g['BPL'], 87, 140, 768, 32, 4, 3072)
    assert g['lazy'] == lazy and g['ledger'] == items
    assert g['DRAW_EVICTABLE'] == (not all(r[2] for r in g['rows']))
    rep = genprobe.report(g)
    assert 'FACTOR = 2.04' in rep and "EVICT = 'modules'" in rep


def test_derive_eviction_fallbacks():
    base = genprobe.parse_prbmem(TRANSCRIPT)
    # sys.modules deletion leaves too much, __dict__.clear() frees it: 'dict'
    r = genprobe.parse_prbmem(TRANSCRIPT.replace('k2 120 kD 100', 'k2 3000 kD 100'))
    assert genprobe.derive(r)['EVICT'] == 'dict'
    # neither works: 'none', with the DESIGN 18.5 consequences as a warning
    r = genprobe.parse_prbmem(TRANSCRIPT.replace('k2 120 kD 100', 'k2 3000 kD 2900'))
    g = genprobe.derive(r)
    assert g['EVICT'] == 'none' and any('no eviction' in w for w in g['warnings'])
    # no sys.modules at all
    r = dict(base, sysmod=False)
    assert genprobe.derive(r)['EVICT'] == 'none'
    # deletion does not re-import a new module
    r = dict(base, reimport='same')
    assert genprobe.derive(r)['EVICT'] == 'dict'


def test_derive_lazymax_and_nmax_warnings():
    # transients 3680, 4750, 6120: 36.8 B/line at worst -> PEAKB 37, LAZYMAX 330
    small = TRANSCRIPT.replace(' peak 11000', ' peak 6000').replace(
        ' peak 20000', ' peak 10000').replace(' peak 29500', ' peak 14000')
    g = genprobe.derive(genprobe.parse_prbmem(small))
    assert g['PEAKB'] == 37 and g['LAZYMAX'] == 330
    assert any('may be merged' in w for w in g['warnings'])
    huge = TRANSCRIPT.replace(' peak 11000', ' peak 40000')
    g = genprobe.derive(genprobe.parse_prbmem(huge))
    assert g['LAZYMAX'] < 50 and any('.mpy' in w for w in g['warnings'])
    fat = TRANSCRIPT.replace('tup4 32', 'tup4 64')
    g = genprobe.derive(genprobe.parse_prbmem(fat))
    assert g['TUPB'] == 64 and g['NMAX'] == 448             # 36864 / 80 = 460.8 -> 448
    assert any('NMAX 448 < 512' in w for w in g['warnings'])


def test_derive_partial_and_invalid_transcripts():
    # one module missing, one without a peak: still derived, with warnings
    text = TRANSCRIPT.replace(' peak 20000', ' peak E:MemoryError')
    text = re.sub(r'PRBL300 cost 8500 ms 600\n.*\n.*\n.*\n', 'PRBL300 missing\n', text)
    g = genprobe.derive(genprobe.parse_prbmem(text))
    assert [r['name'] for r in g['modules']] == ['PRBL100', 'PRBL200']
    assert any('PRBL300: missing' in w for w in g['warnings'])
    assert any('PRBL200: no peak' in w for w in g['warnings'])
    assert g['FACTOR'] == 2.05                  # (3100 + 5800) / (1498 + 2856) = 2.044, up
    # no probe module at all
    with pytest.raises(ValueError):
        genprobe.derive(genprobe.parse_prbmem('PRBL100 missing\nPRBL200 missing\n'))
    # a desktop dry run without a mem_free: all costs 0
    zero = re.sub(r'cost \d+', 'cost 0', TRANSCRIPT)
    with pytest.raises(ValueError):
        genprobe.derive(genprobe.parse_prbmem(zero))


# -- the provisional model and the manifest -----------------------------------------------------

def test_provisional_model_reproduces_the_design_ledger():
    g = genprobe.provisional()
    led = dict((k.split(' (')[0], b / 1024.0) for k, b in g['ledger'])
    assert led['free after ti_system and ti_graphics'] == 173
    assert led['resident code'] == pytest.approx(-58, abs=1)
    assert led['boot buffers'] == pytest.approx(-28, abs=0.5)
    assert led['command working set'] == pytest.approx(-32, abs=0.5)
    assert led['reserve'] == pytest.approx(-15, abs=0.5)
    assert g['lazy'] / 1024.0 == pytest.approx(40, abs=1)       # DESIGN 18.1: about 40
    rows = dict((r[0], r) for r in g['rows'])
    # DESIGN 18.2 "yes" rows fit; its "no" rows do not, except limit, which the per-line
    # model puts just inside (38.9 of 40.1 KB; the design rounds each module up to whole KB)
    for label in ('simplify, expand', 'factor', 'solve', 'diff, grad', 'taylor',
                  'integrate S0-S2', 'F1 menu, F5 help'):
        assert rows[label][2], label
    for label in ('integrate S3-S8', 'definite (integrate phase)', 'sum',
                  'desolve (integrate phase)'):
        assert not rows[label][2], label
    assert abs(rows['limit'][1] - g['lazy']) < 3 * 1024


def test_manifest_holds_the_gate_constants():
    man = bundle.load_manifest(genprobe.MANIFEST)
    assert bundle.check_manifest(man) == []
    for name in genprobe.CONSTS:
        assert hasattr(man, name), name
    assert man.EVICT in ('modules', 'dict', 'none')
    assert isinstance(man.DRAW_EVICTABLE, bool)
    assert isinstance(man.NMAX, int) and man.NMAX % 64 == 0 and man.NMAX >= 512
    if man.CALIBRATION == 'provisional':
        # until the device run, the DESIGN 18 numbers (DESIGN 4.1 keeps CVDRAW resident)
        for name in ('FACTOR', 'PEAKB', 'NMAX', 'EVICT', 'FRAG', 'MPYB'):
            assert getattr(man, name) == genprobe.PROVISIONAL[name], name
        # packs are compiled off the calculator (docs/notes/FASTBOOT.md): LAZYMAX is a line
        # budget for the build, no longer the on-calculator compile reserve
        assert man.LAZYMAX >= genprobe.PROVISIONAL['LAZYMAX']
        assert man.DRAW_EVICTABLE is False


def test_apply_manifest_rewrites_only_the_gate_constants(tmp_path):
    path = str(tmp_path / 'manifest.py')
    shutil.copy(genprobe.MANIFEST, path)
    with open(path, encoding='utf-8') as fh:
        before = fh.read().splitlines()
    g = genprobe.derive(genprobe.parse_prbmem(TRANSCRIPT))
    ch = genprobe.apply_manifest(g, path)
    assert [c[0] for c in ch] == list(genprobe.CONSTS)
    with open(path, encoding='utf-8') as fh:
        after = fh.read().splitlines()
    assert len(after) == len(before)
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    for old, new in changed:
        name = new.split('=')[0].strip()
        assert name in genprobe.CONSTS, new
        if '#' in old:                                  # the trailing comment survives
            assert new.endswith(old[old.index('#'):])
    man = bundle.load_manifest(path)
    assert bundle.check_manifest(man) == []
    assert (man.FACTOR, man.PEAKB, man.LAZYMAX, man.NMAX, man.EVICT, man.CALIBRATION) == \
        (2.04, 87, 140, 768, 'modules', 'M0.5')
    assert man.DRAW_EVICTABLE is g['DRAW_EVICTABLE']
    # applying again is stable
    genprobe.apply_manifest(g, path)
    with open(path, encoding='utf-8') as fh:
        assert fh.read().splitlines() == after


def test_apply_manifest_needs_every_constant(tmp_path):
    path = str(tmp_path / 'manifest.py')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('FACTOR = 1.8\nPEAKB = 80   # x\n')
    g = genprobe.derive(genprobe.parse_prbmem(TRANSCRIPT))
    with pytest.raises(ValueError):
        genprobe.apply_manifest(g, path)


def test_cli(tmp_path, capsys, monkeypatch):
    assert genprobe.main(['--provisional']) == 0
    assert 'lazy code budget' in capsys.readouterr().out
    t = tmp_path / 'prbmem.txt'
    t.write_text(TRANSCRIPT, encoding='utf-8')
    assert genprobe.main(['--derive', str(t)]) == 0
    out = capsys.readouterr().out
    assert 'PEAKB 87 B/line' in out and 'LAZYMAX = 140' in out
    man = tmp_path / 'manifest.py'
    shutil.copy(genprobe.MANIFEST, str(man))
    monkeypatch.setattr(genprobe, 'MANIFEST', str(man))
    before = bundle.load_manifest(genprobe.MANIFEST).LAZYMAX
    assert genprobe.main(['--derive', str(t), '--apply']) == 0
    assert 'manifest LAZYMAX: %d -> 140' % before in capsys.readouterr().out
    assert bundle.load_manifest(str(man)).LAZYMAX == 140
    assert genprobe.main(['--bogus']) == 2


# -- the probes on the desktop: PRBMEM and PROBE6 with the generated modules ---------------------

def _run(tmp_path, name, prelude=''):
    d = tmp_path / ('run_' + name)
    d.mkdir()
    for f in os.listdir(PROBE):
        if f.endswith('.py') or f.endswith('.mpy'):
            shutil.copy(os.path.join(PROBE, f), str(d / f))
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env['PYTHONIOENCODING'] = 'ascii'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    code = 'import sys; sys.path.insert(0, %r)\n%s\nfrom %s import *\n' % (str(d), prelude, name)
    p = subprocess.run([sys.executable, '-c', code], cwd=str(d), env=env, capture_output=True,
                       text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_prbmem_dry_run_transcript_feeds_the_gate(tmp_path):
    # tracemalloc stands in for gc.mem_free, so the costs are CPython's (meaningless for the
    # device, but positive): the transcript format and the whole pipeline are exercised
    out = _run(tmp_path, 'PRBMEM', 'import gc, tracemalloc\ntracemalloc.start()\n'
               'gc.mem_free = lambda: 400000 - tracemalloc.get_traced_memory()[0]')
    r = genprobe.parse_prbmem(out)
    assert r['unparsed'] == []
    assert set(r['shapes']) == set(genprobe.SHAPES)
    for name in NAMES + ('PRBMOD',):
        assert set(r['mods'][name]) == {'cost', 'ms', 'kept', 'k2', 'kD', 'peak'}, name
        assert r['mods'][name]['cost'] > 0
    assert r['sysmod'] and r['delmod'] == 'ok' and r['dictclr'] == 'ok'
    g = genprobe.derive(r)
    assert g['FACTOR'] > 0 and [m['name'] for m in g['modules']] == list(NAMES)


def test_probe6_imports_prbl300_from_depth_6(tmp_path):
    out = _run(tmp_path, 'PROBE6')
    imp = [s for s in out.splitlines() if s.startswith('imp6')]
    assert imp and imp[0].startswith('imp6 ok'), out
