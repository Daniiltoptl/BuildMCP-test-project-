RED="red_nether_bricks"; RS="red_nether_brick_stairs"; RW="red_nether_brick_wall"
DT="deepslate_tiles"; DS="deepslate_tile_stairs"; DSL="deepslate_tile_slab"
Y0=65
R_ = np.random.default_rng(31)
LV = {0: dict(t=2, bt=1, drop=4, ov=3), 1: dict(t=3, bt=2, drop=7, ov=4), 2: dict(t=3, bt=2, drop=8, ov=5), 3: dict(t=4, bt=3, drop=11, ov=6)}

def frame(axis, a, b, v0, H, lv=0, ova=None, ovb=None, lan=True):
    t, bt, drop, ov = (LV[lv][k] for k in ("t", "bt", "drop", "ov"))
    big = lv >= 2
    def bx(u1,u2,y1,y2,w1=0,w2=None):
        if w2 is None: w2=t-1
        u1,u2=min(u1,u2),max(u1,u2)
        if axis=="x": return (u1,y1,v0+w1,u2,y2,v0+w2)
        return (v0+w1,y1,u1,v0+w2,y2,u2)
    pos = "east" if axis=="x" else "south"; neg = "west" if axis=="x" else "north"
    lo = "south" if axis=="x" else "east"; hi = "north" if axis=="x" else "west"
    A0,A1,B0,B1 = a,a+t-1,b,b+t-1
    top = Y0+H
    ova = ov if ova is None else ova; ovb = ov if ovb is None else ovb
    ny = top-drop
    for p0,p1 in ((A0,A1),(B0,B1)):
        S.fill(bx(p0-1,p1+1,Y0,Y0,-1,t), "polished_blackstone_brick_slab[type=bottom]")
        S.fill(bx(p0,p1,Y0,top-1), RED)
        S.fill(bx(p0,p1,Y0,Y0), "chiseled_polished_blackstone")
        S.fill(bx(p0,p1,Y0+1,Y0+(1 if lv==0 else 2 if lv<3 else 3)), "polished_blackstone_bricks")
        if lv==3:
            S.fill(bx(p0-1,p1+1,Y0,Y0+1,-1,t), "polished_blackstone_bricks")
            S.fill(bx(p0-1,p1+1,Y0+2,Y0+2,-1,t), "polished_blackstone_brick_slab[type=bottom]")
            S.fill(bx(p0,p1,Y0+2,Y0+3), "chiseled_polished_blackstone")
            S.fill(bx(p0,p1,Y0+4,Y0+4), "gilded_blackstone")
    S.fill(bx(A0-ova,B1+ovb,ny-bt+1,ny), RED)
    S.fill(bx(A0-ova-1,A0-ova-1,ny,ny), f"{RS}[facing={pos},half=top]")
    S.fill(bx(B1+ovb+1,B1+ovb+1,ny,ny), f"{RS}[facing={neg},half=top]")
    for k in range(1 if lv==0 else 2 if lv<3 else 3):   # stepped brackets under the tie beam
        yy = ny-bt-k
        for j in range(1, (1 if lv==0 else 2 if lv<3 else 3)-k+1):
            last = j == (1 if lv==0 else 2 if lv<3 else 3)-k
            S.fill(bx(A1+j,A1+j,yy,yy), f"{RS}[facing={neg},half=top]" if last else RED)
            S.fill(bx(B0-j,B0-j,yy,yy), f"{RS}[facing={pos},half=top]" if last else RED)
            if ova>j: S.fill(bx(A0-j,A0-j,yy,yy), f"{RS}[facing={pos},half=top]" if last else RED)
            if ovb>j: S.fill(bx(B1+j,B1+j,yy,yy), f"{RS}[facing={neg},half=top]" if last else RED)
    S.fill(bx(A0-ova-1,B1+ovb+1,top-bt+1,top), RED)
    S.fill(bx(A0-ova-2,A0-ova-2,top,top), f"{RS}[facing={pos},half=top]")
    S.fill(bx(B1+ovb+2,B1+ovb+2,top,top), f"{RS}[facing={neg},half=top]")
    # short struts between the beams
    c0,c1 = (A1+B0)//2, (A1+B0+1)//2
    wm0, wm1 = (0, t-1) if t==2 else (1, t-2)
    if lv>=1:
        hw = 1 if lv<3 else 2
        c0-=hw; c1+=hw
        S.fill(bx(c0,c1,ny+1,top-bt,wm0,wm1), "polished_blackstone")
        S.fill(bx(c0,c1,ny+2,top-bt-1,wm0,wm1), "gilded_blackstone")
        S.fill(bx(c0+1,c1-1,ny+2,top-bt-1,wm0,wm1), "gold_block")
        S.fill(bx(c0-1,c0-1,ny+1,top-bt,wm0,wm1), RW); S.fill(bx(c1+1,c1+1,ny+1,top-bt,wm0,wm1), RW)
        for u in (A0+ (t//2), B0 + (t//2)):
            S.fill(bx(u,u,ny+1,top-bt,wm0,wm1), RED)
    else:
        S.fill(bx(c0,c1,ny+1,top-1), "gilded_blackstone")
    L0,L1 = A0-ova-2, B1+ovb+2
    S.fill(bx(L0,L1,top+1,top+1), DT)
    S.fill(bx(L0,L1,top+1,top+1,-1,-1), f"{DS}[facing={lo},half=bottom]")
    S.fill(bx(L0,L1,top+1,top+1,t,t), f"{DS}[facing={hi},half=bottom]")
    S.fill(bx(L0+3,L1-3,top+2,top+2), f"{DSL}[type=bottom]")
    if t>=3:
        S.fill(bx(L0+3,L1-3,top+2,top+2,1,t-2), DT)
        S.fill(bx(L0+4,L1-4,top+3,top+3,1,t-2), f"{DSL}[type=bottom]")
    if lv==3:
        S.fill(bx(L0-1,L1+1,top+1,top+1,-2,-2), f"{DSL}[type=bottom]")
        S.fill(bx(L0-1,L1+1,top+1,top+1,t+1,t+1), f"{DSL}[type=bottom]")
    S.fill(bx(L0,L0+2,top+2,top+2), DT); S.fill(bx(L1-2,L1,top+2,top+2), DT)
    for (e0,e1) in ((L0,L0+2),(L1-2,L1)):
        S.fill(bx(e0,e1,top+2,top+2,-1,-1), f"{DS}[facing={lo},half=bottom]")
        S.fill(bx(e0,e1,top+2,top+2,t,t), f"{DS}[facing={hi},half=bottom]")
    S.fill(bx(L0-1,L0-1,top+2,top+2), f"{DS}[facing={pos},half=top]")
    S.fill(bx(L1+1,L1+1,top+2,top+2), f"{DS}[facing={neg},half=top]")
    if lv>=1:
        S.fill(bx(L0-1,L0,top+3,top+3), DT); S.fill(bx(L1,L1+1,top+3,top+3), DT)
        S.fill(bx(L0+1,L0+1,top+3,top+3), f"{DS}[facing={neg},half=bottom]")
        S.fill(bx(L1-1,L1-1,top+3,top+3), f"{DS}[facing={pos},half=bottom]")
        S.fill(bx(L0-2,L0-2,top+3,top+3), f"{DS}[facing={pos},half=top]")
        S.fill(bx(L1+2,L1+2,top+3,top+3), f"{DS}[facing={neg},half=top]")
        if lv==3:
            S.fill(bx(L0-2,L0-1,top+4,top+4), DT); S.fill(bx(L1+1,L1+2,top+4,top+4), DT)
            S.fill(bx(L0-3,L0-3,top+4,top+4), f"{DS}[facing={pos},half=top]")
            S.fill(bx(L1+3,L1+3,top+4,top+4), f"{DS}[facing={neg},half=top]")
            S.fill(bx(L0-3,L0-2,top+5,top+5), f"{DSL}[type=bottom]")
            S.fill(bx(L1+2,L1+3,top+5,top+5), f"{DSL}[type=bottom]")
        else:
            S.fill(bx(L0-2,L0-1,top+4,top+4), f"{DSL}[type=bottom]")
            S.fill(bx(L1+1,L1+2,top+4,top+4), f"{DSL}[type=bottom]")
    else:
        S.fill(bx(L0-1,L0,top+3,top+3), f"{DSL}[type=bottom]")
        S.fill(bx(L1,L1+1,top+3,top+3), f"{DSL}[type=bottom]")
    if lan:
        under = ny-bt
        nmax = under-(Y0+6)
        spots = [(A1+4, 0), (B0-4, t-1)]
        if ova>2: spots.append((A0-ova+1, t-1))
        if ovb>2: spots.append((B1+ovb-1, 0))
        if lv>=1: spots += [(c0-2, 0), (c1+2, t-1)]
        if B0-A1 > 16: spots += [(A1+8, t-1), (B0-8, 0)]
        for (u,w) in spots:
            n = int(min(nmax, R_.integers(3, 6 + 2*lv)))
            if n < 1: continue
            S.fill(bx(u,u,under-n+1,under,w,w), "chain[axis=y]")
            S.fill(bx(u,u,under-n,under-n,w,w), "ochre_froglight")
            if lv>=2: S.fill(bx(u,u,under-n-1,under-n-1,w,w), "ochre_froglight")

def qpost(p1,p2,t,s): return (p1,p2) if s>0 else (-(p2+t-1), -(p1+t-1))
def qv(q,t,s): return q if s>0 else -(q+t-1)

# grand torii on the four avenues + a medium one in front of each
for ax in ("x","z"):
    frame(ax,-13,10,-71,34,lv=3); frame(ax,-13,10,68,34,lv=3)
    frame(ax,-11,9,-48,24,lv=1); frame(ax,-11,9,46,24,lv=1)
quads=[(1,-1),(1,1),(-1,1),(-1,-1)]
HA=[27,22,28,20]; HB=[21,28,23,26]
HA2=[15,17,14,18]; HB2=[18,14,17,15]
for i,(sx,sz) in enumerate(quads):
    a,b=qpost(19,40,3,sx); frame("x",a,b,qv(58,3,sz),HA[i],lv=2)
    a,b=qpost(19,40,3,sz); frame("z",a,b,qv(58,3,sx),HB[i],lv=2)
    a,b=qpost(16,30,2,sx); frame("x",a,b,qv(44,2,sz),HA2[i],lv=0)
    a,b=qpost(16,30,2,sz); frame("z",a,b,qv(44,2,sx),HB2[i],lv=0)
for (sx,sz,hc,hd) in ((1,-1,15,20),(-1,1,20,15),(1,1,13,17),(-1,-1,17,13)):
    a,b=qpost(35,50,2,sx)
    frame("x",a,b,qv(50,2,sz),hc, ova=(3 if sx>0 else 1), ovb=(1 if sx>0 else 3))
    a,b=qpost(35,50,2,sz)
    frame("z",a,b,qv(50,2,sx),hd, ova=(3 if sz>0 else 1), ovb=(1 if sz>0 else 3))

def board(axis,u1,u2,v):
    def bx(a,b,y1,y2,d=0): return (a,y1,v+d,b,y2,v+d) if axis=="x" else (v+d,y1,a,v+d,y2,b)
    brick = P.mix({"bricks":7,"granite":1,"polished_granite":1}, seed=abs(u1*3+v))
    S.fill(bx(u1,u2,Y0,Y0), "polished_blackstone_bricks")
    S.fill(bx(u1+1,u2-1,Y0+1,Y0+7), brick)
    for yy in (Y0+1, Y0+4, Y0+7): S.fill(bx(u1+1,u2-1,yy,yy), "dark_oak_planks")
    S.fill(bx(u1,u1,Y0+1,Y0+7), "stripped_dark_oak_log[axis=y]")
    S.fill(bx(u2,u2,Y0+1,Y0+7), "stripped_dark_oak_log[axis=y]")
    m = (u1+u2)//2
    S.fill(bx(m,m,Y0+1,Y0+7), "stripped_dark_oak_log[axis=y]")
    S.fill(bx(u1-1,u2+1,Y0+8,Y0+8), f"{DSL}[type=bottom]")
    S.fill(bx(u1,u2,Y0+8,Y0+8), DT)
    S.fill(bx(u1+1,u2-1,Y0+9,Y0+9), f"{DSL}[type=bottom]")

def bamboo(cells, seed):
    rr=np.random.default_rng(abs(seed))
    for (x,z) in cells:
        if x*x+z*z > 74.3**2 or rr.random()<0.25: continue
        g = str(S.get(x,65,z))
        if not g.endswith("air") and "petals" not in g: continue
        S.set(x,64,z,"podzol")
        h=int(rr.integers(8,17))
        for k in range(h):
            lv_ = "large" if k>=h-2 else "small" if k>=h-5 else "none"
            S.set(x,65+k,z,f"bamboo[age=1,leaves={lv_},stage=0]")

for i,(sx,sz) in enumerate(quads):
    if i%2==0:
        a,b=qpost(19,40,3,sx); v=qv(58,3,sz)
        board("x",a+5,b-3,v+1)
        vo = [v-1,v-2,v-3] if sz<0 else [v+3,v+4,v+5]
        bamboo([(x,z) for x in range(a+3,b) for z in vo], 5+i)
    else:
        a,b=qpost(19,40,3,sz); v=qv(58,3,sx)
        board("z",a+5,b-3,v+1)
        vo = [v-1,v-2,v-3] if sx<0 else [v+3,v+4,v+5]
        bamboo([(x,z) for z in range(a+3,b) for x in vo], 5+i)
for (sx,sz) in quads:
    bamboo([(sx*x, sz*z) for x in range(18,27) for z in range(66,71)], 40+sx+3*sz)
    bamboo([(sx*x, sz*z) for z in range(18,27) for x in range(66,71)], 50+sx+3*sz)

def toro(x,z,y=Y0):
    S.set(x,y,z,"chiseled_polished_blackstone")
    S.set(x,y+1,z,"polished_blackstone_wall"); S.set(x,y+2,z,"polished_blackstone_wall")
    S.set(x,y+3,z,"polished_blackstone_slab[type=top]")
    S.set(x,y+4,z,"ochre_froglight")
    for f,(dx,dz) in (("north",(0,-1)),("south",(0,1)),("west",(-1,0)),("east",(1,0))):
        S.set(x+dx,y+4,z+dz,f"dark_oak_trapdoor[facing={f},open=true,half=bottom]")
    S.fill((x-1,y+5,z-1,x+1,y+5,z+1), f"{DSL}[type=bottom]")
    S.set(x,y+5,z,DT); S.set(x,y+6,z,"polished_blackstone_wall")
for s1 in (-1,1):
    for s2 in (-1,1):
        for (u,v) in ((14,41),(15,54),(16,64)):
            toro(s1*u, s2*v); toro(s2*v, s1*u)
for k in range(8):
    a = math.radians(22.5 + 45*k)
    toro(int(round(24.5*math.cos(a))), int(round(24.5*math.sin(a))), 68)

def pavilion(cx,cz,h,kind):
    S.fill((cx-5,Y0,cz-5,cx+5,Y0,cz+5), "polished_blackstone_brick_slab[type=bottom]")
    S.fill((cx-4,Y0,cz-4,cx+4,Y0,cz+4), P.mix({"polished_blackstone_bricks":4,"polished_deepslate":2,"cracked_polished_blackstone_bricks":1},seed=abs(cx)))
    S.fill((cx-1,Y0,cz-1,cx+1,Y0,cz+1), "chiseled_polished_blackstone")
    for dx in (-3,3):
        for dz in (-3,3):
            S.fill((cx+dx,Y0+1,cz+dz,cx+dx,Y0+h,cz+dz), RED)
            S.set(cx+dx,Y0+1,cz+dz,"polished_blackstone_bricks")
    yb=Y0+h
    S.fill((cx-3,yb-1,cz-3,cx+3,yb,cz+3), RED)
    S.fill((cx-2,yb-1,cz-2,cx+2,yb,cz+2), "air")
    for d in (-4,4):
        S.fill((cx+d,yb,cz-3,cx+d,yb,cz+3), f"{RS}[facing={'east' if d<0 else 'west'},half=top]", only="air")
        S.fill((cx-3,yb,cz+d,cx+3,yb,cz+d), f"{RS}[facing={'south' if d<0 else 'north'},half=top]", only="air")
    arch.roof((cx-3,Y0+1,cz-3,cx+3,yb,cz+3), style="asian", material="deepslate_tiles", overhang=3, pitch=0.85)
    ty = S.top_y(cx,cz)
    S.set(cx,ty+1,cz,"polished_blackstone_wall"); S.set(cx,ty+2,cz,"gold_block"); S.set(cx,ty+3,cz,"lightning_rod")
    if kind=="bell":
        S.fill((cx,yb-2,cz,cx,yb+2,cz),"chain[axis=y]")
        for dx,dz in ((-3,0),(3,0),(0,-3),(0,3)):
            S.set(cx+dx,yb-2,cz+dz,"chain[axis=y]"); S.set(cx+dx,yb-3,cz+dz,"ochre_froglight")
    else:
        S.fill((cx-2,Y0+1,cz-1,cx+2,Y0+1,cz+1), "polished_blackstone_bricks")
        S.fill((cx-1,Y0+1,cz,cx+1,Y0+1,cz), "water_cauldron[level=3]")
        S.fill((cx-2,Y0+2,cz-1,cx+2,Y0+2,cz-1), "bamboo_fence")
        S.fill((cx,yb-3,cz,cx,yb+1,cz),"chain[axis=y]"); S.set(cx,yb-4,cz,"ochre_froglight")
pavilion(40,40,9,"bell")
pavilion(-40,-40,8,"water")
print("red", S.count("red_nether_bricks"))
