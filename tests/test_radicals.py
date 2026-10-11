"""T1.1 radicals (DESIGN 6.2, 8.2 rules 3, 6, 7, 11): alg section 6 seeds 2.2, the canonical
form, real odd roots, even roots of negatives, and a SymPy-checked random property."""
import math
import random

import pytest

import node as K
from test_node import pw, pwe, q, sm, prod, sqrt, div, ev, close, struct

sympy = pytest.importorskip('sympy')


def rad(c, n, p=1, s=2):
    """The canonical radical node c * n^(p/s) (c an int), built directly (no constructor)."""
    return K.mk((K.MUL, K.num(c), K.num(n), K.num(p, 0, s)))


def to_sympy(e):
    """The SymPy value of a numeric node (positive numeric bases only, so principal powers)."""
    t = K.N[e]
    op = t[0]
    if op == K.NUM:
        return sympy.Rational(t[1], t[3]) + sympy.I * sympy.Rational(t[2], t[3])
    if op == K.CON:
        return {0: sympy.pi, 1: sympy.E}[t[1]]
    if op == K.ADD:
        return to_sympy(t[1]) + sympy.Add(*[to_sympy(t[j + 1]) * to_sympy(t[j])
                                            for j in range(2, len(t), 2)])
    if op == K.MUL:
        return to_sympy(t[1]) * sympy.Mul(*[to_sympy(t[j]) ** to_sympy(t[j + 1])
                                            for j in range(2, len(t), 2)])
    if op == K.LN:
        return sympy.log(to_sympy(t[1]))
    if op == K.ATAN:
        return sympy.atan(to_sympy(t[1]))
    raise ValueError(t)


def mp_pow(a, d, p, s):
    """(a/d)^(p/s) at 50 digits, with the real odd root of a negative base (DESIGN 20.5)."""
    mp = sympy.mpmath if hasattr(sympy, 'mpmath') else __import__('mpmath')
    mp.mp.dps = 50
    g = math.gcd(p, s)
    p, s = p // g, s // g
    b = mp.mpf(a) / d
    if b < 0 and s % 2:
        r = (-b) ** (mp.mpf(p) / s)
        return -r if p % 2 else r
    return mp.power(mp.mpc(b), mp.mpf(p) / s)


def same(e, want):
    got = complex(sympy.N(to_sympy(e), 40))
    want = complex(want)
    return abs(got - want) <= 1e-25 * max(1.0, abs(want))


# -- alg section 6 seeds 2.2 ---------------------------------------------------------------------

def test_seed_sqrt72():
    assert sqrt(q(72)) == rad(6, 2)


def test_seed_sqrt_8_over_27():
    assert sqrt(q(8, 27)) == K.mk((K.MUL, K.num(2, 0, 9), K.num(6), K.HALF))


def test_seed_real_cube_root_of_minus_8():
    assert pw(q(-8), 1, 3) == q(-2)


def test_seed_sqrt_3_plus_2sqrt2_is_left_for_simplify():
    e = sqrt(sm(q(3), prod(q(2), sqrt(q(2)))))
    t = K.N[e]                                   # denesting is simplify's job (6.2, T1.10)
    assert t[0] == K.MUL and K.N[t[2]][0] == K.ADD and t[3] == K.HALF
    assert close(ev(e), 1 + math.sqrt(2))


def test_seed_rationalized_one_over_sqrt2():
    assert div(q(1), sqrt(q(2))) == K.mk((K.MUL, K.HALF, K.TWO, K.HALF))


def test_seed_sqrt_minus_4():
    assert sqrt(q(-4)) == q(0, 1, 2)


# -- the canonical form ------------------------------------------------------------------------

def test_one_base_per_exponent_and_prime_merging():
    s2, s3, s6 = sqrt(q(2)), sqrt(q(3)), sqrt(q(6))
    assert prod(s2, s3) == s6
    assert prod(s2, s6) == rad(2, 3)                                   # sqrt(12) = 2 sqrt(3)
    assert prod(s2, pw(q(2), 1, 3)) == pw(q(2), 5, 6)
    assert pw(q(4), 1, 3) == pw(q(2), 2, 3)                            # per-prime canonical
    assert prod(pw(q(4), 1, 3), pw(q(2), 1, 3)) == q(2)
    assert pw(q(12), 1, 4) == prod(sqrt(q(2)), pw(q(3), 1, 4))
    assert sqrt(q(2, 3)) == K.mk((K.MUL, K.num(1, 0, 3), K.num(6), K.HALF))
    assert pw(q(8), 2, 3) == q(4) and pw(q(1, 8), 1, 3) == q(1, 2) and pw(q(2), 3, 2) == rad(2, 2)
    assert pw(q(8), -2, 3) == q(1, 4) and pw(q(27, 8), 4, 3) == q(81, 16)
    assert prod(s2, s2) == q(2) and prod(s3, s6, s2) == q(6)
    assert sqrt(q(1)) == K.ONE and sqrt(q(0)) == K.ZERO
    with pytest.raises(K.Undefined):
        pw(q(0), -1, 2)
    t = K.N[prod(pw(q(2), 1, 3), pw(q(3), 1, 3), sqrt(q(5)))]
    assert sorted((K.N[t[j]][1], K.N[t[j + 1]][1:]) for j in range(2, len(t), 2)) == \
        [(5, (1, 0, 2)), (6, (1, 0, 3))]


def test_negative_bases():
    assert pw(q(-8), 2, 3) == q(4) and pw(q(-32), 1, 5) == q(-2)
    assert pw(q(-2), 1, 3) == K.neg_(pw(q(2), 1, 3))
    assert sqrt(q(-2)) == K.mk((K.MUL, K.I, K.TWO, K.HALF))           # i sqrt(2)
    assert sqrt(q(-1, 4)) == q(0, 2, 1)                               # i/2
    assert pw(q(-4), 1, 4) == q(1, 1, 1)                              # 1 + i
    assert pw(q(-1), 1, 4) == K.mk((K.MUL, K.num(1, 1, 2), K.TWO, K.HALF))
    assert prod(sqrt(q(-1)), sqrt(q(-1))) == K.MONE
    assert prod(pw(q(-1), 1, 3), pw(q(-1), 1, 3)) == K.ONE           # real roots
    e6 = pw(q(-1), 1, 6)                                              # e^(i pi/6)
    assert K.N[e6] == (K.MUL, K.ONE, K.E, prod(q(0, 6, 1), K.PI))
    assert prod(e6, e6) == pwe(K.E, prod(q(0, 3, 1), K.PI))           # not the real root -1
    assert pw(e6, 6) == K.MONE and pw(e6, 3) == K.I
    assert sqrt(q(-3, 5)) == K.mk((K.MUL, K.num(0, 1, 5), K.num(15), K.HALF))


def test_exp_of_i_pi_multiples():
    def e_ipi(p, d):
        return pwe(K.E, prod(q(0, d, p), K.PI))
    assert e_ipi(1, 1) == K.MONE and e_ipi(2, 1) == K.ONE and e_ipi(1, 2) == K.I
    assert e_ipi(-1, 2) == q(0, 1, -1) and e_ipi(3, 2) == q(0, 1, -1)
    assert e_ipi(1, 4) == K.mk((K.MUL, K.num(1, 1, 2), K.TWO, K.HALF))
    assert e_ipi(-3, 4) == K.mk((K.MUL, K.num(-1, -1, 2), K.TWO, K.HALF))
    assert K.N[e_ipi(1, 3)][2] == K.E


def test_gaussian_bases_with_fractional_exponents_are_kept():
    b = q(1, 1, 1)
    e = sqrt(b)
    assert K.N[e] == (K.MUL, K.ONE, b, K.HALF)
    assert prod(e, e) == q(2, 1, 0) or prod(e, e) == b
    assert prod(e, e) == b and pw(e, 4) == q(0, 1, 2)


def test_large_radicands_and_cofactors():
    p, r = 10007, 1000003
    assert sqrt(q(p * p * 3)) == rad(p, 3)
    assert pw(q(p ** 3), 1, 3) == q(p)
    assert K.N[sqrt(q(p * r))] == (K.MUL, K.ONE, K.num(p * r), K.HALF)
    assert sqrt(q(2 ** 200)) == q(2 ** 100)
    big = 2 ** 300 * 3
    assert sqrt(q(big)) == rad(2 ** 150, 3)


# -- symbolic radicals (rules 5-7) ---------------------------------------------------------------

def test_symbolic_radicals():
    x = K.sym('x')
    assert sqrt(pw(x, 2)) == K.fn_(K.ABS, x)
    assert prod(sqrt(x), pw(x, 1, 3)) == pw(x, 5, 6)
    assert pw(sqrt(x), 2) == x and pw(pw(x, 1, 3), 3) == x
    assert sqrt(prod(q(8), x)) == prod(rad(2, 2), sqrt(x))
    assert pw(prod(q(1, 2), x), 1, 3) == div(pw(prod(q(4), x), 1, 3), q(2))
    assert prod(sqrt(q(2)), sqrt(x), sqrt(q(2)), sqrt(x)) == prod(q(2), x)


# -- random property: canonical radicals equal their SymPy values ----------------------------------

@pytest.mark.parametrize('seed', range(6))
def test_random_radical_products_match_sympy(seed):
    rng = random.Random(seed)
    for _ in range(25):
        pairs = []
        want = 1
        for _ in range(rng.randint(1, 3)):
            a = rng.choice([-1, 1]) * rng.randint(1, 200)
            d = rng.randint(1, 30)
            s = rng.randint(2, 6)
            p = rng.choice([1, 1, 2, 3, -1, 5]) % (2 * s) or 1
            pairs.append((q(a, d), K.num(p, 0, s)))
            want *= mp_pow(a, d, p, s)
        e = K.mul_(K.ONE, pairs)
        assert same(e, want), (pairs, struct(e))
        # every numeric base is a positive integer and every exponent a fraction in (0, 1)
        t = K.N[e]
        if t[0] == K.MUL:
            for j in range(2, len(t), 2):
                b, x = K.N[t[j]], K.N[t[j + 1]]
                if b[0] == K.NUM:
                    assert b[1] >= 2 and b[3] == 1 and 0 < x[1] < x[3]
        K.reset()


@pytest.mark.parametrize('seed', range(4))
def test_equal_radicals_built_two_ways_are_one_node(seed):
    rng = random.Random(100 + seed)
    for _ in range(40):
        n = rng.randint(2, 500)
        s = rng.randint(2, 5)
        # n^(1/s) directly, and as the product of its prime powers
        f = K.ifac(n)
        parts = [pw(q(f[j]), f[j + 1], s) for j in range(0, len(f), 2)]
        assert pw(q(n), 1, s) == prod(*parts)
        m = rng.randint(1, 9)
        assert pw(q(n ** m), 1, s * m) == pw(q(n), 1, s)
        K.reset()
