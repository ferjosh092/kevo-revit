"""Lamina E-09 - ESCALERA, generada del modelo IFC (model_all.pkl).
Plantas 1:25 (primer piso y tipica), cortes longitudinales A-A (tramo 1) y B-B (tramo 2) 1:25 cortando el modelo
real con su acero, detalle del cimiento de arranque 1:20 (corte y planta), seccion transversal tipica de tramo
1:10, cuadro de acero y notas.  Salida: E-09_Escalera.dxf / .pdf / _preview.png"""
import math, collections
import numpy as np
from shapely.geometry import Polygon, LineString, box, Point
from shapely.ops import unary_union
from sheetcommon import *
from sheetlib import View, section_mark, ptext, view_title, add_vp, table

M = load_model()
E = M["elements"]
GU, GV = M["GU"], M["GV"]
LV = M["levels"]
TRS = ["N1-N2", "N2-N3", "N3-N4", "N4-N5"]
ZF = {"N1-N2": 0.0, "N2-N3": LV["Nivel 2"], "N3-N4": LV["Nivel 3"], "N4-N5": LV["Nivel 4"]}
ZT = {"N1-N2": LV["Nivel 2"], "N2-N3": LV["Nivel 3"], "N3-N4": LV["Nivel 4"], "N4-N5": LV["Nivel 5"]}


def f2(x):
    return f"{x:.2f}"


def sgn2(x):
    return "±0.00" if abs(x) < 0.005 else (f"+{x:.2f}" if x > 0 else f"{x:.2f}")


def sep_txt(s):
    return f"@ {s:.2f}".replace("0.", ".")


def piece(tr, part):
    for t, e in E.items():
        c = e["com"] or ""
        if c.startswith("SJ_ESCALERA_CONCRETO_4X3_R1|") and c.endswith(f"|{tr}|{part}"):
            return t
    raise KeyError(tr + part)


CIM = [t for t, e in E.items() if e["tipo"] == "CIM_ESCALERA_ARRANQUE_R1"][0]
CIMP = footprint(E[CIM])
cb0, cb1 = E[CIM]["bbox"]
PARTS = ("LOSA_T1", "LOSA_T2", "DESCANSO_J2", "EXTENSION_PLATAFORMA_J1", "PELDANOS_T1", "PELDANOS_T2",
         "NUDO_PRISMATICO_J2", "NUDO_PRISMATICO_J2B", "NUDO_PRISMATICO_J1")
PC = {(tr, p): piece(tr, p) for tr in TRS for p in PARTS}
HOST = {}          # tag -> (tramo, pieza)
for (tr, p), t in PC.items():
    HOST[t] = (tr, p)
HOST[CIM] = ("N1-N2", "CIMIENTO")

# ------------------------------------------------------------------ acero de escalera
SB = []
for b in M["bars"]:
    if b["grp"] == "SJ_ACERO_ESCALERA_R1":
        b = dict(b, pl=np.asarray(b["pl"], float))
        b["let"] = "M" if b["role"].startswith("MECHA") else b["role"][0]
        b["tr"], b["pz"] = HOST[b["host"]]
        SB.append(b)


def bars_of(tag, let=None):
    return [b for b in SB if b["host"] == tag and (let is None or b["let"] == let)]


# ------------------------------------------------------------------ geometria de tramos (medida)
def rect(tag):
    b0, b1 = E[tag]["bbox"]
    return float(b0[0]), float(b1[0]), float(b0[1]), float(b1[1]), float(b0[2]), float(b1[2])


def treads(tag):
    """huellas del modelo generico de peldanos, cortado por el centro del ancho: [(u0,u1,z)]"""
    u0, u1, v0, v1, _, _ = rect(tag)
    p = cut_polys(E[tag], 1, (v0 + v1) / 2)[0]
    c = np.array(p.exterior.coords)
    hs = {}
    for a, b in zip(c[:-1], c[1:]):
        if abs(a[1] - b[1]) < 1e-4 and abs(a[0] - b[0]) > 1e-3:
            k = round(a[1], 4)
            lo, hi = min(a[0], b[0]), max(a[0], b[0])
            if k in hs:
                hs[k] = (min(hs[k][0], lo), max(hs[k][1], hi))
            else:
                hs[k] = (lo, hi)
    return sorted([(lo, hi, z) for z, (lo, hi) in hs.items()], key=lambda x: x[2])


def slab_line(tag):
    """recta inferior y superior del tramo en el corte por su centro: z = a + s*u"""
    u0, u1, v0, v1, _, _ = rect(tag)
    c = np.array(cut_polys(E[tag], 1, (v0 + v1) / 2)[0].exterior.coords)
    zb0 = c[np.isclose(c[:, 0], u0, atol=1e-3)][:, 1].min()
    zb1 = c[np.isclose(c[:, 0], u1, atol=1e-3)][:, 1].min()
    zt0 = c[np.isclose(c[:, 0], u0, atol=1e-3)][:, 1].max()
    s = (zb1 - zb0) / (u1 - u0)
    th = math.atan(abs(s))
    return dict(s=s, th=th, zb0=zb0, u0=u0, u1=u1, vert=zt0 - zb0, t=(zt0 - zb0) * math.cos(th))


FL = {}
for tr in TRS:
    desc = rect(PC[(tr, "DESCANSO_J2")])
    plat = rect(PC[(tr, "EXTENSION_PLATAFORMA_J1")])
    for k, (lt, pt) in {"T1": ("LOSA_T1", "PELDANOS_T1"), "T2": ("LOSA_T2", "PELDANOS_T2")}.items():
        tl = treads(PC[(tr, pt)])
        u0, u1, v0, v1, _, _ = rect(PC[(tr, lt)])
        if k == "T1":
            zs = [ZF[tr]] + [t[2] for t in tl] + [desc[5]]
            risers = [t[0] for t in tl] + [tl[-1][1]]            # sube hacia +u
        else:
            zs = [desc[5]] + [t[2] for t in tl] + [ZT[tr]]
            risers = [t[1] for t in tl] + [tl[-1][0]]            # sube hacia -u
        cps = np.diff(zs)
        FL[(tr, k)] = dict(tag=PC[(tr, lt)], treads=tl, zs=zs, risers=risers, n_cp=len(cps), cp=float(np.mean(cps)),
                           cp_rng=(float(cps.min()), float(cps.max())), n_p=len(tl),
                           p=float(np.mean([t[1] - t[0] for t in tl])), u0=u0, u1=u1, v0=v0, v1=v1,
                           vc=(v0 + v1) / 2, sl=slab_line(PC[(tr, lt)]))
    FL[(tr, "D")] = desc
    FL[(tr, "P")] = plat

for tr in TRS:
    for k in ("T1", "T2"):
        f = FL[(tr, k)]
        print(tr, k, "cp", f["n_cp"], round(f["cp"], 4), "pasos", f["n_p"], round(f["p"], 4),
              "t", round(f["sl"]["t"], 3), "ang", round(math.degrees(f["sl"]["th"]), 2), "u", f["u0"], f["u1"])
    print(tr, "descanso", FL[(tr, "D")], "plataforma", FL[(tr, "P")])


# ------------------------------------------------------------------ codigos de barra (planilla)
def segs(b):
    return [float(x) for x in b["segs"] if x]


def seg_key(b):
    return tuple(round(s, 2) for s in segs(b))


PRI = {"CIMIENTO": 0, "LOSA_T1": 1, "LOSA_T2": 2, "DESCANSO_J2": 3, "EXTENSION_PLATAFORMA_J1": 4}
LETO = {"M": 0, "L": 1, "S": 2, "T": 3}
groups = collections.OrderedDict()
for b in sorted(SB, key=lambda b: (TRS.index(b["tr"]) if b["pz"] != "CIMIENTO" else -1, PRI[b["pz"]], LETO[b["let"]])):
    k = (b["let"], round(b["L"], 2), seg_key(b))
    groups.setdefault(k, []).append(b)
# orden: por primera aparicion (mecha, tramo 1 N1-N2, ...)
CODE = {}
for i, k in enumerate(groups):
    CODE[k] = f"E{i + 1}"
for k, bl in groups.items():
    for b in bl:
        b["code"] = CODE[k]
PZN = {"CIMIENTO": "cimiento", "LOSA_T1": "tramo 1", "LOSA_T2": "tramo 2", "DESCANSO_J2": "descanso",
       "EXTENSION_PLATAFORMA_J1": "plataforma"}
LETN = {"M": "Mecha (sale del cimiento)", "L": "Long. inferior", "S": "Long. superior", "T": "Transversal"}


def tr_range(trs):
    trs = sorted(set(trs), key=TRS.index)
    if len(trs) == 1:
        return trs[0]
    if trs == TRS:
        return "todos"
    return f"{trs[0]} a {trs[-1]}"


def code_desc(k):
    bl = groups[k]
    pz = sorted({b["pz"] for b in bl}, key=lambda p: PRI[p])
    let = k[0]
    if let == "M":
        return "Mecha cimiento, traslapa con sup. tramo 1"
    where = " y ".join(PZN[p] for p in pz)
    return f"{LETN[let]} {where} ({tr_range([b['tr'] for b in bl])})"


def spacing(tag, let):
    """n y separacion medida de las barras de una pieza (v para L/S; a lo largo de la pieza para T)"""
    bl = bars_of(tag, let)
    if not bl:
        return 0, 0.0
    if let in ("L", "S", "M"):
        pos = sorted(b["pl"][:, 1].mean() for b in bl)
        return len(bl), (pos[-1] - pos[0]) / (len(bl) - 1)
    P = sorted([b["pl"].mean(0) for b in bl], key=lambda p: p[0])
    d = [np.linalg.norm((P[i + 1] - P[i])[[0, 2]]) for i in range(len(P) - 1)]
    return len(bl), float(np.mean(d))


def code_of(tag, let):
    return bars_of(tag, let)[0]["code"]


def lab_txt(tag, let, extra=""):
    n, s = spacing(tag, let)
    c = code_of(tag, let)
    return f'{c}: {n} Ø3/8" {sep_txt(s)}{extra}'


# ------------------------------------------------------------------ documento
doc = new_doc()
add_layers(doc)
for nm, col in (("E-ESC-NUM", 7), ("E-ESC-FLECHA", 7)):
    if nm not in doc.layers:
        doc.layers.add(nm, color=col)


def arrow_head(V, tip, direction, L_mm=2.6, W_mm=1.0, layer="E-ESC-FLECHA"):
    d = np.array(direction, float)
    d /= np.linalg.norm(d)
    n = np.array([-d[1], d[0]])
    t = np.array(tip, float)
    b = t - d * L_mm * V.m
    pts = [tuple(t), tuple(b + n * W_mm * V.m), tuple(b - n * W_mm * V.m)]
    V.hatch(pts, layer, color=7)
    V.pline(pts, layer, close=True)


def dpl(V, pts, layer="E-OCULTO", close=False, dash_mm=2.5, gap_mm=1.2, **kw):
    """linea oculta dibujada como trazos reales (el visor PDF no escala los tipos de linea en ventanas)"""
    pts = [tuple(map(float, p)) for p in pts]
    if close:
        pts = pts + [pts[0]]
    ls = LineString(pts)
    Lt = ls.length
    d, g = dash_mm * V.m, gap_mm * V.m
    t = 0.0
    while t < Lt - 1e-9:
        a, b = ls.interpolate(t), ls.interpolate(min(t + d, Lt))
        V.line((a.x, a.y), (b.x, b.y), layer)
        t += d + g


def poly_edges_in(V, poly, win, layer, **kw):
    """dibuja el contorno de poly recortado a la ventana, sin los bordes de la ventana"""
    W = box(*win)
    q = poly.intersection(W)
    edge = W.exterior.buffer(1e-4)
    for g in ([q] if q.geom_type == "Polygon" else [g for g in getattr(q, "geoms", []) if g.geom_type == "Polygon"]):
        for ring in [g.exterior] + list(g.interiors):
            vis = LineString(list(ring.coords)).difference(edge)
            for ls in (vis.geoms if hasattr(vis, "geoms") else [vis]):
                if ls.length > 1e-4:
                    if layer == "E-OCULTO":
                        dpl(V, list(ls.coords))
                    else:
                        V.pline(list(ls.coords), layer, **kw)


# ============================================================ 1. PLANTAS 1:25
PWIN = (5.22, -1.02, 11.30, 3.52)


def plan_view(off, tr, plat_tr, first):
    V = View(doc, 25, off)
    m = V.m
    zf = ZF[tr]
    zc = zf + 1.0
    # ejes
    for k in ("A-2", "A-3"):
        u = GU[k]
        V.line((u, -0.90), (u, 3.10), "E-EJES", linetype=V.lt("EJE"))
        V.grid_bubble((u, 3.10 + 5 * m), k)
    for k in ("N-4", "N-3"):
        vv = GV[k]
        V.line((5.52, vv), (11.12, vv), "E-EJES", linetype=V.lt("EJE"))
        V.grid_bubble((5.52 - 5 * m, vv), k)
    # losa del nivel (borde del ducto de escalera)
    if not first:
        for t, e in E.items():
            if e["cat"] == "losa" and abs(e["bbox"][1][2] - zf) < 0.02:
                fp = footprint(e)
                if fp.intersects(box(*PWIN)):
                    poly_edges_in(V, fp, PWIN, "E-VIGA")
                    V.text(f"LOSA NPT {sgn2(zf)}", (7.10, 3.12), 1.8, "E-TEXTO")
    # vigas (ocultas bajo losa / collarin visible)
    for t, e in E.items():
        if e["cat"] != "viga":
            continue
        b0, b1 = e["bbox"]
        if not (zf - 0.65 < b1[2] <= zf + 0.02) or b1[0] < PWIN[0] or b0[0] > PWIN[2] or b1[1] < PWIN[1] or b0[1] > PWIN[3]:
            continue
        fp = footprint(e)
        col = "COLLARIN" in (e["com"] or "")
        if col:
            poly_edges_in(V, fp, PWIN, "E-VIGA")
            c = fp.centroid
            V.text("VIGA COLLARÍN 0.30x0.50", (c.x, c.y), 1.6, "E-TEXTO")
        else:
            poly_edges_in(V, fp, PWIN, "E-OCULTO")
    # columnas
    for t, e in E.items():
        if e["cat"] != "columna":
            continue
        b0, b1 = e["bbox"]
        if not (b0[2] <= zc <= b1[2]) or b1[0] < PWIN[0] or b0[0] > PWIN[2] or b1[1] < PWIN[1] or b0[1] > PWIN[3]:
            continue
        fp = footprint(e)
        pts = list(fp.exterior.coords)[:-1]
        V.hatch(pts, "E-COLUMNA-ACH")
        V.pline(pts, "E-COLUMNA", close=True)
        ct = "C-2" if (e["tipo"] or "").startswith("L_") else "C-1"
        V.text(ct, (fp.bounds[0] + 0.02, fp.bounds[3] + 0.02) if fp.bounds[1] > 1 else (fp.bounds[0] + 0.02, fp.bounds[1] - 0.02),
               1.6, "E-TEXTO", "BOTTOM_LEFT" if fp.bounds[1] > 1 else "TOP_LEFT")
    # cimiento de arranque (oculto)
    if first:
        dpl(V, list(CIMP.exterior.coords))
        V.text("CIMIENTO DE ARRANQUE (abajo)", (6.25, 1.52), 1.5, "E-TEXTO", "BOTTOM_CENTER")
    # piezas de la escalera
    t1, t2 = FL[(tr, "T1")], FL[(tr, "T2")]
    d = FL[(tr, "D")]
    pl_ = FL[(plat_tr, "P")] if plat_tr else None
    for f in (t1, t2):
        V.pline([(f["u0"], f["v0"]), (f["u1"], f["v0"]), (f["u1"], f["v1"]), (f["u0"], f["v1"])], "E-CORTE", close=True)
        for u in f["risers"]:
            V.line((u, f["v0"]), (u, f["v1"]), "E-PROYECCION")
    V.pline([(d[0], d[2]), (d[1], d[2]), (d[1], d[3]), (d[0], d[3])], "E-CORTE", close=True)
    if first:
        pa = FL[(tr, "P")]
        dpl(V, [(pa[0], pa[2]), (pa[1], pa[2]), (pa[1], pa[3]), (pa[0], pa[3])], close=True)
        V.text(f"PLATAFORMA NPT {sgn2(pa[5])} (arriba)", ((pa[0] + pa[1]) / 2, pa[3] - 0.12), 1.5, "E-TEXTO")
    else:
        V.pline([(pl_[0], pl_[2]), (pl_[1], pl_[2]), (pl_[1], pl_[3]), (pl_[0], pl_[3])], "E-CORTE", close=True)
        V.text("PLATAFORMA", ((pl_[0] + pl_[1]) / 2, 1.33), 1.8, "E-TEXTO")
        V.text(f"NPT {sgn2(pl_[5])}", ((pl_[0] + pl_[1]) / 2, 1.18), 1.8, "E-TEXTO")
    V.text("DESCANSO", (d[1] - 0.36, 1.33), 1.8, "E-TEXTO")
    V.text(f"NPT {sgn2(d[5])}", (d[1] - 0.36, 1.18), 1.8, "E-TEXTO")
    # numeracion de contrapasos (numero sobre la huella que sigue a cada contrapaso)
    n = 0
    for f, sgn in ((t1, 1), (t2, -1)):
        vnum = f["v0"] + 0.22 if sgn > 0 else f["v1"] - 0.22
        for i, u in enumerate(f["risers"]):
            n += 1
            if i < len(f["treads"]):
                tu = (f["treads"][i][0] + f["treads"][i][1]) / 2
            else:
                tu = u + sgn * 0.09
            V.text(str(n), (tu, vnum), 2.0, "E-ESC-NUM")
    # flecha SUBE
    ua = (t1["treads"][0][0] + t1["treads"][0][1]) / 2
    ut = d[0] + 0.30
    ue = t2["risers"][-1] - 0.10
    path = [(ua, t1["vc"]), (ut, t1["vc"]), (ut, t2["vc"]), (ue, t2["vc"])]
    V.pline(path, "E-ESC-FLECHA")
    V.circle(path[0], 0.8 * m, "E-ESC-FLECHA", fill=True)
    arrow_head(V, path[-1], (-1, 0))
    V.text("SUBE", (ua + 0.10, t1["vc"] + 0.09), 2.2, "E-TITULO", "MIDDLE_LEFT")
    if first:
        V.text("ARRANQUE", (5.74, 0.44), 1.6, "E-TEXTO")
        V.text(f"NPT {sgn2(zf)}", (5.74, 0.30), 1.6, "E-TEXTO")
    # cotas
    #  abajo: tramo 1 + descanso (+ plataforma)
    if first:
        xs = [t1["u0"], t1["u1"], d[1]]
        tx = [f"{t1['n_p']} p. @ {t1['p']:.3f} = {t1['u1'] - t1['u0']:.2f}".replace(" 0.", " ."), f2(d[1] - d[0])]
    else:
        xs = [pl_[0], t1["u0"], t1["u1"], d[1]]
        tx = [f2(pl_[1] - pl_[0]), f"{t1['n_p']} p. @ {t1['p']:.2f} = {t1['u1'] - t1['u0']:.2f}".replace(" 0.", " ."),
              f2(d[1] - d[0])]
    V.hdim_chain(xs, t1["v0"], -0.50, texts=tx)
    gx = [6.10, GU["A-2"], GU["A-3"], 10.15]
    V.hdim_chain(gx, -0.15, -0.80)
    #  arriba: tramo 2
    xs2 = [t2["u0"], t2["u1"]]
    V.hdim_chain(xs2, t2["v1"], 2.85, texts=[f"{t2['n_p']} p. @ {t2['p']:.3f} = {t2['u1'] - t2['u0']:.2f}".replace(" 0.", " .")])
    #  derecha: anchos
    V.dim((10.15, t1["v0"]), (10.15, t1["v1"]), (10.62, t1["v0"]), 90)
    V.dim((10.15, t2["v0"]), (10.15, t2["v1"]), (10.62, t2["v0"]), 90)
    V.dim((10.15, d[2]), (10.15, d[3]), (10.90, d[2]), 90, dec=3)
    V.dim((10.15, GV["N-4"]), (10.15, GV["N-3"]), (11.18, GV["N-4"]), 90, dec=3)
    # marcas de corte
    section_mark(V, (5.92, t1["vc"]), (10.30, t1["vc"]), "A")
    section_mark(V, (5.92, t2["vc"]), (10.30, t2["vc"]), "B")
    return V


PL1 = plan_view((0, 0), "N1-N2", None, True)
PLT = plan_view((0, 20), "N2-N3", "N1-N2", False)


# ============================================================ 2. CORTES LONGITUDINALES 1:25
def stair_cut(V, val, win, cats=("escalera", "zapata", "viga", "columna", "losa")):
    st, oth = [], []
    for t, e in E.items():
        if e["cat"] not in cats:
            continue
        b0, b1 = e["bbox"]
        if not (b0[1] - 1e-6 <= val <= b1[1] + 1e-6):
            continue
        if b1[0] < win[0] or b0[0] > win[2] or b1[2] < win[1] or b0[2] > win[3]:
            continue
        ps_ = cut_polys(e, 1, val)
        (st if e["cat"] == "escalera" else oth).extend(ps_)
    U = unary_union([p.buffer(2e-4, join_style=2) for p in st]).buffer(-2e-4, join_style=2)
    U = [U] if U.geom_type == "Polygon" else list(U.geoms)
    U = [p.simplify(1e-4) for p in U]
    draw_cut(V, U + oth, win)
    # falso piso (solo contorno)
    for t, e in E.items():
        if e["cat"] == "falsopiso":
            b0, b1 = e["bbox"]
            if b0[1] <= val <= b1[1] and b0[2] < win[3] and b1[2] > win[1]:
                fp = unary_union(cut_polys(e, 1, val)).difference(unary_union(U + oth))
                for g in ([fp] if fp.geom_type == "Polygon" else list(fp.geoms)):
                    poly_edges_in(V, g, win, "E-PROYECCION")
    return U, oth


def pick_bars(val, hosts):
    """barras representativas en el plano v=val: las paralelas mas cercanas (L, S, mecha) y todas las que cruzan (T)"""
    out = []
    for h in hosts:
        for let in ("L", "S", "M"):
            bl = bars_of(h, let)
            if bl:
                out.append(min(bl, key=lambda b: abs(b["pl"][:, 1].mean() - val)))
        out += [b for b in bars_of(h, "T") if b["pl"][:, 1].min() <= val <= b["pl"][:, 1].max()]
    return out


def pt_on(b, frac=None, u=None):
    """punto (u,z) de la barra: en la abscisa u (sobre el tramo mas largo) o fraccion de su tramo mas largo"""
    pl = b["pl"]
    i = int(np.argmax([np.linalg.norm(pl[k + 1] - pl[k]) for k in range(len(pl) - 1)]))
    a, c = pl[i], pl[i + 1]
    if u is not None:
        s = (u - a[0]) / (c[0] - a[0])
    else:
        s = frac
    P = a + (c - a) * s
    return (float(P[0]), float(P[2]))


def seg_pts(b):
    return [(float(p[0]), float(p[2])) for p in b["pl"]]


def slope_dim(V, f, u, side=-1, off_mm=4.0):
    """espesor de garganta: cota perpendicular a la losa con el texto bajo la losa"""
    sl = f["sl"]
    s, th = sl["s"], sl["th"]
    zb = sl["zb0"] + s * (u - sl["u0"])
    nrm = np.array([-math.sin(th) * np.sign(s), math.cos(th)])
    tg = np.array([math.cos(th), math.sin(th) * np.sign(s)])
    p1 = np.array([u, zb])
    p2 = p1 + nrm * sl["t"]
    m = V.m
    for p in (p1, p2):
        V.line(tuple(p - tg * 0.9 * m + nrm * 0.9 * m), tuple(p + tg * 0.9 * m - nrm * 0.9 * m), "E-COTA")
    q = p1 - nrm * 5 * m
    V.line(tuple(p2), tuple(q), "E-COTA")
    V.text(f"t = {sl['t']:.2f}", (q[0], q[1] - 1.6 * m), 1.8, "E-COTA", "TOP_CENTER")


def step_dims(V, f, i, up=True):
    """paso y contrapaso de la huella i"""
    u0, u1, z = f["treads"][i]
    m = V.m
    V.dim((u0, z), (u1, z), (u0, z + 3.2 * m), 0, text=f"p={u1 - u0:.3f}".rstrip("0") if abs((u1 - u0) * 100 - round((u1 - u0) * 100)) > 0.05 else f"p={u1 - u0:.2f}")
    zprev = f["zs"][i]
    ur = f["risers"][i]
    side = -1 if ur == u0 else 1
    V.dim((ur, zprev), (ur, z), (ur + side * 3.4 * m, zprev), 90, text=f"cp={z - zprev:.3f}")


def level_chain(V, zs, x_ref, x_dim, texts):
    V.vdim_chain(zs, x_ref, x_dim, texts=texts)


SECS = {}
# ---------- CORTE A-A: plano v = centro del tramo 1 (N1-N2 desde el cimiento y N2-N3 tipico)
vA = FL[("N1-N2", "T1")]["vc"]
AW = (5.22, -1.30, 11.10, 4.95)
SA = View(doc, 25, (0, 50))
stair_cut(SA, vA, AW)
hostsA = [CIM] + [PC[(tr, p)] for tr in ("N1-N2", "N2-N3") for p in ("LOSA_T1", "DESCANSO_J2", "EXTENSION_PLATAFORMA_J1")]
selA = pick_bars(vA, hostsA)
draw_bars_section(SA, selA, 1, vA, AW, par_tol=0.5)
SECS["A"] = (SA, AW)

# ---------- CORTE B-B: plano v = centro del tramo 2
vB = FL[("N1-N2", "T2")]["vc"]
BW = (5.22, 1.18, 11.10, 6.25)
SBv = View(doc, 25, (0, 80))
stair_cut(SBv, vB, BW)
hostsB = [PC[(tr, p)] for tr in ("N1-N2", "N2-N3") for p in ("LOSA_T2", "DESCANSO_J2", "EXTENSION_PLATAFORMA_J1")]
selB = pick_bars(vB, hostsB)
draw_bars_section(SBv, selB, 1, vB, BW, par_tol=0.5)
SECS["B"] = (SBv, BW)


def bar_sel(sel, host, let):
    for b in sel:
        if b["host"] == host and b["let"] == let:
            return b


def sec_common(V, win, trs, tkey):
    """niveles, ejes, cotas de niveles, paso/contrapaso y garganta"""
    m = V.m
    for k in ("A-2", "A-3"):
        V.line((GU[k], win[1] + 0.05), (GU[k], win[1] + 0.40), "E-EJES", linetype=V.lt("EJE"))
    zs = []
    for tr in trs:
        f = FL[(tr, tkey)]
        d = FL[(tr, "D")]
        zs += [ZF[tr], d[5], ZT[tr]]
    zs = sorted(set(round(z, 3) for z in zs if win[1] < z < win[3]))
    return zs


m = SA.m


def L(V, a, b, s, side=1, h=1.8):
    V.leader(a, b, s, h, side=side)


def dot_of(sel, host, u_near):
    """punto (u,z) de la barra transversal de host mas cercana a u_near"""
    bl = [b for b in sel if b["host"] == host and b["let"] == "T"]
    b = min(bl, key=lambda b: abs(b["pl"][:, 0].mean() - u_near))
    P = b["pl"].mean(0)
    return (float(P[0]), float(P[2]))


def hdim_pts(V, pts, zdim, texts):
    for i in range(len(pts) - 1):
        V.dim(pts[i], pts[i + 1], (pts[i][0], zdim), 0, text=texts[i])


def cp_txt(f):
    return f"{f['n_cp']} cp @ {f['cp']:.3f}".replace(" 0.", " .")


# ---------- anotaciones CORTE A-A
V = SA
f1, f1t = FL[("N1-N2", "T1")], FL[("N2-N3", "T1")]
d1, d2 = FL[("N1-N2", "D")], FL[("N2-N3", "D")]
p2 = FL[("N1-N2", "P")]
# niveles
V.level(5.80, 0.0, "NPT ±0.00", left=True)
V.level(5.72, cb0[2], f"FONDO {cb0[2]:.2f}", left=True)
V.level(5.98, p2[5], f"NPT {sgn2(p2[5])}  (N2)", left=True)
V.level(10.25, d1[5], f"NPT {sgn2(d1[5])}", left=False)
V.level(10.25, d2[5], f"NPT {sgn2(d2[5])}", left=False)
# desniveles (cadena vertical derecha)
zsA = [0.0, d1[5], p2[5], d2[5]]
V.vdim_chain(zsA, 10.74, 10.92, texts=[f"{cp_txt(f1)} = {d1[5]:.2f}", f"{cp_txt(FL[('N1-N2', 'T2')])} = {p2[5] - d1[5]:.2f}",
                                        f"{cp_txt(f1t)} = {d2[5] - p2[5]:.2f}"])
# longitudes en planta
hdim_pts(V, [(f1["u0"], f1["zs"][1]), (f1["u1"], d1[5]), (d1[1], d1[5])], 2.40,
         [f"{f1['n_p']} p @ {f1['p']:.3f} = {f1['u1'] - f1['u0']:.2f}".replace(" 0.", " ."), f"descanso {d1[1] - d1[0]:.2f}"])
hdim_pts(V, [(p2[0], p2[5]), (p2[1], p2[5]), (f1t["u1"], d2[5]), (d2[1], d2[5])], 4.86,
         [f"plataf. {p2[1] - p2[0]:.2f}", f"{f1t['n_p']} p @ {f1t['p']:.2f} = {f1t['u1'] - f1t['u0']:.2f}".replace(" 0.", " ."),
          f"desc. {d2[1] - d2[0]:.2f}"])
# paso / contrapaso / garganta
step_dims(V, f1, 4)
step_dims(V, f1t, 2)
slope_dim(V, f1, 7.95, side=1)
slope_dim(V, f1t, 8.55, side=1)
# acero
h11 = PC[("N1-N2", "LOSA_T1")]
h21 = PC[("N2-N3", "LOSA_T1")]
bL = bar_sel(selA, h11, "L")
bS = bar_sel(selA, h11, "S")
L(V, pt_on(bL, u=7.62), (8.00, 0.36), lab_txt(h11, "L", " inf."))
L(V, dot_of(selA, h11, 8.07), (8.30, 0.62), lab_txt(h11, "T", " transv."))
L(V, pt_on(bS, u=6.95), (6.55, 1.30), lab_txt(h11, "S", " sup."), side=-1)
hd1 = PC[("N1-N2", "DESCANSO_J2")]
L(V, (9.33, bar_sel(selA, hd1, "L")["pl"][0, 2]), (9.33, 1.28), lab_txt(hd1, "L"))
L(V, dot_of(selA, hd1, 9.645), (9.64, 1.52), lab_txt(hd1, "T"))
hp2 = PC[("N1-N2", "EXTENSION_PLATAFORMA_J1")]
L(V, (6.95, bar_sel(selA, hp2, "L")["pl"][0, 2]), (6.62, 3.66), lab_txt(hp2, "L"), side=-1)
L(V, dot_of(selA, hp2, 6.585), (6.40, 3.46), lab_txt(hp2, "T"), side=-1)
bL2 = bar_sel(selA, h21, "L")
bS2 = bar_sel(selA, h21, "S")
L(V, pt_on(bL2, u=8.72), (9.02, 3.52), lab_txt(h21, "L", " inf."))
L(V, dot_of(selA, h21, 8.251), (8.62, 3.28), lab_txt(h21, "T", " transv."))
L(V, pt_on(bS2, u=7.95), (7.62, 4.38), lab_txt(h21, "S", " sup."), side=-1)
hd2 = PC[("N2-N3", "DESCANSO_J2")]
L(V, (9.62, bar_sel(selA, hd2, "L")["pl"][0, 2]), (9.62, 3.92), lab_txt(hd2, "L"))
L(V, dot_of(selA, hd2, 9.915), (9.91, 4.12), lab_txt(hd2, "T"))
mA = [b for b in selA if b["let"] == "M"][0]
L(V, (float(mA["pl"][0, 0]), -0.55), (6.62, -0.42), f'{mA["code"]}: {len(mech_all := bars_of(CIM, "M"))} mechas Ø3/8" (ver detalle)')
V.text("CIMIENTO DE", (6.25, -0.72), 1.6, "E-TEXTO")
V.text("ARRANQUE", (6.25, -0.80), 1.6, "E-TEXTO")
# anclajes medidos (tramo tipico)
pl = bL2["pl"]
V.dim((pl[0, 0], pl[0, 2]), (pl[1, 0], pl[1, 2]), (pl[0, 0], 2.86), 0, text=f"{segs(bL2)[0]:.2f}")
pl = bL["pl"]
V.dim((pl[-3, 0], pl[-1, 2]), (pl[-1, 0], pl[-1, 2]), (pl[-3, 0], 2.16), 0, text=f"{segs(bL)[-1]:.2f}")
pl = bL2["pl"]
V.dim((pl[-3, 0], pl[-1, 2]), (pl[-1, 0], pl[-1, 2]), (pl[-3, 0], 4.62), 0, text=f"{segs(bL2)[-1]:.2f}")
for k in ("A-2", "A-3"):
    V.line((GU[k], AW[1] + 0.02 + 8.4 * m), (GU[k], -1.05), "E-EJES", linetype=V.lt("EJE"))
    V.grid_bubble((GU[k], AW[1] + 0.02 + 4.4 * m), k, 4)

# ---------- anotaciones CORTE B-B
V = SBv
f2_, f2t = FL[("N1-N2", "T2")], FL[("N2-N3", "T2")]
p3 = FL[("N2-N3", "P")]
V.level(5.98, p2[5], f"NPT {sgn2(p2[5])}  (N2)", left=True)
V.level(5.98, p3[5], f"NPT {sgn2(p3[5])}  (N3)", left=True)
V.level(10.25, d1[5], f"NPT {sgn2(d1[5])}", left=False)
V.level(10.25, d2[5], f"NPT {sgn2(d2[5])}", left=False)
zsB = [d1[5], p2[5], d2[5], p3[5]]
V.vdim_chain(zsB, 10.74, 10.92, texts=[f"{cp_txt(f2_)} = {p2[5] - d1[5]:.2f}", f"{cp_txt(f1t)} = {d2[5] - p2[5]:.2f}",
                                        f"{cp_txt(f2t)} = {p3[5] - d2[5]:.2f}"])
hdim_pts(V, [(p2[0], p2[5]), (p2[1], p2[5]), (f2_["u1"], d1[5]), (d1[1], d1[5])], 3.47,
         [f"plataf. {p2[1] - p2[0]:.2f}", f"{f2_['n_p']} p @ {f2_['p']:.3f} = {f2_['u1'] - f2_['u0']:.2f}".replace(" 0.", " ."),
          f"descanso {d1[1] - d1[0]:.2f}"])
hdim_pts(V, [(p3[0], p3[5]), (p3[1], p3[5]), (f2t["u1"], d2[5]), (d2[1], d2[5])], 6.07,
         [f"plataf. {p3[1] - p3[0]:.2f}", f"{f2t['n_p']} p @ {f2t['p']:.2f} = {f2t['u1'] - f2t['u0']:.2f}".replace(" 0.", " ."),
          f"desc. {d2[1] - d2[0]:.2f}"])
step_dims(V, f2_, 4)
step_dims(V, f2t, 5)
slope_dim(V, f2_, 8.45, side=-1)
slope_dim(V, f2t, 8.45, side=-1)
h12 = PC[("N1-N2", "LOSA_T2")]
h22 = PC[("N2-N3", "LOSA_T2")]
for h, zl, zt_, zs_, ul, us in ((h12, 2.05, 1.83, 3.02, 7.75, 8.2), (h22, 4.62, 4.40, 5.62, 7.75, 8.2)):
    bL_ = bar_sel(selB, h, "L")
    bS_ = bar_sel(selB, h, "S")
    L(V, pt_on(bL_, u=ul), (ul - 0.30, zl), lab_txt(h, "L", " inf."), side=-1)
    L(V, dot_of(selB, h, ul + 0.35), (ul + 0.05, zt_), lab_txt(h, "T", " transv."), side=-1)
    L(V, pt_on(bS_, u=us), (us + 0.35, zs_), lab_txt(h, "S", " sup."))
for hd, z0_ in ((PC[("N1-N2", "DESCANSO_J2")], 1.56), (PC[("N2-N3", "DESCANSO_J2")], 4.04)):
    zb = bar_sel(selB, hd, "L")["pl"][0, 2]
    L(V, (9.33, zb), (9.33, z0_), lab_txt(hd, "L"))
    L(V, dot_of(selB, hd, 9.645), (9.64, z0_ + 0.19), lab_txt(hd, "T"))
hp3 = PC[("N2-N3", "EXTENSION_PLATAFORMA_J1")]
for hp, zl in ((hp2, 2.90), (hp3, 5.50)):
    zb = bar_sel(selB, hp, "L")["pl"][0, 2]
    L(V, (6.20, zb), (6.12, zl), lab_txt(hp, "L"), side=-1)
    L(V, dot_of(selB, hp, 6.13), (6.02, zl - 0.18), lab_txt(hp, "T"), side=-1)
nj1 = rect(PC[("N1-N2", "NUDO_PRISMATICO_J1")])
V.leader(((nj1[0] + nj1[1]) / 2, (nj1[5] + p2[4]) / 2), (6.70, 2.36), f"vacío de {p2[4] - nj1[5]:.2f} en el modelo (obs. 3)",
         1.5, side=-1, layer="E-TEXTO")
for k in ("A-2", "A-3"):
    V.line((GU[k], BW[1] + 0.02 + 8.4 * m), (GU[k], 1.80), "E-EJES", linetype=V.lt("EJE"))
    V.grid_bubble((GU[k], BW[1] + 0.02 + 4.4 * m), k, 4)

# ============================================================ 3. CIMIENTO DE ARRANQUE 1:20 (corte C-C y planta)
mech = sorted(bars_of(CIM, "M"), key=lambda b: b["pl"][:, 1].mean())
vC = float(mech[2]["pl"][:, 1].mean())
CW = (5.40, -1.36, 7.75, 0.80)
CE = View(doc, 20, (0, 110))
stair_cut(CE, vC, CW)
selC = pick_bars(vC, [CIM, h11])
draw_bars_section(CE, selC, 1, vC, CW, par_tol=0.5)
V = CE
mc = [b for b in selC if b["let"] == "M"][0]
bLc = bar_sel(selC, h11, "L")
bSc = bar_sel(selC, h11, "S")
mp = mc["pl"]
u_m = float(mp[0, 0])
z_bot, z_bend = float(mp[0, 2]), float(mp[1, 2])
V.hdim_chain([cb0[0], f1["u0"], cb1[0]], cb0[2], cb0[2] - 5 * V.m)
V.dim((cb0[0], cb0[2]), (cb1[0], cb0[2]), (cb0[0], cb0[2] - 10 * V.m), 0)
V.vdim_chain([cb0[2], z_bot, z_bend], cb0[0], cb0[0] - 6 * V.m)
V.dim((cb0[0], cb0[2]), (cb0[0], cb1[2]), (cb0[0] - 12 * V.m, cb0[2]), 90)
# traslape mecha - barra superior (a lo largo de la pendiente)
s0 = np.array([bSc["pl"][0, 0], bSc["pl"][0, 2]])
e0 = np.array([mp[-1, 0], mp[-1, 2]])
dd = (e0 - s0) / np.linalg.norm(e0 - s0)
nn = np.array([-dd[1], dd[0]])
lap = float(np.linalg.norm(e0 - s0))
ang = math.degrees(math.atan2(dd[1], dd[0]))
V.dim(tuple(s0), tuple(e0), tuple(s0 + nn * 9 * V.m), ang, text=f"traslape {lap:.2f}")
V.level(5.97, 0.0, "NPT ±0.00", left=True)
V.level(cb1[0] + 0.10, cb0[2], f"FONDO {cb0[2]:.2f}", left=False)
L(V, (u_m, -0.35), (6.62, -0.30), f'{mc["code"]}: mecha Ø3/8" L={mc["L"]:.2f}', side=1)
V.text(f"({len(mech)} und., vertical {z_bend - z_bot:.2f} + {segs(mc)[-1]:.2f} en pendiente)", (6.66, -0.39), 1.5,
       "E-ACERO-TXT", "MIDDLE_LEFT")
L(V, pt_on(bLc, u=6.80), (7.00, 0.28), f'{bLc["code"]}: inf. (llega recto)', side=1)
L(V, pt_on(bSc, u=6.72), (6.55, 0.68), f'{bSc["code"]}: sup.', side=-1)
L(V, dot_of(selC, h11, 6.496), (7.00, 0.14), f'{bars_of(h11, "T")[0]["code"]}: transv.', side=1)
V.text("CIMIENTO", ((cb0[0] + cb1[0]) / 2, -0.78), 2.0, "E-TITULO")
V.text(f"{cb1[1] - cb0[1]:.2f} x {cb1[0] - cb0[0]:.2f} x {cb1[2] - cb0[2]:.2f}", ((cb0[0] + cb1[0]) / 2, -0.86), 1.6, "E-TEXTO")
V.text("rec. 7.5 cm", (u_m + 0.02, -0.95), 1.4, "E-ACERO-TXT", "MIDDLE_LEFT")
V.text("falso piso", (7.25, -0.05), 1.4, "E-TEXTO")

# planta del cimiento
CPW = (5.62, -0.30, 7.40, 1.66)
CP = View(doc, 20, (0, 125))
V = CP
V.hatch([(6.1, -0.15), (6.7, -0.15), (6.7, 0.15), (6.1, 0.15)], "E-COLUMNA-ACH")
V.pline([(6.1, -0.15), (6.7, -0.15), (6.7, 0.15), (6.1, 0.15)], "E-COLUMNA", close=True)
V.text("C-1", (6.40, 0.0), 1.6, "E-TEXTO")
V.pline(list(CIMP.exterior.coords), "E-ZAPATA")
dpl(V, [(f1["u0"], f1["v0"]), (6.98, f1["v0"])])
dpl(V, [(f1["u0"], f1["v1"]), (6.98, f1["v1"])])
dpl(V, [(f1["u0"], f1["v0"]), (f1["u0"], f1["v1"])])
for u in f1["risers"][:3]:
    dpl(V, [(u, f1["v0"]), (u, f1["v1"])])
V.text("TRAMO 1 (arriba)", (7.02, (f1["v0"] + f1["v1"]) / 2), 1.5, "E-TEXTO", rot=90)
for b in mech:
    p = b["pl"]
    V.circle((p[0, 0], p[0, 1]), 0.55 * V.m, "E-ACERO", fill=True)
    V.pline([(p[1, 0], p[1, 1]), (p[-1, 0], p[-1, 1])], "E-ACERO")
vm = [float(b["pl"][0, 1]) for b in mech]
V.vdim_chain([cb0[1]] + vm + [cb1[1]], cb0[0], 5.74, texts=[f"{b_ - a_:.2f}" for a_, b_ in zip([cb0[1]] + vm, vm + [cb1[1]])])
V.dim((cb1[0], cb0[1]), (cb1[0], cb1[1]), (6.86, cb0[1]), 90)
V.dim((cb0[0], cb1[1]), (cb1[0], cb1[1]), (cb0[0], cb1[1] + 6 * V.m), 0)
V.dim((cb0[0], cb1[1]), (f1["u0"], cb1[1]), (cb0[0], cb1[1] + 11 * V.m), 0)
L(V, (vm[-1] * 0 + mech[-1]["pl"][0, 0], vm[-1]), (6.20, 1.60), "mecha extrema: sin recubr. lateral (obs. 1)", side=1, h=1.4)
section_mark(V, (6.00, vC), (6.62, vC), "C")

# ============================================================ 4. SECCION TRANSVERSAL TIPICA DE TRAMO 1:10 (perpendicular a la losa)
TS = View(doc, 10, (0, 140))
V = TS
ft = FL[("N2-N3", "T1")]
sl = ft["sl"]
s_, th = sl["s"], sl["th"]


def nloc(P):
    zb = sl["zb0"] + s_ * (P[0] - sl["u0"])
    return (P[2] - zb) * math.cos(th)


tt = sl["t"]
V.hatch([(ft["v0"], 0), (ft["v1"], 0), (ft["v1"], tt), (ft["v0"], tt)], "E-CORTE-ACH")
V.pline([(ft["v0"], 0), (ft["v1"], 0), (ft["v1"], tt), (ft["v0"], tt)], "E-CORTE", close=True)
umid = 8.18
TSD = {}
for let in ("L", "S"):
    for b in bars_of(ft["tag"], let):
        p = b["pl"]
        i = int(np.argmax([np.linalg.norm(p[k + 1] - p[k]) for k in range(len(p) - 1)]))
        a, c = p[i], p[i + 1]
        P = a + (c - a) * ((umid - a[0]) / (c[0] - a[0]))
        V.circle((P[1], nloc(P)), RAD["3/8"], "E-ACERO", fill=True)
        TSD.setdefault(let, []).append((float(P[1]), nloc(P)))
bt = min(bars_of(ft["tag"], "T"), key=lambda b: abs(b["pl"][:, 0].mean() - umid))
pT = bt["pl"]
nT = nloc(pT.mean(0))
V.pline([(pT[0, 1], nT), (pT[-1, 1], nT)], "E-ACERO", const_width=2 * RAD["3/8"])
TSD["T"] = (float(pT[0, 1]), float(pT[-1, 1]), nT)
V.dim((ft["v0"], 0), (ft["v1"], 0), (ft["v0"], -0.045), 0)
V.dim((ft["v1"], 0), (ft["v1"], tt), (ft["v1"] + 0.05, 0), 90, text=f"t={tt:.2f}")
yL = TSD["L"][0][1]
yS = TSD["S"][0][1]
V.dim((ft["v0"], 0), (ft["v0"], yL - RAD["3/8"]), (ft["v0"] - 0.035, 0), 90, text=f"{yL - RAD['3/8']:.3f}")
V.dim((ft["v0"], yS + RAD["3/8"]), (ft["v0"], tt), (ft["v0"] - 0.035, yS), 90, text=f"{tt - yS - RAD['3/8']:.3f}")
xs_L = sorted(x for x, _ in TSD["L"])
V.hdim_chain([ft["v0"]] + xs_L + [ft["v1"]], 0, tt + 0.07,
             texts=[f"{b_ - a_:.3f}" if abs((b_ - a_) * 100 - round((b_ - a_) * 100)) > 0.05 else f"{b_ - a_:.2f}"
                    for a_, b_ in zip([ft["v0"]] + xs_L, xs_L + [ft["v1"]])])
L(V, TSD["L"][2], (0.52, -0.075), f'{code_of(ft["tag"], "L")}: long. inf. (capa 1)', side=-1, h=1.8)
L(V, TSD["S"][3], (1.00, 0.33), f'{code_of(ft["tag"], "S")}: long. sup.', side=1, h=1.8)
L(V, (0.98, nT), (1.08, -0.075), f'{bt["code"]}: transv. (capa 2)', side=1, h=1.8)
V.text("(eje de barras de capa 1 a capa 2: {:.1f} mm)".format((nT - yL) * 1000), ((ft["v0"] + ft["v1"]) / 2, -0.125), 1.6,
       "E-TEXTO")

# ------------------------------------------------------------------ hoja
ps = new_sheet(doc, "E-09")
if "E-HOJA" not in doc.layers:
    doc.layers.add("E-HOJA", color=8).dxf.lineweight = 5
ps.add_lwpolyline([(0.2, 0.2), (W_ - 0.2, 0.2), (W_ - 0.2, H_ - 0.2), (0.2, H_ - 0.2)], close=True,
                  dxfattribs={"layer": "E-HOJA"})      # borde de corte de la hoja (fija la escala 1:1 del PDF)


def place(V, win, cx, cy, extra=(0, 0), k=None):
    k = k or V.k
    w = (win[2] - win[0]) * 1000 / k + extra[0]
    h = (win[3] - win[1]) * 1000 / k + extra[1]
    add_vp(ps, cx, cy, w, h, V.P((win[0] + win[2]) / 2, (win[1] + win[3]) / 2), k)
    return w, h


# plantas
place(PL1, PWIN, 27 + 122, 584 - 3 - 91)
view_title(ps, 149, 584 - 3 - 182 - 8, "PLANTA ESCALERA - PRIMER PISO (N1 → N2)", "ESC. 1:25", w=110)
place(PLT, PWIN, 149, 390 - 13 - 91)
view_title(ps, 149, 390 - 13 - 182 - 8, "PLANTA ESCALERA - PISO TÍPICO (N2→N3, N3→N4, N4→N5)", "ESC. 1:25  (dibujado N2 → N3)", w=140)
# cortes
place(SA, AW, 277 + 118, 584 - 3 - 127)
view_title(ps, 395, 584 - 3 - 254 - 8, "CORTE A-A  TRAMO 1  (N1→N2 desde el cimiento y N2→N3 típico)", "ESC. 1:25", w=160)
place(SBv, BW, 520 + 118, 584 - 3 - 102)
view_title(ps, 638, 584 - 3 - 203 - 8, "CORTE B-B  TRAMO 2  (N1→N2 y N2→N3 típico)", "ESC. 1:25", w=130)
# cimiento
place(CE, CW, 27 + 60, 100)
view_title(ps, 87, 100 - 54 - 7, "CORTE C-C  CIMIENTO DE ARRANQUE", "ESC. 1:20", w=95)
place(CP, CPW, 27 + 60 + 59 + 50, 100)
view_title(ps, 196, 100 - 49 - 7, "PLANTA CIMIENTO DE ARRANQUE", "ESC. 1:20", w=80)
TSW = (0.00, -0.15, 1.40, 0.36)
place(TS, TSW, 395, 272)
view_title(ps, 395, 272 - 26 - 7, "SECCIÓN TÍPICA DE TRAMO (perpendicular a la losa)", "ESC. 1:10  (tramo 1, N2→N3)", w=130)

# ------------------------------------------------------------ cuadro de tramos (geometria medida)
rows = [["PISO", "TRAMO 1: contrapasos / pasos", "TRAMO 2: contrapasos / pasos", "TOTAL", "DESCANSO", "LLEGADA"]]
for tr in TRS:
    a, b = FL[(tr, "T1")], FL[(tr, "T2")]
    d = FL[(tr, "D")]
    def ft_(f):
        return f"{f['n_cp']} x {f['cp']:.4f} / {f['n_p']} x {f['p']:.3f}"
    rows.append([tr, ft_(a), ft_(b), f"{a['n_cp'] + b['n_cp']} cp", f"NPT {sgn2(d[5])}  L={d[1] - d[0]:.2f}", f"NPT {sgn2(ZT[tr])}"])
tx0, ty0 = 280, 216
Wt, Ht = table(ps, tx0, ty0, [16, 52, 52, 16, 44, 24], rows, row_h=5.6, h_txt=2.0)
ptext(ps, "CUADRO DE TRAMOS (medido del modelo, m)", (tx0, ty0 + 2), 3.0, "E-TITULO")
ang1 = math.degrees(FL[("N1-N2", "T1")]["sl"]["th"])
ang2 = math.degrees(FL[("N1-N2", "T2")]["sl"]["th"])
angt = math.degrees(FL[("N2-N3", "T1")]["sl"]["th"])
ptext(ps, f"Ancho de tramo 1.10 (junta 0.015 entre tramos); garganta t = 0.15 perpendicular; pendiente: N1-N2 T1 {ang1:.1f}°, "
          f"T2 {ang2:.1f}°; típico {angt:.1f}°.", (tx0, ty0 - Ht - 4), 1.8)
ptext(ps, "Plataforma de llegada 1.20 x 2.215 (e = 0.15) en cada nivel. 2cp + p (N1-N2) = "
          f"{2 * FL[('N1-N2', 'T1')]['cp'] + FL[('N1-N2', 'T1')]['p']:.3f}; típico = "
          f"{2 * FL[('N2-N3', 'T1')]['cp'] + FL[('N2-N3', 'T1')]['p']:.3f}.", (tx0, ty0 - Ht - 8), 1.8)

# ------------------------------------------------------------ cuadro de acero (planilla)
rows = [["CÓD.", "DESCRIPCIÓN", "FORMA", "TRAMOS (m)", "Ø", "CANT.", "LONG. (m)", "TOTAL (m)", "PESO (kg)"]]
tot_w = 0.0
tot_n = 0
shapes = []
for k, bl in groups.items():
    b0_ = bl[0]
    n = len(bl)
    Lb = float(np.mean([b["L"] for b in bl]))
    w_ = sum(b["L"] for b in bl) * KG["3/8"]
    tot_w += w_
    tot_n += n
    rows.append([CODE[k], code_desc(k), "", " / ".join(f"{x:.2f}" for x in segs(b0_)), 'Ø3/8"', str(n), f"{Lb:.2f}",
                 f"{sum(b['L'] for b in bl):.2f}", f"{w_:.1f}"])
    shapes.append(b0_)
rows.append(["", "TOTAL ACERO DE ESCALERA (0.56 kg/m)", "", "", "", str(tot_n), "",
             f"{sum(b['L'] for b in SB):.2f}", f"{tot_w:.1f}"])
cx0, cy0 = 520, 350
cw = [11, 92, 30, 44, 11, 12, 16, 17, 17]
rh = 7.0
Wc, Hc = table(ps, cx0, cy0, cw, rows, row_h=rh, h_txt=2.0, aligns=["C", "L", "C", "C", "C", "C", "C", "C", "C"])
ptext(ps, "CUADRO DE ACERO DE ESCALERA (planilla, medido del modelo)", (cx0, cy0 + 2), 3.0, "E-TITULO")
fx0 = cx0 + cw[0] + cw[1]
for i, b in enumerate(shapes):
    pl = b["pl"]
    if np.ptp(pl[:, 0]) >= np.ptp(pl[:, 1]):
        P = pl[:, [0, 2]].copy()
    else:
        P = pl[:, [1, 2]].copy()
    if b["let"] in ("L", "S") and b["pz"] == "LOSA_T2":
        P[:, 0] = -P[:, 0]
    P -= P.min(0)
    ext = np.maximum(P.max(0), 1e-6)
    sc = min((cw[2] - 4) / ext[0], (rh - 2) / ext[1] if ext[1] > 1e-3 else 1e9)
    yc = cy0 - (i + 1.5) * rh
    Q = [(fx0 + 2 + x * sc + ((cw[2] - 4) - ext[0] * sc) / 2, yc - ext[1] * sc / 2 + y * sc) for x, y in P]
    ps.add_lwpolyline(Q, dxfattribs={"layer": "E-ACERO"})
ptext(ps, "TRAMOS: longitudes de los segmentos de la barra según el modelo (Revit), en orden. LONG.: longitud de corte "
          "de una barra.", (cx0, cy0 - Hc - 4), 1.8)
ptext(ps, "Códigos E# en los cortes. Cantidades: todas las barras modeladas (4 pisos de escalera + cimiento).",
      (cx0, cy0 - Hc - 7.5), 1.8)

# ------------------------------------------------------------ notas
m1 = sorted(bars_of(CIM, "M"), key=lambda b: b["pl"][:, 1].mean())[0]
lapv = lap
notas = [
    "NOTAS - ESCALERA",
    "1. CONCRETO f'c = 210 kg/cm² en tramos, descansos, plataformas y cimiento de arranque.",
    "2. ACERO corrugado ASTM A615 Grado 60, fy = 4200 kg/cm². Todo el acero de escalera es Ø3/8\" (0.56 kg/m).",
    "3. RECUBRIMIENTO libre 2 cm en losas de escalera (E.060 7.7.1); cimiento de arranque 7.5 cm contra el terreno.",
    "4. Losa (garganta) e = 0.15 m. Malla inferior Ø3/8\" en dos capas (capa 1 longitudinal abajo, capa 2 transversal)",
    "    y acero superior longitudinal Ø3/8\" corrido; separación de diseño @ 0.25 máx., modelada @ .19 - .24 (ver cortes).",
    "5. ANCLAJES (medidos): extremo bajo, inferior entra horizontal 0.49 en la plataforma; superior baja y entra 0.36.",
    "    Extremo alto: ambas capas suben en el nudo y doblan 0.40 horizontales ARRIBA en el descanso/plataforma.",
    f"6. ARRANQUE (fig. 107, Manual del Maestro Constructor - Aceros Arequipa): el inferior llega recto al cimiento;",
    f"    el superior traslapa {lapv:.2f} con mechas Ø3/8\" que salen del cimiento (vertical {z_bend - z_bot:.2f} a 7.5 cm de su cara posterior).",
    "7. Traslape de Ø3/8\" = 0.45 m. El cimiento se vacía antes que la escalera (dejar mechas).",
    "8. Cimiento de arranque 1.25 x 0.50 x 1.00, fondo -1.00: confirmar capacidad portante a esa profundidad (EMS a Df 2.00).",
    "9. Niveles NPT en metros. Plano generado del modelo IFC 'Proyect sj.ifc'; acero tal como está modelado.",
]
ny = notes(ps, 280, 168, notas, h=2.1, lead=4.4)
obs = [
    "OBSERVACIONES DEL MODELO (revisar antes de emitir)",
    "1. Mecha extrema del cimiento (E1, a 0.004 del borde del tramo 1): queda en la cara lateral, sin recubrimiento.",
    "2. Tramo 1 N1-N2: patas superiores en el descanso con recubr. 1.2-1.4 cm; barras de borde del descanso y",
    "    plataforma N1-N2 (a 1.5 cm del borde) con 1.0 cm. Deben quedar a 2 cm libres.",
    "3. Nudo de llegada del tramo 2 (J1) termina 0.05 bajo el fondo de la plataforma (+3.00 vs +3.05; igual en N3-N5):",
    "    vacío en el modelo que atraviesan los anclajes del tramo 2. En obra se vacía monolítico.",
    "4. Capa 2 (transversal) a 4.5 mm de eje de la capa 1 (7.3 mm en T2 N1-N2): las mallas se interfieren en el modelo;",
    "    en obra la transversal apoya sobre la longitudinal.",
    "5. Acero superior sin barras transversales de repartición en el modelo: definir (sugerido Ø3/8\" @ .25).",
    "6. Descansos intermedios sin viga de apoyo modelada (apoyan en los tramos y en las caras de columnas A-3).",
]
notes(ps, 520, 234, obs, h=2.1, lead=4.4)

title_block(ps, "E-09", ["ESCALERA: PLANTAS, CORTES, CIMIENTO DE", "ARRANQUE Y CUADRO DE ACERO"])
import os


def render(doc, ps, base, pdf=True, dpi=110):
    """como save_and_render de sheetcommon pero sin fit_page: la hoja sale a escala real 1:1 (841x594 mm)"""
    doc.set_modelspace_vport(height=20, center=(5, 5))
    doc.saveas(base + ".dxf")
    from ezdxf.addons.drawing import Frontend, RenderContext, pymupdf, layout, config
    be = pymupdf.PyMuPdfBackend()
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE, color_policy=config.ColorPolicy.COLOR,
                               lineweight_policy=config.LineweightPolicy.ABSOLUTE, lineweight_scaling=1.0,
                               min_lineweight=0.09, hatch_policy=config.HatchPolicy.NORMAL,
                               line_policy=config.LinePolicy.ACCURATE)
    Frontend(RenderContext(doc), be, config=cfg).draw_layout(
        ps, filter_func=lambda e: e.dxf.layer != "E-VPORT" or e.dxftype() == "VIEWPORT")
    page = layout.Page(W_, H_, layout.Units.mm, margins=layout.Margins.all(0))
    st_ = layout.Settings(fit_page=False, scale=1.0)
    open(base + "_preview.png", "wb").write(be.get_pixmap_bytes(page, fmt="png", dpi=dpi, settings=st_))
    if pdf:
        open(base + ".pdf", "wb").write(be.get_pdf_bytes(page, settings=st_))


render(doc, ps, "E-09_Escalera", pdf=not os.environ.get("QUICK"))
print("ok")
