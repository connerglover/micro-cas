"""The rule engine (DESIGN 9, task T1.9): rules.py (rset, guard_ok, check, g_rewrite),
rulesb.py (match, view) and ident.py (the identity sets, denest, lnsplit).

- matcher cases, the AC backtrack of 9.5, constraints, binders, coefficient wildcards, the
  solution index (alt), caps;
- rset buckets and caching; guard_ok, including the NEAR protocol of 9.2/9.7;
- g_rewrite termination (fixpoint, cycle, MAXPASS, budget), regions, binding retries; the
  root-only table application of S1 (apply_root, the loop CVINT's g_table needs);
- the 9.8 suite for every rule of every set: the rule lint (20.3), self-match, soundness
  (mpmath at 30 digits), measure, context match, coverage; derivative and inverse templates;
- denesting and the ln split; properties (matcher undo and reproduction, fixpoints and
  soundness on generated inputs); nesting invariance.

The runner is replaced by a stub (MODS, TICK), so these tests do not depend on run.py's
loader; the exact zero test of the NEAR protocol (norm.normal, T1.10) is a SymPy stub.
"""
import importlib
import os
import random
import sys
import types
import warnings
import zlib

import mpmath
import pytest
import sympy

import alg as A
import gen
import node as K
import parse as P


def _import_rules():
    """rules imports run at module level (DESIGN 4.2); without a working run.py a placeholder
    stands in for the import only (every test patches rules.R with STUB below)."""
    try:
        return importlib.import_module('rules')
    except Exception:                                   # run.py absent or not importable yet
        pass
    ph = types.ModuleType('run')
    saved = sys.modules.get('run')
    sys.modules['run'] = ph
    try:
        return importlib.import_module('rules')
    finally:
        if saved is None:
            sys.modules.pop('run', None)
        else:
            sys.modules['run'] = saved


RU = _import_rules()
import rulesb as RB                                     # noqa: E402
import ident as ID                                      # noqa: E402

TICK = ['tick']
X = 'x'
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')

# -- the design's tables (DESIGN 9.2, 9.3) as fixtures; the real modules are tested too when
# they exist (itab.py: T2.4, diff.py: T2.1, solve*.py: T1.12) ----------------------------------
DITAB = (
    'L^N', 'L^(N+1)/(A*(N+1))', 'N!=-1',
    'L^(-1)', 'ln(abs(L))/A', '',
    'e^L', 'e^L/A', '',
    'K^L', 'K^L/(A*ln(K))', 'K>0',
    'sin(L)', '-cos(L)/A', '',
    'cos(L)', 'sin(L)/A', '',
    'sec(L)^2', 'tan(L)/A', '',
    'sec(L)', 'ln(abs(sec(L)+tan(L)))/A', '',
    'sec(L)*tan(L)', 'sec(L)/A', '',
    'Q^(-1)', '2*atan((2*A*x+B)/sqrt(4*A*C-B^2))/sqrt(4*A*C-B^2)', '4*A*C-B^2>0',
)
DDT = {K.SIN: 'cos(U)', K.COS: '-sin(U)', K.TAN: 'sec(U)^2', K.SEC: 'sec(U)*tan(U)',
       K.CSC: '-csc(U)*cot(U)', K.COT: '-csc(U)^2', K.ASIN: '1/sqrt(1-U^2)',
       K.ACOS: '-1/sqrt(1-U^2)', K.ATAN: '1/(1+U^2)', K.SINH: 'cosh(U)', K.COSH: 'sinh(U)',
       K.TANH: '1-tanh(U)^2', K.LN: '1/U', K.ABS: 'abs(U)/U', K.SIGN: '0', K.FLOOR: '0',
       K.CEIL: '0'}
DINV = {K.SIN: (('asin(T)', 'pi-asin(T)'), 'abs(T)<=1'),
        K.COS: (('acos(T)', '2*pi-acos(T)'), 'abs(T)<=1'),
        K.TAN: (('atan(T)', 'atan(T)+pi'), ''),
        K.LN: (('e^T',), ''), K.ABS: (('T', '-T'), 'T>=0')}


def _real(name):
    """src/<name>.py when it exists (only from src/: never a same-named site package)."""
    if not os.path.exists(os.path.join(SRC, name + '.py')):
        return None
    try:
        return importlib.import_module(name)
    except Exception:                                   # noqa: BLE001 - in flight elsewhere
        return None


REAL_ITAB = getattr(_real('itab'), 'ITAB', None)
REAL_DT = getattr(_real('diff'), 'DT', None)
REAL_INV = None
for _m in ('solve', 'solveb', 'solvec'):
    REAL_INV = REAL_INV or getattr(_real(_m), 'INV', None)

# test-only rule sets, reached through the module key 'test'
TESTSETS = types.SimpleNamespace(
    DITAB=DITAB,
    RITAB=REAL_ITAB or (),
    CYCLE=(('size',), 'sin(U)', 'cos(U)', '', 'cos(U)', 'sin(U)', ''),
    GROW=(('size',), 'sin(U)', 'sin(U+1)', ''),
    NEARZ=(('size',), 'sin(U)', 'cos(U)', '(1+sqrt(2))^2=3+2*sqrt(2)'),
    NEARLE=(('size',), 'sin(U)', 'cos(U)', '(1+sqrt(2))^2<=3+2*sqrt(2)'),
    NEARLT=(('size',), 'sin(U)', 'cos(U)', '(1+sqrt(2))^2<3+2*sqrt(2)'),
    NEARNE=(('size',), 'sin(U)', 'cos(U)', '(1+sqrt(2))^2!=3+2*sqrt(2)'),
    NEARNZ=(('size',), 'sin(U)', 'cos(U)', 'e^(pi*sqrt(163))=640320^3+744'),
    ORDER=(('size',), 'U^2*R', 'ln(U)*R', '', 'sin(U)', 'cos(2*U)', '',
           'U^P*R', 'cos(U)*R', 'P>=2', 'cos(U)', 'tan(U)', ''),
    UNDEF=(('size',), 'sin(U)', 'cos(U)', '1/(U-U)>0'),
    BADRHS=(('size',), 'sin(U)', '1/(U-U)', ''),
    NOOP=(('size',), 'U^2*R', 'U*U*R', '', 'U^P*R', 'cos(U)*R', 'P>=2'),
    NOOP1=(('size',), 'U^2*R', 'U*U*R', ''),
    ALT=(('size',), 'cos(U)^P*R', 'sin(U)^P*R', 'P>=2'),
)
TESTKEYS = ('ditab', 'ritab', 'cycle', 'grow', 'nearz', 'nearle', 'nearlt', 'nearne', 'nearnz',
            'order', 'undef', 'badrhs', 'noop', 'noop1', 'alt')


# -- the runner stub and an exact zero test for NEAR guards ----------------------------------------

def to_sympy(n):
    """The SymPy value of node n (pure reads of K.N); odd-denominator powers are real roots."""
    vals = {}
    for i in A.postorder(n):
        t = K.N[i]
        op = t[0]
        if op == K.NUM:
            v = sympy.Rational(t[1], t[3]) + sympy.I * sympy.Rational(t[2], t[3])
        elif op == K.FLT:
            v = sympy.Float(t[1]) + sympy.I * sympy.Float(t[2])
        elif op == K.SYM:
            v = sympy.Symbol(t[1], real=True)
        elif i == K.PI:
            v = sympy.pi
        elif i == K.E:
            v = sympy.E
        elif op == K.ADD:
            v = vals[t[1]]
            for j in range(2, len(t), 2):
                v = v + vals[t[j]] * vals[t[j + 1]]
        elif op == K.MUL:
            v = vals[t[1]]
            for j in range(2, len(t), 2):
                e = K.N[t[j + 1]]
                if e[0] == K.NUM and not e[2] and e[3] % 2 and e[3] > 1:
                    v = v * sympy.real_root(vals[t[j]], e[3]) ** e[1]
                else:
                    v = v * vals[t[j]] ** vals[t[j + 1]]
        elif op >= K.FN0:
            f = {K.SIN: sympy.sin, K.COS: sympy.cos, K.TAN: sympy.tan, K.SEC: sympy.sec,
                 K.CSC: sympy.csc, K.COT: sympy.cot, K.ASIN: sympy.asin, K.ACOS: sympy.acos,
                 K.ATAN: sympy.atan, K.SINH: sympy.sinh, K.COSH: sympy.cosh,
                 K.TANH: sympy.tanh, K.LN: sympy.log, K.ABS: sympy.Abs, K.SIGN: sympy.sign,
                 K.FLOOR: sympy.floor, K.CEIL: sympy.ceiling, K.FACT: sympy.factorial}[op]
            v = f(vals[t[1]])
        else:
            raise ValueError('no SymPy value for %r' % (t,))
        vals[i] = v
    return vals[n]


NORMAL_CALLS = []


def stub_normal(d):
    """norm.normal for the NEAR protocol: ZERO when d is exactly 0, else d (no new nodes)."""
    NORMAL_CALLS.append(d)
    return K.ZERO if sympy.simplify(sympy.expand(to_sympy(d))) == 0 else d


STUB = types.SimpleNamespace(
    MODS={'rules': RU, 'rulesb': RB, 'ident': ID, 'itab': types.SimpleNamespace(ITAB=DITAB),
          'test': TESTSETS, 'norm': types.SimpleNamespace(normal=stub_normal)},
    TICK=TICK)


@pytest.fixture(autouse=True)
def stub_run(monkeypatch):
    monkeypatch.setattr(RU, 'R', STUB)
    monkeypatch.setattr(RB, 'R', STUB)
    w = dict(RU.WHERE)
    for k in TESTKEYS:
        w[k] = 'test'
    monkeypatch.setattr(RU, 'WHERE', w)
    del NORMAL_CALLS[:]


# -- helpers --------------------------------------------------------------------------------------

def sx():
    return K.sym(X)


def ex(s, **kw):
    """The node of s (explicit '*'; x is the symbol x), through inst in template mode."""
    env = [0] * P.NSLOT
    env[P.XSLOT] = sx()
    for k, v in kw.items():
        env[P.WSLOT[k][0]] = v
    return P.inst(P.tcode(s), env)


def pat(s):
    """A pattern node, registered in RULECACHE (the invariant scan allows WILD only there)."""
    m = K.NN
    p = K.keep(m, P.inst(P.tcode(s), None))
    rs = K.RULECACHE.setdefault('_pats', {0: ()})
    rs[0] = rs[0] + ((p, s, ''),)
    return p


def fresh(x=None):
    env = [0] * P.NSLOT
    env[P.XSLOT] = sx() if x is None else x
    return env


def slot(letter):
    return P.WSLOT[letter][0]


def clean(env, x=None):
    return env == fresh(x)


def bound(env):
    """{letter: node} of the bound rule letters (x excluded)."""
    out = {}
    for L, (sl, c) in P.WSLOT.items():
        if L != 'x' and env[sl]:
            out[L] = env[sl]
    return out


def m1(ps, ss, x=None, alt=0):
    """(matched, {letter: node}, env) of pattern text ps against subject text ss."""
    p = pat(ps)
    s = ex(ss)
    env = fresh(x)
    ok = RB.match(p, s, env, sx() if x is None else x, alt)
    return ok, bound(env), env


TICKS = [0]


def drive(g, soft=False):
    """The trampoline of DESIGN 10.4, cut down: generators nest on a list, TICK is counted,
    CasSoft gives None (or propagates with soft=True)."""
    stack = [g]
    val = None
    TICKS[0] = 0
    while stack:
        try:
            y = stack[-1].send(val)
        except StopIteration:
            y = None
        except K.CasSoft:
            if soft:
                raise
            y = None
        else:
            if y is TICK:
                TICKS[0] += 1
                val = None
                continue
            if type(y) is types.GeneratorType:
                stack.append(y)
                val = None
                continue
        stack.pop()
        val = y
    return val


def rewrite(e, rs, x=None, budget=1000, soft=True):
    return drive(RU.g_rewrite(e, rs, sx() if x is None else x, budget), soft)


def apply1(e, name, x=None):
    """The root-only table application of S1 (DESIGN 9.1, 10.6; the loop of CVINT's g_table,
    T2.4): the RHS of the first rule of the set whose pattern matches e with a binding (at
    most MAXALT, as g_rewrite) whose guard holds, instantiated; None when no rule fires."""
    x = sx() if x is None else x
    rs = RU.rset(name)
    for p, rhs, guard in rs.get(K.N[e][0], rs[RU.VIEW]):
        for k in range(RU.MAXALT):
            env = fresh(x)
            if not RB.match(p, e, env, x, k):
                break
            if guard_holds(guard, env):
                return P.inst(P.tcode(rhs), env)
    return None


def reachable(roots):
    """Ids reachable from roots and from every RULECACHE pattern."""
    st = [r for r in roots if r]
    for nm in K.RULECACHE:
        for op in K.RULECACHE[nm]:
            for r in K.RULECACHE[nm][op]:
                st.append(r[0])
    seen = set()
    while st:
        i = st.pop()
        if i in seen:
            continue
        seen.add(i)
        t = K.N[i]
        if t[0] >= K.COMP:
            st.extend(t[1:])
    return seen


def no_garbage_above(m, roots):
    live = reachable(roots)
    dead = [i for i in range(m, K.NN) if i not in live]
    assert not dead, 'garbage left above the mark: %r' % [K.N[i] for i in dead[:5]]


def guard_holds(guard, env):
    """guard_ok, with the exact test of a NEAR result done as g_rewrite does it."""
    ok = RU.guard_ok(guard, env)
    if type(ok) is tuple:
        return stub_normal(ok[2]) == K.ZERO and ok[1] in (K.EQ, K.LE)
    return bool(ok)


# -- an mpmath evaluator (30 digits) with the real odd-root rule and a reals flag ---------------

mpmath.mp.dps = 30
TINY = mpmath.mpf('1e-24')


class Bad(Exception):
    """No finite value here."""


def isreal(v):
    return abs(mpmath.im(v)) <= TINY * max(1, abs(v))


def _sign(a):
    return mpmath.mpf(mpmath.sign(mpmath.re(a)))


MFN = {K.SIN: mpmath.sin, K.COS: mpmath.cos, K.TAN: mpmath.tan, K.SEC: mpmath.sec,
       K.CSC: mpmath.csc, K.COT: mpmath.cot, K.ASIN: mpmath.asin, K.ACOS: mpmath.acos,
       K.ATAN: mpmath.atan, K.SINH: mpmath.sinh, K.COSH: mpmath.cosh, K.TANH: mpmath.tanh,
       K.LN: mpmath.log, K.ABS: abs, K.SIGN: _sign,
       K.FLOOR: lambda a: mpmath.floor(mpmath.re(a)),
       K.CEIL: lambda a: mpmath.ceil(mpmath.re(a)), K.FACT: mpmath.factorial}


def mev(n, vals):
    """(value, real) of node n at vals {name: number}; real: no operation on real operands
    left the reals (the LEFTREAL rule of DESIGN 6.6 and 8.3). Bad: no finite value."""
    v = {}
    real = True
    try:
        for i in A.postorder(n):
            t = K.N[i]
            op = t[0]
            if op == K.NUM:
                r = mpmath.mpc(mpmath.mpf(t[1]) / t[3], mpmath.mpf(t[2]) / t[3])
            elif op == K.FLT:
                r = mpmath.mpc(t[1], t[2])
            elif op == K.SYM:
                r = mpmath.mpc(vals[t[1]])
            elif i == K.PI:
                r = mpmath.mpc(mpmath.pi)
            elif i == K.E:
                r = mpmath.mpc(mpmath.e)
            elif op == K.ADD:
                r = v[t[1]]
                for j in range(2, len(t), 2):
                    r += v[t[j]] * v[t[j + 1]]
            elif op == K.MUL:
                r = v[t[1]]
                for j in range(2, len(t), 2):
                    b = v[t[j]]
                    te = K.N[t[j + 1]]
                    if te[0] == K.NUM and not te[2] and isreal(b):
                        p, q = te[1], te[3]
                        if q == 1:
                            f = b ** p
                        elif q % 2 and mpmath.re(b) < 0:
                            f = (-1) ** p * (-mpmath.re(b)) ** (mpmath.mpf(p) / q)
                        else:
                            f = b ** (mpmath.mpf(p) / q)
                    else:
                        f = b ** v[t[j + 1]]
                    if isreal(b) and isreal(v[t[j + 1]]) and not isreal(f):
                        real = False
                    r *= f
            elif op >= K.FN0:
                a = v[t[1]]
                r = MFN[op](a)
                if isreal(a) and not isreal(r):
                    real = False
            else:
                raise Bad()
            r = mpmath.mpc(r)
            if not mpmath.isfinite(r):
                raise Bad()
            v[i] = r
    except (ZeroDivisionError, ValueError, OverflowError):
        raise Bad()
    return v[n], real


def close(a, b, tol=mpmath.mpf('1e-20')):
    return abs(a - b) <= tol * max(1, abs(a), abs(b))


RPTS = [('0.37', '1.21', '0.53'), ('1.3', '-0.7', '2.2'), ('2.1', '0.45', '-1.1'),
        ('-0.6', '1.7', '0.8'), ('-1.7', '-2.3', '1.4'), ('-2.4', '0.9', '-0.35')]
CPTS = [(mpmath.mpc('0.3', '0.7'), mpmath.mpc('-0.4', '0.2'), mpmath.mpc('1.1', '-0.3')),
        (mpmath.mpc('-1.1', '0.25'), mpmath.mpc('0.8', '-0.6'), mpmath.mpc('0.2', '0.9'))]


def pts(complex_too=False):
    out = []
    for a, b, c in RPTS:
        out.append(({'x': mpmath.mpf(a), 'y': mpmath.mpf(b), 'z': mpmath.mpf(c)}, True))
    if complex_too:
        for a, b, c in CPTS:
            out.append(({'x': a, 'y': b, 'z': c}, False))
    return out


def agree(lhs, rhs, policy=False):
    """Count the points where lhs and rhs were compared; assert they agree there. Real points
    where the lhs left the reals are skipped (8.3); a constant lhs must agree exactly (numbers
    alone); complex points are used unless policy (a branch-policy rule)."""
    n = 0
    const = not K.V[lhs]
    for vals, isr in (pts(not policy) if not const else [({}, True)]):
        try:
            a, ra = mev(lhs, vals)
        except Bad:
            continue
        if isr and not ra and not const:
            continue
        try:
            b, _ = mev(rhs, vals)
        except Bad:
            raise AssertionError('the rhs has no value where the lhs is %s (%r)' % (a, vals))
        assert close(a, b), (vals, a, b)
        n += 1
    return n


def deriv_agree(F, f):
    """Count the real points where d/dx F was compared with f (f real there); assert they
    agree (mpmath numerical differentiation at 30 digits)."""
    n = 0
    for vals, _ in pts(False):
        try:
            fv, fr = mev(f, vals)
        except Bad:
            continue
        if not fr or not isreal(fv):
            continue

        def g(t, vals=vals):
            v = dict(vals)
            v['x'] = t
            return mev(F, v)[0]
        try:
            d = mpmath.diff(g, vals['x'])
        except Bad:
            continue
        assert close(d, fv, mpmath.mpf('1e-15')), (vals, d, fv)
        n += 1
    return n


# -- measures (DESIGN 9.2); test-side only (the device never reads them) ------------------------

def _walk(e):
    """The nodes of the tree e with multiplicity (an explicit stack)."""
    st = [e]
    while st:
        i = st.pop()
        yield i
        t = K.N[i]
        if t[0] >= K.COMP:
            st.extend(t[1:])


def _posint(e):
    t = K.N[e]
    return t[1] if t[0] == K.NUM and not t[2] and t[3] == 1 and t[1] > 0 else 0


def _factors(a):
    """The factor count of a product argument: 1 per coefficient != 1, 1 per pair with
    exponent 1, 2 per other pair; 1 for anything that is not a MUL."""
    t = K.N[a]
    if t[0] != K.MUL:
        return 1
    n = 1 if t[1] != K.ONE else 0
    for j in range(2, len(t), 2):
        n += 1 if t[j + 1] == K.ONE else 2
    return n


MEASURES = ('size', 'count', 'excess', 'pow', 'lex', 'split')


def measure(m, e):
    kind = m[0]
    if kind == 'size':
        return A.size(e)
    if kind == 'lex':
        return tuple(measure(s, e) for s in m[1:])
    ops = m[1:]
    total = 0
    if kind == 'count':                         # nodes with these ops (with multiplicity)
        for i in _walk(e):
            if K.N[i][0] in ops:
                total += 1
        return total
    if kind == 'pow':                           # total positive integer exponent on bases
        st = [e]                                # with these ops; a bare one counts 1
        while st:
            i = st.pop()
            t = K.N[i]
            if t[0] == K.MUL:
                st.append(t[1])
                for j in range(2, len(t), 2):
                    b = K.N[t[j]]
                    st.append(t[j + 1])
                    if b[0] in ops:
                        total += _posint(t[j + 1])
                        st.extend(b[1:])
                    else:
                        st.append(t[j])
                continue
            if t[0] in ops:
                total += 1
            if t[0] >= K.COMP:
                st.extend(t[1:])
        return total
    if kind == 'excess':                        # per product: sum of integer exponents - 1
        for i in _walk(e):
            t = K.N[i]
            if t[0] == K.MUL:
                s = 0
                for j in range(2, len(t), 2):
                    if K.N[t[j]][0] in ops:
                        s += _posint(t[j + 1])
                total += max(0, s - 1)
        return total
    if kind == 'split':                         # per op node: (factors of its argument)^2
        for i in _walk(e):
            t = K.N[i]
            if t[0] in ops:
                total += _factors(t[1]) ** 2
        return total
    raise ValueError(m)


# -- the rule sets under test --------------------------------------------------------------------

def ident_sets():
    """The identity sets of ident.py (a name bound to the same tuple as an earlier one, such
    as ZBASIS = TRIGCOS, is an alias and is tested once)."""
    out = []
    seen = []
    for name in sorted(dir(ID)):
        v = getattr(ID, name)
        if name.isupper() and type(v) is tuple and len(v) >= 4 and type(v[0]) is tuple:
            if not any(v is w for w in seen):
                out.append(name.lower())
                seen.append(v)
    return out


IDENT = ident_sets()
TABLES = ['ditab'] + (['ritab'] if REAL_ITAB else [])
ALLSETS = IDENT + TABLES


def set_data(name):
    if name in TESTKEYS:
        return getattr(TESTSETS, name.upper())
    return getattr(ID, name.upper())


def rules_of(name):
    d = set_data(name)
    j = 1 if type(d[0]) is tuple else 0
    out = []
    while j < len(d):
        out.append((d[j], d[j + 1], d[j + 2]))
        j += 3
    return out


RULES = []
for _n in ALLSETS:
    for _i in range(len(rules_of(_n))):
        RULES.append((_n, _i))
RULE_IDS = ['%s-%d' % r for r in RULES]
IRULES = [r for r in RULES if r[0] in IDENT]
IRULE_IDS = ['%s-%d' % r for r in IRULES]
TRULES = [r for r in RULES if r[0] in TABLES]
TRULE_IDS = ['%s-%d' % r for r in TRULES]

# binding pools: disjoint per letter, so that distinct letters never collide (9.8: the LHS
# built from the bindings through the constructors must keep its shape)
POOLS = {
    'U': ('x', 'x+1', '2*x', 'x^2', '3*x-1', 'x/2', '2', 'pi/7', 'sqrt(2)', 'x^2+x'),
    'V': ('x+2', '3*x', 'x^3', '5*x+1', 'x/3-1', '1/3', 'pi/9', 'sqrt(3)', 'x^2-x'),
    'W': ('x', 'y+1', 'x^2', 'sin(y)', '2*x+y', 'x/5'),
    'T': ('1/2', '-1/3', 'y', '2', 'sqrt(2)/2', '0', '-1'),
    'A': ('2', '-3', '1/2', 'y', 'pi', 'y+1', 'sqrt(3)'),
    'B': ('5', '-1', '3/2', 'y^2', 'e', '2*y-1'),
    'C': ('7', '-2', '1/4', 'y-3', 'pi/2'),
    'K': ('2', '3', '1/2', 'pi', 'e', 'y', '-2', 'y^2+1', '5/3'),
    'M': ('2', '5', '-3', '3/2', '-1/2', '7'),
    'N': ('3', '-2', '1/3', '-5', '4', '1/2', '2'),
    'P': ('2', '3', '4', '5', '-1', '1', '-2', '6'),
    'L': ('x', '2*x+1', '3-x', 'x/2', 'y*x+1', '-x', 'pi*x-2', '5*x'),
    'Q': ('x^2+x+1', '2*x^2-3*x+5', 'x^2+4', '-x^2+2*x+3', 'x^2', '3*x^2+y', 'x^2-1'),
    'R+': ('0', 'y', 'y^2+1', '3', '-2*y', 'cos(y)'),
    'R*': ('1', 'y', '3', 'y^2+1', '-2', 'y/2', 'cosh(y)'),
}
# per-set pools where the defaults collapse under the constructors (numbers fold together)
OVERRIDE = {
    # ln(U*R): U must stay a factor with exponent 1 next to R; ln(U^N): U^N must stay a power
    'lnexpand': {'U': ('pi', 'e+1', 'sqrt(2)+1', 'ln(3)', 'pi^2+1'),
                 'R*': ('2', '3', '1/2', 'sqrt(3)', 'pi+1', '5/3', 'e'),
                 'N': ('2', '1/2', '3', '-2/3', '5', '-1')},
    # M^W*N^W: equal bases would merge into one power
    'expmerge': {'N': ('3', '1/3', '4', '5/2', '11')},
}
MINGOOD = 3         # instances per rule that must pass the guard (out of TRIES samples)
WANT = 6
TRIES = 80


def letters(s):
    out = set()
    if s:
        for t in P.lex(s.lstrip('~')):
            if t[0] == P.K_NAME and t[1] in P.WSLOT and t[1] != 'x':
                out.add(t[1])
    return out


def rest_parent(p):
    """ADD or MUL: the op of the pattern node that holds the REST pair, or None."""
    for i in A.postorder(p):
        t = K.N[i]
        if t[0] in (K.ADD, K.MUL):
            for j in range(2, len(t), 2):
                w = K.N[t[j]]
                if w[0] == K.WILD and w[2] == P.W_REST:
                    return t[0]
    return None


class Inst(object):
    """One sampled instance of a rule: s the LHS instance, (c, g) its split for tables (s =
    c*g), env the matcher's bindings for g, r the RHS instance, noop: r == g."""

    def __init__(self, s, c, g, env, r):
        self.s, self.c, self.g, self.env, self.r = s, c, g, env, r
        self.noop = r == g


def sample(name, idx, want=WANT, tries=TRIES):
    """Instances of rule idx of set name (DESIGN 9.8 tests 1-2): bindings drawn from the
    pools (guard checked), the LHS built through the constructors (split_const first for a
    table, as S1 does), then matched by the compiled pattern (up to MAXALT bindings, as the
    rewriter tries them); the bindings must rebuild the instance exactly."""
    lhs, rhs, guard = rules_of(name)[idx]
    table = name in TABLES
    p = pat(lhs)
    ls = letters(lhs)
    rp = rest_parent(p)
    pools = dict(POOLS)
    pools.update(OVERRIDE.get(name, {}))
    rng = random.Random(zlib.crc32(('%s/%d' % (name, idx)).encode()))
    x = sx()
    out = []
    for _ in range(tries):
        env = fresh()
        for L in sorted(ls):
            if L == 'R':
                pool = pools['R+'] if rp == K.ADD else pools['R*']
            else:
                pool = pools[L]
            env[slot(L)] = ex(rng.choice(pool))
        if 'L' in ls:
            ab = A.linear(env[slot('L')], x)
            env[slot('A')], env[slot('B')] = ab
        if 'Q' in ls:
            abc = A.quadratic(env[slot('Q')], x)
            env[slot('A')], env[slot('B')], env[slot('C')] = abc
        try:
            if not guard_holds(guard, env):
                continue
            s = P.inst(P.tcode(lhs), env)
        except K.CasSoft:
            continue
        c, g = A.split_const(s, x) if table else (K.ONE, s)
        hit = None
        for k in range(RU.MAXALT):
            env2 = fresh()
            if not RB.match(p, g, env2, x, k):
                assert clean(env2), 'a failed match left bindings'
                break
            back = P.inst(P.tcode(lhs), env2)
            assert back == g, '%s: the bindings %r rebuild %r, not %r' % (
                lhs, bound(env2), K.N[back], K.N[g])
            if guard_holds(guard, env2):
                hit = env2
                break
        assert hit is not None, '%s-%d: the pattern %r does not match its instance %r' % (
            name, idx, lhs, K.N[g])
        r = P.inst(P.tcode(rhs), hit)
        out.append(Inst(s, c, g, hit, r))
        if len(out) >= want:
            break
    assert len(out) >= MINGOOD, '%s-%d: only %d instances pass the guard' % (
        name, idx, len(out))
    return out


def policy_rule(name, idx):
    """A branch-policy rule (8.3): its guard lets symbolic differences pass ('~'), so it is
    checked at real points where the input is real only."""
    return rules_of(name)[idx][2].startswith('~')


# -- 1. the matcher (rulesb, DESIGN 9.5) -------------------------------------------------------

def test_ac_backtrack_of_section_9_5():
    ok, b, env = m1('sin(U)*cos(U)*R', 'sin(x)*cos(2*x)*sin(2*x)')
    assert ok
    assert b['U'] == ex('2*x') and b['R'] == ex('sin(x)')
    ok, b, env = m1('sin(U)*cos(U)*R', 'sin(x)*cos(2*x)*sin(3*x)')
    assert not ok and clean(env)


def test_failed_matches_leave_env_clean():
    cases = [('sin(U)*cos(U)', 'sin(x)*cos(y)'), ('N*sin(U)^2+N*cos(U)^2+R',
             '3*sin(x)^2+2*cos(x)^2'), ('L^N', 'x^2+1'), ('cos(U)^P*R', 'sin(x)^2'),
             ('Q^(-1)', '1/x^3'), ('M^W*N^W*R', '2^x*3^y'), ('sec(L)*tan(L)', 'sec(x)*tan(2*x)'),
             ('U*V*W', 'x*y')]
    for ps, ss in cases:
        ok, b, env = m1(ps, ss)
        assert not ok and clean(env), (ps, ss, b)


def test_view_identity_elements_act_as_defaults():
    ok, b, _ = m1('x^N', 'x')
    assert ok and b == {'N': K.ONE}
    ok, b, _ = m1('L^N', 'x')
    assert ok and b['N'] == K.ONE and b['A'] == K.ONE and b['B'] == K.ZERO
    ok, b, _ = m1('sin(U)+R', '3*sin(x)')          # 3*sin(x) seen as the sum 0 + 3*sin(x)?
    assert not ok                                   # no: the pattern term has coefficient 1
    ok, b, _ = m1('N*sin(U)+R', '3*sin(x)')
    assert ok and b['N'] == ex('3') and b['R'] == K.ZERO
    ok, b, _ = m1('cos(U)^2*R', '3*cos(x)^2')
    assert ok and b['R'] == ex('3')
    ok, b, _ = m1('cos(U)^2*R', 'cos(x)^2')
    assert ok and b['R'] == K.ONE
    ok, b, _ = m1('U+R', '5')                       # a number as a sum: the constant only
    assert not ok
    ok, b, _ = m1('ln(U)*R', 'ln(x)')
    assert ok and b['R'] == K.ONE


def test_view_and_check_helpers():
    x = sx()
    s = ex('3*x^2')
    assert RB.view(K.MUL, s) == (K.N[s][1], K.N[s][2:])
    c, sp = RB.view(K.ADD, s)
    assert c == K.ZERO and sp == (ex('x^2'), ex('3'))
    assert RB.view(K.ADD, ex('7')) == (ex('7'), ())
    assert RB.view(K.MUL, ex('x+1')) == (K.ONE, (ex('x+1'), K.ONE))
    assert RB.view(K.ADD, ex('-sin(x)')) == (K.ZERO, (ex('sin(x)'), K.MONE))
    tr = []
    env = fresh()
    assert RU.check(P.W_FREE, ex('y+pi'), env, x, tr) and not RU.check(P.W_FREE, x, env, x, tr)
    assert RU.check(P.W_FREE, ex('pi'), env, 0, tr) and not RU.check(P.W_FREE, ex('y'), env, 0, tr)
    assert RU.check(P.W_NUMB, ex('3/2+i'), env, x, tr) and not RU.check(P.W_NUMB, K.PI, env, x, tr)
    assert RU.check(P.W_INT, ex('-4'), env, x, tr) and not RU.check(P.W_INT, ex('1/2'), env, x, tr)
    assert not RU.check(P.W_LIN, ex('y'), env, x, tr)                # a = 0
    assert not RU.check(P.W_LIN, ex('x^2'), env, x, tr)
    assert not RU.check(P.W_LIN, ex('x'), env, 0, tr)                # no focus variable
    assert tr == [] and clean(env)
    assert RU.check(P.W_LIN, ex('3*y*x-2'), env, x, tr)
    assert env[slot('A')] == ex('3*y') and env[slot('B')] == ex('-2')
    assert sorted(tr) == [slot('A'), slot('B')]
    env = fresh()
    tr = []
    assert RU.check(P.W_QUAD, ex('2*x^2-3*x+5'), env, x, tr)
    assert (env[slot('A')], env[slot('B')], env[slot('C')]) == (ex('2'), ex('-3'), ex('5'))
    env[slot('A')] = ex('7')                        # A already bound to something else
    assert not RU.check(P.W_QUAD, ex('2*x^2+1'), env, x, [])


def test_constraints_and_binders():
    ok, b, _ = m1('A*x+R', 'y*x+1')
    assert ok and b == {'A': ex('y'), 'R': K.ONE}
    assert not m1('A*x+R', '3*x+1')[0]             # 3 is the pair's coefficient: use L
    assert not m1('A*x', 'x^2')[0]
    ok, b, _ = m1('sin(A*x)', 'sin(y*x)')
    assert ok and b['A'] == ex('y')
    assert not m1('sin(A*x)', 'sin(x^2)')[0]
    ok, b, _ = m1('M*x^P', '3/2*x^4')
    assert ok and b == {'M': ex('3/2'), 'P': ex('4')}
    assert not m1('M*x^P', '3/2*x^(1/2)')[0]
    assert not m1('M*x^P', 'pi*x^2')[0]             # pi is no NUM
    ok, b, _ = m1('sin(L)', 'sin(5-2*x)')            # sin(5-2x) = -sin(2x-5): no match
    assert not ok
    ok, b, _ = m1('sin(L)*R', 'sin(5-2*x)')
    assert ok and b['A'] == ex('2') and b['B'] == ex('-5') and b['R'] == K.MONE
    ok, b, _ = m1('Q^(-1)', '1/(x^2+y*x)')
    assert ok and (b['A'], b['B'], b['C']) == (K.ONE, ex('y'), K.ZERO)
    ok, b, _ = m1('sec(L)*tan(L)', 'sec(2*x+1)*tan(2*x+1)')
    assert ok and b['L'] == ex('2*x+1')
    assert not m1('sec(L)*tan(L)', 'sec(2*x+1)*tan(2*x)')[0]


def test_rest_takes_the_leftovers():
    ok, b, _ = m1('sin(U)^2+R', 'sin(x)^2+3*y+cos(x)+7')
    assert ok and b['R'] == ex('3*y+cos(x)+7')
    ok, b, _ = m1('sin(U)*R', '-6*sin(x)*y^2*e^x')
    assert ok and b['R'] == ex('-6*y^2*e^x')
    ok, b, _ = m1('sin(U)^2+R', 'sin(x)^2')
    assert ok and b['R'] == K.ZERO
    ok, b, _ = m1('U^2*R', 'x^2*y^2')               # distinct pairs; the first by order
    assert ok and {b['U'], b['R']} == {ex('x'), ex('y^2')}


def test_pattern_pairs_take_distinct_subject_pairs():
    assert not m1('sin(U)*sin(V)*R', 'sin(x)^2')[0]
    ok, b, _ = m1('sin(U)*sin(V)*R', 'sin(x)*sin(2*x)')
    assert ok and {b['U'], b['V']} == {ex('x'), ex('2*x')} and b['R'] == K.ONE
    assert not m1('sin(U)*cos(U)', 'sin(x)*cos(y)')[0]
    assert m1('sin(U)*cos(U)', 'sin(x)*cos(x)')[0]


def test_coefficient_wildcards():
    ok, b, _ = m1('N*sin(U)', '-sin(x)')
    assert ok and b['N'] == K.MONE
    ok, b, _ = m1('N*sin(U)', 'sin(x)')
    assert ok and b['N'] == K.ONE
    assert not m1('P*sin(U)', '1/2*sin(x)')[0]
    ok, b, _ = m1('N*ln(U)+M*ln(V)+R', '2*ln(x)-3*ln(y)+5')
    assert ok and b['R'] == ex('5')
    assert {(b['N'], b['U']), (b['M'], b['V'])} == {(ex('2'), sx()), (ex('-3'), ex('y'))}
    ok, b, _ = m1('N*cosh(U)^2-N*sinh(U)^2+R', '-2*sinh(x)^2+2*cosh(x)^2')
    assert ok and b['N'] == ex('2') and b['R'] == K.ZERO
    assert not m1('N*cosh(U)^2-N*sinh(U)^2+R', '2*sinh(x)^2+2*cosh(x)^2')[0]
    assert not m1('N*sin(U)^2+N*cos(U)^2+R', '3*sin(x)^2+2*cos(x)^2+x')[0]


def test_fixed_arity_nodes_and_leaves():
    ok, b, _ = m1('f(U,V)', 'f(x+1,y)')
    assert ok and b == {'U': ex('x+1'), 'V': ex('y')}
    assert not m1('f(U,V)', 'g(x,y)')[0] and not m1('f(U,V)', 'f(x)')[0]
    assert m1('pi*U', 'pi*y')[0] and not m1('pi*U', 'e*y')[0]
    ok, b, _ = m1('x^N', 'y^2')                     # x is the focus variable, not a wildcard
    assert not ok
    ok, b, _ = m1('x^N', 'y^2', x=ex('y'))
    assert ok and b == {'N': ex('2')}
    ok, b, _ = m1('abs(U)', 'abs(x-1)')
    assert ok and b['U'] == ex('x-1')


def test_solution_index_enumerates_bindings_in_a_fixed_order():
    p = pat('cos(U)^P*R')
    s = ex('cos(x)*cos(y)^2*cos(z)^3')
    sols = []
    for k in range(5):
        env = fresh()
        if not RB.match(p, s, env, sx(), k):
            assert clean(env)
            break
        sols.append((env[slot('U')], env[slot('P')]))
    assert len(sols) == 3 and len(set(sols)) == 3
    assert set(sols) == {(sx(), K.ONE), (ex('y'), ex('2')), (ex('z'), ex('3'))}
    again = []
    for k in range(3):
        env = fresh()
        RB.match(p, s, env, sx(), k)
        again.append((env[slot('U')], env[slot('P')]))
    assert again == sols


def test_maxstep_bounds_a_match(monkeypatch):
    ok, b, env = m1('U*V*W', 'a*b*c*d*f*g*h*k*m*n')     # 10*9*8 orders, all fail at the end
    assert not ok and clean(env)
    p = pat('sin(U)*cos(U)*R')
    s = ex('sin(x)*cos(2*x)*sin(2*x)')
    monkeypatch.setattr(RB, 'MAXSTEP', 6)
    env = fresh()
    assert not RB.match(p, s, env, sx()) and clean(env)
    monkeypatch.setattr(RB, 'MAXSTEP', 400)
    assert RB.match(p, s, env, sx())


def test_rest_is_rebuilt_exactly_with_the_constructors():
    ok, b, _ = m1('sin(U)*R', 'sqrt(2)*sin(x)*sqrt(y)')
    assert ok and b['R'] == ex('sqrt(2)*sqrt(y)')


# -- 2. rset (DESIGN 9.4) ------------------------------------------------------------------------

def test_rset_buckets_are_view_aware_and_in_file_order():
    rs = RU.rset('order')
    ps = [pat(s) for s, _, _ in rules_of('order')]
    view = (ps[0], ps[2])
    assert tuple(r[0] for r in rs[RU.VIEW]) == view
    assert tuple(r[0] for r in rs[K.SIN]) == (ps[0], ps[1], ps[2])
    assert tuple(r[0] for r in rs[K.COS]) == (ps[0], ps[2], ps[3])
    assert sorted(rs) == sorted([RU.VIEW, K.SIN, K.COS])
    assert rs[K.SIN][1][1:] == ('cos(2*U)', '')
    assert rs[K.SIN][2][1:] == ('cos(U)*R', 'P>=2')


def test_rset_caches_and_leaves_no_garbage():
    m = K.NN
    rs = RU.rset('trigsin')
    n = K.NN
    assert RU.rset('trigsin') is rs and K.NN == n
    assert K.RULECACHE['trigsin'] is rs
    no_garbage_above(m, ())
    for name in IDENT + ['zbasis']:
        RU.rset(name)
    no_garbage_above(m, ())
    assert K.RULECACHE['zbasis'] == K.RULECACHE['trigcos']


def test_rset_patterns_survive_keep_and_still_match():
    m = K.NN
    junk = ex('sin(x)^3+cos(y)+ln(z)')              # garbage below the patterns
    rs = RU.rset('tan2sincos')
    p0 = rs[K.TAN][0][0]
    assert p0 > junk
    K.keep(m, None)                                 # drops junk; patterns move down
    p1 = RU.rset('tan2sincos')[K.TAN][0][0]
    assert p1 < p0 and K.N[p1][0] == K.TAN
    assert rewrite(ex('tan(x)'), 'tan2sincos') == ex('sin(x)/cos(x)')


def test_rset_of_an_unknown_set_is_a_hard_error():
    with pytest.raises(AttributeError):
        RU.rset('nosuchset')


def test_rset_reads_the_module_named_in_where():
    rs = RU.rset('itab')                            # WHERE['itab'] -> MODS['itab'].ITAB
    assert len(rs[RU.VIEW]) == 7        # L^N, L^(-1), e^L, K^L, sec^2, sec*tan, Q^(-1)
    assert len(rs[K.SEC]) == 8 and len(rs[K.SIN]) == 8 and rs[K.SIN][4][1] == '-cos(L)/A'


# -- 3. guard_ok (DESIGN 9.2) ------------------------------------------------------------------

def genv(**kw):
    env = fresh()
    for k, v in kw.items():
        env[slot(k)] = ex(v)
    return env


def test_guard_folds_numeric_relations():
    assert RU.guard_ok('', fresh()) == 1
    assert RU.guard_ok('P>=2', genv(P='3')) == 1
    assert RU.guard_ok('P>=2', genv(P='1')) == 0
    assert RU.guard_ok('N!=-1', genv(N='-1')) == 0
    assert RU.guard_ok('N!=-1', genv(N='2')) == 1
    assert RU.guard_ok('P>=2,floor(P/2)=P/2', genv(P='4')) == 1
    assert RU.guard_ok('P>=2,floor(P/2)=P/2', genv(P='5')) == 0


def test_guard_decides_constants_numerically():
    assert RU.guard_ok('abs(T)<=1', genv(T='sqrt(2)/2')) == 1
    assert RU.guard_ok('abs(T)<=1', genv(T='sqrt(2)')) == 0
    assert RU.guard_ok('K>0', genv(K='pi')) == 1
    assert RU.guard_ok('K>0', genv(K='1-pi')) == 0
    assert RU.guard_ok('e^pi>pi^e', fresh()) == 1
    assert RU.guard_ok('pi<3', fresh()) == 0
    assert RU.guard_ok('pi!=3', fresh()) == 1
    assert RU.guard_ok('pi=3', fresh()) == 0
    assert RU.guard_ok('4*A*C-B^2>0', genv(A='1', B='1', C='1')) == 1
    assert RU.guard_ok('4*A*C-B^2>0', genv(A='1', B='sqrt(5)', C='1')) == 0


def test_guard_fails_on_symbols_nonreal_and_undefined():
    assert RU.guard_ok('K>0', genv(K='y')) == 0
    assert RU.guard_ok('K>0', genv(K='y^2+1')) == 0      # true, but not decided: missed only
    assert RU.guard_ok('U>0', genv(U='sqrt(-2)')) == 0    # not real
    assert RU.guard_ok('M>0', genv(M='i')) == 0           # rel_ raises Undefined: caught
    assert RU.guard_ok('1/(U-U)>0', genv(U='x')) == 0
    assert RU.guard_ok('ln(U)>0', genv(U='-1')) == 0


def test_guard_soft_prefix_lets_symbols_pass_and_still_decides_constants():
    assert RU.guard_ok('~U>0,V>0', genv(U='x', V='y+1')) == 1
    assert RU.guard_ok('~U>0,V>0', genv(U='x', V='1-pi')) == 0
    assert RU.guard_ok('~U>0,V>0', genv(U='2', V='pi')) == 1


def test_guard_near_zero_returns_the_difference():
    ok = RU.guard_ok('(1+sqrt(2))^2=3+2*sqrt(2)', fresh())
    assert type(ok) is tuple and ok[0] == RU.NEAR and ok[1] == K.EQ
    assert stub_normal(ok[2]) == K.ZERO
    ok = RU.guard_ok('e^(pi*sqrt(163))=640320^3+744', fresh())
    assert type(ok) is tuple and stub_normal(ok[2]) != K.ZERO
    two = RU.guard_ok('(1+sqrt(2))^2=3+2*sqrt(2),(1+sqrt(3))^2=4+2*sqrt(3)', fresh())
    assert two == 0                                 # two undecided relations: fail


# -- 4. g_rewrite and the root-only table application (DESIGN 9.7, 9.1) ---------------------------

def test_rewrite_fixpoint_returns_the_root_without_passes():
    e = ex('x^2+y')
    assert rewrite(e, 'tan2sincos') == e and TICKS[0] == 0


def test_rewrite_is_bottom_up_in_one_pass():
    r = rewrite(ex('tan(tan(x))+sec(x)'), 'tan2sincos')
    u = ex('sin(x)/cos(x)')
    assert r == K.add_([K.mul_(K.ONE, [(K.fn_(K.SIN, u), K.ONE), (K.fn_(K.COS, u), K.MONE)]),
                        ex('1/cos(x)')])
    assert TICKS[0] == 1


def test_rewrite_stops_on_a_cycle():
    r = rewrite(ex('sin(x)'), 'cycle')
    assert r == ex('cos(x)') and TICKS[0] == 1
    assert rewrite(ex('sin(x)'), 'cycle') == r      # deterministic


def test_rewrite_stops_after_maxpass():
    r = rewrite(ex('sin(x)'), 'grow')
    assert r == ex('sin(x+%d)' % RU.MAXPASS) and TICKS[0] == RU.MAXPASS


def test_rewrite_budget_is_a_soft_failure():
    e = ex('tan(x)+tan(y)+tan(z)')
    with pytest.raises(K.CasSoft):
        rewrite(e, 'tan2sincos', budget=2)
    assert drive(RU.g_rewrite(e, 'tan2sincos', sx(), 2)) is None
    assert rewrite(e, 'tan2sincos', budget=3) == ex('sin(x)/cos(x)+sin(y)/cos(y)+sin(z)/cos(z)')


def test_rewrite_keeps_only_its_result():
    e = ex('cos(x)^4*tan(y)+sin(x)^2*tan(x)')
    m = K.NN
    r = rewrite(e, 'trigsin')
    no_garbage_above(m, (r,))
    assert agree(e, r) > 3


def test_rewrite_compiles_a_set_inside_a_region():
    m = K.NN
    e = ex('tan(x)*y')
    m2 = K.NN
    r = rewrite(e, 'tan2sincos')
    r = K.keep(m2, r)                               # the region of a scoped call
    assert 'tan2sincos' in K.RULECACHE
    no_garbage_above(m, (e, r))
    assert r == ex('y*sin(x)/cos(x)')


def test_rewrite_first_rule_in_file_order_fires():
    def rw(s):
        return drive(RU.g_rewrite(ex(s), 'order', 0, 10))
    assert rw('y^2') == ex('ln(y)')                 # U^2*R wins over the later U^P*R
    assert rw('y^3') == ex('tan(y)')                # U^2*R fails: U^P*R, then cos(U)
    assert rw('sin(y)') == ex('tan(2*y)')           # sin(U), then cos(U) in the next pass
    assert rw('sin(y)^2') == ex('ln(tan(2*y))')     # bottom-up: the inner sin(y) first


def test_rewrite_tries_more_bindings_when_a_guard_fails():
    assert rewrite(ex('cos(x)*cos(y)^2'), 'alt') == ex('cos(x)*sin(y)^2')
    assert rewrite(ex('cos(x)*cos(y)^2'), 'trigsin') == ex('cos(x)*(1-sin(y)^2)')
    assert rewrite(ex('ln(2)-ln(3)+ln(x)'), 'lncollect') == ex('ln(2*x/3)')


def test_rewrite_skips_a_fire_that_the_constructors_undo():
    e = ex('x^2')                                   # U*U folds back to U^2: no fire
    assert rewrite(e, 'noop1') == e and TICKS[0] == 0
    assert rewrite(e, 'noop') == ex('cos(x)')       # so the next rule is tried
    e = ex('ln(2)-ln(3)')                           # ln(2/3) folds back to ln(2)-ln(3)
    assert rewrite(e, 'lncollect') == e and TICKS[0] == 0


def test_rewrite_near_guards_take_the_exact_test():
    assert rewrite(ex('sin(x)'), 'nearz') == ex('cos(x)') and NORMAL_CALLS
    assert rewrite(ex('sin(x)'), 'nearle') == ex('cos(x)')
    assert rewrite(ex('sin(x)'), 'nearlt') == ex('sin(x)')
    assert rewrite(ex('sin(x)'), 'nearne') == ex('sin(x)')
    del NORMAL_CALLS[:]
    assert rewrite(ex('sin(x)'), 'nearnz') == ex('sin(x)') and NORMAL_CALLS


def test_rewrite_undefined_guard_misses_and_undefined_rhs_is_soft():
    assert rewrite(ex('sin(x)'), 'undef') == ex('sin(x)')
    assert drive(RU.g_rewrite(ex('sin(x)'), 'badrhs', sx(), 10)) is None
    with pytest.raises(K.CasSoft):
        rewrite(ex('sin(x)'), 'badrhs')


def test_rewrite_accepts_a_compiled_set_and_no_focus_variable():
    rs = RU.rset('pyth')
    for x in (None, 0):
        assert drive(RU.g_rewrite(ex('2*sin(y)^2+2*cos(y)^2+x'), rs, x, 10)) == ex('x+2')


def test_apply_integral_table_heads_and_guards():
    cases = [('x', 'x^2/2'), ('1/x', 'ln(abs(x))'), ('x^(-3)', '-1/(2*x^2)'),
             ('e^(2*x+1)', 'e^(2*x+1)/2'), ('pi^x', 'pi^x/ln(pi)'),
             ('2^(3*x)', '2^(3*x)/(3*ln(2))'),
             ('sec(2*x)^2', 'tan(2*x)/2'), ('sec(2*x)*tan(2*x)', 'sec(2*x)/2'),
             ('1/(x^2+1)', 'atan(x)'), ('sqrt(3-x)', '-2*(3-x)^(3/2)/3'),
             ('1/(x^2+x+1)', '2*atan((2*x+1)/sqrt(3))/sqrt(3)')]
    for s, want in cases:
        assert apply1(ex(s), 'itab') == ex(want), s
    for s in ('sin(x^2)', 'y', 'e^(x^2)', '1/(x^2-1)', 'tan(x)'):
        assert apply1(ex(s), 'itab') is None, s
    assert apply1(ex('y^x'), 'itab') is None        # K>0 undecided for a symbol: missed


def test_apply_focus_variable_matters():
    assert apply1(ex('y'), 'itab', x=ex('y')) == ex('y^2/2')
    assert apply1(ex('cos(x*y)'), 'itab', x=ex('y')) == ex('sin(x*y)/x')


# -- 5. the 9.8 suite for every rule ------------------------------------------------------------

def _names(s):
    return [t[1] for t in P.lex(s.lstrip('~')) if t[0] == P.K_NAME]


def lint_rule(lhs, rhs, guard, kind):
    """The rule lint of DESIGN 20.3 for one rule; kind 'ident' or 'table'. A list of problems."""
    bad = []
    allowed = set('UVWABCKMNPLQR')
    for s in (lhs, rhs, guard):
        if not s:
            continue
        if any(ord(ch) > 126 for ch in s):
            bad.append('non-ASCII in %r' % s)
        for nm in _names(s):
            if nm != nm.lower() and (len(nm) != 1 or nm not in allowed):
                bad.append('%r: %r is no rule letter' % (s, nm))
            if kind == 'ident' and nm == 'x':
                bad.append('%r: an identity uses the focus variable x' % s)
        toks = P.ti_implicit(list(P.lex(s.lstrip('~'))))
        if any(t[4] & P.F_IMPL for t in toks):
            bad.append('%r: a missing explicit *' % s)
        try:
            P.rpn(P.lex(s.lstrip('~')))
        except K.CasError as e:
            bad.append('%r does not parse: %s' % (s, e))
    if bad:
        return bad
    p = pat(lhs)
    for i in A.postorder(p):
        t = K.N[i]
        if t[0] in (K.ADD, K.MUL):
            rest = 0
            other = 0
            for j in range(2, len(t), 2):
                w = K.N[t[j]]
                if w[0] == K.WILD and w[2] == P.W_REST and t[j + 1] == K.ONE:
                    rest += 1
                else:
                    other += 1
            if rest > 1 or other > 3:
                bad.append('%r: an AC node with %d pairs and %d R' % (lhs, other, rest))
    units = set()
    for i in A.postorder(p):
        t = K.N[i]
        if t[0] in (K.ADD, K.MUL):
            for j in range(2, len(t), 2):
                if K.N[t[j]][0] == K.WILD and K.N[t[j]][2] == P.W_REST and t[j + 1] == K.ONE:
                    units.add(t[j])
    for i in A.postorder(p):
        t = K.N[i]
        if t[0] >= K.COMP:
            for j in range(1, len(t)):
                w = K.N[t[j]]
                if w[0] == K.WILD and w[2] == P.W_REST and not (
                        t[0] in (K.ADD, K.MUL) and j >= 2 and j % 2 == 0 and
                        t[j + 1] == K.ONE):
                    bad.append('%r: R outside a unit pair of a sum or product' % lhs)
    if K.N[p][0] == K.WILD and K.N[p][2] == P.W_REST:
        bad.append('%r: a bare R' % lhs)
    if kind == 'ident' and K.N[p][0] in (K.ADD, K.MUL) and not (
            rest_parent(p) == K.N[p][0] and any(
                K.N[p][j] in units for j in range(2, len(K.N[p]), 2))):
        bad.append('%r: an ADD/MUL identity LHS without R at its head' % lhs)
    ll = letters(lhs)
    if ll & set('ABC') and ll & set('LQ'):
        bad.append('%r: A, B or C next to L or Q' % lhs)
    if 'T' in ll:
        bad.append('%r: T in a LHS' % lhs)
    have = set(ll)
    if 'L' in ll:
        have |= set('AB')
    if 'Q' in ll:
        have |= set('ABC')
    for s in (rhs, guard):
        miss = letters(s) - have
        if miss:
            bad.append('%r reads unbound letters %s' % (s, sorted(miss)))
    want = set(slot(L) for L in ll)
    if 'x' in _names(lhs):
        want.add(P.XSLOT)
    got = set(K.N[i][1] for i in A.postorder(p) if K.N[i][0] == K.WILD)
    if got != want:
        bad.append('%r: the pattern lost or gained letters (%r, %r)' % (lhs, got, want))
    if guard:
        m = K.NN
        g = P.inst(P.tcode(guard.lstrip('~')), None)
        rels = K.N[g][1:] if K.N[g][0] == K.LST else (g,)
        for r in rels:
            if not (K.EQ <= K.N[r][0] <= K.LE or r in (K.TRUE, K.FALSE)):
                bad.append('%r: %r is no relation' % (guard, K.N[r]))
        K.keep(m, None)
    return bad


@pytest.mark.parametrize('name,idx', RULES, ids=RULE_IDS)
def test_rule_lint(name, idx):
    lhs, rhs, guard = rules_of(name)[idx]
    assert lint_rule(lhs, rhs, guard, 'table' if name in TABLES else 'ident') == []


@pytest.mark.parametrize('name', IDENT)
def test_identity_sets_declare_a_measure(name):
    m = set_data(name)[0]
    st = [m]
    while st:
        x = st.pop()
        assert x[0] in MEASURES, (name, m)
        if x[0] == 'lex':
            assert len(x) >= 3
            st.extend(x[1:])
        elif x[0] != 'size':
            assert len(x) >= 2 and all(type(o) is int and o >= K.FN0 for o in x[1:]), m


def test_rule_lint_catches_bad_rules():
    assert lint_rule('cos(U)', 'sin(U)', '', 'ident') == []
    assert lint_rule('cos(U)^2*R', '(1-sin(U)^2)*R', '', 'ident') == []
    assert any('without R' in b for b in lint_rule('cos(U)^2', '1-sin(U)^2', '', 'ident'))
    assert any('without R' in b for b in lint_rule('cos(U)*sin(V)', 'U', '', 'ident'))
    assert any('explicit' in b for b in lint_rule('2sin(U)*R', 'R', '', 'ident'))
    assert any('rule letter' in b for b in lint_rule('sin(Z)', 'Z', '', 'ident'))
    assert any('next to' in b for b in lint_rule('A*L', 'L', '', 'table'))
    assert any('unbound' in b for b in lint_rule('sin(U)', 'V', '', 'ident'))
    assert any('AC node' in b for b in lint_rule('U*V*W*K*R', 'R', '', 'ident'))
    assert any('unit pair' in b for b in lint_rule('sin(R)*U', 'U', '', 'ident'))
    assert any('focus' in b for b in lint_rule('sin(x)*R', 'R', '', 'ident'))
    assert any('relation' in b for b in lint_rule('sin(U)', 'U', 'U+1', 'ident'))
    assert any('lost' in b for b in lint_rule('U-U+V', 'V', '', 'ident'))


@pytest.mark.parametrize('name,idx', RULES, ids=RULE_IDS)
def test_rule_self_match_and_soundness(name, idx):
    """9.8 tests 1 and 2: every sampled instance matches, its bindings rebuild it, and the
    rewrite is sound (identities: lhs = rhs at real points where the input is real, complex
    points too unless a policy rule; tables: d/dx(c*rhs) = c*g, the integrand)."""
    pol = policy_rule(name, idx)
    compared = 0
    for it in sample(name, idx):
        if name in TABLES:
            F = K.mul_(it.c, [(it.r, K.ONE)])
            compared += deriv_agree(F, it.s)
        else:
            compared += agree(it.s, it.r, pol)
    assert compared >= 3


@pytest.mark.parametrize('name,idx', IRULES, ids=IRULE_IDS)
def test_rule_measure_decreases(name, idx):
    """9.8 test 3: measure(rhs) < measure(lhs) on random instances (a fire that the
    constructors fold back to the input is no fire, 9.7)."""
    m = set_data(name)[0]
    n = 0
    for it in sample(name, idx, want=20, tries=200):
        if it.noop:
            continue
        a = measure(m, it.s)
        b = measure(m, it.r)
        assert b < a, (name, idx, K.N[it.s], a, K.N[it.r], b)
        n += 1
    assert n >= MINGOOD


def single_set(name, idx):
    """A one-rule test set (key s_<name>_<idx>) holding rule idx of set name."""
    key = 's_%s_%d' % (name, idx)
    lhs, rhs, guard = rules_of(name)[idx]
    setattr(TESTSETS, key.upper(), (set_data(name)[0], lhs, rhs, guard))
    RU.WHERE[key] = 'test'
    return key


def contexts(lhs, s):
    """9.8 test 5: the instance alone (its head may differ from the pattern's through the
    identity defaults), times 3, times a factor, plus a term. The factor is sin(x) unless the
    LHS itself mentions sin (sin(x) would then merge into the instance's own sin pairs)."""
    f = 'atan(x+3)' if 'sin' in lhs else 'sin(x)'
    return [s, K.mul_(ex('3'), [(s, K.ONE)]), K.mul_(K.ONE, [(ex(f), K.ONE), (s, K.ONE)]),
            K.add_([s, ex('atan(y)')])]


@pytest.mark.parametrize('name,idx', IRULES, ids=IRULE_IDS)
def test_rule_fires_in_context(name, idx):
    """9.8 test 5: the rule alone fires through g_rewrite on its instance, x3, x a factor and
    inside a sum; its whole set rewrites each of them, and the instance times sin(x), soundly
    (bucket lookups and missing R would make a rule skip silently)."""
    key = single_set(name, idx)
    pol = policy_rule(name, idx)
    lhs = rules_of(name)[idx][0]
    done = 0
    for it in sample(name, idx):
        if it.noop:
            continue
        cs = contexts(lhs, it.s)
        for c in cs:
            r = rewrite(c, key)
            assert r != c, (name, idx, 'did not fire on', K.N[c])
            agree(c, r, pol)
        for c in cs + [K.mul_(K.ONE, [(ex('sin(x)'), K.ONE), (it.s, K.ONE)])]:
            r = rewrite(c, name)
            assert r != c, (name, idx, 'the set did not fire on', K.N[c])
            agree(c, r, pol)
        done += 1
        if done == 2:
            break
    assert done >= 1


@pytest.mark.parametrize('name,idx', TRULES, ids=TRULE_IDS)
def test_table_first_match_is_sound(name, idx):
    """For a table, apply1 on every instance (after split_const) fires the first rule whose
    guard holds, and the result is an antiderivative."""
    for it in sample(name, idx):
        r = apply1(it.g, name)
        assert r is not None
        deriv_agree(K.mul_(it.c, [(r, K.ONE)]), it.s)


def test_table_heads_differ_from_the_pattern():
    """9.8 test 5 for tables: a bare x against L^N, a bare exponential, a bare reciprocal."""
    for s in ('x', 'e^x', '1/x', 'x^2', 'sec(x)', 'cos(x)'):
        e = ex(s)
        r = apply1(e, 'ditab')
        assert r is not None, s
        assert deriv_agree(r, e) >= 3


# -- derivative and inverse templates (DESIGN 9.3; 9.8 test 2) ------------------------------------

def dt_tables():
    out = [('design', DDT)]
    if isinstance(REAL_DT, dict):
        out.append(('diff.DT', REAL_DT))
    return out


@pytest.mark.parametrize('label,table', dt_tables(), ids=[t[0] for t in dt_tables()])
def test_derivative_templates_equal_sympy_diff(label, table):
    X_ = sympy.Symbol('x', real=True)
    for op in sorted(table):
        tmpl = table[op]
        assert not any(t[4] & P.F_IMPL for t in P.ti_implicit(list(P.lex(tmpl)))), tmpl
        assert set(_names(tmpl)) <= {'U', 'sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'sqrt',
                                     'cosh', 'sinh', 'tanh', 'abs', 'sign'}, tmpl
        f = ex(tmpl, U=sx())
        F = K.fn_(op, sx())
        dF = sympy.diff(to_sympy(F), X_)
        n = 0
        for x0 in ('0.37', '0.81', '-0.45', '1.3', '-2.1', '2.7'):
            fv, fr = None, True
            try:
                fv, fr = mev(f, {'x': mpmath.mpf(x0)})
            except Bad:
                continue
            if not fr:
                continue
            if dF.has(sympy.Derivative):
                d = mpmath.diff(lambda t: mev(F, {'x': t})[0], mpmath.mpf(x0))
            else:
                d = sympy.N(dF.subs(X_, sympy.Rational(x0)), 30)
                d = mpmath.mpc(complex(d)) if d.is_finite else None
            if d is None:
                continue
            assert close(fv, d, mpmath.mpf('1e-12')), (label, op, x0, fv, d)
            n += 1
        assert n >= 2, (label, op)


def inv_tables():
    out = [('design', DINV)]
    if isinstance(REAL_INV, dict):
        out.append(('solve.INV', REAL_INV))
    return out


@pytest.mark.parametrize('label,table', inv_tables(), ids=[t[0] for t in inv_tables()])
def test_inverse_templates_invert(label, table):
    """f(rhs) = T wherever the guard holds; the guard is decided by guard_ok, so
    sin(x) = sqrt(2)/2 qualifies (a guard with radicals, 20.12)."""
    for op in sorted(table):
        tmpls, guard = table[op]
        for s in tmpls + ((guard,) if guard else ()):
            assert letters(s) <= {'T'} and not (set(_names(s)) & set('UVWABCKMNPLQR')), s
            assert not any(t[4] & P.F_IMPL for t in P.ti_implicit(list(P.lex(s)))), s
        hits = 0
        for tv in POOLS['T']:
            env = fresh()
            env[P.TSLOT] = ex(tv)
            if not guard_holds(guard, env):
                continue
            for s in tmpls:
                u = P.inst(P.tcode(s), env)
                assert agree(K.fn_(op, u), env[P.TSLOT], True) >= 1, (label, op, s, tv)
            hits += 1
        assert hits >= 2, (label, op)
    env = fresh()
    env[P.TSLOT] = ex('sqrt(2)/2')
    assert guard_holds(DINV[K.SIN][1], env)
    sols = [P.inst(P.tcode(s), env) for s in DINV[K.SIN][0]]
    assert sols == [ex('pi/4'), ex('3*pi/4')]


# -- coverage (9.8 test 4) -------------------------------------------------------------------------

CORPUS = ('sin(x)^2+cos(x)^2', 'tan(x)*cos(x)', 'sec(x)^2-tan(x)^2', 'csc(x)^2-cot(x)^2',
          'cosh(x)^2-sinh(x)^2', 'sin(x)*cos(x)', 'sin(x)*sin(3*x)', 'cos(x)*cos(2*x)',
          'sin(x)^4', 'cos(x)^3', 'cot(x)/csc(x)', '2*ln(x)+ln(y)', 'ln(2*pi)',
          'ln(sqrt(pi))', '2^x*3^x', 'sin(x)^3*cos(x)^2', '1-sin(x)^2')


def coverage(corpus):
    """{(set, rule index): times the rule alone changed a corpus expression}."""
    hit = {}
    for name in IDENT:
        for idx in range(len(rules_of(name))):
            key = single_set(name, idx)
            n = 0
            for s in corpus:
                e = ex(s)
                if rewrite(e, key) != e:
                    n += 1
            hit[(name, idx)] = n
    return hit


@pytest.mark.slow
def test_coverage_report():
    hit = coverage(CORPUS)
    cold = sorted(k for k in hit if not hit[k])
    if cold:
        warnings.warn('rules that never fired on the corpus: %r' % (cold,))
    assert len(cold) < len(hit)


# -- denesting and the ln split (ident.py) -----------------------------------------------------

@pytest.mark.parametrize('s,want', [
    ('sqrt(3+2*sqrt(2))', '1+sqrt(2)'),
    ('1/sqrt(3+2*sqrt(2))', '1/(1+sqrt(2))'),
    ('sqrt(5+2*sqrt(6))', 'sqrt(2)+sqrt(3)'),
    ('sqrt(2-sqrt(3))', 'sqrt(6)/2-sqrt(2)/2'),
    ('sqrt(1/2+sqrt(2)/3)', 'sqrt(6)/6+sqrt(3)/3'),
    ('(3+2*sqrt(2))^(3/2)', '(1+sqrt(2))^3'),
    ('sin(sqrt(3+2*sqrt(2)))+x', 'sin(1+sqrt(2))+x'),
    ('sqrt(2+sqrt(2))', 'sqrt(2+sqrt(2))'),
    ('sqrt(3+2*sqrt(2))^2', '3+2*sqrt(2)'),
    ('sqrt(x+2*sqrt(2))', 'sqrt(x+2*sqrt(2))'),
    ('(-3+2*sqrt(2))^(1/2)', '(-3+2*sqrt(2))^(1/2)'),
])
def test_denest(s, want):
    e = ex(s)
    r = ID.denest(e)
    assert r == ex(want)
    assert agree(e, r) >= 1


def test_denest_random_squares():
    rng = random.Random(7)
    for _ in range(40):
        a = sympy.Rational(rng.randint(1, 9), rng.randint(1, 4))
        b = sympy.Rational(rng.randint(1, 9), rng.randint(1, 4))
        p, q = rng.choice((2, 3, 5, 7)), rng.choice((11, 13, 6, 10))
        # (a*sqrt(p) + b*sqrt(q))^2 = a^2 p + b^2 q + 2ab sqrt(pq)
        s = 'sqrt(%s+%s*sqrt(%d))' % (a ** 2 * p + b ** 2 * q, 2 * a * b, p * q)
        e = ex(s)
        r = ID.denest(e)
        assert r == ex('%s*sqrt(%d)+%s*sqrt(%d)' % (a, p, b, q)), s
        assert agree(e, r) >= 1


@pytest.mark.parametrize('s,want', [
    ('ln(6)', 'ln(2)+ln(3)'),
    ('ln(6)+ln(2)', '2*ln(2)+ln(3)'),
    ('x*ln(30)', 'x*(ln(2)+ln(3)+ln(5))'),
    ('ln(7)', 'ln(7)'),
    ('ln(36)', '2*(ln(2)+ln(3))'),
    ('ln(2/15)', 'ln(2)-ln(3)-ln(5)'),
    ('ln(x)+ln(12)', 'ln(x)+2*ln(2)+ln(3)'),
    ('ln(x)', 'ln(x)'),
])
def test_lnsplit(s, want):
    e = ex(s)
    r = ID.lnsplit(e)
    assert r == ex(want)
    assert agree(e, r) >= 1


def test_lnsplit_leaves_floats_and_big_cofactors():
    e = K.fn_(K.LN, K.flt(1.5))
    assert ID.lnsplit(e) == e
    big = 1000003 * 1000033                         # both prime, above the trial bound
    e = K.fn_(K.LN, K.num(2 * big))
    r = ID.lnsplit(e)
    assert r == K.add_([K.fn_(K.LN, K.TWO), K.fn_(K.LN, K.num(big))])


# -- properties (DESIGN 20.7) ----------------------------------------------------------------------

def gen_subjects(seed, n, funcs=('sin', 'cos', 'tan', 'sec', 'ln', 'sqrt', 'exp', 'sinh',
                                 'cosh', 'cot', 'csc')):
    g = gen.Gen(seed, syms=('x', 'y'), funcs=funcs, maxint=4)
    out = []
    while len(out) < n:
        try:
            out.append(gen.build(g.tree(3), K))
        except K.CasSoft:
            continue
    return out


def test_matcher_undo_and_reproduction_on_generated_subjects():
    """A failed match leaves env clean; a match's bindings rebuild the subject exactly."""
    subs = gen_subjects(11, 24)
    hits = 0
    for name in ALLSETS:
        for lhs, rhs, guard in rules_of(name):
            p = pat(lhs)
            for s in subs:
                for g in (s, K.mul_(K.ONE, [(s, K.ONE), (ex('sin(x)^2'), K.ONE)])):
                    env = fresh()
                    if RB.match(p, g, env, sx()):
                        assert P.inst(P.tcode(lhs), env) == g, (lhs, K.N[g])
                        hits += 1
                    else:
                        assert clean(env), (lhs, K.N[g])
    assert hits > 20


@pytest.mark.parametrize('name', IDENT)
def test_rewrite_reaches_a_sound_fixpoint_on_generated_inputs(name):
    m = set_data(name)[0]
    pol = any(g.startswith('~') for _, _, g in rules_of(name))
    for e in gen_subjects(zlib.crc32(name.encode()), 25):
        m0 = K.NN
        r = rewrite(e, name)
        assert TICKS[0] < RU.MAXPASS, (name, K.N[e])
        assert rewrite(r, name) == r                # a fixpoint
        assert not (measure(m, r) > measure(m, e)), (name, K.N[e], K.N[r])
        agree(e, r, pol)
        no_garbage_above(m0, (e, r))


@pytest.mark.parametrize('kind', ['tan', 'cos2', 'sum', 'denest', 'lnsplit'])
def test_depth_does_not_grow_with_nesting(evodepth, kind):
    def build(n):
        e = sx()
        if kind == 'denest':
            e = ex('sqrt(3+2*sqrt(2))')
        elif kind == 'lnsplit':
            e = ex('ln(6)')
        for _ in range(n):
            if kind == 'tan':
                e = K.fn_(K.TAN, e)
            elif kind == 'cos2':
                e = K.mul_(K.ONE, [(K.fn_(K.COS, e), K.TWO)])
            elif kind in ('denest', 'lnsplit'):
                e = K.fn_(K.SIN, K.add_([e, sx()]))
            else:
                e = K.add_([K.mul_(K.ONE, [(K.fn_(K.SIN, e), K.TWO)]),
                            K.mul_(K.ONE, [(K.fn_(K.COS, e), K.TWO)])])
        return e

    def run(n):
        K.reset()
        e = build(n)
        if kind == 'denest':
            return ID.denest(e)
        if kind == 'lnsplit':
            return ID.lnsplit(e)
        name = {'tan': 'tan2sincos', 'cos2': 'trigsin', 'sum': 'pyth'}[kind]
        return rewrite(e, name)
    depths = []
    for n in (1, 8, 32):
        _, d, _ = evodepth.measure(run, n)
        depths.append(d)
    assert depths[0] == depths[1] == depths[2] <= 7, depths
