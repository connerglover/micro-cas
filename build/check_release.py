"""Run the packed calculator release with strict EVO depth checks (desktop CPython).

    python build/check_release.py [--dist dist]

The packs import as real modules through a recording __import__ that follows MicroPython's
rules: a module is registered before its body runs, and a body that fails stays registered
(run.unload removes it). sys and gc are stand-ins, so eviction, soft packs and admission run
their calculator code paths. The fake heap reading charges every loaded pack its release
estimate against a chosen total; it exercises the loader, not physical RAM (native
MicroPython runs check that: build/micro_smoke.py).
"""
import argparse
import builtins
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import types
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / 'tests/support', ROOT / 'shim'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import evodepth
import invariants
import keyscript
import ti_draw as TD
import ti_system as TS

PLENTY = 1 << 20


class _ReleaseDepth(evodepth.DepthChecker):
    """A pack import is a native call on the calculator: its body is the only new frame."""

    def __init__(self, release):
        super().__init__((str(release.dist),), base=0, budget=8, hard_limit=10,
                         native_penalty=1, dunder_penalty=1, gen_penalty=1,
                         levels=release.levels, check_levels=False,
                         entry_files=(str(release.path),))
        self.release = release

    def _enter(self, code, frame, quiet):
        caller = frame.f_back
        bridge = caller is not None and caller.f_code is Release._load.__code__
        if bridge:
            self._native[caller] = builtins.__import__
        try:
            super()._enter(code, frame, quiet)
        finally:
            if bridge:
                self._native.pop(caller, None)
        self.release.seen.add((code.co_filename, code.co_name))
        if self.release.observer is not None and not quiet:
            self.release.observer(frame)


class Release:
    def __init__(self, dist=ROOT / 'dist', total=None):
        self.dist = Path(dist).resolve()
        self.path = self.dist / 'CAS.py'
        self.source = self.path.read_text('ascii')
        self.meta = json.loads((self.dist / 'release.json').read_text('ascii'))
        self.total = total               # None: the heap never runs short
        self.packs = set(self.meta['kinds'])
        self.modules = {}                # the calculator's sys.modules
        self.sys = SimpleNamespace(modules=self.modules)
        # Native stand-ins: no Python callback frame enters the depth model.
        self.gc = SimpleNamespace(mem_free=self.memory, collect={}.clear)
        self.builtins = dict(vars(builtins), __import__=self._import)
        self.globals = {'__name__': 'CAS', '__builtins__': self.builtins}
        self.imports, self.loads, self.seen = [], [], set()
        self.observer = None
        self.fail = None                 # pack name -> exception to raise inside its body
        self.max_depth, self.max_stack = 0, ()
        self.screen, self.snaps, self.ended = '', {}, None
        self.levels = {}
        for pack, rows in self.meta['levels'].items():
            path = evodepth.norm_path(self.dist / (pack + '.py'))
            for fn, level in rows.items():
                self.levels[(path, fn)] = level

    # -- the calculator side ------------------------------------------------------------------
    def cost(self, pack):
        factor = 1.6 if self.meta['kinds'].get(pack) in ('core', 'ui') else 1.3
        return int(self.meta['mpy_estimate'].get(pack, 0) * factor)

    def memory(self):
        if self.total is None:
            return PLENTY
        return self.total - sum(self.cost(name) for name in self.modules)

    def _import(self, name, *args, **kwargs):
        self.imports.append(name)
        if name == 'sys':
            return self.sys
        if name == 'gc':
            return self.gc
        if name in self.packs:
            if name not in self.modules:
                self._load(name)
            return self.modules[name]
        if name[:2] == 'CV' or name[:3] == 'CAS' or name in self.meta['modules']:
            raise AssertionError('unpackaged project import: ' + name)
        return builtins.__import__(name, *args, **kwargs)

    def _load(self, name):
        self.loads.append(name)
        module = types.ModuleType(name)
        module.__dict__['__builtins__'] = self.builtins
        self.modules[name] = module      # MicroPython registers the module first
        path = self.dist / (name + '.py')
        code = compile(path.read_text('ascii'), str(path), 'exec')
        if self.fail is not None and name in self.fail:
            raise self.fail.pop(name)
        exec(code, module.__dict__)

    # -- source names -------------------------------------------------------------------------
    def name(self, old):
        return self.meta['names'].get(old, old)

    def device(self, src):
        return self.meta['modules'].get(src, src)

    def where(self, src, old):
        device = self.device(src)
        return self.meta['place'].get('%s.%s' % (device, old), self.meta['owner'][device])

    def final(self, src, old):
        renamed = self.meta['renames'].get('%s.%s' % (self.device(src), old), old)
        return self.name(renamed)

    def module(self, src, old=None):
        pack = self.meta['owner'][self.device(src)] if old is None else self.where(src, old)
        return self._import(pack)

    def get(self, src, old):
        return getattr(self.module(src, old), self.final(src, old))

    def set(self, src, old, value):
        setattr(self.module(src, old), self.final(src, old), value)

    # -- running ------------------------------------------------------------------------------
    @contextmanager
    def traced(self):
        checker = _ReleaseDepth(self)
        try:
            with checker:
                yield checker
        finally:
            if checker.max_depth >= self.max_depth:
                self.max_depth, self.max_stack = checker.max_depth, checker.max_stack
            failures = evodepth.failures(checker)
            if failures:
                raise AssertionError('\n'.join(failures))

    def boot(self):
        """The engine as CVTEST wires it (no UI)."""
        with self.traced():
            self.set('parse', 'SESS', self.module('run'))
            self.set('node', 'MEMFREE', self.memory)
            self.set('run', 'MEMFREE', self.memory)
            self.set('node', 'ESC', lambda: False)
            self.set('run', 'BUSY', None)
        return self

    def reset_session(self):
        with self.traced():
            self.get('run', 'evict_all')()
            self.get('node', 'reset')()
        for name, value in (('ANS', None), ('HIST', []), ('VARS', {}), ('FUNCS', {}),
                            ('SET', {'deg': 0})):
            self.set('run', name, value)

    def go(self, text):
        job = text if isinstance(text, tuple) else ('eval', text)
        with self.traced():
            result = self.get('run', 'go')(job)
        if result[0] == 'msg' and result[1].startswith('internal error'):
            raise AssertionError((job, result))
        return result

    def assert_clean(self):
        assert self.get('node', 'NN') == self.get('node', 'BASE')
        for name in ('LIVE', 'NEEDED', 'PINNED'):
            assert not self.get('run', name), name
        node = self.module('node')
        namespace = dict(vars(node))
        for old, new in self.meta['names'].items():
            if new in namespace:
                namespace[old] = namespace[new]
        problems = invariants.scan(SimpleNamespace(**namespace))
        assert not problems, problems[:5]
        norm = self.modules.get(self.meta['owner'][self.device('normb')])
        if norm is not None:
            assert getattr(norm, self.final('normb', 'SIMPBUG'), 0) in (0, None)

    def run(self, script):
        """The real CAS launcher against the desktop shims and a key script."""
        TS.reset()
        TD.reset()
        TS.load(keyscript.parse(script) if isinstance(script, str) else list(script))
        previous = TS.MARK_HOOK[0]
        TS.MARK_HOOK[0] = lambda label: self.snaps.__setitem__(label, TD.screen_text())
        try:
            with self.traced():
                try:
                    exec(compile(self.source, str(self.path), 'exec'), self.globals)
                    self.ended = 'quit'
                except TS.StopScript:
                    self.ended = 'script'
        finally:
            TS.MARK_HOOK[0] = previous
            self.screen = TD.screen_text()
        return self


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args(argv)
    app = Release(args.dist).boot()
    for command, expected in (('1/3+1/6', '1/2'), ('diff(x^3,x)', '3*x^2'),
                              ('sum(k^2,k,1,10)', '385'),
                              ('integrate(1/(2+cos(x)),x,0,2*pi)', '2*sqrt(3)*pi/3')):
        result = app.go(command)
        assert result[:2] == ('ans', expected), (command, result)
        app.assert_clean()
        print(command + ' -> ' + result[1])
    print('Packaged self-test passed; strict depth %d/8' % app.max_depth)


if __name__ == '__main__':
    main()
