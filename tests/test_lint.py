"""The subset lint (DESIGN.md 17.4, 20.3; device-python 13) on good and bad snippets and on
src/ itself.

This file also holds the self-tests of the other M0.1 support modules that have no test file
of their own in the DESIGN 21.3 ownership table: the invariant scanner (invariants.py, 8.9)
and the random expression generator (gen.py, 20.7).
"""
import math
import os
import textwrap

import pytest

import gen
import invariants as INV
import lint

# -- subset lint: snippets --------------------------------------------------------------------


def errs(src, module='alg'):
    return lint.lint(textwrap.dedent(src).lstrip('\n'), module + '.py', module)


def has(es, *needles):
    for e in es:
        if all(n in e for n in needles):
            return True
    return False


GOOD = '''
    #@L 7
    import math
    import gc
    import array
    import node as K

    TABLE = (1, 2, 3)
    NAMES = {'a': 1}


    class CasError(Exception):
        pass


    def f(x, y=None, *args):
        out = []
        for i in range(len(x)):
            out.append(x[i] // 2)
        s = '%d,%s' % (1, 'a')
        d = {}
        d[1] = 2
        for k in sorted(d):
            out.append(k)
        for k in d:                    #@unordered-ok (summed)
            out.append(k)
        try:
            v = math.sqrt(2.0) * math.pi
        except ValueError as e:
            raise CasError('x')
        return (out, s, v, K.N, gc.collect(), array.array('i', [0]))
'''


def test_good_snippet_is_clean():
    assert errs(GOOD) == []
    assert errs('a = x[1:4]\nb = x[1:4:1]\nc = x[1:4:None]\n') == []


@pytest.mark.parametrize('src, needle', [
    ('x = f"{a}"\n', 'f-string'),
    ('def f(a, *, b):\n    pass\n', 'keyword-only'),
    ('def f(a: int):\n    pass\n', 'annotation'),
    ('def f(a) -> int:\n    pass\n', 'return annotation'),
    ('x: int = 1\n', 'variable annotation'),
    ('x = [*a, *b]\n', '*unpacking'),
    ('x = {**a}\n', '{**d}'),
    ('f(*a, *b)\n', 'more than one *args'),
    ('f(*a, b)\n', 'positional argument after *args'),
    ('f(**a, **b)\n', 'more than one **kwargs'),
    ('raise E from x\n', 'raise ... from'),
    ('y = (x := 1)\n', '3.4 syntax'),
    ('n = 1_000\n', 'underscore'),
    ("s = 'pi \u03c0'\n", 'non-ASCII'),
    ('import re\n', "module 're'"),
    ('import functools\n', "module 'functools'"),
    ('n = x.bit_length()\n', '.bit_length'),
    ('n = s.ljust(3)\n', '.ljust'),
    ('r = reversed(x)\n', "'reversed'"),
    ('s = frozenset(x)\n', "'frozenset'"),
    ('v = eval(s)\n', "'eval'"),
    ("if __name__ == '__main__':\n    pass\n", '__main__'),
    ('x = [i for i in y]\n', 'comprehension'),
    ('x = a[::2]\n', 'stepped slice'),
    ('x = a[::-1]\n', 'stepped slice'),
    ('x = a[1:n:k]\n', 'stepped slice'),
    ('x = {i: 1 for i in y}\n', 'comprehension'),
    ('x = sum(i for i in y)\n', 'generator expression'),
    ('f = lambda x: x\n', 'lambda'),
    ('y = sorted(x, key=len)\n', 'key='),
    ('y = list(map(g, x))\n', 'map() with a Python callable'),
    ('class A:\n    def m(self):\n        pass\n', 'only empty Exception subclasses'),
    ('class A(Exception):\n    x = property(f)\n', 'only empty Exception subclasses'),
    ('with f() as g:\n    pass\n', 'with statement'),
    ('def g():\n    yield from h()\n', 'yield from'),
    ('async def g():\n    pass\n', 'async'),
    ('from math import sqrt\n', "'from math import"),
    ('from node import *\n', "'from node import"),
    ('import node\n', 'the fixed alias is K'),
    ('import node as N\n', 'the fixed alias is K'),
    ('import polyb as PB\n', 'the fixed alias is POB'),
    ('import mystery as Q\n', 'unknown module'),
    ('import ti_system\n', 'only ui, draw, menu and casevo import ti_*'),
    ('d = {}\nfor k in d:\n    pass\n', 'iteration over a dict or set'),
    ('for k in x.items():\n    pass\n', 'iteration over a dict or set'),
    ('s = set()\nt = tuple(s)\n', 'tuple() over a dict or set'),
    ("d = {}\nw = ','.join(d)\n", 'join() over a dict or set'),
    ('v = round(x, 2)\n', 'round()'),
    ('v = repr(x)\n', 'repr()'),
    ("v = '%.3g' % x\n", 'float formatting'),
    ('v = math.log10(x)\n', 'log10'),
    ('import math\nv = math.inf\n', 'math.inf is not in the device math module'),
    ('v = s.startswith(("a", "b"))\n', 'startswith() with a tuple'),
    ('v = s.rsplit(None, 1)\n', 'rsplit(None, n)'),
    ('def f():\n    return f()\n', 'direct recursion'),
    ('def g():\n    yield 1\n    raise StopIteration\n', 'raise StopIteration'),
    ('print(1, file=x)\n', 'print(file=...)'),
    ('def __add__(a, b):\n    pass\n', 'dunder function'),
    ('n = x.__len__()\n', '.__len__'),
    ('@deco\ndef f():\n    pass\n', 'decorator'),
    ('__slots__ = ()\n', "'__slots__'"),
])
def test_bad_snippets(src, needle):
    es = errs(src)
    assert has(es, needle), es


def test_div_in_exact_modules_only():
    src = 'a = b / c\n'
    assert has(errs(src, 'node'), "'/' in an exact module")
    assert has(errs(src, 'polyb'), "'/' in an exact module")      # parts count by family
    assert errs(src, 'alg') == []                                   # nev works in floats
    assert errs('a = b / c   #@float-ok\n', 'node') == []
    assert errs('a = b // c\n', 'node') == []


def test_markers_silence_what_they_name():
    assert errs('d = {}\nfor k in d:   #@unordered-ok\n    pass\n') == []
    assert errs('v = round(x)   #@float-ok\n') == []


def test_ti_imports_in_ui_modules():
    assert errs('import ti_system\nimport ti_draw as TD\n', 'draw') == []
    assert errs('import ti_system\n', 'casevo') == []
    assert errs('import ti_system\n', 'menub') == []
    assert has(errs('import ti_system\n', 'node'), 'only ui, draw, menu')


def test_ti_graphics_is_not_used():
    # setColor(r, g, b) raised TypeError on the EVO; the UI draws through ti_draw
    for mod in ('ui', 'draw', 'casevo'):
        assert has(errs('import ti_graphics as G\n', mod), 'draw through ti_draw')


def test_device_names_mode():
    src = 'import CVNODE as K\nimport math\n'
    assert lint.lint(src, 'CVALG.py', 'CVALG', device_names=True) == []
    assert has(lint.lint('import cvnode as K\n', 'CVALG.py', 'CVALG', device_names=True),
               'bad device module name')


def test_alias_table():
    assert lint.alias_for('node') == 'K'
    assert lint.alias_for('polyc') == 'POC'
    assert lint.alias_for('integ2b') == 'I2B'
    assert lint.alias_for('rulesb') == 'RUB'
    assert lint.alias_for('casevo') is None
    assert lint.family('integ2b') == 'integ2'


SRC_FILES = lint.device_files(lint.SRC)


@pytest.mark.parametrize('path', SRC_FILES, ids=[os.path.basename(p) for p in SRC_FILES])
def test_src_lint_clean(path):
    assert lint.lint_file(path) == []


# -- invariants.py self-tests -----------------------------------------------------------------

OP = INV.OPS


class FakeK(object):
    """A minimal node table that interns like DESIGN 5.10, with the reference hash."""

    def __init__(self, nmax=96, nb=16):
        for k in OP:
            setattr(self, k, OP[k])
        self.N = [None] * nmax
        self.H = [0] * nmax
        self.V = [0] * nmax
        self.NX = [0] * nmax
        self.B = [0] * nb
        self.NN = 1
        self.SYMN = []
        self.SYMI = {}
        self.RULECACHE = {}
        for name, _, (oname, *pay) in INV.PREALLOC:
            if oname == 'LN':
                t = (OP['LN'], self.TEN)
            else:
                t = (OP[oname],) + tuple(pay)
            setattr(self, name, self.mk(t))
        self.BASE = self.NN

    def mk(self, t):
        h = INV.ref_hash(t, self.H)
        v = 0
        if t[0] >= OP['COMP']:
            for c in t[1:]:
                v |= self.V[c]
        elif t[0] == OP['SYM']:
            bit = self.SYMI.get(t[1])
            if bit is None:
                bit = len(self.SYMN)
                self.SYMN.append(t[1])
                self.SYMI[t[1]] = bit
            v = 1 << bit
        b = h & (len(self.B) - 1)
        i = self.B[b]
        while i:
            if self.H[i] == h and self.N[i] == t:
                return i
            i = self.NX[i]
        i = self.NN
        self.N[i] = t
        self.H[i] = h
        self.V[i] = v
        self.NX[i] = self.B[b]
        self.B[b] = i
        self.NN = i + 1
        return i

    def num(self, a, b=0, d=1):
        return self.mk((OP['NUM'], a, b, d))

    def sym(self, s):
        return self.mk((OP['SYM'], s))

    def pairs(self, op, head, prs):
        """An ADD/MUL with its pairs in canonical order."""
        terms = INV.canonical_order([p[0] for p in prs], self.N, self.H)
        co = dict(prs)
        t = [op, head]
        for x in terms:
            t.append(x)
            t.append(co[x])
        return self.mk(tuple(t))

    def negfirst(self, u):
        t = self.N[u]
        if t[0] == OP['NUM']:
            return t[1] < 0 or (t[1] == 0 and t[2] < 0)
        if t[0] == OP['MUL']:
            return self.N[t[1]][1] < 0
        if t[0] == OP['ADD']:
            return self.N[t[3]][1] < 0
        return False

    def reset(self):
        for i in range(self.BASE, self.NN):
            self.N[i] = None
        self.NN = self.BASE


@pytest.fixture
def K():
    return FakeK()


def valid_table(K):
    x = K.sym('x')
    y = K.sym('y')
    three = K.num(3)
    sum_ = K.pairs(OP['ADD'], K.ONE, [(x, K.ONE), (y, three)])                 # 1 + x + 3y
    sq2 = K.mk((OP['MUL'], K.ONE, K.TWO, K.HALF))                               # sqrt(2)
    sq = K.mk((OP['MUL'], K.ONE, x, K.TWO))                                      # x^2
    prod = K.pairs(OP['MUL'], three, [(x, K.TWO), (y, K.MONE)])                 # 3x^2/y
    sinx = K.mk((OP['SIN'], x))
    absx = K.mk((OP['ABS'], sum_))
    ex = K.mk((OP['MUL'], K.ONE, K.E, x))                                        # e^x
    ln2 = K.mk((OP['LN'], K.TWO))
    eq = K.mk((OP['EQ'], sum_, K.ZERO))
    lst = K.mk((OP['LST'], eq, sinx))
    return dict(x=x, y=y, sum=sum_, sq2=sq2, sq=sq, prod=prod, sinx=sinx, absx=absx, ex=ex,
                ln2=ln2, lst=lst)


def test_invariants_valid_table_is_clean(K):
    valid_table(K)
    assert INV.scan(K) == []


def kinds(es):
    out = set()
    for e in es:
        out.add(e[1:e.index(']')])
    return out


def test_invariants_hash_mask_slots(K):
    v = valid_table(K)
    K.H[v['sq']] ^= 1
    assert 'hash' in kinds(INV.scan(K))
    K.H[v['sq']] ^= 1
    K.V[v['sinx']] = 0
    assert 'mask' in kinds(INV.scan(K))
    K.V[v['sinx']] = K.V[v['x']]
    K.N[K.NN] = (OP['SYM'], 'z')
    assert kinds(INV.scan(K)) == {'slots'}


def test_invariants_numbers(K):
    K.mk((OP['NUM'], 2, 0, 4))
    K.mk((OP['NUM'], 1, 0, -2))
    K.mk((OP['FLT'], -0.0, 0.0))
    es = INV.scan(K)
    assert len([e for e in es if e.startswith('[num]')]) == 3


def test_invariants_add(K):
    x = K.sym('x')
    y = K.sym('y')
    K.mk((OP['ADD'], K.ZERO, x, K.TWO))                                  # one pair, c == 0
    K.pairs(OP['ADD'], K.ONE, [(x, K.ZERO), (y, K.ONE)])                 # zero coefficient
    s = K.pairs(OP['ADD'], K.ONE, [(x, K.ONE), (y, K.ONE)])
    K.pairs(OP['ADD'], K.TWO, [(s, K.ONE), (y, K.ONE)])                  # nested ADD
    m3 = K.mk((OP['MUL'], K.num(3), x, K.TWO))
    K.pairs(OP['ADD'], K.ONE, [(m3, K.ONE), (y, K.ONE)])                 # MUL term with k != 1
    es = INV.scan(K)
    msgs = ' | '.join(e for e in es if e.startswith('[add]'))
    for needle in ('should be the product', 'zero coefficient', 'nested ADD',
                   'coefficient is not 1'):
        assert needle in msgs


def test_invariants_order(K):
    x = K.sym('x')
    y = K.sym('y')
    good = INV.canonical_order([x, y], K.N, K.H)
    K.mk((OP['ADD'], K.ONE, good[1], K.ONE, good[0], K.ONE))
    assert kinds(INV.scan(K)) == {'order'}


def test_invariants_mul(K):
    x = K.sym('x')
    s = K.pairs(OP['ADD'], K.ONE, [(x, K.ONE)])
    K.mk((OP['MUL'], K.ONE, K.TWO, K.num(3)))                    # 2^3 should fold
    K.mk((OP['MUL'], K.ONE, K.num(8), K.HALF))                   # sqrt(8) not square-free
    K.mk((OP['MUL'], K.ONE, K.num(3), K.num(3, 0, 2)))           # 3^(3/2): exponent > 1
    K.mk((OP['MUL'], K.ONE, x, K.ONE))                           # 1*x
    K.mk((OP['MUL'], K.MONE, s, K.ONE))                          # -(1+x)
    lnx = K.mk((OP['LN'], x))
    K.mk((OP['MUL'], K.ONE, K.E, lnx))                           # e^ln(x)
    msgs = ' | '.join(e for e in INV.scan(K) if e.startswith('[mul]'))
    for needle in ('should fold', 'not 2-th-power-free', 'not in (0, 1)', 'should be b',
                   'distributed', 'e^ln(u)'):
        assert needle in msgs, needle


def test_invariants_hold_is_exempt(K):
    raw = K.mk((OP['MUL'], K.ONE, K.TWO, K.num(3), K.num(3), K.TWO, K.num(5), K.ONE))
    K.mk((OP['HOLD'], raw))                                      # factor(360) display
    assert INV.scan(K) == []


def test_invariants_special_sign_abs(K):
    x = K.sym('x')
    K.mk((OP['SIN'], K.ZERO))
    K.mk((OP['LN'], K.ONE))
    K.mk((OP['LN'], K.num(4)))
    K.mk((OP['COS'], K.mk((OP['MUL'], K.num(1, 0, 6), K.PI, K.ONE))))
    K.mk((OP['SIN'], K.mk((OP['ASIN'], x))))
    K.mk((OP['SIN'], K.mk((OP['MUL'], K.MONE, x, K.ONE))))       # sin(-x)
    K.mk((OP['ABS'], K.num(-3)))
    K.mk((OP['ABS'], K.PI))
    K.mk((OP['ABS'], K.mk((OP['MUL'], K.TWO, x, K.ONE))))
    K.mk((OP['ABS'], K.pairs(OP['ADD'], K.TWO, [(x, K.TWO)])))   # abs(2x+2)
    es = INV.scan(K)
    sp = ' | '.join(e for e in es if e.startswith('[special]'))
    for needle in ('multiple of pi/12', 'ln(1)', 'non-powers', 'should cancel'):
        assert needle in sp, needle
    assert any(e.startswith('[sign]') for e in es)
    ab = ' | '.join(e for e in es if e.startswith('[abs]'))
    for needle in ('modulus', 'provably positive', 'real coefficient', 'rational content 2/1'):
        assert needle in ab, needle


def test_invariants_sentinels_undef_wild(K):
    x = K.sym('x')
    K.pairs(OP['ADD'], K.ONE, [(x, K.ONE), (K.TRUE, K.ONE)])
    K.mk((OP['MUL'], K.ONE, x, K.UNDEF))
    w = K.mk((OP['WILD'], 1, 0))
    es = INV.scan(K)
    assert {'sentinel', 'undef', 'wild'} <= kinds(es)
    K.RULECACHE = {'set': {OP['SIN']: ((w, 'rhs', ''),)}}
    assert 'wild' not in kinds(INV.scan(K))


def test_invariants_structure(K):
    x = K.sym('x')
    K.mk((OP['SIN'], x))
    i = K.NN                                       # a duplicate, appended behind mk's back
    K.N[i] = (OP['SIN'], x)
    K.H[i] = INV.ref_hash(K.N[i], K.H)
    K.V[i] = K.V[x]
    K.NN = i + 1
    ks = kinds(INV.scan(K))
    assert 'unique' in ks and 'buckets' in ks
    K2 = FakeK()
    K2.N[K2.NN] = (OP['SIN'], K2.NN + 3)
    K2.NN += 1
    assert 'topo' in kinds(INV.scan(K2))


def test_invariants_skip_and_check(K):
    K.mk((OP['SIN'], K.ZERO))
    assert INV.scan(K, skip=('special',)) == []
    with pytest.raises(AssertionError, match='special'):
        INV.check(K)


def test_invariants_prealloc(K):
    K.N[K.ONE], K.N[K.TWO] = K.N[K.TWO], K.N[K.ONE]
    assert 'prealloc' in kinds(INV.scan(K))


def test_struct_cmp_tie_break():
    N = [None, (OP['SYM'], 'a'), (OP['SYM'], 'b'), (OP['NUM'], 1, 0, 1),
         (OP['SIN'], 1), (OP['SIN'], 2), (OP['ADD'], 3, 1, 3), (OP['COS'], 1)]
    H = [0] * len(N)                               # every hash equal: only the tie-break
    assert INV.struct_cmp(1, 2, N, H) < 0          # payload 'a' < 'b'
    assert INV.struct_cmp(3, 1, N, H) < 0          # NUM (op 0) before SYM (op 2)
    assert INV.struct_cmp(4, 5, N, H) < 0          # same op and child hashes: the walk
    assert INV.struct_cmp(4, 7, N, H) < 0          # SIN (24) before COS (25)
    assert INV.canonical_order([7, 5, 4, 6, 2], N, H) == [2, 6, 4, 5, 7]


def test_number_helpers():
    assert INV.iroot(10 ** 30, 3) == 10 ** 10 and INV.iroot(26, 3) == 2
    assert INV.rootsplit_free(6, 2) and not INV.rootsplit_free(12, 2)
    assert not INV.rootsplit_free(2 * 101 ** 2, 2)        # found by the cofactor test
    assert not INV.rootsplit_free(10007 ** 2, 2)
    assert INV.rootsplit_free(10007 ** 2 * 10009, 2)      # documented partial reduction
    assert INV.is_perfect_power(8) and not INV.is_perfect_power(12)
    assert INV.ref_hash((OP['NUM'], 3, 0, 1), []) == 0x19      # DESIGN 5.6: H=0000019
    assert INV.ref_hash((OP['NUM'], 3, 0, 2), []) == 0x1a      # DESIGN 5.6: H=000001a
    # the rest of the DESIGN 5.6 worked example (ids there: 2 ONE, 4 TWO, 13 x)
    H = [0] * 14
    H[2] = INV.ref_hash((OP['NUM'], 1, 0, 1), H)
    H[4] = INV.ref_hash((OP['NUM'], 2, 0, 1), H)
    H[13] = INV.ref_hash((OP['SYM'], 'x'), H)
    assert H[13] == 0x2a0d8                                     # H=002a0d8
    assert INV.ref_hash((OP['MUL'], 2, 13, 4), H) == 0x50bf11   # x^2: H=050bf11
    assert INV.ref_hash((OP['SIN'], 13), H) == 0x2a3d8          # sin(x): H=002a3d8


# -- gen.py self-tests ------------------------------------------------------------------------

def test_gen_is_deterministic():
    a = [gen.Gen(7).expr(3) for _ in range(1)] + [gen.Gen(7).line()]
    b = [gen.Gen(7).expr(3) for _ in range(1)] + [gen.Gen(7).line()]
    assert a == b
    g1 = gen.Gen(11)
    g2 = gen.Gen(11)
    for _ in range(50):
        assert g1.line() == g2.line()


def test_gen_nested():
    assert gen.nested('sin', 3) == 'sin(sin(sin(x)))'
    assert gen.nested('square', 2) == '((x+1)^2+1)^2'
    assert gen.nested('frac', 2) == '1/(1+1/(1+x))'
    assert gen.nested('paren', 0) == 'x'


def _has_odd_root(t):
    st = [t]
    while st:
        u = st.pop()
        if u[0] == 'pow' and u[2][0] == 'num' and u[2][2] > 1:
            return True
        for c in u[1:]:
            if isinstance(c, tuple) and c and isinstance(c[0], str):
                st.append(c)
            elif isinstance(c, tuple):
                st.extend(c)
    return False


def _value(e, pt):
    import sympy as S
    v = complex(S.N(e.subs(pt), 30))
    return v


@pytest.mark.oracle
def test_gen_text_and_variants_agree_with_sympy():
    import sympy as S
    x, y = S.Symbol('x', real=True), S.Symbol('y', real=True)
    pt = {x: S.Rational(7, 10), y: S.Rational(13, 10)}
    loc = {'x': x, 'y': y, 'pi': S.pi, 'e': S.E, 'i': S.I, 'ln': S.log, 'abs': S.Abs,
           'log': lambda u: S.log(u, 10), 'sqrt': S.sqrt, 'exp': S.exp}
    g = gen.Gen(3)
    checked = 0
    for _ in range(60):
        t = g.tree(3)
        try:
            ref = _value(gen.to_sympy(t), pt)
        except (ZeroDivisionError, TypeError, ValueError):
            continue
        if not all(math.isfinite(c) for c in (ref.real, ref.imag)):
            continue
        for v in g.variants(t, 2):
            w = _value(gen.to_sympy(v), pt)
            assert abs(w - ref) <= 1e-9 * max(1.0, abs(ref)), (t, v)
        if not _has_odd_root(t):
            p = S.parse_expr(gen.text(t).replace('^', '**'), local_dict=loc)
            w = _value(p, pt)
            assert abs(w - ref) <= 1e-9 * max(1.0, abs(ref)), gen.text(t)
        checked += 1
    assert checked >= 30


class _Rec(object):
    """A recording stand-in for the node module's constructor API."""

    ONE, MONE, HALF, E, PI, I, LN10 = 'ONE', 'MONE', 'HALF', 'E', 'PI', 'I', 'LN10'
    SIN, LN, ABS = 'SIN', 'LN', 'ABS'

    def num(self, a, b, d):
        return 'num(%d,%d,%d)' % (a, b, d)

    def sym(self, s):
        return s

    def add_(self, ids):
        return 'add_[%s]' % ','.join(ids)

    def mul_(self, k, prs):
        return 'mul_(%s,[%s])' % (k, ','.join('(%s,%s)' % p for p in prs))

    def fn_(self, op, a):
        return 'fn_(%s,%s)' % (op, a)

    def flt(self, v):
        return 'flt(%r)' % v


def test_gen_build_uses_the_frozen_api():
    R = _Rec()
    assert gen.build(('sub', ('sym', 'x'), gen.num(1, 2)), R) == \
        'add_[x,mul_(MONE,[(num(1,0,2),ONE)])]'
    assert gen.build(('fn', 'sqrt', ('sym', 'x')), R) == 'mul_(ONE,[(x,HALF)])'
    assert gen.build(('fn', 'log', ('sym', 'x')), R) == \
        'mul_(ONE,[(fn_(LN,x),ONE),(LN10,MONE)])'
    assert gen.build(('fn', 'sin', ('con', 'pi')), R) == 'fn_(SIN,PI)'
    assert gen.build(('div', ('flt', '0.5'), ('sym', 'y')), R) == \
        'mul_(ONE,[(flt(0.5),ONE),(y,MONE)])'
