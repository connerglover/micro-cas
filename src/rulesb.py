#@L 3
# CVRULEB: the rule matcher (DESIGN 9.5), part b of the CVRULE family (4.3). A goal stack, a
# trail of bound slots and choice points; no recursion. Holds no state. The wildcard check is
# in part a (R.MODS['rules'].check).
import node as K
import parse as P
import run as R

MAXSTEP = 400       # goal steps per match (10.7); running out is a failure


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


def match(p, s, env, x, alt=0):                                 #@L 3
    # Match the pattern p against the subject s (9.5). env: slot -> bound id (0: unbound),
    # with env[XSLOT] = x set by the caller. True: env holds the bindings of solution number
    # alt (0: the first; the search order is fixed, so the rewriter can ask for the next
    # binding when a guard fails). False: env is as it was.
    # ADD and MUL patterns match AC: the subject is viewed as the pattern's op, pattern pairs
    # take distinct subject pairs (concrete heads first), a REST unit pair takes the leftovers
    # with the constant or coefficient. A NUMB or INT wildcard factor of exponent 1 in a MUL
    # pattern binds the coefficient (N*sin(U) matches 3*sin(x) with N=3). A MUL term of an
    # ADD pattern meets a subject term with the subject's coefficient over the pattern's
    # (N*ln(U)+R matches 2*ln(x)+1 with N=2; -N*sinh(U)^2 matches -2*sinh(x)^2 with N=2).
    # Goals: (pattern, subject), (pattern, term, coefficient) and AC goals (op, pattern pairs,
    # subject pairs, next pair, rest slot, constant); choice points (goals, trail length, AC
    # goal to resume); the bottom one fails.
    N = K.N
    RA = R.MODS['rules']
    goals = [(p, s)]
    trail = []
    cps = [((), 0, None)]
    steps = 0
    while True:
        steps += 1
        ok = True
        if steps > MAXSTEP:
            ok = False
            del cps[1:]
        elif not goals:
            if not alt:
                return True
            alt -= 1                                            # skip this solution
            ok = False
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
                    else:
                        ok = RA.check(tp[2], ss, env, x, trail)
                        if ok:
                            env[sl] = ss
                            trail.append(sl)
                elif op == K.ADD or op == K.MUL:
                    c, sp = view(op, ss)
                    if len(g) == 3:                             # a term: its coefficient
                        c = g[2]
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
                        elif tp[j + 1] == K.ONE and w[2] == P.W_REST:
                            rest = w[1]
                        elif tp[j + 1] == K.ONE and op == K.MUL and not cw and (
                                w[2] == P.W_NUMB or w[2] == P.W_INT):
                            cw = b
                        else:
                            pw.append(b)
                            pw.append(tp[j + 1])
                    k = tp[1]
                    rc = c                                      # what REST takes
                    if cw:                                      # N binds the coefficient
                        ok = k == K.ONE
                        k = cw
                        rc = K.ONE
                    elif rest >= 0:                             # REST takes the constant
                        ok = k == (K.ZERO if op == K.ADD else K.ONE)
                        k = c
                    goals.append((op, tuple(pc + pw), sp, 0, rest, rc))
                    goals.append((k, c))
                elif op >= K.COMP and N[ss][0] == op and len(N[ss]) == len(tp):
                    ts = N[ss]                                  # a fixed-arity node
                    for j in range(len(tp) - 1, 0, -1):
                        goals.append((tp[j], ts[j]))
                else:
                    ok = False                                  # different leaves or heads
            else:                                               # an AC goal
                op, pps, sps, j, rest, c = g
                if not pps:
                    if rest < 0:
                        ok = not sps
                    else:                                       # REST: rebuild the leftovers
                        ts = [c]
                        for j in range(0, len(sps), 2):
                            ts.append(K.mul_(sps[j + 1], [(sps[j], K.ONE)]) if op == K.ADD
                                      else (sps[j], sps[j + 1]))
                        r = K.add_(ts) if op == K.ADD else K.mul_(c, ts[1:])
                        if env[rest]:
                            ok = env[rest] == r
                        else:
                            env[rest] = r
                            trail.append(rest)
                else:
                    pb = pps[0]
                    pe = pps[1]
                    hb = N[pb][0]
                    if hb != K.WILD and hb != K.ADD and hb != K.MUL:
                        while j < len(sps) and N[sps[j]][0] != hb:
                            j += 2
                    if j >= len(sps):
                        ok = False
                    else:                                       # try pair j; remember j+2
                        cps.append((tuple(goals), len(trail), (op, pps, sps, j + 2, rest, c)))
                        goals.append((op, pps[2:], sps[:j] + sps[j + 2:], 0, rest, c))
                        if op == K.ADD and hb == K.MUL:         # coefficient over pattern's
                            k = sps[j + 1]
                            if pe != K.ONE:
                                k = K.mk(K.nmul(N[k], K.ninv(N[pe])))
                            goals.append((pb, sps[j], k))
                        else:
                            goals.append((pe, sps[j + 1]))
                            goals.append((pb, sps[j]))
        if not ok:
            gl, tl, acg = cps.pop()
            while len(trail) > tl:
                env[trail.pop()] = 0
            if acg is None:
                return False
            goals = list(gl)
            goals.append(acg)
