"""The rule engine (DESIGN 9, task T1.9): rules.py (rset, guard_ok, g_rewrite, g_apply),
rulesb.py (match, check, view) and ident.py (the identity sets, denest).

- matcher cases, the AC backtrack of 9.5, constraints, binders, coefficient wildcards, caps;
- rset buckets and caching; guard_ok, including the NEAR protocol of 9.2/9.7;
- g_rewrite termination (fixpoint, cycle, MAXPASS, budget) and regions; g_apply;
- the 9.8 suite for every rule of every set: the rule lint (20.3), self-match, soundness
  (mpmath at 30 digits), measure, context match; derivative and inverse templates;
- denesting; properties (matcher undo, fixpoints on generated inputs); nesting invariance.

The runner is replaced by a stub (MODS, TICK), so these tests do not depend on run.py; the
exact zero test of the NEAR protocol (norm.normal, T1.10) is a SymPy stub.
"""
import importlib
import random
import sys
import types

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

# -- the design's tables (DESIGN 9.2, 9.3) as fixtures; the real modules are tested too when
# they exist (itab.py: T2.4, diff.py: T2.1, solve: T1.12) --------------------------------------
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
    try:
        return importlib.import_module(name)
    except Exception:
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
    NEARLT=(('size',), 'sin(U)', 'cos(U)', '(1+sqrt(2))^2<3+2*sqrt(2)'),
    NEARNZ=(('size',), 'sin(U)', 'cos(U)', 'e^(pi*sqrt(163))=640320^3+744'),
    ORDER=(('size',), 'U^2*R', 'ln(U)*R', '', 'sin(U)', 'sin(2*U)', '',
           'sin(U)^P*R', 'cos(U)*R', 'P>=3', 'cos(U)', 'tan(U)', ''),
    UNDEF=(('size',), 'sin(U)', 'cos(U)', '1/(U-U)>0'),
)
TESTKEYS = ('ditab', 'ritab', 'cycle', 'grow', 'nearz', 'nearlt', 'nearnz', 'order', 'undef')


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
    MODS={'rulesb': RB, 'ident': ID, 'itab': types.SimpleNamespace(ITAB=DITAB),
          'test': TESTSETS, 'norm': types.SimpleNamespace(normal=stub_normal)},
    TICK=TICK)


@pytest.fixture(autouse=True)
def stub_run(monkeypatch):
    monkeypatch.setattr(RU, 'R', STUB)
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


def apply1(e, rs, x=None):
    return drive(RU.g_apply(e, rs, sx() if x is None else x), True)


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


# -- measures (DESIGN 9.2); test-side only ---------------------------------------------------------

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


def measure(m, e):
    kind = m[0]
    if kind == 'size':
        return A.size(e)
    if kind == 'lex':
        return tuple(measure(s, e) for s in m[1:])
    ops = m[1:]
    total = 0
    if kind == 'count':
        for i in _walk(e):
            if K.N[i][0] in ops:
                total += 1
        return total
    if kind == 'pow':                          # bare occurrences count as exponent 1
        st = [e]
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
    if kind == 'excess':
        for i in _walk(e):
            t = K.N[i]
            if t[0] == K.MUL:
                s = 0
                for j in range(2, len(t), 2):
                    if K.N[t[j]][0] in ops:
                        s += _posint(t[j + 1])
                total += max(0, s - 1)
        return total
    raise ValueError(m)


# -- the rule sets under test ------------------------------------------------------------------------

def ident_sets():
    out = []
    for name in sorted(dir(ID)):
        v = getattr(ID, name)
        if name.isupper() and type(v) is tuple and len(v) >= 4 and type(v[0]) is tuple:
            out.append(name.lower())
    return out


IDENT = ident_sets()
ALLSETS = [(n, 'ident') for n in IDENT] + [('ditab', 'itab')]
if REAL_ITAB:
    ALLSETS.append(('ritab', 'itab'))


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
for _n, _k in ALLSETS:
    for _i in range(len(rules_of(_n))):
        RULES.append((_n, _k, _i))
RULE_IDS = ['%s-%d' % (n, i) for n, k, i in RULES]

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
LETTERS = 'UVWABCKMNPLQRT'


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
                if w[0] == K.WILD and w[2] == RB.REST:
                    return t[0]
    return None


