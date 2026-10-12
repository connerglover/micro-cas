"""FRAMELINT: static frame-level checks for device code (DESIGN.md sections 10.2, 17.3, 4.2).

    python tests/support/framelint.py [--report] [--levels OUT.json] [paths...]   # default src/

Annotations (comments):

    #@L n          on a module's first line: the default level of its functions;
                   trailing a ``def`` line: that function's level (1..7).
    #@calls k      on a call line: a dynamic call whose callees are declared at level k
                   (``getattr(M, name)(...)``, ``FNUM[op](a)``, ``R.BUSY(...)``, a callable
                   parameter). k must exceed the caller's level, except a virtual generator
                   call (``yield scoped(getattr(M, name)(...))  #@calls 2`` inside a ``g_*``).
    #@table k      on a module-level assignment that holds src functions: each must have a
                   level >= k. A ``#@calls k`` through such a table needs k <= the table's k.
    #@native       on a module-level hook assignment (``ESC = None  #@native``): the hook holds
                   a native function, so calling it costs no Python frame and needs no
                   ``#@calls``. (An extension of section 17.3; see docs/notes/M0.1.md.)
    #@lazy mod     on a module-level ``X = None`` (X the fixed alias of mod): X is bound to the
                   module mod at run time (``ui.engine`` imports the engine on first use), so
                   ``X.f(...)`` is resolved like an import of mod. ``U.X`` for a module U
                   that declares it lazily resolves to mod too (``R = U.R`` in a function).

Checks:

- every resolvable call edge has L(callee) > L(caller): same-module names, ``ALIAS.f`` through
  the module's own ``import x as Y``, ``R.MODS['key'].f``, ``R.need('key').f`` and locals bound
  to those (``M = R.need('poly')``; ``MT = R.MODS['rulesb']``); this also proves there is no
  recursion;
- generators (``g_*``) are exactly L2 and contain ``yield``; a ``g_*`` call appears only as the
  operand of ``yield`` or inside ``scoped(...)`` under ``yield``, or in ``run.go`` (the root
  generator); no function references a ``g_*`` without calling it;
- inside a generator: no ``yield from``, no ``return value``, no bare ``except:``, no
  ``finally`` (section 10.2);
- imports (and ``__import__``) inside functions only in ``run.need``, ``run.go``,
  ``ui.engine``;
- module bodies contain only imports, defs, empty exception classes, docstrings and
  assignments whose calls are builtins (or create a same-module generator object); the entry
  module ``casevo`` is exempt (its body is the depth-0 event loop);
- no nested functions or classes inside functions;
- every function has a level (its own or the module default) in 1..7.
"""
import ast
import builtins
import json
import os
import re
import sys

import lint as _lint

LEVEL_RE = re.compile(r'#@L\s*(\d+)')
CALLS_RE = re.compile(r'#@calls\s*(\d+)')
TABLE_RE = re.compile(r'#@table\s*(\d+)')
NATIVE_MARK = '#@native'
LAZY_RE = re.compile(r'#@lazy\s+(\w+)')

MINLEVEL = 1
MAXLEVEL = 7
GEN_LEVEL = 2
IMPORT_OK = (('run', 'need'), ('run', 'go'), ('ui', 'engine'))
ROOT_GEN_OK = (('run', 'go'),)
ENTRY = ('casevo', 'CASEVO')

# Runtime keys (need, MODS, DEPS, STRATS) -> src module, where they differ (DESIGN 4.3, 15.1).
# A literal DEV = {...} table in run.py, when present, overrides these.
KEYS = {
    'fact': 'factor', 'factb': 'factorb', 'factc': 'factorc', 'factd': 'factord',
    'ser': 'series', 'serb': 'seriesb',
    'lim': 'limit', 'limb': 'limitb', 'limc': 'limitc', 'int': 'integ',
    'int2': 'integ2', 'int2b': 'integ2b', 'int3': 'integ3', 'int3b': 'integ3b',
    'def': 'defint', 'defb': 'defintb', 'defc': 'defintc', 'sum': 'sums', 'sumb': 'sumsb', 'sumc': 'sumsc',
    'form': 'forms', 'cat': 'catalog', 'catb': 'catalogb',
}

DYN = 'dynamic module'      # a local bound to a module chosen at run time


class Func(object):
    def __init__(self, mod, node, level, explicit):
        self.mod = mod
        self.node = node
        self.name = node.name
        self.lineno = node.lineno
        self.level = level
        self.explicit = explicit
        self.is_gen = _has_own_yield(node)

    def label(self, here=None):
        if here is not None and here is self.mod:
            return self.name
        return '%s.%s' % (self.mod.name, self.name)


class Glob(object):
    def __init__(self, name, node, native, table):
        self.name = name
        self.node = node
        self.native = native
        self.table = table


class Mod(object):
    def __init__(self, name, path, src):
        self.name = name
        self.path = path
        self.src = src
        self.lines = src.splitlines()
        self.errors = []
        self.default = None
        self.funcs = {}
        self.classes = set()
        self.globs = {}
        self.imports = {}       # alias -> src module name
        self.lazy = {}          # alias -> src module name, bound at run time (#@lazy)
        self.native_mods = set()
        self.tree = None
        m = LEVEL_RE.search(self.lines[0]) if self.lines else None
        if m:
            self.default = int(m.group(1))
        try:
            self.tree = ast.parse(src, path)
        except SyntaxError as e:
            self.errors.append('%s:%s: syntax error: %s' % (path, e.lineno, e.msg))
            return
        self._collect(self.tree.body)

    def err(self, line, msg):
        self.errors.append('%s:%d: %s' % (self.path, line or 0, msg))

    def marker(self, node, regex_or_text, first_only=False):
        a = getattr(node, 'lineno', 0) or 0
        b = a if first_only else (getattr(node, 'end_lineno', a) or a)
        for i in range(a, b + 1):
            if 0 < i <= len(self.lines):
                s = self.lines[i - 1]
                if isinstance(regex_or_text, str):
                    if regex_or_text in s:
                        return True
                else:
                    m = regex_or_text.search(s)
                    if m:
                        return int(m.group(1))
        return None

    def _collect(self, body):
        for st in body:
            if isinstance(st, ast.Import):
                for a in st.names:
                    nm = a.asname or a.name.split('.')[0]
                    self.imports[nm] = a.name
            elif isinstance(st, ast.ImportFrom):
                for a in st.names:
                    self.native_mods.add(a.asname or a.name)
            elif isinstance(st, ast.FunctionDef):
                lv, explicit = self._def_level(st)
                self.funcs[st.name] = Func(self, st, lv, explicit)
            elif isinstance(st, ast.ClassDef):
                self.classes.add(st.name)
            elif isinstance(st, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = st.targets if isinstance(st, ast.Assign) else [st.target]
                native = self.marker(st, NATIVE_MARK) is not None
                table = self.marker(st, TABLE_RE)
                for t in targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name):
                            self.globs[n.id] = Glob(n.id, st, native, table)
                self._collect_lazy(st, targets)
            elif isinstance(st, (ast.If, ast.Try, ast.While, ast.For)):
                for field in ('body', 'orelse', 'finalbody'):
                    self._collect(getattr(st, field, []) or [])
                for h in getattr(st, 'handlers', []) or []:
                    self._collect(h.body)

    def _collect_lazy(self, st, targets):
        line = self.lines[st.lineno - 1] if 0 < st.lineno <= len(self.lines) else ''
        m = LAZY_RE.search(line)
        if m is None:
            return
        mod = m.group(1)
        want = _lint.alias_for(mod)
        if len(targets) != 1 or not isinstance(targets[0], ast.Name) or \
                not isinstance(st.value, ast.Constant) or st.value.value is not None:
            self.err(st.lineno, '#@lazy %s: write "%s = None  #@lazy %s"'
                     % (mod, want or 'X', mod))
        elif want is None:
            self.err(st.lineno, '#@lazy %s: not a module of the map (DESIGN 4.1)' % mod)
        elif targets[0].id != want:
            self.err(st.lineno, '#@lazy %s binds %s: the fixed alias is %s (DESIGN 4.1)'
                     % (mod, targets[0].id, want))
        else:
            self.lazy[want] = mod
            self.imports[want] = mod

    def _def_level(self, node):
        last = node.lineno
        if node.body and node.body[0].lineno > node.lineno:
            last = node.body[0].lineno - 1
        for i in range(node.lineno, last + 1):
            if 0 < i <= len(self.lines):
                m = LEVEL_RE.search(self.lines[i - 1])
                if m:
                    return int(m.group(1)), True
        return self.default, False


def _has_own_yield(fn):
    st = list(fn.body)
    while st:
        n = st.pop()
        if isinstance(n, (ast.Yield, ast.YieldFrom)):
            return True
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                              ast.ClassDef)):
            st.extend(ast.iter_child_nodes(n))
    return False


def _own_nodes(fn):
    """Every node inside a function body, not descending into nested defs and classes."""
    out = []
    st = list(fn.body)
    while st:
        n = st.pop()
        out.append(n)
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                              ast.ClassDef)):
            st.extend(ast.iter_child_nodes(n))
    return out


class Analysis(object):
    """Cross-module analysis of a set of device modules."""

    def __init__(self, mods):
        self.mods = mods                       # name -> Mod
        self.errors = []
        self.edges = []                        # (caller Func, callee Func, line)
        self.entries = []                      # the entry bodies, as level-0 pseudo functions
        self.keys = dict(KEYS)
        run = mods.get('run')
        if run is not None and 'DEV' in run.globs:
            try:
                dev = ast.literal_eval(run.globs['DEV'].node.value)
                if isinstance(dev, dict):
                    for k in sorted(dev):
                        self.keys[k] = dev[k]
            except (ValueError, AttributeError, SyntaxError):
                pass
        self._check_imports()
        for name in sorted(mods):
            m = mods[name]
            if m.tree is None:
                continue
            if name in ENTRY:
                self._check_entry(m)
            else:
                self._check_body(m)
            for fname in sorted(m.funcs):
                self._check_func(m, m.funcs[fname])
        for name in sorted(mods):
            self.errors.extend(mods[name].errors)
        self.errors.sort(key=_lint._errkey)

    # -- the module-level import graph (DESIGN 4.2) ----------------------------------------

    def _check_imports(self):
        graph = {}
        for name in sorted(self.mods):
            m = self.mods[name]
            if m.tree is None:
                continue
            outs = []
            for st in m.tree.body:
                if not isinstance(st, ast.Import):
                    continue
                for a in st.names:
                    tgt = a.name
                    fam = _lint.family(tgt)
                    if name not in ENTRY and fam in _lint.ALIASES and (
                            fam not in _lint.RESIDENT):
                        m.err(st.lineno, 'module-level import of lazy module %s: use '
                                         "R.need('%s') in a generator or R.MODS in a plain "
                                         'function (DESIGN 4.2)' % (tgt, tgt))
                    if tgt in self.mods:
                        outs.append((tgt, st.lineno))
            graph[name] = outs
        state = {}
        for start in sorted(graph):
            if state.get(start):
                continue
            stack = [(start, 0)]
            path = [start]
            state[start] = 1                     # 1: on the path, 2: done
            while stack:
                node, i = stack[-1]
                outs = graph.get(node, [])
                if i < len(outs):
                    stack[-1] = (node, i + 1)
                    nxt, line = outs[i]
                    st = state.get(nxt, 0)
                    if st == 1:
                        cyc = path[path.index(nxt):] + [nxt]
                        self.mods[node].err(line, 'import cycle: %s (DESIGN 4.2: the import '
                                                  'graph must be acyclic)' % ' -> '.join(cyc))
                    elif st == 0:
                        state[nxt] = 1
                        path.append(nxt)
                        stack.append((nxt, 0))
                else:
                    state[node] = 2
                    stack.pop()
                    path.pop()

    # -- resolution -----------------------------------------------------------------------

    def key_mod(self, key):
        return self.keys.get(key, key)

    def _run_alias(self, m, node, local, binds=None):
        """True if node is the run module: an alias of 'run' (or bare, inside run.py), or a
        local bound to it (``R = U.R``)."""
        if not isinstance(node, ast.Name):
            return False
        if binds and node.id in binds:
            return binds[node.id] == 'run'
        return node.id not in local and m.imports.get(node.id) == 'run'

    def mod_expr(self, m, expr, local, binds):
        """The src module an expression denotes, DYN, or None if it is not a module."""
        if isinstance(expr, ast.Name):
            if expr.id in binds:
                return binds[expr.id]
            if expr.id in local:
                return None
            tgt = m.imports.get(expr.id)
            if tgt is not None and (tgt in self.mods or _lint.alias_for(tgt) is not None):
                return tgt
            return None
        if isinstance(expr, ast.Attribute):
            owner = self.mod_expr(m, expr.value, local, binds)
            if owner not in (None, DYN) and owner in self.mods:
                return self.mods[owner].lazy.get(expr.attr)
            return None
        if isinstance(expr, ast.Subscript):
            v = expr.value
            is_mods = (isinstance(v, ast.Attribute) and v.attr == 'MODS' and
                       self._run_alias(m, v.value, local, binds)) or \
                      (m.name == 'run' and isinstance(v, ast.Name) and v.id == 'MODS' and
                       'MODS' not in local)
            if is_mods:
                s = expr.slice
                if isinstance(s, ast.Constant) and isinstance(s.value, str):
                    return self.key_mod(s.value)
                return DYN
            return None
        if isinstance(expr, ast.Call):
            f = expr.func
            is_need = (isinstance(f, ast.Attribute) and f.attr == 'need' and
                       self._run_alias(m, f.value, local, binds)) or \
                      (m.name == 'run' and isinstance(f, ast.Name) and f.id == 'need' and
                       'need' not in local)
            if is_need:
                if expr.args and isinstance(expr.args[0], ast.Constant) and \
                        isinstance(expr.args[0].value, str):
                    return self.key_mod(expr.args[0].value)
                return DYN
        return None

    def _global_kind(self, T, attr):
        """('edge', Func) | ('native', None) | ('dynamic', table) | None for T.attr."""
        if attr in T.funcs:
            return ('edge', T.funcs[attr])
        if attr in T.classes:
            return ('native', None)
        g = T.globs.get(attr)
        if g is not None:
            if g.native:
                return ('native', None)
            return ('dynamic', g.table)
        return None

    def classify(self, m, call, local, binds):
        f = call.func
        if isinstance(f, ast.Name):
            n = f.id
            if n in local:
                return ('dynamic', None)
            k = self._global_kind(m, n)
            if k is not None:
                return k
            if n in m.imports or n in m.native_mods:
                return ('native', None)
            if hasattr(builtins, n):
                return ('native', None)
            return ('error', 'unresolved name %r' % n)
        if isinstance(f, ast.Attribute):
            tgt = self.mod_expr(m, f.value, local, binds)
            if tgt == DYN:
                return ('dynamic', None)
            if tgt is not None:
                T = self.mods.get(tgt)
                if T is None:
                    return ('skip', None)
                k = self._global_kind(T, f.attr)
                if k is not None:
                    return k
                return ('error', '%s has no %r' % (tgt, f.attr))
            return ('native', None)            # a method of a list, dict, str or native module
        table = None
        if isinstance(f, ast.Subscript):
            v = f.value
            if isinstance(v, ast.Name) and v.id not in local and v.id in m.globs:
                table = m.globs[v.id].table
            elif isinstance(v, ast.Attribute):
                tgt = self.mod_expr(m, v.value, local, binds)
                if tgt not in (None, DYN) and tgt in self.mods:
                    g = self.mods[tgt].globs.get(v.attr)
                    if g is not None:
                        table = g.table
        return ('dynamic', table)

    # -- per function ---------------------------------------------------------------------

    def _locals(self, fn):
        names = set()
        glob = set()
        a = fn.args
        for p in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
            if p is not None:
                names.add(p.arg)
        for n in _own_nodes(fn):
            if isinstance(n, ast.Global):
                glob.update(n.names)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                names.add(n.id)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                names.add(n.name)
            elif isinstance(n, ast.Import):
                for al in n.names:
                    names.add(al.asname or al.name.split('.')[0])
        return names - glob

    def _binds(self, m, fn, local):
        binds = {}
        for n in _own_nodes(fn):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and \
                    isinstance(n.targets[0], ast.Name):
                t = self.mod_expr(m, n.value, local, {})
                if t is not None:
                    nm = n.targets[0].id
                    if nm in binds and binds[nm] != t:
                        binds[nm] = DYN
                    else:
                        binds[nm] = t
        return binds

    def _is_g(self, func_obj):
        return func_obj.name.startswith('g_')

    def _virtual(self, call, parents):
        """True if the call is the operand of yield, or the argument of scoped(...)."""
        p = parents.get(call)
        if isinstance(p, ast.Yield) and p.value is call:
            return True
        if isinstance(p, ast.Call) and call in p.args:
            pf = p.func
            nm = pf.id if isinstance(pf, ast.Name) else (
                pf.attr if isinstance(pf, ast.Attribute) else None)
            if nm == 'scoped':
                return True
        return False

    def _check_func(self, m, F):
        fn = F.node
        here = (m.name, F.name)
        lv = F.level
        if lv is None:
            m_err = 'no #@L annotation on %s() and no module default on line 1' % F.name
            self.errors.append('%s:%d: %s' % (m.path, F.lineno, m_err))
            return
        if lv < MINLEVEL or lv > MAXLEVEL:
            self.errors.append('%s:%d: %s() is at level %d: functions run at levels %d..%d'
                               % (m.path, F.lineno, F.name, lv, MINLEVEL, MAXLEVEL))
        if F.name.startswith('g_'):
            if lv != GEN_LEVEL:
                self.errors.append('%s:%d: generator %s() must be exactly L%d, not L%d'
                                   % (m.path, F.lineno, F.name, GEN_LEVEL, lv))
            if not F.is_gen:
                self.errors.append('%s:%d: %s() is named g_* but has no yield'
                                   % (m.path, F.lineno, F.name))
        nodes = _own_nodes(fn)
        parents = {}
        for p in [fn] + nodes:
            for c in ast.iter_child_nodes(p):
                parents[c] = p
        local = self._locals(fn)
        binds = self._binds(m, fn, local)
        for n in nodes:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.errors.append('%s:%d: nested %s inside %s() (closures cost frames; '
                                   'use module-level functions)'
                                   % (m.path, n.lineno,
                                      'class' if isinstance(n, ast.ClassDef) else 'def',
                                      F.name))
            if isinstance(n, (ast.Import, ast.ImportFrom)) and here not in IMPORT_OK:
                self.errors.append('%s:%d: import inside %s(): only run.need, run.go and '
                                   'ui.engine import' % (m.path, n.lineno, F.name))
            if F.is_gen:
                if isinstance(n, ast.YieldFrom):
                    self.errors.append('%s:%d: yield from in generator %s() (nests frames)'
                                       % (m.path, n.lineno, F.name))
                elif isinstance(n, ast.Return) and n.value is not None:
                    self.errors.append('%s:%d: return value in generator %s(): the driver '
                                       'reads it as a failure; use "yield value" then '
                                       '"return"' % (m.path, n.lineno, F.name))
                elif isinstance(n, ast.ExceptHandler) and n.type is None:
                    self.errors.append('%s:%d: bare except: in generator %s() (catches '
                                       'GeneratorExit on the desktop only)'
                                       % (m.path, n.lineno, F.name))
                elif isinstance(n, ast.Try) and n.finalbody:
                    self.errors.append('%s:%d: finally in generator %s() (runs on '
                                       'GeneratorExit on the desktop only)'
                                       % (m.path, n.lineno, F.name))
            if isinstance(n, ast.Call):
                self._check_call(m, F, n, local, binds, parents, here)
            elif isinstance(n, (ast.Name, ast.Attribute)) and \
                    isinstance(getattr(n, 'ctx', None), ast.Load):
                self._check_ref(m, F, n, local, binds, parents, here)

    def _check_ref(self, m, F, n, local, binds, parents, here):
        p = parents.get(n)
        if isinstance(p, ast.Call) and p.func is n:
            return
        tgt = None
        if isinstance(n, ast.Name):
            if n.id not in local and n.id in m.funcs:
                tgt = m.funcs[n.id]
        else:
            t = self.mod_expr(m, n.value, local, binds)
            if t not in (None, DYN) and t in self.mods:
                tgt = self.mods[t].funcs.get(n.attr)
        if tgt is not None and self._is_g(tgt) and here not in ROOT_GEN_OK:
            self.errors.append('%s:%d: %s() references %s without calling it (name '
                               'generators in tables by string)'
                               % (m.path, n.lineno, F.name, tgt.label(m)))

    def _check_call(self, m, F, call, local, binds, parents, here):
        if isinstance(call.func, ast.Name) and call.func.id == '__import__' and \
                '__import__' not in local and here not in IMPORT_OK:
            self.errors.append('%s:%d: __import__ inside %s(): only run.need, run.go and '
                               'ui.engine import' % (m.path, call.lineno, F.name))
        kind, x = self.classify(m, call, local, binds)
        virtual = F.is_gen and self._virtual(call, parents)
        lv = F.level
        if kind == 'error':
            self.errors.append('%s:%d: %s() calls %s' % (m.path, call.lineno, F.name, x))
        elif kind == 'edge':
            callee = x
            if self._is_g(callee):
                if virtual or here in ROOT_GEN_OK:
                    return
                self.errors.append('%s:%d: %s() calls generator %s without yield (only '
                                   '"yield %s(...)", "yield scoped(%s(...))" or run.go)'
                                   % (m.path, call.lineno, F.name, callee.label(m),
                                      callee.name, callee.name))
                return
            if callee.level is None:
                return                                   # reported at its definition
            if callee.level <= lv:
                self.errors.append('%s:%d: %s (L%d) -> %s (L%d): callee must be > %d'
                                   % (m.path, call.lineno, F.name, lv, callee.label(m),
                                      callee.level, lv))
            else:
                self.edges.append((F, callee, call.lineno))
        elif kind == 'dynamic':
            k = m.marker(call, CALLS_RE)
            if k is None:
                self.errors.append('%s:%d: dynamic call in %s() needs "#@calls k" (k: the '
                                   'level of the callees)' % (m.path, call.lineno, F.name))
                return
            if virtual and k == GEN_LEVEL:
                return                                   # a virtual generator call
            if k <= lv:
                self.errors.append('%s:%d: %s (L%d) -> #@calls %d: callee must be > %d'
                                   % (m.path, call.lineno, F.name, lv, k, lv))
            if x is not None and k > x:
                self.errors.append('%s:%d: #@calls %d through a #@table %d: the table only '
                                   'guarantees level >= %d' % (m.path, call.lineno, k, x, x))

    # -- module bodies --------------------------------------------------------------------

    def _check_body(self, m):
        for st in m.tree.body:
            if isinstance(st, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef,
                               ast.Pass)):
                continue
            if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
                continue
            if isinstance(st, (ast.Assign, ast.AugAssign)):
                self._check_body_value(m, st)
                continue
            m.err(st.lineno, 'module body: only imports, defs, exception classes and '
                             'assignments (DESIGN 4.2); found %s' % type(st).__name__)

    def _check_body_value(self, m, st):
        table = m.marker(st, TABLE_RE)
        refs = []
        parents = {}
        for p in ast.walk(st.value):
            for c in ast.iter_child_nodes(p):
                parents[c] = p
        for n in ast.walk(st.value):
            if isinstance(n, ast.Call):
                f = n.func
                ok = False
                if isinstance(f, ast.Name):
                    if f.id in m.funcs:
                        ok = m.funcs[f.id].is_gen      # creates a generator object only
                    elif f.id not in m.globs and f.id not in m.classes and \
                            hasattr(builtins, f.id):
                        ok = True
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    tgt = m.imports.get(f.value.id)
                    ok = tgt is not None and tgt not in self.mods and \
                        _lint.alias_for(tgt) is None
                if not ok:
                    m.err(n.lineno, 'module body calls %s: only builtins (DESIGN 4.2)'
                          % ast.unparse(f))
            elif isinstance(n, (ast.Name, ast.Attribute)) and \
                    isinstance(n.ctx, ast.Load):
                p = parents.get(n)
                if isinstance(p, ast.Call) and p.func is n:
                    continue
                F = None
                if isinstance(n, ast.Name) and n.id in m.funcs:
                    F = m.funcs[n.id]
                elif isinstance(n, ast.Attribute):
                    t = self.mod_expr(m, n.value, set(), {})
                    if t not in (None, DYN) and t in self.mods:
                        F = self.mods[t].funcs.get(n.attr)
                if F is not None:
                    refs.append((n, F))
        for n, F in refs:
            if self._is_g(F):
                m.err(n.lineno, 'module body references generator %s: name generators '
                                'by string' % F.label(m))
            elif table is None:
                m.err(n.lineno, 'a table of functions needs "#@table k" (it holds %s)'
                      % F.label(m))
            elif F.level is not None and F.level < table:
                m.err(n.lineno, '#@table %d holds %s at L%d (< %d)'
                      % (table, F.label(m), F.level, table))

    def _check_entry(self, m):
        """The entry body is depth 0: check its calls like an L0 function's."""
        fake = ast.FunctionDef(name='<module>', args=ast.arguments(
            posonlyargs=[], args=[], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
            defaults=[]), body=[s for s in m.tree.body
                                if not isinstance(s, (ast.FunctionDef, ast.ClassDef))],
            decorator_list=[], returns=None, type_params=[])
        fake.lineno = 1
        F = Func(m, fake, 0, True)
        self.entries.append(F)
        nodes = _own_nodes(fake)
        parents = {}
        for p in [fake] + nodes:
            for c in ast.iter_child_nodes(p):
                parents[c] = p
        for n in nodes:
            if isinstance(n, ast.Call):
                self._check_call(m, F, n, set(), {}, parents, (m.name, '<module>'))
            elif isinstance(n, (ast.Name, ast.Attribute)) and \
                    isinstance(getattr(n, 'ctx', None), ast.Load):
                self._check_ref(m, F, n, set(), {}, parents, (m.name, '<module>'))

    # -- outputs --------------------------------------------------------------------------

    def levels(self):
        """{module: {function: level}} for every annotated function."""
        out = {}
        for name in sorted(self.mods):
            m = self.mods[name]
            d = {}
            for fname in sorted(m.funcs):
                if m.funcs[fname].level is not None:
                    d[fname] = m.funcs[fname].level
            out[name] = d
        return out

    def chains(self):
        """[(chain of Funcs)] longest declared chain from each entry point, longest first.

        Entry points are the functions nothing calls through a frame edge (generators are
        entered by the trampoline at depth 2). Edges are the resolved, valid frame edges.
        """
        out_edges = {}
        has_in = set()
        for a, b, _ in self.edges:
            out_edges.setdefault(id(a), []).append(b)
            has_in.add(id(b))
        best = {}
        allf = list(self.entries)
        for name in sorted(self.mods):
            m = self.mods[name]
            for fname in sorted(m.funcs):
                allf.append(m.funcs[fname])
        allf.sort(key=lambda f: -(f.level or 0))     # deepest first: callees before callers
        for f in allf:
            chain = (f,)
            for g in out_edges.get(id(f), ()):
                c = best.get(id(g), (g,))
                if len(c) + 1 > len(chain) or (len(c) + 1 == len(chain) and
                                                (c[-1].level or 0) > (chain[-1].level or 0)):
                    chain = (f,) + c
            best[id(f)] = chain
        res = []
        for f in allf:
            if id(f) not in has_in:
                res.append(best[id(f)])
        res.sort(key=lambda c: (-(c[-1].level or 0), -len(c), c[0].label()))
        return res

    def report(self):
        lines = []
        for c in self.chains():
            if len(c) < 2:
                continue
            lines.append('%d: %s' % (c[-1].level or 0, ' > '.join(
                '%s %s' % (f.level, f.label()) for f in c)))
        return lines


# -- entry points ---------------------------------------------------------------------------

def load_dir(d):
    mods = {}
    for p in _lint.device_files(d):
        name = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding='utf-8', errors='replace', newline='') as fh:
            mods[name] = Mod(name, p, fh.read().replace('\r\n', '\n'))
    return mods


def analyze_dir(d=_lint.SRC):
    return Analysis(load_dir(d))


def analyze_sources(sources):
    """sources: {module name: source text}. File names are '<name>.py'."""
    mods = {}
    for name in sorted(sources):
        mods[name] = Mod(name, name + '.py', sources[name])
    return Analysis(mods)


def lint_sources(sources):
    return analyze_sources(sources).errors


def level_table(d=_lint.SRC):
    """{(normcased absolute file path, function name): level} for the depth checker."""
    out = {}
    for p in _lint.device_files(d):
        name = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding='utf-8', errors='replace', newline='') as fh:
            m = Mod(name, p, fh.read().replace('\r\n', '\n'))
        key = os.path.normcase(os.path.abspath(p))
        for fname in m.funcs:
            if m.funcs[fname].level is not None:
                out[(key, fname)] = m.funcs[fname].level
    return out


def main(argv):
    report = '--report' in argv
    out = None
    paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--levels':
            out = argv[i + 1]
            i += 2
            continue
        if a != '--report':
            paths.append(a)
        i += 1
    d = paths[0] if paths else _lint.SRC
    an = analyze_dir(d)
    for e in an.errors:
        print(e)
    if report:
        for ln in an.report():
            print(ln)
    if out:
        with open(out, 'w', encoding='ascii', newline='\n') as fh:
            json.dump(an.levels(), fh, indent=1, sort_keys=True)
            fh.write('\n')
    return 1 if an.errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
