"""cas-evo bundler, phase 1: strip and rename imports (DESIGN 19.2; task M0.4).

    python build/bundle.py [--src DIR] [--dist DIR] [--no-lint] [--test]
    python build/bundle.py --tables      # run.py's desktop DEV/PARTS/FAMILY/CLOSURE literals

1. Lint ``src/`` with the subset lint and FRAMELINT (tests/support). Any error stops the build.
2. Name checks: the manifest (``check_manifest``) and the src tree (every file has a manifest
   row, families are complete, nothing imports the entry module, no module name in a string).
3. Per module (``minify`` + ``rewrite_imports``): tokenize; drop comments, docstrings (every
   string-only statement) and the ``#@`` annotations; join continuation lines, so one device
   line is one logical line; 1-space indentation; drop blank lines; a block left empty gets a
   ``pass``; a multi-line string literal is re-encoded on one line; ``import x as Y`` becomes
   ``import DEV as Y``. In run.py the device tables ``DEV PARTS FAMILY CLOSURE COST LINES
   PEAKB FRAG`` are written from build/manifest.py (``CLOSURE`` from run.py's ``DEPS``), when
   run.py defines them as module-level literals.
4. Write ``dist/device/<DEV>.py`` (ASCII, LF; stale files are removed), ``dist/linemap.json``
   (device line -> source lines), ``dist/sizes.txt`` and ``dist/levels.json`` (FRAMELINT levels
   by device module, read by ``pytest --bundled``).
5. Check: line budgets and ``LAZYMAX``; ``compile()``; the subset lint on the output (its
   ``#@float-ok``/``#@unordered-ok`` markers are looked up in the source through the line map);
   if mpy-cross is found (``pip install mpy-cross``, or ``MPY_CROSS=path``), ``.mpy bytes x
   FACTOR`` against the KB budget, else a warning.
6. ``--test`` runs ``pytest --bundled``.

Phase 2 (renaming module-level names, DESIGN 18.8 step 2) belongs to B.1. See
docs/notes/M0.4.md.
"""
import argparse
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
DIST = os.path.join(ROOT, 'dist')
SUPPORT = os.path.join(ROOT, 'tests', 'support')
MANIFEST = os.path.join(HERE, 'manifest.py')

DEVNAME = re.compile(r'^[A-Z][A-Z0-9]{0,7}$')     # device module names [V]
MODNAME = re.compile(r'^CV[A-Z0-9]{1,6}$')          # our modules: CV plus up to 6 (DESIGN 0.6)
SRCNAME = re.compile(r'^[a-z][a-z0-9_]*$')
CLASSES = ('R', 'L', 'U')
# run.py tables the bundler writes (DESIGN 18.4, 19.1)
TABLES = ('DEV', 'PARTS', 'FAMILY', 'CLOSURE', 'COST', 'LINES', 'PEAKB', 'FRAG')
# output-lint messages that a source marker silences: (marker, message fragment)
MARKERS = (('#@float-ok', '#@float-ok'), ('#@unordered-ok', 'order is not portable'))
REQUIRED = ('ENTRY', 'MODULES', 'KEYS', 'PARTS', 'FAMILY', 'FACTOR', 'PEAKB', 'LAZYMAX', 'FRAG',
            'MPYB')

_SIG = (tokenize.NAME, tokenize.NUMBER, tokenize.STRING, tokenize.OP)
_WORD = (tokenize.NAME, tokenize.NUMBER, tokenize.STRING)
_DEFAULT = object()


class BundleError(Exception):
    pass


def _support():
    """tests/support/lint.py and framelint.py (the src checks of DESIGN 20.3)."""
    if SUPPORT not in sys.path:
        sys.path.insert(0, SUPPORT)
    import framelint
    import lint
    return lint, framelint


# -- the manifest ------------------------------------------------------------------------------

class Manifest(object):
    """build/manifest.py as an object: its upper-case names, plus lookups."""

    def __init__(self, ns):
        for k in ns:
            if k[:1].isupper():
                setattr(self, k, ns[k])

    def rows(self):
        """{src: (src, device, class, max lines, KB budget)}"""
        out = {}
        for r in self.MODULES:
            out[r[0]] = r
        return out

    def key_of(self, src):
        """The runtime key of a src module ('integ' -> 'int')."""
        for k in self.KEYS:
            if self.KEYS[k] == src:
                return k
        return src

    def src_of(self, key):
        return self.KEYS.get(key, key)

    def family_of(self, key):
        return self.FAMILY.get(key, key)

    def parts_of(self, fam):
        return tuple(self.PARTS.get(fam, (fam,)))


def load_manifest(path=MANIFEST):
    ns = {}
    with open(path, encoding='utf-8') as fh:
        exec(compile(fh.read(), path, 'exec'), ns)
    return Manifest(ns)


def _posnum(v, integer=False):
    if isinstance(v, bool):
        return False
    if integer:
        return isinstance(v, int) and v > 0
    return isinstance(v, (int, float)) and v > 0


def check_manifest(man):
    """Name and consistency checks of a Manifest. Returns error strings."""
    lint, framelint = _support()
    missing = [n for n in REQUIRED if not hasattr(man, n)]
    if missing:
        return ['build/manifest.py: missing %s' % ', '.join(missing)]
    errs = []
    srcs = {}
    devs = {}
    E = man.ENTRY
    if not (isinstance(E, tuple) and len(E) == 2 and isinstance(E[0], str) and
            isinstance(E[1], str)):
        errs.append('ENTRY must be (src, device), not %r' % (E,))
    else:
        if not DEVNAME.match(E[1]):
            errs.append('bad device name %r for the entry (want [A-Z][A-Z0-9]{0,7})' % E[1])
        srcs[E[0]] = 'ENTRY'
        devs[E[1]] = E[0]
    eb = getattr(man, 'ENTRY_BUDGET', (1, 1))
    if not (isinstance(eb, tuple) and len(eb) == 2 and _posnum(eb[0], True) and
            _posnum(eb[1])):
        errs.append('ENTRY_BUDGET must be (max lines, KB budget), not %r' % (eb,))
    rows = {}
    for r in man.MODULES:
        if not (isinstance(r, tuple) and len(r) == 5 and isinstance(r[0], str) and
                isinstance(r[1], str)):
            errs.append('bad MODULES row %r: want (src, device, class, max lines, KB budget)'
                        % (r,))
            continue
        src, dev, cls, mx, kb = r
        if src in srcs:
            errs.append('duplicate src module %r' % src)
        if dev in devs:
            errs.append('duplicate device name %r (%s and %s)' % (dev, devs[dev], src))
        srcs[src] = dev
        devs[dev] = src
        rows[src] = r
        if not DEVNAME.match(dev):
            errs.append('bad device name %r for %s (want [A-Z][A-Z0-9]{0,7})' % (dev, src))
        elif not MODNAME.match(dev):
            errs.append('device name %r of %s: modules are CV plus up to 6 letters or digits '
                        '(DESIGN 0.6)' % (dev, src))
        if not SRCNAME.match(src):
            errs.append('bad src module name %r' % src)
        if src in lint.NATIVE_MODULES or src in lint.BANNED_MODULES:
            errs.append('src module %r shadows a native module' % src)
        if cls not in CLASSES:
            errs.append('class %r of %s: want one of %s' % (cls, src, ', '.join(CLASSES)))
        if not _posnum(mx, True) or not _posnum(kb):
            errs.append('the line and KB budgets of %s must be positive (%r, %r)'
                        % (src, mx, kb))
        if lint.alias_for(src) is None:
            errs.append('%s is not in the module map (tests/support/lint.py ALIASES, '
                        'DESIGN 4.1)' % src)
        elif cls in CLASSES:
            resident = lint.family(src) in lint.RESIDENT
            if (cls == 'R') != resident:
                errs.append('%s is class %s, but the lint map (tests/support/lint.py RESIDENT) '
                            'says %s' % (src, cls, 'resident' if resident else 'lazy'))
    for mod in sorted(lint.ALIASES):
        if mod not in rows:
            errs.append('module map entry %s (tests/support/lint.py ALIASES) has no manifest '
                        'row' % mod)
    if not isinstance(man.KEYS, dict) or not isinstance(man.PARTS, dict) or \
            not isinstance(man.FAMILY, dict):
        errs.append('KEYS, PARTS and FAMILY must be dicts')
        return errs
    if man.KEYS != framelint.KEYS:
        errs.append('KEYS differ from tests/support/framelint.py KEYS: keep them equal')
    for k in sorted(man.KEYS):
        if man.KEYS[k] not in rows:
            errs.append('KEYS[%r] = %r is not a module' % (k, man.KEYS[k]))
    keys = {}
    for src in sorted(rows):
        k = man.key_of(src)
        if k in keys:
            errs.append('runtime key %r is used by both %s and %s' % (k, keys[k], src))
        keys[k] = src
    seen = {}
    for fam in sorted(man.PARTS):
        parts = man.PARTS[fam]
        if not isinstance(parts, tuple) or not parts:
            errs.append('PARTS[%r] must be a non-empty tuple' % fam)
            continue
        if parts[0] != fam:
            errs.append('PARTS[%r] must start with the family key' % fam)
        for p in parts:
            s = man.src_of(p)
            if s not in rows:
                errs.append('PARTS[%r]: %r is not a module' % (fam, p))
            elif rows[s][2] == 'R':
                errs.append('PARTS[%r]: %s is resident' % (fam, s))
            elif rows[s][2] != rows.get(man.src_of(fam), rows[s])[2]:
                errs.append('PARTS[%r]: %s is class %s, unlike its family' % (fam, s, rows[s][2]))
            if p in seen:
                errs.append('part %r is in two families (%s and %s)' % (p, seen[p], fam))
            seen[p] = fam
    want = {}
    for fam in man.PARTS:
        for p in tuple(man.PARTS[fam])[1:]:
            want[p] = fam
    if man.FAMILY != want:
        errs.append('FAMILY does not match PARTS: it must be %r' % (dict(sorted(want.items())),))
    for src in sorted(rows):
        if rows[src][2] == 'R':
            continue
        logical = lint.family(src)
        if logical != src:
            lk = man.key_of(logical)
            if lk in man.PARTS and man.key_of(src) not in man.PARTS[lk]:
                errs.append('%s is a part of %s but in no family of PARTS (DESIGN 4.3)'
                            % (src, logical))
    for n in ('FACTOR', 'PEAKB', 'MPYB'):
        if not _posnum(getattr(man, n)):
            errs.append('%s must be a positive number' % n)
    if not _posnum(man.LAZYMAX, True):
        errs.append('LAZYMAX must be a positive int')
    if not (isinstance(man.FRAG, int) and not isinstance(man.FRAG, bool) and man.FRAG >= 0):
        errs.append('FRAG must be an int >= 0')
    return errs


def families(man):
    """Every lazy family key, in manifest order (one-part families included)."""
    out = []
    for r in man.MODULES:
        if r[2] == 'R':
            continue
        f = man.family_of(man.key_of(r[0]))
        if f not in out:
            out.append(f)
    return tuple(out)


def closure(deps, fams, family):
    """{family: leaf-first tuple of families, ending with the family} (DESIGN 18.4).

    deps: run.py's DEPS (family key -> keys it needs); fams: every family key; family: part
    key -> family key. A part key in DEPS stands for its family.
    """
    def fam_of(k):
        return family.get(k, k)

    norm = {}
    for k in sorted(deps):
        f = fam_of(k)
        if f not in fams:
            raise BundleError('DEPS: unknown family %r' % k)
        ds = []
        for d in deps[k]:
            fd = fam_of(d)
            if fd not in fams:
                raise BundleError('DEPS[%r]: unknown family %r' % (k, d))
            if fd not in ds:
                ds.append(fd)
        norm[f] = tuple(ds)
    out = {}
    for fam in fams:
        order = []
        state = {fam: 1}                  # 1: on the path, 2: done
        stack = [(fam, 0)]
        while stack:
            node, i = stack[-1]
            ds = norm.get(node, ())
            if i < len(ds):
                stack[-1] = (node, i + 1)
                d = ds[i]
                s = state.get(d, 0)
                if s == 1:
                    path = [n for n, _ in stack] + [d]
                    raise BundleError('DEPS cycle: %s' % ' -> '.join(path[path.index(d):]))
                if s == 0:
                    state[d] = 1
                    stack.append((d, 0))
            else:
                state[node] = 2
                order.append(node)
                stack.pop()
        out[fam] = tuple(order)
    return out


# -- the minifier ------------------------------------------------------------------------------

class Line(object):
    """One device line: a logical source line, its depth and source span."""

    def __init__(self, depth, toks, span, header=False):
        self.depth = depth
        self.toks = toks                 # [(token type, string)], significant tokens only
        self.span = span                 # (first, last) source line
        self.header = header             # opens an indented block

    def render(self):
        return ' ' * self.depth + _join(self.toks)


class Minified(object):
    """A minified module: ``lines`` (device lines), ``spans`` ((first, last) source line of
    each device line), ``text`` (LF-terminated)."""

    def __init__(self, name, items):
        self.name = name
        self.items = items

    @property
    def lines(self):
        return [it.render() for it in self.items]

    @property
    def spans(self):
        return [it.span for it in self.items]

    @property
    def text(self):
        ls = self.lines
        return '\n'.join(ls) + '\n' if ls else ''


def _space(a, b):
    if a[0] in _WORD and b[0] in _WORD:
        return True
    return a[0] == tokenize.NUMBER and b[1][:1] == '.'


def _sig(text):
    """The significant tokens of one line of code, or None if it does not tokenize."""
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text + '\n').readline):
            if tok.type in _SIG:
                out.append((tok.type, tok.string))
            elif tok.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER,
                                  tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT):
                return None
    except (tokenize.TokenError, SyntaxError):
        return None
    return out


def _join(toks):
    """Tokens -> the shortest text that tokenizes back to the same tokens."""
    out = []
    prev = None
    for t in toks:
        if prev is not None and _space(prev, t):
            out.append(' ')
        out.append(t[1])
        prev = t
    s = ''.join(out)
    if _sig(s) != list(toks):
        s = ' '.join(t[1] for t in toks)            # safety net for an unforeseen merge
    return s


def _is_fstring(tt):
    nm = tokenize.tok_name.get(tt, '')
    return nm.startswith('FSTRING') or nm.startswith('TSTRING')


def _logical(text, name):
    """Logical lines of a module: [Line] (comments, blank lines and NL tokens dropped)."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if text and not text.endswith('\n'):
        text += '\n'
    try:
        ast.parse(text, name)
    except SyntaxError as e:
        raise BundleError('%s:%s: syntax error: %s' % (name, e.lineno, e.msg))
    items = []
    depth = 0
    cur = []
    start = end = 0
    at = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            tt = tok.type
            if tt == tokenize.INDENT:
                depth += 1
                if items:
                    items[-1].header = True
                continue
            if tt == tokenize.DEDENT:
                depth -= 1
                continue
            if tt in (tokenize.COMMENT, tokenize.NL, tokenize.ENDMARKER):
                continue
            if tt == tokenize.NEWLINE:
                if cur:
                    items.append(Line(at, cur, (start, end)))
                    cur = []
                continue
            if _is_fstring(tt):
                raise BundleError('%s:%d: f-strings are not device Python'
                                  % (name, tok.start[0]))
            if tt not in _SIG:
                raise BundleError('%s:%d: unexpected token %r' % (name, tok.start[0],
                                                                  tok.string))
            s = tok.string
            if tt == tokenize.STRING and '\n' in s:
                s = ascii(ast.literal_eval(s))     # one device line per logical line
            if not cur:
                start = tok.start[0]
                at = depth
            cur.append((tt, s))
            end = tok.end[0]
    except (tokenize.TokenError, SyntaxError) as e:
        raise BundleError('%s: does not tokenize: %s' % (name, e))
    if cur:
        items.append(Line(at, cur, (start, end)))
    return items


def _fill_empty_blocks(items):
    """A block whose statements were all dropped gets a pass (mapped to its header)."""
    out = []
    for i, it in enumerate(items):
        out.append(it)
        if it.header:
            nxt = items[i + 1] if i + 1 < len(items) else None
            if nxt is None or nxt.depth <= it.depth:
                out.append(Line(it.depth + 1, [(tokenize.NAME, 'pass')], it.span))
    return out


def minify(text, name='<src>'):
    """Strip one module: comments, docstrings (every string-only statement), annotations,
    blank lines; one device line per logical line; 1-space indentation. Returns a Minified.
    Raises BundleError on a syntax error or an f-string."""
    items = []
    for it in _logical(text, name):
        only_strings = True
        for t in it.toks:
            if t[0] != tokenize.STRING:
                only_strings = False
                break
        if not only_strings:
            items.append(it)
    return Minified(name, _fill_empty_blocks(items))


# -- import rewriting --------------------------------------------------------------------------

def _split(toks, sep):
    out = [[]]
    for t in toks:
        if t == sep:
            out.append([])
        else:
            out[-1].append(t)
    return out


def _rewrite_stmt(toks, names, entry, errs):
    if toks and toks[0] == (tokenize.NAME, 'import'):
        out = [toks[0]]
        groups = _split(toks[1:], (tokenize.OP, ','))
        for gi, g in enumerate(groups):
            if gi:
                out.append((tokenize.OP, ','))
            k = g.index((tokenize.NAME, 'as')) if (tokenize.NAME, 'as') in g else len(g)
            mod = ''.join(t[1] for t in g[:k])
            top = mod.split('.')[0]
            if entry is not None and top == entry:
                errs.append('imports the entry module %s (no module may import it)' % entry)
                out.extend(g)
            elif mod in names:
                out.append((tokenize.NAME, names[mod]))
                if k < len(g):
                    out.extend(g[k:])
                else:
                    out.extend([(tokenize.NAME, 'as'), (tokenize.NAME, mod)])
            elif top in names:
                errs.append('dotted import of src module %s' % mod)
                out.extend(g)
            else:
                out.extend(g)
        toks = out
    elif toks and toks[0] == (tokenize.NAME, 'from'):
        k = toks.index((tokenize.NAME, 'import')) if (tokenize.NAME, 'import') in toks else 1
        mod = ''.join(t[1] for t in toks[1:k])
        top = mod.split('.')[0]
        if top in names or (entry is not None and top == entry):
            errs.append("'from %s import ...': use 'import %s as Y' (DESIGN 4.2)" % (mod, mod))
    for i in range(len(toks) - 2):
        a, b, c = toks[i], toks[i + 1], toks[i + 2]
        if c[0] != tokenize.STRING or not ((a == (tokenize.NAME, '__import__') and
                                            b == (tokenize.OP, '(')) or
                                           (a == (tokenize.NAME, 'modules') and
                                            b == (tokenize.OP, '['))):
            continue
        try:
            v = ast.literal_eval(c[1])
        except (ValueError, SyntaxError):
            continue
        if v in names or v == entry:
            errs.append('module name %r in a string: take device names from the DEV table '
                        '(device-python 11)' % v)
    return toks


def rewrite_imports(m, names, entry=None):
    """Rewrite every import statement of a Minified in place: ``import node as K`` ->
    ``import CVNODE as K``, ``import node`` -> ``import CVNODE as node``. names: src module
    -> device name. Returns error strings ('name:line: message')."""
    errs = []
    for it in m.items:
        stmts = _split(it.toks, (tokenize.OP, ';'))
        new = []
        for si, st in enumerate(stmts):
            e = []
            st = _rewrite_stmt(st, names, entry, e)
            for msg in e:
                errs.append('%s:%d: %s' % (m.name, it.span[0], msg))
            if si:
                new.append((tokenize.OP, ';'))
            new.extend(st)
        it.toks = new
    return errs


# -- run.py tables -----------------------------------------------------------------------------

_NOLIT = object()


def _lit(v):
    """A deterministic, compact literal (sorted dict keys)."""
    if isinstance(v, dict):
        return '{' + ','.join(_lit(k) + ':' + _lit(v[k]) for k in sorted(v)) + '}'
    if isinstance(v, tuple):
        return '(' + ','.join(_lit(x) for x in v) + (',' if len(v) == 1 else '') + ')'
    if isinstance(v, list):
        return '[' + ','.join(_lit(x) for x in v) + ']'
    if isinstance(v, str):
        return ascii(v)
    if v is None or isinstance(v, (bool, int, float)):
        return repr(v)
    raise BundleError('cannot write %r as a device literal' % (v,))


def _same(a, b):
    """Equal values, a list standing for a tuple."""
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return tuple(a) == tuple(b)
    return a == b


def find_tables(m, wanted):
    """{name: (item index, value or _NOLIT)} for module-level ``NAME = literal`` lines."""
    out = {}
    dup = []
    for i, it in enumerate(m.items):
        t = it.toks
        if it.depth == 0 and len(t) >= 3 and t[0][0] == tokenize.NAME and \
                t[0][1] in wanted and t[1] == (tokenize.OP, '='):
            try:
                v = ast.literal_eval(_join(t[2:]))
            except (ValueError, SyntaxError, TypeError):
                v = _NOLIT
            if t[0][1] in out:
                dup.append(t[0][1])
            out[t[0][1]] = (i, v)
    return out, dup


def set_table(m, i, name, value):
    m.items[i].toks = _sig('%s=%s' % (name, _lit(value)))


def run_tables(m, man, present, lines, mpy):
    """Write the device tables into run.py's Minified. present: bundled src modules; lines
    and mpy: {src: device lines / .mpy bytes or None}. Returns error strings."""
    errs = []
    found, dup = find_tables(m, TABLES + ('DEPS',))
    for n in dup:
        errs.append('run.py assigns %s more than once at module level' % n)
    for n in sorted(found):
        if found[n][1] is _NOLIT:
            errs.append('run.py %s is not a literal: the bundler cannot check or rewrite it'
                        % n)
    if errs:
        return errs
    rows = man.rows()
    lazy = [s for s in present if s in rows and rows[s][2] != 'R' and s in lines]
    fams = []
    for s in lazy:
        f = man.family_of(man.key_of(s))
        if f not in fams:
            fams.append(f)
    full = {'PARTS': dict(man.PARTS), 'FAMILY': dict(man.FAMILY)}
    if 'DEPS' in found:
        try:
            full['CLOSURE'] = closure(found['DEPS'][1], families(man), man.FAMILY)
        except BundleError as e:
            errs.append('run.py %s' % e)
    elif 'CLOSURE' in found:
        errs.append('run.py defines CLOSURE but no literal DEPS to derive it from')
    for n in ('PARTS', 'FAMILY', 'CLOSURE'):
        if n not in found or n not in full:
            continue
        have = found[n][1]
        if not isinstance(have, dict):
            errs.append('run.py %s must be a dict' % n)
            continue
        for k in sorted(have):
            if k not in full[n]:
                errs.append('run.py %s has key %r, which build/manifest.py does not know'
                            % (n, k))
            elif not _same(have[k], full[n][k]):
                errs.append('run.py %s[%r] = %r, but build/manifest.py says %r'
                            % (n, k, have[k], full[n][k]))
    want = {}
    want['PARTS'] = dict((f, man.PARTS[f]) for f in fams if f in man.PARTS)
    want['FAMILY'] = dict((p, f) for p, f in man.FAMILY.items() if f in fams)
    if 'CLOSURE' in full:
        cl = {}
        for f in fams:
            c = full['CLOSURE'][f]
            for g in c:
                if g not in fams:
                    errs.append('CLOSURE[%r] needs family %r, which is not in the bundle'
                                % (f, g))
            cl[f] = c
        want['CLOSURE'] = cl
    want['LINES'] = dict((man.key_of(s), lines[s]) for s in lazy)
    cost = {}
    for s in lazy:
        if mpy.get(s):
            cost[man.key_of(s)] = int(mpy[s] * man.FACTOR)
        else:
            cost[man.key_of(s)] = int(lines[s] * man.MPYB * man.FACTOR)
    want['COST'] = cost
    want['PEAKB'] = man.PEAKB
    want['FRAG'] = man.FRAG
    if 'DEV' in found:
        have = found['DEV'][1]
        dev = {}
        if not isinstance(have, dict):
            errs.append('run.py DEV must be a dict')
            have = {}
        for k in sorted(have):
            v = have[k]
            if v not in rows:
                errs.append('run.py DEV[%r] = %r is not a module of build/manifest.py' % (k, v))
            elif man.key_of(v) != k:
                errs.append('run.py DEV[%r] = %r, but the runtime key of %s is %r '
                            '(build/manifest.py KEYS)' % (k, v, v, man.key_of(v)))
            else:
                dev[k] = rows[v][1]
        for s in lazy:
            if man.key_of(s) not in have:
                errs.append('run.py DEV has no key %r for the lazy module %s'
                            % (man.key_of(s), s))
        want['DEV'] = dev
    for n in TABLES:
        if n in found and n in want:
            set_table(m, found[n][0], n, want[n])
    return errs


def desktop_tables(man, deps=None):
    """The desktop values of run.py's loader tables, from the manifest: DEV (runtime key ->
    src module, every lazy module), PARTS, FAMILY and, given DEPS, CLOSURE. The bundler
    checks run.py's literals against these and writes the device values."""
    rows = man.rows()
    dev = {}
    for s in rows:
        if rows[s][2] != 'R':
            dev[man.key_of(s)] = s
    out = {'DEV': dev, 'PARTS': dict(man.PARTS), 'FAMILY': dict(man.FAMILY)}
    if deps is not None:
        out['CLOSURE'] = closure(deps, families(man), man.FAMILY)
    return out


def _src_deps(src):
    """run.py's literal DEPS, or None."""
    p = os.path.join(src, 'run.py')
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8', errors='replace') as fh:
        m = minify(fh.read(), _rel(p))
    found = find_tables(m, ('DEPS',))[0]
    if 'DEPS' not in found or found['DEPS'][1] is _NOLIT:
        return None
    return found['DEPS'][1]


# -- sizes -------------------------------------------------------------------------------------

def _mpy_cmd():
    env = os.environ.get('MPY_CROSS')
    if env is not None:
        return [env] if env and os.path.isfile(env) else None
    if importlib.util.find_spec('mpy_cross') is not None:
        return [sys.executable, '-m', 'mpy_cross']
    exe = shutil.which('mpy-cross')
    return [exe] if exe else None


def mpy_sizer():
    """A function path -> .mpy bytes using mpy-cross, or None if mpy-cross is not found
    (the environment variable MPY_CROSS, then the mpy_cross package, then PATH)."""
    cmd = _mpy_cmd()
    if cmd is None:
        return None

    def size(path):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, 'm.mpy')
            p = subprocess.run(cmd + ['-o', out, '-s', os.path.basename(path), path],
                               capture_output=True, text=True, timeout=120)
            if p.returncode != 0 or not os.path.exists(out):
                raise BundleError('mpy-cross failed on %s: %s'
                                  % (path, (p.stderr or p.stdout).strip()))
            return os.path.getsize(out)
    size.cmd = cmd
    return size


# -- the bundle --------------------------------------------------------------------------------

class Result(object):
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.files = []          # written device files
        self.lines = {}          # device name -> device lines
        self.mpy = {}            # device name -> .mpy bytes (None without mpy-cross)
        self.sizes = ''          # the dist/sizes.txt text


def _rel(p):
    p = os.path.abspath(p)
    try:
        r = os.path.relpath(p, ROOT)
    except ValueError:
        r = p
    if r.startswith('..'):
        r = p
    return r.replace(os.sep, '/')


def _marked(src_lines, span, marker):
    for i in range(span[0], span[1] + 1):
        if 0 < i <= len(src_lines) and marker in src_lines[i - 1]:
            return True
    return False


def _write(path, text):
    with open(path, 'w', encoding='ascii', newline='\n') as fh:
        fh.write(text)


def bundle(src=SRC, dist=DIST, man=None, lint=True, sizer=_DEFAULT):
    """Bundle src/ into dist/ (DESIGN 19.2, phase 1). Returns a Result; nothing raises.

    man: a Manifest (default build/manifest.py); lint: run the src lint and FRAMELINT first;
    sizer: path -> .mpy bytes, None to skip the size gate, default mpy-cross if found.
    """
    res = Result()
    if man is None:
        man = load_manifest()
    lintmod, framelint = _support()
    res.errors = check_manifest(man)
    if res.errors:
        return res
    an = framelint.analyze_dir(src)
    if lint:
        res.errors = lintmod.lint_dir(src) + an.errors
        if res.errors:
            return res
    if sizer is _DEFAULT:
        sizer = mpy_sizer()
    if sizer is None:
        res.warnings.append('mpy-cross not found (pip install mpy-cross into the venv, or set '
                            'MPY_CROSS): the size gate is skipped')
    rows = man.rows()
    esrc, edev = man.ENTRY
    names = {}
    for s in rows:
        names[s] = rows[s][1]
    budget = {esrc: (edev, 'E') + tuple(getattr(man, 'ENTRY_BUDGET', (30, 1)))}
    for s in rows:
        budget[s] = (rows[s][1], rows[s][2], rows[s][3], rows[s][4])
    present = {}
    for p in lintmod.device_files(src):
        nm = os.path.splitext(os.path.basename(p))[0]
        if nm in budget:
            present[nm] = p
        else:
            res.errors.append('%s: %s is not in build/manifest.py' % (_rel(p), nm))
    if not present:
        res.warnings.append('no src files in %s' % _rel(src))
    done = set()
    for s in sorted(present):
        if s == esrc or rows[s][2] == 'R':
            continue
        fam = man.family_of(man.key_of(s))
        if fam in done:
            continue
        done.add(fam)
        for p in man.parts_of(fam):
            ps = man.src_of(p)
            if ps not in present:
                res.errors.append('family %s is incomplete: %s (%s.py) has no src file'
                                  % (fam, ps, ps))
    # minify and rename imports
    mins = {}
    srclines = {}
    for s in sorted(present):
        with open(present[s], encoding='utf-8', errors='replace', newline='') as fh:
            text = fh.read().replace('\r\n', '\n')
        srclines[s] = text.split('\n')
        try:
            m = minify(text, _rel(present[s]))
        except BundleError as e:
            res.errors.append(str(e))
            continue
        res.errors.extend(rewrite_imports(m, names, esrc))
        mins[s] = m
    # write: every module but run, then run with its tables
    dev_dir = os.path.join(dist, 'device')
    os.makedirs(dev_dir, exist_ok=True)
    for fn in sorted(os.listdir(dev_dir)):
        if fn.endswith('.py') or fn.endswith('.mpy'):
            os.remove(os.path.join(dev_dir, fn))
    lines = {}
    mpy = {}
    order = [s for s in sorted(mins) if s != 'run'] + (['run'] if 'run' in mins else [])
    for s in order:
        m = mins[s]
        if s == 'run':
            res.errors.extend(run_tables(m, man, sorted(mins), lines, mpy))
            if 'DEV' not in find_tables(m, ('DEV',))[0] and any(
                    t != 'run' and t in rows and rows[t][2] != 'R' for t in mins):
                res.warnings.append('run.py has no literal DEV table: the device cannot load '
                                    'the lazy modules by their device names')
        dev = budget[s][0]
        path = os.path.join(dev_dir, dev + '.py')
        text = m.text
        try:
            _write(path, text)
        except UnicodeEncodeError as e:
            res.errors.append('%s: non-ASCII output: %s' % (dev, e))
            continue
        res.files.append(path)
        lines[s] = len(m.items)
        res.lines[dev] = lines[s]
        mpy[s] = None
        if sizer is not None:
            try:
                mpy[s] = sizer(path)
            except BundleError as e:
                res.errors.append(str(e))
        res.mpy[dev] = mpy[s]
        res.errors.extend(_check_output(s, m, text, path, budget[s], man, srclines[s],
                                        lintmod, mpy[s]))
    # side files
    lm = {}
    lv = {}
    levels = an.levels()
    for s in order:
        dev = budget[s][0]
        lm[dev] = {'src': _rel(present[s]), 'lines': [list(sp) for sp in mins[s].spans]}
        lv[dev] = levels.get(s, {})
    with open(os.path.join(dist, 'linemap.json'), 'w', encoding='ascii', newline='\n') as fh:
        json.dump(lm, fh, indent=0, sort_keys=True)
        fh.write('\n')
    with open(os.path.join(dist, 'levels.json'), 'w', encoding='ascii', newline='\n') as fh:
        json.dump(lv, fh, indent=1, sort_keys=True)
        fh.write('\n')
    res.sizes = _sizes(order, budget, mins, srclines, mpy, man, sizer, dev_dir)
    _write(os.path.join(dist, 'sizes.txt'), res.sizes)
    return res


def _check_output(s, m, text, path, bud, man, src_lines, lintmod, mpy_bytes):
    errs = []
    dev, cls, mx, kb = bud
    n = len(m.items)
    if n > mx:
        errs.append('%s: %d lines > line budget %d (build/manifest.py)' % (dev, n, mx))
    if cls in ('L', 'U') and n > man.LAZYMAX:
        errs.append('%s: %d lines > LAZYMAX %d: a lazy part must be split (DESIGN 4.3)'
                    % (dev, n, man.LAZYMAX))
    try:
        compile(text, path, 'exec')
    except SyntaxError as e:
        errs.append('%s:%s: the output does not compile: %s' % (_rel(path), e.lineno, e.msg))
        return errs
    for e in lintmod.lint(text, dev + '.py', module=s, device_names=True):
        mo = re.match(r'^(.*?):(\d+): (.*)$', e)
        if mo is None:
            errs.append('%s: output lint: %s' % (dev, e))
            continue
        ln = int(mo.group(2))
        msg = mo.group(3)
        span = m.items[ln - 1].span if 0 < ln <= len(m.items) else (0, 0)
        hush = False
        for marker, frag in MARKERS:
            if frag in msg and _marked(src_lines, span, marker):
                hush = True
        if not hush:
            errs.append('%s:%d (%s:%d): output lint: %s' % (_rel(path), ln, m.name, span[0],
                                                             msg))
    if mpy_bytes is not None:
        est = mpy_bytes * man.FACTOR
        if est > kb * 1024:
            errs.append('%s: .mpy %d B x FACTOR %s = %.1f KB > KB budget %s (build/manifest.py)'
                        % (dev, mpy_bytes, man.FACTOR, est / 1024.0, kb))
    return errs


def _sizes(order, budget, mins, srclines, mpy, man, sizer, dev_dir):
    cmd = getattr(sizer, 'cmd', None)
    tool = ' '.join(cmd) if cmd else ('custom' if sizer is not None else 'not found')
    out = ['# cas-evo bundle sizes (DESIGN 19.2). FACTOR %s, MPYB %s, LAZYMAX %d, mpy-cross: %s'
           % (man.FACTOR, man.MPYB, man.LAZYMAX, tool),
           '# est KB = .mpy bytes x FACTOR, or lines x MPYB x FACTOR without mpy-cross (~)',
           '%-9s %-9s %-5s %5s %5s %6s %7s %6s %7s %5s  %s'
           % ('device', 'src', 'class', 'lines', 'max', 'srcln', 'py B', 'mpy B', 'est KB',
              'KB', 'status')]
    tot = {}
    for s in order:
        dev, cls, mx, kb = budget[s]
        n = len(mins[s].items)
        with open(os.path.join(dev_dir, dev + '.py'), 'rb') as fh:
            pyb = len(fh.read())
        b = mpy.get(s)
        est = (b * man.FACTOR if b else n * man.MPYB * man.FACTOR) / 1024.0
        status = []
        if n > mx:
            status.append('LINES')
        if cls in ('L', 'U') and n > man.LAZYMAX:
            status.append('LAZYMAX')
        if b and est > kb:
            status.append('KB')
        out.append('%-9s %-9s %-5s %5d %5d %6d %7d %6s %6.1f%s %5s  %s'
                   % (dev, s, cls, n, mx, len(srclines[s]), pyb, b if b else '-', est,
                      ' ' if b else '~', kb, ' '.join(status) or 'ok'))
        t = tot.setdefault(cls, [0, 0.0])
        t[0] += n
        t[1] += est
    for cls in ('E', 'R', 'L', 'U'):
        if cls in tot:
            out.append('# total class %s: %d lines, est %.1f KB' % (cls, tot[cls][0],
                                                                    tot[cls][1]))
    return '\n'.join(out) + '\n'


# -- command line ------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description='Bundle src/ into dist/device (DESIGN 19.2).')
    ap.add_argument('--src', default=SRC, help='source dir (default src/)')
    ap.add_argument('--dist', default=DIST, help='output dir (default dist/)')
    ap.add_argument('--no-lint', action='store_true', help='skip the src lint and FRAMELINT')
    ap.add_argument('--test', action='store_true', help='then run pytest --bundled')
    ap.add_argument('--tables', action='store_true',
                    help="print run.py's desktop loader tables (CLOSURE from src/run.py DEPS) "
                         'and exit')
    a = ap.parse_args(argv)
    if a.tables:
        import pprint
        try:
            t = desktop_tables(load_manifest(), _src_deps(a.src))
        except BundleError as e:
            print('error: %s' % e)
            return 1
        for n in ('DEV', 'PARTS', 'FAMILY', 'CLOSURE'):
            if n in t:
                print('%s = %s' % (n, pprint.pformat(t[n], width=96)))
        return 0
    res = bundle(a.src, a.dist, lint=not a.no_lint)
    for w in res.warnings:
        print('warning: ' + w)
    if res.sizes:
        print(res.sizes, end='')
    for e in res.errors:
        print('error: ' + e)
    if res.errors:
        print('bundle FAILED: %d error(s)' % len(res.errors))
        return 1
    print('bundle ok: %d modules -> %s' % (len(res.files),
                                           _rel(os.path.join(a.dist, 'device'))))
    if a.test:
        if os.path.abspath(a.dist) != os.path.abspath(DIST):
            print('warning: pytest --bundled reads dist/, not %s' % a.dist)
        return subprocess.call([sys.executable, '-m', 'pytest', '-q', '--bundled'], cwd=ROOT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
