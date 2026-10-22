#@L 2
# CVDIFF: iterative derivative fold, n-th derivatives, FTC and gradients (11.3).
import node as K
import alg as A
import parse as P
import run as R

# Templates take U in the same real/radian node algebra as the parser. Degree mode
# has already inserted pi/180 or 180/pi, so the ordinary chain rule suffices.
DT = {K.SIN: 'cos(U)', K.COS: '-sin(U)', K.TAN: 'sec(U)^2',
      K.SEC: 'sec(U)*tan(U)', K.CSC: '-csc(U)*cot(U)', K.COT: '-csc(U)^2',
      K.ASIN: '1/sqrt(1-U^2)', K.ACOS: '-1/sqrt(1-U^2)', K.ATAN: '1/(1+U^2)',
      K.SINH: 'cosh(U)', K.COSH: 'sinh(U)', K.TANH: '1/cosh(U)^2',
      K.LN: '1/U', K.ABS: 'sign(U)', K.SIGN: '0', K.FLOOR: '0', K.CEIL: '0'}
MAXORDER = 20
M_ARG = 'Invalid argument'


def variables(e):                                              #@L 3
    # Call heads are names, not independent variables.
    nodes = A.postorder(e)
    heads = []
    for n in nodes:
        if K.N[n][0] == K.CALL:
            heads.append(K.N[n][1])
    names = []
    for n in nodes:
        if K.N[n][0] == K.SYM and n not in heads:
            names.append((K.N[n][1], n))
    names.sort()
    out = []
    for name, n in names:
        out.append(n)
    return out


def product(t, d):                                             #@L 3
    # Differentiate each factor b^p, retaining the others without introducing 1/b
    # for constant powers. General exponents use logarithmic differentiation.
    out = []
    for j in range(2, len(t), 2):
        b, p = t[j], t[j + 1]
        db, dp = d[b], d[p]
        if db == K.ZERO and dp == K.ZERO:
            continue
        pairs = []
        for h in range(2, len(t), 2):
            if h != j:
                pairs.append((t[h], t[h + 1]))
        if dp == K.ZERO:
            pairs += [(p, K.ONE), (db, K.ONE), (b, K.add_([p, K.MONE]))]
        else:
            terms = []
            if dp != K.ZERO:
                terms.append(K.mul_(K.ONE, [(dp, K.ONE), (K.fn_(K.LN, b), K.ONE)]))
            if db != K.ZERO:
                terms.append(K.mul_(K.ONE, [(p, K.ONE), (db, K.ONE), (b, K.MONE)]))
            pairs += [(b, p), (K.add_(terms), K.ONE)]
        out.append(K.mul_(t[1], pairs))
    return K.add_(out)


def g_deriv(e, x):                                              #@L 2
    # Shared calculus API: yields one derivative node, with no automatic simplify.
    # Unknown calls retain diff(call,x). Integral nodes obey the full Leibniz rule;
    # the integration variable binds only the integrand, not the bounds.
    if K.N[x][0] != K.SYM:
        raise K.CasError(M_ARG)
    d = {}
    for n in A.postorder(e):
        t = K.N[n]
        op = t[0]
        r = K.ZERO
        if n == x:
            r = K.ONE
        elif op == K.LST:
            out = [K.LST]
            for c in t[1:]:
                out.append(d[c])
            r = K.mk(tuple(out))
        elif K.free_of(n, x):
            pass
        elif op == K.ADD:
            terms = []
            for j in range(2, len(t), 2):
                terms.append(K.mul_(t[j + 1], [(d[t[j]], K.ONE)]))
            r = K.add_(terms)
        elif op == K.MUL:
            r = product(t, d)
        elif op in DT:
            if d[t[1]] != K.ZERO:
                env = [0] * P.NSLOT
                env[P.WSLOT['U'][0]] = t[1]
                template = P.inst(P.tcode(DT[op]), env)
                r = K.mul_(K.ONE, [(d[t[1]], K.ONE), (template, K.ONE)])
        elif op == K.CALL and K.N[t[1]][1] in ('integrate', 'int') and len(t) in (4, 6):
            f, v = t[2], t[3]
            if K.N[v][0] != K.SYM:
                raise K.CasError(M_ARG)
            terms = []
            if len(t) == 4 and v == x:
                terms.append(f)
            elif v != x and d[f] != K.ZERO:
                terms.append(K.mk((K.CALL, t[1], d[f]) + t[3:]))
            if len(t) == 6:
                for bound, sign in ((t[5], K.ONE), (t[4], K.MONE)):
                    if d[bound] != K.ZERO:
                        value = A.subst(f, v, bound)
                        terms.append(K.mul_(sign, [(value, K.ONE), (d[bound], K.ONE)]))
            r = K.add_(terms)
        else:
            r = K.mk((K.CALL, K.sym('diff'), n, x))
        d[n] = r
        yield R.TICK
    yield d[e]


def g_diff(args, ctx):                                          #@L 2
    e = args[0]
    xs = variables(e)
    x = args[1] if len(args) > 1 else (xs[0] if len(xs) == 1 else K.sym('x'))
    n = K.N[args[2]] if len(args) > 2 else K.N[K.ONE]
    if K.N[x][0] != K.SYM or n[0] != K.NUM or n[2] or n[3] != 1 or not 0 <= n[1] <= MAXORDER:
        raise K.CasError(M_ARG)
    ctx[P.X_MV] = x
    for j in range(n[1]):
        e = yield g_deriv(e, x)
        if j + 1 < n[1]:
            simplified = yield R.MODS['norm'].g_autosimp(e)
            if simplified is not None:
                e = simplified
    yield e


def g_grad(args, ctx):                                          #@L 2
    e = args[0]
    if len(args) > 1:
        t = K.N[args[1]]
        if t[0] != K.LST:
            raise K.CasError(M_ARG)
        xs = t[1:]
    else:
        xs = variables(e)
    for x in xs:
        if K.N[x][0] != K.SYM:
            raise K.CasError(M_ARG)
    out = []
    for x in xs:
        r = yield g_deriv(e, x)
        s = yield R.MODS['norm'].g_autosimp(r)
        out.append(r if s is None else s)
    yield K.mk((K.LST,) + tuple(out))
