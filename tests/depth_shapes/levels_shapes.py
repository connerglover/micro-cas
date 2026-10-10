#@L 7
# Level-annotated replica of the deepest planned chain (DESIGN.md section 17.2, first row):
#   0 loop > 1 R.go > 2 g_check > 3 diff > 4 inst > 5 mul_ > 6 add_ > 7 mk
# The calibration tests run it through a miniature trampoline under the depth checker with
# the levels that framelint reads from these annotations.
N = [0]


def mk(t):
    N[0] += 1
    return N[0]


def add_(ts):                                                   #@L 6
    return mk(ts)


def mul_(k, ps):                                                #@L 5
    return add_(ps)


def inst(code):                                                 #@L 4
    return mul_(1, code)


def diff(e):                                                    #@L 3
    return inst(e)


def g_inner(e):                                                 #@L 2
    yield diff(e)


def g_check(e):                                                 #@L 2
    r = yield g_inner(e)
    yield diff(r)


def go(e):                                                      #@L 1
    gtype = type(g_check(0))
    stack = [g_check(e)]
    val = None
    while stack:
        try:
            y = stack[-1].send(val)
        except StopIteration:
            y = None
        if type(y) is gtype:
            stack.append(y)
            val = None
            continue
        stack.pop()
        val = y
    return val


def drop(box):
    del box[:]              # (L7) releases what the box holds, here and now


def bad_diff(e):                                                #@L 3
    return diff(e)          # an L3 -> L3 edge: diff then runs at depth 4 > its level 3


def go_bad(e):                                                  #@L 2
    return bad_diff(e)
