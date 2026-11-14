#@L 2
# Step-by-step working (docs/notes/STEPS.md; sdiff.py describes the scheme) of an equation (linear, factorable, quadratic) and of a limit
# (direct substitution, L'Hopital's rule). A limit's chain is shown only when it ends at the
# entry's own answer (the check pair that printer.steps compares).
import node as K
import alg as A
import parse as P
import run as R


def add(out, title, a, b):                                      #@L 4
    """One step: its title and the line a=b (ids). K.UNDEF as a: b alone; as b: the entry's
    answer. An empty title is a check, not a step: b must print as the entry's answer."""
    R.STEPS.append(title)
    out.append(a)
    out.append(b)


def call(name, args):                                           #@L 4
    return K.mk((K.CALL, K.sym(name)) + tuple(args))


def done(out, title, lhs, ctx):                                 #@L 3
    """The end of a walk: the entry's own answer as the last step, and LST(lhs1, rhs1, ...)
    for printer.steps. No title (no walk) or no step is the message 'No steps'."""
    if not title or not out:
        raise K.CasError('No steps for this one')
    add(out, title, lhs, K.UNDEF)
    ctx[P.X_APPROX] = 0                 # a decimal in the input: the lines stay exact
    return K.mk((K.LST,) + tuple(out))


def g_walk(args, ctx):                                          #@L 2
    R.need('norm')
    out = []
    if R.STEPS[0] == 'solve':
        t = yield g_solve(args, ctx, out)
        yield done(out, t, K.UNDEF, ctx)
    else:
        t = yield g_limit(args, ctx, out)
        yield done(out, t, call('limit', args), ctx)


def disc(a, b, c):                                              #@L 3
    return K.add_([K.mul_(K.ONE, [(b, K.TWO)]), K.mul_(K.num(-4), [(a, K.ONE), (c, K.ONE)])])


def root(a, b, d, s):                                           #@L 3
    # (-b + s*sqrt(d))/(2*a)
    return K.mul_(K.ONE, [(K.add_([K.neg_(b), K.mul_(s, [(d, K.HALF)])]), K.ONE),
                          (K.mul_(K.TWO, [(a, K.ONE)]), K.MONE)])


def g_solve(args, ctx, out):                                    #@L 2
    """solve(eq, [x]) for one polynomial equation. Yields the title of the answer step, or
    None for no steps (systems, inequalities, other equations)."""
    e = args[0]
    t = K.N[e]
    if t[0] == K.LST or K.NE <= t[0] <= K.LE or len(args) > 1 and K.N[args[1]][0] != K.SYM:
        yield None
        return
    f = K.add_([t[1], K.neg_(t[2])]) if t[0] == K.EQ else e
    if len(args) > 1:
        x = args[1]
    else:
        v = R.MODS['diff'].variables(f)
        x = v[0] if len(v) == 1 else K.sym('x')
    ctx[P.X_MV] = x
    if t[0] == K.EQ and t[2] != K.ZERO:
        add(out, 'Move all terms to one side', f, K.ZERO)
    n = R.MODS['norm'].normal(f)
    t = K.N[n]
    if t[0] == K.MUL:                   # k*N/D = 0 is N = 0
        top = []
        den = False
        for j in range(2, len(t), 2):
            w = K.N[t[j + 1]]
            if w[0] == K.NUM and not w[2] and w[1] < 0:
                den = den or not K.free_of(t[j], x)
            elif not K.free_of(t[j], x):
                top.append((t[j], t[j + 1]))
        n = K.mul_(K.ONE, top)
        if den:
            add(out, 'Multiply by the denominator', n, K.ZERO)
        else:                           # no denominator: the equation keeps its coefficients
            n = f
    n = R.MODS['norm'].normal(n, 1)
    d = A.degree(n, x)
    if d == 1:
        ab = A.linear(n, x)
        if ab is None:
            yield None
            return
        add(out, 'Isolate the variable term', K.mul_(K.ONE, [(ab[0], K.ONE), (x, K.ONE)]),
               K.neg_(ab[1]))
        yield 'Answer' if ab[0] == K.ONE else 'Divide both sides'
        return
    if d < 2:
        yield None
        return
    FA = R.need('fact')
    fa = yield FA.g_factor((n,), ctx)
    t = K.N[fa]
    bases = []
    k = 0
    if t[0] == K.MUL:
        for j in range(2, len(t), 2):
            w = K.N[t[j + 1]]
            if not K.free_of(t[j], x):
                bases.append(t[j])
                k += w[1] if w[0] == K.NUM and not w[2] and w[3] == 1 and w[1] > 0 else 1
    if k > 1:
        add(out, 'Factor', n, fa)
        for b in bases[:6]:
            add(out, 'A factor is zero', b, K.ZERO)
        yield 'Solve each equation'
        return
    q = A.quadratic(n, x) if d == 2 else None
    if q is None:
        yield None
        return
    # the formula in the letters a, b, c, then with the equation's numbers
    a, b, c = K.sym('a'), K.sym('b'), K.sym('c')
    add(out, 'Standard form', n, K.ZERO)
    add(out, 'Read off a, b, c', K.UNDEF, K.mk((K.LST, K.mk((K.EQ, a, q[0])),
                                                 K.mk((K.EQ, b, q[1])), K.mk((K.EQ, c, q[2])))))
    t = disc(a, b, c)
    add(out, 'Quadratic formula', x, root(a, b, t, K.ONE))
    a, b, c = q
    d = disc(a, b, c)
    add(out, 'Discriminant', t, d)
    add(out, 'With these numbers', x, root(a, b, d, K.ONE))
    add(out, 'And with the other sign', x, root(a, b, d, K.MONE))
    yield 'Simplify'


def g_limit(args, ctx, out):                                    #@L 2
    """limit(f, x, a, [side]) and limit(f, x=a, [side]): direct substitution, after up to
    three uses of L'Hopital's rule on 0/0 or oo/oo. Yields the answer step's title, or None."""
    f, x = args[0], args[1]
    t = K.N[x]
    side = K.ZERO
    if t[0] == K.EQ:
        if len(args) > 3:
            yield None
            return
        x, a = t[1], t[2]
        if len(args) == 3:
            side = args[2]
    else:
        if len(args) < 3:
            yield None
            return
        a = args[2]
        if len(args) == 4:
            side = args[3]
    q = K.N[side]
    if K.N[x][0] != K.SYM or q[0] != K.NUM or q[2] or q[3] != 1 or q[1] not in (-1, 0, 1):
        yield None
        return
    ctx[P.X_MV] = x
    R.need('lim')
    LB = R.MODS['limb']
    tail = (x, a, side) if q[1] else (x, a)
    for k in range(4):
        r = yield LB.g_direct(f, x, a, q[1] or 1)
        if r is not None:
            add(out, '', K.UNDEF, r)         # the check: r is the entry's answer
            add(out, 'Direct substitution', x, a)
            yield 'Evaluate'
            return
        t = K.N[f]
        top = []
        bot = []
        if t[0] == K.MUL:
            for j in range(2, len(t), 2):
                w = K.N[t[j + 1]]
                if w[0] == K.NUM and not w[2] and w[1] < 0:
                    bot.append((t[j], K.neg_(t[j + 1])))
                else:
                    top.append((t[j], t[j + 1]))
        if not bot:
            break
        n = K.mul_(t[1], top)
        d = K.mul_(K.ONE, bot)
        rn = yield LB.g_direct(n, x, a, q[1] or 1)
        rd = yield LB.g_direct(d, x, a, q[1] or 1)
        if rn is None or rd is None:
            break
        title = "L'Hopital's rule: 0/0"
        if rn != K.ZERO or rd != K.ZERO:
            if not ((rn == K.OO or K.isninf(rn)) and (rd == K.OO or K.isninf(rd))):
                break
            title = "L'Hopital's rule: oo/oo"
        n = yield R.MODS['diff'].g_deriv(n, x)
        d = yield R.MODS['diff'].g_deriv(d, x)
        g = K.mul_(K.ONE, [(n, K.ONE), (d, K.MONE)])
        s = yield R.MODS['norm'].g_autosimp(g)
        if s is not None:
            g = s
        add(out, title, call('limit', (f,) + tail), call('limit', (g,) + tail))
        f = g
    yield None
