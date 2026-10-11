#@L 2
# integ2 family: integ2b helpers.
import node as K
import alg as A
import parse as P
import run as R

def g_decompose(f, x):                                          #@L 2
    # Returns polynomial part and (numerator, irreducible base, exponent) terms.
    f = R.MODS['norm'].normal(f)
    t = K.N[f]
    coef = K.ONE
    pairs = (f, K.ONE)
    if t[0] == K.MUL:
        coef, pairs = t[1], t[2:]
    sides = ([], [])
    for j in range(0, len(pairs), 2):
        p = K.N[pairs[j + 1]]
        if p[0] != K.NUM or p[2] or p[3] != 1:
            yield None
            return
        sides[1 if p[1] < 0 else 0].append((pairs[j], K.num(abs(p[1]))))
    nn = R.MODS['int2'].dense(K.mul_(coef, sides[0]), x)
    dd = R.MODS['int2'].dense(K.mul_(K.ONE, sides[1]), x, R.MODS['int2'].MAXDEG)
    if nn is None or dd is None or not dd[0]:
        yield None
        return
    PO = R.MODS['poly']
    numerator = PO.padd([], nn[0], dd[1])
    denominator = PO.padd([], dd[0], nn[1])
    q, rem, m = PO.pdivrem(numerator, denominator)
    polynomial = R.MODS['int2'].expr(q, m, x)
    if not rem:
        yield (polynomial, [])
        return
    # Factoring is loaded by the generator before entering this plain helper.
    c, factors, complete = R.MODS['factb'].ufac(denominator)
    columns = []
    specs = []
    for base, count in factors:
        if len(base) > 3:
            yield None
            return
        b = R.MODS['int2'].expr(base, 1, x)
        for power in range(1, count + 1):
            quotient = PO.pdivex(denominator, PO.ppow(base, power))
            if quotient is None:
                yield None
                return
            for j in range(len(base) - 1):
                columns.append([0] * j + quotient)
            specs.append((b, power, len(base) - 1))
    nv = len(columns)
    matrix = []
    for i in range(nv):
        row = []
        for col in columns:
            row.append(col[i] if i < len(col) else 0)
        row.append(rem[i] if i < len(rem) else 0)
        matrix.append(row)
    solution = R.MODS['polyb'].gjsolve(matrix, nv)
    if solution is None or len(solution[0]) != nv:
        yield None
        return
    k = 0
    terms = []
    for base, power, degree in specs:
        cs = []
        for j in range(degree):
            row = solution[1][k]
            cs.append(K.mul_(K.nnorm(row[-1], 0, m * row[k]), [(x, K.num(j))]))
            k += 1
        u = K.add_(cs)
        if u != K.ZERO:
            terms.append((u, base, power))
    yield (polynomial, terms)



def g_partfrac(args, ctx):                                      #@L 2
    x = args[1] if len(args) > 1 else K.sym('x')
    if K.N[x][0] != K.SYM:
        raise K.CasError('invalid argument')
    ctx[P.X_MV] = x
    R.need('fact')
    parts = yield g_decompose(args[0], x)
    if parts is None:
        yield K.mk((K.CALL, K.sym('partfrac'), args[0], x))
        return
    out = [parts[0]]
    for u, base, power in parts[1]:
        out.append(K.mul_(K.ONE, [(u, K.ONE), (base, K.num(-power))]))
    result = K.add_(out)
    good = yield R.MODS['normb'].g_iszero(K.add_([result, K.neg_(args[0])]))
    yield args[0] if good == A.NO else result



def g_rational(f, x, depth=0):                                  #@L 2
    R.need('fact')
    parts = yield g_decompose(f, x)
    if parts is None:
        yield None
        return
    result = yield R.MODS['int'].g_int(parts[0], x, depth + 1)
    out = [result[0]]
    for u, base, power in parts[1]:
        lin = A.linear(base, x)
        if lin is not None:
            s = 'U*ln(abs(V))/A' if power == 1 else 'U*V^(1-W)/(A*(1-W))'
            out.append(R.MODS['int2'].template(s, x, lin[0], u=u, v=base, w=K.num(power)))
            continue
        a, b, c = A.quadratic(base, x)
        n1, n0 = A.linear(u, x)
        alpha = K.mul_(K.HALF, [(n1, K.ONE), (a, K.MONE)])
        beta = K.add_([n0, K.neg_(K.mul_(K.ONE, [(alpha, K.ONE), (b, K.ONE)]))])
        if alpha != K.ZERO:
            s = 'U*ln(abs(V))' if power == 1 else 'U*V^(1-W)/(1-W)'
            out.append(R.MODS['int2'].template(s, x, u=alpha, v=base, w=K.num(power)))
        if beta == K.ZERO:
            continue
        reciprocal = K.mul_(K.ONE, [(base, K.MONE)])
        r = yield R.MODS['int'].g_table(reciprocal, x, depth)
        if r is None:
            yield None
            return
        primitive = r[0]
        for n in range(2, power + 1):
            primitive = R.MODS['int2'].template('(2*A*x+B)/((W-1)*(4*A*C-B^2)*V^(W-1))+2*A*(2*W-3)*U/((W-1)*(4*A*C-B^2))', x, a, b, c, primitive, base, K.num(n))
        out.append(K.mul_(K.ONE, [(beta, K.ONE), (primitive, K.ONE)]))
        yield R.TICK
    yield (K.add_(out), K.ZERO)
