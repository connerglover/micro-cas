# Desktop replica of the PROBE6 trampoline shapes (DESIGN.md Appendix B).
# The device expectations are in the comments; PROBE6 has not run on the EVO yet, so the
# 'ingen' value is the design's assumption (resuming a generator with send() costs no frame).
cnt = [0]


def plain():
    cnt[0] += 1
    plain()


def gchild(d):
    cnt[0] += 1
    if d > 0:
        r = yield gchild(d - 1)
        yield r + 1
    else:
        yield 0


GEN = type(gchild(0))


def tramp(g):
    st = [g]
    val = None
    while st:
        try:
            y = st[-1].send(val)
        except StopIteration:
            y = None
        if type(y) is GEN:
            st.append(y)
            val = None
            continue
        st.pop()
        val = y
    return val


def deep_in_gen():
    # one generator at trampoline depth, then plain recursion inside it
    cnt[0] = 0
    try:
        plain()
    except RuntimeError:
        pass
    yield cnt[0]


def tryit(f):
    try:
        return f()
    except BaseException as e:
        return 'E:' + type(e).__name__


# PROBE6 ran tryit("ingen", lambda: tramp(deep_in_gen())) from module level:
# tryit 1 > lambda 2 > tramp 3 > gen 4 > plain x N. Device expectation: N = 6.
INGEN = lambda: tramp(deep_in_gen())  # noqa: E731


def gthrow():
    try:
        yield 1
    except ValueError:
        yield 2


def t_throw():
    g = gthrow()
    a = g.send(None)
    b = g.throw(ValueError('x'))
    return '%d %d' % (a, b)
