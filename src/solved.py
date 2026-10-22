#@L 2
# Compile-unit split: helpers shared by the family through R.MODS (no extra frames).
import node as K
import alg as A
import parse as P
import run as R
NS = 400


def rkey(r):                                                    #@L 3
    # the sort key of a root: (0, re, im, H, r) for a constant; (1, v, 0.0, H, r) for a
    # symbolic root real at a fixed sample point of its symbols (value v); else
    # (2, 0 or 1, 0.0, H, r), the negated-looking one first
    xs = R.MODS['solve'].syms(r)
    vs = []
    for i in range(len(xs)):
        vs.append(0.5 + 0.618 * i)
    try:
        v = complex(A.nrun(A.nprog(r, tuple(xs)), vs))
        if not xs or not (v.imag or A.LEFTREAL[0]):
            return (1 if xs else 0, v.real, v.imag, K.H[r], r)
    except K.CasSoft:
        pass
    return (2, 0 if K.negfirst(r) else 1, 0.0, K.H[r], r)


def nchk(f, xs, vs):                                            #@L 3
    # f vanishes at the (float) values vs of xs within the propagated tolerance (A.ntol, with
    # a relative uncertainty of every leaf, the root included), at a real point
    try:
        ys = []
        for v in vs:
            t = K.N[v]
            ys.append(complex(t[1], t[2]) if t[0] == K.FLT else A.nrun(A.nprog(v, ()), ()))
        p = A.nprog(f, xs)
        r = [0.0] * len(p)
        u = A.nrun(p, ys, r)
        w = A.ntol(p, r, [0.0] * len(p))
    except K.CasSoft:
        return False
    return not A.LEFTREAL[0] and w >= 0.0 and abs(u) <= 4.0 * w + 1e-300


def rform(r):                                                   #@L 6
    # how a root is finished (g_roots, solvec.g_sys): 1 it holds a float (P.approx); 2 it
    # holds pi, e or a function (left as built: pi/6-y, 180-asin(1/3) in degree mode); 0 a
    # rational function of symbols and numeric radicals (normal: b/a, (sqrt(5)-1)/2)
    f = 0
    for m in A.postorder(r):
        t = K.N[m]
        f |= 1 if t[0] == K.FLT else (2 if t[0] == K.CON or t[0] >= K.FN0 else 0)
    return 1 if f & 1 else f


def g_fin(fs, ds, xs, ss):                                      #@L 2
    # the solutions ss (tuples of values of xs) of fs = 0 that pass g_ok (the ds nonzero),
    # each value finished (rform), sorted (rkey), without repeats: a list of tuples. With no
    # i in fs, a solution with a non-real constant value is dropped (real mode, D3).
    NO = R.MODS['norm']
    real = 1
    for m in A.postorder(fs):
        if K.N[m][0] <= K.FLT and K.N[m][2]:
            real = 0
    out = []
    for s in ss:
        z = []
        for w in s:
            f = rform(w)
            z.append(P.approx(w) if f == 1 else (w if f else NO.normal(w)))
        z = tuple(z)
        ok = yield R.scoped(g_ok(fs, ds, xs, z))    # 0 or 1: a region drops its nodes
        k = []
        for w in z:
            k.extend(rkey(w)[:4])
            if real and k[-4] == 0 and abs(k[-2]) > 1e-9 * (1 + abs(k[-3])):
                ok = 0
        if ok and (k, z) not in out:
            out.append((k, z))
    out.sort()
    res = []
    p = None
    for k, z in out:            # a float root found twice (two kernels): once
        if not (p and k[0] == p[0] == 0 and K.N[z[0]][0] == K.FLT and
                abs(k[1] - p[1]) <= 1e-10 * (1 + abs(p[1]))):
            res.append(z)
        p = k
    yield res


def g_ok(fs, ds, xs, vs):                                       #@L 2
    # 1 when the values vs of xs (a tuple) make every f of fs zero and leave every d of ds
    # nonzero, else 0 (11.2). An undefined substitution fails. Float values are checked
    # numerically (nchk). A value with parameters left is generic: only an exact normal form
    # refutes it (a nonzero number for an f, zero for a d). Otherwise g_iszero must not say
    # NO for an f, and must say NO for a d.
    NO = R.MODS['norm']
    NB = R.MODS['normb']
    fl = 0
    for v in vs:
        if K.N[v][0] == K.FLT:
            fl = 1
    n = len(fs)
    for i in range(n + len(ds)):
        f = fs[i] if i < n else ds[i - n]
        try:
            e = A.subst(f, xs, vs)
        except K.CasSoft:
            e = 0
        if not e:
            yield 0
            return
        if fl:
            z = i >= n or nchk(f, xs, vs)
        elif K.V[e]:
            r = NO.normal(e)
            z = r != K.ZERO if i >= n else (r == K.ZERO or K.N[r][0] > K.FLT)
        else:
            v = yield NB.g_iszero(e)
            z = v == A.NO if i >= n else v != A.NO
        if not z:
            yield 0
            return
    yield 1


def nsolve(g, x, lo, hi):                                       #@L 3
    # the real roots of g in x in [lo, hi), ascending floats: sign changes over NS samples,
    # refined by Illinois regula falsi; a root is kept only if g vanishes there within its
    # propagated tolerance (A.ntol), which drops the poles of tan and 1/u. A soft failure
    # when g has no numeric value (an unknown function f(x)) or vanishes on an interval
    try:
        p = A.nprog(g, (x,))
    except K.CasSoft:
        raise K.CasSoft('Cannot solve')
    r = [0.0] * len(p)
    out = []
    a = fa = None
    for i in range(NS + 1):
        if not i & 63 and K.ESC is not None and K.ESC():
            raise K.Cancel()
        b = lo + (hi - lo) * i / NS                                     #@float-ok
        try:
            fb = A.nrun(p, (b,), r)
            if type(fb) is complex or A.LEFTREAL[0]:
                fb = None
        except K.CasSoft:
            fb = None
        if fb == 0.0 and fa == 0.0:     # zero on an interval (floor): no isolated roots
            raise K.CasSoft('Cannot solve')
        z = b if fb == 0.0 else None
        if fb and fa and fa * fb < 0.0:
            u, fu, w, fw = a, fa, b, fb
            for k in range(100):
                z = (u * fw - w * fu) / (fw - fu)                       #@float-ok
                try:
                    v = A.nrun(p, (z,), r)
                except K.CasSoft:
                    v = None
                if type(v) is not float or not v or abs(w - u) <= 1e-15 * (abs(u) + abs(w)):
                    break
                if v * fw < 0.0:
                    u, fu = w, fw
                else:
                    fu *= 0.5
                w, fw = z, v
        if z is not None and z < hi and len(out) <= 24:
            try:
                v = A.nrun(p, (z,), r)
                if abs(v) <= A.ntol(p, r, [0.0] * len(p)):
                    out.append(z)
            except K.CasSoft:
                pass
        a, fa = b, fb
    return out
