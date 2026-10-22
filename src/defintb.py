#@L 2
# Definite integration helper family.
import math
import node as K
import alg as A
import run as R

# Positive and negative abscissae, with weights, on [-1,1].
G6 = ((-.9324695142031521,.1713244923791704),(-.6612093864662645,.3607615730481386),(-.2386191860831969,.4679139345726910),(.2386191860831969,.4679139345726910),(.6612093864662645,.3607615730481386),(.9324695142031521,.1713244923791704)) #@float-ok
G10 = ((-.9739065285171717,.0666713443086881),(-.8650633666889845,.1494513491505806),(-.6794095682990244,.2190863625159820),(-.4333953941292472,.2692667193099963),(-.1488743389816312,.2955242247147529),(.1488743389816312,.2955242247147529),(.4333953941292472,.2692667193099963),(.6794095682990244,.2190863625159820),(.8650633666889845,.1494513491505806),(.9739065285171717,.0666713443086881)) #@float-ok

def number(e):                                                #@L 3
    if e == K.OO:
        return float('inf')
    if K.isninf(e):
        return -float('inf')
    if K.V[e]:
        return None
    try:
        v = A.nrun(A.nprog(e, ()), ())
        if type(v) is complex:
            return v.real if not v.imag else None
        return v
    except K.CasSoft:
        return None



def sample(program, z, dz, a, b, mode):                        #@L 3
    if mode == 0:
        x = (a + b) * 0.5 + (b - a) * 0.5 * z
        jac = (b - a) * 0.5
        if x <= a or x >= b:
            return 0.0
    elif mode == 1:
        x, jac = a + (1 + z) / (1 - z), 2 / (1 - z) ** 2
    elif mode == 2:
        x, jac = b - (1 - z) / (1 + z), 2 / (1 + z) ** 2
    else:
        x, jac = z / (1 - z*z), (1 + z*z) / (1 - z*z) ** 2
    try:
        value = A.nrun(program, (x,))
        if A.LEFTREAL[0]:
            return None
        if type(value) is complex:
            if abs(value.imag) > 1e-12:
                return None
            value = value.real
        result = value * jac * dz
        return result if -1e300 < result < 1e300 else None
    except K.CasSoft:
        return None



def g_quad(f, x, a, b, budget=R.MODS['def'].MAXEVAL):                        #@L 2
    lo, hi = number(a), number(b)
    if lo is None or hi is None:
        yield None
        return
    direction = 1
    if lo > hi:
        lo, hi, direction = hi, lo, -1
    if lo == hi:
        yield K.ZERO
        return
    mode = (2 if lo == -float('inf') else 0) + (1 if hi == float('inf') else 0)
    try:
        program = A.nprog(f, (x,))
    except K.CasSoft:
        yield None
        return
    # Dyadic nodes share an integer grid; avoid float-key dict growth/fragmentation.
    grid = 1 << R.MODS['def'].MAXLEVEL
    # 64-slot rows: no single large list, which a fragmented heap may lack (FASTBOOT.md).
    cache = []
    for j in range((7 * grid) // 64 + 1):
        cache.append([None] * 64)
    count = 0
    largest = 0.0
    previous = None
    for level in range(R.MODS['def'].MAXLEVEL + 1):
        h = 0.5 ** level
        total = 0.0
        for j in range(-int(3.5 / h), int(3.5 / h) + 1):
            t = j * h
            slot = 7 * grid // 2 + j * (1 << (R.MODS['def'].MAXLEVEL - level))
            value = cache[slot >> 6][slot & 63]
            if value is None:
                if count >= budget:
                    yield None
                    return
                et = math.exp(t)
                u = math.pi * 0.25 * (et - 1 / et)
                q = math.exp(-2 * abs(u))
                z = (1 - q) / (1 + q)
                if u < 0:
                    z = -z
                if abs(z) >= 1.0:
                    value = 0.0
                else:
                    dz = math.pi * (et + 1 / et) * q / (1 + q) ** 2
                    value = sample(program, z, dz, lo, hi, mode)
                    count += 1
                    if count % 64 == 0:
                        yield R.TICK
                if value is None:
                    yield None
                    return
                cache[slot >> 6][slot & 63] = value
            total += value
            largest = max(largest, abs(value))
        current = total * h
        if previous is not None and level >= 2 and abs(current - previous) <= R.MODS['def'].QTOL * (1 + abs(current)):
            if largest < 1e-14:
                yield None             # no sampled evidence: a narrow peak may be missed
                return
            yield K.flt(direction * current)
            return
        previous = current
        yield R.TICK
    yield None


def g_double(inner, x, a, b):                                  #@L 2
    t = K.N[inner]
    if t[0] != K.CALL or len(t) != 6 or K.N[t[1]] != (K.SYM, 'integrate'):
        yield None
        return
    f, y, c, d = t[2:]
    lo, hi = number(a), number(b)
    if K.N[y][0] != K.SYM or x == y or lo is None or hi is None or not -1e200 < lo < 1e200 or not -1e200 < hi < 1e200:
        yield None
        return
    try:
        program, lower, upper = A.nprog(f, (x, y)), A.nprog(c, (x,)), A.nprog(d, (x,))
        previous = None
        for rule in (G6, G10):
            total = 0.0
            for z, w in rule:
                xv = (lo + hi + (hi - lo) * z) * 0.5
                yl = A.nrun(lower, (xv,))
                if A.LEFTREAL[0] or type(yl) is complex or not -1e200 < yl < 1e200:
                    raise K.Undefined()
                yh = A.nrun(upper, (xv,))
                if A.LEFTREAL[0] or type(yh) is complex or not -1e200 < yh < 1e200:
                    raise K.Undefined()
                half = (yh - yl) * 0.5
                if half == 0.0:
                    continue
                for v, weight in rule:
                    value = A.nrun(program, (xv, (yl + yh) * 0.5 + half * v))
                    if A.LEFTREAL[0] or type(value) is complex or not -1e300 < value < 1e300:
                        raise K.Undefined()
                    total += w * weight * value * half * (hi - lo) * 0.5
                yield R.TICK
            if previous is not None and abs(total - previous) <= R.MODS['def'].QTOL * (1 + abs(total)) and max(abs(previous), abs(total)) > 1e-14:
                yield K.flt(total)
                return
            previous = total
    except K.CasSoft:
        pass
    yield None
