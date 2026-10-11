"""T1.1 number tower: Gaussian-rational kernels, floats, factoring and the size guards (DESIGN 6.1,
6.3). The kernels are checked against fractions.Fraction pairs and sympy.factorint."""
import math
import random
import time
from fractions import Fraction as F

import pytest

import node as K
from test_node import pw, pwe, q, sm, prod, ev, close


def gq(t):
    """(re, im) Fractions of a NUM tuple."""
    assert t[0] == K.NUM
    return (F(t[1], t[3]), F(t[2], t[3]))


def normal(t):
    a, b, d = t[1:]
    return t[0] == K.NUM and d >= 1 and math.gcd(math.gcd(a, b), d) == 1 and \
        all(type(v) is int for v in (a, b, d))


def rnd_num(rng, big=False, real=False):
    m = 10 ** 30 if big else 50
    d = rng.randint(1, m)
    b = 0 if real or rng.random() < 0.4 else rng.randint(-m, m)
    return K.nnorm(rng.randint(-m, m), b, d)


@pytest.mark.parametrize('seed', range(5))
def test_kernels_match_fraction_arithmetic(seed):
    rng = random.Random(seed)
    for _ in range(400):
        big = rng.random() < 0.3
        x = rnd_num(rng, big)
        y = rnd_num(rng, big)
        (xa, xb), (ya, yb) = gq(x), gq(y)
        s = K.nadd(x, y)
        assert normal(s) and gq(s) == (xa + ya, xb + yb)
        p = K.nmul(x, y)
        assert normal(p) and gq(p) == (xa * ya - xb * yb, xa * yb + xb * ya)
        n = K.nneg(x)
        assert normal(n) and gq(n) == (-xa, -xb)
        if xa or xb:
            v = K.ninv(x)
            m = xa * xa + xb * xb
            assert normal(v) and gq(v) == (xa / m, -xb / m)
        k = rng.randint(-6, 6)
        if xa or xb or k >= 0:
            r = K.npowi(x, k)
            want = (F(1), F(0))
            base = (xa, xb)
            if k < 0:
                m = xa * xa + xb * xb
                base = (xa / m, -xb / m)
            for _ in range(abs(k)):
                want = (want[0] * base[0] - want[1] * base[1],
                        want[0] * base[1] + want[1] * base[0])
            assert normal(r) and gq(r) == want
        if not xb and not yb:
            assert K.ncmp(x, y) == (xa > ya) - (xa < ya)
            assert K.nsign(x) == (xa > 0) - (xa < 0)


def test_nnorm_and_num():
    assert K.nnorm(4, -6, -8) == (K.NUM, -2, 3, 4)
    assert K.nnorm(0, 0, -5) == (K.NUM, 0, 0, 1)
    assert K.nnorm(10 ** 50, 0, 10 ** 49) == (K.NUM, 10, 0, 1)
    with pytest.raises(K.Undefined):
        K.nnorm(1, 0, 0)
    with pytest.raises(K.Undefined):
        K.num(1, 0, 0)
    assert K.num(6, 0, 4) == K.num(3, 0, 2) and K.num(0) == K.ZERO and K.num(1, 0, 2) == K.HALF
    assert K.num(0, 1) == K.I and K.num(-1) == K.MONE


def test_kernel_errors_and_fast_paths():
    with pytest.raises(K.Undefined):
        K.ninv(K.Q0)
    with pytest.raises(K.Undefined):
        K.npowi(K.Q0, -2)
    with pytest.raises(K.Undefined):
        K.nsign((K.NUM, 1, 1, 1))
    with pytest.raises(K.Undefined):
        K.ncmp((K.NUM, 0, 1, 1), K.Q1)
    assert K.npowi(K.Q0, 0) == K.Q1 and K.npowi(K.Q0, 3) == K.Q0
    i = (K.NUM, 0, 1, 1)
    assert [K.npowi(i, n) for n in range(-2, 5)] == [K.QM1, (K.NUM, 0, -1, 1), K.Q1, i, K.QM1,
                                                     (K.NUM, 0, -1, 1), K.Q1]
    assert K.npowi(K.QM1, 7) == K.QM1 and K.npowi(K.QM1, -8) == K.Q1
    assert K.npowi((K.NUM, 0, -1, 1), 3) == i


def test_gaussian_folding_in_the_constructors():
    i = K.I
    assert pw(i, 2) == K.MONE                                          # i^2 = -1
    assert pw(q(1, 1, 1), -1) == q(1, 2, -1)                           # 1/(1+i) = (1-i)/2
    assert pw(q(0, 1, 2), 3) == q(0, 1, -8)                            # (2i)^3 = -8i
    assert prod(i, i, i, i) == K.ONE and sm(i, q(3)) == q(3, 1, 1)
    assert K.mul_(q(2, 1, 1), [(q(2, 1, -1), K.ONE)]) == q(5)          # (2+i)(2-i) = 5


def test_maxbits_guard_is_immediate():
    t0 = time.perf_counter()
    with pytest.raises(K.CasError) as ei:
        pw(q(2), 10 ** 6)
    assert ei.value.args[0] == 'number too large'
    with pytest.raises(K.CasError):
        K.npowi((K.NUM, 3, 0, 7), -(10 ** 9))
    with pytest.raises(K.CasError):
        K.npowi((K.NUM, 1, 1, 1), 10 ** 6)
    with pytest.raises(K.CasError):
        pw(q(1, 3), 1, 10 ** 5)                       # rationalizing would need 3^99999
    assert time.perf_counter() - t0 < 1.0
    assert K.npowi((K.NUM, 2, 0, 1), 16000) == (K.NUM, 2 ** 16000, 0, 1)


# -- floats (6.3) ----------------------------------------------------------------------------------

def test_flt_leaf_is_finite_and_has_no_negative_zero():
    z = K.flt(-0.0, -0.0)
    assert K.N[z] == (K.FLT, 0.0, 0.0) and math.copysign(1.0, K.N[z][1]) > 0
    for bad in (float('inf'), float('-inf'), float('nan')):
        with pytest.raises(K.Undefined):
            K.flt(bad)
    assert K.flt(2) == K.flt(2.0) and K.N[K.flt(1, 2)] == (K.FLT, 1.0, 2.0)


def test_float_kernels_and_overflow():
    h = (K.FLT, 0.5, 0.0)
    assert K.nadd(h, K.QH) == (K.FLT, 1.0, 0.0)
    assert K.nmul(h, (K.NUM, 1, 1, 1)) == (K.FLT, 0.5, 0.5)
    assert K.ninv((K.FLT, 0.0, 2.0)) == (K.FLT, 0.0, -0.5)
    assert K.npowi((K.FLT, -2.0, 0.0), 3) == (K.FLT, -8.0, 0.0)
    assert K.nneg((K.FLT, 0.0, 1.0)) == (K.FLT, 0.0, -1.0)
    r = K.nneg((K.FLT, 0.0, 0.0))
    assert math.copysign(1.0, r[1]) > 0
    assert K.ncmp(h, K.QH) == 0 and K.ncmp((K.FLT, 0.3, 0.0), (K.NUM, 1, 0, 3)) < 0
    for f in (lambda: K.nmul((K.FLT, 1e300, 0.0), (K.FLT, 1e300, 0.0)),
              lambda: K.nadd((K.FLT, 1e308, 0.0), (K.FLT, 1e308, 0.0)),
              lambda: K.npowi((K.FLT, 10.0, 0.0), 400),
              lambda: K.nadd((K.FLT, 1.0, 0.0), (K.NUM, 10 ** 400, 0, 1)),
              lambda: K.fpow((K.FLT, 10.0, 0.0), (K.NUM, 1000, 0, 3))):
        with pytest.raises(K.CasError):
            f()
    with pytest.raises(K.Undefined):
        K.ninv((K.FLT, 0.0, 0.0))
    with pytest.raises(K.Undefined):
        K.npowi((K.FLT, 0.0, 0.0), -1)


def test_fpow_conventions():
    r = K.fpow((K.FLT, -8.0, 0.0), (K.NUM, 2, 0, 3))
    assert r[0] == K.FLT and abs(r[1] - 4.0) < 1e-14 and r[2] == 0.0
    assert K.fpow((K.FLT, -8.0, 0.0), (K.NUM, 1, 0, 3)) == (K.FLT, -2.0, 0.0)
    r = K.fpow((K.FLT, -4.0, 0.0), (K.NUM, 1, 0, 2))
    assert abs(r[1]) < 1e-15 and abs(r[2] - 2.0) < 1e-15
    r = K.fpow((K.NUM, -8, 0, 1), (K.FLT, 0.5, 0.0))             # a float exponent: principal
    assert abs(complex(r[1], r[2]) - (-8) ** 0.5) < 1e-12
    assert K.fpow((K.FLT, 0.0, 0.0), (K.NUM, 1, 0, 2)) == (K.FLT, 0.0, 0.0)
    with pytest.raises(K.Undefined):
        K.fpow((K.FLT, 0.0, 0.0), (K.NUM, -1, 0, 2))


# -- integer factoring (6.2) -------------------------------------------------------------------

def test_ifac_matches_sympy():
    sympy = pytest.importorskip('sympy')
    rng = random.Random(7)
    ns = [1, 2, 4, 360, 1024, 9973 * 9973, 10007, 10 ** 8 - 1, 2 ** 61 - 1]
    ns += [rng.randint(2, 10 ** 8) for _ in range(150)]
    for n in ns:
        f = K.ifac(n)
        want = sympy.factorint(n)
        got = {f[j]: f[j + 1] for j in range(0, len(f), 2)}
        if n < 10 ** 8:
            assert got == want, n
        else:
            assert math.prod(p ** a for p, a in got.items()) == n
        assert list(f[0::2]) == sorted(f[0::2])


def test_ifac_cofactors_above_the_trial_bound():
    p, r = 10007, 1000003                       # primes above TRIAL = 10^4
    assert K.ifac(p * p) == (p, 2)
    assert K.ifac(p ** 3) == (p, 3)
    assert K.ifac(2 ** 5 * p ** 6) == (2, 5, p, 6)
    assert K.ifac(p * r) == (p * r, 1)          # partly reduced: a documented cofactor
    assert K.ifac(r * r * 12) == (2, 2, 3, 1, r, 2)
    assert K.rootsplit(72, 2) == (6, 2) and K.rootsplit(p ** 5, 2) == (p * p, p)
    assert K.rootsplit(1, 3) == (1, 1) and K.rootsplit(16 * 3, 4) == (2, 3)


def test_ifac_polls_cancel(monkeypatch):
    monkeypatch.setattr(K, 'ESC', lambda: True)
    with pytest.raises(K.Cancel):
        K.ifac(10007 * 10009)


# -- numeric values of constructed numbers ----------------------------------------------------

@pytest.mark.parametrize('seed', range(4))
def test_random_numeric_products_and_sums(seed):
    rng = random.Random(50 + seed)
    for _ in range(60):
        fs = []
        want = 1
        for _ in range(rng.randint(1, 4)):
            a = rng.randint(-30, 30) or 1
            d = rng.randint(1, 12)
            b = rng.choice([0, 0, 0, rng.randint(-3, 3)])
            n = rng.choice([1, 1, 2, -1, -2, 3])
            fs.append((q(a, d, b), q(n)))
            want *= (complex(a, b) / d) ** n
        e = K.mul_(K.ONE, fs)
        assert K.N[e][0] == K.NUM and close(ev(e), want)
        s = sm(*[pw(f, n) for f, (_, n) in zip([f for f, _ in fs], [(0, K.N[x][1]) for _, x in fs])])
        tot = sum((complex(K.N[f][1], K.N[f][2]) / K.N[f][3]) ** K.N[x][1] for f, x in fs)
        assert close(ev(s), tot)
    assert K.N[pwe(q(2), K.I)] == (K.MUL, K.ONE, K.TWO, K.I)      # 2^i is kept
