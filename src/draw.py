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
PALETTES = (
    ((247,248,250),(17,20,25),(108,117,129),(219,224,231),(36,92,204),(226,234,250),(255,255,255),(255,255,255),(78,86,98)),
    ((12,15,20),(234,238,243),(134,145,158),(38,46,58),(100,165,255),(24,40,64),(22,28,36),(16,21,28),(150,160,173)))
SLOTS = ('BG','INK','SUB','LINE','ACC','ACCSOFT','CARD','BAR','BARINK')
COLORS = {}
CURRENT = None      # the color set_color last received
CACHE = []
CACHE_BYTES = 0
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

def theme(n):                                                  #@L 3
    for j in range(len(SLOTS)):
        COLORS[SLOTS[j]] = PALETTES[1 if n else 0][j]


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
    if not s or top < clip[1] or top + ASC + DESC - 1 > clip[3]:
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
    global CACHE_BYTES
    del CACHE[:]
    CACHE_BYTES = 0


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
        a, d = max(a,b[1]), max(d,b[2])
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
    if kind == 'frac':
        c = boxes[ids[1]]
        w = max(w,c[0])+4
        ny, dy = -AXIS-1-d, -AXIS+2+c[1]
        children = [(ids[0],(w-b[0])//2,ny),(ids[1],(w-c[0])//2,dy)]
        a, d = a-ny, c[2]+dy
        decor = [('l',0,-AXIS,w-1,-AXIS)]
    elif kind == 'sup':
        c = boxes[ids[1]]
        sy = -(a*9//20)-c[2]
        children = [(ids[0],0,0),(ids[1],w+1,sy)]
        w, a = w+c[0]+1, max(a,c[1]-sy)
    elif kind in ('sqrt','root'):
        pad = max(0,boxes[ids[1]][0]-5) if kind == 'root' else 0
        children = [(ids[0],pad+12,0)]
        decor = [('g',pad,-a-2,'sqrt',12,a+d+2),('l',pad+10,-a-2,pad+w+13,-a-2)]
        w, a = w+pad+14, a+2
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
        top, bottom = -ASC-6, DESC+6        # the stroked sign spans the integrand and more
        lower, upper = (ids[2],ids[3]) if len(ids)>3 else (-1,-1)
        col = 12
        gx = 0
        if lower >= 0:
            lo, hi = boxes[lower],boxes[upper]
            if kind == 'sum':               # bounds centered under and over the sigma
                col = max(col,lo[0],hi[0])
                gx = (col-12)//2
                ly, uy = bottom+2+lo[1], top-1-hi[2]
                children.extend([(lower,(col-lo[0])//2,ly),(upper,(col-hi[0])//2,uy)])
            else:                           # integral bounds at the sign's lower and upper end
                ly, uy = bottom-4+lo[1], top+5-hi[2]
                children.extend([(lower,13,ly),(upper,13,uy)])
                col = 13+max(lo[0],hi[0])
            a, d = max(a,hi[1]-uy), max(d,ly+lo[2])
        prefix = col+4
        children.append((ids[0],prefix,0))
        decor.append(('g',gx,top,'integral' if kind=='integral' else 'sum',12,bottom-top))
        a, d, w = max(a,-top), max(d,bottom), prefix+f[0]
        if kind == 'integral':
            decor.append(('t',w+4,-ASC,'d'))
            children.append((ids[1],w+5+CW,0))
            w += 5+CW+boxes[ids[1]][0]
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
    dl, kinds = [],[]
    work = [(root,0,boxes[root][1])]
    while work:
        n,x,y = work.pop()
        b = boxes[n]
        if b[5] not in kinds:
            kinds.append(b[5])
        for item in b[4]:
            if item[0]=='l':
                dl.append(('l',x+item[1],y+item[2],x+item[3],y+item[4]))
            else:
                dl.append((item[0],x+item[1],y+item[2])+item[3:])
        for j in range(len(b[3])-1,-1,-1):
            child,dx,dy = b[3][j]
            work.append((child,x+dx,y+dy))
    return dl,kinds


def layout(s, width=300, height=92):                            #@L 3
    """The display list of an answer text in a width x height view (cached). A text that does
    not parse, or nests too deeply, is laid out as one plain line."""
    global CACHE_BYTES
    key = (s,width,height)
    for cached in CACHE:
        if cached[0]==key:
            return cached[1]
    fallback = False
    try:
        code = P.rpn(P.lex(s))
        if len(code)>400:
            raise ValueError('layout size')
        boxes,root = measure(tree(code))
    except Exception:
        boxes = []
        root = leaf(boxes,s[:4000])
        fallback = True
    dl,kinds = place(boxes,root)
    w,a,d = boxes[root][:3]
    result = {'dl':dl,'kinds':kinds,'w':w,'h':a+d,'asc':a,'desc':d,'fallback':fallback,'overflow':w>width or a+d>height,'vw':width,'vh':height}
    cost = len(dl)*24+len(s)
    if cost<=4096:
        while CACHE and (len(CACHE)>=5 or CACHE_BYTES+cost>4096):
            CACHE_BYTES-=CACHE.pop(0)[2]
        CACHE.append((key,result,cost))
        CACHE_BYTES+=cost
    return result


def render(dl, dx=0, clip=SCREEN, dy=0):                        #@L 4
    color(COLORS.get('INK',PALETTES[0][1]))
    for item in dl:
        x,y = item[1]+dx,item[2]+dy
        if item[0]=='l':
            clipped_line(x,y,item[3]+dx,item[4]+dy,clip)
        elif item[0]=='g':
            name,w,h = item[3:]
            g = GLYPHS[name]
            for j in range(0, len(g), 4):
                clipped_line(x+g[j]*(w-1)//10,y+g[j+1]*(h-1)//10,
                             x+g[j+2]*(w-1)//10,y+g[j+3]*(h-1)//10,clip)
        else:
            text(item[3],x,y,None,clip)


def paint(box,x,y,scrollx=0,scrolly=0):                         #@L 3
    """Draw a layout in its view (x, y, vw, vh), shifted left by scrollx and up by scrolly
    (negative values center a small answer), clipped to the view and the screen."""
    clip = (max(x,0),max(y,0),min(x+box['vw']-1,W-1),min(y+box['vh']-1,H-1))
    render(box['dl'],x-scrollx,clip,y-scrolly)
