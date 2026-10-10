"""Emulate the TI-84 EVO call-depth cap on desktop CPython (3.12+).

DESIGN.md sections 17.5 and 20.2; base design: docs/reference/device-python.md section 12.

Only frames whose code lives under a *device dir* (src/, or dist/device for the bundled tier)
count. pytest, test modules, shim/ and the stdlib are invisible: on the device they are native
code or do not exist.

Additions over device-python section 12.2:

1. ``gen_penalty`` (default 0): the cost of a frame resumed by ``gen.send``, ``throw`` or
   ``__next__``. On CPython 3.12+ the CALL event for ``top.send(v)`` passes the *unbound*
   ``send`` descriptor as ``func`` and the generator as ``arg0``, so both are inspected.
2. Automatic base: a device frame with no live device ancestor (a test calling into src/
   directly) starts at its *declared level* (``levels``), not at ``base + 1``. So ``K.add_``
   called from a test is measured at depth 6, its real worst case. ``auto_base=False`` (the
   ``device_base(n)`` marker) starts such frames at ``base + 1`` instead.
3. Level assertion: every device frame's depth must be <= its declared level. It is meant for
   the default mode (``gen_penalty == 0``), where the levels are exact; strict runs
   (``gen_penalty = 1``) check only the budget.

Also: PY_THROW is treated like a resume, except that a ``GeneratorExit`` thrown into a dying
generator (``close()`` or garbage collection) is never counted or checked: on the device a
dropped generator runs no code (``finally`` and bare ``except`` are banned in ``g_*``).
"""
import ast
import linecache
import os
import sys

_M = sys.monitoring
_E = _M.events

HARD_LIMIT = 10     # deepest frame that ran on the device (PROBE4); the 11th raised
BUDGET = 8          # the test budget (DESIGN section 17.1)

CURRENT = [None]    # the checker of the running test (set by tests/conftest.py)
_GENOP = object()   # marks "this frame is resuming a generator" in DepthChecker._native
_GEN_METHODS = ('send', 'throw', '__next__')


# Comprehension caches, shared by every checker of the session (source files do not change
# during a run, and code objects of loaded modules live as long as the modules).
_SPANS = {}         # filename -> comprehension source spans
_POS = {}           # code -> list of instruction positions
_HERE = {}          # (code, offset) -> comprehension nesting at that call
_MAXCOMP = {}       # code -> max comprehension nesting inside it


def norm_path(p):
    return os.path.normcase(os.path.abspath(p))


class DepthChecker(object):
    """A ``sys.monitoring`` tool that tracks the device depth of every device frame.

    levels:        {(norm_path(file), function name): declared level}, or None.
    auto_base:     root device frames start at their declared level (default: True when
                   ``levels`` is given).
    check_levels:  record a level violation when a frame runs deeper than its declared level
                   (default: True when ``levels`` is given and ``gen_penalty == 0``).
    entry_files:   files whose module body is depth 0 (the entry program ``casevo.py``).
    """

    TOOL_IDS = (4, 3)   # free sys.monitoring ids (0, 1, 2, 5 are taken by convention)

    def __init__(self, device_dirs, base=0, budget=BUDGET, hard_limit=HARD_LIMIT,
                 native_penalty=1, dunder_penalty=1, gen_penalty=0, emulate=True,
                 levels=None, auto_base=None, check_levels=None, entry_files=()):
        self.dirs = tuple(norm_path(d) + os.sep for d in device_dirs)
        self.base = base
        self.budget = budget
        self.hard_limit = hard_limit
        self.native_penalty = native_penalty
        self.dunder_penalty = dunder_penalty
        self.gen_penalty = gen_penalty
        self.emulate = emulate
        self.levels = levels
        self.auto_base = (levels is not None) if auto_base is None else auto_base
        if check_levels is None:
            check_levels = levels is not None and gen_penalty == 0
        self.check_levels = check_levels
        self.entry_files = frozenset(norm_path(p) for p in entry_files)
        self._dev = {}                    # code object -> is device code
        self._lvl = {}                    # code object -> declared level or None
        self._live = {}                   # running device frame -> its device depth
        self._native = {}                 # frame -> builtin it is calling (or _GENOP)
        self._spans = _SPANS
        self._pos = _POS
        self._here = _HERE
        self._maxcomp = _MAXCOMP
        self.max_depth = 0
        self.max_stack = ()
        self.violations = []              # (depth, stack) for every depth > budget
        self.level_violations = []        # (depth, level, stack) for depth > declared level
        self.tool = None

    # -- classification -------------------------------------------------------------------

    def _is_dev(self, code):
        r = self._dev.get(code)
        if r is None:
            r = self._dev[code] = norm_path(code.co_filename).startswith(self.dirs)
        return r

    def level_of(self, code):
        """Declared level of a device code object, or None."""
        if code in self._lvl:
            return self._lvl[code]
        lv = None
        if self.levels is not None and code.co_name != '<module>':
            lv = self.levels.get((norm_path(code.co_filename), code.co_name))
        self._lvl[code] = lv
        return lv

    # CPython 3.12+ inlines list/set/dict comprehensions (PEP 709); MicroPython runs each one
    # as a separate function, i.e. one more frame on the device.
    def _comp_spans(self, filename):
        spans = self._spans.get(filename)
        if spans is None:
            spans = []
            try:
                tree = ast.parse(''.join(linecache.getlines(filename)))
            except (SyntaxError, ValueError):
                tree = None
            for n in (ast.walk(tree) if tree else ()):
                if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp)):
                    spans.append(((n.lineno, n.col_offset),
                                  (n.end_lineno, n.end_col_offset)))
            self._spans[filename] = spans
        return spans

    def _nest_at(self, code, index, spans):
        pos = self._pos.get(code)
        if pos is None:
            pos = self._pos[code] = list(code.co_positions())
        if index >= len(pos) or pos[index][0] is None:
            return 0
        l, el, c, ec = pos[index]
        if c is None or ec is None:
            return 0
        n = 0
        for (a, b) in spans:
            if a <= (l, c) and (el, ec) <= b:
                n += 1
        return n

    def _comp_here(self, frame):          # comprehensions around the current call
        key = (frame.f_code, frame.f_lasti)
        n = self._here.get(key)
        if n is None:
            spans = self._comp_spans(frame.f_code.co_filename)
            n = self._nest_at(frame.f_code, frame.f_lasti // 2, spans) if spans else 0
            self._here[key] = n
        return n

    def _comp_max(self, code):            # deepest comprehension inside this code
        m = self._maxcomp.get(code)
        if m is None:
            spans = self._comp_spans(code.co_filename)
            m = 0
            if spans:
                for i in range(len(list(code.co_positions()))):
                    k = self._nest_at(code, i, spans)
                    if k > m:
                        m = k
            self._maxcomp[code] = m
        return m

    # -- events ---------------------------------------------------------------------------

    def _enter(self, code, frame, quiet):
        depth = None
        f = frame.f_back
        while f is not None:                         # nearest live device ancestor
            d = self._live.get(f)
            if d is not None:
                depth = d + 1
                break
            f = f.f_back
        lvl = self.level_of(code)
        if depth is None:                            # a root device frame
            if code.co_name == '<module>' and norm_path(code.co_filename) in self.entry_files:
                depth = 0
            elif self.auto_base and lvl is not None:
                depth = lvl
            else:
                depth = self.base + 1
        caller = frame.f_back
        if caller is not None and self._is_dev(caller.f_code):
            depth += self._comp_here(caller)
        mark = self._native.get(caller) if caller is not None else None
        if mark is not None:
            depth += self.gen_penalty if mark is _GENOP else self.native_penalty
        elif code.co_name[:2] == '__' and code.co_name[-2:] == '__' and \
                code.co_name != '__module__':
            depth += self.dunder_penalty
        self._live[frame] = depth
        if quiet:
            return
        reach = depth + self._comp_max(code)        # its own comprehensions run deeper
        if reach > self.max_depth:
            self.max_depth = reach
            self.max_stack = self.stack(frame)
        if reach > self.budget:
            self.violations.append((reach, self.stack(frame)))
        if self.check_levels and lvl is not None and depth > lvl:
            self.level_violations.append((depth, lvl, self.stack(frame)))
        if self.emulate and depth > self.hard_limit:
            del self._live[frame]
            raise RuntimeError('maximum recursion depth exceeded')

    def _start(self, code, offset):                  # PY_START, PY_RESUME
        if not self._is_dev(code):
            return _M.DISABLE
        self._enter(code, sys._getframe(1), False)

    def _throw(self, code, offset, exc):             # PY_THROW (cannot be disabled)
        if self._is_dev(code):
            self._enter(code, sys._getframe(1), isinstance(exc, GeneratorExit))

    def _leave(self, code, offset, value):           # PY_RETURN, PY_YIELD
        if not self._is_dev(code):
            return _M.DISABLE
        f = sys._getframe(1)
        self._live.pop(f, None)
        self._native.pop(f, None)

    def _unwind(self, code, offset, exc):            # PY_UNWIND (cannot be disabled)
        f = sys._getframe(1)
        self._live.pop(f, None)
        self._native.pop(f, None)

    def _call(self, code, offset, func, arg0):       # CALL, in device code only
        if not self._is_dev(code):
            return _M.DISABLE
        f = sys._getframe(1)
        if hasattr(func, '__code__'):                # plain Python call
            self._native.pop(f, None)
        elif getattr(func, '__name__', '') in _GEN_METHODS and (
                type(getattr(func, '__self__', None)).__name__ == 'generator'
                or type(arg0).__name__ == 'generator'):
            self._native[f] = _GENOP                 # generator resume: gen_penalty
        else:                                        # builtin function or a class
            self._native[f] = func

    def _c_done(self, code, offset, func, arg0):     # C_RETURN, C_RAISE (cannot be disabled)
        if self._native:
            self._native.pop(sys._getframe(1), None)

    # -- reporting ------------------------------------------------------------------------

    def stack(self, frame):
        out = []
        f = frame
        while f is not None:
            d = self._live.get(f)
            if f is frame or d is not None:
                out.append('%s:%s@%s' % (os.path.basename(f.f_code.co_filename),
                                         f.f_code.co_name, '?' if d is None else d))
            f = f.f_back
        out.reverse()
        return tuple(out)

    def measure(self, fn, *args, **kw):
        """Run ``fn`` and return ``(result, max_depth, max_stack)`` for that call only.

        The checker's overall maximum still includes the span afterwards.
        """
        old = (self.max_depth, self.max_stack)
        self.max_depth = 0
        self.max_stack = ()
        try:
            r = fn(*args, **kw)
            span = (self.max_depth, self.max_stack)
        finally:
            got = (self.max_depth, self.max_stack)
            if old[0] >= got[0]:
                self.max_depth, self.max_stack = old
        return r, span[0], span[1]

    _EVENTS = ((_E.PY_START, '_start'), (_E.PY_RESUME, '_start'),
               (_E.PY_THROW, '_throw'),
               (_E.PY_RETURN, '_leave'), (_E.PY_YIELD, '_leave'),
               (_E.PY_UNWIND, '_unwind'), (_E.CALL, '_call'),
               (_E.C_RETURN, '_c_done'), (_E.C_RAISE, '_c_done'))

    def __enter__(self):
        free = [i for i in self.TOOL_IDS if _M.get_tool(i) is None]
        if not free:
            raise RuntimeError('no free sys.monitoring tool id')
        self.tool = free[0]          # a second, nested checker gets the next id
        _M.use_tool_id(self.tool, 'evo-depth')
        mask = 0
        for ev, name in self._EVENTS:
            _M.register_callback(self.tool, ev, getattr(self, name))
            mask |= ev
        _M.set_events(self.tool, mask)
        return self

    def __exit__(self, *exc):
        _M.set_events(self.tool, 0)
        for ev, name in self._EVENTS:
            _M.register_callback(self.tool, ev, None)
        _M.free_tool_id(self.tool)
        _M.restart_events()          # re-enable locations DISABLEd for this tool
        self._live.clear()
        self._native.clear()
        return False


def squash(stack):
    """'a > b x3 > c' for a stack tuple with repeated frames collapsed."""
    out = []
    for s in stack:
        if out and out[-1][0] == s:
            out[-1][1] += 1
        else:
            out.append([s, 1])
    parts = []
    for s, n in out:
        parts.append(s if n == 1 else '%s x%d' % (s, n))
    return ' > '.join(parts)


def failures(dc):
    """Human-readable failure lines for a finished checker (empty when it passed)."""
    msgs = []
    if dc.violations:
        d, st = max(dc.violations)
        msgs.append('device call depth %d > budget %d (%d violation(s)); deepest: %s'
                    % (d, dc.budget, len(dc.violations), squash(st)))
    if dc.level_violations:
        seen = set()
        for d, lv, st in dc.level_violations:
            key = st[-1] if st else ''
            if key in seen:
                continue
            seen.add(key)
            msgs.append('frame %s ran at depth %d > its declared level %d: %s'
                        % (key, d, lv, squash(st)))
            if len(seen) >= 5:
                break
    return msgs
