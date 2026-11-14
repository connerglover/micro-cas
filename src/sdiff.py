#@L 2
# Step-by-step working of a derivative (docs/notes/STEPS.md). Nothing is recorded while a
# command runs: a steps job (run.start) parses the history entry again and puts g_walk in place
# of its last command. The walk only builds nodes: a title in R.STEPS and a pair lhs, rhs per
# step. Their texts are made afterwards (printer.steps), once the command's families can give
# way to the printer. Each steps command has its walk in a pack of its own (sdiff, sint, salg).
import node as K
import alg as A
import parse as P
import run as R

MAXSTEPS = 24       # steps kept: a walk stops there, the answer still follows
MAXNODES = 560      # ... or when the node table is this full (the cap is 768)


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
    """diff(e, [x], [n]): the rule at each node from the top down (sum, constant multiple,
    product, quotient, power, chain, known derivative), each line with the parts still to do
    as diff(...). A higher order is one line per derivative."""
    R.need('norm')                      # diff, normal and the simplifier, for the whole walk
    DF = R.MODS['diff']
    out = []
    e = args[0]
    xs = DF.variables(e)
    x = args[1] if len(args) > 1 else (xs[0] if len(xs) == 1 else K.sym('x'))
    n = K.N[args[2]] if len(args) > 2 else K.N[K.ONE]
    if K.N[x][0] != K.SYM or n[0] != K.NUM or n[2] or n[3] != 1 or not 1 <= n[1] <= 6:
        raise K.CasError('No steps for this one')
    ctx[P.X_MV] = x
    S = R.STEPS
    if n[1] > 1:
        for j in range(n[1]):
            d = yield DF.g_deriv(e, x)
            s = yield R.MODS['norm'].g_autosimp(d)
            if s is not None:
                d = s
            add(out, 'Differentiate again' if j else 'Differentiate', call('diff', (e, x)), d)
            e = d
        yield done(out, 'Answer', call('diff', args), ctx)
        return
    work = [e]
    while work and len(S) <= MAXSTEPS and K.NN < MAXNODES:
        u = work.pop()
        if u == x or K.free_of(u, x):
            continue
        t = K.N[u]
        op = t[0]
        title = 'Derivative'
        r = None
        new = []
        c, v = A.split_const(u, x)
        if c != K.ONE:
            title = 'Constant multiple'
            if v != x:
                r = K.mul_(K.ONE, [(c, K.ONE), (call('diff', (v, x)), K.ONE)])
                new.append(v)
        elif op == K.ADD:
            title = 'Sum rule'
            ts = []
            for j in range(2, len(t), 2):
                if not K.free_of(t[j], x):
                    ts.append(K.mul_(t[j + 1], [(call('diff', (t[j], x)), K.ONE)]))
                    new.append(t[j])
            r = K.add_(ts)
        elif op == K.MUL and len(t) == 4:
            b, p = t[2], t[3]
            if K.free_of(p, x):
                title = 'Power rule'
                if b != x:              # (b^p)' = p*b^(p-1)*b'
                    title = 'Chain rule'
                    r = K.mul_(K.ONE, [(p, K.ONE), (b, K.add_([p, K.MONE])),
                                       (call('diff', (b, x)), K.ONE)])
                    new.append(b)
            elif K.free_of(b, x):
                title = 'Known derivative'
                if p != x:              # (b^p)' = b^p*ln(b)*p'
                    title = 'Chain rule'
                    ps = [(u, K.ONE), (call('diff', (p, x)), K.ONE)]
                    if b != K.E:
                        ps.append((K.fn_(K.LN, b), K.ONE))
                    r = K.mul_(K.ONE, ps)
                    new.append(p)
            else:
                title = 'Logarithmic differentiation'
        elif op == K.MUL:
            top = []
            bot = []
            for j in range(2, len(t), 2):
                w = K.N[t[j + 1]]
                if w[0] == K.NUM and not w[2] and w[1] < 0:
                    bot.append((t[j], K.neg_(t[j + 1])))
                else:
                    top.append((t[j], t[j + 1]))
            if top and bot:             # (f/g)' = (f'*g - f*g')/g^2
                title = 'Quotient rule'
                f = K.mul_(K.ONE, top)
                g = K.mul_(K.ONE, bot)
                r = K.add_([K.mul_(K.ONE, [(call('diff', (f, x)), K.ONE), (g, K.ONE)]),
                            K.mul_(K.MONE, [(f, K.ONE), (call('diff', (g, x)), K.ONE)])])
                r = K.mul_(K.ONE, [(r, K.ONE), (g, K.num(-2))])
            else:                       # (f*g)' = f'*g + f*g'
                title = 'Product rule'
                f = K.mul_(K.ONE, [(t[2], t[3])])
                g = K.mk((K.MUL, K.ONE) + t[4:]) if len(t) > 6 else K.mul_(K.ONE, [(t[4], t[5])])
                r = K.add_([K.mul_(K.ONE, [(call('diff', (f, x)), K.ONE), (g, K.ONE)]),
                            K.mul_(K.ONE, [(f, K.ONE), (call('diff', (g, x)), K.ONE)])])
            new.append(f)
            new.append(g)
        elif op in DF.DT:
            title = 'Known derivative'
            if t[1] != x:               # f(g)' = f'(g)*g'
                title = 'Chain rule'
                env = [0] * P.NSLOT
                env[P.WSLOT['U'][0]] = t[1]
                r = K.mul_(K.ONE, [(P.inst(P.tcode(DF.DT[op]), env), K.ONE),
                                   (call('diff', (t[1], x)), K.ONE)])
                new.append(t[1])
        if r is None:
            r = yield DF.g_deriv(u, x)
        add(out, title, call('diff', (u, x)), r)
        while new:                      # the first part is explained first
            work.append(new.pop())
    yield done(out, 'Answer', call('diff', args), ctx)
