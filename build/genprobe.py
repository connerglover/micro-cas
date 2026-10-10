"""M0.5 memory gate (DESIGN 18.7): the PRBL probe modules and the calibration of the memory model.

    python build/genprobe.py                 write probe/PRBL100.py, PRBL200.py, PRBL300.py
    python build/genprobe.py --check         exit 1 if those files are stale
    python build/genprobe.py --stats         shape statistics (and .mpy bytes if mpy-cross is found)
    python build/genprobe.py --derive FILE   the gate: a PRBMEM transcript -> the manifest values

**The probe modules.** ``generate(n)`` writes exactly ``n`` minified lines of code shaped like
ours: the prototype's functions (pair loops over flat node tuples, ``if`` chains on op codes,
explicit-stack loops, dense integer lists, a generator strategy, printer string building) and
tuple and string tables. The source goes through the M0.4 minifier (``bundle.minify``), so a
"line" is a device line, as in ``LAZYMAX`` and the manifest budgets. Every function and table
name carries a per-module tag (``a`` for PRBL100, ``b``, ``c``), so no two modules share a
name: each import interns its own names, as a real lazy module does. The module bodies only
define functions and tables, so the probes import at any depth (PROBE6 ``imp6`` imports PRBL300
from depth 6). The functions are never called; ``K``, ``R`` and ``A`` stand in for the resident
modules a lazy module imports.

**The gate.** PRBMEM prints, per module, ``cost`` (steady RAM after the first import), ``kept``
(RAM not freed by the first, second and third import/evict cycles; the third clears
``__dict__`` first) and ``peak`` (the free memory the import needs, found with a ballast; it
runs after three cycles, so the module's names are already interned). ``derive`` turns these
into the values DESIGN 18.7 asks for:

- ``FACTOR`` = sum(cost) / sum(.mpy bytes) (``MPY_BYTES``, mpy-cross 1.29), and the steady
  bytes per line ``FACTOR * MPYB``, which the ledger and the bundler's ``COST`` both use;
- ``PEAKB``: the compile transient per line, ``(peak - cost + qstr) / lines``, where
  ``qstr = kept1 - kept2`` is the name table the first import interned. The worst module
  counts. ``R.need`` adds the part's ``COST`` to ``PEAKB * LINES`` (DESIGN 18.4), so the
  steady cost is not counted twice;
- ``LAZYMAX``: the largest part (a multiple of 10) whose transient fits the 12 KB compile
  reserve of the ledger (DESIGN 18.1);
- ``NMAX``: the node memory of the ledger (768 x (32 B tuple + 4 x 4 B slots) = 36 KB) divided
  by the measured bytes per node, a multiple of 64;
- ``EVICT``: ``'modules'`` (``del sys.modules[...]`` frees the code), ``'dict'``
  (``m.__dict__.clear()`` first) or ``'none'`` (DESIGN 18.5);
- ``DRAW_EVICTABLE``: ladder step 4 (DESIGN 18.8), needed when a load set of DESIGN 18.2 does
  not fit the lazy budget with CVDRAW resident.

Desktop-only code (CPython). It is not device code, so the subset lint does not apply.
"""
import ast
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROBE = os.path.join(ROOT, 'probe')
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bundle  # noqa: E402

SIZES = (100, 200, 300)
TAGS = {100: 'a', 200: 'b', 300: 'c'}

# .mpy bytes of the generated modules, from mpy-cross 1.29.0.post2 (mpy v6.3). FACTOR divides
# PRBMEM's cost by these. `--stats` re-measures them when mpy-cross is found (MPY_CROSS=path,
# the mpy_cross package or PATH); tests/test_genprobe.py checks them then.
MPY_BYTES = {'PRBL100': 1328, 'PRBL200': 2600, 'PRBL300': 3893}

# -- the code shapes ------------------------------------------------------------------------
#
# Each template is a fragment of a lazy module, adapted from the memory-first prototype
# (core.py, rules.py, prt.py) and the DESIGN sketches (10.6 g_int, 18.4 need). '@' marks the
# per-copy name suffix. One statement per line, so a template's line count is its device
# line count. The order interleaves the shapes, so PRBL100 already holds most of them.

HEAD = 'K = R = A = None\nMAXSTEP = 400\n'

TEMPLATES = (
    # pair loop over a flat ADD/MUL tuple; constructor calls through the K alias
    '''
def linear@(e, x):
    if e == x:
        return K.ONE
    t = K.N[e]
    if t[0] == K.MUL and len(t) == 4 and t[2] == x and t[3] == K.ONE:
        return t[1]
    if t[0] == K.ADD:
        a = 0
        j = 2
        while j < len(t):
            if t[j] == x:
                a = t[j + 1]
            elif not K.free_of(t[j], x):
                return 0
            j += 2
        return a
    return 0
''',
    # a generator strategy (DESIGN 10.6) with its strategy table
    '''
STRATS@ = (('int', 'g_table'), ('intb', 'g_usub'), ('int2', 'g_tabular'), ('int2b', 'g_rational'), ('int3', 'g_parts'))


def g_int@(f, x, depth):
    if K.free_of(f, x):
        yield (K.mul_(K.ONE, [(f, K.ONE), (x, K.ONE)]), K.ZERO)
        return
    c, g = A.split_const(f, x)
    t = K.N[g]
    if t[0] == K.ADD:
        Fs = [K.mul_(t[1], [(x, K.ONE)])]
        Rs = []
        j = 2
        while j < len(t):
            r = yield g_int@(t[j], x, depth)
            if r is None:
                r = (K.ZERO, t[j])
            Fs.append(K.mul_(t[j + 1], [(r[0], K.ONE)]))
            Rs.append(K.mul_(t[j + 1], [(r[1], K.ONE)]))
            j += 2
        yield (K.add_(Fs), K.add_(Rs))
        return
    for mod, name in STRATS@:
        M = R.need(mod)
        r = yield R.scoped(getattr(M, name)(g, x, depth))
        if r is not None:
            yield (K.mul_(K.ONE, [(c, K.ONE), (r[0], K.ONE)]), r[1])
            return
    yield (K.ZERO, f)
''',
    # printer: string building, short strings and name tables
    '''
CNAME@ = ('pi', 'e', 'oo', 'undef', 'true', 'false')
FNAME@ = ('sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'ln', 'abs', 'sign', 'floor', 'ceil')


def items@(n, x):
    t = K.N[n]
    op = t[0]
    if op == K.NUM:
        if t[2]:
            return [K.ntext(t)]
        return [str(t[1]) if t[3] == 1 else '%d/%d' % (t[1], t[3])]
    if op == K.SYM:
        return [t[1]]
    if op == K.CON:
        return [CNAME@[t[1]]]
    if op >= K.FN0:
        return [FNAME@[op - K.FN0] + '(', t[1], ')']
    if op == K.EQ:
        return [t[1], '=', t[2]]
    out = []
    j = 2
    while j < len(t):
        if out:
            out.append('+' if op == K.ADD else '*')
        out.append(t[j])
        if t[j + 1] != K.ONE:
            out.append('^' if op == K.MUL else '*')
            out.append(t[j + 1])
        j += 2
    return out
''',
    # an if chain on op codes
    '''
def prec@(n):
    t = K.N[n]
    op = t[0]
    if op == K.ADD:
        return 1
    if op == K.NUM:
        return 4 if t[3] == 1 and t[2] == 0 and t[1] >= 0 else 1
    if op == K.MUL:
        if t[1] != K.ONE or len(t) > 4:
            return 2
        return 4 if t[3] == K.HALF else 3
    return 4
''',
    # an explicit goal stack with a step cap (the matcher)
    '''
def match@(p, s, env, x):
    goals = [(p, s)]
    trail = []
    steps = 0
    while goals:
        steps += 1
        if steps > MAXSTEP:
            return False
        pp, ss = goals.pop()
        tp = K.N[pp]
        op = tp[0]
        if pp == ss:
            continue
        if op == K.WILD:
            sl = tp[1]
            if env[sl]:
                if env[sl] != ss:
                    return False
            elif tp[2] == 1 and not K.free_of(ss, x):
                return False
            else:
                env[sl] = ss
                trail.append(sl)
            continue
        ts = K.N[ss]
        if op < K.COMP or ts[0] != op or len(ts) != len(tp):
            return False
        for j in range(len(tp) - 1, 0, -1):
            goals.append((tp[j], ts[j]))
    return True
''',
    # pseudo-division over Z (poly.py style): nested loops over int lists
    '''
def pdivrem@(a, b):
    n = len(b) - 1
    lb = b[-1]
    r = a[:]
    q = [0] * max(len(a) - n, 1)
    m = 1
    i = len(r) - 1
    while i >= n:
        c = r[i]
        if c:
            g = lb if lb > 0 else -lb
            h = c if c > 0 else -c
            while h:
                g, h = h, g % h
            s = lb // g
            if s != 1:
                for j in range(len(r)):
                    r[j] *= s
                for j in range(len(q)):
                    q[j] *= s
                m *= s
            f = r[i] // lb
            q[i - n] += f
            for j in range(n + 1):
                r[i - n + j] -= f * b[j]
        i -= 1
    while r and not r[-1]:
        r.pop()
    return q, r, m
''',
    # a view of a node as pairs
    '''
def view@(op, s):
    t = K.N[s]
    if t[0] == op:
        ps = []
        j = 2
        while j < len(t):
            ps.append((t[j], t[j + 1]))
            j += 2
        return t[1], tuple(ps)
    if t[0] == K.NUM:
        return s, ()
    if op == K.MUL:
        return K.ONE, ((s, K.ONE),)
    if t[0] == K.MUL and t[1] != K.ONE:
        if len(t) == 4 and t[3] == K.ONE:
            return K.ZERO, ((t[2], t[1]),)
        return K.ZERO, ((K.mk((K.MUL, K.ONE) + t[2:]), t[1]),)
    return K.ZERO, ((s, K.ONE),)
''',
    # a rule table of strings, scanned in file order
    '''
RULES@ = (('sin(A*X)', '-cos(A*X)/A', ''), ('cos(A*X)', 'sin(A*X)/A', ''), ('e^(A*X)', 'e^(A*X)/A', 'A!=0'), ('1/(A*X+B)', 'ln(abs(A*X+B))/A', ''), ('sec(A*X)^2', 'tan(A*X)/A', ''))


def rule@(op, s, env):
    for lhs, rhs, guard in RULES@:
        if lhs[:3] == s[:3] and (not guard or K.guard_ok(guard, env)):
            return rhs
    return None
''',
    # nested loops with a structural compare stack (the prototype's tiefix)
    '''
def tiefix@(lst):
    i = 1
    while i < len(lst):
        j = i
        while j > 0 and lst[j][0] == lst[j - 1][0]:
            st = [(lst[j][1], lst[j - 1][1])]
            r = 0
            while st and not r:
                a, b = st.pop()
                if a == b:
                    continue
                ta = K.N[a]
                tb = K.N[b]
                if K.H[a] != K.H[b] or ta[0] != tb[0] or len(ta) != len(tb):
                    r = -1 if (K.H[a], ta[0], len(ta)) < (K.H[b], tb[0], len(tb)) else 1
                elif ta[0] < K.COMP:
                    r = -1 if ta[1:] < tb[1:] else 1
                else:
                    for k in range(len(ta) - 1, 0, -1):
                        st.append((ta[k], tb[k]))
            if r >= 0:
                break
            lst[j], lst[j - 1] = lst[j - 1], lst[j]
            j -= 1
        i += 1
''',
    # integer kernel with an exception
    '''
def qn@(p, q):
    if q < 0:
        p = -p
        q = -q
    elif q == 0:
        raise K.Undefined('division by zero')
    a = -p if p < 0 else p
    b = q
    while b:
        a, b = b, a % b
    if a > 1:
        p //= a
        q //= a
    return p, q
''',
    # postorder rebuild with a memo dict
    '''
def subst@(e, x, v):
    new = {}
    for n in A.postorder(e):
        if n == x:
            new[n] = v
            continue
        t = K.N[n]
        if t[0] < K.COMP:
            new[n] = n
            continue
        kids = []
        same = 1
        for j in range(1, len(t)):
            c = new[t[j]]
            kids.append(c)
            if c != t[j]:
                same = 0
        new[n] = n if same else K.rebuild(t[0], kids)
    return new[e]
''',
    # dense Z[x] lists
    '''
def padd@(a, b, k=1):
    if len(a) < len(b):
        r = a + [0] * (len(b) - len(a))
    else:
        r = a[:]
    for i in range(len(b)):
        r[i] += k * b[i]
    while r and not r[-1]:
        r.pop()
    return r
''',
    '''
def split@(e, x):
    t = K.N[e]
    if t[0] != K.MUL:
        return (e, K.ONE) if K.free_of(e, x) else (K.ONE, e)
    c = []
    g = []
    j = 2
    while j < len(t):
        if K.free_of(t[j], x) and K.free_of(t[j + 1], x):
            c.append((t[j], t[j + 1]))
        else:
            g.append((t[j], t[j + 1]))
        j += 2
    return K.mul_(t[1], c), K.mul_(K.ONE, g)
''',
    '''
def pmul@(a, b):
    if not a or not b:
        return []
    r = [0] * (len(a) + len(b) - 1)
    for i in range(len(a)):
        x = a[i]
        if x:
            for j in range(len(b)):
                r[i + j] += x * b[j]
    return r
''',
    '''
def deg@(n, x):
    if n == x:
        return 1
    t = K.N[n]
    if t[0] == K.MUL:
        j = 2
        while j < len(t):
            e = K.N[t[j + 1]]
            if t[j] == x and e[0] == K.NUM and e[3] == 1:
                return e[1]
            j += 2
    return 0
''',
    # the inline LRU victim search of R.need (DESIGN 18.4)
    '''
def pick@(loaded, use, pinned, live):
    v = None
    for n in loaded:
        if n not in pinned and not live.get(n, 0) and (v is None or use[n] < use[v]):
            v = n
    return v
''',
    '''
def pcont@(a):
    g = 0
    for c in a:
        h = c if c >= 0 else -c
        while h:
            g, h = h, g % h
        if g == 1:
            break
    return g
''',
    '''
def horner@(a, x):
    v = 0
    for i in range(len(a) - 1, -1, -1):
        v = v * x + a[i]
    return v
''',
    '''
def sgn@(a):
    return -1 if a < 0 else (1 if a > 0 else 0)
''',
)

# A one-line table, for the last line when no template fits.
FILL = "TAB%s = ((%d, 'sin', %d), (%d, 'cos', %d), (%d, 'ln', %d))"


def _nlines(text):
    return len(bundle.minify(text).lines)


_SIZE = []


def template_lines():
    """The device line count of each template."""
    if not _SIZE:
        for t in TEMPLATES:
            _SIZE.append(_nlines(t.replace('@', '0')))
    return list(_SIZE)


def module_source(n, tag=None):
    """The unminified source of an n-line probe module (n >= 2). Deterministic.

    Templates are used in TEMPLATES order, cyclically; when the next one does not fit, the
    next one in that order that fits; a one-line table fills a last single line."""
    if n < 2:
        raise ValueError('a probe module has at least 2 lines')
    if tag is None:
        tag = TAGS.get(n, 'z%d' % n)
    sizes = template_lines()
    parts = [HEAD]
    left = n - _nlines(HEAD)
    used = [0] * len(TEMPLATES)
    i = 0
    nfill = 0
    while left > 0:
        pick = -1
        for d in range(len(TEMPLATES)):
            k = (i + d) % len(TEMPLATES)
            if sizes[k] <= left:
                pick = k
                break
        if pick < 0:
            v = 10 * nfill
            parts.append(FILL % (tag + str(nfill), v + 1, v + 2, v + 3, v + 4, v + 5, v + 6) +
                         '\n')
            nfill += 1
            left -= 1
            continue
        parts.append(TEMPLATES[pick].replace('@', tag + str(used[pick])))
        used[pick] += 1
        left -= sizes[pick]
        i = pick + 1
    return '\n'.join(parts)


def generate(n, tag=None):
    """The text of probe module PRBL<n>: a two-line comment, then exactly n device lines."""
    name = 'PRBL%d' % n
    m = bundle.minify(module_source(n, tag), name)
    if len(m.lines) != n:
        raise AssertionError('%s has %d lines, not %d' % (name, len(m.lines), n))
    return ('# %s: generated by build/genprobe.py (cas-evo M0.5, DESIGN 18.7). Do not edit.\n'
            '# %d lines of prototype-shaped code, minified; PRBMEM and PROBE6 import it.\n'
            % (name, n)) + m.text


def write(dirpath=PROBE, sizes=SIZES):
    """Write PRBL<n>.py for each size (ASCII, LF). Returns the paths."""
    out = []
    for n in sizes:
        p = os.path.join(dirpath, 'PRBL%d.py' % n)
        with open(p, 'w', encoding='ascii', newline='\n') as fh:
            fh.write(generate(n))
        out.append(p)
    return out


def stale(dirpath=PROBE, sizes=SIZES):
    """The probe files that are missing or differ from generate()."""
    bad = []
    for n in sizes:
        p = os.path.join(dirpath, 'PRBL%d.py' % n)
        try:
            with open(p, encoding='ascii', newline='') as fh:
                same = fh.read() == generate(n)
        except (OSError, UnicodeDecodeError):
            same = False
        if not same:
            bad.append(p)
    return bad


def stats(text):
    """Shape statistics of a module's text: lines (code lines, comments and blanks dropped),
    AST nodes, nodes per line, characters per line, distinct names, string constants, short
    strings (<= 10 characters: interned by the MicroPython parser), defs and generators."""
    m = bundle.minify(text)
    tree = ast.parse(m.text)
    names = set()
    nodes = strs = short = defs = gens = 0
    for nd in ast.walk(tree):
        nodes += 1
        if isinstance(nd, ast.Name):
            names.add(nd.id)
        elif isinstance(nd, ast.Attribute):
            names.add(nd.attr)
        elif isinstance(nd, ast.arg):
            names.add(nd.arg)
        elif isinstance(nd, ast.FunctionDef):
            names.add(nd.name)
            defs += 1
            for sub in ast.walk(nd):
                if isinstance(sub, (ast.Yield, ast.YieldFrom)):
                    gens += 1
                    break
        elif isinstance(nd, ast.Constant) and isinstance(nd.value, str):
            strs += 1
            if len(nd.value) <= 10:
                short += 1
    n = len(m.lines)
    return {'lines': n, 'nodes': nodes, 'nodes_per_line': nodes / float(n),
            'chars_per_line': len(m.text) / float(n), 'names': len(names), 'strings': strs,
            'short_strings': short, 'defs': defs, 'generators': gens}


# -- the gate: PRBMEM transcript -> manifest values ------------------------------------------

# The ledger of DESIGN 18.1 and the line targets of DESIGN 4.1.
FREE_KB = 173                # free heap after importing ti_system and ti_graphics [V]
BOOT_OTHER_KB = 16           # boot buffers besides the node slots: buckets 4, history 8, VARS 2,
                             # misc 2
WORK_OTHER_KB = 8            # command working set besides nodes: tokens, generators, dicts
COMPILE_RESERVE = 12 * 1024  # the compile transient the ledger reserves (LAZYMAX x PEAKB)
NODE_BUDGET = 768 * (32 + 4 * 4)    # node memory: live tuples plus the 4 preallocated slots
LEAKMAX = 2048               # bytes an evicted LAZYMAX-line part may leave (DESIGN 18.7)
PROVISIONAL = {'FACTOR': 1.8, 'PEAKB': 80, 'LAZYMAX': 150, 'NMAX': 768, 'MPYB': 12.5,
               'TUPB': 32, 'SLOTB': 4}

# (module, lines, class) of DESIGN 4.1; 'catalog' is data: 7 KB at the provisional 22.5 B
# per line is about 320 line-equivalents.
LOGICAL = (
    ('casevo', 30, 'R'), ('node', 520, 'R'), ('parse', 420, 'R'), ('printer', 330, 'R'),
    ('alg', 300, 'R'), ('run', 300, 'R'), ('draw', 350, 'R'), ('ui', 400, 'R'),
    ('rules', 250, 'L'), ('poly', 350, 'L'), ('norm', 300, 'L'), ('ident', 120, 'L'),
    ('factor', 280, 'L'), ('solve', 330, 'L'), ('forms', 150, 'L'), ('diff', 150, 'L'),
    ('series', 300, 'L'), ('limit', 300, 'L'), ('integ', 300, 'L'), ('itab', 100, 'L'),
    ('integ2', 300, 'L'), ('integ3', 250, 'L'), ('defint', 300, 'L'), ('sums', 300, 'L'),
    ('ode', 320, 'L'), ('menu', 250, 'U'), ('catalog', 320, 'U'),
)
PART_LINES = {'integ2b': 150}        # the largest S3-S8 strategy family (DESIGN 4.3, 18.2)
DRAW = 'draw'

# The load sets of DESIGN 18.2 (the largest phase of each command family).
NORMSET = ('norm', 'poly', 'rules', 'ident')
INTSET = ('integ', 'itab', 'diff', 'integ2b', 'factor')
ROWS = (
    ('simplify, expand', NORMSET),
    ('factor', NORMSET + ('factor',)),
    ('solve', NORMSET + ('factor', 'solve')),
    ('diff, grad', NORMSET + ('diff',)),
    ('taylor', NORMSET + ('series',)),
    ('limit', NORMSET + ('limit', 'series', 'diff')),
    ('integrate S0-S2', NORMSET + ('integ', 'itab', 'diff')),
    ('integrate S3-S8', NORMSET + INTSET),
    ('definite (integrate phase)', NORMSET + INTSET + ('defint',)),
    ('sum', NORMSET + ('sums', 'limit', 'series', 'diff')),
    ('desolve (integrate phase)', NORMSET + INTSET + ('ode',)),
    ('F1 menu, F5 help', ('menu', 'catalog')),
)

SHAPES = ('tup2', 'tup3', 'tup4', 'tup5', 'tup7', 'tup9', 'list3', 'dict2', 'inst2', 'float',
          'int64', 'str20', 'clos', 'gen', 'slot', 'arr', 'dent')
_CONT = ('kept', 'k2', 'kD', 'peak', 'ms', 'reimport')
_PROMPT = re.compile(r'^--\s*p\d+')


def logical_lines(text):
    """PRBMEM's printed lines -> logical lines: prompts, framing and blank lines dropped; a
    line that starts with a space (a wrap or a module's second and third line), or with
    'kept'/'peak'/... when typed by hand, is joined to the line before."""
    out = []
    for raw in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        s = raw.rstrip()
        if not s.strip() or _PROMPT.match(s.strip()) or s.startswith('=='):
            continue
        first = s.split()[0]
        if out and (s[0] == ' ' or first in _CONT):
            out[-1] = out[-1] + ' ' + s.strip()
        else:
            out.append(s.strip())
    return out


def _int(s):
    try:
        return int(s)
    except ValueError:
        return None


def parse_prbmem(text):
    """Read a PRBMEM transcript (the printed lines, typed from the screenshots) into a dict:
    'start', 'end', 'shapes' {label: bytes}, 'sysmod' (bool), 'delmod' ('ok', 'stays' or
    'E:...'), 'reimport' ('new'/'same'), 'dictclr' ('ok', 'no effect' or 'E:...'), 'mods'
    {name: {'cost', 'ms', 'kept', 'k2', 'kD', 'peak'} or {'status': ...}}, 'unparsed'."""
    res = {'shapes': {}, 'mods': {}, 'unparsed': []}
    for line in logical_lines(text):
        tok = line.split()
        lab = tok[0]
        if lab == 'PRBMEM':
            continue
        if lab in ('start', 'end') and len(tok) == 2 and _int(tok[1]) is not None:
            res[lab] = _int(tok[1])
        elif lab in SHAPES and len(tok) == 2 and _int(tok[1]) is not None:
            res['shapes'][lab] = _int(tok[1])
        elif lab == 'sys.modules' and len(tok) == 2:
            res['sysmod'] = tok[1] == 'yes'
        elif lab == 'delmod' and len(tok) >= 2:
            res['delmod'] = tok[1]
            if len(tok) == 4 and tok[2] == 'reimport':
                res['reimport'] = tok[3]
        elif lab == 'dictclr' and len(tok) >= 2:
            res['dictclr'] = ' '.join(tok[1:])
        elif len(tok) == 2 and tok[1] in ('missing', 'MemoryError'):
            res['mods'][lab] = {'status': tok[1]}
        elif len(tok) >= 3 and tok[1] == 'cost':
            d = {}
            ok = True
            j = 1
            while j + 1 < len(tok):
                v = _int(tok[j + 1])
                if v is None and tok[j] == 'peak' and tok[j + 1].startswith('E:'):
                    d['peak_error'] = tok[j + 1]
                elif v is None:
                    ok = False
                else:
                    d[tok[j]] = v
                j += 2
            if ok and j == len(tok) and 'cost' in d:
                res['mods'][lab] = d
            else:
                res['unparsed'].append(line)
        else:
            res['unparsed'].append(line)
    return res


def _ceil(x, step):
    return int(math.ceil(x / float(step) - 1e-9)) * step


def _floor(x, step):
    return int(math.floor(x / float(step) + 1e-9)) * step


def ledger(bpl, peakb, lazymax, nmax, tupb, slotb, frag):
    """The heap ledger of DESIGN 18.1 in bytes: [(item, bytes)], and the lazy code budget."""
    free = FREE_KB * 1024
    res_lines = 0
    for name, lines, cls in LOGICAL:
        if cls == 'R':
            res_lines += lines
    items = [
        ('free after ti_system and ti_graphics', free),
        ('resident code (%d lines)' % res_lines, -int(res_lines * bpl)),
        ('boot buffers (node slots %d x %d B)' % (nmax, 4 * slotb),
         -(BOOT_OTHER_KB * 1024 + nmax * 4 * slotb)),
        ('command working set (%d nodes x %d B + %d KB)' % (nmax, tupb, WORK_OTHER_KB),
         -(nmax * tupb + WORK_OTHER_KB * 1024)),
        ('reserve (%d lines x %d B + FRAG)' % (lazymax, peakb), -(lazymax * peakb + frag)),
    ]
    lazy = 0
    for _, b in items:
        lazy += b
    return items, lazy


def row_bytes(mods, bpl):
    lines = dict((m, n) for m, n, _ in LOGICAL)
    lines.update(PART_LINES)
    total = 0
    for m in mods:
        total += lines[m]
    return int(total * bpl)


def derive(res, mpy=None, lines=None, mpyb=None, frag=3072):
    """The M0.5 gate (DESIGN 18.7) from a parsed PRBMEM transcript. Returns a dict with the
    manifest values ('FACTOR', 'PEAKB', 'LAZYMAX', 'NMAX', 'EVICT', 'DRAW_EVICTABLE'), the
    figures behind them ('BPL', 'TUPB', 'SLOTB', 'modules', 'ledger', 'lazy', 'rows') and
    'warnings'. Raises ValueError if no probe module was measured."""
    if mpy is None:
        mpy = MPY_BYTES
    if lines is None:
        lines = {}
        for n in SIZES:
            lines['PRBL%d' % n] = n
    if mpyb is None:
        mpyb = PROVISIONAL['MPYB']
    warn = []
    mods = []
    for name in sorted(lines):
        d = res['mods'].get(name)
        if d is None:
            warn.append('%s: not in the transcript' % name)
        elif 'status' in d:
            warn.append('%s: %s' % (name, d['status']))
        elif name not in mpy:
            warn.append('%s: no .mpy size' % name)
        else:
            mods.append((name, d))
    if not mods:
        raise ValueError('no probe module was measured (PRBL100, PRBL200, PRBL300)')
    g = {'warnings': warn, 'modules': []}
    cost_sum = mpy_sum = 0
    peakb = 0.0
    for name, d in mods:
        n = lines[name]
        cost = d['cost']
        k1, k2, kd = d.get('kept', 0), d.get('k2', 0), d.get('kD', 0)
        qstr = max(0, k1 - k2)
        cost_sum += cost
        mpy_sum += mpy[name]
        row = {'name': name, 'lines': n, 'mpy': mpy[name], 'cost': cost, 'kept': k1, 'k2': k2,
               'kD': kd, 'qstr': qstr, 'peak': d.get('peak'), 'transient': None}
        if d.get('peak') is not None:
            tr = d['peak'] - cost + qstr
            row['transient'] = tr
            peakb = max(peakb, tr / float(n))
        else:
            warn.append('%s: no peak (%s)' % (name, d.get('peak_error', 'missing')))
        g['modules'].append(row)
    if cost_sum <= 0:
        raise ValueError('the costs are not positive: is this a desktop dry run?')
    factor = cost_sum / float(mpy_sum)
    g['FACTOR'] = math.ceil(factor * 100 - 1e-9) / 100.0
    g['BPL'] = g['FACTOR'] * mpyb
    g['probe_bpl'] = cost_sum / float(sum(r['lines'] for r in g['modules']))
    if peakb <= 0:
        warn.append('no usable peak: PEAKB stays at the provisional %d' % PROVISIONAL['PEAKB'])
        peakb = PROVISIONAL['PEAKB']
    g['PEAKB'] = int(math.ceil(peakb - 1e-9))
    g['LAZYMAX'] = _floor(COMPILE_RESERVE / float(g['PEAKB']), 10)
    if g['LAZYMAX'] < 50:
        warn.append('LAZYMAX %d < 50: the compile peak is too large for parts; consider .mpy '
                    'output (PROBE7) or the ladder (DESIGN 18.8)' % g['LAZYMAX'])
    elif g['LAZYMAX'] < PROVISIONAL['LAZYMAX']:
        warn.append('LAZYMAX %d < 150: the DESIGN 4.3 seams move; every lazy part must fit'
                    % g['LAZYMAX'])
    elif g['LAZYMAX'] >= 300:
        warn.append('LAZYMAX %d >= 300: parts of one family may be merged (DESIGN 4.3)'
                    % g['LAZYMAX'])
    sh = res.get('shapes', {})
    tupb = max(sh.get('tup4', 0), sh.get('tup5', 0))
    if tupb <= 0:
        warn.append('no tup4/tup5 bytes: the node tuple stays at 32 B')
        tupb = PROVISIONAL['TUPB']
    slotb = sh.get('slot', 0)
    if slotb <= 0:
        warn.append('no slot bytes: a list slot stays at 4 B')
        slotb = PROVISIONAL['SLOTB']
    g['TUPB'], g['SLOTB'] = tupb, slotb
    g['NMAX'] = _floor(NODE_BUDGET / float(tupb + 4 * slotb), 64)
    if g['NMAX'] < 512:
        warn.append('NMAX %d < 512: below the ladder floor (DESIGN 18.8 step 6)' % g['NMAX'])
    # eviction (DESIGN 18.5): what an evicted LAZYMAX-line part leaves behind
    scale = []
    for r in g['modules']:
        scale.append(g['LAZYMAX'] / float(r['lines']))
    k2max = max(r['k2'] * s for r, s in zip(g['modules'], scale))
    kdmax = max(r['kD'] * s for r, s in zip(g['modules'], scale))
    qmax = max(r['qstr'] * s for r, s in zip(g['modules'], scale))
    g['leak'], g['leak_dict'], g['qstr_part'] = int(k2max), int(kdmax), int(qmax)
    can = res.get('sysmod') is True and res.get('delmod') == 'ok'
    if can and res.get('reimport', 'new') == 'new' and k2max <= LEAKMAX:
        g['EVICT'] = 'modules'
    elif can and res.get('dictclr') == 'ok' and kdmax <= LEAKMAX:
        g['EVICT'] = 'dict'
    else:
        g['EVICT'] = 'none'
        warn.append('no eviction: lazy families load at most once per session and are merged '
                    'into fewer modules; the T3 cut decision moves to T1.15 (DESIGN 18.5)')
    if qmax > LEAKMAX:
        warn.append('first import of a %d-line part interns about %d B of names for good'
                    % (g['LAZYMAX'], qmax))
    # the ledger and the load sets (DESIGN 18.1, 18.2), and ladder step 4 (DESIGN 18.8)
    g['ledger'], g['lazy'] = ledger(g['BPL'], g['PEAKB'], g['LAZYMAX'], g['NMAX'], tupb,
                                     slotb, frag)
    draw = row_bytes((DRAW,), g['BPL'])
    g['draw'] = draw
    g['rows'] = []
    short = []
    for label, ms in ROWS:
        b = row_bytes(ms, g['BPL'])
        fit = b <= g['lazy']
        fit4 = b <= g['lazy'] + draw
        g['rows'].append((label, b, fit, fit4))
        if not fit4:
            short.append('%s (%+.1f KB)' % (label, (g['lazy'] + draw - b) / 1024.0))
    g['DRAW_EVICTABLE'] = not all(r[2] for r in g['rows'])
    if short:
        warn.append('still short with CVDRAW evictable: %s; ladder steps 5-7 (DESIGN 18.8)'
                    % ', '.join(short))
    g['FRAG'] = frag
    return g


def manifest_block(g):
    """The constants block for build/manifest.py."""
    return ('FACTOR = %s\nPEAKB = %d\nLAZYMAX = %d\nFRAG = %d\nNMAX = %d\nEVICT = %r\n'
            'DRAW_EVICTABLE = %r\n' % (repr(g['FACTOR']), g['PEAKB'], g['LAZYMAX'], g['FRAG'],
                                       g['NMAX'], g['EVICT'], g['DRAW_EVICTABLE']))


def report(g):
    """A text report of derive(): modules, ledger, load sets, warnings, the manifest block."""
    L = ['M0.5 memory gate (DESIGN 18.7)', '',
         'module    lines  .mpy   cost  kept1  kept2  keptD   peak  transient  B/line']
    for r in g['modules']:
        tr = r['transient']
        L.append('%-8s %6d %5d %6d %6d %6d %6d %6s %10s %7.1f' % (
            r['name'], r['lines'], r['mpy'], r['cost'], r['kept'], r['k2'], r['kD'],
            '-' if r['peak'] is None else r['peak'], '-' if tr is None else tr,
            r['cost'] / float(r['lines'])))
    L += ['', 'FACTOR %.2f (provisional 1.8); steady %.1f B/line at MPYB %.1f (probe code: %.1f)'
          % (g['FACTOR'], g['BPL'], g['BPL'] / g['FACTOR'], g['probe_bpl']),
          'PEAKB %d B/line (provisional 80) -> LAZYMAX %d' % (g['PEAKB'], g['LAZYMAX']),
          'node: tuple %d B + 4 slots x %d B -> NMAX %d' % (g['TUPB'], g['SLOTB'], g['NMAX']),
          'eviction %s (repeat leak %d B, with __dict__.clear() %d B, names %d B per %d-line '
          'part)' % (g['EVICT'], g['leak'], g['leak_dict'], g['qstr_part'], g['LAZYMAX']),
          '', 'ledger (DESIGN 18.1)']
    for item, b in g['ledger']:
        L.append('  %-52s %7.1f KB' % (item, b / 1024.0))
    L.append('  %-52s %7.1f KB' % ('lazy code budget', g['lazy'] / 1024.0))
    L += ['', 'load sets (DESIGN 18.2); CVDRAW is %.1f KB' % (g['draw'] / 1024.0)]
    for label, b, fit, fit4 in g['rows']:
        L.append('  %-28s %6.1f KB  %-3s %s' % (label, b / 1024.0, 'yes' if fit else 'no',
                                               '' if fit else ('fits with CVDRAW evictable'
                                                               if fit4 else 'short')))
    L += ['', 'KB per module (DESIGN 4.1)']
    for name, lines, cls in LOGICAL:
        L.append('  %-8s %s %4d lines %5.1f KB' % (name, cls, lines, lines * g['BPL'] / 1024.0))
    if g['warnings']:
        L += [''] + ['warning: ' + w for w in g['warnings']]
    L += ['', 'build/manifest.py:', manifest_block(g)]
    return '\n'.join(L)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['--check']:
        bad = stale()
        for p in bad:
            print('stale: %s (run python build/genprobe.py)' % p)
        return 1 if bad else 0
    if argv[:1] == ['--stats']:
        sizer = bundle.mpy_sizer()
        for n in SIZES:
            p = os.path.join(PROBE, 'PRBL%d.py' % n)
            s = stats(generate(n))
            b = sizer(p) if sizer and os.path.exists(p) else None
            print('PRBL%d: %d lines, %.2f nodes/line, %.1f chars/line, %d names, %d strings, '
                  '%d defs (%d generators), .mpy %s' % (
                      n, s['lines'], s['nodes_per_line'], s['chars_per_line'], s['names'],
                      s['strings'], s['defs'], s['generators'],
                      '%d B (%.1f B/line)' % (b, b / float(n)) if b else 'n/a (no mpy-cross)'))
        return 0
    if argv[:1] == ['--derive'] and len(argv) == 2:
        with open(argv[1], encoding='utf-8') as fh:
            res = parse_prbmem(fh.read())
        for s in res['unparsed']:
            print('unparsed: %s' % s)
        print(report(derive(res)))
        return 0
    if argv:
        print(__doc__.split('\n\n')[0])
        return 2
    for p in write():
        print('wrote %s' % os.path.relpath(p, ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
