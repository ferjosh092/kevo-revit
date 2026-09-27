"""Lamina E-01 - CIMENTACION, generada del modelo IFC (Proyect sj.ifc).
Entradas: cim.json (extract_cim.py) y mesh.pkl (extract_mesh.py).
Salidas: E-01_Cimentacion.dxf (modelo en metros + hoja A1 con ventanas) y E-01_Cimentacion.pdf."""
import json, math, pickle, collections, sys
import numpy as np
from shapely.geometry import Polygon, LineString, box, MultiLineString, Point
from shapely.ops import unary_union, polygonize, linemerge
import ezdxf
from sheetlib import (new_doc, add_layers, View, section_mark, frame_and_title, ptext, view_title, add_vp, table)

KG = {"1/4": 0.250, "3/8": 0.560, "1/2": 0.994, "5/8": 1.552, "3/4": 2.235}
cim = json.load(open("cim.json"))
MS = pickle.load(open("mesh.pkl", "rb"))
meshes = MS["meshes"]
grids = cim["grids"]
GU = {k: g["pos"] for k, g in grids.items() if g["dir"] == "v"}   # ejes A -> coordenada u
GV = {k: g["pos"] for k, g in grids.items() if g["dir"] == "u"}   # ejes N -> coordenada v
import pickle as _pk
from beamdesign import corrected_bars
_M = _pk.load(open("model_all.pkl", "rb"))
_cb, DESIGN_POS = corrected_bars(_M)
_hosts = {x["id"] for x in cim["footings"]} | {x["id"] for x in cim["columns"]} | {x["id"] for x in cim["beams"]}
bars = [dict(b, pl=np.asarray(b["pl"], float).tolist()) for b in _cb if b["host"] in _hosts or "MECHA" in b["role"]]


def dstr(d):
    return f'Ø{d}"'


def f2(x):
    s = f"{x:.2f}"
    return s


def f3(x):
    return f"{x:.3f}".rstrip("0").rstrip(".") if abs(x * 100 - round(x * 100)) > 1e-6 else f"{x:.2f}"


def mark_of(z):
    return z["com"].split("|")[1]


# ------------------------------------------------------------------ datos de zapatas
foot = [z for z in cim["footings"] if z["tipo"].startswith("ZR_")]
cim_esc = [z for z in cim["footings"] if z["tipo"].startswith("CIM_ESC")][0]
sizes = sorted({(round(z["B"], 3), round(z["L"], 3), round(z["h"], 3)) for z in foot})
TYPE = {s: f"Z-{i + 1}" for i, s in enumerate(sizes)}
for z in foot:
    z["T"] = TYPE[(round(z["B"], 3), round(z["L"], 3), round(z["h"], 3))]
    p = np.array(z["poly"])
    z["u0"], z["u1"], z["v0"], z["v1"] = p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()
    m = mark_of(z)
    z["gv"] = m.split("-A-")[0]
    z["gu"] = "A-" + m.split("-A-")[1]

cols = cim["columns"]
for c in cols:
    p = np.array(c["poly"])
    c["u0"], c["u1"], c["v0"], c["v1"] = p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()
    c["CT"] = "C-2" if c["tipo"].startswith("L_") else "C-1"
colby = {c["mark"]: c for c in cols}


def col_on(z):
    """columna apoyada en la zapata z"""
    fp = Polygon(z["poly"])
    best = None
    for c in cols:
        a = Polygon(c["poly"]).intersection(fp).area
        if a > 0.01 and (best is None or a > best[0]):
            best = (a, c)
    return best[1] if best else None


def bar_arr(b):
    return np.array(b["pl"])


def parrilla(z):
    """Resumen de la parrilla de una zapata: por direccion (X=u, Y=v): n, diametro, separacion."""
    out = {}
    for b in [b for b in bars if b["host"] == z["id"]]:
        pl = bar_arr(b)
        dirn = "X" if np.ptp(pl[:, 0]) > np.ptp(pl[:, 1]) else "Y"
        pos = pl[:, 1].mean() if dirn == "X" else pl[:, 0].mean()
        o = out.setdefault(dirn, {"d": b["d"], "pos": [], "L": b["L"], "segs": b["segs"], "z": pl[:, 2].min()})
        o["pos"].append(pos)
    for o in out.values():
        o["pos"].sort()
        o["n"] = len(o["pos"])
        o["s"] = (o["pos"][-1] - o["pos"][0]) / (o["n"] - 1)
    return out


for z in foot:
    z["par"] = parrilla(z)


def sep_txt(s):
    return f"@ {s:.2f}".replace("0.", ".")


def par_txt(o):
    return f'{o["n"]} {dstr(o["d"])} {sep_txt(o["s"])}'


# ------------------------------------------------------------------ utilidades de corte
def slice_mesh(V, F, axis, val):
    """Interseccion de una malla con el plano coord[axis]=val. Devuelve segmentos en (otra, z)."""
    other = 0 if axis == 1 else 1
    d = V[:, axis] - val
    segs = []
    for t in F:
        dd = d[t]
        if dd.max() < -1e-9 or dd.min() > 1e-9:
            continue
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = dd[i], dd[j]
            if (a < 0 < b) or (b < 0 < a):
                s = a / (a - b)
                P = V[t[i]] + s * (V[t[j]] - V[t[i]])
                pts.append((P[other], P[2]))
            elif abs(a) <= 1e-9:
                pts.append((V[t[i]][other], V[t[i]][2]))
        pts = list(dict.fromkeys([(round(x, 6), round(y, 6)) for x, y in pts]))
        if len(pts) >= 2:
            segs.append(LineString(pts[:2]))
    return segs


def cut_polys(tag, axis, val):
    m = meshes[tag]
    segs = slice_mesh(m["v"], m["f"], axis, val)
    if not segs:
        return []
    polys = list(polygonize(unary_union(segs)))
    u = unary_union(polys)
    return [u] if u.geom_type == "Polygon" else list(u.geoms)


def draw_cut(v, polys, win, fill=True):
    W = box(*win)
    for p in polys:
        q = p.intersection(W)
        if q.is_empty:
            continue
        for g in ([q] if q.geom_type == "Polygon" else [g for g in getattr(q, "geoms", []) if g.geom_type == "Polygon"]):
            pts = list(g.exterior.coords)[:-1]
            if fill:
                v.hatch(pts, "E-CORTE-ACH")
            # contorno sin los bordes sobre la ventana (alli va linea de corte)
            ring = LineString(list(g.exterior.coords))
            edge = W.exterior.buffer(1e-4)
            vis = ring.difference(edge)
            for ls in (vis.geoms if hasattr(vis, "geoms") else [vis]):
                if ls.length > 1e-4:
                    v.pline(list(ls.coords), "E-CORTE")
            # lineas de quiebre donde el elemento sigue fuera de la ventana
            brk = ring.intersection(edge)
            for ls in (brk.geoms if hasattr(brk, "geoms") else [brk]):
                if ls.geom_type == "LineString" and ls.length > 0.05:
                    c = list(ls.coords)
                    v.break_line(c[0], c[-1])


def draw_bars_section(v, blist, axis, val, win, dot_min_mm=0.45, par_tol=0.35, force_dots=False):
    """Acero en un corte por el plano coord[axis]=val. Barras que cruzan el plano -> punto;
    barras casi paralelas al plano (a menos de par_tol) -> proyeccion. Todo recortado a win."""
    other = 0 if axis == 1 else 1
    W = box(*win)
    dots = []
    for b in blist:
        pl = np.array(b["pl"])
        r = {"1/4": 0.00318, "3/8": 0.00476, "1/2": 0.00635, "5/8": 0.00794, "3/4": 0.00953}[b["d"]]
        if b.get("role", "").startswith("ESTRIBO") and not force_dots:
            if abs(pl[:, axis].mean() - val) < 0.9:
                ls = LineString(pl[:, [other, 2]])
                q = ls.intersection(W)
                for g in (q.geoms if hasattr(q, "geoms") else [q]):
                    if g.geom_type == "LineString" and g.length > 1e-4:
                        v.pline(list(g.coords), "E-ACERO")
            continue
        crossed = False
        for i in range(len(pl) - 1):
            a, c = pl[i], pl[i + 1]
            da, dc = a[axis] - val, c[axis] - val
            seg = c - a
            L = np.linalg.norm(seg)
            if L < 1e-6:
                continue
            if (da <= 0 <= dc or dc <= 0 <= da) and abs(seg[axis]) / L > 0.7:
                s = da / (da - dc) if da != dc else 0
                P = a + s * seg
                pt = (P[other], P[2])
                if W.contains(Point(pt)):
                    dots.append((pt, max(r, dot_min_mm * v.m)))
                crossed = True
        if crossed:
            continue
        if np.ptp(pl[:, axis]) < 0.08 and abs(pl[:, axis].mean() - val) < par_tol:
            ls = LineString(pl[:, [other, 2]])
            q = ls.intersection(W)
            for g in (q.geoms if hasattr(q, "geoms") else [q]):
                if g.geom_type == "LineString" and g.length > 1e-4:
                    v.pline(list(g.coords), "E-ACERO")
    seen = []
    for pt, r in dots:
        if any(abs(pt[0] - s[0]) < 0.004 and abs(pt[1] - s[1]) < 0.004 for s in seen):
            continue
        seen.append(pt)
        v.circle(pt, r, "E-ACERO", fill=True)
    return dots


def bars_of(hosts):
    hs = set(hosts)
    return [b for b in bars if b["host"] in hs]


# ------------------------------------------------------------------ documento
doc = new_doc()
add_layers(doc)

# ============================================================ 1. PLANTA DE CIMENTACION 1:50
PL = View(doc, 50, (0, 0))
m = PL.m
U0, U1, V0, V1 = -0.15, 10.15, -0.15, 10.165           # caras extremas de columnas
ext_u = (-2.4, 12.4)
ext_v = (-2.2, 12.6)
# ejes
for k, u in GU.items():
    PL.line((u, -1.35), (u, 11.35), "E-EJES", linetype=PL.lt("EJE"))
    PL.grid_bubble((u, 11.35 + 5 * m), k)
    PL.grid_bubble((u, -1.35 - 5 * m), k)
for k, vv in GV.items():
    PL.line((-1.35, vv), (11.35, vv), "E-EJES", linetype=PL.lt("EJE"))
    PL.grid_bubble((-1.35 - 5 * m, vv), k)
    PL.grid_bubble((11.35 + 5 * m, vv), k)

# limite de propiedad
for seg in MS["property"]:
    PL.pline(seg, "E-LIMITE", linetype=PL.lt("LIMITE"))
ptxt = MS["property"][3]
pb = MS["property"][1]
ang = math.degrees(math.atan2(pb[0][1] - pb[1][1], pb[0][0] - pb[1][0]))
PL.text("LÍMITE DE PROPIEDAD (según modelo)", (2.6, pb[1][1] + (pb[0][1] - pb[1][1]) * 2.6 / (pb[0][0] - pb[1][0]) - 1.8 * m), 1.8, "E-TEXTO", "TOP_CENTER", rot=ang)

# zapatas, vigas de cimentacion, columnas
colpolys = [Polygon(c["poly"]) for c in cols]
colU = unary_union(colpolys)
for z in foot:
    PL.pline(z["poly"], "E-ZAPATA", close=True)
PL.pline(cim_esc["poly"], "E-ZAPATA", close=True)
for b in cim["beams"]:
    q = Polygon(b["poly"]).difference(colU)
    for g in ([q] if q.geom_type == "Polygon" else q.geoms):
        PL.pline(list(g.exterior.coords)[:-1], "E-VIGA", close=True)
for c in cols:
    PL.hatch(c["poly"], "E-COLUMNA-ACH")
    PL.pline(c["poly"], "E-COLUMNA", close=True)
# primer tramo de escalera (sobre el nivel) en linea oculta
st = [s for s in cim["stair"]][0]
PL.pline(st["poly"], "E-OCULTO", close=True, linetype=PL.lt("OCULTA"))
sp = np.array(st["poly"])
PL.line((sp[:, 0].min() + 0.1, (sp[:, 1].min() + sp[:, 1].max()) / 2), (sp[:, 0].min() + 1.3, (sp[:, 1].min() + sp[:, 1].max()) / 2), "E-TEXTO")
_ya = (sp[:, 1].min() + sp[:, 1].max()) / 2
PL.pline([(sp[:, 0].min() + 1.3 - 1.8 * m, _ya + 0.7 * m), (sp[:, 0].min() + 1.3, _ya), (sp[:, 0].min() + 1.3 - 1.8 * m, _ya - 0.7 * m)], "E-TEXTO", close=True)
PL.text("SUBE", (sp[:, 0].min() + 1.9, (sp[:, 1].min() + sp[:, 1].max()) / 2), 1.8)
PL.text("1er TRAMO ESCALERA (N1-N2)", ((sp[:, 0].min() + sp[:, 0].max()) / 2 + 0.3, sp[:, 1].max() - 2.2 * m), 1.6)

# rotulos de zapatas y columnas
for z in foot:
    c = col_on(z)
    zp = Polygon(z["poly"])
    free = zp.difference(Polygon(c["poly"]).buffer(0.06)) if c else zp
    # punto libre: centro del mayor rectangulo aproximado -> usa punto representativo alejado de la columna
    cu, cv = (z["u0"] + z["u1"]) / 2, (z["v0"] + z["v1"]) / 2
    if c:
        ccu, ccv = (c["u0"] + c["u1"]) / 2, (c["v0"] + c["v1"]) / 2
        du = (z["u1"] - z["u0"]) / 2 * 0.5
        dv = (z["v1"] - z["v0"]) / 2 * 0.5
        cu = cu + (du if ccu <= cu + 1e-3 else -du) * (1 if abs(ccu - cu) > 0.05 else 0)
        cv = cv + (dv if ccv <= cv + 1e-3 else -dv) * (1 if abs(ccv - cv) > 0.05 else 0)
        if abs(ccu - (z["u0"] + z["u1"]) / 2) < 0.05 and abs(ccv - (z["v0"] + z["v1"]) / 2) < 0.05:
            cv = z["v0"] + 0.30
    from shapely.ops import polylabel
    obst = unary_union([Polygon(c_["poly"]) for c_ in cols] + [Polygon(b_["poly"]) for b_ in cim["beams"]]).buffer(0.10)
    free = Polygon(z["poly"]).buffer(-0.08).difference(obst)
    if free.geom_type != "Polygon":
        free = max(free.geoms, key=lambda g: g.area)
    lp = polylabel(free, 0.01)
    cu, cv = lp.x, lp.y
    PL.text(z["T"], (cu, cv + 1.2 * m), 2.6, "E-TITULO")
    PL.text(f'{z["B"]:.2f}x{z["L"]:.2f}', (cu, cv - 1.6 * m), 1.6)
PL.text("CE", ((cim_esc["poly"][0][0] + cim_esc["poly"][2][0]) / 2, 0.95), 2.0, "E-TITULO")
for c in cols:
    cu, cv = (c["u0"] + c["u1"]) / 2, (c["v0"] + c["v1"]) / 2
    # rotulo en la esquina exterior superior derecha de la columna
    PL.text(c["CT"], (c["u1"] + 0.03, c["v1"] + 0.03), 1.7, "E-TEXTO", "BOTTOM_LEFT")

# rotulos de vigas de cimentacion (una vez por tramo, en el centro)
for b in cim["beams"]:
    p = np.array(b["poly"])
    cu, cv = p[:, 0].mean(), p[:, 1].mean()
    horiz = np.ptp(p[:, 0]) > np.ptp(p[:, 1])
    if horiz:
        PL.text("VC-1", (cu, p[:, 1].max() + 1.2 * m), 1.7, "E-TEXTO", "BOTTOM_CENTER")
    else:
        PL.text("VC-1", (p[:, 0].min() - 1.2 * m, cv), 1.7, "E-TEXTO", "BOTTOM_CENTER", rot=90)

# cotas generales (arriba e izquierda) y totales (abajo y derecha)
us = [U0] + sorted(GU.values()) + [U1]
PL.hdim_chain(us, V1, 10.75)
PL.dim((U0, V1), (U1, V1), (U0, 11.05), 0)
vs = [V0] + sorted(GV.values()) + [V1]
PL.vdim_chain(vs, U0, -1.05, texts=[(f"{b_-a_:.3f}" if abs(round((b_-a_)*100)-(b_-a_)*100)>0.01 else f"{b_-a_:.2f}") for a_, b_ in zip(vs, vs[1:])])
PL.dim((U0, V0), (U0, V1), (-1.35 + 0.0, V0), 90, dec=3)
# cotas de ubicacion de cada zapata respecto a su eje (ancho y largo)
for z in foot:
    ua = GU[z["gu"]]
    va = GV[z["gv"]]
    xs = sorted({round(z["u0"], 4), round(ua, 4), round(z["u1"], 4)})
    ys = sorted({round(z["v0"], 4), round(va, 4), round(z["v1"], 4)})
    ybase = z["v0"] - 3.5 * m
    PL.hdim_chain(xs, z["v0"], ybase)
    xbase = z["u1"] + 3.5 * m if z["gu"] in ("A-3",) else z["u0"] - 3.5 * m
    if z["gu"] == "A-1":
        xbase = z["u1"] + 3.5 * m
    PL.vdim_chain(ys, z["u1"] if xbase > z["u1"] else z["u0"], xbase)
# cimiento de escalera
ce = np.array(cim_esc["poly"])
PL.hdim_chain([ce[:, 0].min(), ce[:, 0].max()], ce[:, 1].max(), ce[:, 1].max() + 3.5 * m)
PL.vdim_chain([ce[:, 1].min(), ce[:, 1].max()], ce[:, 0].max(), ce[:, 0].max() + 3.5 * m)
PL.hdim_chain([GU["A-2"], ce[:, 0].min()], ce[:, 1].max(), ce[:, 1].max() + 3.5 * m)

# marcas de corte (ubicadas despues de elegir las zapatas representativas)
REP_PREF = {"Z-1": "N-4-A-2", "Z-2": "N-1-A-1", "Z-3": "N-2-A-3", "Z-4": "N-2-A-2"}
reps = {}
for T in sorted(set(TYPE.values())):
    cand = [z for z in foot if z["T"] == T]
    pref = [z for z in cand if mark_of(z) == REP_PREF.get(T)]
    reps[T] = (pref or cand)[0]
for i, T in enumerate(sorted(reps)):
    z = reps[T]
    va = GV[z["gv"]]
    section_mark(PL, (z["u0"] - 0.12, va), (z["u1"] + 0.12, va), str(i + 1), flip=True)
# corte de viga de cimentacion y del cimiento de escalera: se colocan mas abajo (necesitan la posicion)

# niveles en planta (texto)
PL.text("NFZ = -2.00 (todas las zapatas, ver cuadro)", (5.0, -2.05), 1.8, "E-TEXTO")

# ============================================================ 2. DETALLES DE ZAPATAS (planta 1:25 y corte 1:25)
DET = {}
for i, T in enumerate(sorted(reps)):
    z = reps[T]
    c = col_on(z)
    off = (100 + i * 12, 0)
    # ---------- planta de la zapata
    V = View(doc, 25, (off[0] - z["u0"], off[1] - z["v0"]))
    mm = V.m
    V.pline(z["poly"], "E-ZAPATA", close=True)
    V.hatch(c["poly"], "E-COLUMNA-ACH")
    V.pline(c["poly"], "E-COLUMNA", close=True)
    ua, va = GU[z["gu"]], GV[z["gv"]]
    V.line((ua, z["v0"] - 0.25), (ua, z["v1"] + 0.25), "E-EJES", linetype=V.lt("EJE"))
    V.line((z["u0"] - 0.25, va), (z["u1"] + 0.25, va), "E-EJES", linetype=V.lt("EJE"))
    V.grid_bubble((ua, z["v1"] + 0.25 + 4 * mm), z["gu"], 4)
    V.grid_bubble((z["u0"] - 0.25 - 4 * mm, va), z["gv"], 4)
    zb = bars_of([z["id"]])
    for b in zb:
        pl = bar_arr(b)
        V.pline([tuple(p[:2]) for p in pl], "E-ACERO")
    # arranques de columna (puntos) y sus patas
    cb = [b for b in bars if b["host"] == c["id"] and b["role"] == "LONG"]
    for b in cb:
        pl = bar_arr(b)
        top = pl[np.argmax(pl[:, 2])]
        r = {"1/2": 0.00635, "5/8": 0.00794}[b["d"]]
        V.circle((top[0], top[1]), max(r, 0.45 * mm), "E-ACERO", fill=True)
        V.pline([tuple(p[:2]) for p in pl if p[2] < -1.7], "E-ACERO")
    # cotas
    xs = sorted({round(z["u0"], 4), round(c["u0"], 4), round(c["u1"], 4), round(z["u1"], 4)})
    V.hdim_chain(xs, z["v0"], z["v0"] - 5 * mm)
    V.dim((z["u0"], z["v0"]), (z["u1"], z["v0"]), (z["u0"], z["v0"] - 10 * mm), 0)
    ys = sorted({round(z["v0"], 4), round(c["v0"], 4), round(c["v1"], 4), round(z["v1"], 4)})
    V.vdim_chain(ys, z["u1"], z["u1"] + 5 * mm)
    V.dim((z["u1"], z["v0"]), (z["u1"], z["v1"]), (z["u1"] + 10 * mm, z["v0"]), 90)
    # rotulos de parrilla
    px, py = z["par"]["X"], z["par"]["Y"]
    V.leader((z["u0"] + 0.22, px["pos"][0]), (z["u0"] + 0.05, z["v0"] - 0.40), par_txt(px) + "  (dir. X)", 1.8, side=1)
    V.leader((py["pos"][1], z["v1"] - 0.10), (z["u0"] + 0.05, z["v1"] + 0.13), par_txt(py) + "  (dir. Y)", 1.8, side=1)
    DET[T] = {"plan": (V, (z["u0"] - 0.55, z["v0"] - 0.55, z["u1"] + 0.5, z["v1"] + 0.45)), "z": z, "c": c}

    # ---------- corte i-i (plano v = eje N de la zapata), vista (u, z)
    S = View(doc, 25, (off[0] - z["u0"], 20 - 0.0))
    zc = (z["u0"] + z["u1"]) / 2
    win = (zc - 1.35, -2.08, zc + 1.35, 0.35)
    tags = [t for t, mm_ in meshes.items() if mm_["cat"] in ("zapata", "columna", "viga", "falsopiso")]
    for t in tags:
        mv = meshes[t]["v"]
        if mv[:, 1].min() - 1e-6 <= va <= mv[:, 1].max() + 1e-6 and mv[:, 0].max() > win[0] and mv[:, 0].min() < win[2] and mv[:, 2].min() < win[3] and mv[:, 2].max() > win[1]:
            draw_cut(S, cut_polys(t, 1, va), win)
    # acero: parrilla + arranques + estribos de columna + acero de vigas de cimentacion cortadas
    hosts = [z["id"], c["id"]] + [b["id"] for b in cim["beams"] if Polygon(b["poly"]).buffer(0.01).intersects(LineString([(win[0], va), (win[2], va)]))]
    draw_bars_section(S, bars_of(hosts), 1, va, win)
    S.line((ua, -2.3), (ua, 0.55), "E-EJES", linetype=S.lt("EJE"))
    S.grid_bubble((ua, 0.55 + 4 * S.m), z["gu"], 4)
    # cotas
    xs = sorted({round(z["u0"], 4), round(c["u0"], 4), round(c["u1"], 4), round(z["u1"], 4)})
    S.hdim_chain(xs, z["z0"], z["z0"] - 5 * S.m)
    S.dim((z["u0"], z["z0"]), (z["u1"], z["z0"]), (z["u0"], z["z0"] - 10 * S.m), 0)
    S.vdim_chain([z["z0"], z["z1"], 0.0], z["u1"], win[2] - 0.06)
    S.level(z["u0"] - 0.05, z["z0"], "NFZ -2.00", left=True)
    S.level(z["u0"] - 0.05, z["z1"], f"NSZ {z['z1']:.2f}", left=True)
    S.level(min(c["u0"], z["u0"]) - 0.05, 0.0, "NPT ±0.00", left=True)
    # rotulos de acero en el corte: del lado libre de la zapata
    o, oy = z["par"]["X"], z["par"]["Y"]
    fl, fr = c["u0"] - z["u0"], z["u1"] - c["u1"]
    right = fr >= fl
    free = max(fl, fr)
    l1 = f'{dstr(o["d"])} {sep_txt(o["s"])} (dir. X)'
    l2 = f'{dstr(oy["d"])} {sep_txt(oy["s"])} (dir. Y, puntos)'
    if free >= 0.6:
        xa = (c["u1"] + 0.25) if right else (c["u0"] - 0.25)
        tx_ = (c["u1"] + 0.06) if right else (c["u0"] - 0.06)
        S.leader((xa, o["z"]), (tx_, z["z1"] - 0.12), l1, 1.7, side=1 if right else -1)
        S.text(l2, (tx_ + (0.08 if right else -0.08) * 1, z["z1"] - 0.20), 1.5, "E-ACERO-TXT",
               "MIDDLE_LEFT" if right else "MIDDLE_RIGHT")
    else:
        xa = z["u1"] - 0.12
        S.leader((xa, o["z"]), (z["u1"] + 0.04, z["z1"] + 0.30), l1, 1.6, side=1)
        S.text(l2, (z["u1"] + 0.11, z["z1"] + 0.22), 1.4, "E-ACERO-TXT", "MIDDLE_LEFT")
    S.text("r = 0.075", ((z["u1"] - 0.22) if right else (z["u0"] + 0.22), z["z0"] + 0.035), 1.4, "E-ACERO-TXT")
    ctxt = "8Ø5/8\"+2Ø1/2\"" if c["CT"] == "C-1" else "14Ø5/8\""
    cm_ = ((c["u1"] - 0.05) if right else (c["u0"] + 0.05))
    S.leader((cm_, -0.62), ((c["u1"] + 0.12) if right else (c["u0"] - 0.12), -0.50), f"{c['CT']}: {ctxt}", 1.7,
             side=1 if right else -1)
    S.text("(ver E-03)", ((c["u1"] + 0.20) if right else (c["u0"] - 0.20), -0.58), 1.5, "E-ACERO-TXT",
           "MIDDLE_LEFT" if right else "MIDDLE_RIGHT")
    DET[T]["sec"] = (S, win)

# ============================================================ 3. SECCION DE VIGA DE CIMENTACION 1:10
beamN = [b for b in cim["beams"] if np.ptp(np.array(b["poly"])[:, 0]) > np.ptp(np.array(b["poly"])[:, 1])]
best = None
for b in beamN:
    p = np.array(b["poly"])
    for uc in np.arange(p[:, 0].min() + 0.35, p[:, 0].max() - 0.35, 0.05):
        if any(z["u0"] - 0.05 <= uc <= z["u1"] + 0.05 and z["v0"] <= p[:, 1].mean() <= z["v1"] for z in foot):
            continue
        n = 0
        for bb in bars_of([x["id"] for x in beamN]):
            if bb["role"] not in ("SUP", "INF"):
                continue
            pl = bar_arr(bb)
            if pl[:, 0].min() <= uc <= pl[:, 0].max() and abs(pl[:, 1].mean() - p[:, 1].mean()) < 0.2:
                n += 1
        if best is None or n < best[0] or (n == best[0] and abs(uc - p[:, 0].mean()) < abs(best[1] - p[:, 0].mean())):
            best = (n, float(uc), b)
nbar, ucut, vb = best
vbp = np.array(vb["poly"])
vc_v = vbp[:, 1].mean()
VS = View(doc, 10, (200, 0))
from details import beam_section
beam_section(VS, 0.25, 0.40, 4, 5, "3/4", "3/8", lab_side=1)
VS.level(-0.10, 0.40, "-1.05", left=True)
VS.level(-0.10, 0.0, "-1.45", left=True)
winb = (-0.20, -0.08, 0.55, 0.47)

# distribucion de estribos del tramo representativo (medida del modelo)
def stirrup_dist(beam):
    p = np.array(beam["poly"])
    horiz = np.ptp(p[:, 0]) > np.ptp(p[:, 1])
    ax = 0 if horiz else 1
    e = [b for b in bars if b["host"] == beam["id"] and b["role"] == "ESTRIBOS"]
    pos = sorted(bar_arr(b)[:, ax].mean() for b in e)
    # caras de apoyo: columnas que tocan la viga
    bp = Polygon(p).buffer(0.02)
    faces = []
    for c in cols:
        cp = Polygon(c["poly"])
        if cp.intersects(bp):
            cc = np.array(c["poly"])
            faces.append((cc[:, ax].min(), cc[:, ax].max()))
    faces.sort()
    f0 = faces[0][1]
    f1 = faces[-1][0]
    gaps = [pos[0] - f0] + [pos[i + 1] - pos[i] for i in range(len(pos) - 1)] + [f1 - pos[-1]]
    return pos, (f0, f1), gaps


pos, (f0, f1), gaps = stirrup_dist(vb)


def rle(vals):
    out = []
    for g in vals:
        g = round(g, 2)
        if out and abs(out[-1][1] - g) < 0.011:
            out[-1][0] += 1
        else:
            out.append([1, g])
    return out


runs = rle(gaps[1:])
mid = max(runs, key=lambda r: r[1])[1]
dense = rle(gaps[: len(gaps) // 2])
dense = [r for r in dense if r[1] < mid - 0.011]
dist_txt = ", ".join(f"{n}@{s:.2f}".replace("0.", ".") for n, s in dense) + f", rto. @{mid:.2f}".replace("0.", ".") + " c/ext."
VS_title_extra = f"Tramo {vb['com'].split('|')[2]}, corte a {ucut - f0:.2f} m de la cara"

# ============================================================ 4. CIMIENTO DE ESCALERA 1:25 (corte B-B)
ce_poly = np.array(cim_esc["poly"])
vcut = float((ce_poly[:, 1].min() + ce_poly[:, 1].max()) / 2 + 0.05)
CE = View(doc, 25, (300, 0))
winc = (ce_poly[:, 0].min() - 0.45, -1.10, ce_poly[:, 0].max() + 1.10, 0.90)
for t, mv_ in meshes.items():
    if mv_["cat"] not in ("zapata", "escalera", "peldanos", "falsopiso", "columna"):
        continue
    mv = mv_["v"]
    if mv[:, 1].min() - 1e-6 <= vcut <= mv[:, 1].max() + 1e-6 and mv[:, 0].max() > winc[0] and mv[:, 0].min() < winc[2] and mv[:, 2].min() < winc[3]:
        draw_cut(CE, cut_polys(t, 1, vcut), winc)
esc_bars = [b for b in MS["stair_bars"] if b["host"] == [t for t, x in meshes.items() if "N1-N2|LOSA_T1" in x["com"]][0]]
mechas = [b for b in bars if b["host"] == cim_esc["id"]]
z_n42 = [z for z in foot if mark_of(z) == "N-4-A-2"][0]
draw_bars_section(CE, esc_bars + mechas + bars_of([z_n42["id"]]), 1, vcut, winc, par_tol=0.12)
cu0, cu1 = ce_poly[:, 0].min(), ce_poly[:, 0].max()
CE.hdim_chain([cu0, cu1], -1.0, -1.0 - 5 * CE.m)
CE.vdim_chain([-1.0, 0.0], cu0, cu0 - 0.35)
CE.level(cu1 + 0.9, 0.0, "NPT ±0.00", left=False)
CE.level(cu0 - 0.1, -1.0, "-1.00", left=True)
mz = bar_arr(mechas[0])
CE.leader((mz[:, 0].mean(), -0.55), (cu1 + 0.25, -0.45), f'{len(mechas)} mechas {dstr(mechas[0]["d"])} L={mechas[0]["L"]:.2f}', 1.8, side=1)
CE.text("traslapan 0.45 con el acero sup. del tramo", (cu1 + 0.25, -0.58), 1.5, "E-ACERO-TXT", "MIDDLE_LEFT")
CE.leader((cu0 + 0.33, 0.25), (cu0 + 0.9, 0.62), f'malla {dstr("3/8")} @ .25 (ver E-09)', 1.8, side=1)
CE.text("CE", ((cu0 + cu1) / 2, -0.80), 2.2, "E-TITULO")

# marcas de corte en planta para VC y CE
section_mark(PL, (ucut, vbp[:, 1].min() - 0.45), (ucut, vbp[:, 1].max() + 0.45), "A")
section_mark(PL, (ce_poly[:, 0].min() - 0.3, vcut), (ce_poly[:, 0].max() + 0.3, vcut), "B", flip=True)


# ============================================================ 4b. ELEVACIONES DE VIGAS DE CIMENTACION 1:50
def vc_elevation(axis, val, offset, axis_tags):
    """Corte longitudinal por un eje de VC. axis=1: plano v=val (eje N); axis=0: plano u=val (eje A)."""
    other = 0 if axis == 1 else 1
    E = View(doc, 50, offset)
    lb = []
    for b in cim["beams"]:
        p = np.array(b["poly"])
        along = np.ptp(p[:, other]) > np.ptp(p[:, axis])
        if along and abs(p[:, axis].mean() - val) < 0.06:
            lb.append(b)
    lo = min(np.array(b["poly"])[:, other].min() for b in lb) - 0.60
    hi = max(np.array(b["poly"])[:, other].max() for b in lb) + 0.60
    win = (lo, -2.75, hi, -0.45)
    for t, mv_ in meshes.items():
        if mv_["cat"] not in ("zapata", "columna", "viga"):
            continue
        mv = mv_["v"]
        if mv[:, 2].min() > -0.5:
            continue
        if mv[:, axis].min() - 1e-6 <= val <= mv[:, axis].max() + 1e-6:
            draw_cut(E, cut_polys(t, axis, val), win)
    bl = bars_of([b["id"] for b in lb])
    draw_bars_section(E, bl, axis, val, win, par_tol=0.2)
    # ejes
    for tag in axis_tags:
        pos = GU[tag] if tag.startswith("A") else GV[tag]
        E.line((pos, -2.45), (pos, -0.45), "E-EJES", linetype=E.lt("EJE"))
        E.grid_bubble((pos, -2.45 - 4 * E.m), tag, 4)
    # caras de columnas sobre el eje
    line = LineString([(lo, val), (hi, val)]) if axis == 1 else LineString([(val, lo), (val, hi)])
    faces = []
    for c in cols:
        cp = Polygon(c["poly"])
        if cp.intersects(line):
            q = cp.intersection(line)
            cc = np.array(q.coords)[:, other]
            faces.append((cc.min(), cc.max()))
    faces.sort()
    # luces libres (abajo)
    xs = [faces[0][0]] + [x for f_ in faces for x in f_][1:-1] + [faces[-1][1]]
    E.hdim_chain(xs, -2.0, -2.0 - 5 * E.m)
    # zonas de confinamiento de estribos (arriba)
    ztop = -1.05
    for b in lb:
        pos = sorted(bar_arr(x)[:, other].mean() for x in bars if x["host"] == b["id"] and x["role"] == "ESTRIBOS")
        if not pos:
            continue
        f0 = max([f_[1] for f_ in faces if f_[1] <= pos[0] + 0.01], default=pos[0])
        f1 = min([f_[0] for f_ in faces if f_[0] >= pos[-1] - 0.01], default=pos[-1])
        g = np.diff(pos)
        mid = max(round(x, 2) for x in g)
        # ultimo estribo de la zona densa en cada extremo
        i0 = next((i for i, x in enumerate(g) if x > mid - 0.011), 0)
        i1 = len(g) - 1 - next((i for i, x in enumerate(g[::-1]) if x > mid - 0.011), 0)
        a, bnd = pos[i0], pos[i1 + 1]
        E.hdim_chain([f0, a, bnd, f1], ztop, ztop + 6 * E.m,
                     texts=[f"{a - f0:.2f}", f"@{mid:.2f}".replace("0.", "."), f"{f1 - bnd:.2f}"])
    # traslapes medidos de las barras
    grp = collections.defaultdict(dict)
    for x in bl:
        if x["role"] in ("SUP", "INF") and len(x["rest"]) >= 3 and x["rest"][2].startswith("PZA"):
            pl = bar_arr(x)
            grp[(x["role"], x["rest"][1])][x["rest"][2]] = (pl[:, other].min(), pl[:, other].max(), pl[:, 2])
    seen = set()
    for (role, bi), d in grp.items():
        if "PZA_A" in d and "PZA_B" in d:
            a0, a1, za = d["PZA_A"]
            b0, b1, zb = d["PZA_B"]
            o0, o1 = max(a0, b0), min(a1, b1)
            key = (role, round(o0, 2), round(o1, 2))
            if o1 - o0 < 0.1 or key in seen:
                continue
            seen.add(key)
            if role == "SUP":
                E.dim((o0, -1.10), (o1, -1.10), (o0, -1.05 + 2.5 * E.m), 0, text=f"trasl. {o1 - o0:.2f}")
            else:
                E.dim((o0, -1.40), (o1, -1.40), (o0, -1.45 - 3.0 * E.m), 0, text=f"trasl. {o1 - o0:.2f}")
    E.level(lo + 0.58, -1.05, "-1.05", left=True)
    E.level(lo + 0.58, -1.45, "-1.45", left=True)
    E.level(lo + 0.58, -2.00, "NFZ -2.00", left=True)
    ns = sum(1 for x in bl if x["role"] == "SUP" and "PZA_B" not in x["rest"])
    return E, win, lb


EN, winN, lbN = vc_elevation(1, GV["N-1"], (400, 0), ["A-1", "A-4", "A-2", "A-3"])
EA, winA, lbA = vc_elevation(0, GU["A-1"], (400, 20), ["N-3", "N-2", "N-1"])

# ============================================================ 5. HOJA A1
W_, H_ = 841, 594
ps = doc.layouts.new("E-01")
ps.page_setup(size=(W_, H_), margins=(0, 0, 0, 0), units="mm")
mv = ps.main_viewport()
if mv is not None:
    mv.dxf.center = (W_ / 2, H_ / 2, 0)
    mv.dxf.width = W_
    mv.dxf.height = H_
    mv.dxf.view_center_point = (W_ / 2, H_ / 2)
    mv.dxf.view_height = H_
frame_and_title(ps, W_, H_)

# planta
pw, ph = 300, 300
pcx, pcy = 25 + 8 + pw / 2, H_ - 14 - ph / 2
add_vp(ps, pcx, pcy, pw, ph, ((ext_u[0] + ext_u[1]) / 2, (ext_v[0] + ext_v[1]) / 2), 50)
view_title(ps, pcx, pcy - ph / 2 - 8, "PLANTA DE CIMENTACIÓN", "ESC. 1:50")

# detalles de zapatas: 4 columnas a la derecha
x0 = 355
colw = 118
for i, T in enumerate(sorted(DET)):
    d = DET[T]
    V, (a0, b0, a1, b1) = d["plan"]
    z = d["z"]
    cx = x0 + colw * i + colw / 2
    w = (a1 - a0) * 1000 / 25 + 4
    h = (b1 - b0) * 1000 / 25 + 4
    top = H_ - 22
    cy = top - h / 2
    add_vp(ps, cx, cy, w, h, V.P((a0 + a1) / 2, (b0 + b1) / 2), 25)
    view_title(ps, cx, top - h - 7, f"ZAPATA {T} - PLANTA", f"ESC. 1:25  (típica: {mark_of(z)})")
    S, win = d["sec"]
    ws = (win[2] - win[0]) * 1000 / 25
    hs = (win[3] - win[1] + 0.25) * 1000 / 25 + 22
    cys = top - h - 22 - hs / 2
    add_vp(ps, cx, cys, ws, hs, S.P((win[0] + win[2]) / 2, (win[1] + win[3]) / 2 + 0.02), 25)
    view_title(ps, cx, cys - hs / 2 - 6, f"CORTE {i + 1}-{i + 1}  ({T})", "ESC. 1:25")

# seccion VC 1:10
bx, by = 385, 215
wv, hv = 100, 78
add_vp(ps, bx, by, wv, hv, VS.P((winb[0] + winb[2]) / 2 + 0.07, (winb[1] + winb[3]) / 2 - 0.01), 10)
view_title(ps, bx, by - hv / 2 - 6, "CORTE A-A  VIGA DE CIMENTACIÓN VC-1", "ESC. 1:10")
ptext(ps, f'VC-1  0.25 x 0.40', (bx - wv / 2 + 2, by - hv / 2 - 19), 2.4, "E-TITULO")
ptext(ps, f'Estribos {dstr("3/8")}: {dist_txt}', (bx - wv / 2 + 2, by - hv / 2 - 24), 2.1)
ptext(ps, "Sección de diseño (E.060). En los nudos, las barras de los", (bx - wv / 2 + 2, by - hv / 2 - 28.5), 1.7)
ptext(ps, "ejes A pasan por dentro de las de los ejes N.", (bx - wv / 2 + 2, by - hv / 2 - 32), 1.7)

# cimiento escalera
cx2, cy2 = 522, 206
wc = (winc[2] - winc[0]) * 40 + 40
hc = (winc[3] - winc[1]) * 40 + 16
add_vp(ps, cx2, cy2, wc, hc, CE.P((winc[0] + winc[2]) / 2 + 0.4, (winc[1] + winc[3]) / 2), 25)
view_title(ps, cx2, cy2 - hc / 2 - 6, "CORTE B-B  CIMIENTO DE ESCALERA (CE)", "ESC. 1:25")


# elevaciones de VC
for (E, win_, ttl, cyy) in ((EN, winN, "ELEVACIÓN VC-1  EJE N-1  (típica ejes N-1, N-2, N-3)", 118),
                            (EA, winA, "ELEVACIÓN VC-1  EJE A-1  (típica ejes A)", 52)):
    we = (win_[2] - win_[0]) * 20
    he = (win_[3] - win_[1]) * 20 + 2
    add_vp(ps, 480, cyy, we, he, E.P((win_[0] + win_[2]) / 2, (win_[1] + win_[3]) / 2), 50)
    view_title(ps, 480, cyy - he / 2 - 9, ttl, "ESC. 1:50  (cotas de estribos: zona de confinamiento desde la cara / separación central)", w=150)

# ------------------------------------------------------------ cuadro de zapatas
rows = [["TIPO", "CANT.", "B x L (m)", "h (m)", "NFZ", "PARRILLA DIR. X", "PARRILLA DIR. Y", "UBICACIÓN (ejes)"]]
for T in sorted(set(TYPE.values())):
    zz = [z for z in foot if z["T"] == T]
    z = zz[0]
    def rng(key):
        ss = [q["par"][key]["s"] for q in zz]
        o = z["par"][key]
        a, b = round(min(ss), 2), round(max(ss), 2)
        sp = f"@ {a:.2f}".replace("0.", ".") if a == b else f"@ {a:.2f}-{b:.2f}".replace("0.", ".")
        return [f'{o["n"]} {dstr(o["d"])} {sp}']
    tx = rng("X")
    ty = rng("Y")
    locs = ", ".join(sorted(mark_of(q).replace("-A-", "/A-") for q in zz))
    rows.append([T, str(len(zz)), f'{z["B"]:.2f} x {z["L"]:.2f}', f'{z["h"]:.2f}', f'{z["z0"]:.2f}',
                 " / ".join(tx), " / ".join(ty), locs])
rows.append(["CE", "1", "0.50 x 1.25", "1.00", "-1.00", f'{len(mechas)} mechas {dstr("3/8")}', "—", "arranque escalera"])
tx0, ty0 = 30, 250
Wt, Ht = table(ps, tx0, ty0, [12, 11, 22, 11, 13, 40, 40, 147], rows, row_h=6.2, h_txt=2.1,
               aligns=["C", "C", "C", "C", "C", "C", "C", "L"])
ptext(ps, "CUADRO DE ZAPATAS", (tx0, ty0 + 2), 3.2, "E-TITULO")
ptext(ps, "Dir. X: paralela a los ejes N (N-1 ... N-4).  Dir. Y: paralela a los ejes A.  Separación medida del modelo (m).",
      (tx0, ty0 - Ht - 4), 1.9)

# ------------------------------------------------------------ resumen de materiales (del modelo)
conc_z = sum(z["B"] * z["L"] * z["h"] for z in foot)
conc_ce = 0.50 * 1.25 * 1.00
conc_vc = sum(meshes[b["id"]]["v"].shape[0] and 0 or 0 for b in cim["beams"])
conc_vc = sum(b["b"] * b["h"] * b["Lc"] for b in cim["beams"])
acero = collections.defaultdict(float)
for b in bars:
    if b["grp"] in ("SJ_ACERO_ZAPATAS_R1",) or b["host"] == cim_esc["id"] or (b["grp"] == "SJ_ACERO_VIGAS_R1" and b["host"] in {x["id"] for x in cim["beams"]}):
        acero[("ZAP" if b["grp"] == "SJ_ACERO_ZAPATAS_R1" and b["host"] != cim_esc["id"] else ("CE" if b["host"] == cim_esc["id"] else "VC"), b["d"])] += b["L"] * KG[b["d"]]
mr = [["ELEMENTO", "CONCRETO (m³)", "ACERO (kg)", "DETALLE ACERO"]]
def acs(key):
    items = sorted([(d, w) for (k, d), w in acero.items() if k == key], key=lambda x: x[0])
    return sum(w for _, w in items), ", ".join(f'{dstr(d)}: {w:.1f}' for d, w in items)
wz, dz = acs("ZAP")
wv_, dv = acs("VC")
wc_, dc = acs("CE")
mr.append(["Zapatas (14)", f"{conc_z:.2f}", f"{wz:.1f}", dz])
mr.append(["Vigas de cimentación (17)", f"{conc_vc:.2f}", f"{wv_:.1f}", dv])
mr.append(["Cimiento de escalera", f"{conc_ce:.2f}", f"{wc_:.1f}", dc])
mr.append(["TOTAL", f"{conc_z + conc_vc + conc_ce:.2f}", f"{wz + wv_ + wc_:.1f}", "arranques de columna: ver E-03"])
my0 = ty0 - Ht - 16
Wm, Hm = table(ps, tx0, my0, [46, 28, 22, 110], mr, row_h=6.0, h_txt=2.1, aligns=["L", "C", "C", "L"])
ptext(ps, "RESUMEN DE MATERIALES DE CIMENTACIÓN (calculado del modelo)", (tx0, my0 + 2), 3.0, "E-TITULO")

# ------------------------------------------------------------ notas
notas = [
    "ESPECIFICACIONES TÉCNICAS - CIMENTACIÓN",
    "1. CONCRETO f'c = ____ kg/cm² en zapatas, vigas de cimentación y cimiento de escalera (COMPLETAR según memoria).",
    "2. ACERO corrugado ASTM A615 Grado 60, fy = 4200 kg/cm².",
    "3. RECUBRIMIENTOS: zapatas 7.5 cm (contra terreno); vigas de cimentación 4 cm; columnas ver E-03.",
    "4. SUELO (EMS): qadm = 1.22 - 1.31 kg/cm² a Df = 2.00 m. NFZ = -2.00 m. El cimiento de escalera se funda a -1.00 m:",
    "    confirmar la capacidad portante a esa profundidad antes de vaciar.",
    "5. Parrilla de zapatas en dos capas, gancho a 90° hacia arriba en ambos extremos. Arranques de columna con pata",
    "    de 12 db apoyada sobre la parrilla, hacia el interior de la zapata.",
    "6. Vigas de cimentación: barras corridas por eje, gancho estándar en columnas extremas. Traslapes fuera de nudos:",
    "    superiores 1.15 m al centro del vano, inferiores 0.90 m a 2h de la cara de columna, alternados.",
    "7. Cotas y niveles en metros. NPT ±0.00 = Nivel 1. Ejes según modelo (orden A-1, A-4, A-2, A-3).",
    "8. Plano generado del modelo IFC 'Proyect sj.ifc' (Revit 2027). Dimensiones y acero tal como están modelados.",
]
ny = my0 - Hm - 10
for i, s in enumerate(notas):
    ptext(ps, s, (tx0, ny - i * 4.3), 2.4 if i == 0 else 2.05, "E-TITULO" if i == 0 else "E-TEXTO")

# ------------------------------------------------------------ leyenda
lx, ly = 600, 245
ptext(ps, "LEYENDA", (lx, ly), 3.0, "E-TITULO")
leg = [("E-COLUMNA-ACH", "Columna (C-1 rectangular 0.30x0.60 / C-2 en L 0.60x0.60x0.30)"),
       ("E-ZAPATA", "Zapata aislada (Z-#) / cimiento de escalera (CE)"),
       ("E-VIGA", "Viga de cimentación VC-1 0.25x0.40 (fondo -1.45, tope -1.05)"),
       ("E-LIMITE", "Límite de propiedad (según modelo)"),
       ("E-ACERO", "Acero de refuerzo")]
for i, (ly_, s) in enumerate(leg):
    yy = ly - 7 - i * 6
    if ly_ == "E-COLUMNA-ACH":
        h = ps.add_hatch(color=252, dxfattribs={"layer": ly_})
        h.paths.add_polyline_path([(lx, yy - 1.5), (lx + 8, yy - 1.5), (lx + 8, yy + 1.5), (lx, yy + 1.5)], is_closed=True)
        ps.add_lwpolyline([(lx, yy - 1.5), (lx + 8, yy - 1.5), (lx + 8, yy + 1.5), (lx, yy + 1.5)], close=True, dxfattribs={"layer": "E-COLUMNA"})
    elif ly_ == "E-LIMITE":
        ps.add_line((lx, yy), (lx + 8, yy), dxfattribs={"layer": ly_, "linetype": "DASHDOT", "ltscale": 0.2})
    else:
        ps.add_lwpolyline([(lx, yy - 1.5), (lx + 8, yy - 1.5), (lx + 8, yy + 1.5), (lx, yy + 1.5)], close=True, dxfattribs={"layer": ly_})
    ptext(ps, s, (lx + 11, yy), 2.0, "E-TEXTO", "MIDDLE_LEFT")

# ------------------------------------------------------------ membrete
mx0, my0_, mw, mh = W_ - 10 - 200, 10, 200, 62
ps.add_lwpolyline([(mx0, my0_), (mx0 + mw, my0_), (mx0 + mw, my0_ + mh), (mx0, my0_ + mh)], close=True, dxfattribs={"layer": "E-MARCO", "lineweight": 50})
for yy in (my0_ + 44, my0_ + 30, my0_ + 18):
    ps.add_line((mx0, yy), (mx0 + mw, yy), dxfattribs={"layer": "E-MARCO", "lineweight": 25})
ps.add_line((mx0 + 150, my0_), (mx0 + 150, my0_ + 30), dxfattribs={"layer": "E-MARCO", "lineweight": 25})
ps.add_line((mx0 + 75, my0_), (mx0 + 75, my0_ + 18), dxfattribs={"layer": "E-MARCO", "lineweight": 25})
ptext(ps, "PROYECTO:", (mx0 + 2, my0_ + 58), 1.8)
ptext(ps, "CASA SAN JERÓNIMO - REDISEÑO ESTRUCTURAL 4 x 3", (mx0 + 2, my0_ + 51), 3.6, "E-TITULO")
ptext(ps, "5 niveles (Cimentación -2.00, N1 ±0.00 ... N5 +11.00)", (mx0 + 2, my0_ + 46), 2.0)
ptext(ps, "ESPECIALIDAD: ESTRUCTURAS", (mx0 + 2, my0_ + 39.5), 2.2)
ptext(ps, "CIMENTACIÓN: PLANTA, DETALLES DE ZAPATAS,", (mx0 + 2, my0_ + 35), 2.6, "E-TITULO")
ptext(ps, "VIGA DE CIMENTACIÓN Y CUADRO DE ZAPATAS", (mx0 + 2, my0_ + 31.5), 2.6, "E-TITULO")
ptext(ps, "LÁMINA", (mx0 + 175, my0_ + 26), 2.0, "E-TEXTO", "BOTTOM_CENTER")
ptext(ps, "E-01", (mx0 + 175, my0_ + 10), 11, "E-TITULO", "BOTTOM_CENTER")
ptext(ps, "ESCALA: INDICADA", (mx0 + 2, my0_ + 24), 2.0)
ptext(ps, "FECHA: SET. 2026", (mx0 + 2, my0_ + 20), 2.0)
ptext(ps, "FUENTE: modelo IFC 'Proyect sj.ifc'", (mx0 + 77, my0_ + 24), 2.0)
ptext(ps, "(Revit 2027, IFC4, 26-09-2026)", (mx0 + 77, my0_ + 20), 2.0)
ptext(ps, "PROFESIONAL RESPONSABLE:", (mx0 + 2, my0_ + 13), 1.8)
ptext(ps, "_______________________  CIP ______", (mx0 + 2, my0_ + 4), 2.0)
ptext(ps, "REVISÓ:", (mx0 + 77, my0_ + 13), 1.8)
ptext(ps, "_______________________", (mx0 + 77, my0_ + 4), 2.0)

doc.set_modelspace_vport(height=20, center=(5, 5))
doc.saveas("E-01_Cimentacion.dxf")
print("DXF ok")
for e in doc.modelspace():
    if e.dxf.hasattr("linetype") and e.dxf.linetype.upper() not in ("BYLAYER", "CONTINUOUS", "BYBLOCK"):
        e.dxf.ltscale = e.dxf.get("ltscale", 1.0) * 1000.0

# ------------------------------------------------------------ PDF
from ezdxf.addons.drawing import Frontend, RenderContext, pymupdf, layout, config
ctx = RenderContext(doc)
be = pymupdf.PyMuPdfBackend()
cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                           color_policy=config.ColorPolicy.COLOR,
                           lineweight_policy=config.LineweightPolicy.ABSOLUTE,
                           lineweight_scaling=1.0,
                           min_lineweight=0.09,
                           hatch_policy=config.HatchPolicy.NORMAL,
                           line_policy=config.LinePolicy.ACCURATE)


def not_vport(e):
    return e.dxf.layer != "E-VPORT" or e.dxftype() == "VIEWPORT"


Frontend(ctx, be, config=cfg).draw_layout(ps, filter_func=not_vport)
page = layout.Page(W_, H_, layout.Units.mm, margins=layout.Margins.all(0))
st_ = layout.Settings(fit_page=True)
open("E-01_Cimentacion.pdf", "wb").write(be.get_pdf_bytes(page, settings=st_))
open("E-01_preview.png", "wb").write(be.get_pixmap_bytes(page, fmt="png", dpi=110, settings=st_))
print("PDF ok", nbar, ucut, dist_txt)
