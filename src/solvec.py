#@L 2
# CVSOLVE part c: systems (DESIGN 11.2) and the numeric root finder. A system linear in its
# unknowns with rational coefficients is solved by Gauss-Jordan over Q (polyb.gjsolve), every
# other monomial on the right-hand side (parameters); free unknowns stay symbols. Any other
# system eliminates one unknown at a time by substitution (the equation and unknown of lowest
# degree first). Every solution is checked against every equation (solve.g_ok).
import node as K
import alg as A
import run as R

MAXVARS = 8


def lsys(rs, vs):                                               #@L 3
    # the normal forms rs = 0 as a linear system over Q in the unknowns vs: [solution] (a
    # tuple of values, a free unknown its own symbol), [] when inconsistent, None when not
    # linear with rational coefficients (or a denominator holds an unknown)
    FA = R.MODS['fact']
    nv = len(vs)
    ks = list(vs)
    mk = 0                          # the unknowns' symbol bits (an overflow bit: not linear)
    for x in vs:
        mk |= K.V[x]
    outs = []
    for r in rs:
        n, d = R.MODS['solve'].nd(r)
        out = []
        if K.V[d] & mk or not FA.terms(n, ks, out):
            return None
        outs.append(out)
    for k in ks[nv:]:
        if K.V[k] & mk:
            return None
    mono = {}                       # a right-hand-side monomial -> its column
    rows = []
    for out in outs:
        row = [0] * nv
        for p in out:
            p = p + [0] * (len(ks) + 1 - len(p))
            m = tuple(p[nv + 1:])
            s = sum(p[1:nv + 1])
            if s > 1 or (s and any(m)):
                return None
            j = p.index(1, 1) - 1 if s else mono.setdefault(m, nv + len(mono))
            row.extend([0] * (j + 1 - len(row)))
            row[j] += p[0] if s else -p[0]
        rows.append(row)
    w = nv + len(mono)
    for row in rows:
        row.extend([0] * (w - len(row)))
    res = R.MODS['polyb'].gjsolve(rows, nv)
    if res is None:
        return []
    mn = list(vs) + [0] * len(mono)
    for m in mono:                                              #@unordered-ok
        mn[mono[m]] = FA.mkpoly({(0,) * nv + m: 1}, ks, 1)
    vals = list(vs)
    for k in range(len(res[0])):
        c = res[0][k]
        row = res[1][k]
        ts = []
        for j in range(w):
            if row[j] and j != c:
                ts.append(K.mul_(K.num(row[j] if j >= nv else -row[j], 0, row[c]),
                                 [(mn[j], K.ONE)]))
        vals[c] = K.add_(ts)
    return [tuple(vals)]


def g_sys(e, v, md):                                            #@L 2
    # solve([eqs], [vars]) (11.2): one solution is the list x=a,y=b (the free unknowns left
    # out), several a list of such lists; the empty list: no solution; TRUE: every value.
    # With no variable list, the unknowns are the symbols in name order.
    SO = R.MODS['solve']
    NO = R.MODS['norm']
    t = K.N[e]
    fs = []
    for q in (t[1:] if t[0] == K.LST else (e,)):
        u = K.N[q]
        if q == K.FALSE:
            yield K.mk((K.LST,))
            return
        if K.NE <= u[0] <= K.LE or u[0] == K.LST:
            raise K.CasSoft(SO.M_CANT)
        if q != K.TRUE:
            fs.append(K.add_([u[1], K.neg_(u[2])]) if u[0] == K.EQ else q)
    fs = tuple(fs)
    vs = tuple(K.N[v][1:] if K.N[v][0] == K.LST else (v,)) if v else tuple(SO.syms(fs))
    for x in vs:
        if K.N[x][0] != K.SYM or vs.count(x) > 1:
            raise K.CasError(SO.M_ARG)
    if len(vs) > MAXVARS:
        raise K.CasError(SO.M_ARG)
    rs = []
    for f in fs:
        rs.append(NO.normal(f))
    ss = lsys(rs, vs)
    if ss is None:
        ss = yield g_elim(tuple(rs), vs, 0, md)
        if ss is None:
            return
    ss = yield R.MODS['solved'].g_fin(fs, (), vs, ss)
    out = []
    for z in ss:
        q = [K.LST]
        for j in range(len(vs)):
            if z[j] != vs[j]:
                q.append(K.rel_(K.EQ, vs[j], z[j]))
        if len(q) == 1:
            yield K.TRUE
            return
        out.append(K.mk(tuple(q)))
    yield out[0] if len(out) == 1 else K.mk(tuple([K.LST] + out))


def g_elim(rs, vs, dep, md):                                    #@L 2
    # the solutions of the system rs = 0 (normal forms) in vs by elimination: a list of value
    # tuples (a free unknown is its own symbol), or a soft failure. The equation and unknown
    # of the lowest degree are solved first (solve.g_eq), the root substituted into the rest.
    SO = R.MODS['solve']
    NO = R.MODS['norm']
    if dep > SO.MAXDEP:
        raise K.CasSoft(SO.M_CANT)
    ns = []
    best = None
    for r in rs:
        r = NO.normal(r)
        n = SO.nd(r)[0]
        k = None
        for j in range(len(vs)):
            d = A.degree(n, vs[j])
            d = 99 if d < 0 else d
            if d and (k is None or d < k[0]):
                k = (d, j)
        if r == K.ZERO:
            continue
        if k is None:                   # free of every unknown, not zero: no solution
            yield []
            return
        if best is None or k[0] < best[0]:
            best = (k[0], len(ns), k[1])
        ns.append(r)
    if not ns:
        yield [vs]
        return
    i = best[1]
    x = vs[best[2]]
    rest = vs[:best[2]] + vs[best[2] + 1:]
    rr = yield R.scoped(SO.g_eq(ns[i], x, dep + 1, md))
    if rr is None or rr == K.TRUE:
        yield None
        return
    out = []
    for r in rr:
        sub = []
        try:
            for j in range(len(ns)):
                if j != i:
                    sub.append(A.subst(ns[j], x, r))
        except K.CasSoft:
            continue
        ss = yield R.MODS['solvec'].g_elim(tuple(sub), rest, dep + 1, md)
        if ss is None:
            return
        for s in ss:
            try:
                w = A.subst(r, rest, s) if rest else r
            except K.CasSoft:
                continue
            out.append(s[:best[2]] + (w,) + s[best[2]:])
            if len(out) > SO.MAXROOTS:
                raise K.CasSoft(SO.M_MANY)
    yield out
