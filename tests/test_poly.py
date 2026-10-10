"""T1.2 Polynomials: src/poly.py, src/polyb.py, src/polyc.py (DESIGN 4.1, 4.3, 8.5, 8.6, 11.2;
alg 2.6-2.9). The CVPOLY family has no node dependency: everything here is plain ints, lists,
tuples and dicts, checked against SymPy on seeded random inputs.

Representations (docs/notes/T1.2.md):
- dense Z[x] (poly, polyb): a list of ints, low degree first, no trailing zeros; [] is 0;
- sparse Z[x1..xn] (polyc): a dict {exponent tuple: nonzero int}; {} is 0.
"""
import ast
import io
import os
import random
import tokenize
from math import gcd

import pytest
import sympy
from sympy import QQ, ZZ, Matrix, Poly, Rational, symbols

import framelint
import lint
import poly as PO
import polyb as POB
import polyc as POC

X, Y, Z, W = symbols('x y z w')
GENS = (X, Y, Z, W)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
PARTS = ('poly', 'polyb', 'polyc')
LAZYMAX = 150           # DESIGN 4.3 / 19.1, provisional until the M0.5 gate


# -- helpers ------------------------------------------------------------------------------------

def sp(p):
    """dense low-first int list -> sympy Poly over ZZ in x"""
    if not p:
        return Poly(0, X, domain=ZZ)
    return Poly(list(reversed(p)), X, domain=ZZ)


def dl(P):
    """sympy Poly (ZZ) -> dense low-first list"""
    c = [int(v) for v in reversed(P.all_coeffs())]
    while c and not c[-1]:
        c.pop()
    return c


def isnorm(p):
    return isinstance(p, list) and (not p or p[-1] != 0) and all(type(c) is int for c in p)


def rpoly(r, deg, mx=9):
    """a random dense poly of exact degree deg (deg < 0: zero)"""
    if deg < 0:
        return []
    p = [r.randint(-mx, mx) for _ in range(deg + 1)]
    while p[-1] == 0:
        p[-1] = r.randint(-mx, mx)
    return p


def cont(p):
    g = 0
    for c in p:
        g = gcd(g, c)
    return g


def msp(d, nv):
    """sparse dict -> sympy Poly over ZZ in the first nv gens"""
    if not d:
        return Poly(0, *GENS[:nv], domain=ZZ)
    return Poly.from_dict(dict(d), *GENS[:nv], domain=ZZ)


def rsparse(r, nv, nterms, maxdeg=3, mx=9):
    d = {}
    for _ in range(nterms):
        e = tuple(r.randint(0, maxdeg) for _ in range(nv))
        c = r.randint(-mx, mx)
        if c:
            d[e] = c
    return d


def wellformed(d, nv):
    return isinstance(d, dict) and all(
        isinstance(k, tuple) and len(k) == nv and all(type(e) is int and e >= 0 for e in k)
        and type(v) is int and v != 0 for k, v in d.items())


# -- part A: dense arithmetic -------------------------------------------------------------------

def test_padd_basic():
    assert PO.padd([1, 2], [3, -2]) == [4]
    assert PO.padd([1, 2, 3], [0, 0, -3]) == [1, 2]
    assert PO.padd([], [5]) == [5]
    assert PO.padd([1], [1], -1) == []
    assert PO.padd([], [1, 2, 3], 4) == [4, 8, 12]            # scaling: padd([], a, c)
    assert PO.padd([1, 2], [], 7) == [1, 2]
    assert PO.padd([2, 3], [1, 1, 1], 0) == [2, 3]
    a = [1, 2]
    b = [0, 0, 1]
    PO.padd(a, b, 3)
    assert a == [1, 2] and b == [0, 0, 1]                      # inputs are never mutated


def test_pmul_ppow_pderiv_peval_basic():
    assert PO.pmul([1, 1], [-1, 1]) == [-1, 0, 1]
    assert PO.pmul([], [1, 2]) == [] and PO.pmul([3], []) == []
    assert PO.ppow([1, 1], 0) == [1] and PO.ppow([], 0) == [1]
    assert PO.ppow([1, 1], 5) == [1, 5, 10, 10, 5, 1]
    assert PO.ppow([], 3) == []
    assert PO.pderiv([5]) == [] and PO.pderiv([]) == []
    assert PO.pderiv([1, 2, 3, 4]) == [2, 6, 12]
    assert PO.peval([], 3) == 0
    assert PO.peval([1, 2, 3], 2) == 17
    assert PO.peval([1, 0, -2], 10 ** 20) == 1 - 2 * 10 ** 40
    assert PO.peval([1, 2, 3], 0.5) == 2.75 and PO.peval([1, 1], 1j) == 1 + 1j


def test_dense_arith_random_vs_sympy():
    r = random.Random(1201)
    for _ in range(150):
        a = rpoly(r, r.randint(-1, 7), r.choice((3, 9, 10 ** 12)))
        b = rpoly(r, r.randint(-1, 7), r.choice((3, 9, 10 ** 12)))
        k = r.choice((1, -1, 0, 3, -7))
        s = PO.padd(a, b, k)
        assert isnorm(s) and sp(s) == sp(a) + sp(b) * k
        m = PO.pmul(a, b)
        assert isnorm(m) and sp(m) == sp(a) * sp(b)
        assert sp(PO.pderiv(a)) == sp(a).diff(X) and isnorm(PO.pderiv(a))
        v = r.randint(-5, 5)
        assert PO.peval(a, v) == sp(a).eval(v)
        n = r.randint(0, 4)
        assert sp(PO.ppow(b, n)) == sp(b) ** n


def test_pcont_pprim():
    assert PO.pcont([]) == 0 and PO.pprim([]) == []
    assert PO.pcont([-4, 6, -8]) == 2
    assert PO.pprim([-4, 6, -8]) == [2, -3, 4]             # lc made positive
    assert PO.pprim([4, -6, 8]) == [2, -3, 4]
    assert PO.pprim([-5]) == [1] and PO.pcont([-5]) == 5
    r = random.Random(1202)
    for _ in range(100):
        a = PO.padd([], rpoly(r, r.randint(0, 6)), r.choice((1, -1, 6, -15, 2 ** 70)))
        c = PO.pcont(a)
        pp = PO.pprim(a)
        assert c == abs(sp(a).content())
        assert isnorm(pp) and pp[-1] > 0 and cont(pp) == 1
        assert PO.padd([], pp, c if a[-1] > 0 else -c) == a


def test_pdivrem_basic():
    q, r, m = PO.pdivrem([0, 0, 1], [2, 2])                # x^2 = (x/2 - 1/2)(2x+2) + 1
    assert (q, r, m) == ([-1, 1], [2], 2)
    assert PO.pdivrem([1, 2], [1, 2, 3]) == ([], [1, 2], 1)  # deg a < deg b
    assert PO.pdivrem([], [3, 1]) == ([], [], 1)
    assert PO.pdivrem([6, 4], [2]) == ([3, 2], [], 1)
    assert PO.pdivrem([1, 1], [0, -2]) == ([-1], [2], 2)    # x+1 = (-1/2)(-2x) + 1
    a = [1, 2, 3]
    b = [1, 1]
    PO.pdivrem(a, b)
    assert a == [1, 2, 3] and b == [1, 1]


def test_pdivrem_random_vs_sympy():
    r = random.Random(1203)
    for _ in range(150):
        b = rpoly(r, r.randint(0, 5), r.choice((2, 9, 1000)))
        a = rpoly(r, r.randint(-1, 9), r.choice((2, 9, 1000)))
        q, rr, m = PO.pdivrem(a, b)
        assert isnorm(q) and isnorm(rr) and type(m) is int and m > 0
        assert len(rr) < len(b)
        assert PO.padd(PO.pmul(q, b), rr) == PO.padd([], a, m)      # m*a = q*b + r
        assert gcd(gcd(m, cont(q)), cont(rr)) == 1                  # m is minimal
        Q, R = sp(a).to_field().div(sp(b).to_field())
        assert Q == Poly(sp(q).as_expr() / m, X, domain=QQ)
        assert R == Poly(sp(rr).as_expr() / m, X, domain=QQ)


def test_pdivex():
    assert PO.pdivex([-1, 0, 1], [1, 1]) == [-1, 1]
    assert PO.pdivex([-1, 0, 1], [1, 2]) is None
    assert PO.pdivex([2, 2], [2]) == [1, 1]
    assert PO.pdivex([2, 3], [2]) is None                   # divisible over Q, not over Z
    assert PO.pdivex([], [5, 1]) == []
    assert PO.pdivex([1], [5, 1]) is None
    assert PO.pdivex([1, 1], [0, 0, 1]) is None
    r = random.Random(1204)
    for _ in range(150):
        b = rpoly(r, r.randint(0, 5))
        c = rpoly(r, r.randint(-1, 5))
        a = PO.pmul(b, c)
        assert PO.pdivex(a, b) == c
        e = PO.padd(a, rpoly(r, r.randint(0, 6)))
        q = PO.pdivex(e, b)
        Q, R = sp(e).to_field().div(sp(b).to_field())
        if R.is_zero and all(v.is_integer for v in Q.all_coeffs()):
            assert q == ([] if Q.is_zero else dl(Q.to_ring()))
        else:
            assert q is None


def test_pgcd_basic():
    assert PO.pgcd([], []) == []
    assert PO.pgcd([2, 2], []) == [2, 2]
    assert PO.pgcd([], [-2, -2]) == [2, 2]
    assert PO.pgcd([4, 4], [6, 6]) == [2, 2]
    assert PO.pgcd([-1, 0, 1], [1, 2, 1]) == [1, 1]
    assert PO.pgcd([1, 0, 1], [0, 1]) == [1]
    assert PO.pgcd([6], [4, 2]) == [2]
    assert PO.pgcd([-3, 0, 3], [0, -6]) == [3]


def test_pgcd_random_vs_sympy():
    r = random.Random(1205)
    for _ in range(300):
        g = rpoly(r, r.randint(0, 4), 5)
        a = PO.pmul(g, rpoly(r, r.randint(-1, 4), 5))
        b = PO.pmul(g, rpoly(r, r.randint(-1, 4), 5))
        h = PO.pgcd(a, b)
        want = sp(a).gcd(sp(b))
        assert isnorm(h) and (not h or h[-1] > 0)
        assert sp(h) == want, (a, b, h, want)
        assert PO.pgcd(b, a) == h


def test_yun_basic():
    assert PO.yun([]) == (0, [])
    assert PO.yun([-7]) == (-7, [])
    c, fs = PO.yun([0, 0, 0, 2])                            # 2x^3
    assert (c, fs) == (2, [([0, 1], 3)])
    # -12 (2x+1) (x-1)^2 (x+2)^3, the SymPy docstring shape
    a = dl(Poly(-12 * (X - 1) ** 2 * (X + 2) ** 3 * (2 * X + 1), X))
    c, fs = PO.yun(a)
    assert c == -12
    assert fs == [([1, 2], 1), ([-1, 1], 2), ([2, 1], 3)]


def test_yun_random_vs_sympy():
    r = random.Random(1206)
    for _ in range(200):
        a = [r.choice((1, -1, 2, -6))]
        for _ in range(r.randint(0, 3)):
            f = rpoly(r, r.randint(1, 3), 4)
            a = PO.pmul(a, PO.ppow(f, r.randint(1, 3)))
        c, fs = PO.yun(a)
        sc, sfs = sp(a).sqf_list()
        assert c == int(sc)
        got = []
        for f, m in fs:
            assert isnorm(f) and len(f) > 1 and f[-1] > 0 and cont(f) == 1
            got.append((tuple(f), m))
        want = []
        for f, m in sfs:
            f = dl(f)
            if f[-1] < 0:                                    # SymPy may leave a sign inside
                f = PO.padd([], f, -1)
            want.append((tuple(f), m))
        assert sorted(got) == sorted(want), (a, fs, sfs)
        ms = [m for _, m in fs]
        assert ms == sorted(set(ms))                         # increasing multiplicities
        back = [c]
        for f, m in fs:
            back = PO.pmul(back, PO.ppow(f, m))
        assert back == a


# -- part B: divisors, rational roots, Gauss-Jordan, Bezout -------------------------------------

def test_divisors():
    assert POB.divisors(1) == ([1], True)
    assert POB.divisors(-12) == ([1, 2, 3, 4, 6, 12], True)
    assert POB.divisors(97) == ([1, 97], True)
    for n in (360, 720720, 2 ** 20, 99991 * 2, 9973 ** 2, 9973 * 9967 * 4, 999983,
              10007 * 6):
        ds, ok = POB.divisors(n)
        assert ok and ds == sympy.divisors(n), n
    ds, ok = POB.divisors(3 * 10007 * 10009)                 # cofactor past trial division
    assert not ok and set(ds) <= set(sympy.divisors(3 * 10007 * 10009))
    big = 1000003 * 1000033                                  # two primes beyond trial division
    ds, ok = POB.divisors(6 * big)
    assert not ok and set(ds) <= set(sympy.divisors(6 * big)) and 6 * big in ds
    ds, ok = POB.divisors(2 ** 40 * 3 ** 40)                 # 1681 divisors: over DIVCAP
    assert ds == [] and not ok
    # x^3 - 2^40*3^40: the root bound prunes the candidates to a list under DIVCAP
    roots, cof, ok = POB.ratroots([-(2 ** 40 * 3 ** 40), 0, 0, 1])
    assert roots == [] and ok and cof == [-(2 ** 40 * 3 ** 40), 0, 0, 1]
    ds, ok = POB.divisors(720720, 100)
    assert ok and ds == [d for d in sympy.divisors(720720) if d <= 100]


def _rat_roots_sympy(a):
    out = []
    for f, m in sp(a).factor_list()[1]:
        if f.degree() == 1:
            b0, a1 = f.all_coeffs()[1], f.all_coeffs()[0]
            v = Rational(-b0, a1)
            out.append((int(v.p), int(v.q), m))
    return sorted(out, key=lambda t: Rational(t[0], t[1]))


def rsorted(roots):
    return sorted(roots, key=lambda t: Rational(t[0], t[1]))


def test_ratroots_basic():
    roots, cof, ok = POB.ratroots([-1, 6, -11, 6])
    assert ok and roots == [(1, 1, 1), (1, 2, 1), (1, 3, 1)] and cof == [1]
    roots, cof, ok = POB.ratroots([0, 0, -4, 0, 1])          # x^2 (x-2)(x+2)
    assert ok and roots == [(0, 1, 2), (2, 1, 1), (-2, 1, 1)] and cof == [1]
    roots, cof, ok = POB.ratroots([1, 0, 1])
    assert ok and roots == [] and cof == [1, 0, 1]
    roots, cof, ok = POB.ratroots([5])
    assert ok and roots == [] and cof == [5]
    roots, cof, ok = POB.ratroots([4, -4, 1])                # (x-2)^2 ... over 1
    assert ok and roots == [(2, 1, 2)] and cof == [1]
    roots, cof, ok = POB.ratroots([2, -6, 4])                # 2(2x-1)(x-1): content stays
    assert ok and roots == [(1, 1, 1), (1, 2, 1)] and cof == [2]
    roots, cof, ok = POB.ratroots([1, -1, 0, 0, 0, 1])      # x^5-x+1: none
    assert ok and roots == [] and len(cof) == 6


def test_ratroots_random_vs_sympy():
    r = random.Random(1207)
    for _ in range(200):
        a = rpoly(r, r.randint(0, 3), 6)
        for _ in range(r.randint(0, 4)):
            q = r.randint(1, 6)
            p = r.randint(-12, 12)
            a = PO.pmul(a, [-p, q])
        roots, cof, ok = POB.ratroots(a)
        assert ok
        assert rsorted(roots) == _rat_roots_sympy(a), a
        back = cof
        for p, q, m in roots:
            assert q > 0 and gcd(p, q) == 1 and m >= 1
            back = PO.pmul(back, PO.ppow([-p, q], m))
        assert back == a
        assert _rat_roots_sympy(cof) == []


def test_ratroots_incomplete_flag():
    big = 1000003 * 1000033
    roots, cof, ok = POB.ratroots([-big, 0, 1])               # x^2 - big: unfactored a0
    assert not ok and roots == []
    roots, cof, ok = POB.ratroots(PO.pmul([-big, 1], [-3, 1]))  # big is itself a candidate
    assert ok and roots == [(3, 1, 1), (big, 1, 1)] and cof == [1]   # nothing left to miss
    roots, cof, ok = POB.ratroots(PO.pmul([-big, 1], [1, 0, 1]))
    assert not ok and roots == [(big, 1, 1)] and cof == [1, 0, 1]


def test_ratroots_budgets(monkeypatch):
    """A short budget or a divisor list over DIVCAP gives a partial answer, never a wrong one."""
    a = [1]
    for k in (7, -11, 13, 17):
        a = PO.pmul(a, [-k, 1])
    monkeypatch.setattr(POB, 'RRMAX', 2)
    roots, cof, ok = POB.ratroots(a)
    assert not ok and len(roots) < 4
    back = cof
    for p, q, m in roots:
        back = PO.pmul(back, PO.ppow([-p, q], m))
    assert back == a
    monkeypatch.setattr(POB, 'RRMAX', 4000)
    big = 2 ** 40 * 3 ** 40                                  # lc with 1681 divisors
    roots, cof, ok = POB.ratroots([-1, big])
    assert roots == [] and cof == [-1, big] and not ok


def test_gjsolve_basic():
    # x + y = 3, x - y = 1  ->  x = 2, y = 1
    piv, rows = POB.gjsolve([[1, 1, 3], [1, -1, 1]], 2)
    assert piv == [0, 1] and rows == [[1, 0, 2], [0, 1, 1]]
    # 2x = 1  ->  x = 1/2
    assert POB.gjsolve([[2, 1]], 1) == ([0], [[2, 1]])
    # x + y = 1, 2x + 2y = 3: inconsistent
    assert POB.gjsolve([[1, 1, 1], [2, 2, 3]], 2) is None
    # x + y = 1, 2x + 2y = 2: one free variable
    assert POB.gjsolve([[1, 1, 1], [2, 2, 2]], 2) == ([0], [[1, 1, 1]])
    # zero rows and no unknowns
    assert POB.gjsolve([], 3) == ([], [])
    assert POB.gjsolve([[0, 0, 0]], 2) == ([], [])
    assert POB.gjsolve([[0, 0, 5]], 2) is None
    m = [[3, 6, 9], [1, 4, 1]]
    POB.gjsolve(m, 2)
    assert m == [[3, 6, 9], [1, 4, 1]]                      # the input is not mutated


def test_gjsolve_random_vs_sympy():
    r = random.Random(1208)
    for _ in range(300):
        nr = r.randint(1, 6)
        nv = r.randint(1, 6)
        nrhs = r.randint(0, 2)
        rank = r.randint(0, min(nr, nv))
        base = [[r.randint(-5, 5) for _ in range(nv + nrhs)] for _ in range(rank)]
        rows = []
        for _ in range(nr):                                  # combinations: rank <= rank
            row = [0] * (nv + nrhs)
            for b in base:
                k = r.randint(-2, 2)
                row = [u + k * v for u, v in zip(row, b)]
            rows.append(row)
        if r.random() < 0.3 and nrhs:                        # maybe break consistency
            rows[r.randrange(nr)][nv] += r.randint(1, 3)
        res = POB.gjsolve(rows, nv)
        R, spiv = Matrix(rows).rref()
        consistent = all(c < nv for c in spiv)
        if not consistent:
            assert res is None
            continue
        piv, out = res
        assert piv == list(spiv)
        assert len(out) == len(piv)
        for k, (c, row) in enumerate(zip(piv, out)):
            assert row[c] > 0 and cont(row) == 1
            for j, c2 in enumerate(piv):
                if j != k:
                    assert row[c2] == 0
            assert [Rational(v, row[c]) for v in row] == list(R.row(k))


def test_bezout_basic():
    # (x^2+1) s + (x-1) t = 1: s = 1/2, t = -(x+1)/2
    s, t, d = POB.bezout([1, 0, 1], [-1, 1], [1])
    assert (s, t, d) == ([1], [-1, -1], 2)
    assert POB.bezout([-1, 0, 1], [1, 1], [1]) is None     # common factor x+1
    assert POB.bezout([3], [2], [1]) == ([], [1], 2)         # 0*3 + (1/2)*2 = 1
    assert POB.bezout([3], [2], []) == ([], [], 1)
    assert POB.bezout([], [1, 1], [1]) is None
    s, t, d = POB.bezout([1, 1], [2], [5, 0, 7])             # b constant: t = c/2
    assert (s, t, d) == ([], [5, 0, 7], 2)


def test_bezout_random_vs_sympy():
    r = random.Random(1209)
    done = 0
    while done < 150:
        a = rpoly(r, r.randint(0, 5), 6)
        b = rpoly(r, r.randint(0, 5), 6)
        c = rpoly(r, r.randint(-1, 9), 6)
        coprime = sp(a).gcd(sp(b)).degree() == 0
        res = POB.bezout(a, b, c)
        if not coprime:
            assert res is None
            continue
        done += 1
        s, t, d = res
        assert isnorm(s) and isnorm(t) and d > 0
        assert len(s) < len(b)                               # deg s < deg b
        lhs = PO.padd(PO.pmul(s, a), PO.pmul(t, b))
        assert lhs == PO.padd([], c, d)
        assert gcd(gcd(d, cont(s)), cont(t)) == 1
        s1, t1, h = sympy.gcdex(sp(a).to_field(), sp(b).to_field())
        want = (s1 * sp(c).to_field()).rem(sp(b).to_field()) * (1 / h.LC())
        assert Poly(sp(s).as_expr() / d, X, domain=QQ) == want


# -- part C: sparse multivariate ----------------------------------------------------------------

def test_sparse_basic():
    a = {(1, 0): 1, (0, 1): 1}                               # x + y
    b = {(1, 0): 1, (0, 1): -1}                              # x - y
    assert POC.madd(a, b) == {(1, 0): 2}
    assert POC.madd(a, b, -1) == {(0, 1): 2}
    assert POC.madd(a, a, -1) == {}
    assert POC.madd({}, a, 3) == {(1, 0): 3, (0, 1): 3}
    assert POC.mmul(a, b) == {(2, 0): 1, (0, 2): -1}
    assert POC.mmul(a, {}) == {}
    assert POC.mpow(a, 0, 2) == {(0, 0): 1}
    assert POC.mpow({}, 0, 2) == {(0, 0): 1}
    assert POC.mpow(a, 2, 2) == {(2, 0): 1, (1, 1): 2, (0, 2): 1}
    assert POC.mcont({(1, 0): -4, (0, 0): 6}) == 2 and POC.mcont({}) == 0
    assert POC.mdeg({(3, 1): 1, (0, 2): 5}, 2) == [3, 2]
    assert POC.mdeg({}, 3) == [0, 0, 0]
    assert POC.mmono({(3, 1, 2): 1, (1, 2, 4): 5}, 3) == [1, 1, 2]
    assert POC.mmono({}, 2) == [0, 0]
    c = dict(a)
    POC.madd(c, b)
    POC.mmul(c, b)
    assert c == a                                            # inputs are never mutated


def test_sparse_random_vs_sympy():
    r = random.Random(1210)
    for _ in range(200):
        nv = r.randint(1, 4)
        a = rsparse(r, nv, r.randint(0, 6))
        b = rsparse(r, nv, r.randint(0, 6))
        k = r.choice((1, -1, 2, 0))
        s = POC.madd(a, b, k)
        assert wellformed(s, nv) and msp(s, nv) == msp(a, nv) + msp(b, nv) * k
        m = POC.mmul(a, b)
        assert wellformed(m, nv) and msp(m, nv) == msp(a, nv) * msp(b, nv)
        n = r.randint(0, 3)
        p = POC.mpow(a, n, nv)
        assert wellformed(p, nv) and msp(p, nv) == msp(a, nv) ** n
        assert POC.mcont(a) == (abs(msp(a, nv).content()) if a else 0)


def test_mdivex():
    a = {(2, 0): 1, (0, 2): -1}
    assert POC.mdivex(a, {(1, 0): 1, (0, 1): 1}) == {(1, 0): 1, (0, 1): -1}
    assert POC.mdivex(a, {(1, 0): 1, (0, 1): 2}) is None
    assert POC.mdivex({(1, 0): 2}, {(0, 0): 2}) == {(1, 0): 1}
    assert POC.mdivex({(1, 0): 3}, {(0, 0): 2}) is None
    assert POC.mdivex({}, {(1, 1): 7}) == {}
    assert POC.mdivex({(0, 0): 1}, {(1, 0): 1}) is None
    # x^3 / (x + y^2): the remainder walks down in y; must stop, not run on
    assert POC.mdivex({(3, 0): 1}, {(1, 0): 1, (0, 2): 1}) is None
    r = random.Random(1211)
    for _ in range(200):
        nv = r.randint(1, 3)
        b = rsparse(r, nv, r.randint(1, 4), 2, 5) or {(0,) * nv: 3}
        c = rsparse(r, nv, r.randint(0, 4), 2, 5)
        a = POC.mmul(b, c)
        assert POC.mdivex(a, b) == c
        e = POC.madd(a, rsparse(r, nv, r.randint(1, 3), 3, 5))
        q = POC.mdivex(e, b)
        Q, R = sympy.div(msp(e, nv), msp(b, nv), *GENS[:nv], domain=QQ)
        exact = R.is_zero and all(v.is_integer for v in Poly(Q, *GENS[:nv]).coeffs())
        if exact:
            assert q is not None and msp(q, nv) == Poly(Q, *GENS[:nv], domain=ZZ)
        else:
            assert q is None


def test_kronecker_roundtrip_and_homomorphism():
    r = random.Random(1212)
    for _ in range(80):
        nv = r.randint(1, 3)
        a = rsparse(r, nv, r.randint(0, 6), 3)
        b = rsparse(r, nv, r.randint(0, 6), 3)
        ab = POC.mmul(a, b)
        D = [x + y + 1 for x, y in zip(POC.mdeg(a, nv), POC.mdeg(b, nv))]
        assert POC.munkron(POC.mkron(a, D), D) == a
        assert POC.munkron(POC.mkron(ab, D), D) == ab
        pa, pb = POC.mkron(a, D), POC.mkron(b, D)
        assert isnorm(pa) and isnorm(pb)
        assert POC.mkron(ab, D) == PO.pmul(pa, pb)          # a ring homomorphism
    # univariate: identity with the dense representation
    assert POC.mkron({(0,): 1, (2,): -3}, [3]) == [1, 0, -3]
    assert POC.munkron([1, 0, -3], [3]) == {(0,): 1, (2,): -3}
    assert POC.mkron({}, [2, 2]) == [] and POC.munkron([], [2, 2]) == {}


def test_mrel():
    # i as a variable: (x + i)^2 with i^2 = -1  ->  x^2 + 2 i x - 1
    xi = {(1, 0): 1, (0, 1): 1}
    sq = POC.mrel(POC.mmul(xi, xi), 1, 2, -1)
    assert sq == {(2, 0): 1, (1, 1): 2, (0, 0): -1}
    # t = 2^(1/3): t^5 = 2 t^2
    assert POC.mrel({(5,): 3}, 0, 3, 2) == {(2,): 6}
    assert POC.mrel({(4,): 1, (1,): -2}, 0, 3, 2) == {}       # t^4 - 2t = 0
    r = random.Random(1213)
    for _ in range(60):
        nv = r.randint(1, 3)
        a = rsparse(r, nv, r.randint(0, 6), 6)
        k = r.randrange(nv)
        q = r.randint(2, 4)
        c = r.choice((-1, 2, 3, -5))
        got = POC.mrel(a, k, q, c)
        assert wellformed(got, nv) and all(e[k] < q for e in got)
        g = GENS[:nv]
        R = sympy.rem(msp(a, nv).as_expr(), g[k] ** q - c, g[k])
        assert msp(got, nv) == Poly(R, *g, domain=ZZ)


def test_mcoef():
    a = {(2, 1): 3, (0, 1): 1, (2, 0): -1, (0, 0): 4}       # (3y - 1) x^2 + (y + 4)
    assert POC.mcoef(a, 0) == [{(0, 1): 1, (0, 0): 4}, {}, {(0, 1): 3, (0, 0): -1}]
    assert POC.mcoef(a, 1) == [{(2, 0): -1, (0, 0): 4}, {(2, 0): 3, (0, 0): 1}]
    assert POC.mcoef({}, 0) == []


def kron_gcd(a, b, nv, kronmax=64):
    """The Kronecker gcd recipe of DESIGN 8.6, built from the CVPOLY parts as norm.py would:
    strip each input's monomial content (otherwise x^2 in a and y in b both map to powers of
    X and leave a spurious common X^k: about half of random cases fail without this), check
    the KRONMAX cap, substitute, dense PRS gcd, map back, verify by exact division, put the
    common monomial back. Returns the gcd (lc > 0 in the substituted order) or None."""
    if not a or not b:
        return None
    ma, mb = POC.mmono(a, nv), POC.mmono(b, nv)
    a = POC.mmul(a, {tuple(-e for e in ma): 1})             # exact: divide by x^ma
    b = POC.mmul(b, {tuple(-e for e in mb): 1})
    D = [max(x, y) + 1 for x, y in zip(POC.mdeg(a, nv), POC.mdeg(b, nv))]
    size = 1
    for d in D:
        size *= d
    if size - 1 > kronmax:
        return None
    g = POC.munkron(PO.pgcd(POC.mkron(a, D), POC.mkron(b, D)), D)
    if POC.mdivex(a, g) is None or POC.mdivex(b, g) is None:
        return None                     # a spurious factor of the images: content only
    return POC.mmul(g, {tuple(min(x, y) for x, y in zip(ma, mb)): 1})


def test_kronecker_gcd_recipe_vs_sympy():
    r = random.Random(1214)
    hits = 0
    for _ in range(200):
        nv = r.randint(1, 3)
        g = rsparse(r, nv, r.randint(1, 3), 2, 4) or {(0,) * nv: 2}
        a = POC.mmul(g, rsparse(r, nv, r.randint(1, 3), 2, 4) or {(0,) * nv: 1})
        b = POC.mmul(g, rsparse(r, nv, r.randint(1, 3), 2, 4) or {(0,) * nv: 1})
        h = kron_gcd(a, b, nv)
        if h is None:
            continue
        hits += 1
        want = msp(a, nv).gcd(msp(b, nv))
        mine = msp(h, nv)
        assert mine == want or mine == -want, (a, b, h, want)
    assert hits >= 170                  # about 93% on random inputs (docs/notes/T1.2.md)
    # the textbook cases: (x^2 - y^2)/(x - y), (x*y + x)/(x*y), a common monomial
    assert kron_gcd({(2, 0): 1, (0, 2): -1}, {(1, 0): 1, (0, 1): -1}, 2) ==         {(1, 0): -1, (0, 1): 1}                              # y - x: the last variable leads
    assert kron_gcd({(1, 1): 1, (1, 0): 1}, {(1, 1): 1}, 2) == {(1, 0): 1}
    assert kron_gcd({(3, 1): 2, (2, 2): 4}, {(2, 0): 6}, 2) == {(2, 0): 2}


def test_inputs_never_mutated():
    """Every public function leaves its arguments as they were (callers share lists)."""
    import copy
    r = random.Random(1217)
    for _ in range(40):
        a = rpoly(r, r.randint(0, 6))
        b = rpoly(r, r.randint(0, 4))
        c = rpoly(r, r.randint(-1, 5))
        m = [[r.randint(-5, 5) for _ in range(4)] for _ in range(3)]
        sa = {(1, 2): 3, (0, 1): -1}
        sb = {(1, 0): 1, (0, 0): 2}
        args = [a, b, c, m, sa, sb]
        keep = copy.deepcopy(args)
        PO.padd(a, b, 2)
        PO.pmul(a, b)
        PO.ppow(b, 3)
        PO.pderiv(a)
        PO.pprim(a)
        PO.pdivrem(a, b)
        PO.pdivex(a, b)
        PO.pgcd(a, b)
        PO.yun(a)
        POB.ratroots(a)
        POB.gjsolve(m, 3)
        POB.bezout(a, b, c)
        POC.madd(sa, sb, -1)
        POC.mmul(sa, sb)
        POC.mpow(sb, 2, 2)
        POC.mdivex(POC.mmul(sa, sb), sb)
        POC.mdivex(sa, sb)
        POC.mrel(sa, 1, 1, 3)
        POC.mcoef(sa, 0)
        POC.mkron(sa, [2, 4])
        assert args == keep


def test_ratroots_many_roots():
    # (x-1)(x-2)...(x-10): a0 = 10! has 270 divisors
    a = [1]
    for k in range(1, 11):
        a = PO.pmul(a, [-k, 1])
    roots, cof, ok = POB.ratroots(a)
    assert ok and roots == [(k, 1, 1) for k in range(1, 11)] and cof == [1]
    r = random.Random(1218)
    for _ in range(10):
        a = [r.choice((1, -3, 5))]
        want = {}
        for _ in range(8):
            q = r.randint(1, 6)
            p = r.randint(-20, 20)
            g = gcd(p, q)
            a = PO.pmul(a, [-p, q])
            key = (p // g, q // g)
            want[key] = want.get(key, 0) + 1
        roots, cof, ok = POB.ratroots(a)
        assert ok
        got = {(p, q): m for p, q, m in roots}
        assert got == want
        assert len(cof) == 1


def test_gjsolve_square_and_wide():
    # a 6x6 Hilbert-like system with a unique solution, checked exactly
    n = 6
    rows = []
    for i in range(n):
        row = [60 * 7 * 11 // (i + j + 1) for j in range(n)]       # 4620/(i+j+1)
        row.append(sum(row[j] * (j + 1) for j in range(n)))         # solution 1..6
        rows.append(row)
    piv, out = POB.gjsolve(rows, n)
    assert piv == list(range(n))
    for k in range(n):
        assert out[k][n] == (k + 1) * out[k][k]
    # wide: 2 equations, 4 unknowns, 2 right-hand sides
    m = [[1, 2, 0, 1, 3, 1], [2, 4, 1, 0, 7, 0]]
    piv, out = POB.gjsolve(m, 4)
    R, sp_piv = Matrix(m).rref()
    assert piv == list(sp_piv)
    for k, row in enumerate(out):
        assert [Rational(v, row[piv[k]]) for v in row] == list(R.row(k))


def test_bezout_high_degree_target():
    r = random.Random(1219)
    for _ in range(20):
        a = rpoly(r, 2, 5)
        b = rpoly(r, 3, 5)
        if sp(a).gcd(sp(b)).degree():
            continue
        c = rpoly(r, 9, 5)                                   # deg c >= deg a + deg b
        s, t, d = POB.bezout(a, b, c)
        assert len(s) < len(b)
        assert PO.padd(PO.pmul(s, a), PO.pmul(t, b)) == PO.padd([], c, d)


# -- device constraints -------------------------------------------------------------------------

def _path(mod):
    return os.path.join(SRC, mod + '.py')


@pytest.mark.parametrize('mod', PARTS)
def test_part_lint_clean(mod):
    assert lint.lint_file(_path(mod)) == []


def test_parts_framelint_clean():
    an = framelint.analyze_dir(SRC)
    mine = [e for e in an.errors if any(os.path.basename(_path(m)) in e for m in PARTS)]
    assert mine == []


def code_lines(src):
    """Lines the bundler keeps: no blank lines, comments or docstrings (DESIGN 19.2)."""
    tree = ast.parse(src)
    drop = set()
    for n in ast.walk(tree):
        body = getattr(n, 'body', None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and \
                isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            drop.update(range(body[0].lineno, body[0].end_lineno + 1))
    keep = set()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                        tokenize.DEDENT, tokenize.ENDMARKER):
            continue
        for ln in range(tok.start[0], tok.end[0] + 1):
            if ln not in drop:
                keep.add(ln)
    return len(keep)


@pytest.mark.parametrize('mod', PARTS)
def test_part_size(mod):
    with open(_path(mod), encoding='ascii') as fh:
        n = code_lines(fh.read())
    assert n <= LAZYMAX, '%s has %d code lines (LAZYMAX %d)' % (mod, n, LAZYMAX)


@pytest.mark.parametrize('mod', PARTS)
def test_no_node_dependency(mod):
    """T1.2: no node dependency; the parts never import each other (4.2, 4.3) either."""
    with open(_path(mod), encoding='ascii') as fh:
        tree = ast.parse(fh.read())
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in n.names]
            assert not set(names) & {'node', 'poly', 'polyb', 'polyc', 'run'}, names


def test_levels_declared():
    """Every public function is annotated; leaves are L7 and the drivers stay callable from
    the algorithm layer (L3) and the helper layer (L4)."""
    want = {'poly': {'padd': 7, 'pmul': 7, 'ppow': 6, 'pderiv': 7, 'peval': 7, 'pcont': 7,
                     'pprim': 6, 'pdivrem': 6, 'pdivex': 7, 'pgcd': 5, 'yun': 4},
            'polyb': {'divisors': 7, 'ratroots': 6, 'gjsolve': 7, 'bezout': 6},
            'polyc': {'madd': 7, 'mmul': 7, 'mpow': 6, 'mcont': 7, 'mdeg': 7, 'mmono': 7,
                      'mdivex': 6, 'mkron': 7, 'munkron': 7, 'mrel': 7, 'mcoef': 7}}
    an = framelint.analyze_dir(SRC)
    lv = an.levels()
    for mod in PARTS:
        assert lv[mod] == want[mod], mod


def test_depth_at_declared_levels(evodepth):
    """Run the deepest drivers from the level they are declared at (automatic base)."""
    a = PO.pmul(PO.ppow([1, 1], 3), PO.ppow([-2, 1], 2))
    _, d, _ = evodepth.measure(PO.yun, a)
    assert d == 7
    _, d, _ = evodepth.measure(POB.bezout, [1, 0, 1], [-1, 1], [1])
    assert d == 7
    _, d, _ = evodepth.measure(POC.mpow, {(1, 1): 2, (0, 0): 1}, 3, 2)
    assert d == 7


@pytest.mark.strict_depth
def test_strict_depth():
    a = PO.pmul(PO.ppow([1, 1], 3), PO.ppow([-2, 1], 2))
    assert PO.yun(a)[1] == [([-2, 1], 2), ([1, 1], 3)]
    assert POB.ratroots(a)[0] == [(-1, 1, 3), (2, 1, 2)]       # candidate order: 1, -1, 2


def test_dict_order_independence():
    """Sparse results do not depend on dict insertion order (device dicts iterate in slot
    order, CPython in insertion order)."""
    r = random.Random(1215)
    for _ in range(30):
        a = rsparse(r, 3, 8)
        b = rsparse(r, 3, 8)
        ra = dict(sorted(a.items(), reverse=True))
        rb = dict(sorted(b.items(), reverse=True))
        assert POC.mmul(a, b) == POC.mmul(ra, rb)
        assert sorted(POC.mmul(a, b).items()) == sorted(POC.mmul(ra, rb).items())
        assert POC.mkron(a, [4, 4, 4]) == POC.mkron(ra, [4, 4, 4])
        ab = POC.mmul(a, b)
        assert POC.mdivex(ab, b) == POC.mdivex(dict(sorted(ab.items())), rb)


@pytest.mark.slow
def test_dense_random_large():
    """Bigger degrees and coefficients (slow tier)."""
    r = random.Random(1216)
    for _ in range(40):
        g = rpoly(r, r.randint(1, 6), 10 ** 6)
        a = PO.pmul(g, rpoly(r, r.randint(0, 10), 10 ** 6))
        b = PO.pmul(g, rpoly(r, r.randint(0, 10), 10 ** 6))
        assert sp(PO.pgcd(a, b)) == sp(a).gcd(sp(b))
        c, fs = PO.yun(PO.pmul(a, PO.ppow(g, 2)))
        back = [c]
        for f, m in fs:
            back = PO.pmul(back, PO.ppow(f, m))
        assert back == PO.pmul(a, PO.ppow(g, 2))
