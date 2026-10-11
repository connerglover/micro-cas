"""Run the actual paged calculator package with strict EVO depth checks.

    python build/check_release.py [--dist dist]

Only packaged carrier modules are imported. Their definitions execute in their
real shared dictionaries; only the exec filename is supplied by a desktop hook.
The fake free-heap reading exercises admission and cleanup, not physical RAM use.
"""
import argparse
import builtins
from contextlib import contextmanager
import gc
import json
import linecache
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / 'tests/support', ROOT / 'shim'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import evodepth
import invariants
import keyscript
import ti_graphics as G
import ti_system as TS


class _ReleaseDepth(evodepth.DepthChecker):
    """Retain the native exec penalty even though filename injection needs a host frame."""

    def __init__(self, release):
        super().__init__((str(release.dist),), base=0, budget=8, hard_limit=10,
                         native_penalty=1, dunder_penalty=1, gen_penalty=1,
                         levels=release.levels, check_levels=False,
                         entry_files=(str(release.path),))
        self.release = release

    def _enter(self, code, frame, quiet):
        caller = frame.f_back
        bridge = None
        if caller is not None:
            if caller.f_code is Release._exec.__code__:
                bridge = builtins.exec
            elif caller.f_code is Release._import.__code__:
                bridge = builtins.__import__
        if bridge is not None:
            self._native[caller] = bridge
        try:
            super()._enter(code, frame, quiet)
        finally:
            if bridge is not None:
                self._native.pop(caller, None)
        self.release.seen.add((code.co_filename, code.co_name))
        observer = self.release.observer
        if observer is not None and not quiet:
            controller = self.release.env.get('CVPH', {})
            observer(frame, tuple(sorted(controller.get('ACTIVE', {}))))


class Release:
    def __init__(self, dist=ROOT / 'dist', free_memory=175 * 1024):
        self.dist = Path(dist).resolve()
        self.path = self.dist / 'CASEVO.py'
        self.source = self.path.read_text('ascii')
        self.meta = json.loads((self.dist / 'release.json').read_text('ascii'))
        self.free_memory = free_memory
        self.seen, self.imports, self.executed = set(), [], []
        self.observer = None
        self.max_depth = 0
        self.max_stack = ()
        self.screen, self.snaps = '', {}
        self.ended = None
        self.builtins = dict(vars(builtins), __import__=self._import)
        self.carriers = {}
        self.sys = SimpleNamespace(modules=self.carriers)
        # Heap acceptance runs in native MicroPython. CPython's reference
        # counting/automatic GC manages these host objects; forcing a full host
        # collection on every page import would also scan the unrelated SymPy
        # test heap thousands of times. Keep this stand-in a native callable so
        # it introduces no Python callback frame in the depth model.
        self.gc = SimpleNamespace(mem_free=self.memory, collect={}.clear)
        self.globals = {'__name__': 'CASEVO', '__builtins__': self.builtins, 'exec': self._exec}
        self.levels = {}
        for module, table in self.meta['levels'].items():
            for old, level in table.items():
                self.levels[(evodepth.norm_path(self.dist / 'blocks' / (module + '.py')),
                             self.name(old))] = level
        for payload, info in self.meta['payloads'].items():
            table = self.meta['levels'].get(info['module'], {})
            renamed = {self.name(name): level for name, level in table.items()}
            for row in info['functions']:
                if row['name'] in renamed:
                    self.levels[(evodepth.norm_path(self.dist / 'blocks' / (payload + '.py')),
                                 row['name'])] = renamed[row['name']]
        for name, level in (('register', 2), ('part', 3), ('load', 2), ('unload', 2)):
            self.levels[(evodepth.norm_path(self.dist / 'blocks/CVPH.py'), name)] = level

    @property
    def env(self):
        return self.globals.get('_env', {})

    def name(self, old):
        return self.meta['names'].get(old, old)

    def is_function(self, frame, module, old):
        owner = Path(frame.f_code.co_filename).stem
        owner = self.meta['payloads'].get(owner, {}).get('module', owner)
        owner = self.meta.get('function_pages', {}).get(owner, {}).get('module', owner)
        return owner == module and frame.f_code.co_name == self.name(old)

    def module(self, name):
        return self.env[self.meta['modules'].get(name, name)]

    def get(self, module, name):
        return self.module(module)[self.name(name)]

    def set(self, module, name, value):
        self.module(module)[self.name(name)] = value

    def memory(self):
        return self.free_memory

    def _import(self, name, *args, **kwargs):
        self.imports.append(name)
        if name == 'sys':
            return self.sys
        if name == 'gc':
            return self.gc
        if name in self.meta['sources']:
            if name not in self.carriers:
                path = self.dist / (name + '.py')
                namespace = {'__name__': name, '__builtins__': self.builtins}
                builtins.exec(compile(path.read_text('ascii'), str(path), 'exec'), namespace)
                self.carriers[name] = SimpleNamespace(**namespace)
            return self.carriers[name]
        if name.startswith('CV') or name == 'CASEVO' or name in self.meta['modules']:
            raise AssertionError('unpackaged project import: ' + name)
        return builtins.__import__(name, *args, **kwargs)

    def _exec(self, source, namespace):
        origin = namespace['__name__']
        current = self.env.get('CVPH', {}).get('CURRENT')
        payload = (current[1] if current and current[0] == origin and
                   self.env.get(origin) is namespace else origin)
        path = str(self.dist / 'blocks' / (payload + '.py'))
        namespace.setdefault('__builtins__', self.builtins)
        linecache.cache[path] = (len(source), None, source.splitlines(True), path)
        self.executed.append((origin, payload))
        builtins.exec(compile(source, path, 'exec'), namespace)

    @contextmanager
    def traced(self):
        missing = object()
        prior = getattr(gc, 'mem_free', missing)
        gc.mem_free = self.memory
        checker = _ReleaseDepth(self)
        try:
            with checker:
                yield checker
        finally:
            if prior is missing:
                del gc.mem_free
            else:
                gc.mem_free = prior
            if checker.max_depth >= self.max_depth:
                self.max_depth, self.max_stack = checker.max_depth, checker.max_stack
            failures = evodepth.failures(checker)
            if failures:
                raise AssertionError('\n'.join(failures))

    def boot(self):
        prefix, separator, entry = self.source.partition('# RUN\n')
        if not separator:
            raise ValueError('release entry marker missing')
        with self.traced():
            builtins.exec(compile(prefix, str(self.path), 'exec'), self.globals)
            for name in ('CVPH', 'CVNODE', 'CVALG', 'CVPARSE', 'CVPRINT', 'CVRUN'):
                self.globals['_load'](name)
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
                            ('SET', {'deg': 0, 'theme': 0})):
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
        namespace = dict(self.module('node'))
        for old, new in self.meta['names'].items():
            if new in namespace:
                namespace[old] = namespace[new]
        problems = invariants.scan(SimpleNamespace(**namespace))
        assert not problems, problems[:5]
        assert self.env.get('CVNORMB', {}).get(self.name('SIMPBUG'), 0) == 0

    def run(self, script):
        TS.reset()
        G.reset()
        TS.load(keyscript.parse(script) if isinstance(script, str) else list(script))
        previous = TS.MARK_HOOK[0]
        TS.MARK_HOOK[0] = lambda label: self.snaps.__setitem__(label, G.screen_text())
        try:
            with self.traced():
                try:
                    builtins.exec(compile(self.source, str(self.path), 'exec'), self.globals)
                    self.ended = 'quit'
                except TS.StopScript:
                    self.ended = 'script'
        finally:
            TS.MARK_HOOK[0] = previous
            self.screen = G.screen_text()
        return self


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args(argv)
    app = Release(args.dist).boot()
    for command, expected in (('1/3+1/6', '1/2'), ('diff(x^3,x)', '3*x^2'),
                              ('sum(k^2,k,1,10)', '385')):
        result = app.go(command)
        assert result[:2] == ('ans', expected), (command, result)
        app.assert_clean()
        print(command + ' -> ' + result[1])
    print('Packaged self-test passed; strict depth %d/8' % app.max_depth)


if __name__ == '__main__':
    main()
