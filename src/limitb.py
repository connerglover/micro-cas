#@L 2
# limit family: limitb helpers.
import node as K
import alg as A
import parse as P
import run as R

def signval(e):                                                #@L 3
    s = K.csign(e)
    if s or e == K.ZERO:
        return s
    if K.V[e]:
        return None
    try:
        v = A.nrun(A.nprog(e, ()), ())
        if type(v) is complex:
            if v.imag:
                return None
            v = v.real
        return 1 if v > 0 else -1 if v < 0 else 0
    except K.CasSoft:
        return None



def g_lead(f, x, a, side):                                     #@L 2
    s = yield R.MODS['ser'].g_series(f, x, a, R.MODS['lim'].SERORDER, side)
    if s is None or len(s) < 2:
        yield None
        return
    c = s[1]
    if a != K.OO and not K.isninf(a) and side < 0 and s[0] % 2:
        c = K.neg_(c)
    yield (s[0], c)



def g_piece(f, x, a, side):                                    #@L 2
    keys, replacements = [], []
    for n in A.postorder(f):
        t = K.N[n]
        if t[0] not in (K.ABS, K.SIGN, K.FLOOR, K.CEIL) or K.free_of(n, x):
            continue
        u = A.subst(t[1], tuple(keys), tuple(replacements)) if keys else t[1]
        try:
            v = A.subst(u, x, a)
        except K.CasSoft:
            continue
        if v == K.UNDEF or K.V[v]:
            continue
        q = K.N[v]
        if t[0] in (K.ABS, K.SIGN):
            s = signval(v)
            if s == 0:
                lead = yield g_lead(u, x, a, side)
                s = signval(lead[1]) if lead is not None else 0 if K.free_of(u, x) else None
            if s is not None:
                keys.append(n)
                replacements.append(K.neg_(u) if t[0] == K.ABS and s < 0 else u if t[0] == K.ABS else K.num(s))
        elif q[0] == K.NUM and not q[2] and q[3] == 1:
            delta = K.add_([u, K.neg_(v)])
            lead = yield g_lead(delta, x, a, side)
            s = signval(lead[1]) if lead is not None else 0 if delta == K.ZERO else None
            if s is not None:
                adjust = -1 if t[0] == K.FLOOR and s < 0 else 1 if t[0] == K.CEIL and s > 0 else 0
                keys.append(n)
                replacements.append(K.num(q[1] + adjust))
    yield A.subst(f, tuple(keys), tuple(replacements)) if keys else f



def g_direct(f, x, a, side):                                   #@L 2
    values = {}
    for n in A.postorder(f):
        t = K.N[n]
        op = t[0]
        if n == x:
            r = a
        elif K.free_of(n, x):
            r = n
        else:
            r = None
            valid = True
            for c in t[1:]:
                if values.get(c) is None:
                    valid = False
            if op == K.CALL:
                valid = False
            if op == K.ATAN and values.get(t[1]) is None:
                lead = yield g_lead(t[1], x, a, side)
                if lead is not None and lead[0] < 0:
                    sg = signval(lead[1])
                    if sg:
                        r = K.fn_(K.ATAN, K.OO if sg > 0 else K.neg_(K.OO))
            if valid:
                if op == K.MUL:
                    for j in range(2, len(t), 2):
                        b, p = values[t[j]], values[t[j + 1]]
                        bi = b == K.OO or K.isninf(b)
                        pi = p == K.OO or K.isninf(p)
                        if not K.free_of(t[j + 1], x) and ((b in (K.ZERO, K.ONE) and (pi or p == K.ZERO)) or (bi and p == K.ZERO)):
                            valid = False
                if op == K.LN and values[t[1]] == K.ZERO:
                    lead = yield g_lead(t[1], x, a, side)
                    if lead is not None and signval(lead[1]) == 1:
                        r = K.neg_(K.OO)
                    valid = False
                if valid:
                    try:
                        r = A.rebuild(n, values)
                    except K.CasSoft:
                        pass
        values[n] = None if r == K.UNDEF else r
    yield values[f]



def g_fast(f, x, a, side):                                     #@L 2
    r = yield g_direct(f, x, a, side)
    if r is not None:
        yield r
        return
    normalized = R.MODS['norm'].normal(f)
    if normalized != f:
        r = yield g_direct(normalized, x, a, side)
        if r is not None:
            yield r
            return
    lead = yield g_lead(normalized, x, a, side)
    if lead is not None:
        v, c = lead
        if v > 0:
            r = K.ZERO
        elif v == 0:
            r = c
        else:
            s = signval(c)
            if s:
                r = K.OO if s > 0 else K.neg_(K.OO)
    yield r
