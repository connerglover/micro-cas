"""Static checks that device code stays inside the TI-84 EVO Python subset.

DESIGN.md sections 4.2, 17.4 and 20.3; docs/reference/device-python.md section 13.

    python tests/support/lint.py [paths...]       # default: src/

Per-file checks only. The call-graph checks (levels, generators, imports inside functions,
module bodies) are FRAMELINT's (``framelint.py``).

Line markers (a comment on the offending line):
    #@unordered-ok   this dict/set iteration does not depend on the order
    #@float-ok       a deliberate float operation (``/`` in an exact module, ``round``,
                     ``repr``, ``%g``-style formats)
"""
import ast
import builtins
import io
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, 'src')

# -- the module map (DESIGN.md section 4.1) ----------------------------------------------------

# src module -> the fixed import alias every module uses for it. Parts (section 4.3) take the
# family's alias plus B, C or D: polyb -> POB, factord -> FAD.
ALIASES = {
    'node': 'K', 'parse': 'P', 'printer': 'PR', 'alg': 'A', 'run': 'R', 'draw': 'D',
    'ui': 'U', 'rules': 'RU', 'poly': 'PO', 'norm': 'NO', 'ident': 'ID', 'factor': 'FA',
    'solve': 'SO', 'forms': 'FO', 'diff': 'DF', 'series': 'SE', 'limit': 'LI',
    'integ': 'IN', 'itab': 'IT', 'integ2': 'I2', 'integ3': 'I3', 'defint': 'DI',
    'sums': 'SU', 'ode': 'OD', 'menu': 'M', 'catalog': 'CA',
}
ENTRY = ('casevo',)
# Resident modules (class R); every other module of the map is lazy (L or U).
RESIDENT = ('node', 'parse', 'printer', 'alg', 'run', 'draw', 'ui')
# Only these import ti_* (section 4.2); parts of menu count as menu.
UI_MODULES = ('ui', 'draw', 'menu', 'menub', 'casevo')
# Modules where '/' is banned (exact arithmetic; section 17.4). Parts are included by family.
EXACT_MODULES = ('node', 'parse', 'run', 'rules', 'poly', 'norm', 'ident', 'factor', 'solve',
                 'diff', 'series', 'integ', 'itab', 'integ2', 'integ3', 'forms', 'sums',
                 'ode')
# Native modules device code may import (device-python section 4.2).
NATIVE_MODULES = ('math', 'gc', 'sys', 'array', 'time', 'collections', 'random',
                  'ti_system', 'ti_graphics', 'ti_draw', 'ti_plotlib', 'ti_image')

BANNED_MODULES = ('re', 'fractions', 'decimal', 'functools', 'itertools', 'cmath', 'os',
                  'typing', 'dataclasses', 'enum', 'abc', 'copy', 'operator', 'string',
                  'struct', 'io', 'micropython', 'json', 'heapq', 'bisect', 'inspect',
                  'traceback', 'weakref', 'contextlib')
BANNED_ATTRS = ('bit_length', 'to_bytes', 'from_bytes', 'isqrt', 'gcd', 'lcm', 'comb',
                'perm', 'prod', 'fsum', 'log2', 'log10', 'hypot', 'removeprefix',
                'removesuffix', 'casefold', 'ljust', 'rjust', 'center', 'zfill', 'title',
                'capitalize', 'swapcase', 'isalnum', 'isnumeric', 'isdecimal',
                'isidentifier', 'isprintable', 'expandtabs', 'translate', 'maketrans',
                'format_map', 'setrecursionlimit', 'getrecursionlimit', 'settrace',
                'setprofile', 'getsizeof', 'set_int_max_str_digits', 'intern', 'popitem')
BANNED_NAMES = ('reversed', 'frozenset', 'format', 'vars', 'ascii', 'open', 'compile',
                'breakpoint', 'NotImplemented', 'RecursionError', 'ModuleNotFoundError',
                'exit', 'quit', 'delattr', 'eval', 'exec', 'property', 'staticmethod',
                'classmethod', 'super', 'help', '__slots__')
# math names documented for the CE (device-python section 4.2)
MATH_OK = ('e', 'pi', 'sqrt', 'pow', 'exp', 'log', 'cos', 'sin', 'tan', 'acos', 'asin',
           'atan', 'atan2', 'ceil', 'copysign', 'fabs', 'floor', 'fmod', 'frexp', 'ldexp',
           'modf', 'isfinite', 'isinf', 'isnan', 'trunc', 'radians', 'degrees')
DUNDER_ATTRS_OK = ('__name__', '__dict__')
FLOAT_FMT = re.compile(r'%[-+ #0]*(\d+|\*)?(\.(\d+|\*))?[eEfFgG]')


def family(mod):
    """'polyb' -> 'poly', 'integ2b' -> 'integ2', 'node' -> 'node'."""
    if mod in ALIASES or mod in ENTRY:
        return mod
    if len(mod) > 1 and mod[-1] in 'bcdefghijklmnopqrstuvwxyz' and mod[:-1] in ALIASES:
        return mod[:-1]
    return mod


def alias_for(mod):
    """The fixed import alias of a src module or part, or None if it is not in the map."""
    if mod in ALIASES:
        return ALIASES[mod]
    f = family(mod)
    if f != mod and f in ALIASES:
        return ALIASES[f] + mod[-1].upper()
    return None


def _marked(lines, node, marker):
    a = getattr(node, 'lineno', 0)
    b = getattr(node, 'end_lineno', a) or a
    for i in range(a, b + 1):
        if 0 < i <= len(lines) and marker in lines[i - 1]:
            return True
    return False


def _dictset_names(body_nodes):
    """Names bound (anywhere in these nodes) to a dict or set value."""
    out = set()
    for top in body_nodes:
        for n in ast.walk(top):
            if isinstance(n, ast.Assign):
                v = n.value
                if _is_dictset_expr(v):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            out.add(t.id)
    return out


def _is_dictset_expr(v):
    if isinstance(v, (ast.Dict, ast.Set, ast.DictComp, ast.SetComp)):
        return True
    if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and \
            v.func.id in ('dict', 'set', 'frozenset'):
        return True
    return False


def _gen_funcs(tree):
    """FunctionDef nodes that contain a yield of their own (not of a nested def)."""
    out = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            st = list(fn.body)
            found = False
            while st and not found:
                n = st.pop()
                if isinstance(n, (ast.Yield, ast.YieldFrom)):
                    found = True
                elif not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                        ast.ClassDef)):
                    st.extend(ast.iter_child_nodes(n))
            if found:
                out.append(fn)
    return out


def lint(src, filename='<src>', module=None, device_names=False):
    """Return a list of 'file:line: message' strings for one device source file.

    module:        the src module name ('node'); defaults to the file's stem.
    device_names:  bundled output: imports use device names (CVNODE) instead of src names.
    """
    if module is None:
        module = os.path.splitext(os.path.basename(filename))[0]
    errs = []
    lines = src.splitlines()

    def err(node, msg):
        errs.append('%s:%d: %s' % (filename, getattr(node, 'lineno', 0) or 0, msg))

    try:
        tree = ast.parse(src, filename)
    except SyntaxError as e:
        return ['%s:%s: syntax error: %s' % (filename, e.lineno, e.msg)]
    try:
        ast.parse(src, filename, feature_version=(3, 4))
    except SyntaxError as e:
        errs.append('%s:%s: not Python 3.4 syntax: %s' % (filename, e.lineno, e.msg))
    for i, ln in enumerate(lines):
        for ch in ln:
            if ord(ch) > 126 or (ord(ch) < 32 and ch not in '\t\r\n\f'):
                errs.append('%s:%d: non-ASCII character %r in source' % (filename, i + 1, ch))
                break
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.NUMBER and '_' in tok.string:
                errs.append('%s:%d: underscore in a numeric literal (3.6+)'
                            % (filename, tok.start[0]))
    except (tokenize.TokenError, SyntaxError):
        pass

    fam = family(module)
    exact = fam in EXACT_MODULES
    imported = {}                        # local name -> module name, for module aliases
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                imported[a.asname or a.name] = a.name
    # dict/set-valued names: module globals plus each function's locals
    gl_dictset = _dictset_names([s for s in tree.body if isinstance(s, ast.Assign)])
    fn_dictset = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            fn_dictset[fn] = _dictset_names(fn.body) | gl_dictset
    gens = _gen_funcs(tree)

    parents = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            parents[c] = p

    def enclosing_fn(n):
        p = parents.get(n)
        while p is not None and not isinstance(p, ast.FunctionDef):
            p = parents.get(p)
        return p

    def is_dictset(expr, at):
        if _is_dictset_expr(expr):
            return True
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and \
                expr.func.attr in ('keys', 'values', 'items') and not expr.args:
            return True
        if isinstance(expr, ast.Name):
            fn = enclosing_fn(at)
            names = fn_dictset.get(fn, gl_dictset) if fn is not None else gl_dictset
            return expr.id in names
        return False

    for node in ast.walk(tree):
        t = type(node)
        # -- syntax beyond Python 3.4 -----------------------------------------------------
        if t is ast.JoinedStr:
            err(node, 'f-string')
        elif t is ast.NamedExpr:
            err(node, 'assignment expression := (3.8+)')
        elif t is ast.AnnAssign:
            err(node, 'variable annotation (3.6+)')
        elif t in (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await):
            err(node, 'async/await')
        elif t.__name__ in ('Match', 'TryStar', 'TypeAlias'):
            err(node, '%s is not Python 3.4' % t.__name__)
        elif t is ast.BinOp and isinstance(node.op, ast.MatMult):
            err(node, '@ operator (3.5+)')
        elif t is ast.Raise and node.cause is not None:
            err(node, 'raise ... from ... (chaining is not kept on the device)')
        elif t in (ast.List, ast.Tuple, ast.Set) and not isinstance(
                getattr(node, 'ctx', None), ast.Store):
            for e in node.elts:
                if isinstance(e, ast.Starred):
                    err(node, '*unpacking inside a display (3.5+)')
                    break
        elif t is ast.Dict and None in node.keys:
            err(node, '{**d} (3.5+)')
        # -- functions ----------------------------------------------------------------------
        if t in (ast.FunctionDef, ast.Lambda):
            a = node.args
            if a.kwonlyargs:
                err(node, 'keyword-only parameters')
            if getattr(a, 'posonlyargs', None):
                err(node, 'positional-only parameters (3.8+)')
            for p in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
                if p is not None and p.annotation is not None:
                    err(node, 'parameter annotation')
                    break
        if t is ast.FunctionDef:
            if node.returns is not None:
                err(node, 'return annotation')
            if node.decorator_list:
                err(node, 'decorator on %s() (a hidden frame per call)' % node.name)
            if node.name[:2] == '__' and node.name[-2:] == '__':
                err(node, 'dunder function %s() (dunders cost frames)' % node.name)
            if getattr(node, 'type_params', None):
                err(node, 'type parameters (3.12+)')
        # -- hidden frames (section 17.4) ---------------------------------------------------
        if t in (ast.ListComp, ast.SetComp, ast.DictComp):
            err(node, 'comprehension (a hidden frame on the device): use a loop')
        elif t is ast.GeneratorExp:
            err(node, 'generator expression (a frame on the device): use a loop')
        elif t is ast.Lambda:
            err(node, 'lambda (a frame per call)')
        elif t is ast.With:
            err(node, 'with statement (hidden __enter__/__exit__ frames)')
        elif t is ast.YieldFrom:
            err(node, 'yield from (nests frames; use the trampoline)')
        elif t is ast.ClassDef:
            ok = (len(node.bases) == 1 and not node.keywords and not node.decorator_list)
            for s in node.body:
                if isinstance(s, ast.Pass):
                    continue
                if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and \
                        isinstance(s.value.value, str):
                    continue
                ok = False
            if not ok:
                err(node, 'class %s: only empty Exception subclasses (one base, body pass)'
                    % node.name)
        # -- calls -------------------------------------------------------------------------
        if t is ast.Call:
            f = node.func
            nstar = 0
            star_seen = False
            for i, a in enumerate(node.args):
                if isinstance(a, ast.Starred):
                    nstar += 1
                    star_seen = True
                elif star_seen:
                    err(node, 'positional argument after *args (3.5+)')
                    break
            if nstar > 1:
                err(node, 'more than one *args in a call (3.5+)')
            dstar = 0
            for i, k in enumerate(node.keywords):
                if k.arg is None:
                    dstar += 1
                    if i != len(node.keywords) - 1:
                        err(node, 'argument after **kwargs (3.5+)')
                elif k.arg == 'key':
                    err(node, 'key= argument (a frame per comparison on the device)')
            if dstar > 1:
                err(node, 'more than one **kwargs in a call (3.5+)')
            if isinstance(f, ast.Name):
                if f.id in ('map', 'filter'):
                    fa = node.args[0] if node.args else None
                    if not (isinstance(fa, ast.Name) and hasattr(builtins, fa.id)):
                        err(node, '%s() with a Python callable (a frame per item)' % f.id)
                elif f.id in ('round', 'repr') and not _marked(lines, node, '#@float-ok'):
                    err(node, '%s() differs on the device: use our own formatter '
                              '(or mark #@float-ok)' % f.id)
                elif f.id == 'print':
                    for k in node.keywords:
                        if k.arg in ('file', 'flush'):
                            err(node, 'print(%s=...) is unverified on the device' % k.arg)
                elif f.id in ('list', 'tuple', 'enumerate', 'zip', 'iter') and node.args \
                        and is_dictset(node.args[0], node) \
                        and not _marked(lines, node, '#@unordered-ok'):
                    err(node, '%s() over a dict or set: order is not portable '
                              '(sort it, or mark #@unordered-ok)' % f.id)
            elif isinstance(f, ast.Attribute):
                if f.attr in ('startswith', 'endswith') and node.args and \
                        isinstance(node.args[0], ast.Tuple):
                    err(node, '.%s() with a tuple is missing on the device' % f.attr)
                elif f.attr == 'rsplit' and node.args and \
                        isinstance(node.args[0], ast.Constant) and node.args[0].value is None:
                    err(node, '.rsplit(None, n) is missing on the device')
                elif f.attr == 'join' and node.args and is_dictset(node.args[0], node) \
                        and not _marked(lines, node, '#@unordered-ok'):
                    err(node, 'join() over a dict or set: order is not portable')
        # Standard MicroPython rejects non-unit slice steps (native smoke regression).
        if t is ast.Slice and node.step is not None and not (
                isinstance(node.step, ast.Constant) and node.step.value in (None, 1)):
            err(node, 'stepped slice is unsupported: use an explicit range loop')
        # -- iteration order ---------------------------------------------------------------
        if t is ast.For and is_dictset(node.iter, node) and \
                not _marked(lines, _Line(node.lineno), '#@unordered-ok'):
            err(node, 'iteration over a dict or set: order is not portable '
                      '(sort it, or mark #@unordered-ok)')
        # -- exactness and float output ----------------------------------------------------
        if exact and ((t is ast.BinOp and isinstance(node.op, ast.Div)) or
                      (t is ast.AugAssign and isinstance(node.op, ast.Div))) and \
                not _marked(lines, node, '#@float-ok'):
            err(node, "'/' in an exact module: use '//' or rationals (or mark #@float-ok)")
        if t is ast.BinOp and isinstance(node.op, ast.Mod) and \
                isinstance(node.left, ast.Constant) and isinstance(node.left.value, str) \
                and FLOAT_FMT.search(node.left.value) and \
                not _marked(lines, node, '#@float-ok'):
            err(node, 'float formatting (%e/%f/%g) differs on the device: use the decimal '
                      'formatter (or mark #@float-ok)')
        # -- imports -----------------------------------------------------------------------
        if t is ast.ImportFrom:
            err(node, "'from %s import ...' is banned in src: use 'import x as Y'"
                % (node.module or '.'))
        elif t is ast.Import:
            for a in node.names:
                m = a.name
                top = m.split('.')[0]
                if top in BANNED_MODULES:
                    err(node, 'module %r is not on the device' % m)
                    continue
                if top.startswith('ti_') and family(module) not in UI_MODULES:
                    err(node, '%s imports %s: only ui, draw, menu and casevo import ti_*'
                        % (module, m))
                if device_names:
                    if re.match(r'^[A-Z][A-Z0-9]{0,7}$', m) is None and \
                            top not in NATIVE_MODULES:
                        err(node, 'bad device module name %r' % m)
                    continue
                want = alias_for(m)
                if want is not None:
                    if a.asname != want:
                        err(node, "import %s as %s: the fixed alias is %s (DESIGN 4.1)"
                            % (m, a.asname or m, want))
                elif top not in NATIVE_MODULES:
                    err(node, 'unknown module %r: not in the module map (DESIGN 4.1)' % m)
        # -- names and attributes ----------------------------------------------------------
        if t is ast.Name and node.id in BANNED_NAMES:
            err(node, '%r is missing, unverified or banned on the device' % node.id)
        elif t is ast.Attribute:
            if node.attr in BANNED_ATTRS:
                err(node, '.%s is missing on the device' % node.attr)
            elif node.attr[:2] == '__' and node.attr[-2:] == '__' and \
                    node.attr not in DUNDER_ATTRS_OK:
                err(node, '.%s: dunder methods of builtins are not attributes on the device'
                    % node.attr)
            elif isinstance(node.value, ast.Name) and \
                    imported.get(node.value.id) == 'math' and node.attr not in MATH_OK:
                err(node, 'math.%s is not in the device math module' % node.attr)
        elif t is ast.Compare:
            sides = [node.left] + list(node.comparators)
            for s in sides:
                if isinstance(s, ast.Name) and s.id == '__name__':
                    err(node, "__name__ == '__main__' is never true on the device "
                              "(programs run as 'from NAME import *')")
                    break
    # -- generators: raise StopIteration ---------------------------------------------------
    for fn in gens:
        for n in ast.walk(fn):
            if isinstance(n, ast.Raise) and n.exc is not None:
                e = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
                if isinstance(e, ast.Name) and e.id == 'StopIteration':
                    err(n, 'raise StopIteration in a generator: CPython turns it into '
                           'RuntimeError; use return')
    # -- direct recursion ------------------------------------------------------------------
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and \
                        sub.func.id == fn.name:
                    err(sub, 'direct recursion in %s()' % fn.name)
    errs.sort(key=_errkey)
    return errs


class _Line(object):
    """A stand-in node carrying only a line number (for _marked on a single line)."""

    def __init__(self, lineno):
        self.lineno = lineno
        self.end_lineno = lineno


def _errkey(e):
    parts = e.split(':')
    try:
        return (parts[0], int(parts[1]), e)
    except (IndexError, ValueError):
        return (parts[0], 0, e)


def lint_file(path, device_names=False):
    with open(path, encoding='utf-8', errors='replace', newline='') as fh:
        src = fh.read()
    return lint(src.replace('\r\n', '\n'), path, device_names=device_names)


def device_files(d=SRC):
    """The .py files of a device dir, sorted."""
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith('.py'):
            out.append(os.path.join(d, name))
    return out


def lint_dir(d=SRC, device_names=False):
    errs = []
    for p in device_files(d):
        errs.extend(lint_file(p, device_names))
    return errs


def main(argv):
    paths = argv or device_files(SRC)
    bad = 0
    for p in paths:
        files = device_files(p) if os.path.isdir(p) else [p]
        for f in files:
            for e in lint_file(f):
                print(e)
                bad += 1
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
