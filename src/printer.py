# printer.py (CVPRINT, alias PR): the 1D printer, display order, decimal formatter, messages.
# DESIGN.md section 12. T1.4 wrote the decimal formatter (dec10, fdec10, section 12.6);
# T1.7 adds text, items, the order keys and record.
import math

# dec10 refuses integers of 2^DECBITS or more (over about 4,000 decimal digits): str() of a big
# int is quadratic and cannot be cancelled (section 6.1). Such a number's text is over MAXTEXT
# anyway, so the answer is Done and no decimal line is lost.
DECBITS = 13287


def dec10(p, q, nd=10):                                         #@L 7
    # p/q (int p, int q > 0) -> nd significant digits, rounded half-up (ties away from zero),
    # integers only. Scientific 'd.ddE-5' / 'dE10' when the rounded value has |x| >= 1e10 or
    # |x| < 1e-4; otherwise fixed. No trailing zeros, no '+'. OverflowError over DECBITS.
    if p == 0:
        return '0'
    s = ''
    if p < 0:
        s = '-'
        p = -p
    if p >> DECBITS or q >> DECBITS:
        raise OverflowError('dec10')
    e = len(str(p)) - len(str(q))          # 10^e <= p/q < 10^(e+1), or e is one too big
    if e >= 0:
        if p < q * 10 ** e:
            e -= 1
    elif p * 10 ** (-e) < q:
        e -= 1
    k = nd - 1 - e                          # m = p/q * 10^k has nd digits before rounding
    if k >= 0:
        m, r = divmod(p * 10 ** k, q)
        den = q
    else:
        den = q * 10 ** (-k)
        m, r = divmod(p, den)
    if 2 * r >= den:                        # half-up
        m += 1
        if m == 10 ** nd:                   # carry into a new decade: 9.99..95 -> 10
            m //= 10
            e += 1
    dg = str(m)
    j = len(dg)
    while j > 1 and dg[j - 1] == '0':
        j -= 1
    dg = dg[:j]
    if e >= 10 or e < -4:                   # scientific: d.ddddE+-n
        t = dg[0]
        if len(dg) > 1:
            t = t + '.' + dg[1:]
        return s + t + 'E' + str(e)
    if e < 0:
        return s + '0.' + '0' * (-e - 1) + dg
    if len(dg) <= e + 1:
        return s + dg + '0' * (e + 1 - len(dg))
    return s + dg[:e + 1] + '.' + dg[e + 1:]


def fdec10(x, nd=10):                                           #@L 6
    # float x -> dec10 of its exact binary value (math.frexp is native: no frame). The digits
    # are the same on the device and the desktop by construction. inf raises OverflowError and
    # nan ValueError (int() of them); nrun has already rejected both (section 6.6).
    if x == 0.0:
        return '0'
    m, ex = math.frexp(x)                   # x = m * 2**ex, 0.5 <= |m| < 1
    p = int(m * 9007199254740992.0)         # m * 2**53: exact
    ex -= 53
    if ex >= 0:
        return dec10(p * 2 ** ex, 1, nd)
    return dec10(p, 2 ** (-ex), nd)
