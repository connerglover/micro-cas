#@L 2
# Compile-unit split: helpers shared by the family through R.MODS (no extra frames).
import node as K
import nodeb as KB
import alg as A
import parse as P
import run as R


def kmono(k, ks):                                               #@L 7
    # the exponent tuple of kernel k (1 in its slot), giving k the first free slot if new
    i = 0
    while ks[i] and ks[i] != k:
        i += 1
    ks[i] = k
    u = [0] * len(ks)
    u[i] = 1
    return tuple(u)


def tonode(n, d, ks, ex):                                       #@L 4
    # the node of the fraction n/d over the kernels ks. ex (expand): d is a constant that
    # divides every term. Else the common monomial, the gcd (Kronecker substitution, checked by
    # exact division; the content only above R.MODS['norm'].KRONMAX) and the contents are cancelled, giving
    # k*N/D with N, D primitive; the constructors normalize the signs.
    if not n:
        return K.ZERO
    nv = len(ks)
    PC = R.MODS['polyc']
    if ex:
        for z in d:                                             #@unordered-ok (one term)
            cn = cd = d[z]
    else:
        a = PC.mmono(n, nv)
        b = PC.mmono(d, nv)
        u = []
        v = []
        for i in range(nv):
            u.append(-a[i])
            v.append(-b[i])
        n = PC.mmul(n, {tuple(u): 1})
        d = PC.mmul(d, {tuple(v): 1})
        u = PC.mdeg(n, nv)
        v = PC.mdeg(d, nv)
        D = []
        s = 1
        for i in range(nv):
            g = a[i] if a[i] < b[i] else b[i]
            a[i] -= g
            b[i] -= g
            D.append((u[i] if u[i] > v[i] else v[i]) + 1)
            s *= D[i]
        if s <= R.MODS['norm'].KRONMAX:
            g = R.MODS['poly'].pgcd(PC.mkron(n, D), PC.mkron(d, D))
            if len(g) > 1:
                g = PC.munkron(g, D)
                u = PC.mdivex(n, g)
                v = PC.mdivex(d, g)
                if u is not None and v is not None:
                    n = u
                    d = v
        n = PC.mmul(n, {tuple(a): 1})
        d = PC.mmul(d, {tuple(b): 1})
        cn = PC.mcont(n)
        cd = PC.mcont(d)
    out = []
    for p, q in ((n, cn), (d, cd)):
        ts = []
        for z in p:                                             #@unordered-ok (add_ sorts)
            ps = []
            for i in range(nv):
                if z[i]:
                    ps.append((ks[i], K.num(z[i])))
            v = K.nnorm(p[z], 0, q)
            if v == K.Q1 and len(ps) == 1 and ps[0][1] == K.ONE:
                ts.append(ps[0][0])                             # a bare kernel (TRUE, a list)
            else:
                ts.append(K.mul_(v, ps))
        out.append(ts[0] if len(ts) == 1 else K.add_(ts))
    if out[1] == K.ONE and cn == cd:
        return out[0]
    return K.mul_(K.nnorm(cn, 0, cd), [(out[0], K.ONE), (out[1], K.MONE)])


def kinds(e):                                                   #@L 6
    # bits: 1 e has sin..cot; 2 e is not a rational function of symbols (a function, a
    # constant, a non-integer power); 4 e has a negative power
    f = 0
    for m in A.postorder(e):
        t = K.N[m]
        op = t[0]
        if K.SIN <= op <= K.COT:
            f |= 1
        if op == K.MUL:
            for j in range(3, len(t), 2):
                w = K.N[t[j]]
                if K.HUGE and KB.huge(t[j - 1], t[j]):
                    continue                    # a power too large to fold is a number (5.3)
                if w[0] or w[2] or w[3] != 1:
                    f |= 2
                elif w[1] < 0:
                    f |= 4
        elif op != K.NUM and op != K.SYM and op != K.ADD:
            f |= 2
    return f


def dden(r):                                                    #@L 7
    # the sum D of a normal form k*N/D (or k*N*D^-1*...), else 0
    t = K.N[r]
    D = 0
    for j in range(2, len(t), 2):
        if t[0] == K.MUL and t[j + 1] == K.MONE and K.N[t[j]][0] == K.ADD:
            D = t[j]
    return D


def dfac(r):                                                    #@L 3
    # r = k*N/D (a normal form: D primitive over Z) with D factored over Q (Yun's square-free
    # parts, their rational roots) when D is a polynomial in one kernel u and the factored
    # form is not bigger (14, FlowCE one fraction); else r
    D = dden(r)
    u = K.N[D][2] if D else 0
    if u and K.N[u][0] == K.MUL:
        u = K.N[u][2]
    n = A.degree(D, u) if D else 0
    cs = A.pco(D, u, n) if n > 0 else None
    if cs is None:
        return r
    a = []
    for c in cs:
        a.append(0)
        for z, w in c:
            if z != K.ONE or w[0] or w[2] or w[3] != 1:
                return r
            a[-1] += w[1]
    c, fs = R.MODS['poly'].yun(a)
    ps = []
    for f, m in fs:
        rs, f, ok = R.MODS['polyb'].ratroots(f)
        for p, q, k in rs:
            ps.append((K.add_([K.mul_(K.num(q), [(u, K.ONE)]), K.num(-p)]), K.num(k * m)))
        ts = []
        for i in range(len(f)):
            ts.append(K.mul_(K.num(f[i]), [(u, K.num(i))]))
        ps.append((K.add_(ts), K.num(m)))
    v = K.mul_(K.ONE, [(r, K.ONE), (D, K.ONE), (K.mul_(K.num(c), ps), K.MONE)])
    return v if A.size(v, True) <= A.size(r, True) else r
