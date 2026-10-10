# Desktop replica of probe/PROBE4.py call shapes (device results in comments).
# This directory is passed to the depth checker as a device dir (device-python section 12.4).
# Test-support code: it deliberately recurses and uses constructs banned in src/.
cnt = [0]


def measure(start):
    cnt[0] = 0
    try:
        start()
        return -1
    except RuntimeError:
        return cnt[0]


def plain():                   # device: 9
    cnt[0] += 1
    plain()


def ping():                    # device: 9
    cnt[0] += 1
    pong()


def pong():
    cnt[0] += 1
    ping()


class C:
    def m(self):               # device: 9
        cnt[0] += 1
        self.m()


def gen(n):                    # device: 8 (started via lambda + list())
    cnt[0] += 1
    yield from gen(n + 1)


def w1():                      # device: 6
    w2()


def w2():
    w3()


def w3():
    plain()


def lc():                      # device: not measured yet (PROBE5 'lcomp')
    cnt[0] += 1
    [lc() for _ in (1,)]


def run_gen():                 # PROBE4 used lambda: list(gen(0))
    return list(gen(0))
