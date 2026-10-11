"""Shared end-to-end oracle/session helpers for the v1 milestone corpora."""
import sympy as S
import parse as P
import run as R
import node as K


def fresh():
    R.ANS = None
    R.HIST = []
    R.VARS = {}
    R.FUNCS = {}
    R.MODS = {}
    R.LOADED = []
    R.USE = {}
    R.PINNED = []
    R.LIVE = {}
    R.NEEDED = []
    R.CLOCK = [0]
    R.SET = {'deg': 0, 'theme': 0}
    P.SESS = R
    K.reset()


def answer(text):
    rec = R.go(('eval', text))
    assert rec[0] == 'ans', (text, rec)
    assert K.NN == K.BASE
    return rec[1]


def sx(text):
    loc = {c: S.Symbol(c, real=True) for c in 'abcdefghijklmnopqrstuvwxyz'}
    loc.update({'e': S.E, 'i': S.I, 'pi': S.pi, 'oo': S.oo, 'ln': S.log,
                'log': lambda x: S.log(x, 10), 'abs': S.Abs, 'O': S.Order,
                'true': S.true, 'false': S.false})
    return S.sympify(text.replace('^', '**'), locals=loc)


def equivalent(a, b):
    delta = S.trigsimp(S.simplify(sx(a) - sx(b)))
    if delta == 0:
        return
    syms = sorted(delta.free_symbols, key=str)
    for point in (S.Rational(1, 5), S.Rational(3, 7), S.Rational(7, 11)):
        value = complex(delta.subs({s: point + j / 17 for j, s in enumerate(syms)}).evalf(30))
        assert abs(value) < 1e-9, (a, b, delta, value)
