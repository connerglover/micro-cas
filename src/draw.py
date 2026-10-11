#@L 3
# CVDRAW: iterative display RPN, postorder boxes, display lists and clipped graphics.
import parse as P
import printer as PR
import ti_graphics as G

FONTS = ((8, 14, 4), (6, 9, 3))
PALETTES = (
    ((247,248,250),(17,20,25),(108,117,129),(219,224,231),(36,92,204),(226,234,250),(255,255,255),(255,255,255),(78,86,98)),
    ((12,15,20),(234,238,243),(134,145,158),(38,46,58),(100,165,255),(24,40,64),(22,28,36),(16,21,28),(150,160,173)))
SLOTS = ('BG','INK','SUB','LINE','ACC','ACCSOFT','CARD','BAR','BARINK')
COLORS = {}
CACHE = []
CACHE_BYTES = 0
GLYPHS = {
    'pi': ((0,2,10,2),(3,2,3,10),(8,2,8,10)),
    'theta': ((2,1,8,1),(8,1,9,5),(9,5,8,9),(8,9,2,9),(2,9,1,5),(1,5,2,1),(1,5,9,5)),
    'oo': ((0,5,2,2),(2,2,4,3),(4,3,6,7),(6,7,8,8),(8,8,10,5),(10,5,8,2),(8,2,6,3),(6,3,4,7),(4,7,2,8),(2,8,0,5)),
    'sqrt': ((0,6,2,5),(2,5,4,10),(4,10,7,0),(7,0,10,0)),
    'integral': ((9,0,6,0),(6,0,5,2),(5,2,4,8),(4,8,3,10),(3,10,0,10)),
    'sum': ((10,0,0,0),(0,0,5,5),(5,5,0,10),(0,10,10,10)),
    '(': ((9,0,4,2),(4,2,2,5),(2,5,4,8),(4,8,9,10)),
    ')': ((1,0,6,2),(6,2,8,5),(8,5,6,8),(6,8,1,10)),
    '[': ((8,0,2,0),(2,0,2,10),(2,10,8,10)),
    ']': ((2,0,8,0),(8,0,8,10),(8,10,2,10)),
    '*': ((4,5,6,5),(5,4,5,6)),
    '->': ((0,5,10,5),(10,5,6,2),(10,5,6,8)),
    '<=': ((9,0,1,4),(1,4,9,8),(1,10,9,10)),
    '>=': ((1,0,9,4),(9,4,1,8),(1,10,9,10)),
    '!=': ((0,3,10,3),(0,7,10,7),(8,0,2,10))}


def theme(n):                                                  #@L 3
    for j in range(len(SLOTS)):
        COLORS[SLOTS[j]] = PALETTES[1 if n else 0][j]


def settheme(n):                                               #@L 3
    for j in range(len(SLOTS)):
        COLORS[SLOTS[j]] = PALETTES[1 if n else 0][j]


def clear_cache():                                             #@L 3
    global CACHE_BYTES
    del CACHE[:]
    CACHE_BYTES = 0


def metrics(s, level):                                         #@L 7
    font = 1 if level else 0
    adv, asc, desc = FONTS[font]
    width = len(s) * adv
    try:
        G.setFont(font)
        size = G.string_size(s)
        width = int(size[0])
    except (AttributeError, TypeError, ValueError):
        pass
    return width, asc, desc, font


def leaf(boxes, s, level, ti=-1):                               #@L 6
    w, a, d, font = metrics(s, level)
    if s in GLYPHS:
        w = 10 if not level else 8
        decor = [('g',0,-a,s,w,a+d)]
    else:
        decor = [('t',0,-a,s,font)]
    boxes.append((w,a,d,(),decor,'text',ti))
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


def frame(boxes, kind, ids, level, ti=-1):                       #@L 5
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
        w, axis = max(w,c[0])+4, FONTS[1 if level else 0][1]//3
        ny, dy = -axis-3-d, -axis+3+c[1]
        children = [(ids[0],(w-b[0])//2,ny),(ids[1],(w-c[0])//2,dy)]
        a, d = a-ny, c[2]+dy
        decor = [('l',0,-axis,w-1,-axis)]
    elif kind == 'sup':
        c = boxes[ids[1]]
        sy = -(a*9//20)-c[2]
        children = [(ids[0],0,0),(ids[1],w+1,sy)]
        w, a = w+c[0]+1, max(a,c[1]-sy)
    elif kind in ('sqrt','root'):
        pad = boxes[ids[1]][0]//2 if kind == 'root' else 0
        children = [(ids[0],pad+12,0)]
        decor = [('g',pad,-a-2,'sqrt',12,a+d+2),('l',pad+10,-a-2,pad+w+13,-a-2)]
        w, a = w+pad+14, a+2
        if kind == 'root':
            c = boxes[ids[1]]
            children.append((ids[1],0,-a//2-c[2]))
            a = max(a,a//2+c[1]+c[2])
    else:
        pad = 4 if kind == 'abs' else 6
        children = [(ids[0],pad,0)]
        if kind == 'abs':
            decor = [('l',0,-a,0,d),('l',w+2*pad-1,-a,w+2*pad-1,d)]
        else:
            ls, rs = ('[',']') if kind == 'list' else ('(',')')
            decor = [('g',0,-a,ls,pad,a+d),('g',w+pad,-a,rs,pad,a+d)]
        w += 2*pad
    boxes.append((w,a,d,children,decor,kind,ti))
    return len(boxes)-1


def large(boxes, kind, ids, level, ti):                         #@L 5
    f = boxes[ids[0]]
    font = 1 if level else 0
    a, d = f[1], f[2]
    children = []
    decor = []
    if kind == 'limit':
        lo = boxes[ids[1]]
        prefix = max(24,lo[0])+5
        children = [(ids[1],0,lo[1]+5),(ids[0],prefix,0)]
        decor = [('t',0,-FONTS[font][1],'lim',font)]
        a, d, w = max(a,FONTS[font][1]), max(d,lo[1]+lo[2]+5), prefix+f[0]
    else:
        lower, upper = (ids[2],ids[3]) if len(ids)>3 else (-1,-1)
        pad = 0
        if lower >= 0:
            lo, hi = boxes[lower],boxes[upper]
            pad = max(lo[0],hi[0])+2
            children.extend([(lower,12,15+lo[1]),(upper,12,-20-hi[2])])
            a,d = max(a,20+hi[1]+hi[2]),max(d,15+lo[1]+lo[2])
        prefix = 16+pad
        children.append((ids[0],prefix,0))
        decor.append(('g',0,-18,'integral' if kind=='integral' else 'sum',12,32))
        a,d,w = max(a,18),max(d,14),prefix+f[0]
        if kind == 'integral':
            decor.append(('t',w+4,-FONTS[font][1],'d',font))
            children.append((ids[1],w+5+FONTS[font][0],0))
            w += 5+FONTS[font][0]+boxes[ids[1]][0]
    boxes.append((w,a,d,children,decor,kind,ti))
    return len(boxes)-1


def tree(code, base):                                          #@L 4
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
    levels = [base]*len(specs)
    for i in range(len(specs)-1,-1,-1):
        item, children = specs[i]
        for j in range(len(children)):
            script = item[0]=='o' and item[1]=='^' and j==1
            if item[0]=='F':
                name = item[1]
                script = script or name=='surd' and j==1 or name=='integrate' and j>=2 or name in ('sum','limit') and j>=1
            levels[children[j]] = levels[i]+(1 if script else 0)
    return specs,levels


def measure(specs, levels):                                    #@L 4
    boxes, roots = [],[]
    for i in range(len(specs)):
        it, children = specs[i]
        ids = []
        for n in children:
            ids.append(roots[n])
        kind, lev, ti = it[0],levels[i],it[-1]
        if kind in ('n','s'):
            s = it[1]
            if kind == 'n':
                s = str(s[0]) if type(s) is tuple else PR.fdec10(s)
            root = leaf(boxes,s,lev,ti)
        elif kind == 'P':
            root = frame(boxes,'paren',ids,lev,ti)
        elif kind == 'o':
            op = it[1]
            if op in ('/','^'):
                root = frame(boxes,'frac' if op=='/' else 'sup',ids,lev,ti)
            else:
                sign = leaf(boxes,'-' if op=='neg' else op,lev,ti)
                rowids = [sign,ids[0]] if op=='neg' else [ids[0],sign] if op=='!' else [ids[0],sign,ids[1]]
                if op=='*':
                    right = specs[children[1]][0]
                    if right[0] in ('s','F','P'):
                        rowids = ids
                root = row(boxes,rowids,2,'row',ti)
        else:
            name = it[1] if kind=='F' else ''
            if name in ('sqrt','abs') and len(ids)==1:
                root = frame(boxes,name,ids,lev,ti)
            elif name=='surd' and len(ids)==2:
                root = frame(boxes,'root',ids,lev,ti)
            elif name=='integrate' and len(ids) in (2,4):
                root = large(boxes,'integral',ids,lev,ti)
            elif name=='sum' and len(ids)==4:
                lower = row(boxes,[ids[1],leaf(boxes,'=',lev+1),ids[2]],1)
                root = large(boxes,'sum',[ids[0],ids[1],lower,ids[3]],lev,ti)
            elif name=='limit' and len(ids)==3:
                lower = row(boxes,[ids[1],leaf(boxes,'->',lev+1),ids[2]],1)
                root = large(boxes,'limit',[ids[0],lower],lev,ti)
            elif name=='diff' and len(ids)==2:
                dn = leaf(boxes,'d',lev)
                den = row(boxes,[leaf(boxes,'d',lev),ids[1]],0)
                frac = frame(boxes,'frac',[dn,den],lev)
                root = row(boxes,[frac,ids[0]],4,'derivative',ti)
            else:
                joined = []
                for j in range(len(ids)):
                    if j:
                        joined.append(leaf(boxes,',',lev))
                    joined.append(ids[j])
                root = row(boxes,joined,2)
                if kind=='L':
                    if ti>=0:
                        root = frame(boxes,'list',[root],lev,ti)
                else:
                    root = frame(boxes,'paren',[root],lev,ti)
                    label = 'arc'+name[1:] if name in ('asin','acos','atan') else name
                    root = row(boxes,[leaf(boxes,label,lev),root],1,'call',ti)
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


def layout(s, width=300, height=110):                           #@L 3
    global CACHE_BYTES
    key = (s,width,height)
    for cached in CACHE:
        if cached[0]==key:
            return cached[1]
    fallback = False
    small = 0
    try:
        code = P.rpn(P.lex(s))
        if len(code)>400:
            raise ValueError('layout size')
        specs, levels = tree(code,0)
        boxes,root = measure(specs,levels)
        if boxes[root][0]>width or boxes[root][1]+boxes[root][2]>height:
            specs,levels = tree(code,1)
            boxes,root = measure(specs,levels)
            small = 1
    except Exception:
        boxes = []
        root = leaf(boxes,s[:4000],1)
        fallback,small = True,1
    dl,kinds = place(boxes,root)
    w,a,d = boxes[root][:3]
    result = {'dl':dl,'kinds':kinds,'w':w,'h':a+d,'asc':a,'desc':d,'fallback':fallback,'small':bool(small),'overflow':w>width or a+d>height,'vw':width,'vh':height}
    cost = len(dl)*24+len(s)
    if cost<=4096:
        while CACHE and (len(CACHE)>=5 or CACHE_BYTES+cost>4096):
            CACHE_BYTES-=CACHE.pop(0)[2]
        CACHE.append((key,result,cost))
        CACHE_BYTES+=cost
    return result


def clipped_line(x1,y1,x2,y2,clip):                             #@L 5
    left,top,right,bottom = clip
    for j in range(8):
        c1 = (1 if x1<left else 2 if x1>right else 0)+(4 if y1<top else 8 if y1>bottom else 0)
        c2 = (1 if x2<left else 2 if x2>right else 0)+(4 if y2<top else 8 if y2>bottom else 0)
        if not c1 and not c2:
            G.drawLine(x1,y1,x2,y2)
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


def render(dl, dx=0, clip=(0,0,319,209), dy=0):                 #@L 4
    G.setColor(*COLORS.get('INK',PALETTES[0][1]))
    for item in dl:
        x,y = item[1]+dx,item[2]+dy
        if item[0]=='l':
            clipped_line(x,y,item[3]+dx,item[4]+dy,clip)
        elif item[0]=='g':
            name,w,h = item[3:]
            for a,b,c,d in GLYPHS[name]:
                clipped_line(x+a*(w-1)//10,y+b*(h-1)//10,x+c*(w-1)//10,y+d*(h-1)//10,clip)
        elif item[0]=='t':
            s,font = item[3:]
            G.setFont(font)
            adv,asc,desc = FONTS[font]
            if clip[1]<=y and y+asc+desc-1<=clip[3]:
                width = metrics(s,font)[0]
                if clip[0]<=x and x+width-1<=clip[2]:
                    G.drawString(s,x,y)
                    continue
                for char in s:
                    adv = metrics(char,font)[0]
                    if clip[0]<=x and x+adv-1<=clip[2]:
                        G.drawString(char,x,y)
                    x+=adv


def paint(box,x,y,scrollx=0,scrolly=0):                         #@L 3
    render(box['dl'],x-scrollx,(x,y,x+box['vw']-1,y+box['vh']-1),y-scrolly)


def text(s,x,y,small=False,color=None):                         #@L 3
    G.setFont(1 if small else 0)
    G.setColor(*(COLORS.get('INK',PALETTES[0][1]) if color is None else color))
    G.drawString(s,x,y)
