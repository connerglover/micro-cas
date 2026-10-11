#@L 2
# CVNORM part b: the zero test g_iszero (8.6), simplify and the default result path (8.7), and
# the factored denominator of the one-fraction form (14). A simplify candidate that would win
# is first compared with the input by the numeric probe; a mismatch is a bug, counted in
# SIMPBUG (every test asserts SIMPBUG == 0).
import node as K
import alg as A
import run as R

YES = 2             # g_iszero: exactly 0 (NO and LIKELY are A.NO = 0 and A.LIKELY = 1)
SIMPBUG = 0
BUD = 64            # rule fires per rewrite pass
AUTOMAX = 100       # the default path leaves results of this size or more alone (FlowCE)
RS = ('', '', 'trigsin', 'trigcos', 'tlin', 'lncollect', 'expmerge')


def g_iszero(e):                                                #@L 2
    # 8.6: YES when e is exactly 0, A.NO when it is not, A.LIKELY when only the numeric probe
    # (real points) says 0 or it finds no usable point. Steps: expand, ln of rationals over
    # primes, sin and cos to the basis ZBASIS, normal; a nonzero rational function of symbols
    # is NO; else the probe. Nothing it builds survives.
    NO = R.MODS['norm']
    m0 = K.NN
    t = K.N[e]
    v = A.LIKELY
    if t[0] <= K.CON:                                   # a number, a symbol, pi, oo, ...
        v = A.NO if t[0] == K.CON or t[1] or t[2] else YES
    else:
        try:
            r = R.MODS['ident'].lnsplit(NO.normal(e, 1))
        except K.CasError:
            r = e
        if R.MODS['normc'].kinds(r) & 1:
            x = yield R.MODS['rules'].g_rewrite(r, 'zbasis', 0, BUD)
            if x is not None:
                r = x
        r = NO.normal(r)
        if r == K.ZERO:
            v = YES
        elif not R.MODS['normc'].kinds(r) & 2 or A.nprobe(e) == A.NO:
            v = A.NO
    K.keep(m0, None)
    yield v


def g_simp(e, full):                                            #@L 2
    # simplify (full: the command) or the default result path (8.7). Inside lists and
    # relations (a solution list) each expression is simplified on its own, then rebuilt.
    x = {}
    for m in A.postorder(e):
        t = K.N[m]
        if t[0] == K.LST or K.EQ <= t[0] <= K.LE:
            for j in range(1, len(t)):
                o = K.N[t[j]][0]
                if t[j] not in x and o != K.LST and not K.EQ <= o <= K.LE:
                    x[t[j]] = yield g_one(t[j], full)
            x[m] = A.rebuild(m, x)
    if e not in x:
        x[e] = yield g_one(e, full)
    yield x[e]


def g_one(e, full):                                             #@L 2
    # The smallest candidate by A.size(., True), ties to e (8.7). A candidate wins only after
    # A.nprobe(e, candidate) agrees: NO counts a SIMPBUG, no usable point discards it.
    # 0 normal with the denominator factored, or for a product of polynomials the bases
    #   normalized (keep_factored); 1 a sum's rational terms collected (collect_rational);
    # with sin..cot: 2 trigsin, 3 trigcos (each also then normal), 4 tlin with expand between
    #   passes; explicit simplify only: 5 lncollect, 6 expmerge, 7 denesting, 8 a denominator
    #   a+b*sqrt(n) rationalized.
    global SIMPBUG
    NO = R.MODS['norm']
    RU = R.MODS['rules']
    t = K.N[e]
    op = t[0]
    if (op != K.ADD and op != K.MUL and op < K.FN0) or (not full and A.size(e) >= AUTOMAX):
        yield e
        return
    m0 = K.NN
    best = e
    bs = A.size(e, True)
    f = R.MODS['normc'].kinds(e)
    for k in range(9):
        r = None
        if 1 < k < 7 and (f & 1 if k < 5 else full):
            r = yield RU.g_rewrite(e, RS[k], 0, BUD)
            for i in range(2 if k == 4 else 0):             # tlin: expand between passes
                if r is not None:
                    try:
                        r = NO.normal(r, 1)
                    except (K.CasSoft, K.CasError):
                        pass
                    r = yield RU.g_rewrite(r, RS[k], 0, BUD)
        cs = [r]
        try:
            if k == 0:
                x = []
                for j in range(2, len(t), 2):
                    if op == K.MUL and not f & 6:
                        x.append((NO.normal(t[j]), t[j + 1]))
                cs = [K.mul_(t[1], x) if len(x) > 1 else R.MODS['normc'].dfac(NO.normal(e))]
            elif k == 1 and op == K.ADD:
                x = [t[1]]
                y = []
                for j in range(2, len(t), 2):
                    (y if R.MODS['normc'].kinds(t[j]) & 2 else x).append(K.mul_(t[j + 1], [(t[j], K.ONE)]))
                if len(x) > 2 and y:
                    cs = [K.add_([R.MODS['normc'].dfac(NO.normal(K.add_(x)))] + y)]
            elif r is not None and k < 4:
                cs.append(NO.normal(r))
            elif k == 7 and full:
                cs = [R.MODS['ident'].denest(e)]
            elif k == 8 and full:                           # D = a+b*sqrt(n): times a-b*sqrt(n)
                r = NO.normal(e)
                x = R.MODS['normc'].dden(r)
                if x:
                    D = K.N[x]
                    y = [D[1]]
                    for j in range(2, len(D), 2):
                        c = K.N[D[j + 1]]
                        y.append(K.mul_(K.nneg(c) if R.MODS['normc'].kinds(D[j]) & 2 else c, [(D[j], K.ONE)]))
                    y = K.add_(y)
                    cs = [NO.normal(K.mul_(K.ONE, [(r, K.ONE), (x, K.ONE), (y, K.ONE), (
                        NO.normal(K.mul_(K.ONE, [(x, K.ONE), (y, K.ONE)]), 1), K.MONE)]))]
        except (K.CasSoft, K.CasError):
            cs = []
        for r in cs:
            if r is not None and r != best:
                s = A.size(r, True)
                if s < bs:
                    v = A.nprobe(e, r)
                    if v == A.LIKELY:
                        best = r
                        bs = s
                    elif v == A.NO:
                        SIMPBUG += 1
        best = K.keep(m0, best)
    yield best
