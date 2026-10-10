# PRBIMP: companion module of PROBE5 (cas-evo M0.3, device-python 14.1).
# Its body recurses until the depth cap. N is how many frames the body
# could still open, so PROBE5 learns what an import costs in frames.
c = [0]


def r():
    c[0] += 1
    r()


try:
    r()
except RuntimeError:
    pass
N = c[0]
