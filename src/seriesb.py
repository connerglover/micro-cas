#@L 2
# series family: seriesb helpers.
import node as K
import alg as A
import run as R

def pack(v, cs):                                                #@L 7
    j = 0
    while j < len(cs) and cs[j] == K.ZERO:
        j += 1
    return tuple([v + j] + cs[j:])



def const(c, n):                                                #@L 6
    return pack(0, [c] + [K.ZERO] * n)



def dense(s, n):                                                #@L 7
    if s[0] < 0:
        return None
    return ([K.ZERO] * s[0] + list(s[1:]))[:n + 1]



def prod(a, b):                                                 #@L 4
    return K.mul_(K.ONE, [(a, K.ONE), (b, K.ONE)])



def sadd(a, b, n):                                              #@L 4
    v = min(a[0], b[0])
    end = min(a[0] + len(a) - 1, b[0] + len(b) - 1, v + n + 1)
    cs = []
    for k in range(v, end):
        x = a[k - a[0] + 1] if k >= a[0] else K.ZERO
        y = b[k - b[0] + 1] if k >= b[0] else K.ZERO
        cs.append(K.add_([x, y]))
    return pack(v, cs)



def smul(a, b, n):                                              #@L 3
    v = a[0] + b[0]
    size = min(len(a) - 1, len(b) - 1, n + 1)
    cs = []
    for k in range(size):
        ts = []
        for j in range(k + 1):
            if a[j + 1] != K.ZERO and b[k - j + 1] != K.ZERO:
                ts.append(prod(a[j + 1], b[k - j + 1]))
        cs.append(K.add_(ts))
    return pack(v, cs)



def spow(a, r, n):                                              #@L 3
    # Miller recurrence: b_j = sum(((r+1)k-j)*a_k*b_(j-k))/(j*a_0).
    if r == K.ZERO:
        return const(K.ONE, n)
    t = K.N[r]
    v = 0
    if a[0]:
        if t[0] != K.NUM or t[2] or a[0] * t[1] % t[3]:
            return None
        v = a[0] * t[1] // t[3]
    if len(a) == 1:
        return (v,) if t[0] == K.NUM and t[1] > 0 else None
    out = [K.mul_(K.ONE, [(a[1], r)])]
    for j in range(1, min(len(a) - 1, n + 1)):
        ts = []
        for k in range(1, j + 1):
            if a[k + 1] != K.ZERO and out[j - k] != K.ZERO:
                w = K.add_([prod(r, K.num(k)), K.num(k - j)])
                ts.append(K.mul_(K.ONE, [(w, K.ONE), (a[k + 1], K.ONE),
                                         (out[j - k], K.ONE)]))
        out.append(K.mul_(K.num(1, 0, j), [(K.add_(ts), K.ONE), (a[1], K.MONE)]))
    return pack(v, out)



def analytic(op, a, n):                                        #@L 3
    u = dense(a, n)
    if not u:
        return None
    if op == K.LN and u[0] == K.ZERO:
        return None
    if op == R.MODS['ser'].EXP:
        out = [K.mul_(K.ONE, [(K.E, u[0])])]
    elif op == K.LN:
        out = [K.fn_(K.LN, u[0])]
    else:
        out = [K.fn_(op, u[0])]
        other = [K.fn_(K.COSH if op == K.SINH else K.COS, u[0])]
    for j in range(1, len(u)):
        ts = []
        us = []
        if op == K.LN:
            ts.append(prod(K.num(j), u[j]))
        for k in range(1, j + 1):
            if op == K.LN:
                if k < j:
                    ts.append(K.mul_(K.num(-k), [(out[k], K.ONE), (u[j - k], K.ONE)]))
            elif u[k] != K.ZERO:
                ts.append(K.mul_(K.num(k), [(u[k], K.ONE),
                                           ((out if op == R.MODS['ser'].EXP else other)[j - k], K.ONE)]))
                if op != R.MODS['ser'].EXP:
                    us.append(K.mul_(K.num(k if op == K.SINH else -k),
                                     [(u[k], K.ONE), (out[j - k], K.ONE)]))
        z = K.add_(ts)
        out.append(K.mul_(K.num(1, 0, j), [(z, K.ONE)] +
                          ([(u[0], K.MONE)] if op == K.LN else [])))
        if op != R.MODS['ser'].EXP and op != K.LN:
            other.append(prod(K.num(1, 0, j), K.add_(us)))
    if op == R.MODS['ser'].EXP or op == K.LN:
        return pack(0, out)
    return pack(0, out), pack(0, other)



def g_fun(op, a, n):                                           #@L 2
    out = None
    if op == R.MODS['ser'].EXP or op == K.LN:
        out = analytic(op, a, n)
    elif K.SIN <= op <= K.COT or K.SINH <= op <= K.TANH:
        pair = analytic(K.SINH if op >= K.SINH else K.SIN, a, n)
        if pair is not None:
            s, c = pair
            if op == K.SIN or op == K.SINH:
                out = s
            elif op == K.COS or op == K.COSH:
                out = c
            else:
                den = s if op == K.CSC or op == K.COT else c
                inv = spow(den, K.MONE, n)
                if inv is not None:
                    num = c if op == K.COT else s
                    out = inv if op == K.SEC or op == K.CSC else smul(num, inv, n)
    elif op == K.ATAN or op == K.ASIN or op == K.ACOS:
        u = dense(a, n)
        if u:
            sq = smul(a, a, n)
            if op != K.ATAN:
                sq = smul(const(K.MONE, n), sq, n)
            den = sadd(const(K.ONE, n), sq, n)
            inv = spow(den, K.MONE if op == K.ATAN else K.num(-1, 0, 2), n)
            if inv is not None and inv[0] == 0:
                du = []
                for j in range(1, len(u)):
                    du.append(prod(K.num(-j if op == K.ACOS else j), u[j]))
                ds = smul(pack(0, du), inv, n)
                ds = dense(ds, n)
                if ds is not None:
                    cs = [K.fn_(op, u[0])]
                    for j in range(len(ds)):
                        cs.append(prod(K.num(1, 0, j + 1), ds[j]))
                    out = pack(0, cs)
    yield out
