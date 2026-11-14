#@L 2
# Step-by-step working of an integral (docs/notes/STEPS.md; sdiff.py describes the scheme). The
# walk mirrors integ.g_int (constant multiple,
# sum, table, substitution, then one strategy at a time) and calls the same strategies, so a
# line is shown only when the engine itself found and checked that primitive.
import node as K
import alg as A
import parse as P
import run as R

# integ.EXTRA, with g_advanced as its two parts: (family key, generator, title)
WAYS = (('int2', 'g_tabular', 'Integration by parts'), ('int2', 'g_trig', 'Trig identities'),
        ('int2b', 'g_rational', 'Partial fractions'), ('int3', 'g_radical', 'Radical formula'),
        ('int3', 'g_parts', 'Integration by parts'), ('int3b', 'g_substitutions', 'Substitution'))
MAXSTEPS = 24       # as in sdiff
MAXNODES = 560


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
    """integrate(f, [x]) and integrate(f, x, a, b): the antiderivative's steps. work holds
    groups of four: 'I', f, x, 0 (explain the integral of f) or 'B', F, f, x (the line that
    closes a substitution). An integral with no primitive found has no steps."""
    x = args[1] if len(args) > 1 else K.sym('x')
    if len(args) == 3 or K.N[x][0] != K.SYM:
        raise K.CasError('No steps for this one')
    ctx[P.X_MV] = x
    R.need('norm')
    IN = R.need('int')
    S = R.STEPS
    out = []
    work = ['I', args[0], x, 0]
    while work and len(S) <= MAXSTEPS and K.NN < MAXNODES:
        q = work.pop()
        x = work.pop()
        f = work.pop()
        if work.pop() == 'B':           # f is the primitive, x the integrand, q its variable
            f = yield R.MODS['normb'].g_polish(f, q, True)
            add(out, 'Substitute back', call('integrate', (x, q)), f)
            continue
        lhs = call('integrate', (f, x))
        c, v = A.split_const(f, x)
        t = K.N[v]
        if K.free_of(f, x):
            add(out, 'Integral of a constant', lhs, IN.scale(f, x))
        elif c != K.ONE:
            add(out, 'Constant multiple', lhs, IN.scale(c, call('integrate', (v, x))))
            work += ['I', v, x, 0]
        elif t[0] == K.ADD:
            ts = []
            new = []
            if t[1] != K.ZERO:
                ts.append(call('integrate', (t[1], x)))
                new.append(t[1])
            for j in range(2, len(t), 2):
                ts.append(K.mul_(t[j + 1], [(call('integrate', (t[j], x)), K.ONE)]))
                new.append(t[j])
            add(out, 'Sum rule', lhs, K.add_(ts))
            while new:
                work += ['I', new.pop(), x, 0]
        else:
            title = 'Known integral'
            if v == x or (t[0] == K.MUL and len(t) == 4 and t[2] == x and t[3] != K.MONE and
                          K.free_of(t[3], x)):
                title = 'Power rule'
            r = yield R.scoped(IN.g_table(v, x, 0))
            if r is None:
                IN.USUB[0] = 0
                r = yield R.scoped(IN.g_usub(v, x, 0))
                u = IN.USUB[0]
                if r is not None and u:
                    w = K.sym('u')
                    for nm in ('w', 't', 's', 'p', 'q'):
                        if K.free_of(v, w):
                            break
                        w = K.sym(nm)
                    du = yield R.MODS['diff'].g_deriv(u, x)
                    q = R.MODS['norm'].normal(K.mul_(K.ONE, [(v, K.ONE), (du, K.MONE)]))
                    q = A.subst(q, u, w)
                    if K.free_of(v, w) and K.free_of(q, x):
                        add(out, 'Substitution', w, u)
                        add(out, 'Rewrite the integral', lhs, call('integrate', (q, w)))
                        work += ['B', r[0], v, x, 'I', q, w, 0]
                        continue
                    title = 'Substitution'
            if r is None:
                for key, name, title in WAYS:
                    mod = R.need(key)
                    if name == 'g_rational':
                        # the decomposition is the step; its terms are then explained one by
                        # one, each a lighter search than the rational strategy as a whole
                        q = yield R.scoped(R.MODS['int2b'].g_partfrac((v, x), ctx))
                        if q != v and K.N[q][0] == K.ADD:
                            add(out, title, v, q)
                            work += ['I', q, x, 0]
                            r = 0
                            break
                    r = yield R.scoped(getattr(mod, name)(v, x, 0))    #@calls 2
                    if r is not None and r[1] == K.ZERO:
                        good = yield IN.g_check(r[0], r[1], v, x)
                        if good:
                            break
                    r = None
                    mod = None
                    R.drop((key,), True)
                mod = None
                if r == 0:
                    R.drop((key,), True)
                    continue
            if r is None or r[1] != K.ZERO:
                raise K.CasError('No steps for this one')
            r = yield R.MODS['normb'].g_polish(r[0], x, True)   # as the answer is written
            add(out, title, lhs, r)
    yield done(out, 'Evaluate at the bounds' if len(args) == 4 else 'Answer',
               call('integrate', args), ctx)
