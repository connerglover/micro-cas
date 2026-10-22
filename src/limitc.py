#@L 2
# limit family: limitc helpers.
import node as K
import run as R

def g_growth(f, x, a, side):                                   #@L 2
    if a != K.OO and not K.isninf(a):
        yield None
        return
    t = K.N[f]
    if t[0] != K.MUL:
        yield None
        return
    exponent = []
    power = K.ZERO
    logs = K.ZERO
    coeff = t[1]
    valid = True
    for j in range(2, len(t), 2):
        b, p = t[j], t[j + 1]
        bt = K.N[b]
        if K.free_of(b, x) and not K.free_of(p, x) and R.MODS['limb'].signval(b) == 1:
            exponent.append(K.mul_(K.ONE, [(p, K.ONE), (K.fn_(K.LN, b), K.ONE)]))
        elif K.free_of(p, x):
            if bt[0] == K.LN:
                u = yield R.MODS['limb'].g_fast(bt[1], x, a, side)
                if u == K.OO:
                    lead = yield R.MODS['limb'].g_lead(bt[1], x, a, side)
                    if lead is None or lead[0] >= 0:
                        valid = False
                    else:
                        logs = K.add_([logs, p])
                        coeff = K.mul_(K.ONE, [(coeff, K.ONE), (K.num(-lead[0]), p)])
                else:
                    valid = False
            else:
                lead = yield R.MODS['limb'].g_lead(b, x, a, side)
                if lead is None:
                    valid = False
                else:
                    power = K.add_([power, K.mul_(K.num(-lead[0]), [(p, K.ONE)])])
                    coeff = K.mul_(K.ONE, [(coeff, K.ONE), (lead[1], p)])
        else:
            valid = False
    r = None
    if valid:
        ex = K.add_(exponent)
        u = yield R.MODS['limb'].g_fast(ex, x, a, side)
        if u == K.OO or (u is not None and K.isninf(u)):
            # Compare the entire logarithm; an exponential of sqrt(log(x))
            # need not dominate a power of x.
            lx = K.fn_(K.LN, K.neg_(x) if K.isninf(a) else x)
            combined = R.MODS['norm'].normal(K.add_([ex, K.mul_(K.ONE, [(power, K.ONE), (lx, K.ONE)]),
                         K.mul_(K.ONE, [(logs, K.ONE), (K.fn_(K.LN, lx), K.ONE)])]))
            v = yield R.MODS['limb'].g_fast(combined, x, a, side)
            if v is None:
                scale = lx if power != K.ZERO else K.fn_(K.LN, lx)
                relative = R.MODS['norm'].normal(K.mul_(K.ONE, [(combined, K.ONE), (scale, K.MONE)]))
                q = yield R.MODS['limb'].g_fast(relative, x, a, side)
                s = R.MODS['limb'].signval(q) if q is not None else None
                if s:
                    v = K.OO if s > 0 else K.neg_(K.OO)
                else:
                    lead = yield R.MODS['limb'].g_lead(ex, x, a, side)
                    if lead is not None and lead[0] < 0:
                        v = u
            if v is not None:
                r = K.mul_(K.ONE, [(coeff, K.ONE), (K.E, v)])
        elif u is not None:
            s = R.MODS['limb'].signval(power)
            if s == 0:
                s = R.MODS['limb'].signval(logs)
            if s == -1:
                r = K.ZERO
            elif s == 1:
                r = K.OO if R.MODS['limb'].signval(coeff) == 1 else K.neg_(K.OO) if R.MODS['limb'].signval(coeff) == -1 else None
            elif s == 0:
                r = K.mul_(K.ONE, [(coeff, K.ONE), (K.E, u)])
    yield r



def g_osc(f, x, a, side):                                      #@L 2
    t = K.N[f]
    pairs = [(f, K.ONE)] if t[0] != K.MUL else []
    if t[0] == K.MUL:
        for j in range(2, len(t), 2):
            pairs.append((t[j], t[j + 1]))
    rest = []
    oscillates = False
    for b, p in pairs:
        bt, pt = K.N[b], K.N[p]
        if bt[0] in (K.SIN, K.COS) and pt[0] == K.NUM and not pt[2] and pt[3] == 1 and pt[1] > 0:
            u = yield R.MODS['limb'].g_fast(bt[1], x, a, side)
            if u == K.OO or (u is not None and K.isninf(u)):
                oscillates = True
                continue
        rest.append((b, p))
    r = None
    if oscillates:
        envelope = K.mul_(t[1] if t[0] == K.MUL else K.ONE, rest)
        v = yield R.MODS['limb'].g_fast(envelope, x, a, side)
        if v == K.ZERO:
            r = K.ZERO
        elif v is not None:
            r = K.mk((K.DNE, K.UNDEF, K.UNDEF))
    yield r



def g_ratio(f, x, a, side):                                    #@L 2
    t = K.N[f]
    if t[0] != K.MUL:
        yield None
        return
    top, bottom = [], []
    for j in range(2, len(t), 2):
        b, p = t[j], t[j + 1]
        pt = K.N[p]
        if pt[0] == K.NUM and not pt[2] and pt[1] < 0:
            bottom.append((b, K.neg_(p)))
        else:
            top.append((b, p))
    if not bottom:
        kept = []
        for b, p in top:
            q = K.mul_(K.ONE, [(b, p)])
            u = yield R.MODS['limb'].g_fast(q, x, a, side)
            if u == K.ZERO:
                bottom.append((b, K.neg_(p)))
            else:
                kept.append((b, p))
        top = kept
    if not bottom:
        yield None
        return
    num, den = K.mul_(t[1], top), K.mul_(K.ONE, bottom)
    r = None
    for j in range(R.MODS['lim'].MAXLH):
        u = yield R.MODS['limb'].g_fast(num, x, a, side)
        v = yield R.MODS['limb'].g_fast(den, x, a, side)
        if u is None or v is None:
            break
        infu, infv = u == K.OO or K.isninf(u), v == K.OO or K.isninf(v)
        if not (u == K.ZERO and v == K.ZERO or infu and infv):
            break
        num = yield R.MODS['diff'].g_deriv(num, x)
        den = yield R.MODS['diff'].g_deriv(den, x)
        if den == K.ZERO:
            break
        quotient = R.MODS['norm'].normal(K.mul_(K.ONE, [(num, K.ONE), (den, K.MONE)]))
        r = yield R.MODS['limb'].g_fast(quotient, x, a, side)
        if r is not None:
            break
    yield r
