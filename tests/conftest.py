"""pytest harness for cas-evo (DESIGN.md section 20.1).

- Puts src/, shim/ and tests/support on sys.path; turns off CPython's int/str digit limit.
- Runs every test's call phase under the depth checker (section 20.2): default mode
  (gen_penalty 0, per-frame level assertion) or, with --strict-depth or the strict_depth
  marker, strict mode (every penalty 1, budget 8 only).
- After each passing test: the node-table invariant scan (section 8.9), SIMPBUG == 0,
  K.NN == K.BASE if the test ran a full command through run.go, and no 'internal error'
  record from run.go.
- After every test: SIMPBUG is zeroed and K.reset() empties the node table, so node ids never
  leak from one test into the next (fixtures must not keep ids across tests).
- Injects desktop stand-ins for the native hooks the UI sets on the device (node.ESC,
  node.MEMFREE, run.MEMFREE, run.BUSY) when a module leaves them at None.

Markers: device_base(n), slow, oracle, bundled, strict_depth, no_depth, no_invariants,
invariants_skip(*checks), allow_internal_error. Options: --strict-depth, --no-depth-check,
--update-golden, --bundled. Fixtures: evodepth, update_golden. See docs/notes/M0.1.md.
"""
import importlib
import importlib.abc
import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
SHIM = os.path.join(ROOT, 'shim')
SUPPORT = os.path.join(HERE, 'support')
DIST = os.path.join(ROOT, 'dist', 'device')

for _p in (HERE, SUPPORT, SHIM, SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.set_int_max_str_digits(0)       # the device has no int<->str digit limit

import evodepth  # noqa: E402

BUDGET = evodepth.BUDGET            # 8: the device hard limit is 10; keep 2 frames of margin
DEFAULT_BASE = 2                    # depth of the caller of unannotated device code

MARKERS = (
    'device_base(n): device depth of the caller of the code under test (overrides the '
    'automatic base: root device frames then start at n + 1)',
    'slow: oracle corpora, fuzz and other long tests (skip with -m "not slow")',
    'oracle: compares against the SymPy oracle',
    'bundled: runs only with --bundled (against dist/device)',
    'strict_depth: run this test with every depth penalty at 1 (budget 8 only)',
    'no_depth: run this test without the depth checker',
    'no_invariants: skip the node-table invariant scan after this test',
    'invariants_skip(*checks): skip the named invariant checks (invariants.CHECKS, plus '
    "'base' for the K.NN == K.BASE check after a full command)",
    'allow_internal_error: this test expects run.go to report an internal error',
)

# native hooks the UI injects on the device: (module, attribute, desktop stand-in)
HOOKS = (
    ('node', 'ESC', lambda: False),
    ('node', 'MEMFREE', lambda: 1 << 20),
    ('run', 'MEMFREE', lambda: 1 << 20),
    ('run', 'BUSY', lambda steps: None),
)


_CURRENT = [None]                   # the running test item (for keyscript.AFTER_RUN)


class _State(object):
    bundled = False
    device_dir = SRC
    levels = None
    entry_files = ()


STATE = _State()


# -- options and configuration ----------------------------------------------------------------

def pytest_addoption(parser):
    g = parser.getgroup('cas-evo')
    g.addoption('--strict-depth', action='store_true', default=False,
                help='run every test with all depth penalties at 1 (budget 8 only)')
    g.addoption('--no-depth-check', action='store_true', default=False,
                help='do not run tests under the depth checker (debugging only)')
    g.addoption('--update-golden', action='store_true', default=False,
                help='rewrite the golden files (review the diff!)')
    g.addoption('--bundled', action='store_true', default=False,
                help='run the suite against dist/device (DESIGN 19.2)')


def pytest_configure(config):
    for m in MARKERS:
        config.addinivalue_line('markers', m)
    if config.getoption('--bundled', default=False):
        _setup_bundled()
    else:
        STATE.device_dir = SRC
        STATE.entry_files = (os.path.join(SRC, 'casevo.py'),)
    _setup_keyscript()


def _setup_keyscript():
    """End-to-end sessions (M0.2's keyscript.run): register the per-session checks."""
    try:
        import keyscript
    except Exception:                   # noqa: BLE001 - M0.2 not there or broken: no e2e checks
        return
    if STATE.bundled and STATE.entry_files:
        keyscript.SRC = STATE.device_dir
        keyscript.ENTRY = STATE.entry_files[0]
    if _session_check not in keyscript.AFTER_RUN:
        keyscript.AFTER_RUN.append(_session_check)


def _strings_in(x, depth=3):
    """Every str inside x (tuples and lists, a few levels deep)."""
    out = []
    st = [(x, 0)]
    while st:
        y, d = st.pop()
        if isinstance(y, str):
            out.append(y)
        elif isinstance(y, (tuple, list)) and d < depth:
            for z in y:
                st.append((z, d + 1))
    return out


def _session_check(sess):
    """keyscript.AFTER_RUN: the session's own modules pass the post-test checks too."""
    item = _CURRENT[0]
    mods = getattr(sess, 'mods', None) or {}
    msgs = []
    noinv = item is not None and item.get_closest_marker('no_invariants') is not None
    K = mods.get('node')
    if K is not None and hasattr(K, 'N') and hasattr(K, 'NN') and not noinv:
        import invariants
        errs = invariants.scan(K)
        if errs:
            msgs.append('session node table: ' + '; '.join(errs[:5]))
        if hasattr(K, 'BASE') and K.NN != K.BASE:
            msgs.append('after the session K.NN == %d, not BASE == %d' % (K.NN, K.BASE))
    R = mods.get('run')
    allow = item is not None and item.get_closest_marker('allow_internal_error') is not None
    if R is not None and not allow:
        for t in _strings_in(getattr(R, 'HIST', None) or []):
            if t.startswith('internal error'):
                msgs.append('the session reported a bug: %r' % t)
    for name in sorted(mods):
        if getattr(mods[name], 'SIMPBUG', 0):
            msgs.append('session %s.SIMPBUG == %r' % (name, mods[name].SIMPBUG))
    if msgs:
        raise AssertionError('\n'.join(msgs))


def _setup_bundled():
    STATE.bundled = True
    STATE.device_dir = DIST
    while SRC in sys.path:
        sys.path.remove(SRC)
    sys.path.insert(0, DIST)
    names = {}
    man = os.path.join(ROOT, 'build', 'manifest.py')
    if os.path.exists(man):
        ns = {}
        with open(man, encoding='utf-8') as fh:
            exec(compile(fh.read(), man, 'exec'), ns)
        for row in ns.get('MODULES', ()):
            names[row[0]] = row[1]
        entry = ns.get('ENTRY')
        if entry:
            names[entry[0]] = entry[1]
            STATE.entry_files = (os.path.join(DIST, entry[1] + '.py'),)
    if names:
        sys.meta_path.insert(0, _DeviceAlias(names))
    lv = os.path.join(ROOT, 'dist', 'levels.json')
    if os.path.exists(lv):
        with open(lv, encoding='utf-8') as fh:
            table = json.load(fh)
        out = {}
        for mod in table:
            path = evodepth.norm_path(os.path.join(DIST, mod + '.py'))
            for fn in table[mod]:
                out[(path, fn)] = table[mod][fn]
        STATE.levels = out
    else:
        STATE.levels = {}           # no level table: no automatic base, no level assertion


class _DeviceAlias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Bundled tier: 'import node' loads dist/device/CVNODE.py and binds it as 'node' too."""

    def __init__(self, names):
        self.names = names

    def find_spec(self, name, path=None, target=None):
        dev = self.names.get(name)
        if dev is None or dev == name:
            return None
        return importlib.util.spec_from_loader(name, self)

    def create_module(self, spec):
        return importlib.import_module(self.names[spec.name])

    def exec_module(self, module):
        pass


def _levels():
    if STATE.levels is None:
        import framelint
        STATE.levels = framelint.level_table(STATE.device_dir)
    return STATE.levels


def make_checker(base=None, strict=False):
    """A DepthChecker configured like the conftest's (for tests that need their own)."""
    levels = _levels() or None
    pen = 1 if strict else 0
    return evodepth.DepthChecker(
        [STATE.device_dir], base=DEFAULT_BASE if base is None else base, budget=BUDGET,
        native_penalty=1, dunder_penalty=1, gen_penalty=pen, levels=levels,
        auto_base=(base is None and levels is not None),
        check_levels=(not strict and levels is not None),
        entry_files=STATE.entry_files)


def pytest_collection_modifyitems(config, items):
    if config.getoption('--bundled'):
        return
    skip = pytest.mark.skip(reason='needs --bundled')
    for it in items:
        if it.get_closest_marker('bundled') is not None:
            it.add_marker(skip)


# -- per-test machinery ----------------------------------------------------------------------

_DEVMOD = {}                        # id(module) -> (module, is a device module)


def _device_modules():
    """Loaded modules whose file is in the device dir."""
    d = evodepth.norm_path(STATE.device_dir) + os.sep
    out = []
    for name in sorted(sys.modules):
        m = sys.modules.get(name)
        hit = _DEVMOD.get(id(m))
        if hit is None or hit[0] is not m:
            f = getattr(m, '__file__', None)
            hit = _DEVMOD[id(m)] = (m, bool(f) and evodepth.norm_path(f).startswith(d))
        if hit[1] and m not in out:
            out.append(m)
    return out


def _node():
    K = sys.modules.get('node')
    if K is not None and hasattr(K, 'N') and hasattr(K, 'NN'):
        return K
    return None


def _inject_hooks():
    for mod, attr, fn in HOOKS:
        m = sys.modules.get(mod)
        if m is not None and hasattr(m, attr) and getattr(m, attr) is None:
            setattr(m, attr, fn)
    K = _node()
    if K is not None and hasattr(K, 'ONRESET') and K.ONRESET is None:
        K.ONRESET = _on_reset


class _ResetScan(object):
    """Scans the table each time node.reset() runs, if node.py calls its ONRESET hook first.

    node.py opts in with ``ONRESET = None  #@native`` and, at the top of ``reset()``,
    ``if ONRESET is not None: ONRESET()``. Then the invariants of every command's table are
    checked before R.go truncates it (the post-test scan alone sees only what survives).
    """
    on = False
    skip = ()
    found = []


def _on_reset():
    if not _ResetScan.on or len(_ResetScan.found) >= 3:
        return
    K = _node()
    if K is not None:
        import invariants
        errs = invariants.scan(K, _ResetScan.skip)
        if errs:
            _ResetScan.found.append(errs)


class _GoSpy(object):
    """Wraps run.go during a test to see full commands and their records."""

    def __init__(self):
        self.calls = 0
        self.records = []
        self.mod = None
        self.orig = None

    def install(self):
        m = sys.modules.get('run')
        go = getattr(m, 'go', None) if m is not None else None
        if go is None or not callable(go) or m not in _device_modules():
            return self
        self.mod = m
        self.orig = go
        spy = self

        def go_spy(job, *a, **kw):
            try:
                r = go(job, *a, **kw)
            finally:
                spy.calls += 1
            spy.records.append(r)
            return r
        m.go = go_spy
        return self

    def remove(self):
        if self.mod is not None:
            self.mod.go = self.orig
            self.mod = None

    def internal_errors(self):
        out = []
        for r in self.records:
            if isinstance(r, tuple):
                for x in r[:2]:
                    if isinstance(x, str) and x.startswith('internal error'):
                        out.append(r)
                        break
        return out


def _post_checks(item, dc, spy):
    msgs = []
    if dc is not None:
        msgs.extend(evodepth.failures(dc))
    K = _node()
    skip = ()
    m = item.get_closest_marker('invariants_skip')
    if m is not None:
        skip = tuple(m.args)
    noinv = item.get_closest_marker('no_invariants') is not None
    for errs in _ResetScan.found:
        msgs.append('node-table invariants violated before a reset:\n  ' +
                    '\n  '.join(errs[:15]))
    if K is not None and not noinv:
        import invariants
        errs = invariants.scan(K, skip)
        if errs:
            more = '' if len(errs) <= 15 else '\n  ... and %d more' % (len(errs) - 15)
            msgs.append('node-table invariants violated:\n  ' + '\n  '.join(errs[:15]) + more)
    for mod in _device_modules():
        v = getattr(mod, 'SIMPBUG', 0)
        if v:
            msgs.append('%s.SIMPBUG == %r: a simplify candidate failed verification'
                        % (mod.__name__, v))
    if spy.calls and K is not None and hasattr(K, 'BASE') and K.NN != K.BASE and (
            not noinv and 'base' not in skip):
        msgs.append('after a full command K.NN == %d, not BASE == %d' % (K.NN, K.BASE))
    if item.get_closest_marker('allow_internal_error') is None:
        for r in spy.internal_errors():
            msgs.append('run.go reported a bug: %r' % (r,))
    return msgs


def _cleanup():
    _ResetScan.on = False
    _CURRENT[0] = None
    ks = sys.modules.get('keyscript')
    if ks is not None and hasattr(ks, 'reset_shims'):
        ks.reset_shims()
    msgs = []
    for mod in _device_modules():
        if getattr(mod, 'SIMPBUG', 0):
            mod.SIMPBUG = 0
    K = _node()
    reset = getattr(K, 'reset', None) if K is not None else None
    if reset is not None:
        try:
            reset()
        except Exception as e:      # noqa: BLE001 - report, never mask the test result
            msgs.append('K.reset() raised %s: %s' % (type(e).__name__, e))
    return msgs


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    cfg = item.config
    _inject_hooks()
    strict = cfg.getoption('--strict-depth') or item.get_closest_marker('strict_depth')
    off = cfg.getoption('--no-depth-check') or item.get_closest_marker('no_depth')
    m = item.get_closest_marker('device_base')
    spy = _GoSpy().install()
    _CURRENT[0] = item
    _ResetScan.found = []
    _ResetScan.on = item.get_closest_marker('no_invariants') is None
    sk = item.get_closest_marker('invariants_skip')
    _ResetScan.skip = tuple(sk.args) if sk is not None else ()
    dc = None
    try:
        if off:
            res = yield
        else:
            dc = make_checker(base=m.args[0] if m else None, strict=bool(strict))
            evodepth.CURRENT[0] = dc
            try:
                with dc:
                    res = yield
            finally:
                evodepth.CURRENT[0] = None
    except BaseException:
        spy.remove()
        _cleanup()
        raise
    spy.remove()
    try:
        msgs = _post_checks(item, dc, spy)
    finally:
        msgs_c = _cleanup()
    msgs = msgs + msgs_c
    if msgs:
        pytest.fail('\n'.join(msgs), pytrace=False)
    return res


# -- fixtures --------------------------------------------------------------------------------

class DepthProbe(object):
    """The ``evodepth`` fixture: the depth checker of the running test."""

    @property
    def checker(self):
        return evodepth.CURRENT[0]

    @property
    def max_depth(self):
        dc = evodepth.CURRENT[0]
        return dc.max_depth if dc is not None else None

    def measure(self, fn, *args, **kw):
        """(result, max device depth, deepest stack) of one call, measured as in the suite."""
        dc = evodepth.CURRENT[0]
        if dc is not None:
            return dc.measure(fn, *args, **kw)
        with make_checker() as tmp:
            return tmp.measure(fn, *args, **kw)


@pytest.fixture(name='evodepth')
def _evodepth_fixture():
    """The depth checker of the running test: .measure(fn, *a), .max_depth, .checker."""
    return DepthProbe()


@pytest.fixture
def update_golden(request):
    """True when the run should rewrite golden files (--update-golden)."""
    return request.config.getoption('--update-golden')
