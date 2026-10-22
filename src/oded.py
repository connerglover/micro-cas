#@L 2
# ode helper family.
import node as K
import alg as A
import run as R

def g_conditions(sol, conds, x, y, constants):                  #@L 2
    NO = R.need('norm')
    DF = R.need('diff')
    t = K.N[sol]
    explicit = t[0] == K.EQ and t[1] == y
    value = t[2] if explicit else None
    rows = []
    checks = []
    nv = len(constants)
    width = nv + 1
    for cond in conds:
        ct = K.N[cond]
        if ct[0] != K.EQ:
            raise K.CasError('Expected initial conditions y(a)=b')
        lhs, rhs = K.N[ct[1]], ct[2]
        if lhs[0] != K.CALL or len(lhs) != 3 or K.N[lhs[1]][0] != K.SYM:
            raise K.CasError('Expected initial conditions y(a)=b')
        name = K.N[lhs[1]][1]
        base = K.N[y][1]
        if name.rstrip("'") != base or len(name) - len(base) > 2:
            raise K.CasError('Invalid initial condition')
        order = len(name) - len(base)
        if not K.free_of(lhs[2], x) or not K.free_of(rhs, x):
            raise K.CasError('Initial conditions must be constant')
        try:
            if explicit:
                ev = value
                for j in range(order):
                    ev = yield DF.g_deriv(ev, x)
                ev = NO.normal(K.add_([A.subst(ev, x, lhs[2]), K.neg_(rhs)]))
            elif order == 0:
                ev = K.add_([A.subst(t[1], y, rhs), K.neg_(t[2])])
                ev = NO.normal(A.subst(ev, x, lhs[2]))
            else:
                yield None
                return
        except K.CasSoft:
            yield K.mk((K.LST,))
            return
        checks.append(ev)
        et = K.N[ev]
        if et[0] == K.MUL:
            ps = []
            for j in range(2, len(et), 2):
                exponent = K.N[et[j + 1]]
                if exponent[0] != K.NUM or exponent[2] or exponent[1] >= 0:
                    ps.append((et[j], et[j + 1]))
            ev = K.mul_(et[1], ps)
        ev = NO.normal(ev, 1)
        for c in constants:
            lin = A.linear(ev, c)
            if lin is None:
                yield None
                return
            rows.append(lin[0])
            ev = lin[1]
        rows.append(K.neg_(ev))
    nr = len(conds)
    pivots = []
    row = 0
    for col in range(nv):
        at = row
        while at < nr and rows[at*width + col] == K.ZERO:
            at += 1
        if at == nr:
            continue
        for j in range(width):
            rows[row*width+j], rows[at*width+j] = rows[at*width+j], rows[row*width+j]
        pivot = rows[row*width + col]
        for j in range(width):
            rows[row*width+j] = NO.normal(R.MODS['ode'].div(rows[row*width+j], pivot))
        for i in range(nr):
            if i == row:
                continue
            coeff = rows[i*width+col]
            for j in range(width):
                rows[i*width+j] = NO.normal(K.add_([rows[i*width+j], K.neg_(R.MODS['ode'].mul(coeff, rows[row*width+j]))]))
        pivots.append(col)
        row += 1
    for i in range(nr):
        empty = True
        for j in range(nv):
            if rows[i*width+j] != K.ZERO:
                empty = False
                break
        if empty and rows[i*width+nv] != K.ZERO:
            yield K.mk((K.LST,))
            return
    values = list(constants)
    for i in range(len(pivots)):
        ts = [rows[i*width+nv]]
        for j in range(nv):
            if j not in pivots:
                ts.append(K.neg_(R.MODS['ode'].mul(rows[i*width+j], constants[j])))
        values[pivots[i]] = K.add_(ts)
    try:
        result = A.subst(sol, tuple(constants), tuple(values))
        for check in checks:
            delta = NO.normal(A.subst(check, tuple(constants), tuple(values)))
            ok = yield R.MODS['normb'].g_iszero(delta)
            if ok == A.NO:
                result = K.mk((K.LST,))
                break
    except K.CasSoft:
        result = K.mk((K.LST,))
    yield result
