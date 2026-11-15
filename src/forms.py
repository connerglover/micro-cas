#@L 2
# F5 (forms) transforms an inert original answer; the runner commits the resulting text.
import node as K
import alg as A
import parse as P
import printer as PR
import run as R

ORDER = ('simplified', 'one fraction', 'factored', 'expanded', 'decimal')


def g_form(code, ctx):                                          #@L 2
    e = R.HIST[R.FORMINDEX]
    f = yield P.g_eval(code, ctx)
    original = e[5][0][1] if e[5] else e[1]
    R.FORMNAME = 'exact'
    if e[2] != R.R_ANS or 'integrate(' in original or 'sum(' in original or 'limit(' in original:
        yield f
        return
    order = ('decimal',) + ORDER[:-1] if e[3] is not None and not K.V[f] else ORDER
    cache = e[5] or [('exact', original)]
    current = 'exact'
    seen = []
    for name, text in cache:
        if text == e[1]:
            current = name
        seen.append(sorted(text))
    start = order.index(current) + 1 if current in order else 0
    for name in order[start:]:
        mark = K.NN
        candidate = None
        if name == 'simplified':
            candidate = yield R.MODS['norm'].g_simplify([f], ctx)
        elif name == 'one fraction':
            candidate = yield R.MODS['norm'].g_together([f], ctx)
        elif name == 'factored':
            candidate = yield R.MODS['fact'].g_factor([f], ctx)
        elif name == 'expanded':
            candidate = yield R.MODS['norm'].g_expand([f], ctx)
        elif A.size(f) <= 40 and not K.V[f]:
            candidate = P.approx(f)
        if candidate is not None:
            text = PR.text(candidate, ctx)
            if text and sorted(text) not in seen and (name != 'simplified' or len(text) < len(original)):
                R.FORMNAME = name
                yield K.keep(mark, candidate)
                return
        K.keep(mark, None)
    yield f


PR12 = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41)    # 13 bases: a proof below 3.3e24


def isprime(n):                                                 #@L 5
    # Miller-Rabin with the first 13 primes as bases (12 pass 318665857834031151167461): a
    # proof below 3317044064679887385961981, so n of 2^81 or more is not claimed (False).
    # No 3-argument pow: MicroPython 1.12 may lack it.
    if n < 2 or n >> 81:
        return False
    for a in PR12:
        if n % a == 0:
            return n == a
    d = n - 1
    s = 0
    while not d & 1:
        d >>= 1
        s += 1
    for a in PR12:
        y = 1
        e = d
        while e:
            if e & 1:
                y = y * a % n
            a = a * a % n
            e >>= 1
        r = 1
        while r < s and y != 1 and y != n - 1:
            y = y * y % n
            r += 1
        if y != n - 1 and (r > 1 or y != 1):
            return False
    return True
