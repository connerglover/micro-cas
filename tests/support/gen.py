"""Seeded random expressions for property, fuzz and nesting tests (DESIGN.md 20.7, 20.12).

Trees are nested tuples (test-side only; device code never sees them):

    ('num', p, q)        the rational p/q (q >= 1, gcd 1)
    ('flt', '0.5')       a typed decimal (a float, D8)
    ('sym', 'x')
    ('con', 'pi' | 'e' | 'i')
    ('add', (a, b, ...)) ('mul', (a, b, ...))
    ('neg', a) ('sub', a, b) ('div', a, b) ('pow', a, b)
    ('fn', 'sin', a)     any name of FUNCS

    g = Gen(seed)
    t = g.tree(depth=3)          # a random tree
    s = text(t)                  # input-language text with explicit '*' (parses without
                                 # implicit multiplication)
    vs = g.variants(t, 4)        # equal trees: operands permuted and regrouped
    g.line()                     # a fuzz input line (valid, mutated or junk)
    nested('sin', 8)             # 'sin(sin(...(x)...))' for the nesting-invariance test
    build(t, K)                  # the node id, through the frozen node API (section 21.2)
    to_sympy(t)                  # the SymPy value (odd roots are real, as section 20.5)
"""
import random
from math import gcd

FUNCS = ('sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'asin', 'acos', 'atan', 'sinh', 'cosh',
         'tanh', 'ln', 'log', 'exp', 'sqrt', 'abs')
# name -> node.py op-code attribute, for the one-argument function nodes (section 5.2)
FNOPS = {'sin': 'SIN', 'cos': 'COS', 'tan': 'TAN', 'sec': 'SEC', 'csc': 'CSC', 'cot': 'COT',
         'asin': 'ASIN', 'acos': 'ACOS', 'atan': 'ATAN', 'sinh': 'SINH', 'cosh': 'COSH',
         'tanh': 'TANH', 'ln': 'LN', 'abs': 'ABS'}
COMMANDS = ('diff(%s,x)', 'integrate(%s,x)', 'solve(%s=0,x)', 'factor(%s)', 'expand(%s)',
            'simplify(%s)', 'limit(%s,x,0)', 'taylor(%s,x,0,4)', 'together(%s)', '%s')
JUNK = ('0', '1', '2', '7', '.', 'x', 'y', 'e', 'E', 'i', 'pi', '+', '-', '*', '/', '^', '(',
        ')', '[', ']', ',', '=', '<', '>', '!', "'", 'sin', 'ln', 'diff', 'Ans', ' ')


def num(p, q=1):
    if q < 0:
        p, q = -p, -q
    g = gcd(p, q) or 1
    return ('num', p // g, q // g)


class Gen(object):
    """A seeded generator. Equal seeds give equal sequences on every platform."""

    def __init__(self, seed=0, syms=('x', 'y'), funcs=FUNCS, maxint=9, floats=False,
                 consts=('pi', 'e')):
        self.r = random.Random(seed)
        self.syms = tuple(syms)
        self.funcs = tuple(funcs)
        self.maxint = maxint
        self.floats = floats
        self.consts = tuple(consts)

    def leaf(self):
        r = self.r
        k = r.random()
        if k < 0.45 and self.syms:
            return ('sym', r.choice(self.syms))
        if k < 0.75:
            return num(r.randint(-self.maxint, self.maxint))
        if k < 0.85:
            return num(r.randint(-self.maxint, self.maxint), r.randint(1, self.maxint))
        if k < 0.92 and self.floats:
            return ('flt', '%d.%d' % (r.randint(0, 9), r.randint(1, 9)))
        if self.consts:
            return ('con', r.choice(self.consts))
        return num(r.randint(1, self.maxint))

    def tree(self, depth=3):
        r = self.r
        if depth <= 0 or r.random() < 0.25:
            return self.leaf()
        k = r.random()
        d = depth - 1
        if k < 0.25:
            n = r.randint(2, 3)
            return ('add', tuple(self.tree(d) for _ in range(n)))
        if k < 0.45:
            n = r.randint(2, 3)
            return ('mul', tuple(self.tree(d) for _ in range(n)))
        if k < 0.55:
            return ('sub', self.tree(d), self.tree(d))
        if k < 0.65:
            return ('div', self.tree(d), self.tree(d))
        if k < 0.75:
            e = num(r.randint(-3, 4)) if r.random() < 0.7 else num(r.choice((1, 1, 2, 3)),
                                                                   r.choice((2, 3)))
            return ('pow', self.tree(d), e)
        if k < 0.8:
            return ('neg', self.tree(d))
        return ('fn', r.choice(self.funcs), self.tree(d))

    def poly(self, var='x', degree=3, maxc=None):
        """A univariate polynomial sum c_k * var^k with small integer coefficients."""
        maxc = self.maxint if maxc is None else maxc
        terms = []
        for k in range(degree + 1):
            c = self.r.randint(-maxc, maxc)
            if c == 0 and k != degree:
                continue
            if k == degree and c == 0:
                c = 1
            if k == 0:
                terms.append(num(c))
            elif k == 1:
                terms.append(('mul', (num(c), ('sym', var))))
            else:
                terms.append(('mul', (num(c), ('pow', ('sym', var), num(k)))))
        return terms[0] if len(terms) == 1 else ('add', tuple(terms))

    def expr(self, depth=3):
        return text(self.tree(depth))

    def variants(self, t, n=3):
        """n trees equal to t by commutativity, associativity and the derived forms."""
        out = []
        for _ in range(n):
            out.append(self._variant(t))
        return out

    def _variant(self, t):
        r = self.r
        k = t[0]
        if k in ('add', 'mul'):
            ch = [self._variant(c) for c in t[1]]
            r.shuffle(ch)
            while len(ch) > 2 and r.random() < 0.5:        # regroup two operands
                i = r.randrange(len(ch) - 1)
                ch[i:i + 2] = [(k, (ch[i], ch[i + 1]))]
            return (k, tuple(ch))
        if k == 'sub':
            a, b = self._variant(t[1]), self._variant(t[2])
            if r.random() < 0.5:
                return ('add', (a, ('neg', b)))
            return ('sub', a, b)
        if k == 'div':
            a, b = self._variant(t[1]), self._variant(t[2])
            if r.random() < 0.5:
                return ('mul', (a, ('pow', b, num(-1))))
            return ('div', a, b)
        if k in ('neg',):
            return ('neg', self._variant(t[1]))
        if k == 'pow':
            return ('pow', self._variant(t[1]), t[2])
        if k == 'fn':
            return ('fn', t[1], self._variant(t[2]))
        return t

    def line(self):
        """A fuzz line for 'R.go never raises' (section 20.12): valid, mutated or junk."""
        r = self.r
        k = r.random()
        if k < 0.4:
            return r.choice(COMMANDS) % self.expr(r.randint(0, 3))
        if k < 0.8:
            s = list(r.choice(COMMANDS) % self.expr(r.randint(0, 3)))
            for _ in range(r.randint(1, 3)):
                op = r.random()
                j = r.randrange(len(s) + 1)
                if op < 0.4 and s:
                    del s[min(j, len(s) - 1)]
                elif op < 0.8:
                    s.insert(j, r.choice(JUNK))
                elif s:
                    s.insert(j, s[min(j, len(s) - 1)])
            return ''.join(s)
        return ''.join(r.choice(JUNK) for _ in range(r.randint(0, 12)))


def text(t):
    """Input-language text: explicit '*', compound operands in parentheses."""
    k = t[0]
    if k == 'num':
        if t[2] == 1:
            return str(t[1]) if t[1] >= 0 else '(%d)' % t[1]
        return '(%d/%d)' % (t[1], t[2])
    if k == 'flt':
        return t[1]
    if k in ('sym', 'con'):
        return t[1]
    if k == 'add':
        return '+'.join(_operand(c) for c in t[1])
    if k == 'mul':
        return '*'.join(_operand(c) for c in t[1])
    if k == 'neg':
        return '-' + _operand(t[1])
    if k == 'sub':
        return '%s-%s' % (_operand(t[1]), _operand(t[2]))
    if k == 'div':
        return '%s/%s' % (_operand(t[1]), _operand(t[2]))
    if k == 'pow':
        return '%s^%s' % (_operand(t[1]), _operand(t[2]))
    if k == 'fn':
        return '%s(%s)' % (t[1], text(t[2]))
    raise ValueError('not a gen tree: %r' % (t,))


def _operand(t):
    s = text(t)
    if t[0] in ('sym', 'con', 'fn', 'flt') or (t[0] == 'num' and t[2] == 1 and t[1] >= 0):
        return s
    if s.startswith('(') and _balanced_outer(s):
        return s
    return '(%s)' % s


def _balanced_outer(s):
    d = 0
    for i, ch in enumerate(s):
        if ch == '(':
            d += 1
        elif ch == ')':
            d -= 1
            if d == 0 and i != len(s) - 1:
                return False
    return d == 0


def nested(kind, n, var='x'):
    """Inputs nested n deep for the nesting-invariance test (section 20.7)."""
    s = var
    for _ in range(n):
        if kind == 'sin':
            s = 'sin(%s)' % s
        elif kind == 'square':
            s = '(%s+1)^2' % s
        elif kind == 'frac':
            s = '1/(1+%s)' % s
        elif kind == 'paren':
            s = '(%s)' % s
        elif kind == 'sum':
            s = '%s+(%s)' % (var, s)
        elif kind == 'prod':
            s = '%s*(%s)' % (var, s)
        elif kind == 'exp':
            s = 'e^(%s)' % s
        elif kind == 'ln':
            s = 'ln(1+%s)' % s
        else:
            raise ValueError('unknown nesting kind %r' % kind)
    return s


def build(t, K):
    """The canonical node id of tree t, through the frozen node API (DESIGN 21.2)."""
    k = t[0]
    if k == 'num':
        return K.num(t[1], 0, t[2])
    if k == 'flt':
        return K.flt(float(t[1]))
    if k == 'sym':
        return K.sym(t[1])
    if k == 'con':
        return {'pi': K.PI, 'e': K.E, 'i': K.I}[t[1]]
    one = K.ONE
    if k == 'add':
        return K.add_([build(c, K) for c in t[1]])
    if k == 'mul':
        return K.mul_(one, [(build(c, K), one) for c in t[1]])
    if k == 'neg':
        return K.mul_(K.MONE, [(build(t[1], K), one)])
    if k == 'sub':
        a = build(t[1], K)
        b = build(t[2], K)
        return K.add_([a, K.mul_(K.MONE, [(b, one)])])
    if k == 'div':
        a = build(t[1], K)
        b = build(t[2], K)
        return K.mul_(one, [(a, one), (b, K.MONE)])
    if k == 'pow':
        return K.mul_(one, [(build(t[1], K), build(t[2], K))])
    if k == 'fn':
        a = build(t[2], K)
        f = t[1]
        if f == 'exp':
            return K.mul_(one, [(K.E, a)])
        if f == 'sqrt':
            return K.mul_(one, [(a, K.HALF)])
        if f == 'log':
            return K.mul_(one, [(K.fn_(K.LN, a), one), (K.LN10, K.MONE)])
        return K.fn_(getattr(K, FNOPS[f]), a)
    raise ValueError('not a gen tree: %r' % (t,))


def to_sympy(t):
    """The SymPy value of tree t; a rational power with an odd denominator is the real root."""
    import sympy as S
    k = t[0]
    if k == 'num':
        return S.Rational(t[1], t[2])
    if k == 'flt':
        return S.Float(t[1])
    if k == 'sym':
        return S.Symbol(t[1], real=True)
    if k == 'con':
        return {'pi': S.pi, 'e': S.E, 'i': S.I}[t[1]]
    if k == 'add':
        return S.Add(*[to_sympy(c) for c in t[1]])
    if k == 'mul':
        return S.Mul(*[to_sympy(c) for c in t[1]])
    if k == 'neg':
        return -to_sympy(t[1])
    if k == 'sub':
        return to_sympy(t[1]) - to_sympy(t[2])
    if k == 'div':
        return to_sympy(t[1]) / to_sympy(t[2])
    if k == 'pow':
        b = to_sympy(t[1])
        e = t[2]
        if e[0] == 'num' and e[2] % 2 == 1 and e[2] > 1:
            return S.real_root(b, e[2]) ** e[1]
        return b ** to_sympy(e)
    if k == 'fn':
        a = to_sympy(t[2])
        f = t[1]
        table = {'sin': S.sin, 'cos': S.cos, 'tan': S.tan, 'sec': S.sec, 'csc': S.csc,
                 'cot': S.cot, 'asin': S.asin, 'acos': S.acos, 'atan': S.atan,
                 'sinh': S.sinh, 'cosh': S.cosh, 'tanh': S.tanh, 'ln': S.log,
                 'exp': S.exp, 'sqrt': S.sqrt, 'abs': S.Abs}
        if f == 'log':
            return S.log(a, 10)
        return table[f](a)
    raise ValueError('not a gen tree: %r' % (t,))
