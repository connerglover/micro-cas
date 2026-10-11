#@L 3
# CVRULE: the rule-set compiler and cache, guards and the rewriter (DESIGN 9.2-9.7), part a of
# the CVRULE family; the matcher is part b, reached as R.MODS['rulesb'] (4.3). Compiled sets
# live in K.RULECACHE, which K.keep treats as roots and K.reset clears with the command.
import node as K
import alg as A
import parse as P
import run as R

VIEW = -1           # the bucket of view-aware rules (ADD, MUL or wildcard heads, 9.4)
NEAR = 2            # guard_ok: a constant difference too close to 0 to decide numerically
MAXPASS = 8         # rewrite passes (10.7)
WHERE = {'itab': 'itab'}    # rule set name -> module key; any other set lives in ident


def rset(name):                                                 #@L 3
    # The compiled rule set name (9.4): {head op: ((pattern id, rhs, guard), ...)} with
    # bucket VIEW, cached in K.RULECACHE[name]. The strings are the tuple NAME (upper case)
    # of the set's module: (lhs, rhs, guard, ...), after a measure tuple for identity sets.
    rs = K.RULECACHE.get(name)
    if rs is not None:
        return rs
    data = getattr(R.MODS[WHERE.get(name, 'ident')], name.upper())
    m = K.NN
    hs = []
    es = []
    j = 1 if type(data[0]) is tuple else 0
    while j < len(data):
        p = P.inst(P.tcode(data[j]), None)
        h = K.N[p][0]
        if h == K.ADD or h == K.MUL or h == K.WILD:
            h = VIEW
        elif h not in hs:
            hs.append(h)
        es.append((h, (p, data[j + 1], data[j + 2])))
        j += 3
    bk = {VIEW: []}
    for h in hs:
        bk[h] = []
    for h, r in es:                                 # file order within every bucket
        if h == VIEW:
            for b in bk:                                        #@unordered-ok
                bk[b].append(r)
        else:
            bk[h].append(r)
    rs = {}
    for b in bk:                                                #@unordered-ok
        rs[b] = tuple(bk[b])
    K.RULECACHE[name] = rs
    K.keep(m, None)                     # drop the build garbage; the patterns are remapped
    return rs


def guard_ok(guard, env):                                       #@L 3
    # Decide a guard (9.2): '' holds; otherwise one relation or a comma list of relations
    # that must all hold, instantiated with env. A relation folds to true/false, or its
    # constant difference is decided numerically; a difference with free symbols fails, or
    # holds after a leading '~' (the branch policy, 8.3: symbolic inputs are real only where
    # the relation holds). Returns 1, 0 or (NEAR, op, d) for one constant difference d that
    # is near 0, for the calling generator to settle exactly.
    if not guard:
        return 1
    soft = guard[0] == '~'
    if soft:
        guard = guard[1:]
    try:
        g = P.inst(P.tcode(guard), env)
    except K.CasSoft:
        return 0
    t = K.N[g]
    rel = t[1:] if t[0] == K.LST else (g,)
    near = None
    for r in rel:
        if r == K.TRUE:
            continue
        t = K.N[r]
        op = t[0]
        if op < K.EQ or op > K.LE:
            return 0
        d = K.add_([t[1], K.neg_(t[2])])
        if K.V[d]:
            if soft:
                continue
            return 0
        try:
            p = A.nprog(d, ())
            v = [0.0] * len(p)
            w = [0.0] * len(p)
            u = A.nrun(p, (), v)
            w = A.ntol(p, v, w)
        except K.CasSoft:
            return 0
        if w < 0 or type(u) is complex:
            return 0
        if u > w or u < -w:
            if op == K.EQ or (op != K.NE and u > 0):
                return 0
        elif near is None:
            near = (NEAR, op, d)
        else:
            return 0
    if near is None:
        return 1
    return near


def g_rewrite(root, rs, x, budget):                             #@L 2
    # Rewrite to a fixpoint with the rule set rs (a name or rset's dict) and the focus
    # variable x (0: none) (9.7): bottom-up passes over postorder(root); a node whose child
    # changed is rebuilt, then the first rule of its bucket that matches and whose guard
    # holds fires. Each pass keeps only its result. Stops at a fixpoint, a repeated root or
    # MAXPASS passes; more than budget fires in one pass is a soft failure.
    MT = R.MODS['rulesb']
    if type(rs) is str:
        rs = rset(rs)
    if not x:
        x = 0
    env = [0] * P.NSLOT
    env[P.XSLOT] = x
    seen = [root]
    for npass in range(MAXPASS):
        m0 = K.NN
        new = {}
        fired = 0
        for n in A.postorder(root):
            m = A.rebuild(n, new)
            for p, rhs, guard in rs.get(K.N[m][0], rs[VIEW]):
                if not MT.match(p, m, env, x):
                    continue
                ok = guard_ok(guard, env)
                if type(ok) is tuple:           # constant and near 0: the exact test (L2)
                    ok = R.MODS['norm'].normal(ok[2]) == K.ZERO and (
                        ok[1] == K.EQ or ok[1] == K.LE)
                if ok:
                    m = P.inst(P.tcode(rhs), env)
                    fired += 1
                env = [0] * P.NSLOT
                env[P.XSLOT] = x
                if ok:
                    break
            if m != n:
                new[n] = m
        if fired > budget:
            raise K.CasSoft('rewrite budget')
        r = K.keep(m0, new.get(root, root))         # drop this pass's garbage
        if r == root or r in seen:                  # a fixpoint or a cycle
            break
        seen.append(r)
        root = r
        yield R.TICK                                # let the driver poll [clear]
    yield root


def g_apply(e, rs, x):                                          #@L 2
    # Match and instantiate at the root only (the integral table, 9.1): the right-hand side
    # of the first rule of rs (a name or rset's dict) that matches e and whose guard holds,
    # instantiated; None when no rule fires.
    MT = R.MODS['rulesb']
    if type(rs) is str:
        rs = rset(rs)
    if not x:
        x = 0
    env = [0] * P.NSLOT
    env[P.XSLOT] = x
    r = None
    for p, rhs, guard in rs.get(K.N[e][0], rs[VIEW]):
        if not MT.match(p, e, env, x):
            continue
        ok = guard_ok(guard, env)
        if type(ok) is tuple:
            ok = R.MODS['norm'].normal(ok[2]) == K.ZERO and (ok[1] == K.EQ or ok[1] == K.LE)
        if ok:
            r = P.inst(P.tcode(rhs), env)
            break
        env = [0] * P.NSLOT
        env[P.XSLOT] = x
    yield r
