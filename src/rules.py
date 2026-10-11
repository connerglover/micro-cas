#@L 3
# CVRULE: the rule-set compiler and cache, guards, the matcher's wildcard check and the
# rewriter (DESIGN 9.2-9.7): part a of the CVRULE family; the matcher is part b, reached as
# R.MODS['rulesb'] (4.3). Compiled sets live in K.RULECACHE, which K.keep treats as roots
# and K.reset clears with the command.
import node as K
import alg as A
import parse as P
import run as R

VIEW = -1           # the bucket of view-aware rules (ADD, MUL or wildcard heads, 9.4)
NEAR = 2            # guard_ok: a constant difference too close to 0 to decide numerically
MAXPASS = 8         # rewrite passes (10.7)
MAXALT = 6          # bindings a rule tries when its guard fails (3 pairs: 3*2 orders)
WHERE = {'itab': 'itab'}    # rule set name -> module key; any other set lives in ident
SA = 3              # the slots A, B, C that the binders L and Q write (parse.WSLOT)


def rset(name):                                                 #@L 3
    # The compiled rule set name (9.4): {head op: ((pattern id, rhs, guard), ...)} with the
    # bucket VIEW, cached in K.RULECACHE[name]. The strings are the tuple NAME (upper case)
    # of the set's module: (lhs, rhs, guard, ...), after a measure tuple for identity sets.
    # An ADD-, MUL- or wildcard-headed rule goes into every bucket; a new head's bucket
    # starts with the VIEW rules before it, so every bucket is in file order.
    rs = K.RULECACHE.get(name)
    if rs is not None:
        return rs
    data = getattr(R.MODS[WHERE.get(name, 'ident')], name.upper())
    m = K.NN
    rs = {VIEW: []}
    j = 1 if type(data[0]) is tuple else 0
    while j < len(data):
        p = P.inst(P.tcode(data[j]), None)
        r = (p, data[j + 1], data[j + 2])
        h = K.N[p][0]
        if h == K.ADD or h == K.MUL or h == K.WILD:
            for b in rs:                                        #@unordered-ok
                rs[b].append(r)
        else:
            if h not in rs:
                rs[h] = list(rs[VIEW])
            rs[h].append(r)
        j += 3
    for b in rs:                                                #@unordered-ok
        rs[b] = tuple(rs[b])
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


def check(c, s, env, x, trail):                                 #@L 4
    # does s satisfy the wildcard constraint c (P.W_*, 9.2)? FREE without a focus variable
    # means constant. LIN and QUAD also bind A, B (and C), on the trail so that backtracking
    # undoes them; a binder whose leading coefficient is 0 fails.
    t = K.N[s]
    if c == P.W_NUMB or c == P.W_INT:
        return t[0] == K.NUM and (c == P.W_NUMB or (not t[2] and t[3] == 1))
    if c == P.W_FREE:
        return K.free_of(s, x) if x else not K.V[s]
    if c != P.W_LIN and c != P.W_QUAD:
        return True                                             # ANY, REST
    r = None
    if x:
        r = A.linear(s, x) if c == P.W_LIN else A.quadratic(s, x)
    if r is None or r[0] == K.ZERO:
        return False
    for j in range(len(r)):
        v = env[SA + j]
        if not v:
            env[SA + j] = r[j]
            trail.append(SA + j)
        elif v != r[j]:
            return False
    return True


def g_rewrite(root, rs, x, budget):                             #@L 2
    # Rewrite to a fixpoint with the rule set rs (a name or rset's dict) and the focus
    # variable x (0 or None: none) (9.7): bottom-up passes over postorder(root); a node whose
    # child changed is rebuilt, then the first rule of its bucket fires that matches with a
    # binding whose guard holds and whose result is a different node (a result that the
    # constructors fold back to the node is no fire). A rule tries at most MAXALT bindings in
    # the matcher's order. Each pass keeps only its result. Stops at a fixpoint, a repeated
    # root or MAXPASS passes; more than budget fires in one pass is a soft failure. Yields
    # TICK after each pass that changed the root, then the result.
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
                r = m
                k = 0
                while r == m and k < MAXALT and MT.match(p, m, env, x, k):
                    ok = guard_ok(guard, env)
                    if type(ok) is tuple:       # constant and near 0: the exact test (L2)
                        ok = R.MODS['norm'].normal(ok[2]) == K.ZERO and (
                            ok[1] == K.EQ or ok[1] == K.LE)
                    if ok:
                        r = P.inst(P.tcode(rhs), env)
                    env = [0] * P.NSLOT
                    env[P.XSLOT] = x
                    k += 1
                if r != m:
                    m = r
                    fired += 1
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
