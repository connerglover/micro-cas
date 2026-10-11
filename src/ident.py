#@L 3
# CVIDENT: identity rule sets (strings, DESIGN 9.1-9.2) and one-level denesting (6.2, alg 2.2).
# A set is (measure, lhs, rhs, guard, lhs, rhs, guard, ...); rules.rset('name') compiles the
# tuple NAME. The measure strictly decreases at every fire (tests/test_rules.py). Every
# rewrite is an identity under the branch policy of 8.3. Rule strings write every '*'.
import node as K
import alg as A

TC = ('count', K.TAN, K.SEC, K.CSC, K.COT)
TAN2SINCOS = (
    TC,
    'tan(U)', 'sin(U)/cos(U)', '',
    'sec(U)', '1/cos(U)', '',
    'csc(U)', '1/sin(U)', '',
    'cot(U)', 'cos(U)/sin(U)', '')
# giac trigsin / trigcos: tan, sec, csc, cot to sin and cos, then cos^2 = 1-sin^2 (trigsin)
# or sin^2 = 1-cos^2 (trigcos) on every power >= 2
TRIGSIN = (('lex', TC, ('pow', K.COS)),) + TAN2SINCOS[1:] + (
    'cos(U)^P*R', '(1-sin(U)^2)*cos(U)^(P-2)*R', 'P>=2')
TRIGCOS = (('lex', TC, ('pow', K.SIN)),) + TAN2SINCOS[1:] + (
    'sin(U)^P*R', '(1-cos(U)^2)*sin(U)^(P-2)*R', 'P>=2')
ZBASIS = TRIGCOS    # the zero-test basis (8.6 step 2): sin, cos and powers of cos only
# giac tlin: products and powers of sin and cos to sums of single sines and cosines
TLIN = (
    ('excess', K.SIN, K.COS),
    'sin(U)*cos(V)*R', '(sin(U+V)+sin(U-V))/2*R', '',
    'sin(U)*sin(V)*R', '(cos(U-V)-cos(U+V))/2*R', '',
    'cos(U)*cos(V)*R', '(cos(U-V)+cos(U+V))/2*R', '',
    'sin(U)^P*R', '(1-cos(2*U))/2*sin(U)^(P-2)*R', 'P>=2',
    'cos(U)^P*R', '(1+cos(2*U))/2*cos(U)^(P-2)*R', 'P>=2')
# Pythagorean sums, with any equal coefficients (a repeated N must bind the same number)
PYTH = (
    ('count', K.SIN, K.COS, K.TAN, K.SEC, K.CSC, K.COT, K.SINH, K.COSH),
    'N*sin(U)^2+N*cos(U)^2+R', 'N+R', '',
    'N*cosh(U)^2-N*sinh(U)^2+R', 'N+R', '',
    'N*sec(U)^2-N*tan(U)^2+R', 'N+R', '',
    'N*csc(U)^2-N*cot(U)^2+R', 'N+R', '')
# ln a + ln b = ln(a*b) (8.3): symbolic arguments are positive wherever the input is real
# ('~'); constant ones must be proved positive, and the coefficients real
LNCOLLECT = (
    ('count', K.LN),
    'N*ln(U)+M*ln(V)+R', 'ln(U^N*V^M)+R', '~U>0,V>0,N^2>=0,M^2>=0')
# 2^x*3^x = 6^x (positive numeric bases; e^a*e^b is merged by the constructors)
EXPMERGE = (
    ('size',),
    'M^W*N^W*R', '(M*N)^W*R', 'M>0,N>0')


def isq(n):                                                     #@L 7
    # the integer square root of n >= 0 (Newton from above)
    if n < 2:
        return n
    r = 1 << (2 * len('%x' % n))
    while True:
        s = (r + n // r) // 2
        if s >= r:
            return r
        r = s


def denest(e):                                                  #@L 3
    # e with every power sqrt(p+q*sqrt(r))^k (k odd; p > 0 and q rational, r an integer)
    # denested when p^2-q^2*r = s^2 with s rational (alg 2.2, giac is_sqrtxy):
    # sqrt(p+q*sqrt(r)) = sqrt((p+s)/2)+sign(q)*sqrt((p-s)/2). The rest is rebuilt unchanged.
    N = K.N
    new = {}
    for n in A.postorder(e):
        m = A.rebuild(n, new)
        t = N[m]
        if t[0] == K.MUL:
            ps = []
            ch = 0
            for j in range(2, len(t), 2):
                b = N[t[j]]
                k = N[t[j + 1]]
                if k[0] == K.NUM and not k[2] and k[3] == 2 and b[0] == K.ADD and len(b) == 4:
                    p = N[b[1]]
                    q = N[b[3]]
                    w = N[b[2]]
                    if p[0] == K.NUM and not p[2] and p[1] > 0 and q[0] == K.NUM and \
                            not q[2] and w[0] == K.MUL and len(w) == 4 and w[1] == K.ONE and \
                            w[3] == K.HALF and N[w[2]][0] == K.NUM:
                        v = p[3] * q[3]                 # p = a/v, q*sqrt(r) = sqrt(c)/v
                        a = p[1] * q[3]
                        c = q[1] * q[1] * N[w[2]][1] * p[3] * p[3]
                        u = a * a - c
                        s = isq(u) if u > 0 else -1
                        if s >= 0 and s * s == u:
                            r = K.add_([K.mul_(K.ONE, [(K.num(a + s, 0, 2 * v), K.HALF)]),
                                        K.mul_(K.ONE if q[1] > 0 else K.MONE,
                                               [(K.num(a - s, 0, 2 * v), K.HALF)])])
                            ps.append((r, K.num(k[1])))
                            ch = 1
                            continue
                ps.append((t[j], t[j + 1]))
            if ch:
                m = K.mul_(t[1], ps)
        if m != n:
            new[n] = m
    return new.get(e, e)
