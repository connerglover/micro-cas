"""T1.8 algorithm core (CVALG): postorder, subst, the shape predicates, size, simplify_candidate,
the numeric evaluator nprog/nrun/nev (real, complex, the odd-root rule) and the numeric probe
(DESIGN 6.6, 8.3, 8.6, 8.7, 11, 17.1, 21.2).

Oracles: ``test_node.ev`` (an independent cmath evaluator of a node, same conventions), the
Python ``math``/``cmath`` modules and SymPy/mpmath for the branch conventions of the complex
functions (asin(2) = pi/2 - i*ln(2+sqrt(3)), odd on the real axis, as SymPy and giac).
"""
import cmath
import math
import random

import pytest

import gen
import node as K
import alg as A
from test_node import q, pw, pwe, prod, sm, sub, div, pimul, sqrt, ev, close


def x_():
    return K.sym('x')


def y_():
    return K.sym('y')


def fn(op, a):
    return K.fn_(op, a)


def reach(e):
    """The reachable set, test side (recursion is fine here)."""
    out = set()
    st = [e]
    while st:
        i = st.pop()
        if i in out:
            continue
        out.add(i)
        t = K.N[i]
        if t[0] >= K.COMP:
            st.extend(t[1:])
    return out


def cvalue(v):
    return complex(v)


# -- API (21.2) ----------------------------------------------------------------------------------

API = ('postorder subst rebuild linear quadratic split_const degree size simplify_candidate '
       'nprog nrun nev ntol nprobe LEFTREAL NO LIKELY UNKNOWN TOL P_CONST P_VAR P_ADD P_MUL '
       'P_POW P_FN FNUM FCPX cpow').split()


def test_frozen_api_names_exist():
    assert [n for n in API if not hasattr(A, n)] == []
    assert (A.NO, A.LIKELY, A.UNKNOWN) == (0, 1, -1)
    assert len(A.FNUM) == len(A.FCPX) == K.FACT - K.FN0 + 1


# -- postorder -----------------------------------------------------------------------------------

def test_postorder_leaves_and_small_trees():
    x = x_()
    assert A.postorder(K.ONE) == [K.ONE]
    assert A.postorder(x) == [x]
    e = sm(pw(x, 2), q(3))                                  # x^2 + 3
    p = A.postorder(e)
    assert p == sorted(reach(e)) and p[-1] == e
    assert K.ONE in p and K.TWO in p                         # preallocated ids are included


@pytest.mark.parametrize('seed', range(6))
def test_postorder_is_sorted_complete_and_children_first(seed):
    g = gen.Gen(seed)
    for _ in range(30):
        try:
            e = gen.build(g.tree(4), K)
        except (K.Undefined, K.CasError):
            continue
        p = A.postorder(e)
        assert p == sorted(set(p))                          # ascending, no duplicates
        assert set(p) == reach(e)
        pos = {n: i for i, n in enumerate(p)}
        for n in p:
            t = K.N[n]
            if t[0] >= K.COMP:
                assert all(pos[c] < pos[n] for c in t[1:])


def test_postorder_of_a_tuple_of_roots():
    x, y = x_(), y_()
    a = fn(K.SIN, x)
    b = sm(y, q(2))
    assert A.postorder((a, b)) == sorted(reach(a) | reach(b))


# -- subst ---------------------------------------------------------------------------------------

def test_subst_matches_a_direct_build():
    x, y = x_(), y_()
    s = sm(y, q(1))
    e = sm(pw(x, 2), prod(q(2), x))                          # x^2 + 2x
    assert A.subst(e, x, s) == sm(pw(s, 2), prod(q(2), s))   # (y+1)^2 + 2y + 2
    k = fn(K.SIN, x)                                         # a kernel: sin(x)^2 + sin(x)
    t = K.sym('t')
    assert A.subst(sm(pw(k, 2), k), k, t) == sm(pw(t, 2), t)


def test_subst_values_special_values_and_errors():
    x, y = x_(), y_()
    assert A.subst(fn(K.SIN, x), x, pimul(1, 6)) == K.HALF
    assert A.subst(sm(pw(x, 2), q(-4)), x, q(2)) == K.ZERO
    assert A.subst(div(q(1), x), x, K.OO) == K.ZERO                # 1/oo = 0 (6.3)
    with pytest.raises(K.Undefined):
        A.subst(div(q(1), x), x, K.ZERO)
    e = sm(x, fn(K.COS, y))
    assert A.subst(e, x, q(5)) == sm(q(5), fn(K.COS, y))
    assert A.subst(e, K.sym('z'), q(5)) == e                        # free: the same id
    assert A.subst(K.ONE, x, y) == K.ONE


def test_subst_simultaneous_swap():
    x, y = x_(), y_()
    e = sub(x, prod(q(2), y))
    assert A.subst(e, (x, y), (y, x)) == sub(y, prod(q(2), x))


def test_subst_relations_lists_calls_and_hold():
    x, y = x_(), y_()
    assert A.subst(K.rel_(K.EQ, x, q(3)), x, q(3)) == K.TRUE
    assert A.subst(K.rel_(K.LT, x, q(3)), x, q(1)) == K.TRUE
    assert A.subst(K.rel_(K.GT, x, q(3)), x, y) == K.rel_(K.GT, y, q(3))
    lst = K.mk((K.LST, x, sm(x, q(1))))
    assert A.subst(lst, x, q(2)) == K.mk((K.LST, q(2), q(3)))
    f = K.sym('f')
    c = K.mk((K.CALL, f, x))
    assert A.subst(c, f, y) == c                                    # the head is a name
    assert A.subst(c, x, y) == K.mk((K.CALL, f, y))
    m = K.mk((K.MUL, K.ONE, q(2), q(3), q(3), q(2), q(5), K.ONE))   # factor(360) (11.2)
    h = K.mk((K.HOLD, m))
    assert A.subst(K.mk((K.LST, h, x)), x, q(1)) == K.mk((K.LST, h, K.ONE))
    assert A.subst(h, q(5), q(7)) == q(504)                          # a changed HOLD folds


def test_rebuild_returns_the_node_when_nothing_changed():
    x, y = x_(), y_()
    e = sm(prod(q(3), x, fn(K.SIN, y)), q(1))
    for n in A.postorder(e):
        assert A.rebuild(n, {}) == n


@pytest.mark.parametrize('seed', range(8))
def test_subst_agrees_numerically(seed):
    g = gen.Gen(seed, syms=('x', 'y'), consts=('pi', 'e'))
    rng = random.Random(seed)
    x, y = x_(), y_()
    done = 0
    for _ in range(60):
        try:
            e = gen.build(g.tree(3), K)
        except (K.Undefined, K.CasError):
            continue
        vy = sm(prod(q(rng.randint(1, 4)), x), q(rng.randint(-3, 3), rng.randint(1, 3)))
        try:
            s = A.subst(e, y, vy)
        except K.Undefined:
            continue
        for _ in range(3):
            px = rng.uniform(0.3, 2.5) * rng.choice((1, -1))
            try:
                want = ev(e, {'x': px, 'y': ev(vy, {'x': px})})
                got = ev(s, {'x': px})
            except (ZeroDivisionError, ValueError, OverflowError):
                continue
            if abs(want.imag) > 1e-9 * max(1.0, abs(want)) or abs(want) > 1e8:
                continue                                        # policy: real points only
            assert close(got, want, 1e-7), (A_text(e), px)
            done += 1
    assert done > 20


def A_text(e):
    t = K.N[e]
    if t[0] < K.COMP:
        return repr(t)
    return '(%d %s)' % (t[0], ' '.join(A_text(c) for c in t[1:]))


# -- linear, quadratic ---------------------------------------------------------------------------

def lin_cases():
    x, y, a, b = x_(), y_(), K.sym('a'), K.sym('b')
    s = sm(x, q(1))
    return [
        (x, (K.ONE, K.ZERO)),
        (q(3), (K.ZERO, q(3))),
        (y, (K.ZERO, y)),
        (sm(prod(q(2), x), q(1)), (q(2), q(1))),
        (sub(div(x, q(2)), q(3)), (q(1, 2), q(-3))),
        (sm(prod(a, x), b), (a, b)),
        (sm(prod(K.PI, x), pimul(1, 2)), (K.PI, pimul(1, 2))),
        (prod(q(2), s), (q(2), q(2))),
        (K.neg_(s), (q(-1), q(-1))),
        (sm(prod(x, y), prod(q(2), y)), (y, prod(q(2), y))),
        (prod(y, s), (y, y)),
        (prod(q(3), y, sm(prod(q(2), x), q(1))), (prod(q(6), y), prod(q(3), y))),
        (div(sm(x, fn(K.SIN, y)), q(3)), (q(1, 3), div(fn(K.SIN, y), q(3)))),
        (prod(pwe(q(2), y), x), (pwe(q(2), y), K.ZERO)),
        (sm(x, prod(x, pwe(K.E, y))), (sm(q(1), pwe(K.E, y)), K.ZERO)),
        (sm(prod(K.flt(0.5), x), K.flt(1.25)), (K.flt(0.5), K.flt(1.25))),
    ]


def test_linear_cases():
    x = x_()
    for e, want in lin_cases():
        assert A.linear(e, x) == want, A_text(e)


def test_linear_rejects_what_is_not_linear():
    x, y, z = x_(), y_(), K.sym('z')
    for e in (pw(x, 2), fn(K.SIN, x), div(q(1), x), pwe(K.E, x), sqrt(x), fn(K.ABS, x),
              pwe(x, y), prod(x, sm(x, q(1))), K.rel_(K.EQ, x, q(1)),
              prod(y, sm(x, z))):                      # the last: y*z needs mul_ (notes)
        assert A.linear(e, x) is None, A_text(e)


def test_linear_in_a_kernel_and_in_y_prime():
    x = x_()
    k = fn(K.SIN, x)
    assert A.linear(sm(prod(q(3), k), x), k) == (q(3), x)
    yp = K.sym("y'")
    y = y_()
    e = sm(yp, prod(q(2), x, y))                               # y' + 2xy
    assert A.linear(e, yp) == (K.ONE, prod(q(2), x, y))
    assert A.linear(e, y) == (prod(q(2), x), yp)


@pytest.mark.parametrize('seed', range(6))
def test_linear_recovers_random_coefficients(seed):
    g = gen.Gen(seed, syms=('y', 'z'), consts=('pi', 'e'))
    x = x_()
    n = 0
    for _ in range(40):
        try:
            a = gen.build(g.tree(2), K)
            b = gen.build(g.tree(2), K)
            e = K.add_([K.mul_(K.ONE, [(a, K.ONE), (x, K.ONE)]), b])
        except (K.Undefined, K.CasError):
            continue
        if K.N[a][0] == K.CON and a in (K.OO, K.UNDEF) or b in (K.OO, K.UNDEF):
            continue
        r = A.linear(e, x)
        assert r is not None, A_text(e)
        ra, rb = r
        assert K.free_of(ra, x) and K.free_of(rb, x)
        for _ in range(2):
            env = {'y': random.Random(n).uniform(0.4, 2.0), 'z': random.Random(n + 7).uniform(0.4, 2.0)}
            n += 1
            try:
                want = (ev(a, env), ev(b, env))
            except (ZeroDivisionError, ValueError, OverflowError):
                continue
            assert close(ev(ra, env), want[0], 1e-8) and close(ev(rb, env), want[1], 1e-8)


def quad_cases():
    x, y, a, b, c = x_(), y_(), K.sym('a'), K.sym('b'), K.sym('c')
    s = sm(x, q(1))
    return [
        (pw(x, 2), (K.ONE, K.ZERO, K.ZERO)),
        (sm(prod(q(3), pw(x, 2)), prod(q(2), x), q(1)), (q(3), q(2), q(1))),
        (sm(pw(x, 2), y), (K.ONE, K.ZERO, y)),
        (pw(s, 2), (K.ONE, q(2), K.ONE)),
        (pw(sm(prod(q(2), x), q(-3)), 2), (q(4), q(-12), q(9))),
        (prod(x, s), (K.ONE, K.ONE, K.ZERO)),
        (prod(sm(x, q(-1)), s), (K.ONE, K.ZERO, q(-1))),
        (sm(prod(a, pw(x, 2)), prod(b, x), c), (a, b, c)),
        (sm(prod(q(2), x), q(1)), (K.ZERO, q(2), q(1))),
        (q(5), (K.ZERO, K.ZERO, q(5))),
        (prod(y, pw(s, 2)), (y, prod(q(2), y), y)),
        (div(pw(x, 2), q(2)), (q(1, 2), K.ZERO, K.ZERO)),
    ]


def test_quadratic_cases():
    x = x_()
    for e, want in quad_cases():
        assert A.quadratic(e, x) == want, A_text(e)


def test_quadratic_rejects():
    x, y = x_(), y_()
    for e in (pw(x, 3), div(q(1), x), sqrt(x), fn(K.COS, x), prod(pw(x, 2), sm(x, q(1))),
              pw(sm(x, y), 2)):                         # the last: y*y needs mul_ (notes)
        assert A.quadratic(e, x) is None, A_text(e)


@pytest.mark.parametrize('seed', range(4))
def test_quadratic_recovers_random_coefficients(seed):
    g = gen.Gen(seed, syms=('y',), consts=('pi',))
    x = x_()
    rng = random.Random(seed)
    for _ in range(30):
        try:
            cs = [gen.build(g.tree(2), K) for _ in range(3)]
            e = K.add_([K.mul_(K.ONE, [(cs[0], K.ONE), (x, K.TWO)]),
                        K.mul_(K.ONE, [(cs[1], K.ONE), (x, K.ONE)]), cs[2]])
        except (K.Undefined, K.CasError):
            continue
        if any(c in (K.OO, K.UNDEF) for c in cs):
            continue
        r = A.quadratic(e, x)
        assert r is not None, A_text(e)
        env = {'y': rng.uniform(0.4, 2.0)}
        try:
            want = [ev(c, env) for c in cs]
        except (ZeroDivisionError, ValueError, OverflowError):
            continue
        for got, w in zip(r, want):
            assert K.free_of(got, x) and close(ev(got, env), w, 1e-8)


# -- split_const ---------------------------------------------------------------------------------

def test_split_const_cases():
    x, y = x_(), y_()
    s = sm(x, q(1))
    sy = sm(y, q(1))
    cases = [
        (prod(q(3), x), (q(3), x)),
        (x, (K.ONE, x)),
        (q(5), (q(5), K.ONE)),
        (y, (y, K.ONE)),
        (prod(q(3), y, pw(x, 2), fn(K.SIN, x)), (prod(q(3), y), prod(pw(x, 2), fn(K.SIN, x)))),
        (s, (K.ONE, s)),
        (prod(q(-2), K.PI, pwe(K.E, x)), (pimul(-2), pwe(K.E, x))),
        (div(y, s), (y, pw(s, -1))),
        (prod(q(-1), y, s), (K.neg_(y), s)),
        (div(s, q(2)), (q(1, 2), s)),
        (prod(q(2), sub(q(1), x)), (q(-2), sub(x, q(1)))),
        (prod(q(-1), K.PI, s), (pimul(-1), s)),
        (prod(q(-1), sy, x), (K.neg_(sy), x)),
        (prod(sy, x), (sy, x)),
    ]
    for e, want in cases:
        assert A.split_const(e, x) == want, A_text(e)


@pytest.mark.parametrize('seed', range(6))
def test_split_const_recomposes_exactly(seed):
    g = gen.Gen(seed, syms=('x', 'y'), consts=('pi', 'e'))
    x = x_()
    for _ in range(50):
        try:
            e = gen.build(g.tree(3), K)
        except (K.Undefined, K.CasError):
            continue
        c, h = A.split_const(e, x)
        assert K.free_of(c, x)
        assert K.mul_(K.ONE, [(c, K.ONE), (h, K.ONE)]) == e, A_text(e)
        if K.free_of(e, x):
            assert h == K.ONE
        else:
            t = K.N[h]
            if t[0] == K.MUL:
                assert t[1] == K.ONE
                assert all(not K.free_of(t[j], x) or not K.free_of(t[j + 1], x)
                           for j in range(2, len(t), 2))
            else:
                assert not K.free_of(h, x)


# -- degree --------------------------------------------------------------------------------------

def test_degree():
    x, y = x_(), y_()
    s = sm(x, q(1))
    cases = [
        (sm(pw(x, 3), x), 3), (q(5), 0), (y, 0), (prod(y, pw(x, 2)), 2), (pw(s, 3), 3),
        (div(q(1), x), -1), (fn(K.SIN, x), -1), (pwe(q(2), x), -1), (sqrt(x), -1),
        (prod(sm(pw(x, 2), q(1)), s), 3), (prod(pwe(K.E, y), x), 1), (x, 1),
        (sm(pw(x, 2), fn(K.SIN, y)), 2), (sm(pw(x, 2), fn(K.SIN, x)), -1),
        (K.rel_(K.EQ, x, q(1)), -1), (pw(sm(pw(x, 2), y), 4), 8),
    ]
    for e, want in cases:
        assert A.degree(e, x) == want, A_text(e)
    k = fn(K.SIN, x)
    assert A.degree(sm(pw(k, 2), x), k) == 2                     # a polynomial in a kernel


# -- size ----------------------------------------------------------------------------------------

def test_size():
    x, y = x_(), y_()
    sx = fn(K.SIN, x)
    cases = [
        (x, 1), (q(7), 1), (sm(x, q(1)), 3), (sub(x, y), 4), (prod(q(2), x), 3), (pw(x, 2), 3),
        (div(x, y), 4), (sx, 2), (pwe(K.E, x), 3), (sm(pw(sx, 2), sx), 7),
        (sm(prod(q(3), pw(x, 2)), prod(q(2), x), q(1)), 8),
        (pwe(K.E, sm(x, q(1))), 5),
    ]
    for e, want in cases:
        assert A.size(e) == want, A_text(e)
    assert A.size(prod(sqrt(q(2)), x)) == 4
    assert A.size(prod(sqrt(q(2)), x), True) == 6               # + 2 per radical pair
    assert A.size(div(q(1), x), True) == 4                      # + 1 per negative exponent
    assert A.size(sm(div(q(1), x), sqrt(q(3))), True) == 1 + (3 + 1) + (3 + 2)


# -- simplify_candidate (8.7) --------------------------------------------------------------------

def test_simplify_candidate():
    x = x_()
    s = sm(x, q(1))
    yes = [sm(x, div(q(1), x)), div(q(1), s), fn(K.TAN, x), prod(fn(K.SEC, x), x),
           fn(K.COT, x), pw(q(2), 1, 3), sm(pw(q(5), 2, 3), x), K.mk((K.LST, x, fn(K.CSC, x))),
           div(sm(pw(x, 2), q(-1)), sm(x, q(-1)))]
    no = [sm(pw(x, 2), q(1)), div(q(1), x), sqrt(q(2)), prod(q(2), sqrt(q(3))), fn(K.SIN, x),
          sm(sqrt(q(2)), q(1)), pwe(K.E, K.neg_(x)), x, q(3), sm(x, fn(K.COS, x))]
    for e in yes:
        assert A.simplify_candidate(e), A_text(e)
    for e in no:
        assert not A.simplify_candidate(e), A_text(e)


def test_simplify_candidate_takes_any_result():
    """g_eval calls it on every result: sentinels, relations, lists and calls (T1.5 notes)."""
    x = x_()
    m = K.mk((K.MUL, K.ONE, q(2), q(3), q(3), q(2), q(5), K.ONE))
    for e in (K.TRUE, K.FALSE, K.UNDEF, K.OO, K.mk((K.HOLD, m)), K.mk((K.DIVG, K.ZERO)),
              K.mk((K.DNE, K.neg_(K.OO), K.OO)), K.rel_(K.LT, x, q(3)),
              K.mk((K.CALL, K.sym('integrate'), x, x)), K.mk((K.LST,))):
        assert not A.simplify_candidate(e)
    assert A.simplify_candidate(K.mk((K.DNE, fn(K.TAN, x), K.OO)))
    assert A.simplify_candidate(K.rel_(K.EQ, x, div(q(1), sm(x, q(1)))))


# -- nprog / nrun / nev (6.6) --------------------------------------------------------------------

def nv(e, **env):
    return A.nev(e, {K.sym(k): v for k, v in env.items()})


def test_nev_constants():
    assert A.nev(K.PI) == math.pi and A.nev(K.E) == math.e
    assert A.nev(q(1, 3)) == 1 / 3
    v = A.nev(q(3, 4, 2))
    assert type(v) is complex and v == complex(0.75, 0.5)
    assert A.nev(K.flt(0.5)) == 0.5
    assert type(A.nev(q(7))) is float
    assert close(A.nev(sqrt(q(2))), math.sqrt(2), 1e-15)
    assert close(A.nev(pw(q(2), 1, 3)), 2 ** (1 / 3), 1e-15)
    assert close(A.nev(K.LN10), math.log(10), 1e-15)
    assert close(A.nev(fn(K.COS, pimul(5, 12))), math.cos(5 * math.pi / 12), 1e-15)
    m = K.mk((K.MUL, K.ONE, q(2), q(3), q(3), q(2), q(5), K.ONE))
    assert A.nev(K.mk((K.HOLD, m))) == 360.0


def test_nev_big_rationals_without_float_of_a_big_int():
    from fractions import Fraction
    for a, d in ((10 ** 400, 3 ** 800), (-(7 ** 300), 11 ** 290), (2 ** 70 + 1, 3),
                 (1, 10 ** 300 + 7), (3 ** 500, 3 ** 500 + 1)):
        v = A.nev(q(a, d))
        assert close(v, float(Fraction(a, d)), 1e-15)
    assert A.nev(q(1, 10 ** 400)) == 0.0                       # underflow is a value
    with pytest.raises(K.Undefined):
        A.nev(q(10 ** 400))                                    # beyond a float


def test_nev_variables_and_unknown_symbols():
    x = x_()
    e = sm(pw(x, 2), div(prod(q(3), x), q(2)), K.neg_(fn(K.SIN, x)))
    assert close(nv(e, x=0.7), 0.49 + 1.05 - math.sin(0.7), 1e-14)
    assert nv(e, x=2) == nv(e, x=2.0)                         # int inputs are fine
    with pytest.raises(K.Undefined):
        A.nev(e)
    with pytest.raises(K.Undefined):
        nv(sm(x, y_()), x=1.0)


def test_nev_real_odd_roots_and_principal_values():
    x = x_()
    assert nv(pw(x, 1, 3), x=-8.0) == -2.0
    assert A.LEFTREAL[0] == 0
    assert close(nv(pw(x, 2, 3), x=-8.0), 4.0, 1e-15)
    assert close(nv(pw(x, -1, 3), x=-8.0), -0.5, 1e-15)
    assert close(nv(pw(x, 5, 3), x=-8.0), -32.0, 1e-15)
    v = nv(sqrt(x), x=-4.0)
    assert close(v, 2j, 1e-15) and A.LEFTREAL[0] == 1
    v = nv(pw(x, 1, 4), x=-16.0)
    assert close(v, 2 * cmath.exp(1j * math.pi / 4), 1e-14) and A.LEFTREAL[0] == 1
    assert nv(sqrt(x), x=4.0) == 2.0 and A.LEFTREAL[0] == 0


def test_nev_logs_and_inverse_trig_branches():
    x = x_()
    v = nv(fn(K.LN, x), x=-1.0)
    assert close(v, 1j * math.pi, 1e-15) and A.LEFTREAL[0] == 1
    s3 = math.log(2 + math.sqrt(3))
    assert close(nv(fn(K.ASIN, x), x=2.0), complex(math.pi / 2, -s3), 1e-14)
    assert close(nv(fn(K.ASIN, x), x=-2.0), complex(-math.pi / 2, s3), 1e-14)
    assert A.LEFTREAL[0] == 1
    assert close(nv(fn(K.ACOS, x), x=2.0), complex(0, s3), 1e-14)
    assert close(nv(fn(K.ACOS, x), x=-2.0), complex(math.pi, -s3), 1e-14)
    assert close(nv(fn(K.ATAN, x), x=2.0), math.atan(2.0), 1e-15)
    # the odd extension (D15): asin(1-x) is built as -asin(x-1)
    e = fn(K.ASIN, sub(q(1), x))
    assert close(nv(e, x=4.0), -nv(fn(K.ASIN, x), x=3.0), 1e-14)


def test_nev_complex_constants_do_not_count_as_leaving_the_reals():
    x = x_()
    v = nv(pw(sm(x, K.I), 2), x=1.0)
    assert close(v, 2j, 1e-15) and A.LEFTREAL[0] == 0
    v = nv(prod(sm(x, K.I), sub(x, K.I)), x=2.0)                 # (x+i)(x-i): back to the reals
    assert v == 5.0 and type(v) is float
    v = nv(pwe(q(2), K.I))
    assert close(v, cmath.exp(1j * math.log(2)), 1e-15)
    v = A.nev(pwe(K.E, prod(K.I, pimul(1, 6))))
    assert close(v, complex(math.sqrt(3) / 2, 0.5), 1e-15)


def test_nev_symbolic_exponents():
    x, y = x_(), y_()
    assert close(nv(pwe(q(2), x), x=0.5), math.sqrt(2), 1e-15)
    assert close(nv(pwe(x, y), x=2.0, y=0.5), math.sqrt(2), 1e-15)
    assert nv(pwe(K.E, x), x=1.5) == math.exp(1.5)
    v = nv(pwe(x, y), x=-2.0, y=2.0)                             # an integral float exponent
    assert v == 4.0 and A.LEFTREAL[0] == 0
    v = nv(pwe(x, y), x=-2.0, y=0.5)
    assert close(v, complex(0, math.sqrt(2)), 1e-14) and A.LEFTREAL[0] == 1
    assert nv(pwe(x, y), x=0.0, y=2.0) == 0.0


REAL_FNS = [(K.SIN, math.sin), (K.COS, math.cos), (K.TAN, math.tan),
            (K.SEC, lambda a: 1 / math.cos(a)), (K.CSC, lambda a: 1 / math.sin(a)),
            (K.COT, lambda a: 1 / math.tan(a)), (K.ASIN, math.asin), (K.ACOS, math.acos),
            (K.ATAN, math.atan), (K.SINH, math.sinh), (K.COSH, math.cosh),
            (K.TANH, math.tanh), (K.LN, math.log), (K.ABS, abs),
            (K.FLOOR, math.floor), (K.CEIL, math.ceil), (K.FACT, lambda a: math.gamma(a + 1)),
            (K.SIGN, lambda a: (a > 0) - (a < 0))]


@pytest.mark.parametrize('op, f', REAL_FNS, ids=[str(o) for o, _ in REAL_FNS])
def test_nrun_real_functions(op, f):
    x = x_()
    p = A.nprog(fn(op, x), (x,))
    pts = [0.3, 0.71, -0.45, 0.999, 1e-9, -2e-6, 3e-4, 0.002]
    if op not in (K.ASIN, K.ACOS):
        pts += [2.5, -3.7, 12.0, 40.5]
    for a in pts:
        if op == K.LN and a <= 0:
            continue
        v = A.nrun(p, (a,))
        assert type(v) is float
        assert close(v, float(f(a)), 1e-13), (op, a)


def test_nrun_factorial_is_gamma():
    x = x_()
    p = A.nprog(fn(K.FACT, x), (x,))
    for a in (0.0, 1.0, 5.0, 20.0, 0.5, 2.7, -0.5, -1.5, -2.25, 100.5, 170.0):
        assert close(A.nrun(p, (a,)), math.gamma(a + 1), 1e-13), a
    for a in (-1.0, -3.0, 172.0, 1e300):
        with pytest.raises(K.Undefined):
            A.nrun(p, (a,))


CPX = [(K.SIN, cmath.sin), (K.COS, cmath.cos), (K.TAN, cmath.tan),
       (K.SEC, lambda z: 1 / cmath.cos(z)), (K.CSC, lambda z: 1 / cmath.sin(z)),
       (K.COT, lambda z: 1 / cmath.tan(z)), (K.ASIN, cmath.asin), (K.ACOS, cmath.acos),
       (K.ATAN, cmath.atan), (K.SINH, cmath.sinh), (K.COSH, cmath.cosh),
       (K.TANH, cmath.tanh), (K.LN, cmath.log), (K.ABS, abs)]


@pytest.mark.parametrize('op, f', CPX, ids=[str(o) for o, _ in CPX])
def test_nrun_complex_functions_off_the_cuts(op, f):
    x = x_()
    p = A.nprog(fn(op, x), (x,))
    for z in (0.3 + 0.4j, -1.2 + 0.7j, 2.5 - 1.5j, -0.1 - 3j, 1e-3 + 2e-3j, 4 + 25j, -3 - 30j):
        v = A.nrun(p, (z,))
        assert close(cvalue(v), f(z), 1e-12), (op, z)
        assert A.LEFTREAL[0] == 0


def test_complex_branch_conventions_match_sympy():
    import mpmath
    x = x_()
    pts = (2.0, -2.0, 1e10, -1e10, 3j, -3j, 1.5 + 0j)
    for op, mp in ((K.ASIN, mpmath.asin), (K.ACOS, mpmath.acos), (K.ATAN, mpmath.atan),
                   (K.LN, mpmath.log)):
        p = A.nprog(fn(op, x), (x,))
        for z in pts:
            if op == K.ATAN and z in (2.0, -2.0, 1e10, -1e10, 1.5 + 0j):
                continue
            want = complex(mp(mpmath.mpc(z)))
            if op in (K.ASIN, K.ACOS) and complex(z).imag == 0 and complex(z).real < -1:
                # mpmath takes the upper side of the cut for -x as well; ours is odd (D15)
                want = complex(-mpmath.asin(-z.real)) if op == K.ASIN else \
                    complex(mpmath.pi - mpmath.acos(-z.real))
            assert close(cvalue(A.nrun(p, (z,))), want, 1e-12), (op, z)
    import sympy
    assert close(cvalue(A.nev(fn(K.ASIN, q(2)))), complex(sympy.N(sympy.asin(2))), 1e-14)
    assert close(cvalue(A.nev(fn(K.ACOS, q(2)))), complex(sympy.N(sympy.acos(2))), 1e-14)
    assert close(cvalue(A.nev(K.neg_(fn(K.ASIN, q(2))))), complex(sympy.N(sympy.asin(-2))),
                 1e-14)


def test_nev_undefined_cases():
    x, y = x_(), y_()
    bad = [(div(q(1), x), 0.0), (fn(K.LN, x), 0.0), (pw(x, -1, 2), 0.0),
           (pwe(K.E, x), 1000.0), (fn(K.SINH, x), 1000.0), (pw(x, 400), 10.0),
           (fn(K.COT, x), 0.0), (fn(K.CSC, x), 0.0), (fn(K.FACT, x), -2.0),
           (pw(sm(x, K.I), -1), 0.0)]
    for e, a in bad:
        with pytest.raises(K.Undefined):
            nv(e, x=a if e != bad[-1][0] else complex(0, -1))
    with pytest.raises(K.Undefined):
        nv(pwe(x, y), x=0.0, y=-1.0)                            # 0^-1 through P_POW
    for e in (K.OO, K.UNDEF, K.neg_(K.OO), K.TRUE, K.rel_(K.EQ, x, q(1)),
              K.mk((K.LST, q(1), q(2))), K.mk((K.CALL, K.sym('integrate'), x, x)),
              K.mk((K.BIGO, pw(x, 6)))):
        with pytest.raises(K.Undefined):
            A.nev(e, {x: 1.0})
    with pytest.raises(K.Undefined):
        A.nprog(sm(x, y), (x,))


def test_nev_float_exponents_take_the_principal_value():
    x = x_()
    e = pwe(x, K.flt(0.5))
    assert nv(e, x=4.0) == 2.0
    v = nv(e, x=-4.0)
    assert close(v, 2j, 1e-15) and A.LEFTREAL[0] == 1
    assert nv(pwe(x, K.flt(2.0)), x=-3.0) == 9.0 and A.LEFTREAL[0] == 0
    assert close(nv(prod(K.flt(0.5), x, K.I), x=2.0), 1j, 1e-15)


def test_ntol_bounds_and_unusable_points():
    x = x_()
    p = A.nprog(sm(pw(x, 2), prod(q(3), x), q(1)), (x,))
    r = [0.0] * len(p)
    t = [0.0] * len(p)
    v = A.nrun(p, (2.0,), r)
    w = A.ntol(p, r, t)
    assert v == 11.0 and 0 < w < 20 * A.TOL * 11.0          # no cancellation: about TOL*|v|
    p = A.nprog(fn(K.SEC, prod(q(10 ** 12), x)), (x,))      # a trig function of a huge argument
    r = [0.0] * len(p)
    A.nrun(p, (1.3,), r)
    assert A.ntol(p, r, [0.0] * len(p)) == -1.0
    p = A.nprog(div(q(1), sm(pw(fn(K.SIN, x), 2), pw(fn(K.COS, x), 2), q(-1))), (x,))
    r = [0.0] * len(p)
    try:
        A.nrun(p, (0.7,), r)
    except K.Undefined:
        pass                                                # 1/0 exactly is undefined too
    else:
        assert A.ntol(p, r, [0.0] * len(p)) == -1.0          # 1/(a zero sum): singular


def test_rebuild_with_a_full_map_and_a_changed_child():
    x, y = x_(), y_()
    e = sm(prod(q(3), x, fn(K.SIN, y)), q(1))
    full = {n: n for n in A.postorder(e)}
    assert A.rebuild(e, full) == e
    full[y] = K.ZERO                                         # sin(0) = 0 folds the product
    s = fn(K.SIN, y)
    full[s] = A.rebuild(s, full)
    t = K.N[e][2]
    full[t] = A.rebuild(t, full)
    assert full[s] == K.ZERO and full[t] == K.ZERO and A.rebuild(e, full) == K.ONE


def test_nrun_reuses_the_value_list():
    x = x_()
    e = sm(pw(x, 2), q(1))
    p = A.nprog(e, (x,))
    r = [0.0] * len(p)
    assert A.nrun(p, (3.0,), r) == 10.0
    assert r[-1] == 10.0 and 9.0 in r and 3.0 in r
    assert all(type(ins) is tuple for ins in p)


def test_nrun_survives_a_device_math_that_returns_nan(monkeypatch):
    """Some MicroPython builds return nan from asin(2) or log(-1) instead of raising (6.6)."""
    x = x_()
    nan = float('nan')
    fnum = list(A.FNUM)

    def nanlog(a):
        return nan if a <= 0 else math.log(a)

    def nanasin(a):
        return nan if abs(a) > 1 else math.asin(a)
    fnum[K.LN - K.FN0] = nanlog
    fnum[K.ASIN - K.FN0] = nanasin
    monkeypatch.setattr(A, 'FNUM', tuple(fnum))
    assert close(nv(fn(K.LN, x), x=-1.0), 1j * math.pi, 1e-15) and A.LEFTREAL[0] == 1
    assert close(nv(fn(K.ASIN, x), x=2.0), complex(math.pi / 2, -math.log(2 + math.sqrt(3))),
                 1e-14)
    with pytest.raises(K.Undefined):
        nv(fn(K.LN, x), x=0.0)


def test_nrun_rejects_inf_without_an_exception(monkeypatch):
    """Float overflow on the device gives inf without raising (3, 6.6)."""
    x = x_()
    fnum = list(A.FNUM)
    fnum[K.SINH - K.FN0] = lambda a: float('inf')
    monkeypatch.setattr(A, 'FNUM', tuple(fnum))
    with pytest.raises(K.Undefined):
        nv(fn(K.SINH, x), x=1.0)


@pytest.mark.parametrize('seed', range(10))
def test_nev_agrees_with_an_independent_evaluator(seed):
    """nev and test_node.ev evaluate the same node: within the propagated tolerance."""
    funcs = tuple(f for f in gen.FUNCS if f not in ('asin', 'acos', 'atan'))
    g = gen.Gen(seed, syms=('x', 'y'), funcs=gen.FUNCS if seed % 2 else funcs,
                consts=('pi', 'e', 'i'))
    rng = random.Random(seed)
    x, y = x_(), y_()
    done = 0
    for _ in range(80):
        try:
            e = gen.build(g.tree(4), K)
        except (K.Undefined, K.CasError):
            continue
        try:
            p = A.nprog(e, (x, y))
        except K.Undefined:
            continue                                         # oo, undef
        cuts = any(K.N[n][0] in (K.ASIN, K.ACOS, K.ATAN) for n in A.postorder(e))
        for _ in range(3):
            px, py = rng.uniform(-2.6, 2.6), rng.uniform(-2.6, 2.6)
            try:
                want = ev(e, {'x': px, 'y': py})
            except (ZeroDivisionError, ValueError, OverflowError):
                continue
            if not (abs(want) < 1e12):
                continue
            r = [0.0] * len(p)
            try:
                got = A.nrun(p, (px, py), r)
            except K.Undefined:
                pytest.fail('nev undefined where ev = %r: %s' % (want, A_text(e)))
            if cuts and (abs(complex(got).imag) > 1e-12 or abs(want.imag) > 1e-12):
                continue                                     # branch conventions differ
            tol = A.ntol(p, r, [0.0] * len(p))
            if tol < 0:
                continue
            assert abs(complex(got) - want) <= tol + 1e-12 * max(1.0, abs(want)), \
                (A_text(e), px, py, got, want, tol)
            done += 1
    assert done > 40


# -- the numeric probe (8.6 step 5, 8.7) --------------------------------------------------------

def test_probe_zero_and_nonzero():
    x, y = x_(), y_()
    s2c2 = sm(pw(fn(K.SIN, x), 2), pw(fn(K.COS, x), 2), q(-1))
    assert A.nprobe(s2c2) == A.LIKELY
    assert A.nprobe(sub(pw(sm(x, q(1)), 2), sm(pw(x, 2), prod(q(2), x), q(1)))) == A.LIKELY
    addf = sub(fn(K.SIN, sm(x, y)), sm(prod(fn(K.SIN, x), fn(K.COS, y)),
                                       prod(fn(K.COS, x), fn(K.SIN, y))))
    assert A.nprobe(addf) == A.LIKELY
    assert A.nprobe(K.ZERO) == A.LIKELY
    assert A.nprobe(x) == A.NO
    assert A.nprobe(sub(fn(K.SIN, x), x)) == A.NO
    assert A.nprobe(sub(x, y)) == A.NO                       # distinct values per symbol
    assert A.nprobe(sub(K.PI, q(22, 7))) == A.NO
    assert A.nprobe(prod(q(1, 10 ** 12), x)) == A.NO          # small is not zero
    c = fn(K.SIN, pimul(1, 7))
    assert A.nprobe(sm(pw(c, 2), pw(fn(K.COS, pimul(1, 7)), 2), q(-1))) == A.LIKELY


def test_probe_tolerance_follows_the_structure():
    x = x_()
    s2c2 = sm(pw(fn(K.SIN, x), 2), pw(fn(K.COS, x), 2), q(-1))
    assert A.nprobe(prod(q(10 ** 20), s2c2)) == A.LIKELY      # a big factor of a zero sum
    assert A.nprobe(sqrt(s2c2)) == A.LIKELY                   # a root of a zero sum
    assert A.nprobe(prod(pw(x, 30), s2c2)) == A.LIKELY
    assert A.nprobe(pw(x, 30)) == A.NO


def test_probe_branch_policy_rows():
    """8.3: rewrites valid only for x > 0 are caught at the negative point."""
    x = x_()
    assert A.nprobe(fn(K.ABS, x), x) == A.NO                  # sqrt(x^2) -> x
    assert A.nprobe(fn(K.LN, pw(x, 2)), prod(q(2), fn(K.LN, x))) == A.NO
    e3 = pwe(K.E, div(fn(K.LN, x), q(3)))
    assert A.nprobe(pw(x, 1, 3), e3) == A.NO                  # the real odd root differs
    assert A.nprobe(sm(fn(K.ATAN, x), fn(K.ATAN, div(q(1), x))), pimul(1, 2)) == A.NO
    e2 = pwe(K.E, div(fn(K.LN, x), q(2)))
    assert A.nprobe(sqrt(x), e2) == A.LIKELY                  # x < 0: sqrt(x) is not real
    assert A.nprobe(e2, sqrt(x)) == A.LIKELY                  # x < 0: ln(x) is not real


def test_probe_points_only_where_the_input_is_real():
    x = x_()
    mx = K.neg_(x)
    e2 = pwe(K.E, div(fn(K.LN, mx), q(2)))
    assert A.nprobe(sqrt(mx), e2) == A.LIKELY                 # three negative points exist
    assert A.nprobe(sqrt(mx), prod(q(2), sqrt(mx))) == A.NO
    assert A.nprobe(sqrt(sub(K.neg_(pw(x, 2)), q(1)))) == A.UNKNOWN   # never real
    assert A.nprobe(K.mk((K.CALL, K.sym('integrate'), x, x))) == A.UNKNOWN
    assert A.nprobe(K.OO) == A.UNKNOWN
    assert A.nprobe(x, K.UNDEF) == A.NO                       # a is fine, b is not
    assert A.nprobe(x, fn(K.LN, sub(K.neg_(pw(x, 2)), q(1)))) == A.NO   # b is never real


IDENTITIES = [
    lambda u, v: sub(pw(sm(u, v), 2), sm(pw(u, 2), prod(q(2), u, v), pw(v, 2))),
    lambda u, v: sm(pw(fn(K.SIN, u), 2), pw(fn(K.COS, u), 2), q(-1)),
    lambda u, v: sub(fn(K.TAN, u), div(fn(K.SIN, u), fn(K.COS, u))),
    lambda u, v: sub(fn(K.SIN, sm(u, v)), sm(prod(fn(K.SIN, u), fn(K.COS, v)),
                                             prod(fn(K.COS, u), fn(K.SIN, v)))),
    lambda u, v: sub(fn(K.SINH, u), prod(K.HALF, sub(pwe(K.E, u), pwe(K.E, K.neg_(u))))),
    lambda u, v: sm(pw(fn(K.COSH, u), 2), K.neg_(pw(fn(K.SINH, u), 2)), q(-1)),
    lambda u, v: sub(pw(sm(u, q(1)), 3), sm(pw(u, 3), prod(q(3), pw(u, 2)), prod(q(3), u), q(1))),
    lambda u, v: sub(fn(K.LN, prod(pw(u, 2), q(3))), sm(fn(K.LN, pw(u, 2)), fn(K.LN, q(3)))),
]


@pytest.mark.invariants_skip('mul')    # the random inputs can build abs(ln5-ln6)^4: see notes
@pytest.mark.parametrize('seed', range(5))
def test_probe_never_says_no_to_an_identity(seed):
    """A false NO would reject a valid antiderivative, root or simplification (8.6, 8.7).
    (The invariant scan's rule-9 check is stricter than T1.1's mul_ for symbol-free u that
    isreal cannot prove real, docs/notes/T1.1.md; these inputs can hit that.)"""
    g = gen.Gen(seed * 7 + 1, syms=('x', 'y'), consts=('pi', 'e'))
    seen = [0, 0, 0]
    for _ in range(12):
        for f in IDENTITIES:
            K.reset()
            try:
                u = gen.build(g.tree(3), K)
                v = gen.build(g.tree(3), K)
                e = f(u, v)
            except (K.Undefined, K.CasError):
                continue
            r = A.nprobe(e)
            assert r != A.NO, A_text(e)
            seen[r + 1] += 1
    assert seen[2] > 4 * seen[0]                              # mostly LIKELY, few UNKNOWN


@pytest.mark.parametrize('seed', range(4))
def test_probe_does_not_call_random_expressions_zero(seed):
    g = gen.Gen(seed + 100, syms=('x', 'y'), floats=True, consts=('pi', 'e', 'i'))
    rng = random.Random(seed)
    likely = wrong = total = 0
    for _ in range(150):
        K.reset()
        try:
            e = gen.build(g.tree(4), K)
        except (K.Undefined, K.CasError):
            continue
        if e == K.ZERO:
            continue
        r = A.nprobe(e)
        total += 1
        if r != A.LIKELY:
            continue
        likely += 1
        for _ in range(4):
            env = {'x': rng.uniform(-2.5, 2.5), 'y': rng.uniform(-2.5, 2.5)}
            try:
                if abs(ev(e, env)) > 1e-6:
                    wrong += 1
                    break
            except (ZeroDivisionError, ValueError, OverflowError):
                pass
    assert total > 100 and wrong <= total // 100, (wrong, likely, total)


def test_probe_is_deterministic_and_builds_no_nodes():
    x, y = x_(), y_()
    e = sub(fn(K.SIN, sm(x, y)), prod(fn(K.SIN, x), fn(K.COS, y)))
    n = K.NN
    r = [A.nprobe(e) for _ in range(3)]
    assert r == [A.NO] * 3 and K.NN == n


# -- depth: nesting invariance (20.7) -----------------------------------------------------------

@pytest.mark.parametrize('what', ['nev', 'subst', 'linear', 'quadratic', 'split', 'size',
                                  'probe', 'degree', 'candidate'])
def test_depth_does_not_grow_with_nesting(evodepth, what):
    def build(n):
        x = x_()
        e = x
        for _ in range(n):
            e = sm(fn(K.SIN, e), prod(q(2), x))
        return e

    def run(n):
        K.reset()
        e = build(n)
        x = x_()
        if what == 'nev':
            return A.nev(e, {x: 0.3})
        if what == 'subst':
            return A.subst(e, x, sm(x_(), q(1)))
        if what == 'linear':
            return A.linear(e, fn(K.SIN, x))
        if what == 'quadratic':
            return A.quadratic(prod(e, x), x)
        if what == 'split':
            return A.split_const(prod(q(3), K.sym('c'), e), x)
        if what == 'size':
            return A.size(e, True)
        if what == 'probe':
            return A.nprobe(e)
        if what == 'degree':
            return A.degree(e, x)
        return A.simplify_candidate(e)
    depths = []
    for n in (1, 8, 32):
        _, d, _ = evodepth.measure(run, n)
        depths.append(d)
    assert depths[0] == depths[1] == depths[2] <= 7, depths
