#@L 3
# CVRULEB: the rule matcher (DESIGN 9.5), part b of the CVRULE family (4.3): match, check,
# view. A goal stack, a trail of bound slots and choice points; no recursion. Holds no state.
import node as K
import alg as A

MAXSTEP = 400       # goal steps per match (10.7); running out is a failure
# wildcard constraints (the third field of a WILD leaf; parse.W_* and DESIGN 9.2)
ANY = 0
FREE = 1
NUMB = 2
INT = 3
LIN = 4
QUAD = 5
REST = 6
SA = 3              # the slots A, B, C that the binders L and Q write


def view(op, s):                                                #@L 4
    # s seen as an ADD or a MUL (op), so that identity elements act as defaults (9.5): the
    # constant or coefficient id and the flat pair tuple (t1, k1, ...) or (b1, e1, ...)
    t = K.N[s]
    o = t[0]
    if o == op:
        return t[1], t[2:]
    if o <= K.FLT:
        return s, ()
    if op == K.MUL:
        return K.ONE, (s, K.ONE)
    if o == K.MUL and t[1] != K.ONE:            # 3*sin(x) is the term sin(x) times 3
        if len(t) == 4 and t[3] == K.ONE:
            return K.ZERO, (t[2], t[1])
        return K.ZERO, (K.mk((K.MUL, K.ONE) + t[2:]), t[1])
    return K.ZERO, (s, K.ONE)


def check(c, s, env, x, trail):                                 #@L 4
    # does s satisfy the wildcard constraint c (9.2)? LIN and QUAD also bind A, B (and C),
    # on the trail so that backtracking undoes them. FREE without a focus variable: constant.
    if c == ANY or c == REST:
        return True
    t = K.N[s]
    if c == NUMB:
        return t[0] == K.NUM
    if c == INT:
        return t[0] == K.NUM and t[2] == 0 and t[3] == 1
    if c == FREE:
        if not x:
            return not K.V[s]
        return K.free_of(s, x)
    if not x:
        return False
    if c == LIN:
        r = A.linear(s, x)
    else:
        r = A.quadratic(s, x)
    if r is None or r[0] == K.ZERO:
        return False
    for j in range(len(r)):
        v = env[SA + j]
        if v:
            if v != r[j]:
                return False
        else:
            env[SA + j] = r[j]
            trail.append(SA + j)
    return True


def match(p, s, env, x):                                        #@L 3
    # Match the pattern p against the subject s (9.5). env: slot -> bound id (0: unbound),
    # with env[XSLOT] = x set by the caller. True: env holds the bindings. False: env is as
    # it was. ADD and MUL patterns match AC: the subject is viewed as the pattern's op, pattern
    # pairs take distinct subject pairs (concrete heads first), a REST unit pair takes the
    # leftovers with the constant or coefficient. A NUMB or INT wildcard base of exponent 1 in
    # a MUL pattern binds the coefficient (N*sin(U) matches 3*sin(x) with N=3), also as a term
    # k*N*f of an ADD pattern, where N binds the term's coefficient over k (N*ln(U)+R matches
    # 2*ln(x)+1 with N=2; -N*sinh(U)^2 matches -2*sinh(x)^2 with N=2). Goals: (pattern,
    # subject), (pattern, term, coefficient) and AC goals (op, pattern pairs, subject pairs,
    # next, rest, const).
    N = K.N
    goals = [(p, s)]
    trail = []
    cps = []
    steps = 0
    while True:
        steps += 1
        ok = True
        if steps > MAXSTEP:
            ok = False
            cps = []
        elif not goals:
            return True
        else:
            g = goals.pop()
            if len(g) < 4:                                      # a plain goal
                pp = g[0]
                ss = g[1]
                tp = N[pp]
                op = tp[0]
                if pp == ss:
                    pass
                elif op == K.WILD:
                    sl = tp[1]
                    if env[sl]:
                        ok = env[sl] == ss
                    elif check(tp[2], ss, env, x, trail):
                        env[sl] = ss
                        trail.append(sl)
                    else:
                        ok = False
                elif op == K.ADD or op == K.MUL:
                    if len(g) == 3:                             # a term with its coefficient
                        c = g[2]
                        sp = view(op, ss)[1]
                    else:
                        c, sp = view(op, ss)
                    pc = []                                     # concrete heads first
                    pw = []
                    rest = -1
                    cw = 0
                    for j in range(2, len(tp), 2):
                        b = tp[j]
                        w = N[b]
                        if w[0] != K.WILD:
                            pc.append(b)
                            pc.append(tp[j + 1])
                        elif tp[j + 1] == K.ONE and w[2] == REST:
                            rest = w[1]
                        elif tp[j + 1] == K.ONE and op == K.MUL and not cw and (
                                w[2] == NUMB or w[2] == INT):
                            cw = b
                        else:
                            pw.append(b)
                            pw.append(tp[j + 1])
                    pps = tuple(pc + pw)
                    k = tp[1]
                    if cw:
                        ok = k == K.ONE
                        k = cw
                    if not ok:
                        pass
                    elif rest < 0:
                        goals.append((op, pps, sp, 0, -1, 0))
                        goals.append((k, c))
                    elif cw:
                        goals.append((op, pps, sp, 0, rest, K.ONE))
                        goals.append((cw, c))
                    elif k == (K.ZERO if op == K.ADD else K.ONE):
                        goals.append((op, pps, sp, 0, rest, c))
                    else:
                        ok = False
                elif op >= K.COMP:                              # a fixed-arity node
                    ts = N[ss]
                    if ts[0] != op or len(ts) != len(tp):
                        ok = False
                    else:
                        for j in range(len(tp) - 1, 0, -1):
                            goals.append((tp[j], ts[j]))
                else:
                    ok = False                                  # different leaves
            else:                                               # an AC goal
                op, pps, sps, j0, rest, c = g
                if not pps:
                    if rest < 0:
                        ok = not sps
                    else:                                       # rebuild the leftovers
                        if op == K.ADD:
                            ts = [c]
                            for j in range(0, len(sps), 2):
                                ts.append(K.mul_(sps[j + 1], [(sps[j], K.ONE)]))
                            r = K.add_(ts)
                        else:
                            ts = []
                            for j in range(0, len(sps), 2):
                                ts.append((sps[j], sps[j + 1]))
                            r = K.mul_(c, ts)
                        if env[rest]:
                            ok = env[rest] == r
                        else:
                            env[rest] = r
                            trail.append(rest)
                else:
                    pb = pps[0]
                    pe = pps[1]
                    tb = N[pb]
                    hb = tb[0]
                    cm = 0                                      # an ADD term k*N*f: N takes
                    if op == K.ADD and hb == K.MUL:             # the coefficient over k
                        for j in range(2, len(tb), 2):
                            w = N[tb[j]]
                            if w[0] == K.WILD and tb[j + 1] == K.ONE and (
                                    w[2] == NUMB or w[2] == INT):
                                cm = 1
                    j = j0
                    if hb != K.WILD and hb != K.ADD and hb != K.MUL:
                        while j < len(sps) and N[sps[j]][0] != hb:
                            j += 2
                    if j >= len(sps):
                        ok = False
                    else:                                       # try pair j; remember j+2
                        cps.append((tuple(goals), len(trail), (op, pps, sps, j + 2, rest, c)))
                        goals.append((op, pps[2:], sps[:j] + sps[j + 2:], 0, rest, c))
                        if cm:
                            k = sps[j + 1]
                            if pe != K.ONE:
                                k = K.mk(K.nmul(N[k], K.ninv(N[pe])))
                            goals.append((pb, sps[j], k))
                        else:
                            goals.append((pe, sps[j + 1]))
                            goals.append((pb, sps[j]))
        if not ok:
            if not cps:
                while trail:
                    env[trail.pop()] = 0
                return False
            gl, tl, acg = cps.pop()
            while len(trail) > tl:
                env[trail.pop()] = 0
            goals = list(gl)
            goals.append(acg)
