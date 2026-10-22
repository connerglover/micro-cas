#@L 2
# CVINT2: exact partial fractions, tabular integration and trig-power reductions.
import node as K
import alg as A
import parse as P
import run as R

MAXDEG = 12


def expr(p, den, x):                                            #@L 4
    terms = []
    for j in range(len(p)):
        if p[j]:
            terms.append(K.mul_(K.nnorm(p[j], 0, den), [(x, K.num(j))]))
    return K.add_(terms)



def dense(e, x, cap=24):                                        #@L 4
    pc = A.pco(e, x, cap)
    if pc is None:
        return None
    nums = []
    den = 1
    for terms in pc:
        out = []
        for u, c in terms:
            out.append(K.mul_(c, [(u, K.ONE)]))
        t = K.N[K.add_(out)]
        if t[0] != K.NUM or t[2]:
            return None
        nums.append(t)
        g, h = den, t[3]
        while h:
            g, h = h, g % h
        den = den * t[3] // g
    p = []
    for t in nums:
        p.append(t[1] * (den // t[3]))
    while p and not p[-1]:
        p.pop()
    return p, den



def template(s, x, a=0, b=0, c=0, u=0, v=0, w=0):               #@L 3
    env = [u, v, w, a, b, c] + [0] * (P.NSLOT - 6)
    env[P.XSLOT] = x
    return P.inst(P.tcode(s), env)



def g_tabular(f, x, depth=0):                                   #@L 2
    t = K.N[f]
    pairs = t[2:] if t[0] == K.MUL else (f, K.ONE)
    coef = t[1] if t[0] == K.MUL else K.ONE
    poly = []
    exponential = K.ONE
    a = K.ZERO
    angle = None
    b = K.ZERO
    sine = K.ZERO
    cosine = K.ONE
    for j in range(0, len(pairs), 2):
        base, power = pairs[j], pairs[j + 1]
        t = K.N[base]
        linear = A.linear(power, x) if base == K.E else None
        if linear is not None:
            a = linear[0]
            exponential = K.mul_(K.ONE, [(base, power)])
        elif t[0] in (K.SIN, K.COS) and power == K.ONE and angle is None:
            linear = A.linear(t[1], x)
            if linear is None:
                yield None
                return
            angle, b = t[1], linear[0]
            sine = K.ONE if t[0] == K.SIN else K.ZERO
            cosine = K.ONE if t[0] == K.COS else K.ZERO
        else:
            poly.append((base, power))
    polynomial = K.mul_(coef, poly)
    degree = A.degree(polynomial, x)
    if degree < 0 or degree > MAXDEG or a == K.ZERO and angle is None:
        yield None
        return
    denom = K.add_([K.mul_(K.ONE, [(a, K.num(2))]), K.mul_(K.ONE, [(b, K.num(2))])])
    out = []
    sign = K.ONE
    for j in range(degree + 1):
        sn = template('(A*U+B*V)/W', x, a, b, u=sine, v=cosine, w=denom)
        cn = template('(A*V-B*U)/W', x, a, b, u=sine, v=cosine, w=denom)
        sine, cosine = sn, cn
        trig = cosine if angle is None else template('U*sin(V)+W*cos(V)', x, u=sine, v=angle, w=cosine)
        out.append(K.mul_(sign, [(polynomial, K.ONE), (exponential, K.ONE), (trig, K.ONE)]))
        polynomial = yield R.MODS['diff'].g_deriv(polynomial, x)
        sign = K.neg_(sign)
    yield (K.add_(out), K.ZERO)



def g_trig(f, x, depth=0):                                      #@L 2
    t = K.N[f]
    pairs = t[2:] if t[0] == K.MUL else (f, K.ONE)
    coef = t[1] if t[0] == K.MUL else K.ONE
    angle = None
    counts = [0, 0]
    valid = True
    for j in range(0, len(pairs), 2):
        base = K.N[pairs[j]]
        p = K.N[pairs[j + 1]]
        if base[0] not in (K.SIN, K.COS) or p[0] != K.NUM or p[2] or p[3] != 1 or not 0 <= p[1] <= 20:
            valid = False
            break
        if angle is not None and angle != base[1]:
            valid = False
            break
        angle = base[1]
        counts[0 if base[0] == K.SIN else 1] += p[1]
    lin = A.linear(angle, x) if angle is not None else None
    if valid and lin is not None and sum(counts) <= 20:
        m, n = counts
        PO = R.MODS['poly']
        coeffs = PO.pmul(PO.ppow([-1, 0, 1], m), PO.ppow([1, 0, 1], n))
        out = []
        for j in range(m + n, len(coeffs)):
            k = j - m - n
            c = coeffs[j] * (-1 if (m // 2) & 1 else 1)
            if not c:
                continue
            if not k:
                out.append(K.mul_(K.nnorm(c, 0, 2 ** (m + n)), [(x, K.ONE)]))
            else:
                arg = K.mul_(K.num(k), [(angle, K.ONE)])
                fn = K.fn_(K.COS if m & 1 else K.SIN, arg)
                out.append(K.mul_(K.nnorm(-2 * c if m & 1 else 2 * c, 0, k * 2 ** (m + n)), [(lin[0], K.MONE), (fn, K.ONE)]))
        yield (K.mul_(coef, [(K.add_(out), K.ONE)]), K.ZERO)
        return
    if len(pairs) == 2 and K.N[pairs[0]][0] in (K.TAN, K.COT, K.SEC, K.CSC):
        base, p = K.N[pairs[0]], K.N[pairs[1]]
        lin = A.linear(base[1], x)
        if lin is not None and p[0] == K.NUM and not p[2] and p[3] == 1 and 2 <= p[1] <= 20:
            r = yield R.MODS['int'].g_table(pairs[0], x, depth)
            if r is not None:
                integrals = [x, r[0]]
                for n in range(2, p[1] + 1):
                    if base[0] in (K.TAN, K.COT):
                        s = ('1' if base[0] == K.TAN else '-1') + '*V^(W-1)/(A*(W-1))-U'
                    else:
                        name = 'tan' if base[0] == K.SEC else 'cot'
                        s = ('1' if base[0] == K.SEC else '-1') + '*V^(W-2)*' + name + '(B)/(A*(W-1))+(W-2)*U/(W-1)'
                    integrals.append(template(s, x, lin[0], base[1], u=integrals[n - 2], v=pairs[0], w=K.num(n)))
                yield (K.mul_(coef, [(integrals[-1], K.ONE)]), K.ZERO)
                return
    if depth < 3:
        expanded = yield R.MODS['rules'].g_rewrite(f, 'tlin', x, 48)
        if expanded is not None and expanded != f:
            expanded = R.MODS['norm'].normal(expanded, 1)
            r = yield R.MODS['int'].g_int(expanded, x, depth + 1)
            if r is not None and r[1] == K.ZERO:
                yield r
                return
    yield None



