#@L 2
# F4 transforms an inert original answer; the runner commits the resulting text.
import node as K
import alg as A
import parse as P
import printer as PR
import run as R

ORDER = ('simplified', 'one fraction', 'factored', 'expanded', 'decimal')


def g_form(code, ctx):                                          #@L 2
    e = R.HIST[R.FORMINDEX]
    f = yield P.g_eval(code, ctx)
    original = e[5][0][1] if e[5] else e[1]
    R.FORMNAME = 'exact'
    if e[2] != R.R_ANS or 'integrate(' in original or 'sum(' in original or 'limit(' in original:
        yield f
        return
    order = ('decimal',) + ORDER[:-1] if e[3] is not None and not K.V[f] else ORDER
    cache = e[5] or [('exact', original)]
    current = 'exact'
    seen = []
    for name, text in cache:
        if text == e[1]:
            current = name
        seen.append(sorted(text))
    start = order.index(current) + 1 if current in order else 0
    for name in order[start:]:
        mark = K.NN
        candidate = None
        if name == 'simplified':
            candidate = yield R.MODS['norm'].g_simplify([f], ctx)
        elif name == 'one fraction':
            candidate = yield R.MODS['norm'].g_together([f], ctx)
        elif name == 'factored':
            candidate = yield R.MODS['fact'].g_factor([f], ctx)
        elif name == 'expanded':
            candidate = yield R.MODS['norm'].g_expand([f], ctx)
        elif A.size(f) <= 40 and not K.V[f]:
            candidate = P.approx(f)
        if candidate is not None:
            text = PR.text(candidate, ctx)
            if text and sorted(text) not in seen and (name != 'simplified' or len(text) < len(original)):
                R.FORMNAME = name
                yield K.keep(mark, candidate)
                return
        K.keep(mark, None)
    yield f
