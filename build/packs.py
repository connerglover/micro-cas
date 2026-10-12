"""Merge bundled device modules into packs: real MicroPython modules with plain globals.

docs/notes/FASTBOOT.md explains why. An archive import costs seconds on the EVO, so the
calculator gets a few large libraries instead of hundreds of small ones. A pack is an
ordinary module: its functions read their globals directly, and no initializer, namespace
dictionary or forwarding call is involved at run time.

``merge(sources, man, clients=())`` takes the bundled device modules (``dist/device``:
minified, device import names, run tables written) and returns ``(packs, clients, meta)``.

Membership (``man.PACKS``): a pack lists whole modules (``'parse'``) and placed functions
(``'parse.ti_rewrite'``). A module's statements and unplaced functions live in its *home*
pack; a placed function lives in the named pack and reaches its module's state through the
home pack. Pack kinds:

- ``ui``: loads at boot and stays; ``core``: loads with the engine and stays;
- ``family``: exactly the parts of one loader family, loaded and evicted by ``run.need``;
- ``soft``: stays cached but may be evicted when memory runs short. Nothing ever holds a soft
  pack: every reference is ``__import__('PACK').name``, which reloads it on demand;
- ``view``: reached like a soft pack, but unloaded only while a computation runs (menus load
  families from inside key handling);
- ``aux``: computation code reached like a soft pack that can never reach the loader (run);
  unloaded last.

Back-references: a module ``T`` that cannot import ``M`` (``M`` imports it, and the import graph
is acyclic) declares ``X = None`` and ``M`` binds it at module level with
``A.X = __import__(__name__)``, A being M's alias of T (node and nodeb: giant powers). In the
packs that statement and ``X = None`` are dropped and ``X.name`` in T reads M's pack, as an
import of M would; T's pack must then be soft (view, aux), so M never holds it.

Rewriting:

- a module-level project import ``import CVX as A`` becomes ``import PACK`` for CVX's home
  pack, once per pack, bound under the pack's own name (a merged function may use ``A`` as a
  local, and the identifier shrinker's alias analysis has no scopes); it disappears when that
  is the importing statement's own pack and is never emitted for a soft pack. A lazy alias
  (``A = None``, later ``global A; import CVX as A``) keeps its name in its home pack;
- ``A.name`` (and a module's references to its own globals from a placed function) becomes a
  plain global in the same pack, ``PACK.name`` for another resident pack, and
  ``__import__('PACK').name`` for a soft pack; same-pack stores in a function get the
  ``global`` declaration they need;
- a top-level name defined by two modules of one pack is renamed in the later module, unless
  both bind the same literal or import the same native module;
- values the loader computes at run time (``R.MODS['k']``, ``R.need('k')``) evaluate to a home
  pack, so their attributes keep attribute syntax (``MODS['k']`` of the running pack itself
  becomes a plain global: it may run while the pack is still importing);
- run.py's ``DEV`` table maps every runtime key to its pack.

Anything this compiler cannot prove raises PackError instead of producing a subtly wrong pack.
``clients`` are entry programs (CASEVO, CVTEST): rewritten with the same mapping, not packed.
This is a desktop build helper; nothing here runs on the calculator.
"""
import ast
import builtins
import copy


class PackError(ValueError):
    pass


KINDS = ('ui', 'core', 'family', 'soft', 'view', 'aux')
# MicroPython's compiler gives these bare names a meaning: const(x) must fold to an integer.
COMPILER = ('const',)


def _literal(node):
    try:
        return ('ok', ast.literal_eval(node))
    except (ValueError, TypeError, SyntaxError):
        return None


def _bindings(tree):
    """{name: [statement, ...]} for module-level bindings (not inside functions/classes)."""
    out = {}

    def add(name, stmt):
        out.setdefault(name, []).append(stmt)

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.ClassDef)):
            add(stmt.name, stmt)
            continue
        if isinstance(stmt, ast.Import):
            for a in stmt.names:
                add(a.asname or a.name, stmt)
            continue
        if isinstance(stmt, ast.ImportFrom):
            raise PackError('from-imports are not supported in device modules')
        for node in ast.walk(stmt):
            if isinstance(node, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
                raise PackError('nested definition at module level')
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                add(node.id, stmt)
    return out


def _comprehension_targets(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    out.add(n.id)
    return out


def _immutable(v):
    if isinstance(v, tuple):
        return all(_immutable(x) for x in v)
    return v is None or isinstance(v, (bool, int, float, complex, str, bytes))


def _function_locals(fn):
    names = {a.arg for a in fn.args.args}
    names.update(a.arg for a in (fn.args.vararg, fn.args.kwarg) if a)
    declared = set()
    for node in ast.walk(fn):
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
            raise PackError('nested definition in %s' % fn.name)
        if isinstance(node, ast.Global):
            declared.update(node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(a.asname or a.name for a in node.names)
    return names - declared, declared


BUILTINS = frozenset(dir(builtins))


def _free_builtins(m, only=None):
    """Builtin names that module m (or only its function `only`) reads without binding them:
    in a pack they would resolve to another module's top-level binding of the same name."""
    out = set()
    for stmt in m.tree.body:
        fn = isinstance(stmt, ast.FunctionDef)
        if only is not None and not (fn and stmt.name == only):
            continue
        local = _function_locals(stmt)[0] if fn else set()
        for node in ast.walk(stmt):
            if isinstance(node, ast.comprehension):
                local = local | set(n.id for n in ast.walk(node.target) if isinstance(n, ast.Name))
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and \
                    node.id in BUILTINS and node.id not in local and node.id not in m.bindings:
                out.add(node.id)
    return out


class Module(object):
    """One bundled device module and what the rewrite needs to know about it."""

    def __init__(self, name, source, home):
        self.name, self.home = name, home
        self.tree = ast.parse(source, filename=name + '.py')
        self.bindings = _bindings(self.tree)
        self.functions = set(s.name for s in self.tree.body if isinstance(s, ast.FunctionDef))
        self.aliases = {}               # module-level alias -> device module (project imports)
        self.natives = {}               # module-level alias -> native module name
        self.values = {}                # name -> literal value of its only plain assignment
        self.mutates = set()            # globals assigned inside functions
        self.lazy = set()               # aliases a function binds later (global N; import X as N)
        self.backref = set()            # aliases another module's body binds to that module
        self.wiring = []                # this module's statements binding a back-reference
        for stmt in self.tree.body:
            if isinstance(stmt, ast.Import):
                for a in stmt.names:
                    if '.' in a.name:
                        raise PackError('%s: dotted import %s' % (name, a.name))
            elif (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and
                  isinstance(stmt.targets[0], ast.Name)):
                lit = _literal(stmt.value)
                if lit is not None and len(self.bindings[stmt.targets[0].id]) == 1:
                    self.values[stmt.targets[0].id] = lit[1]
            elif isinstance(stmt, ast.FunctionDef):
                self.mutates.update(_function_locals(stmt)[1])


def _runtime_keys(run_source):
    """run.py's device DEV table: runtime key -> device module."""
    for stmt in ast.parse(run_source).body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and
                isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == 'DEV'):
            return ast.literal_eval(stmt.value)
    raise PackError('run module has no literal DEV table')


class Plan(object):
    """Pack membership, function placement, renames and the run-time key map."""

    def __init__(self, sources, man, run='CVRUN'):
        rows = man.rows()
        dev = dict((rows[s][0], rows[s][1]) for s in rows)
        self.order = []                 # (pack, kind, home modules, placed (module, fn))
        self.kind = {}
        self.owner = {}                 # device module -> home pack
        self.place = {}                 # (device module, function) -> pack
        for pack, members, kind in man.PACKS:
            if kind not in KINDS:
                raise PackError('pack %s: unknown kind %r' % (pack, kind))
            if pack in self.kind:
                raise PackError('pack %s is listed twice' % pack)
            self.kind[pack] = kind
            homes, placed = [], []
            for item in members:
                src, _, fn = item.partition('.')
                if src not in dev or dev[src] not in sources:
                    raise PackError('pack %s: %s has no bundled source' % (pack, src))
                d = dev[src]
                if fn:
                    if (d, fn) in self.place:
                        raise PackError('%s.%s is placed twice' % (src, fn))
                    self.place[(d, fn)] = pack
                    placed.append((d, fn))
                else:
                    if d in self.owner:
                        raise PackError('%s is in two packs' % d)
                    self.owner[d] = pack
                    homes.append(d)
            self.order.append((pack, kind, tuple(homes), tuple(placed)))
        for d in sources:
            if d not in self.owner and d != 'CASEVO':
                raise PackError('%s is in no pack' % d)
        # Soft and view packs are never held: code reaches them through __import__ only. A view
        # pack (UI code) may run while run.need loads a family, so only a computation unloads it.
        # An aux pack holds computation code that cannot reach the loader; it gives way last.
        self.soft = set(p for p in self.kind if self.kind[p] in ('soft', 'view', 'aux'))
        self.run = run
        self.keys = _runtime_keys(sources[run])
        self.modules = {}
        for d in self.owner:
            self.modules[d] = Module(d, sources[d], self.owner[d])
        for (d, fn), pack in self.place.items():
            if d not in self.modules or (fn not in self.modules[d].functions and
                                         not self.constant(d, fn)):
                raise PackError('%s.%s is placed but is no top-level function or constant'
                                % (d, fn))
            if pack == self.owner[d]:
                raise PackError('%s.%s is placed in its own home pack' % (d, fn))
        for m in self.modules.values():
            for stmt in m.tree.body:
                if isinstance(stmt, ast.Import):
                    for a in stmt.names:
                        (m.aliases if a.name in self.owner else m.natives)[a.asname or a.name] = a.name
            if m.home in self.soft and m.mutates - set(m.aliases):
                raise PackError('%s lives in soft pack %s but assigns globals %s: a reload '
                                'would lose them' % (m.name, m.home, sorted(m.mutates)))
            clash = set(self.kind) & set(m.bindings)
            if clash:
                raise PackError('%s binds a pack name: %s' % (m.name, sorted(clash)))
        self._lazy()
        self._backrefs()
        self._check_aux()
        self.stored = set()             # names some module stores as an attribute (A.NAME = v)
        for m in self.modules.values():
            for node in ast.walk(m.tree):
                if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                    self.stored.add(node.attr)
        self.rename = {}                # (device module, name) -> new name
        used = set()
        for m in self.modules.values():
            used.update(m.bindings)
            for node in ast.walk(m.tree):
                if isinstance(node, ast.Name):
                    used.add(node.id)
                elif isinstance(node, ast.Attribute):
                    used.add(node.attr)
        for pack, kind, homes, placed in self.order:
            first = {}
            entries = []
            for d in homes:
                m = self.modules[d]
                for name in sorted(m.bindings):
                    if self.place.get((d, name), pack) != pack:
                        continue        # placed functions live elsewhere
                    if name in m.aliases and name not in m.lazy and \
                            self.owner[m.aliases[name]] in (pack,) + tuple(self.soft):
                        continue        # same-pack and soft aliases bind nothing in a pack
                    entries.append((d, name))
            entries.extend(placed)
            free = {}                   # builtin name -> modules of this pack that read it
            for d in homes:
                for n in _free_builtins(self.modules[d]):
                    free.setdefault(n, set()).add(d)
            for d, fn in placed:
                for n in _free_builtins(self.modules[d], fn):
                    free.setdefault(n, set()).add(d)
            for d, name in entries:
                m = self.modules[d]
                if free.get(name, set()) - set([d]):
                    # another module of this pack calls the builtin `name`: keep it reaching
                    # the builtin, not this module's global
                    new = '%s_%s' % (name, d[2:].lower())
                    while new in used:
                        new += '_'
                    used.add(new)
                    self.rename[(d, name)] = new
                    continue
                if name in COMPILER:
                    new = '%s_%s' % (name, d[2:].lower())
                    while new in used:
                        new += '_'
                    used.add(new)
                    self.rename[(d, name)] = new
                    continue
                if name not in first:
                    first[name] = d
                    continue
                if first[name] == d or self._shared(self.modules[first[name]], m, name):
                    continue
                new = '%s_%s' % (name, d[2:].lower())
                while new in used:
                    new += '_'
                used.add(new)
                self.rename[(d, name)] = new
        self.renamed = set(name for _, name in self.rename)
        self.strings = set()            # every string constant: possible reflective names
        for m in self.modules.values():
            for node in ast.walk(m.tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.strings.add(node.value)

    def _backrefs(self):
        """Module-level 'A.X = __import__(__name__)' in M, A M's alias of T and 'X = None' in T:
        X is T's alias of M (see the module docstring). T must live in a soft pack."""
        for m in self.modules.values():
            for stmt in m.tree.body:
                if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and
                        isinstance(stmt.targets[0], ast.Attribute) and
                        isinstance(stmt.targets[0].value, ast.Name) and
                        stmt.targets[0].value.id in m.aliases and
                        isinstance(stmt.value, ast.Call) and
                        isinstance(stmt.value.func, ast.Name) and
                        stmt.value.func.id == '__import__' and len(stmt.value.args) == 1 and
                        isinstance(stmt.value.args[0], ast.Name) and
                        stmt.value.args[0].id == '__name__'):
                    continue
                t = self.modules[m.aliases[stmt.targets[0].value.id]]
                x = stmt.targets[0].attr
                if x not in t.values or t.values[x] is not None or x in t.aliases:
                    raise PackError('%s binds %s.%s, which is no "%s = None" back-reference'
                                    % (m.name, t.name, x, x))
                if t.home not in self.soft:
                    raise PackError('%s has a back-reference to %s but lives in %s, which is '
                                    'not a soft pack' % (t.name, m.name, t.home))
                t.aliases[x] = m.name
                t.backref.add(x)
                m.wiring.append(stmt)

    def _check_aux(self):
        """Code in an aux pack runs while run.need may unload packs, so it must never reach the
        loader: its module may not import run, even through other project modules."""
        aux = [(d, fn) for (d, fn), pack in self.place.items() if self.kind[pack] == 'aux']
        aux += [(d, None) for d, pack in self.owner.items() if self.kind[pack] == 'aux']
        for d, fn in aux:
            pack = self.place.get((d, fn), self.owner[d])
            what = '%s.%s' % (d, fn) if fn else d
            seen, todo = set(), [d]
            while todo:
                x = todo.pop()
                if x in seen:
                    continue
                seen.add(x)
                if x == self.run:
                    raise PackError('%s is in aux pack %s but %s reaches run' % (what, pack, d))
                todo.extend(self.modules[x].aliases.values())
            for s in self.modules[d].tree.body:
                if isinstance(s, ast.FunctionDef) and (fn is None or s.name == fn) and \
                        any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(s)):
                    raise PackError('%s.%s: a generator cannot live in aux pack %s'
                                    % (d, s.name, pack))

    def _lazy(self):
        """Lazy aliases (ui.engine): a module-level 'N = None' that some function of the pack
        binds with 'global N' and 'import X as N'. Every module of the pack binding N shares it."""
        for pack, kind, homes, placed in self.order:
            found = {}
            for d in homes:
                for stmt in self.modules[d].tree.body:
                    if not isinstance(stmt, ast.FunctionDef):
                        continue
                    declared = _function_locals(stmt)[1]
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Import):
                            for a in sub.names:
                                n = a.asname or a.name
                                if a.name in self.owner and n in declared:
                                    if found.get(n, a.name) != a.name:
                                        raise PackError('%s: lazy alias %s names two modules' % (pack, n))
                                    found[n] = a.name
            for d in homes:
                m = self.modules[d]
                for n, x in found.items():
                    if n in m.bindings:
                        if n not in m.values or m.values[n] is not None:
                            raise PackError('%s: lazy alias %s must start as None' % (d, n))
                        m.aliases[n] = x
                        m.lazy.add(n)

    def constant(self, device, name):
        """A module-level name bound once to a literal and never assigned in a function: it
        can live in any pack, like a function (tables only the UI's screens read)."""
        m = self.modules[device]
        return name in m.values and name not in m.mutates

    def _shared(self, a, b, name):
        """Both modules bind name to the same literal, import the same native module, or alias
        modules of the same pack."""
        if name in a.aliases or name in b.aliases:
            return (name in a.aliases and name in b.aliases and
                    self.owner[a.aliases[name]] == self.owner[b.aliases[name]])
        if name in a.natives or name in b.natives:
            return a.natives.get(name) == b.natives.get(name) and name in a.natives
        if name in a.values and name in b.values:
            va, vb = a.values[name], b.values[name]
            if name in a.mutates or name in b.mutates or name in self.stored or \
                    not _immutable(va):
                return False        # one shared object or global would couple the modules
            return va == vb and type(va) is type(vb)
        return False

    def where(self, device, name):
        """The pack holding a module-level binding of a device module."""
        return self.place.get((device, name), self.owner.get(device))


class Resolver(object):
    """Which device module an expression evaluates to, statically or through the loader."""

    def __init__(self, plan, module, aliases, local_aliases=None, locals_=()):
        self.plan, self.module = plan, module
        self.aliases = aliases          # module-level project aliases of the current module
        self.local = local_aliases or {}
        self.locals = set(locals_)

    def static(self, node):
        """The device module of a plain alias name (import binding), else None."""
        if isinstance(node, ast.Name):
            if node.id in self.local:
                v = self.local[node.id]
                if isinstance(v, tuple) and v[0] == 'import':
                    return v[1]
                return None
            if node.id not in self.locals:
                return self.aliases.get(node.id)
        return None

    def __call__(self, node):
        plan = self.plan
        if isinstance(node, ast.Name):
            if node.id in self.local:
                v = self.local[node.id]
                return v[1] if isinstance(v, tuple) else v
            if node.id in self.locals:
                return None
            if node.id in self.aliases:
                return self.aliases[node.id]
            if self.module == plan.run and node.id == 'MODS':
                return '#mods'
            return None
        if isinstance(node, ast.Attribute):
            if node.attr == 'MODS' and self(node.value) == plan.run:
                return '#mods'
            return None
        if isinstance(node, ast.Subscript):
            if self(node.value) == '#mods':
                key = node.slice
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    return plan.keys.get(key.value, '*')
                return '*'
            return None
        if isinstance(node, ast.Call):
            fn = node.func
            needer = (isinstance(fn, ast.Attribute) and fn.attr == 'need' and
                      self(fn.value) == plan.run) or (
                isinstance(fn, ast.Name) and fn.id == 'need' and self.module == plan.run and
                'need' not in self.locals)
            if needer:
                if node.args and isinstance(node.args[0], ast.Constant):
                    return plan.keys.get(node.args[0].value, '*')
                return '*'
            if isinstance(fn, ast.Name) and fn.id == '__import__':
                return '*'
        return None


def _local_aliases(plan, module, aliases, fn, locals_):
    """Function-local names bound to modules: imports and assignments from module values."""
    table = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in plan.owner:
                    table[a.asname or a.name] = ('import', a.name)
    for _ in range(8):
        before = dict(table)
        r = Resolver(plan, module, aliases, table, locals_)
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1 and
                    isinstance(node.targets[0], ast.Name)):
                name = node.targets[0].id
                if isinstance(table.get(name), tuple):
                    continue
                v = r(node.value)
                if v is not None and v != '#mods':
                    old = table.get(name)
                    table[name] = v if old in (None, v) else '*'
        if table == before:
            return table
    raise PackError('module aliases did not converge in %s.%s' % (module, fn.name))


def _import(pack, node):
    return ast.copy_location(ast.Call(func=ast.Name(id='__import__', ctx=ast.Load()),
                                      args=[ast.Constant(pack)], keywords=[]), node)


class Rewrite(ast.NodeTransformer):
    """Rewrite the statements of one device module (or client) emitted into pack ``here``."""

    def __init__(self, plan, name, here, aliases, client=False):
        self.plan, self.name, self.here = plan, name, here
        self.aliases = aliases
        self.client = client
        self.fn = None
        self.locals = set()
        self.declared = set()
        self.needs_global = set()
        self.drop_global = set()
        self.uses = set()               # resident packs this code reads by name
        self.resolve = Resolver(plan, name, aliases)

    # -- references --------------------------------------------------------------------------
    def alias_name(self, via):
        """The name an alias of this module (or a local import alias) has in the pack."""
        if self.fn is not None and via in self.locals:
            return via
        if self.client:
            return via
        return self.plan.rename.get((self.name, via), via)

    def lazy_elsewhere(self, via):
        """A lazy alias read by code placed away from its home: the engine is bound there at
        run time, and importing it here would load it too early (at boot for the UI)."""
        if self.client or (self.fn is not None and via in self.locals):
            return False
        m = self.plan.modules.get(self.name)
        return m is not None and via in m.lazy and self.here != m.home

    def home_alias(self, via, node):
        home = self.plan.owner[self.name]
        self.use(home)
        return ast.copy_location(ast.Attribute(value=ast.Name(id=home, ctx=ast.Load()),
                                               attr=self.alias_name(via), ctx=ast.Load()), node)

    def bound(self, via, device):
        """Does the alias via (naming device) exist where this code runs? Module aliases exist
        in the module's home pack only; import aliases of the pack itself or of a soft pack are
        never bound."""
        pack = self.plan.owner.get(device)
        if pack == self.here or pack in self.plan.soft:
            return False
        if self.fn is not None and via in self.locals:
            return True
        if self.client:
            return via in self.aliases
        # Module aliases are bound as the pack's own name; a lazy alias (bound later by a
        # function) exists in its home pack only.
        m = self.plan.modules.get(self.name)
        return m is not None and via in m.lazy and self.here == m.home

    def ref(self, device, name, ctx, node, via=None):
        """An expression for a module-level binding of a device module, read or written here.
        via: the alias name the source used for the module, if any; it reaches the pack."""
        plan = self.plan
        loc = plan.where(device, name)
        new = plan.rename.get((device, name), name)
        if loc == self.here and not self.client:
            if self.fn is not None:
                if new in self.locals:
                    raise PackError('%s.%s: the global %s is also a local' % (self.name, self.fn, new))
                if not isinstance(ctx, ast.Load):
                    self.needs_global.add(new)
            return ast.copy_location(ast.Name(id=new, ctx=ctx), node)
        if loc in plan.soft:
            if self.fn is None and self.here is not None and not self.client:
                raise PackError('%s: module code reaches %s.%s in soft pack %s and would keep '
                                'it loaded' % (self.name, device, name, loc))
            value = _import(loc, node)
        elif via is not None and plan.owner.get(device) == loc and self.bound(via, device):
            value = ast.copy_location(ast.Name(id=self.alias_name(via), ctx=ast.Load()), node)
        elif via is not None and plan.owner.get(device) == loc and self.lazy_elsewhere(via):
            value = self.home_alias(via, node)
        else:
            self.use(loc)
            value = ast.copy_location(ast.Name(id=loc, ctx=ast.Load()), node)
        return ast.copy_location(ast.Attribute(value=value, attr=new, ctx=ctx), node)

    def use(self, pack):
        """Record a by-name read of a resident pack unless a function-level import binds it."""
        if self.fn is not None:
            for v in self.resolve.local.values():
                if isinstance(v, tuple) and self.plan.owner.get(v[1]) == pack:
                    return
        self.uses.add(pack)

    def module_value(self, device, node, via=None):
        """An expression for the module object of a device module (its home pack)."""
        pack = self.plan.owner[device]
        if pack == self.here and not self.client:
            return _import(pack, node)
        if pack in self.plan.soft:
            return _import(pack, node)
        if via is not None and self.bound(via, device):
            return ast.copy_location(ast.Name(id=self.alias_name(via), ctx=ast.Load()), node)
        if via is not None and self.lazy_elsewhere(via):
            return self.home_alias(via, node)
        self.use(pack)
        return ast.copy_location(ast.Name(id=pack, ctx=ast.Load()), node)

    def own_global(self, name):
        """Is a free name in the current code a module-level binding of this module?"""
        if self.client:
            return False
        m = self.plan.modules.get(self.name)
        return m is not None and name in m.bindings and name not in m.aliases

    def visit_Name(self, node):
        if self.fn is not None and node.id in self.locals:
            if node.id in self.resolve.local and isinstance(self.resolve.local[node.id], tuple):
                device = self.resolve.local[node.id][1]
                if isinstance(node.ctx, ast.Load):
                    return self.module_value(device, node, node.id)
            return node
        if node.id in self.aliases:
            lazy = self.id_lazy(node.id)
            if not isinstance(node.ctx, ast.Load) and not lazy:
                raise PackError('%s rebinds the module alias %s' % (self.name, node.id))
            if not isinstance(node.ctx, ast.Load):
                return self.ref(self.name, node.id, node.ctx, node)   # the lazy global itself
            return self.module_value(self.aliases[node.id], node, node.id)
        if self.own_global(node.id):
            return self.ref(self.name, node.id, node.ctx, node)
        return node

    def visit_Attribute(self, node):
        target = self.resolve(node.value)
        if target is None and node.attr in self.plan.renamed:
            raise PackError('%s: .%s on a value that is not a known module, but a pack renamed '
                            'that name' % (self.name, node.attr))
        if target is None or target == '#mods':
            return self.generic_visit(node)
        if target == '*':
            loaded = set(self.plan.keys.values())
            if any(t in loaded and n == node.attr for t, n in self.plan.rename) or \
                    any(t in loaded and f == node.attr for t, f in self.plan.place):
                raise PackError('%s: .%s of a run-time module is renamed or placed in a pack' %
                                (self.name, node.attr))
            return self.generic_visit(node)
        static = self.resolve.static(node.value)
        if static is None and isinstance(node.value, ast.Subscript):
            # R.MODS['k'] of a module in this very pack: the pack is running, so the module is
            # loaded, even while its own import is still running (defaults, module tables).
            # The lookup has no side effects; need('k') calls keep their pin bookkeeping.
            if self.plan.owner.get(target) == self.here and not self.client:
                static = target
        if static is not None:
            via = node.value.id if isinstance(node.value, ast.Name) else None
            return self.ref(static, node.attr, node.ctx, node, via)
        loc = self.plan.where(target, node.attr)
        if loc != self.plan.owner[target]:
            raise PackError('%s: %s.%s is placed in %s, but this code reaches it through the '
                            'loader' % (self.name, target, node.attr, loc))
        attr = self.plan.rename.get((target, node.attr), node.attr)
        value = self.visit(node.value)
        return ast.copy_location(ast.Attribute(value=value, attr=attr, ctx=node.ctx), node)

    def visit_Call(self, node):
        fn = node.func
        if (isinstance(fn, ast.Name) and fn.id in ('getattr', 'hasattr', 'setattr', 'delattr') and
                (self.fn is None or fn.id not in self.locals) and len(node.args) >= 2):
            target = self.resolve(node.args[0])
            if target not in (None, '#mods'):
                key = node.args[1]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if target == '*':
                        if key.value in self.plan.renamed:
                            raise PackError('%s: %s(..., %r) of a run-time module is renamed'
                                            % (self.name, fn.id, key.value))
                    else:
                        if self.plan.where(target, key.value) != self.plan.owner[target]:
                            raise PackError('%s: %s of placed %s.%s' % (self.name, fn.id, target, key.value))
                        new = self.plan.rename.get((target, key.value), key.value)
                        node.args[1] = ast.copy_location(ast.Constant(new), key)
                else:
                    # A run-time module ('*') is one the loader can return: a family module.
                    loaded = set(self.plan.keys.values())
                    reach = lambda t: t == target or (target == '*' and t in loaded)
                    said = lambda n: n in self.plan.strings or n.lower() in self.plan.strings
                    names = sorted(n for t, n in self.plan.rename if reach(t) and said(n))
                    names += sorted(f for (t, f) in self.plan.place if reach(t) and said(f))
                    if names:
                        raise PackError('%s: computed %s may name renamed or placed %s'
                                        % (self.name, fn.id, names))
        return self.generic_visit(node)

    # -- statements ----------------------------------------------------------------------------
    def id_lazy(self, name):
        m = self.plan.modules.get(self.name)
        return m is not None and name in m.lazy

    def visit_Import(self, node):
        kept = []
        out = []
        for a in node.names:
            if a.name in self.plan.owner:
                pack = self.plan.owner[a.name]
                alias = a.asname or a.name
                if pack in self.plan.soft:
                    continue                # soft packs are reached through __import__ only
                if pack == self.here and not self.client:
                    continue                # the pack itself: plain globals
                if self.fn is not None and alias in self.declared:
                    # global N; import X as N (ui.engine): bind the pack to the global
                    target = self.visit_Name(ast.copy_location(
                        ast.Name(id=alias, ctx=ast.Store()), node))
                    out.append(ast.copy_location(ast.Assign(
                        targets=[target], value=_import(pack, node)), node))
                    continue
                if self.fn is None and not self.client:
                    # Module aliases bind the pack under its own name: a merged pack may use
                    # the old alias spelling as some function's local, and the shrinker's
                    # alias analysis is scope-free.
                    if all(not (isinstance(s, ast.Import) and s.names[0].name == pack) for s in out):
                        out.append(ast.copy_location(ast.Import(names=[ast.alias(name=pack)]), node))
                    continue
                name = self.alias_name(alias)
                out.append(ast.copy_location(ast.Import(names=[ast.alias(
                    name=pack, asname=name if name != pack else None)]), node))
            else:
                alias = a.asname or a.name
                new = alias
                if self.fn is None and not self.client:
                    new = self.plan.rename.get((self.name, alias), alias)
                kept.append(ast.alias(name=a.name, asname=new if new != a.name else None))
        if kept:
            out.insert(0, ast.copy_location(ast.Import(names=kept), node))
        if not out:
            return ast.copy_location(ast.Pass(), node)
        return out if len(out) > 1 else out[0]

    def visit_Assign(self, node):
        value = self.resolve.static(node.value) if isinstance(node.value, ast.Name) else None
        if value is not None and self.plan.owner[value] in self.plan.soft:
            for t in node.targets:          # only the wiring of a lazy alias may store it
                ok = False
                if isinstance(t, ast.Name):
                    ok = self.plan.modules[self.name].aliases.get(t.id) == value
                elif isinstance(t, ast.Attribute):
                    d = self.resolve.static(t.value)
                    ok = d is not None and d in self.plan.modules and \
                        self.plan.modules[d].aliases.get(t.attr) == value
                if not ok:
                    raise PackError('%s stores soft module %s: it would stay loaded'
                                    % (self.name, value))
            return ast.copy_location(ast.Pass(), node)
        return self.generic_visit(node)

    def visit_Global(self, node):
        names = []
        for n in node.names:
            if self.own_global(n) and self.plan.where(self.name, n) != self.here:
                continue                    # written through the home pack instead
            names.append(self.plan.rename.get((self.name, n), n) if self.own_global(n) else n)
        if not names:
            return ast.copy_location(ast.Pass(), node)
        node.names = names
        return node

    def _unshadow(self, node, locals_, local_aliases):
        """Rename locals that would capture a global this function now reads by bare name."""
        r = Resolver(self.plan, self.name, self.aliases, local_aliases, locals_)
        wanted = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute):
                st = r.static(sub.value)
                if st is not None and self.plan.where(st, sub.attr) == self.here and not self.client:
                    wanted.add(self.plan.rename.get((st, sub.attr), sub.attr))
        clash = sorted(wanted & locals_)
        if not clash:
            return node
        params = {a.arg for a in node.args.args}
        params.update(a.arg for a in (node.args.vararg, node.args.kwarg) if a)
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | wanted
        mapping = {}
        for name in clash:
            if name in params:
                raise PackError('%s.%s: parameter %s shadows a same-pack global' %
                                (self.name, node.name, name))
            new = name + '_'
            while new in used:
                new += '_'
            used.add(new)
            mapping[name] = new
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in mapping:
                sub.id = mapping[sub.id]
            elif isinstance(sub, ast.ExceptHandler) and sub.name in mapping:
                sub.name = mapping[sub.name]
            elif isinstance(sub, ast.alias) and (sub.asname or sub.name) in mapping:
                sub.asname = mapping[sub.asname or sub.name]
        return node

    def visit_FunctionDef(self, node):
        if self.fn is not None:
            raise PackError('nested function in %s' % self.name)
        locals_, declared = _function_locals(node)
        local_aliases = _local_aliases(self.plan, self.name, self.aliases, node, locals_)
        node = self._unshadow(node, locals_, local_aliases)
        locals_, declared = _function_locals(node)
        local_aliases = _local_aliases(self.plan, self.name, self.aliases, node, locals_)
        saved = self.resolve
        self.resolve = Resolver(self.plan, self.name, self.aliases, local_aliases, locals_)
        node.args.defaults = [self.visit_default(d) for d in node.args.defaults]
        self.fn, self.locals, self.declared, self.needs_global = node.name, locals_, declared, set()
        body = []
        for s in node.body:
            new = self.visit(s)
            body.extend(new if isinstance(new, list) else [new])
        kept = set()
        for s in body:
            if isinstance(s, ast.Global):
                kept.update(s.names)
        extra = sorted(self.needs_global - kept)
        if extra:
            body.insert(0, ast.Global(names=extra))
        node.body = body
        if not self.client:
            node.name = self.plan.rename.get((self.name, node.name), node.name)
        self.fn, self.locals, self.declared, self.needs_global = None, set(), set(), set()
        self.resolve = saved
        return node

    def visit_default(self, node):
        saved = self.fn, self.locals
        self.fn, self.locals = None, set()
        try:
            return self.visit(node)
        finally:
            self.fn, self.locals = saved

    def visit_ClassDef(self, node):
        if self.fn is not None:
            raise PackError('class inside a function in %s' % self.name)
        node.bases = [self.visit(b) for b in node.bases]
        if not self.client:
            node.name = self.plan.rename.get((self.name, node.name), node.name)
        return node

    def visit_Lambda(self, node):
        raise PackError('lambda in %s: closures need a scope audit' % self.name)


def _check_comprehensions(plan, module):
    risky = set(module.aliases) | set(n for (d, n) in plan.rename if d == module.name)
    risky.update(f for (d, f) in plan.place if d == module.name)
    hit = _comprehension_targets(module.tree) & risky
    if hit:
        raise PackError('%s: comprehension rebinds %s' % (module.name, sorted(hit)))


def _dev_table(plan, tree):
    """Point run.py's DEV entries at packs (missing modules keep their device name)."""
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and
                isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == 'DEV'):
            table = ast.literal_eval(stmt.value)
            new = dict((k, plan.owner.get(v, v)) for k, v in table.items())
            stmt.value = ast.parse(repr(dict(sorted(new.items()))), mode='eval').body
            return new
    raise PackError('run module has no DEV table')


def _set(tree, name, value):
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and
                isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == name):
            stmt.value = ast.parse(repr(value), mode='eval').body
            return
    raise PackError('run module has no %s table' % name)


def loader_tables(source, run_tables):
    """Set run.py's loader tables in an (unshrunk) pack source; returns the new source."""
    tree = ast.parse(source)
    for name in sorted(run_tables):
        _set(tree, name, run_tables[name])
    return ast.unparse(tree) + '\n'


def costs(plan_meta, family_keys, sizes, factor=1.25, fixed=512):
    """COST for run.need: each family's pack, charged once to its family key (bytes of heap).

    The 32-bit measurements in docs/notes/FASTBOOT.md put a pack's heap at 1.1 to 1.6 times
    its bytecode; factor and fixed cover the common case, and a short estimate only means the
    actual import raises MemoryError, which run.go retries once without stale families.
    """
    out = {}
    for key, pack in sorted(family_keys.items()):
        out[key] = int(sizes[pack] * factor) + fixed
    return out


def merge(sources, man, clients=()):
    """Return ({pack: source}, {client: source}, metadata). Sources use device names."""
    plan = Plan(sources, man)
    for m in plan.modules.values():
        _check_comprehensions(plan, m)
    emitted = dict((p, []) for p in plan.kind)  # pack -> [(module, statement)]
    for pack, kind, homes, placed in plan.order:
        for d in homes:
            m = plan.modules[d]
            for stmt in m.tree.body:
                if isinstance(stmt, ast.FunctionDef) and (d, stmt.name) in plan.place:
                    continue
                if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and
                        isinstance(stmt.targets[0], ast.Name) and
                        ((d, stmt.targets[0].id) in plan.place or
                         stmt.targets[0].id in m.backref)):
                    continue
                if any(stmt is w for w in m.wiring):
                    continue                    # a back-reference: compiled away
                emitted[pack].append((d, stmt))
        for d, fn in placed:
            stmt = [s for s in plan.modules[d].tree.body
                    if isinstance(s, ast.FunctionDef) and s.name == fn or
                    isinstance(s, ast.Assign) and len(s.targets) == 1 and
                    isinstance(s.targets[0], ast.Name) and s.targets[0].id == fn][0]
            emitted[pack].append((d, stmt))
    packs, meta = {}, {'packs': {}, 'statements': {}}
    for pack, kind, homes, placed in plan.order:
        body, spans, uses = [], [], set()
        for d, stmt in emitted[pack]:
            m = plan.modules[d]
            rw = Rewrite(plan, d, pack, m.aliases)
            new = rw.visit(copy.deepcopy(stmt))
            new = new if isinstance(new, list) else [new]
            if d == plan.run and isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
                    isinstance(stmt.targets[0], ast.Name):
                holder = ast.Module(body=new, type_ignores=[])
                table = stmt.targets[0].id
                if table == 'DEV':
                    meta['dev'] = _dev_table(plan, holder)
                elif table == 'SOFT':
                    _set(holder, 'SOFT', tuple(p for p, k, _, _ in plan.order if k == 'soft'))
                elif table == 'VIEW':
                    _set(holder, 'VIEW', tuple(p for p, k, _, _ in plan.order if k == 'view'))
                elif table == 'AUX':
                    _set(holder, 'AUX', tuple(p for p, k, _, _ in plan.order if k == 'aux'))
                elif table == 'EVDICT':
                    _set(holder, 'EVDICT', 1)       # see run.unload
                elif table == 'SHEDAT':
                    _set(holder, 'SHEDAT', 0)       # set by the release
                elif table == 'ROOM':
                    _set(holder, 'ROOM', {})        # set from compiled sizes by the release
                elif table in ('LINES', 'COST'):
                    _set(holder, table, {})     # set from compiled sizes by the release
                elif table == 'PEAKB':
                    _set(holder, 'PEAKB', 0)    # bytecode: no compiler runs on the calculator
                elif table == 'FRAG':
                    _set(holder, 'FRAG', getattr(man, 'PACKFRAG', 2048))
            uses.update(rw.uses)
            for s in new:
                if isinstance(s, ast.Import) and len(s.names) == 1 and s.names[0].asname is None \
                        and s.names[0].name in plan.kind and \
                        any(isinstance(b, ast.Import) and len(b.names) == 1 and
                            b.names[0].asname is None and b.names[0].name == s.names[0].name
                            for b in body):
                    continue                # the pack is already imported, by another module
                body.append(s)
                spans.append((d, stmt.lineno, stmt.end_lineno))
        imported = set()
        for s in body:
            if isinstance(s, ast.Import):
                imported.update(a.asname or a.name for a in s.names)
        missing = [p for p, _, _, _ in plan.order if p in uses and p not in imported and p != pack]
        for p in missing:
            if plan.kind[p] not in ('core', 'ui'):
                raise PackError('%s reads %s by name, which may be evicted' % (pack, p))
        head = [ast.Import(names=[ast.alias(name=p)]) for p in missing]
        body = head + body
        spans = [None] * len(head) + spans
        # The last statement: MicroPython 1.12 keeps a module whose body raised (a MemoryError
        # while it loads), so run.sweep and run.room tell a whole pack by this binding.
        body.append(ast.Assign(targets=[ast.Name(id='__ok__', ctx=ast.Store())],
                               value=ast.Constant(1)))
        spans.append(None)
        module = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
        source = ast.unparse(module) + '\n'
        compile(source, pack + '.py', 'exec')
        packs[pack] = source
        meta['packs'][pack] = {'kind': kind, 'modules': list(homes),
                               'placed': ['%s.%s' % p for p in placed]}
        meta['statements'][pack] = spans
    out_clients = {}
    for name in clients:
        tree = ast.parse(clients[name], filename=name + '.py')
        aliases = {}
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for a in stmt.names:
                    if a.name in plan.owner:
                        aliases[a.asname or a.name] = a.name
        rw = Rewrite(plan, name, None, aliases, client=True)
        body = []
        for stmt in tree.body:
            new = rw.visit(stmt)
            body.extend(new if isinstance(new, list) else [new])
        tree.body = body
        source = ast.unparse(ast.fix_missing_locations(tree)) + '\n'
        compile(source, name + '.py', 'exec')
        out_clients[name] = source
    meta['renames'] = dict(('%s.%s' % k, v) for k, v in sorted(plan.rename.items()))
    meta['owner'] = dict(sorted(plan.owner.items()))
    meta['place'] = dict(('%s.%s' % k, v) for k, v in sorted(plan.place.items()))
    meta['soft'] = sorted(plan.soft)
    meta['kinds'] = dict(sorted(plan.kind.items()))
    return packs, out_clients, meta
