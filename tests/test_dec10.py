"""T1.4: the decimal formatter `PR.dec10` / `PR.fdec10` (DESIGN.md section 12.6).

The reference is CPython's `decimal` module: division and `plus` are correctly rounded under
the context, so `ROUND_HALF_UP` at precision `nd` gives the exact expected digits. The layout
rules (scientific when the *rounded* value has |x| >= 1e10 or |x| < 1e-4, no trailing zeros,
`E` with no `+`) are re-implemented independently in `ref_text`.
"""
import math
import random
import struct
from decimal import Decimal, localcontext, ROUND_HALF_UP, MAX_EMAX, MIN_EMIN

import pytest

import printer as PR


# -- the reference ----------------------------------------------------------------------------

def _round(v, nd):
    """Decimal v rounded half-up (away from zero on ties) to nd significant digits."""
    with localcontext() as c:
        c.prec = nd
        c.rounding = ROUND_HALF_UP
        c.Emax = MAX_EMAX
        c.Emin = MIN_EMIN
        return c.plus(v)


def _div(p, q, nd):
    with localcontext() as c:
        c.prec = nd
        c.rounding = ROUND_HALF_UP
        c.Emax = MAX_EMAX
        c.Emin = MIN_EMIN
        return Decimal(p) / Decimal(q)     # Decimal(int) is exact; division correctly rounded


def ref_text(v):
    """The section 12.6 layout of a Decimal that is already rounded."""
    if v == 0:
        return '0'
    sign, digits, _ = v.as_tuple()
    dg = ''.join(str(d) for d in digits).rstrip('0')
    e = v.adjusted()                        # exponent of the leading digit
    s = '-' if sign else ''
    if e >= 10 or e < -4:
        return s + dg[0] + ('.' + dg[1:] if len(dg) > 1 else '') + 'E' + str(e)
    if e < 0:
        return s + '0.' + '0' * (-e - 1) + dg
    if len(dg) <= e + 1:
        return s + dg + '0' * (e + 1 - len(dg))
    return s + dg[:e + 1] + '.' + dg[e + 1:]


def ref_dec(p, q, nd=10):
    return ref_text(_div(p, q, nd))


def ref_fdec(x, nd=10):
    return ref_text(_round(Decimal(x), nd))     # Decimal(float) is the exact binary value


# -- random cases -----------------------------------------------------------------------------

def _rand_int(rng, lo_digits, hi_digits):
    n = rng.randint(lo_digits, hi_digits)
    return rng.randint(10 ** (n - 1) if n > 1 else 1, 10 ** n - 1)


def rand_rational(rng):
    """A signed rational p/q with q > 0, spread over magnitudes, near-ties and exact ties."""
    kind = rng.random()
    if kind < 0.45:                                  # general: 1..40 digits each
        p = _rand_int(rng, 1, 40)
        q = _rand_int(rng, 1, 40)
    elif kind < 0.65:                                # magnitudes near the thresholds
        q = _rand_int(rng, 1, 25)
        e = rng.choice((-6, -5, -4, -3, 8, 9, 10, 11, rng.randint(-12, 14)))
        p = q * 10 ** e if e >= 0 else q
        if e < 0:
            q = q * 10 ** (-e)
        p = p * rng.randint(1, 10 ** 12) // 10 ** 11 + rng.randint(-3, 3)
        if p <= 0:
            p = 1
    elif kind < 0.85:                                # an exact tie at digit nd + 1 = 11
        m = _rand_int(rng, 10, 10) * 10 + 5          # 11 significant digits ending in 5
        j = rng.randint(-20, 20)
        if j >= 0:
            p, q = m * 10 ** j, 1
        else:
            p, q = m, 10 ** (-j)
        if rng.random() < 0.5:                       # same value, non-reduced or scaled q
            k = rng.randint(2, 999)
            p, q = p * k, q * k
        if rng.random() < 0.3:                       # just above or below the tie
            p, q = p * 10 ** 6 + rng.choice((-1, 1)), q * 10 ** 6
    else:                                            # values that round up to a power of 10
        n = rng.randint(1, 15)
        j = rng.randint(-25, 25)
        m = 10 ** (10 + n) - rng.randint(1, 10 ** n) # 9999999999xxx..: rounds to 10^k or not
        if j >= 0:
            p, q = m * 10 ** j, 1
        else:
            p, q = m, 10 ** (-j)
    if rng.random() < 0.5:
        p = -p
    return p, q


def rand_float(rng):
    """Any finite double: random bit patterns (normals and subnormals), plus decimal-ish ones."""
    if rng.random() < 0.7:
        while True:
            x = struct.unpack('<d', struct.pack('<Q', rng.getrandbits(64)))[0]
            if not (math.isinf(x) or math.isnan(x)):
                return x
    e = rng.randint(-12, 14)
    return rng.choice((-1, 1)) * rng.randint(1, 10 ** 12) * 10.0 ** (e - 12)


# -- spec examples and thresholds -------------------------------------------------------------

SPEC = [                                   # DESIGN.md 12.6 examples [M]
    (1, 3, '0.3333333333'),
    (22, 7, '3.142857143'),
    (1, 100000, '1E-5'),
    (99999999995, 10, '1E10'),             # 9999999999.5
]

THRESHOLDS = [
    (0, 1, '0'),
    (0, 7, '0'),
    (1, 1, '1'),
    (-1, 1, '-1'),
    (10 ** 10 - 1, 1, '9999999999'),
    (10 ** 10, 1, '1E10'),
    (-10 ** 10, 1, '-1E10'),
    (10 ** 10 + 1, 1, '1E10'),
    (10 ** 10 + 5, 1, '1.000000001E10'),   # 10000000005: a tie, half-up
    (10 ** 10 + 4, 1, '1E10'),
    (99999999994, 10, '9999999999'),       # 9999999999.4
    (-99999999995, 10, '-1E10'),           # ties go away from zero
    (123456789012, 1, '1.23456789E11'),
    (1, 10 ** 4, '0.0001'),
    (-1, 10 ** 4, '-0.0001'),
    (1, 10 ** 4 + 1, '9.9990001E-5'),
    (99999999995, 10 ** 15, '0.0001'),     # 9.9999999995E-5 rounds up to 1E-4: fixed
    (99999999994, 10 ** 15, '9.999999999E-5'),
    (12345, 10 ** 8, '0.00012345'),
    (1, 2, '0.5'),
    (5, 2, '2.5'),
    (-5, 2, '-2.5'),
    (2, 3, '0.6666666667'),
    (-2, 3, '-0.6666666667'),
    (1000, 1, '1000'),
    (123456789, 1, '123456789'),
    (1234567891, 1, '1234567891'),
    (12345678915, 10, '1234567892'),       # 1234567891.5: half-up at the units digit
    (12345678914, 10, '1234567891'),
    (314159265358979, 10 ** 14, '3.141592654'),
    (10 ** 30, 3, '3.333333333E29'),
    (1, 3 * 10 ** 30, '3.333333333E-31'),
    (7, 10 ** 400, '7E-400'),
    (10 ** 400, 7, '1.428571429E399'),
]


@pytest.mark.parametrize('p, q, want', SPEC + THRESHOLDS)
def test_dec10_cases(p, q, want):
    assert PR.dec10(p, q) == want
    assert ref_dec(p, q) == want            # the reference agrees with the hand-written text


@pytest.mark.parametrize('x, want', [
    (math.pi, '3.141592654'),
    (0.1 + 0.2, '0.3'),
    (0.1, '0.1'),
    (1e-5, '1E-5'),
    (1e10, '1E10'),
    (9999999999.0, '9999999999'),
    (9999999999.5, '1E10'),
    (9999999999.4, '9999999999'),
    (1e-4, '0.0001'),
    (0.5, '0.5'),
    (-2.5, '-2.5'),
    (1.0 / 3.0, '0.3333333333'),
    (2.0 / 3.0, '0.6666666667'),
    (0.0, '0'),
    (-0.0, '0'),
    (5e-324, '4.940656458E-324'),           # the smallest subnormal
    (1.7976931348623157e308, '1.797693135E308'),
    (123456.789, '123456.789'),
    (-0.000123, '-0.000123'),
])
def test_fdec10_cases(x, want):
    assert PR.fdec10(x) == want
    assert ref_fdec(x) == want


@pytest.mark.parametrize('x, nd, want', [   # the 15-digit form used for FLT text (12.1, 12.4)
    (0.1, 15, '0.1'),
    (0.1 + 0.2, 15, '0.3'),
    (1.0 / 3.0, 15, '0.333333333333333'),
    (2.5e-3, 15, '0.0025'),
    (1e-5, 15, '1E-5'),
    (123456789012.0, 15, '1.23456789012E11'),
    (math.pi, 15, '3.14159265358979'),
    (math.e, 15, '2.71828182845905'),
    (-1e100, 15, '-1E100'),
    (0.1 + 0.2, 17, '0.30000000000000004'),
    (math.pi, 1, '3'),
    (9.5, 1, '10'),                         # rounds up to 1E1; e = 1 < 10, so fixed
])
def test_fdec10_nd(x, nd, want):
    assert PR.fdec10(x, nd) == want
    assert ref_fdec(x, nd) == want


def test_rounding_carry_updates_exponent():
    # the carry m == 10^nd moves the value up a decade before the layout is chosen
    assert PR.dec10(9999999999999, 10 ** 3) == '1E10'      # 9999999999.999
    assert PR.dec10(99999999996, 10 ** 15) == '0.0001'      # 9.9999999996E-5
    assert PR.dec10(999995, 10 ** 6, 5) == '1'              # 0.999995 to 5 digits
    assert PR.dec10(999994, 10 ** 6, 5) == '0.99999'
    assert PR.dec10(95, 10, 1) == ref_dec(95, 10, 1) == '10'


def test_nd_range():
    rng = random.Random(1404)
    for _ in range(600):
        p, q = rand_rational(rng)
        nd = rng.randint(1, 30)
        assert PR.dec10(p, q, nd) == ref_dec(p, q, nd), (p, q, nd)
        x = rand_float(rng)
        assert PR.fdec10(x, nd) == ref_fdec(x, nd), (x.hex(), nd)


# -- the acceptance runs: exact against decimal on 20,000 random cases each --------------------

def test_dec10_random_20000():
    rng = random.Random(20000)
    bad = []
    for _ in range(20000):
        p, q = rand_rational(rng)
        got = PR.dec10(p, q)
        want = ref_dec(p, q)
        if got != want:
            bad.append((p, q, got, want))
    assert not bad, bad[:5]


def test_fdec10_random_20000():
    rng = random.Random(53)
    bad = []
    for _ in range(20000):
        x = rand_float(rng)
        for nd in (10, 15):
            got = PR.fdec10(x, nd)
            want = ref_fdec(x, nd)
            if got != want:
                bad.append((x.hex(), nd, got, want))
    assert not bad, bad[:5]


def test_fdec10_17_digits_round_trip():
    # 17 significant digits identify every double: the text parses back to the same float
    rng = random.Random(17)
    for _ in range(5000):
        x = rand_float(rng)
        s = PR.fdec10(x, 17)
        assert float(s) == x, (x.hex(), s)


def test_value_and_shape():
    # every output is a well-formed decimal whose value is p/q rounded to nd digits
    rng = random.Random(7)
    for _ in range(3000):
        p, q = rand_rational(rng)
        s = PR.dec10(p, q)
        assert Decimal(s) == _div(p, q, 10), (p, q, s)
        body = s.lstrip('-')
        assert body and body[0] in '0123456789'
        mant = body.split('E')[0]
        assert len(mant.replace('.', '').lstrip('0')) <= 10
        if '.' in mant:
            assert not mant.endswith('0') and not mant.endswith('.')
        if 'E' in body:
            e = int(body.split('E')[1])
            assert e >= 10 or e < -4
            assert mant[0] != '0' and (len(mant) == 1 or mant[1] == '.')
        else:
            v = abs(Decimal(s))
            assert v == 0 or Decimal('1E-4') <= v < Decimal('1E10')


def test_exact_large_rationals():
    # big p and q (hundreds to about 4,000 digits) stay exact
    rng = random.Random(4000)
    for nd in (10, 15):
        for _ in range(40):
            p = _rand_int(rng, 1, 3900) * rng.choice((-1, 1))
            q = _rand_int(rng, 1, 3900)
            assert PR.dec10(p, q, nd) == ref_dec(p, q, nd)
    p = 2 ** 13000 + 1
    assert PR.dec10(p, 3) == ref_dec(p, 3)
    assert PR.dec10(3, p) == ref_dec(3, p)
    assert PR.dec10(p, p + 2) == ref_dec(p, p + 2) == '1'


def test_huge_integers_refused():
    # section 6.1: the printer never str()s an integer of over about 4,000 digits; dec10
    # raises OverflowError instead, and PR.record turns any exception into "no decimal line"
    big = 1 << PR.DECBITS
    assert PR.dec10(big - 1, 1)                             # 4,000 digits: still formatted
    with pytest.raises(OverflowError):
        PR.dec10(big, 1)
    with pytest.raises(OverflowError):
        PR.dec10(-big, 3)
    with pytest.raises(OverflowError):
        PR.dec10(1, big)
    with pytest.raises(OverflowError):
        PR.dec10(10 ** 19000, 10 ** 19000 + 1)
    assert len(str(big - 1)) == 4000


def test_fdec10_non_finite_raises():
    # nrun rejects nan and inf before the decimal line (6.6); fdec10 itself refuses them
    for x in (float('inf'), float('-inf'), float('nan')):
        with pytest.raises((OverflowError, ValueError)):
            PR.fdec10(x)


def test_ints_accepted_by_fdec10():
    # fdec10 of an int-valued float, including above 2^53
    assert PR.fdec10(2.0 ** 60, 15) == ref_fdec(2.0 ** 60, 15) == '1.15292150460685E18'
    assert PR.fdec10(1e22, 10) == '1E22'
    assert PR.fdec10(12345678.0, 10) == '12345678'


# -- device depth -----------------------------------------------------------------------------

def test_depth(evodepth):
    # dec10 is an L7 leaf (no Python calls); fdec10 is L6 and calls only dec10
    r, depth, _ = evodepth.measure(PR.dec10, 22, 7)
    assert r == '3.142857143'
    assert depth == 7
    r, depth, _ = evodepth.measure(PR.fdec10, math.pi)
    assert r == '3.141592654'
    assert depth == 7
