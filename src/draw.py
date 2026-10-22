#@L 3
# CVDRAW: the EVO screen through ti_draw, and the 2D layout (RPN, postorder boxes, display list).
# ti_draw as measured on the EVO (docs/notes/FASTBOOT.md): 320 x 210 pixels; one fixed font,
# 10 px per character, ink in rows y-17..y-3 of draw_text(x, y, s); fill_rect(x, y, w, h)
# fills only the interior, and w or h below 2 raises; set_color is slow, so it is cached.
import ti_draw as TD

P = None            #@lazy parse   (ui.engine sets the engine modules)
PR = None           #@lazy printer
W = 320
H = 210
SCREEN = (0, 0, 319, 209)
CW = 10             # pixels per character
ASC = 11            # text cell rows above the baseline
DESC = 4            # and below: 15 rows of ink
TY = 17             # draw_text(x, top + TY, s) puts the first ink row at top
AXIS = 4            # fraction bars, above the baseline
# The one light palette: background, ink, gray, rules and empty boxes, accent, accent tint.
COLORS = {'BG': (247, 248, 250), 'INK': (17, 20, 25), 'SUB': (108, 117, 129),
          'LINE': (219, 224, 231), 'ACC': (36, 92, 204), 'ACCSOFT': (226, 234, 250)}
CURRENT = None      # the color set_color last received
CACHE = []
CACHE_BYTES = 0
ICACHE = []         # history-input layouts (MathPrint, mode 1): (text, result, cost)
ICACHE_BYTES = 0
# MathPrint (docs/notes/MATHPRINT.md 1.2, 3.1): argument counts of the template form of a call,
# the trailing gap after a template, and the operator precedences of parse.PREC (draw cannot
# read the engine), with 8 for a blank or stray character that clings to the next operand.
TPL = {'sqrt': (1,), 'abs': (1,), 'exp': (1,), 'surd': (2,), 'log': (2,), 'integrate': (2, 4),
       'diff': (2, 3), 'sum': (4,), 'limit': (3, 4)}
TGAP = 3
# The argument table (QPL Q4, Q5; MATHPRINT.md 3.3, 7.5): ;name[#count]:<required><boxed><codes>;
# required: the arguments ENTER needs (an empty box after them is optional: mshut flags it, tidy
# drops it); boxed: the boxes a menu inserts (menub.insertion); codes: one
# ui.ARGPH phrase per argument (A-Z a-z 0-9), * after the last one repeats it. #count: the form
# with that many arguments. / and ^ are the fraction and exponent slots.
ARGS = (';simplify:11C;expand:11D;factor:11EF;solve:12GH;together:11I;partfrac:11JF;diff:22KLM;'
        'integrate:24NOPQ;limit:34RFST;limit#2:22RU;taylor:23VWX;taylor#4:33VFYX;sum:44Zabc;'
        'riemann:56dFefgh;desolve:12ij;desolve#3:11ikj;grad:11lm;polararea:44nopq;'
        'paramarea:55rstbu;arclen:44vFbu;arclen#5:55rstbu;approx:11w;purge:11xy*;log:12Az;'
        'surd:2201;sqrt:110;exp:112;abs:113;sign:11A;floor:11A;ceil:11A;/:2245;^:112;')
MPREC = {'=>': 1, ':=': 1, '=': 3, '!=': 3, '<': 3, '<=': 3, '>': 3, '>=': 3, '+': 4, '-': 4,
         '*': 5, '/': 5, '^': 7}
# parse.FNT: the functions the engine cuts out of a longer name (ysin( is y*sin(, kln( k*ln()
MFNT = ('asinh', 'acosh', 'atanh', 'log10', 'sinh', 'cosh', 'tanh', 'asin', 'acos', 'atan',
        'sqrt', 'sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'exp', 'abs', 'log', 'ln')
# Line segments (x1,y1,x2,y2 on a 0..10 grid), four bytes each: compact on the heap.
GLYPHS = {
    'pi': b'\x00\x02\x0a\x02\x03\x02\x03\x0a\x08\x02\x08\x0a',
    'theta': b'\x02\x01\x08\x01\x08\x01\x09\x05\x09\x05\x08\x09\x08\x09\x02\x09\x02\x09\x01\x05\x01\x05\x02\x01\x01\x05\x09\x05',
    'oo': b'\x00\x05\x02\x02\x02\x02\x04\x03\x04\x03\x06\x07\x06\x07\x08\x08\x08\x08\x0a\x05\x0a\x05\x08\x02\x08\x02\x06\x03\x06\x03\x04\x07\x04\x07\x02\x08\x02\x08\x00\x05',
    'sqrt': b'\x00\x06\x02\x05\x02\x05\x04\x0a\x04\x0a\x07\x00\x07\x00\x0a\x00',
    'integral': b'\x09\x00\x06\x00\x06\x00\x05\x02\x05\x02\x04\x08\x04\x08\x03\x0a\x03\x0a\x00\x0a',
    'sum': b'\x0a\x00\x00\x00\x00\x00\x05\x05\x05\x05\x00\x0a\x00\x0a\x0a\x0a',
    '(': b'\x09\x00\x04\x02\x04\x02\x02\x05\x02\x05\x04\x08\x04\x08\x09\x0a',
    ')': b'\x01\x00\x06\x02\x06\x02\x08\x05\x08\x05\x06\x08\x06\x08\x01\x0a',
    '[': b'\x08\x00\x02\x00\x02\x00\x02\x0a\x02\x0a\x08\x0a',
    ']': b'\x02\x00\x08\x00\x08\x00\x08\x0a\x08\x0a\x02\x0a',
    '*': b'\x04\x05\x06\x05\x05\x04\x05\x06',
    '->': b'\x00\x05\x0a\x05\x0a\x05\x06\x02\x0a\x05\x06\x08',
    '<=': b'\x09\x00\x01\x04\x01\x04\x09\x08\x01\x0a\x09\x0a',
    '>=': b'\x01\x00\x09\x04\x09\x04\x01\x08\x01\x0a\x09\x0a',
    '!=': b'\x00\x03\x0a\x03\x00\x07\x0a\x07\x08\x00\x02\x0a'}


# -- the screen ----------------------------------------------------------------------------------

def reset():                                                   #@L 3
    """Forget the cached color: the next color() call sets it."""
    global CURRENT
    CURRENT = None


def color(c):                                                  #@L 6
    """Make c the current color, calling the slow set_color only when it changes."""
    global CURRENT
    if c != CURRENT:
        TD.set_color(c[0], c[1], c[2])
        CURRENT = c


def rect(x, y, w, h, c=None):                                  #@L 5
    """Fill exactly columns x..x+w-1 and rows y..y+h-1, clipped to the screen."""
    if c is not None:
        color(c)
    if x < 0:
        w, x = w + x, 0
    if y < 0:
        h, y = h + y, 0
    w = min(w, W - x)
    h = min(h, H - y)
    if w > 0 and h > 0:
        TD.fill_rect(x - 1, y - 1, w + 1, h + 1)


def text(s, x, top, c=None, clip=SCREEN):                       #@L 5
    """Draw s with its text cell at column x, first ink row top (10 px per character, 15 rows).
    Characters outside the clip columns are dropped; nothing is drawn unless the rows fit."""
    if c is not None:
        color(c)
    if not s or top < clip[1] or top + (ASC + DESC - 1) > clip[3]:
        return
    if x < clip[0]:
        k = (clip[0] - x + CW - 1) // CW
        s = s[k:]
        x += k * CW
    n = (clip[2] - x + 1) // CW
    if n < len(s):
        s = s[:max(0, n)]
    if s:
        TD.draw_text(x, top + TY, s)


def line(x1, y1, x2, y2, c=None):                               #@L 5
    if c is not None:
        color(c)
    clipped_line(x1, y1, x2, y2, SCREEN)


def clipped_line(x1,y1,x2,y2,clip):                             #@L 6
    left,top,right,bottom = clip
    for j in range(8):
        c1 = (1 if x1<left else 2 if x1>right else 0)+(4 if y1<top else 8 if y1>bottom else 0)
        c2 = (1 if x2<left else 2 if x2>right else 0)+(4 if y2<top else 8 if y2>bottom else 0)
        if not c1 and not c2:
            TD.draw_line(x1,y1,x2,y2)
            return
        if c1&c2:
            return
        c = c1 or c2
        if c&12:
            y = top if c&4 else bottom
            x = x1+(x2-x1)*(y-y1)//(y2-y1)
        else:
            x = left if c&1 else right
            y = y1+(y2-y1)*(x-x1)//(x2-x1)
        if c1:
            x1,y1=x,y
        else:
            x2,y2=x,y


def wrap(s, cols):                                             #@L 3
    """s as lines of at most cols characters, broken at spaces where possible."""
    out = []
    while len(s) > cols:
        j = s.rfind(' ', 0, cols + 1)
        if j <= 0:
            j = cols
        out.append(s[:j])
        s = s[j:].lstrip(' ')
    if s:
        out.append(s)
    return out


def clear_cache():                                             #@L 3
    global CACHE_BYTES, ICACHE_BYTES
    del CACHE[:]
    del ICACHE[:]
    CACHE_BYTES = ICACHE_BYTES = 0


# -- the 2D layout: every text is one size, so scripts are raised and lowered ---------------------

def leaf(boxes, s, ti=-1):                                      #@L 6
    if s in GLYPHS:
        w = CW
        decor = [('g',0,2-ASC,s,w,ASC-2)]
    else:
        w = len(s)*CW
        decor = [('t',0,-ASC,s)]
    boxes.append((w,ASC,DESC,(),decor,'text',ti))
    return len(boxes)-1


def row(boxes, ids, gap=2, kind='row', ti=-1):                    #@L 5
    w, a, d = 0, 0, 0
    children = []
    for n in ids:
        b = boxes[n]
        children.append((n,w,0))
        w += b[0]+gap
        if b[1] > a:
            a = b[1]
        if b[2] > d:
            d = b[2]
    boxes.append((max(0,w-gap),a,d,children,(),kind,ti))
    return len(boxes)-1


def frame(boxes, kind, ids, ti=-1):                              #@L 5
    ids = list(ids)
    if kind in ('frac','sup','sqrt','root'):
        for j in range(len(ids)):
            if boxes[ids[j]][5] == 'paren' and (kind != 'sup' or j):
                ids[j] = boxes[ids[j]][3][0][0]
    b = boxes[ids[0]]
    w, a, d = b[:3]
    decor = []
    if kind == 'frac':                  # the bar 2 px wider than the operands each side, and
        c = boxes[ids[1]]               # 2 px clear of the neighbours ('+' never touches it)
        w = max(w,c[0])+8
        ny, dy = -AXIS-1-d, -AXIS+2+c[1]
        children = [(ids[0],(w-b[0])//2,ny),(ids[1],(w-c[0])//2,dy)]
        a, d = a-ny, c[2]+dy
        decor = [('l',2,-AXIS,w-3,-AXIS)]
    elif kind == 'sup':
        c = boxes[ids[1]]
        sy = -(a*9//20)-c[2]
        children = [(ids[0],0,0),(ids[1],w+1,sy)]
        w, a = w+c[0]+1, max(a,c[1]-sy)
    elif kind in ('sqrt','root'):
        pad = max(0,boxes[ids[1]][0]-5) if kind == 'root' else 2
        q = b
        while q[5] == 'row' and len(q[3]) == 1:     # through the slot rows around it
            q = boxes[q[3][0][0]]
        g = 4 if q[5] in ('sqrt','root') else 2     # a nested radical: its own bar 3 rows
        children = [(ids[0],pad+12,0)]              # below this one, not 1
        decor = [('g',pad,-a-g,'sqrt',12,a+d+g),('l',pad+10,-a-g,pad+w+13,-a-g)]
        w, a = w+pad+14, a+g
        if kind == 'root':
            c = boxes[ids[1]]
            children.append((ids[1],0,-(a//2)-c[2]))
            a = max(a,a//2+c[1]+c[2])
    else:
        pad = 4 if kind == 'abs' else 6
        children = [(ids[0],pad,0)]
        if kind == 'abs':
            decor = [('l',1,-a,1,d-1),('l',w+2*pad-2,-a,w+2*pad-2,d-1)]
        else:
            ls, rs = ('[',']') if kind == 'list' else ('(',')')
            decor = [('g',0,-a,ls,pad,a+d),('g',w+pad,-a,rs,pad,a+d)]
        w += 2*pad
    boxes.append((w,a,d,children,decor,kind,ti))
    return len(boxes)-1


def large(boxes, kind, ids, ti):                                 #@L 5
    f = boxes[ids[0]]
    a, d = f[1], f[2]
    children = []
    decor = []
    if kind == 'limit':
        lo = boxes[ids[1]]
        col = max(3*CW,lo[0])
        children = [(ids[1],(col-lo[0])//2,DESC+1+lo[1]),(ids[0],col+5,0)]
        decor = [('t',(col-3*CW)//2,-ASC,'lim')]
        a, d, w = max(a,ASC), max(d,DESC+1+lo[1]+lo[2]), col+5+f[0]
    else:
        # The stroked sign spans the text cell and 2 (sigma) or 4 (integral) rows more each
        # way; the bounds sit close to it, so a sum or integral with a one-level fraction in
        # a bound (or a sum in a fraction) fits the 76 px cap (MATHPRINT.md 5.3, 6.2).
        e = 2 if kind == 'sum' else 4
        top, bottom = -ASC-e, DESC+e
        lower, upper = (ids[2],ids[3]) if len(ids)>3 else (-1,-1)
        col = 12
        gx = 0
        if lower >= 0:
            lo, hi = boxes[lower],boxes[upper]
            if kind == 'sum':               # bounds centered under and over the sigma
                col = max(col,lo[0],hi[0])
                gx = (col-12)//2
                ly, uy = bottom+1+lo[1], top-1-hi[2]
                children.extend([(lower,(col-lo[0])//2,ly),(upper,(col-hi[0])//2,uy)])
            else:                           # integral bounds at the sign's lower and upper end
                ly, uy = bottom-6+lo[1], top+7-hi[2]
                children.extend([(lower,13,ly),(upper,13,uy)])
                col = 13+max(lo[0],hi[0])
            a, d = max(a,hi[1]-uy), max(d,ly+lo[2])
        prefix = col+4
        children.append((ids[0],prefix,0))
        decor.append(('g',gx,top,'integral' if kind=='integral' else 'sum',12,bottom-top))
        a, d, w = max(a,-top), max(d,bottom), prefix+f[0]
        if kind == 'integral':
            decor.append(('t',w+4,-ASC,'d'))
            v = boxes[ids[1]]               # the variable slot, on the baseline: its height
            children.append((ids[1],w+5+CW,0))  # counts too (a template typed into dx)
            w += 5+CW+v[0]
            a, d = max(a,v[1]), max(d,v[2])
    boxes.append((w,a,d,children,decor,kind,ti))
    return len(boxes)-1


def tree(code):                                                 #@L 4
    specs, stack, depths = [],[],[]
    for item in code:
        op = item[0]
        count = 0
        if op == 'P':
            count = 1
        elif op == 'o':
            count = 1 if item[1] in ('neg','!') else 2
        elif op == 'F':
            count = item[2]
        elif op == 'L':
            count = item[1]
        children = stack[len(stack)-count:] if count else []
        if len(children) != count:
            raise ValueError('layout stack')
        if count:
            del stack[len(stack)-count:]
        depth = 0
        for n in children:
            depth = max(depth,depths[n]+1)
        if depth > 24:
            raise ValueError('layout nesting')
        depths.append(depth)
        specs.append((item,children))
        stack.append(len(specs)-1)
    if len(stack) != 1:
        raise ValueError('layout root')
    return specs


def measure(specs):                                             #@L 4
    boxes, roots = [],[]
    for i in range(len(specs)):
        it, children = specs[i]
        ids = []
        for n in children:
            ids.append(roots[n])
        kind, ti = it[0],it[-1]
        if kind in ('n','s'):
            s = it[1]
            if kind == 'n':
                s = str(s[0]) if type(s) is tuple else PR.fdec10(s)
            root = leaf(boxes,s,ti)
        elif kind == 'P':
            root = frame(boxes,'paren',ids,ti)
        elif kind == 'o':
            op = it[1]
            if op in ('/','^'):
                root = frame(boxes,'frac' if op=='/' else 'sup',ids,ti)
            else:
                sign = leaf(boxes,'-' if op=='neg' else op,ti)
                rowids = [sign,ids[0]] if op=='neg' else [ids[0],sign] if op=='!' else [ids[0],sign,ids[1]]
                if op=='*':
                    right = specs[children[1]][0]
                    if right[0] in ('s','F','P'):
                        rowids = ids
                root = row(boxes,rowids,2,'row',ti)
        else:
            name = it[1] if kind=='F' else ''
            if name in ('sqrt','abs') and len(ids)==1:
                root = frame(boxes,name,ids,ti)
            elif name=='surd' and len(ids)==2:
                root = frame(boxes,'root',ids,ti)
            elif name=='integrate' and len(ids) in (2,4):
                root = large(boxes,'integral',ids,ti)
            elif name=='sum' and len(ids)==4:
                lower = row(boxes,[ids[1],leaf(boxes,'='),ids[2]],1)
                root = large(boxes,'sum',[ids[0],ids[1],lower,ids[3]],ti)
            elif name=='limit' and len(ids)==3:
                lower = row(boxes,[ids[1],leaf(boxes,'->'),ids[2]],1)
                root = large(boxes,'limit',[ids[0],lower],ti)
            elif name=='diff' and len(ids)==2:
                dn = leaf(boxes,'d')
                den = row(boxes,[leaf(boxes,'d'),ids[1]],0)
                frac = frame(boxes,'frac',[dn,den])
                root = row(boxes,[frac,ids[0]],4,'derivative',ti)
            else:
                joined = []
                for j in range(len(ids)):
                    if j:
                        joined.append(leaf(boxes,','))
                    joined.append(ids[j])
                root = row(boxes,joined,2)
                if kind=='L':
                    if ti>=0:
                        root = frame(boxes,'list',[root],ti)
                else:
                    root = frame(boxes,'paren',[root],ti)
                    label = 'arc'+name[1:] if name in ('asin','acos','atan') else name
                    root = row(boxes,[leaf(boxes,label),root],1,'call',ti)
        roots.append(root)
    return boxes,roots[-1]


def place(boxes, root):                                        #@L 4
    dl = []
    work = [(root,0,boxes[root][1])]
    while work:
        n,x,y = work.pop()
        b = boxes[n]
        for item in b[4]:
            if item[0]=='l':
                dl.append(('l',x+item[1],y+item[2],x+item[3],y+item[4]))
            else:
                dl.append((item[0],x+item[1],y+item[2])+item[3:])
        for j in range(len(b[3])-1,-1,-1):
            child,dx,dy = b[3][j]
            work.append((child,x+dx,y+dy))
    return dl


def layout(s, width=300, height=92):                            #@L 3
    """The display list of an answer text in a width x height view (cached). A text that does
    not parse, or nests too deeply, is laid out as one plain line."""
    global CACHE_BYTES
    cache = CACHE
    key = (s,width,height)
    for j in range(len(cache)):
        if cache[j][0]==key:            # least recently used goes first (MATHPRINT.md 7.3)
            cached = cache.pop(j)
            cache.append(cached)
            return cached[1]
    try:
        code = P.rpn(P.lex(s))
        if len(code)>400:
            raise ValueError('layout size')
        boxes,root = measure(tree(code))
    except Exception:
        boxes = []
        root = leaf(boxes,s[:4000])
    dl = place(boxes,root)
    w,a,d = boxes[root][:3]
    result = (dl,w,a,a+d)
    cost = len(dl)*24+len(s)
    if cost<=4096:
        while cache and (len(cache)>=6 or CACHE_BYTES+cost>4096):
            CACHE_BYTES-=cache.pop(0)[2]
        cache.append((key,result,cost))
        CACHE_BYTES+=cost
    return result


def render(dl, dx=0, clip=SCREEN, dy=0):                        #@L 4
    color(COLORS['INK'])
    for item in dl:
        x,y = item[1]+dx,item[2]+dy
        if item[0]=='l':
            clipped_line(x,y,item[3]+dx,item[4]+dy,clip)
        elif item[0]=='g':
            glyph(item,x,y,clip)
        else:
            text(item[3],x,y,None,clip)


def glyph(item, x, y, clip):                                   #@L 5
    """Stroke the glyph item ('g', _, _, name, w, h) with its cell at x, y."""
    w = item[4] - 1
    h = item[5] - 1
    g = GLYPHS[item[3]]
    for j in range(0, len(g), 4):
        clipped_line(x + g[j]*w//10, y + g[j+1]*h//10, x + g[j+2]*w//10, y + g[j+3]*h//10, clip)


# -- MathPrint: the editor's engine-free 2D layout (docs/notes/MATHPRINT.md section 5) ------------
# A parse node is a list [kind, start, end, kids, aux] over the buffer: L leaf, E empty, R row,
# N prefix sign, S slot, Q stacked fraction, W power, G group, C call, T template. Boxes keep
# the 2D layout's format; a box's ti is the node it draws (or -1), for the caret marks.

def mflat(s):                                                  #@L 4
    """True when s has no 2D construct (section 5.1), so it is drawn and edited as a 1D row. An
    empty call argument or group is one too (QPL Q4): its box is a slot, f(,), sin() or 2*()."""
    if '^' in s or ')/(' in s or 'pi' in s or 'theta' in s or 'oo' in s or '()' in s or \
            '(,' in s or ',,' in s or ',)' in s:
        return False
    i = s.find('(')
    while i >= 0:
        j = mname(s, i)
        if j >= 0 and s[j:i] in TPL:
            return False
        i = s.find('(', i + 1)
    return True


def mname(s, o):                                               #@L 5
    """Where the call name before the '(' at o starts as the engine reads it (letters and
    digits before o, leading digits dropped, then mcall), or -1: no name or a product."""
    j = o
    while j and (s[j-1].isalpha() or s[j-1].isdigit()):
        j -= 1
    while j < o and s[j].isdigit():
        j += 1
    return mcall(s, j, o) if j < o else -1


def mcall(s, i, j):                                            #@L 6
    """Where the call name starts in the name s[i:j] right before a '(' at j, as the engine
    reads it (parse.iscall, ti_rewrite, ti_implicit): -1 for a product (one letter but f, g, h:
    x(x+1) is x*(x+1); pi(2)); a later index when the letters before a function the engine
    cuts out are a product (ysin( is y*sin(, xsqrt( x*sqrt(; before surd and the template
    commands at most two letters); else i."""
    if j - i == 1:
        return i if s[i] in 'fgh' else -1
    nm = s[i:j]
    if nm == 'pi' or nm == 'oo' or nm == 'theta':
        return -1
    if j - i > 2 and nm.isalpha() and nm not in MFNT:
        for t in MFNT:
            if nm.startswith(t):
                return i                # sinsin( stays whole (parse.fnpre)
        for k in range(1, j - i - 1):
            t = nm[k:]
            if t in MFNT or k <= 2 and t in TPL:
                return i + k
    return i


def mstop(s, i):                                               #@L 4
    """Whether caret position i of a flat line is a stop: not inside a call name before its '('
    (section 4.1; a cut letter or a product's letter is no call name, as in mcall)."""
    n = len(s)
    j = i
    while j < n and (s[j].isalpha() or s[j].isdigit()):
        j += 1
    if i <= 0 or j >= n or s[j] != '(':
        return True
    k = i
    while k and (s[k-1].isalpha() or s[k-1].isdigit()):
        k -= 1
    while k < i and s[k].isdigit():
        k += 1
    if k >= i or not s[k].isalpha():
        return True
    k = mcall(s, k, j)
    return k < 0 or i <= k


def mlex(s):                                                   #@L 4
    """Tokens (kind, start, end) of a buffer: n number, a name, f name before '(', A ans(),
    o operator, ( and ) any bracket, ',' comma, ! postfix ! or ', ? anything else."""
    out = []
    n = len(s)
    i = 0
    while i < n:
        c = s[i]
        j = i + 1
        if c.isdigit() or c == '.':
            while j < n and (s[j].isdigit() or s[j] == '.'):
                j += 1
            if j < n and s[j] == 'E' and s[j-1].isdigit():
                m = j + 1
                if m < n and (s[m] == '-' or s[m] == '+'):
                    m += 1
                if m < n and s[m].isdigit():
                    j = m + 1
                    while j < n and s[j].isdigit():
                        j += 1
            k = 'n'
        elif c.isalpha():
            while j < n and (s[j].isalpha() or s[j].isdigit()):
                j += 1
            k = 'a'
            if j == i + 3 and s.find('ans()', i, i + 5) == i:
                j = i + 5
                k = 'A'
            elif j < n and s[j] == '(':
                m = mcall(s, i, j)
                if m > i:                       # xsqrt( is x, then the call sqrt(
                    out.append(('a', i, m))
                    i = m
                if m >= 0:
                    k = 'f'
        elif c in '([{':
            k = '('
        elif c in ')]}':
            k = ')'
        elif c == ',':
            k = ','
        elif j < n and (s[j] == '=' and c in '<>!:' or c == '=' and s[j] == '>'):
            j += 1
            k = 'o'
        elif c in '+-*/^=<>':
            k = 'o'
        elif c == '!' or c == "'":
            k = '!'
        else:
            k = '?'
        out.append((k, i, j))
        i = j
    return out


def mparse(s, tk, mode):                                       #@L 4
    """A tolerant shunting-yard over the tokens (section 5.2): (nodes, root slot), or None past
    the caps (24 open groups, 192 nodes). It never raises: a missing operand is an E node, a
    juxtaposition an implicit product, a stray closer or other character clings to its operand
    as text, and an unclosed group ends at len(s). Mode 1 stacks every '/', mode 2 only a '/'
    between two groups (..)/(..)."""
    nodes = []
    vals = []
    ops = [['(', -1, -1, [], 0]]        # openers: ['(', at, name start, slots, slot start]
    expect = True                       # an operand comes next
    trail = False                       # the last token was an operator (not ^)
    fs = -1
    depth = 0
    for t in tk:
        k, a, b = t
        if len(nodes) > 192:
            return None
        if k == ')' and not depth or k == '!' and expect:
            k = '?'
        if k == 'o':
            o = s[a:b]
            if expect and (o == '-' or o == '+'):
                nodes.append(['L', a, b, (), 2])
                ops.append(('N', o, 6, len(nodes) - 1))
                trail = True
                continue
            if expect:
                nodes.append(['E', a, a, (), 0])
                vals.append(len(nodes) - 1)
            nodes.append(['L', a, b, (), 2])
            mpush(nodes, vals, ops, ('o', o, MPREC[o], len(nodes) - 1), mode)
            expect = True
            trail = o != '^'
        elif k == ',' or k == ')':
            mshut(s, nodes, vals, ops, a, 0 if k == ',' else 1, expect, trail, mode)
            if k == ')':
                depth -= 1
            expect = k == ','
            trail = False
        elif k == '?' or k == '!':
            nodes.append(['L', a, b, (), 0])
            if expect:
                ops.append(('P', '', 8, len(nodes) - 1))
            else:
                v = vals.pop()
                nodes.append(['R', nodes[v][1], b, [v, len(nodes) - 1], 0])
                vals.append(len(nodes) - 1)
        else:
            if not expect:
                mpush(nodes, vals, ops, ('o', '*', 5, -1), mode)
            expect = True
            trail = False
            if k == 'f':
                fs = a
            elif k == '(':
                depth += 1
                if depth > 24:
                    return None
                ops.append(['(', a, fs, [], a + 1])
                fs = -1
            else:
                g = 0                   # 1 a glyph; 4 a name the engine may cut (ab: a*b)
                if k == 'a' and b - a > 1:
                    t = s[a:b]
                    if t == 'pi' or t == 'oo' or t == 'theta':
                        g = 1
                    elif t.isalpha():
                        g = 4
                nodes.append(['A' if k == 'A' else 'L', a, b, (), g])
                vals.append(len(nodes) - 1)
                expect = False
    n = len(s)
    while depth:
        mshut(s, nodes, vals, ops, n, 2, expect, trail, mode)
        depth -= 1
        expect = trail = False
    root = mshut(s, nodes, vals, ops, n, 2, expect, trail, mode)
    if len(nodes) > 192:
        return None
    return nodes, root


def mpush(nodes, vals, ops, op, mode):                         #@L 5
    """Push a binary operator after reducing those that bind at least as tightly (^, => and
    := are right-associative). op: ('o', text, precedence, leaf node or -1)."""
    p = op[2]
    right = op[1] == '^' or op[1] == '=>' or op[1] == ':='
    while ops[-1][0] != '(':
        q = ops[-1][2]
        if q > p or q == p and not right:
            mreduce(nodes, vals, ops.pop(), mode)
        else:
            break
    ops.append(op)


def mshut(s, nodes, vals, ops, pos, how, expect, trail, mode):    #@L 5
    """End the innermost argument at pos (how 0: a comma, 1: its closer, 2: the end of the line)
    as a slot. Unless a comma, then build the group, call or template; the root returns its
    slot (a top-level comma list is an unbracketed group)."""
    if expect:
        nodes.append(['E', pos, pos, (), 1 if trail else 0])
        vals.append(len(nodes) - 1)
    while ops[-1][0] != '(':
        mreduce(nodes, vals, ops.pop(), mode)
    op = ops[-1]
    args = op[3]
    nodes.append(['S', op[4], pos, [vals.pop()], [-1, len(args)]])
    args.append(len(nodes) - 1)
    if not how:
        op[4] = pos + 1
        return -1
    ops.pop()
    at = op[1]
    f = op[2]
    n = len(nodes)
    end = pos + 1 if how == 1 else pos
    if at < 0:
        if len(args) == 1:
            return args[0]
        nodes.append(['G', 0, pos, args, 8])
        nodes.append(['S', 0, pos, [n], [-1, 0]])
    elif f >= 0:
        nm = s[f:at]
        m = len(args)
        if how == 1 and nm in TPL and m in TPL[nm] and not (nm == 'limit' and '=' in s[at:pos]):
            nodes.append(['T', f, end, args, [at, True]])
            # The optional boxes (flag 2: tidy drops them, ENTER skips them, MATHPRINT.md
            # 2.2): the base of log_b, the order of d^n/dx^n, the direction of lim (a lone
            # sign there: its empty operand is not drawn, flag 4), both integral bounds.
            t = TPL[nm]
            e = nodes[nodes[args[-1]][3][0]]
            g = nodes[nodes[args[2]][3][0]] if m == 4 and nm == 'integrate' else e
            if e[0] == 'N' and m == 4 and nm == 'limit' and e[2] - e[1] == 1:
                e = g = nodes[e[3][1]]
                e[4] |= 4
            if e[0] == 'E' and g[0] == 'E' and m == t[-1] and (len(t) > 1 or nm == 'log'):
                e[4] |= 2
                g[4] |= 2
        else:                           # 2: a name the engine may cut (ab( is a*b*()
            nodes.append(['C', f, end, args, [at, how == 1,
                                              at - f > 1 and nm not in MFNT and nm not in TPL]])
            # Empty boxes after a command's required arguments are optional (flag 2, QPL Q4):
            # only a trailing run of them, so f(a,,b) keeps its meaning, and none past the
            # command's last argument (log(8,2,)) (ARGS; the form with m arguments first:
            # taylor(f,x,0,), desolve(eq,x,))
            j = ARGS.find(';' + nm + '#' + str(m) + ':')
            if j < 0:
                j = ARGS.find(';' + nm + ':')
            if j >= 0:
                j = ARGS.find(':', j) + 1
                r = int(ARGS[j])
                q = ARGS.find(';', j) - j - 2
                if ARGS[j + q + 1] == '*':
                    q = 99
                j = m - 1
                if j >= q:
                    j = -1
                while j >= r and nodes[nodes[args[j]][3][0]][0] == 'E':
                    nodes[nodes[args[j]][3][0]][4] |= 2
                    j -= 1
    else:
        fl = 0
        if how == 1:
            fl = 6 if len(args) == 1 and s[at] == '(' and s[pos] == ')' else 4
        nodes.append(['G', at, end, args, fl])
    for j in args:
        nodes[j][4][0] = n
    if at < 0:
        return n + 1
    vals.append(n)
    return n


def mreduce(nodes, vals, op, mode):                            #@L 6
    """Apply one operator to the operand stack: a sign, a clinging character, a fraction, a
    power, or a row (extended in place, so a long sum stays O(n))."""
    b = vals.pop()
    nb = nodes[b]
    if op[0] != 'o':
        nodes.append(['N' if op[0] == 'N' else 'R', nodes[op[3]][1], nb[2], [op[3], b], 0])
        vals.append(len(nodes) - 1)
        return
    a = vals.pop()
    o = op[1]
    n = len(nodes)
    pb = nb[0] == 'G' and nb[4] & 2
    if o == '/' or o == '^':            # a name the engine may cut outside brackets in the
        st = [b]                        # right operand (x^ab is b*x^a, 1/(-2)^ab is b/(-2)^a):
        while st:                       # its extent is unknown, so the operator stays inline
            x = nodes[st.pop()]
            k = x[0]
            if k == 'L' and x[4] & 4 or k == 'C' and x[4][2]:
                o = ''
                break
            if k == 'N' or k == 'R':
                for c in x[3]:
                    st.append(c)
            elif k == 'W':
                st.append(x[3][0])
                st.append(x[4][1])
    if o == '/':
        sg = -1
        if nodes[a][0] == 'N':          # -a/b: the sign stays outside the bar
            sg = a
            a = nodes[a][3][1]
        elif mode == 2 and pb and nodes[a][0] == 'R' and not nodes[a][4] and \
                nodes[nodes[a][3][-1]][0] == 'G' and nodes[nodes[a][3][-1]][4] & 2:
            sg = a                      # 2*(a)/(b): the same value as 2*((a)/(b)), so the
            a = nodes[a][3][-1]         # group after * or a juxtaposition is the numerator
        na = nodes[a]
        pa = na[0] == 'G' and na[4] & 2
        if mode == 1 or pa and pb:
            ka = a
            kb = b
            if pa:
                na[4] |= 1
                ka = na[3][0]
                nodes[ka][4] = [n, 0]
            if pb:
                nb[4] |= 1
                kb = nb[3][0]
                nodes[kb][4] = [n, 1]
            nodes.append(['Q', na[1], nb[2], [ka, kb], (a, b)])
            if sg >= 0:
                nodes[sg][3][-1] = n
                nodes[sg][2] = nb[2]
                n = sg
            vals.append(n)
            return
        if sg >= 0:
            a = sg
    elif o == '^':
        sl = n + 1
        if pb:
            nb[4] |= 1
            sl = nb[3][0]
            nodes[sl][4] = [n, 0]
        nodes.append(['W', nodes[a][1], nb[2], [a, sl], (nodes[op[3]][1], b)])
        if not pb:
            nodes.append(['S', nb[1], nb[2], [b], [n, 0]])
        vals.append(n)
        return
    na = nodes[a]
    if na[0] == 'R':
        kids = na[3]
    else:
        kids = [a]
        na = ['R', na[1], 0, kids, 0]
        nodes.append(na)
        a = n
    # Append the operator's leaf, then b (or b's row items). A text leaf that continues the
    # previous one is merged into it (glyphs never; in mode 1 neither are operators, which may
    # be glyphs there), so a run like 2+3*x is one leaf, one box and one text item.
    mask = 1 if mode == 2 else 3
    last = nodes[kids[-1]]
    more = nb[3] if nb[0] == 'R' else (b,)
    j = -1
    while j < len(more):
        c = op[3] if j < 0 else more[j]
        j += 1
        if c < 0:
            continue
        x = nodes[c]
        if last[0] == 'L' and x[0] == 'L' and not (last[4] | x[4]) & mask and last[2] == x[1]:
            last[2] = x[2]
            last[4] |= x[4]             # keeps 4, a name the engine may cut
        else:
            kids.append(c)
            last = x
    na[2] = nb[2]
    na[4] = 1 if op[1] == '/' else 0    # a row that ends in a '/' keeps a later one inline
    vals.append(a)


def tleaf(boxes, i0, i1, txt, ti):                             #@L 5
    """A text box, always drawn as text: the buffer slice [i0, i1) (cut when the display list is
    built, so runs merge), or txt when i0 < 0."""
    w = CW * (i1 - i0) if i0 >= 0 else CW * len(txt)
    boxes.append((w, ASC, DESC, (), (('s', 0, -ASC, txt, i0, i1),), 'text', ti))
    return len(boxes) - 1


def mbox(s, nodes, root, mode):                                #@L 4
    """Boxes for the nodes under root, children first through an explicit stack, built with the
    2D layout's row/frame/large/leaf (section 3). Returns (boxes, root box)."""
    boxes = []
    bx = [-1] * len(nodes)
    st = [root]
    while st:
        n = st.pop()
        nd = nodes[n]
        k = nd[0]
        kids = nd[3]
        if kids and bx[n] == -1:
            bx[n] = -2
            st.append(n)
            for c in kids:
                st.append(c)
            continue
        a = nd[1]
        e = nd[2]
        if k == 'L':
            if nd[4] & 1 or mode == 1 and nd[4] & 2 and s[a:e] in GLYPHS:
                bx[n] = leaf(boxes, s[a:e], n)
            else:
                bx[n] = tleaf(boxes, a, e, None, n)
            continue
        if k == 'E':
            boxes.append((0 if nd[4] & 4 else CW, ASC, DESC, (),
                          (('b', 1, -11, 8, 13, a, nd[4]),) if mode == 2 and not nd[4] & 4
                          else (), 'empty', n))
            bx[n] = len(boxes) - 1
            continue
        if k == 'S':                            # a slot: a row of its one item
            c = bx[kids[0]]
            cb = boxes[c]
            boxes.append((cb[0], cb[1], cb[2], [(c, 0, 0)], (), 'row', n))
            bx[n] = len(boxes) - 1
            continue
        sb = []
        for c in kids:
            sb.append(bx[c])
        if k == 'A':
            r = tleaf(boxes, -1, -1, 'Ans', n)
        elif k == 'R' or k == 'N':
            r = row(boxes, sb, 0, 'row', -1)
        elif k == 'Q':
            for j in range(2):
                if boxes[sb[j]][5] != 'row':
                    sb[j] = row(boxes, [sb[j]], 0)
            r = frame(boxes, 'frac', sb, n)
        elif k == 'W':
            r = frame(boxes, 'sup', sb, n)
        elif k == 'T':
            at = nd[4][0]
            nm = s[a:at]
            if nm == 'sqrt' or nm == 'abs':
                r = frame(boxes, nm, sb, n)
            elif nm == 'exp':
                r = frame(boxes, 'sup', [tleaf(boxes, -1, -1, 'e', -1), sb[0]], n)
            elif nm == 'surd':
                r = frame(boxes, 'root', sb, n)
                ch = boxes[r][3]
                ch[0], ch[1] = ch[1], ch[0]     # the index is drawn, and visited, first
            elif nm == 'integrate':
                r = large(boxes, 'integral', sb, n)
            elif nm == 'sum':
                lo = row(boxes, [sb[1], tleaf(boxes, -1, -1, '=', -1), sb[2]], 0)
                r = large(boxes, 'sum', [sb[0], sb[1], lo, sb[3]], n)
            elif nm == 'limit':
                p = sb[2]
                if len(sb) > 3:             # the direction: + or - over a (a history input's
                    q = sb[3]               # 1 or -1 too)
                    t = s[nodes[kids[3]][1]:nodes[kids[3]][2]]
                    if mode == 1 and (t == '1' or t == '-1'):
                        q = tleaf(boxes, -1, -1, '+-'[len(t) - 1], -1)
                    p = frame(boxes, 'sup', [sb[2], q])
                lo = row(boxes, [sb[1], leaf(boxes, '->'), p], 0)
                r = large(boxes, 'limit', [sb[0], lo], n)
            else:                               # diff and log: the operand u in parens
                u = sb[0]
                if boxes[u][1] <= ASC and boxes[u][2] <= DESC:
                    p = row(boxes, [tleaf(boxes, at, at + 1, None, -1), u,
                                    tleaf(boxes, e - 1, e, None, -1)], 0)
                else:
                    p = frame(boxes, 'paren', [u])
                if nm == 'diff':        # d/d[]([]); d^n/d[]^n([]): the order is typed in
                    num = tleaf(boxes, -1, -1, 'd', -1)     # the denominator and mirrored
                    x = sb[1]                               # over the d (no stop)
                    if len(sb) > 2:
                        q = nodes[kids[2]]
                        c = boxes[bx[q[3][0]]]  # one leaf or empty box: a copy, else its text
                        if c[3]:
                            c = boxes[tleaf(boxes, -1, -1, s[q[1]:q[2]], -1)]
                        boxes.append(c[:6] + (-1,))
                        num = frame(boxes, 'sup', [num, len(boxes) - 1])
                        x = frame(boxes, 'sup', [x, sb[2]])
                    den = row(boxes, [tleaf(boxes, -1, -1, 'd', -1), x], 0)
                    fr = frame(boxes, 'frac', [num, den])
                    r = row(boxes, [fr, p], 2, 'row', n)
                else:                           # log_b: the base lowered 6 px at x 30
                    lb = tleaf(boxes, a, a + 3, None, -1)
                    bb = boxes[sb[1]]
                    pb = boxes[p]
                    boxes.append((3*CW + bb[0] + pb[0], max(ASC, pb[1], bb[1] - 6),
                                  max(DESC, pb[2], 6 + bb[2]),
                                  [(lb, 0, 0), (sb[1], 3*CW, 6), (p, 3*CW + bb[0], 0)], (),
                                  'log', n))
                    r = len(boxes) - 1
        else:                                   # G and C: brackets (or name) and arguments
            one = True
            for c in sb:
                if boxes[c][1] > ASC or boxes[c][2] > DESC:
                    one = False
            closed = nd[4][1] if k == 'C' else nd[4] & 4
            at = nd[4][0] if k == 'C' else a
            items = []
            for j in range(len(sb)):
                if j:
                    c = nodes[kids[j - 1]][2]
                    items.append(tleaf(boxes, c, c + 1, None, -1))
                items.append(sb[j])
            if k == 'G' and nd[4] & 8:
                r = row(boxes, items, 0, 'row', -1)
            elif one or not closed:
                items.insert(0, tleaf(boxes, a, at + 1, None, -1))
                if closed:
                    items.append(tleaf(boxes, e - 1, e, None, -1))
                r = row(boxes, items, 0, 'row', n)
            elif k == 'C':
                p = frame(boxes, 'paren', [row(boxes, items, 0)])
                r = row(boxes, [tleaf(boxes, a, at, None, -1), p], 0, 'row', n)
            else:
                r = frame(boxes, 'list' if s[a] == '[' else 'paren', [row(boxes, items, 0)], n)
        if mode == 2 and (k == 'T' or k == 'Q'):
            b = boxes[r]
            boxes[r] = (b[0] + TGAP, b[1], b[2], b[3], b[4], b[5], b[6])
        bx[n] = r
    return boxes, bx[root]


def mmark(M, i, x, y, dep, sl):                                #@L 5
    """Record caret stop i at x, text top y, in slot sl of depth dep, unless it has a record
    from a slot at least as deep (section 4.1: ties keep the first emission)."""
    if M[2][i] < 0 or dep > M[2][i]:
        M[0][i] = x
        M[1][i] = y
        M[2][i] = dep
        M[3][i] = M[5]
        M[4][i] = sl
        M[5] += 1


def mplace(s, nodes, boxes, root, mode):                       #@L 4
    """The display list of the boxes under root (text merged into one item per buffer run) and,
    in mode 2, the caret map of section 4.1: (dl, X, Y, None, ORD, SL, SLOTS, CONS, EMPTY); a
    stop's rank is its index in ORD (the slot that held RK stays None)."""
    n = len(s)
    dl = []
    M = None
    slots = []
    cons = []
    empty = []
    if mode == 2:
        M = [[-1] * (n + 1), [-1] * (n + 1), [-1] * (n + 1), [0] * (n + 1), [-1] * (n + 1), 0]
        mx, my, dp, mq, ms = M[0], M[1], M[2], M[3], M[4]
    ra = -1                             # the open text run: s[ra:rb] at rx, ry (none: -1)
    rb = rx = ry = 0
    work = [(0, root, 0, boxes[root][1], 0, -1)]
    while work:
        tag, bi, x, y, dep, sl = work.pop()
        if tag:                         # mmark, inline: one stop after a construct
            if dp[bi] < 0 or dep > dp[bi]:
                mx[bi] = x
                my[bi] = y
                dp[bi] = dep
                mq[bi] = M[5]
                ms[bi] = sl
                M[5] += 1
            continue
        b = boxes[bi]
        for item in b[4]:
            k = item[0]
            if k == 's' and item[4] >= 0:       # a buffer slice: extend the open run
                tx = x + item[1]
                ty = y + item[2]
                if ra >= 0 and ry == ty and rb == item[4] and rx + CW * (rb - ra) == tx:
                    rb = item[5]
                    continue
                if ra >= 0:
                    dl.append(('t', rx, ry, s[ra:rb]))
                rx = tx
                ry = ty
                ra = item[4]
                rb = item[5]
                continue
            if ra >= 0:
                dl.append(('t', rx, ry, s[ra:rb]))
                ra = -1
            if k == 'l':
                dl.append(('l', x + item[1], y + item[2], x + item[3], y + item[4]))
            elif k == 't' or k == 's':
                dl.append(('t', x + item[1], y + item[2], item[3]))
            else:
                dl.append((k, x + item[1], y + item[2]) + item[3:])
        ch = b[3]
        ti = b[6]
        if M is not None and ti >= 0:
            nd = nodes[ti]
            k = nd[0]
            a = nd[1]
            e = nd[2]
            top = y - ASC
            if k == 'L' and not nd[4] & 1:      # every index of a text leaf (mmark, inline)
                q = M[5]
                for i in range(a, e + 1):
                    if dp[i] < 0 or dep > dp[i]:
                        mx[i] = x + CW * (i - a)
                        my[i] = top
                        dp[i] = dep
                        mq[i] = q
                        ms[i] = sl
                        q += 1
                M[5] = q
            elif k == 'L' or k == 'A':
                mmark(M, a, x, top, dep, sl)
                mmark(M, e, x + b[0], top, dep, sl)
            elif k == 'E':
                mmark(M, a, x, top, dep, sl)
                empty.append((a, nd[4]))
            elif k == 'S':
                own = nd[4][0]
                if own < 0:
                    slots.append((a, e, 'R', 0, n, 0, 1, False, dep))
                else:
                    o = nodes[own]
                    ok = o[0]
                    os = o[1]
                    ns = len(o[3])
                    hid = ok == 'T' or ok == 'Q'
                    if ok == 'W':
                        os = o[4][0]
                        ns = 1
                        g = nodes[o[4][1]]
                        hid = g[0] == 'G' and g[4] & 1 != 0
                    dep += 1
                    slots.append((a, e, ok, os, o[2], nd[4][1], ns, hid, dep))
                sl = len(slots) - 1
                mmark(M, a, x, top, dep, sl)
                work.append((1, e, x + b[0], top, dep, sl))
            else:                               # a construct: Q W T C G
                os = nd[4][0] if k == 'W' else a
                cons.append((a, os, e, k))
                work.append((1, e, x + b[0], top, dep, sl))
                if k == 'W':                    # base, the stop after it (at ^), exponent
                    c = ch[1]
                    work.append((0, c[0], x + c[1], y + c[2], dep, sl))
                    work.append((1, os, x + boxes[ch[0][0]][0], top, dep, sl))
                    work.append((0, ch[0][0], x, y, dep, sl))
                    continue
                mmark(M, a, x, top, dep, sl)
        for j in range(len(ch) - 1, -1, -1):
            c = ch[j]
            work.append((0, c[0], x + c[1], y + c[2], dep, sl))
    if ra >= 0:
        dl.append(('t', rx, ry, s[ra:rb]))
    if M is None:
        return dl
    order = [-1] * M[5]
    for i in range(n + 1):
        if dp[i] >= 0:
            order[mq[i]] = i
    ORD = []
    for i in order:
        if i >= 0:
            ORD.append(i)
    return dl, mx, my, None, ORD, ms, slots, cons, empty


def mlayout(s, mode):                                          #@L 3
    """The MathPrint layout of a buffer (section 5.2). Mode 2, the editor (never cached):
    (s, dl, w, asc, desc, X, Y, None, ORD, SL, SLOTS, CONS, EMPTY). Mode 1, a history input
    (cached in ICACHE; every '/' stacked; no caret map or empty boxes): (dl, w, asc, desc).
    None past the caps of section 5.3: 160 characters, 24 open groups, 192 nodes, 76 px high.
    Display-list coordinates are relative to the content's top-left corner."""
    global ICACHE_BYTES
    cache = ICACHE
    if mode == 1:
        for j in range(len(cache)):
            if cache[j][0] == s:        # least recently used goes first (section 7.3)
                c = cache.pop(j)
                cache.append(c)
                return c[1]
    res = None
    if len(s) <= 160:
        try:
            r = mparse(s, mlex(s), mode)
            if r is not None:
                boxes, root = mbox(s, r[0], r[1], mode)
                w, a, d = boxes[root][:3]
                if a + d <= 76:
                    p = mplace(s, r[0], boxes, root, mode)
                    res = (p, w, a, d) if mode == 1 else (s, p[0], w, a, d) + p[1:]
                boxes = None
            r = None
        except MemoryError:             # a history input is drawn 1D, and the failure is
            r = boxes = p = res = None  # cached like a result: no retry until the next job
            if mode != 1:
                raise
    if mode == 1:
        # the retained heap measured on MicroPython 1.12 (32-bit): ~128 B per entry, 32 B per
        # display-list item and 4 B per character of text (section 9.3)
        cost = 128 + 32 * (len(res[0]) if res is not None else 0) + 4 * len(s)
        if cost <= 4096:
            while cache and (len(cache) >= 6 or ICACHE_BYTES + cost > 4096):
                ICACHE_BYTES -= cache.pop(0)[2]
            cache.append((s, res, cost))
            ICACHE_BYTES += cost
    return res


def mrender(dl, dx, dy, clip, x0, x1, c, boxes, cur=-1):        #@L 4
    """Draw in color c the display-list items of one kind (boxes: the empty-slot boxes; else
    text, lines and glyphs) whose screen x-range meets [x0, x1], clipped to clip. An empty box
    flagged as the trailing operand at buffer index cur is skipped (section 5.4)."""
    first = True
    for item in dl:
        k = item[0]
        if (k == 'b') != boxes:
            continue
        x = item[1] + dx
        if k == 't':
            r = x + CW * len(item[3]) - 1
        elif k == 'l':
            r = max(x, item[3] + dx)
            x = min(x, item[3] + dx)
        elif k == 'g':
            r = x + item[4] - 1
        else:
            r = x + item[3] - 1
            if item[6] & 1 and item[5] == cur:
                continue
        if x > x1 or r < x0:
            continue
        cut = x < clip[0] or r > clip[2]
        if cut and k != 't' and k != 'b' and (k == 'g' or r - x < 3 * CW or item[2] != item[4]):
            continue                    # a stroke cut by the view edge would lose its text,
        if first:                       # which is clipped by whole characters (section 6.3)
            color(c)
            first = False
        x = item[1] + dx
        y = item[2] + dy
        if k == 't':
            text(item[3], x, y, None, clip)
        elif k == 'l':
            if cut:                     # a wide rule: kept 2 px clear of the scroll markers
                clipped_line(x, y, item[3] + dx, item[4] + dy,
                             (clip[0] + 2, clip[1], clip[2] - 2, clip[3]))
            else:
                clipped_line(x, y, item[3] + dx, item[4] + dy, clip)
        elif k == 'g':
            glyph(item, x, y, clip)
        else:                           # an empty slot: a 1 px outline (as on the Nspire)
            b = y + item[4] - 1
            clipped_line(x, y, r, y, clip)
            clipped_line(x, b, r, b, clip)
            clipped_line(x, y + 1, x, b - 1, clip)
            clipped_line(r, y + 1, r, b - 1, clip)
