"""T1.1 special values and function rules in fn_ (DESIGN 6.3, 6.4): alg section 6 seeds 2.3,
every table angle for the six trig functions, the inverse tables, sign normalization (D15),
ln, abs, sign/floor/ceil/fact and the infinity table."""
import cmath
import math

import pytest

import node as K
from test_node import pw, pwe, q, sm, sub, prod, sqrt, div, pimul, ev, close, struct

TRIG = {K.SIN: math.sin, K.COS: math.cos, K.TAN: math.tan,
        K.SEC: lambda a: 1 / math.cos(a), K.CSC: lambda a: 1 / math.sin(a),
        K.COT: lambda a: 1 / math.tan(a)}
KEYS = sorted(K.COS_T)                          # 0 10 12 15 20 24 30 36 40 45 48 50 60


def angle(m):
    """m*pi/120 as the constructors build it."""
    return pimul(m, 120)


def has_fn(e):
    t = K.N[e]
    if t[0] >= K.FN0:
        return True
    return t[0] >= K.COMP and any(has_fn(c) for c in t[1:])


# -- alg section 6 seeds 2.3 ---------------------------------------------------------------------

def test_seed_cos_5pi_12():
    e = K.fn_(K.COS, pimul(5, 12))                    # a sum: (sqrt(6) - sqrt(2))/4
    assert e == sm(div(sqrt(q(6)), q(4)), div(sqrt(q(2)), q(-4)))


def test_seed_tan_pi_12():
    assert K.fn_(K.TAN, pimul(1, 12)) == sub(q(2), sqrt(q(3)))


def test_seed_cos_pi_5():
    assert K.fn_(K.COS, pimul(1, 5)) == sm(q(1, 4), div(sqrt(q(5)), q(4)))


def test_seed_sin_30_degrees():
    # degree mode: the builder (T1.5) makes sin(30) into sin(30*pi/180) (6.5)
    assert K.fn_(K.SIN, K.mul_(q(30), [(K.PI, K.ONE), (q(180), K.MONE)])) == K.HALF


def test_seed_atan_sqrt3():
    assert K.fn_(K.ATAN, sqrt(q(3))) == pimul(1, 3)


# -- the tables ----------------------------------------------------------------------------------

def _reducible(m):
    """True if the table covers angle m*pi/120 (by symmetry)."""
    r = m % 120
    return min(r, 120 - r) in K.COS_T or (m % 60) in (0,)


@pytest.mark.parametrize('op', sorted(TRIG))
def test_every_table_angle_folds_to_its_exact_value(op):
    f = TRIG[op]
    n = 0
    for m in range(-240, 480):
        r = m % 120
        if min(r, 120 - r) not in K.COS_T:
            continue
        a = m * math.pi / 120
        pole = abs(math.cos(a)) < 1e-9 if op in (K.TAN, K.SEC) else \
            abs(math.sin(a)) < 1e-9 if op in (K.CSC, K.COT) else False
        if pole:
            with pytest.raises(K.Undefined):
                K.fn_(op, angle(m))
            continue
        e = K.fn_(op, angle(m))
        assert not has_fn(e) and K.V[e] == 0, (op, m, struct(e))
        assert close(ev(e).real, f(a), 1e-12) and ev(e).imag == 0, (op, m)
        n += 1
        if K.NN > 600:
            K.reset()
    assert n > 100


def test_angles_off_the_table_stay_unevaluated_with_their_sign():
    for op in sorted(TRIG):
        for m in (1, 61, 119, 121, 179, 239, -1, -61):
            e = K.fn_(op, angle(m))
            a = m * math.pi / 120
            assert has_fn(e) and close(ev(e).real, TRIG[op](a), 1e-12), (op, m)
    x = K.sym('x')
    assert K.N[K.fn_(K.SIN, pimul(1, 7))][0] == K.SIN
    assert K.N[K.fn_(K.COS, sm(K.PI, x))][0] == K.COS


def test_pi_over_12_multiples_always_fold():
    for op in sorted(TRIG):
        for k in range(-30, 31):
            try:
                e = K.fn_(op, pimul(k, 12))
            except K.Undefined:
                continue
            assert not has_fn(e)


def test_zero_and_pi_arguments():
    assert K.fn_(K.SIN, K.ZERO) == K.ZERO and K.fn_(K.COS, K.ZERO) == K.ONE
    assert K.fn_(K.TAN, K.PI) == K.ZERO and K.fn_(K.COS, K.PI) == K.MONE
    assert K.fn_(K.SEC, K.PI) == K.MONE
    for op in (K.CSC, K.COT):
        with pytest.raises(K.Undefined):
            K.fn_(op, K.ZERO)
    with pytest.raises(K.Undefined):
        K.fn_(K.TAN, pimul(1, 2))
    with pytest.raises(K.Undefined):
        K.fn_(K.SEC, pimul(-3, 2))


def _forward(op, m):
    return K.fn_(op, angle(m))


def test_inverse_hash_tables_regenerate():
    asin = {}
    atan = {}
    for m in range(-60, 61):
        if abs(m) in K.COS_T:
            asin.setdefault(K.H[_forward(K.SIN, m)], []).append(m)
        if abs(m) in K.TAN_T:
            atan.setdefault(K.H[_forward(K.TAN, m)], []).append(m)
    assert all(len(v) == 1 for v in asin.values()) and all(len(v) == 1 for v in atan.values())
    assert {h: v[0] for h, v in asin.items()} == K.ASIN_H
    assert {h: v[0] for h, v in atan.items()} == K.ATAN_H


def test_inverse_trig_of_every_table_value():
    for m in KEYS:
        for sgn in (1, -1):
            v = _forward(K.SIN, sgn * m)
            assert K.fn_(K.ASIN, v) == (angle(sgn * m) if m else K.ZERO)
            want = (60 - sgn * m)
            assert K.fn_(K.ACOS, v) == (angle(want) if want else K.ZERO)
    for m in sorted(K.TAN_T):
        for sgn in (1, -1):
            v = _forward(K.TAN, sgn * m)
            assert K.fn_(K.ATAN, v) == (angle(sgn * m) if m else K.ZERO)
    assert K.fn_(K.ACOS, K.MONE) == K.PI and K.fn_(K.ASIN, K.MONE) == pimul(-1, 2)
    assert K.fn_(K.ACOS, q(-1, 2)) == pimul(2, 3)


def test_inverse_trig_off_the_tables():
    x = K.sym('x')
    for op in (K.ASIN, K.ACOS, K.ATAN):
        for v in (q(1, 3), q(2), sqrt(q(7)), x):
            e = K.fn_(op, v)
            assert K.N[e] == (op, v)
    assert K.fn_(K.ASIN, q(-1, 3)) == K.neg_(K.fn_(K.ASIN, q(1, 3)))
    assert K.N[K.fn_(K.ACOS, q(-1, 3))] == (K.ACOS, q(-1, 3))     # acos is neither odd nor even


# -- sign normalization (D15) and inverse cancellation -------------------------------------------

def test_sign_normalization():
    x = K.sym('x')
    omx, xm1 = sub(q(1), x), sub(x, q(1))
    for op in (K.SIN, K.TAN, K.CSC, K.COT, K.ASIN, K.ATAN, K.SINH, K.TANH):
        assert K.fn_(op, omx) == K.neg_(K.fn_(op, xm1))
        assert K.fn_(op, K.neg_(x)) == K.neg_(K.fn_(op, x))
    for op in (K.COS, K.SEC, K.COSH):
        assert K.fn_(op, omx) == K.fn_(op, xm1)
        assert K.fn_(op, prod(q(-2), x)) == K.fn_(op, prod(q(2), x))
    for op in (K.LN, K.ACOS, K.FLOOR):
        assert K.N[K.fn_(op, omx)] == (op, omx)
    assert K.fn_(K.ABS, sm(K.neg_(x), q(-1))) == K.fn_(K.ABS, sm(x, q(1)))


def test_inverse_cancellation_only_one_way():
    x = K.sym('x')
    for f, g in ((K.SIN, K.ASIN), (K.COS, K.ACOS), (K.TAN, K.ATAN)):
        assert K.fn_(f, K.fn_(g, x)) == x
        assert K.N[K.fn_(g, K.fn_(f, x))][0] == g                  # asin(sin x) is kept
    assert K.fn_(K.SIN, K.fn_(K.ASIN, K.neg_(x))) == K.neg_(x)


def test_hyperbolic_at_zero_and_float_arguments():
    assert K.fn_(K.SINH, K.ZERO) == K.ZERO and K.fn_(K.TANH, K.ZERO) == K.ZERO
    assert K.fn_(K.COSH, K.ZERO) == K.ONE
    h = K.flt(0.5)
    assert K.N[K.fn_(K.SIN, h)] == (K.SIN, h)
    assert K.fn_(K.SIN, K.flt(-0.5)) == K.neg_(K.fn_(K.SIN, h))


# -- ln (6.4) ------------------------------------------------------------------------------------

def test_ln_rules():
    x = K.sym('x')
    ln = lambda u: K.fn_(K.LN, u)                       # noqa: E731
    l2 = K.mk((K.LN, K.TWO))
    assert ln(K.ONE) == K.ZERO and ln(K.E) == K.ONE
    with pytest.raises(K.Undefined):
        ln(K.ZERO)
    assert ln(pwe(K.E, x)) == x and ln(pwe(K.E, q(2))) == q(2)
    assert ln(q(8)) == prod(q(3), l2) and ln(q(100)) == prod(q(2), K.LN10)
    assert ln(q(10)) == K.LN10 and ln(q(36)) == prod(q(2), ln(q(6)))
    assert K.N[ln(q(12))] == (K.LN, q(12))
    assert ln(q(1, 2)) == K.neg_(l2) and ln(q(8, 9)) == sub(prod(q(3), l2), prod(q(2), ln(q(3))))
    assert ln(q(-1)) == prod(K.I, K.PI) and ln(q(-2)) == sm(l2, prod(K.I, K.PI))
    assert ln(K.I) == prod(q(0, 2, 1), K.PI) and ln(q(0, 1, -3)) == sm(ln(q(3)),
                                                                        prod(q(0, 2, -1), K.PI))
    assert ln(q(1, 1, 1)) == sm(div(l2, q(2)), prod(q(0, 4, 1), K.PI))
    assert ln(q(-1, 1, -1)) == sm(div(l2, q(2)), prod(q(0, 4, -3), K.PI))
    for z in ((3, 4, 1), (-3, 4, 1), (-3, -4, 1), (3, -4, 5), (1, 2, 7), (-5, 12, 2)):
        e = ln(K.num(z[0], z[1], z[2]))
        assert close(ev(e), cmath.log(complex(z[0], z[1]) / z[2]), 1e-12), z
        assert not any(K.N[i][0] == K.LN and K.N[K.N[i][1]][0] == K.NUM and K.N[K.N[i][1]][2]
                       for i in range(K.BASE, K.NN) if K.N[i] is not None)
    assert K.N[ln(sqrt(q(2)))][0] == K.LN                        # radicals are kept


def test_exp_ln_round_trips():
    x = K.sym('x')
    assert pwe(K.E, K.fn_(K.LN, x)) == x
    assert K.fn_(K.LN, pwe(K.E, prod(q(3), x))) == prod(q(3), x)
    assert pwe(K.E, K.fn_(K.LN, q(5))) == q(5)
    assert pwe(K.E, prod(q(2), K.fn_(K.LN, q(3)))) == q(9)


# -- abs (6.4) -----------------------------------------------------------------------------------

def test_absn_rules():
    x, y = K.sym('x'), K.sym('y')
    ab = lambda u: K.fn_(K.ABS, u)                      # noqa: E731
    ax = K.mk((K.ABS, x))
    assert ab(q(-3, 4)) == q(3, 4) and ab(q(3, 4, 4)) == q(5, 4)
    assert ab(q(1, 1, 1)) == sqrt(q(2)) and ab(q(1, 2, 1)) == div(sqrt(q(2)), q(2))
    assert ab(q(2, 1, 3)) == sqrt(q(13))
    assert ab(K.flt(-2.5)) == K.flt(2.5) and ab(K.flt(3.0, 4.0)) == K.flt(5.0)
    assert ab(K.PI) == K.PI and ab(K.neg_(K.PI)) == K.PI and ab(sm(K.PI, q(1))) == sm(K.PI, q(1))
    assert ab(K.neg_(sqrt(q(2)))) == sqrt(q(2)) and ab(sub(q(-1), K.E)) == sm(q(1), K.E)
    assert ab(prod(q(-2), x)) == prod(q(2), ax)
    assert ab(sm(prod(q(2), x), q(2))) == prod(q(2), ab(sm(x, q(1))))
    assert ab(sm(prod(q(-2, 3), x), q(4, 9))) == prod(q(2, 9), ab(sub(prod(q(3), x), q(2))))
    assert ab(pw(x, 2)) == pw(x, 2) and ab(prod(q(-3), pw(x, 2), pw(y, 4))) == \
        prod(q(3), pw(x, 2), pw(y, 4))
    assert ab(ab(x)) == ax and ab(K.OO) == K.OO and ab(K.neg_(K.OO)) == K.OO
    assert ab(K.UNDEF) == K.UNDEF
    assert ab(K.neg_(K.fn_(K.SIN, x))) == K.mk((K.ABS, K.fn_(K.SIN, x)))
    assert K.N[ab(sub(q(1), K.PI))] == (K.ABS, sub(K.PI, q(1)))
    assert ab(prod(K.I, x)) == ax and ab(prod(q(0, 1, -3), x)) == prod(q(3), ax)
    assert ab(prod(q(3, 1, 4), x)) == prod(q(5), ax)                # rational moduli come out
    assert ab(prod(q(0, 1, 16), sqrt(q(2)))) == prod(q(16), sqrt(q(2)))
    w = prod(q(1, 1, 1), x)                                          # sqrt(2) stays inside
    assert K.N[ab(w)] == (K.ABS, w) and ab(prod(q(-1, 1, -1), x)) == ab(w)
    assert ab(prod(K.flt(-2.0), x)) == prod(K.flt(2.0), ax)
    assert ab(prod(K.flt(3.0, 4.0), x)) == prod(K.flt(5.0), ax)


# -- sign, floor, ceil, fact ---------------------------------------------------------------------

def test_sign_floor_ceil_fact_of_numbers():
    f = K.fn_
    x = K.sym('x')
    assert f(K.SIGN, q(-3)) == K.MONE and f(K.SIGN, K.ZERO) == K.ZERO and f(K.SIGN, K.PI) == K.ONE
    assert f(K.SIGN, sub(q(-1), sqrt(q(2)))) == K.MONE
    assert K.N[f(K.SIGN, x)][0] == K.SIGN and K.N[f(K.SIGN, sub(K.PI, q(3)))][0] == K.SIGN
    assert f(K.FLOOR, q(7, 2)) == q(3) and f(K.FLOOR, q(-7, 2)) == q(-4)
    assert f(K.CEIL, q(7, 2)) == q(4) and f(K.CEIL, q(-7, 2)) == q(-3) and f(K.CEIL, q(5)) == q(5)
    assert f(K.FACT, q(0)) == K.ONE and f(K.FACT, q(5)) == q(120)
    assert f(K.FACT, q(1000)) == q(math.factorial(1000))
    assert K.N[f(K.FACT, q(1001))][0] == K.FACT and K.N[f(K.FACT, q(1, 2))][0] == K.FACT
    with pytest.raises(K.Undefined):
        f(K.FACT, q(-1))


# -- infinity (6.3) ------------------------------------------------------------------------------

def test_functions_of_infinity():
    oo, ninf = K.OO, K.neg_(K.OO)
    f = K.fn_
    assert f(K.LN, oo) == oo and f(K.LN, ninf) == K.UNDEF
    assert f(K.ATAN, oo) == pimul(1, 2) and f(K.ATAN, ninf) == pimul(-1, 2)
    assert f(K.TANH, oo) == K.ONE and f(K.TANH, ninf) == K.MONE
    assert f(K.SIGN, oo) == K.ONE and f(K.SIGN, ninf) == K.MONE
    assert f(K.FLOOR, ninf) == ninf and f(K.CEIL, oo) == oo
    assert f(K.SINH, ninf) == ninf and f(K.COSH, ninf) == oo and f(K.FACT, oo) == oo
    for op in (K.SIN, K.COS, K.TAN, K.SEC, K.CSC, K.COT, K.ASIN, K.ACOS):
        assert f(op, oo) == K.UNDEF and f(op, ninf) == K.UNDEF
    for op in (K.SIN, K.LN, K.ABS, K.SINH):
        assert f(op, K.UNDEF) == K.UNDEF
