"""Laminas E-04 ... E-07 - LOSAS ALIGERADAS (Nivel 2 ... Nivel 5), generadas del modelo IFC.
Un solo script parametrizado por nivel. Todo (geometria, acero, longitudes, cantidades) se mide del modelo
(model_all.pkl); los casetones NO estan modelados (la losa es un piso macizo de 0.20) y se dibujan segun la
regla del nodo Dynamo 14 (viguetas 0.10 @ 0.40, casetones 0.30 x 0.15, losita 0.05), indicados como tales.
Uso:  python3 gen_losas.py            (las 4 laminas)
      python3 gen_losas.py "Nivel 3"  (una sola)
"""
import sys, re, math, collections
import numpy as np
from shapely.geometry import Polygon, LineString, box, Point, MultiPolygon
from shapely.ops import unary_union
from sheetcommon import *
from sheetlib import View, section_mark, ptext, view_title, add_vp, table
from losas_render import save_and_render_lt

M = load_model()
E = M["elements"]
GU, GV = M["GU"], M["GV"]
GRP = "SJ_ACERO_LOSAS_R1"
SHEETS = [("Nivel 2", "E-04", "E-04_Losa_Nivel2"), ("Nivel 3", "E-05", "E-05_Losa_Nivel3"),
          ("Nivel 4", "E-06", "E-06_Losa_Nivel4"), ("Nivel 5", "E-07", "E-07_Losa_Nivel5")]
CAS_H = 0.15          # altura de casetón (regla del nodo 14, no modelado)
LOSITA = 0.05
RIB = 0.10


def P(b):
    return np.asarray(b["pl"], float)


def base(role):
    return re.sub(r"\d+$", "", role)


def idx(role):
    m = re.search(r"(\d+)$", role)
    return int(m.group(1)) if m else 0


def geo(b):
    """direccion (0=u/X, 1=v/Y), coordenada fija media, extremos a lo largo."""
    pl = P(b)
    ax = 0 if np.ptp(pl[:, 0]) > np.ptp(pl[:, 1]) else 1
    return ax, float(pl[:, 1 - ax].mean()), float(pl[:, ax].min()), float(pl[:, ax].max())


def f2(x):
    return f"{x:.2f}"


def sp(x):
    return f"@ {x:.2f}".replace("0.", ".")


def dtxt(d):
    return f'Ø{d}"'


# ------------------------------------------------------------------ marcas del cuadro de acero
def mark(b):
    r, d = base(b["role"]), b["d"]
    if r == "VIG_INF":
        return "V1"
    if r == "VIG_BAS12_":
        return "B1"
    if r == "VIG_BAS38_":
        return "B2"
    if r == "VIG_VOL":
        return "B3"
    if r == "LAT_SUPL":
        return "L1" if d == "1/2" else "L2"
    if r == "LAT_SUPR":
        return "L3"
    if r == "LAT_INFL":
        return "L4"
    if r == "LAT_INFR":
        return "L5"
    if r.startswith("CHATA_SUP"):
        return "C1"
    if r.startswith("CHATA_INF"):
        return "C2"
    if r.startswith("CHATA_EST"):
        return "C3"
    if r == "TEMP_V":
        return "T1"
    if r == "TEMP_U":
        return "T2"
    return "?"


DESC = {
    "V1": "Vigueta dir. X: inferior corrido (trasl. 0.60 sobre viga interior)",
    "B1": "Vigueta dir. X: bastón superior sobre apoyos interiores A-4 / A-2",
    "B2": "Vigueta dir. X: bastón superior apoyo extremo A-3 (gancho)",
    "B3": "Vigueta dir. X: superior del volado eje A-1 (gancho en borde)",
    "L1": "Vigueta dir. Y volado N-4: superior, borde a VCH (ganchos)",
    "L2": "Vigueta dir. Y lado escalera: superior, borde a VCH",
    "L3": "Vigueta dir. Y borde N-1: superior, viga N-1 a VCH (ganchos)",
    "L4": "Vigueta dir. Y (lado N-4 / N-3): inferior constructivo",
    "L5": "Vigueta dir. Y (lado N-1): inferior constructivo",
    "C1": "Viga chata VCH 0.30x0.20: superior 2 barras corridas",
    "C2": "Viga chata VCH 0.30x0.20: inferior 2 barras corridas",
    "C3": "Viga chata VCH: estribos 0.25 x 0.12 @ .20",
    "T1": "Malla de temperatura en losita, dir. X",
    "T2": "Malla de temperatura en losita, dir. Y",
}
ORDER = ["V1", "B1", "B2", "B3", "L1", "L2", "L3", "L4", "L5", "C1", "C2", "C3", "T1", "T2"]


def steel_table(LB):
    g = collections.OrderedDict()
    for b in LB:
        g.setdefault((mark(b), b["d"]), []).append(b)
    rows, tot = [], collections.defaultdict(float)
    for mk in ORDER:
        for (m_, d), bl in g.items():
            if m_ != mk:
                continue
            Ls = [b["L"] for b in bl]
            lt = sum(Ls)
            kg = lt * KG[d]
            tot[d] += kg
            lo, hi = min(Ls), max(Ls)
            lu = f2(lo) if hi - lo < 0.006 else f"{lo:.2f} - {hi:.2f}"
            rows.append([mk, DESC[mk], dtxt(d), str(len(bl)), lu, f"{lt:.2f}", f"{kg:.1f}"])
    return rows, tot


# ------------------------------------------------------------------ dibujo auxiliar
def plan_bar(V, b, tick_mm=1.3, layer="E-ACERO"):
    """barra en planta; los ganchos verticales se indican con un trazo corto perpendicular."""
    pl = P(b)
    zmed = np.median(pl[:, 2])
    xy = [tuple(pl[0, :2])]
    for p in pl[1:]:
        if np.hypot(p[0] - xy[-1][0], p[1] - xy[-1][1]) > 0.004:
            xy.append((p[0], p[1]))
    if len(xy) < 2:
        return
    V.pline(xy, layer)
    for end, nxt, zz in ((xy[0], xy[1], pl[0, 2]), (xy[-1], xy[-2], pl[-1, 2])):
        if abs(zz - zmed) > 0.05:
            d = np.array(end) - np.array(nxt)
            d /= np.linalg.norm(d)
            n = np.array([-d[1], d[0]]) * tick_mm * V.m
            V.line(tuple(np.array(end) - n), tuple(np.array(end) + n), layer)


def double_arrow(V, a, b, layer="E-TEXTO"):
    a, b = np.array(a, float), np.array(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]])
    m = V.m
    V.line(tuple(a), tuple(b), layer)
    for p, s in ((a, 1), (b, -1)):
        V.hatch([tuple(p), tuple(p + s * d * 2.2 * m + n * 0.7 * m), tuple(p + s * d * 2.2 * m - n * 0.7 * m)], layer, color=7)


def alig_symbol(V, c, along_u, L=1.2, txt="ALIG. h=0.20"):
    """simbolo de aligerado: flecha doble en la direccion de las viguetas + texto."""
    cu, cv = c
    if along_u:
        double_arrow(V, (cu - L / 2, cv), (cu + L / 2, cv))
        V.text(txt, (cu, cv + 0.8 * V.m), 1.5, "E-TEXTO", "BOTTOM_CENTER")
    else:
        double_arrow(V, (cu, cv - L / 2), (cu, cv + L / 2))
        V.text(txt, (cu - 0.8 * V.m, cv), 1.5, "E-TEXTO", "BOTTOM_CENTER", rot=90)


def alig_section(V, win, zb, zt, solids, beam_polys=(), ext=None):
    """Corte idealizado de aligerado (s, z): losita + nervios/zonas macizas + casetones (no modelados).
    solids: intervalos (a, b) macizos en todo el espesor; beam_polys: cortes reales de vigas bajo la losa."""
    s0, _, s1, _ = win
    e0, e1 = ext if ext else (s0 - 1, s1 + 1)
    geo_ = [box(e0, zt - LOSITA, e1, zt)]
    for a, b in solids:
        geo_.append(box(a, zb, b, zt))
    conc = unary_union(geo_ + list(beam_polys)).intersection(box(s0 - 1, zb - 2, s1 + 1, zt))
    polys = [conc] if conc.geom_type == "Polygon" else list(conc.geoms)
    draw_cut(V, polys, win)
    # casetones = huecos bajo la losita
    free = box(max(s0, e0), zb, min(s1, e1), zb + CAS_H).difference(unary_union([box(a, zb, b, zt) for a, b in solids] + [box(-99, -99, -98, -98)]))
    cas = []
    for g in ([free] if free.geom_type == "Polygon" else list(free.geoms)):
        if g.area < 1e-5:
            continue
        a, _, b, _ = g.bounds
        cas.append((a, b))
        ring = [(a, zb), (b, zb), (b, zb + CAS_H), (a, zb + CAS_H)]
        edge_l, edge_r = a <= s0 + 1e-6, b >= s1 - 1e-6
        V.line((a, zb + CAS_H), (b, zb + CAS_H), "E-PROYECCION")
        if not edge_l:
            V.line((a, zb), (a, zb + CAS_H), "E-PROYECCION")
        if not edge_r:
            V.line((b, zb), (b, zb + CAS_H), "E-PROYECCION")
        # achurado de casetón: diagonales finas
        n = max(1, int(round((b - a) / 0.15)))
        w = (b - a) / n
        for i in range(n):
            x0 = a + i * w
            V.line((x0, zb), (x0 + w, zb + CAS_H), "E-PROYECCION")
            V.line((x0, zb + CAS_H), (x0 + w, zb), "E-PROYECCION")
        V.line((a, zb), (b, zb), "E-PROYECCION", linetype=V.lt("OCULTA"))
    return cas


def union_cut(els, axis, val, win):
    polys = []
    for el in els:
        bb0, bb1 = el["bbox"]
        if not (bb0[axis] - 1e-6 <= val <= bb1[axis] + 1e-6):
            continue
        polys += cut_polys(el, axis, val)
    if not polys:
        return []
    u = unary_union([p.buffer(0.0005) for p in polys]).buffer(-0.0005)
    return [u] if u.geom_type == "Polygon" else list(u.geoms)


# ================================================================== una lamina
def build(level, code, basename):
    slab_tag = [t for t, e in E.items() if e["cat"] == "losa" and e["level"] == level][0]
    SL = E[slab_tag]
    zb, zt = float(SL["bbox"][0][2]), float(SL["bbox"][1][2])
    H = zt - zb
    fp = footprint(SL)
    umin, vmin, umax, vmax = fp.bounds
    LB = [b for b in M["bars"] if b["grp"] == GRP and b["host"] == slab_tag]
    byb = collections.defaultdict(list)
    for b in LB:
        byb[base(b["role"])].append(b)
    beams = {t: e for t, e in E.items() if e["cat"] == "viga" and e["level"] == level}
    cols = {t: e for t, e in E.items() if e["cat"] == "columna" and e["bbox"][0][2] < zt - 0.3 <= e["bbox"][1][2]}
    colfp = {t: footprint(e) for t, e in cols.items()}
    colU = unary_union(list(colfp.values()))
    beamfp = {t: footprint(e) for t, e in beams.items()}
    beamU = unary_union(list(beamfp.values()))
    bbars = [b for b in M["bars"] if b["host"] in beams]
    npt = f"+{zt:.2f}"

    # ---------------- datos medidos
    # viguetas dir. X (centros = bastones), por indice
    vigX = {}
    for b in byb["VIG_BAS12_"]:
        vigX[idx(b["role"])] = round(geo(b)[1], 3)
    vigX = dict(sorted(vigX.items()))
    stripA = [k for k, v in vigX.items() if v < GV["N-2"]]
    stripB = [k for k, v in vigX.items() if v > GV["N-2"]]
    # viguetas dir. Y (centros de nervio segun la regla del nodo: u = umax - 0.20 - 0.40 (k-1))
    ribY = {}
    for side in ("L", "R"):
        ks = sorted({idx(b["role"]) for b in byb["LAT_INF" + side]})
        ribY[side] = {k: round(umax - 0.20 - 0.40 * (k - 1), 3) for k in ks}
    # vigas chatas: limites de estribos +/- 0.025
    VCH = {}
    for side in ("L", "R"):
        es = byb["CHATA_EST" + side]
        pts = np.vstack([P(b) for b in es])
        VCH[side] = dict(v0=float(pts[:, 1].min() - 0.025), v1=float(pts[:, 1].max() + 0.025),
                         n=len(es), pos=sorted(float(P(b)[:, 0].mean()) for b in es),
                         ew=float(np.ptp(P(es[0])[:, 1])), eh=float(np.ptp(P(es[0])[:, 2])),
                         ez0=float(P(es[0])[:, 2].min() - zb), ez1=float(zt - P(es[0])[:, 2].max()))
        bars_ch = byb["CHATA_SUP" + side] + byb["CHATA_INF" + side]
        VCH[side]["u0"] = min(geo(b)[2] for b in bars_ch) - 0.025
        VCH[side]["u1"] = max(geo(b)[3] for b in bars_ch) + 0.025
        ss = np.diff(VCH[side]["pos"])
        VCH[side]["s"] = float(np.median(ss))
    # caras de vigas de ejes A (u) y N (v)
    faceA = {k: (u - 0.15, u + 0.15) for k, u in GU.items()}
    faceN = {k: (v - 0.15, v + 0.15) for k, v in GV.items()}
    # recubrimientos medidos
    cov_inf = float(min(P(b)[:, 2].min() for b in byb["VIG_INF"]) - zb - byb["VIG_INF"][0]["db"] / 2)
    cov_sup = float(zt - max(P(b)[:, 2].max() for b in byb["VIG_BAS12_"]) - byb["VIG_BAS12_"][0]["db"] / 2)
    # separacion de la malla de temperatura
    tsep = {}
    for r in ("TEMP_V", "TEMP_U"):
        byi = collections.defaultdict(list)
        for b in byb[r]:
            byi[idx(b["role"])].append(geo(b)[1])
        fx = sorted(min(v) for v in byi.values())
        tsep[r] = (len(fx), (fx[-1] - fx[0]) / (len(fx) - 1))

    doc = new_doc()
    add_layers(doc)

    # ============================================================ 1. PLANTA 1:50
    PL = View(doc, 50, (0, 0))
    m = PL.m
    gu0, gu1 = -2.30, 11.30
    gv0, gv1 = -0.95, 11.30
    for k, u in GU.items():
        PL.line((u, gv0), (u, gv1), "E-EJES", linetype=PL.lt("EJE"))
        PL.grid_bubble((u, gv1 + 5 * m), k)
        PL.grid_bubble((u, gv0 - 5 * m), k)
    for k, v in GV.items():
        PL.line((gu0, v), (gu1, v), "E-EJES", linetype=PL.lt("EJE"))
        PL.grid_bubble((gu0 - 5 * m, v), k)
        PL.grid_bubble((gu1 + 5 * m, v), k)

    # columnas (achuradas) y vigas bajo la losa (ocultas)
    for t, g in colfp.items():
        PL.hatch(list(g.exterior.coords)[:-1], "E-COLUMNA-ACH")
        PL.pline(list(g.exterior.coords), "E-COLUMNA")
    for t, g in beamfp.items():
        q = g.difference(colU.buffer(0.001))
        for gg in ([q] if q.geom_type == "Polygon" else list(q.geoms)):
            if gg.area < 1e-4:
                continue
            ring = LineString(list(gg.exterior.coords))
            # los bordes que coinciden con el borde de losa se ven como borde; el resto oculto
            vis = ring.difference(fp.exterior.buffer(0.004)).difference(colU.buffer(0.002))
            for ls in (vis.geoms if hasattr(vis, "geoms") else [vis]):
                if ls.geom_type == "LineString" and ls.length > 0.02:
                    PL.pline(list(ls.coords), "E-OCULTO", linetype=PL.lt("OCULTA"))
    # contorno de losa
    PL.pline(list(fp.exterior.coords), "E-CORTE")
    for hole in fp.interiors:
        PL.pline(list(hole.coords), "E-CORTE")

    # vigas chatas (ocultas, dentro del espesor)
    for side, c in VCH.items():
        for vv in (c["v0"], c["v1"]):
            seg = LineString([(c["u0"] - 0.03, vv), (c["u1"] + 0.03, vv)]).intersection(fp).difference(beamU.union(colU))
            for ls in (seg.geoms if hasattr(seg, "geoms") else [seg]):
                if ls.geom_type == "LineString" and ls.length > 0.05:
                    PL.pline(list(ls.coords), "E-OCULTO", linetype=PL.lt("OCULTA"))

    # viguetas (nervios 0.10) en linea fina
    solidU = beamU.union(colU).union(unary_union([box(c["u0"] - 1, c["v0"], c["u1"] + 1, c["v1"]) for c in VCH.values()]))
    free_fp = fp.difference(solidU)

    def rib_lines(line, off_axis):
        q = line.intersection(free_fp)
        for ls in (q.geoms if hasattr(q, "geoms") else [q]):
            if ls.geom_type != "LineString" or ls.length < 0.1:
                continue
            c = np.array(ls.coords)
            for s in (-RIB / 2, RIB / 2):
                cc = c.copy()
                cc[:, off_axis] += s
                PL.pline([tuple(p) for p in cc], "E-PROYECCION")

    for k, v in vigX.items():
        rib_lines(LineString([(umin - 1, v), (umax + 1, v)]), 1)
    for side in ("L", "R"):
        for k, u in ribY[side].items():
            rib_lines(LineString([(u, vmin - 1), (u, VCH["L"]["v0"])]) if side == "L" else LineString([(u, VCH["R"]["v1"]), (u, vmax + 1)]), 0)

    # -------- simbolos de aligerado por paño
    ch = VCH
    vA = (ch["L"]["v1"], faceN["N-2"][0])
    vB = (faceN["N-2"][1], ch["R"]["v0"])
    bays = [(faceA["A-1"][1], faceA["A-4"][0]), (faceA["A-4"][1], faceA["A-2"][0]), (faceA["A-2"][1], faceA["A-3"][0])]
    sym_v = {}
    # franja A: entre la vigueta 2 y la 3 (hueco libre de rotulos)
    ka = stripA
    kb = stripB
    yA = (vigX[ka[1]] + vigX[ka[2]]) / 2 - 0.03
    yB = (vigX[kb[1]] + vigX[kb[2]]) / 2 - 0.03
    for (a, b_), off in zip(bays, (0.0, 0.75, 0.35)):
        c = (a + b_) / 2 + off
        alig_symbol(PL, (c, yA), True, L=1.0)
        alig_symbol(PL, (c, yB), True, L=1.0)
    # franjas laterales (viguetas dir. Y)
    ribsL = sorted(ribY["L"].values())
    ribsR = sorted(ribY["R"].values())
    midL = [(ribsL[i] + ribsL[i + 1]) / 2 for i in range(len(ribsL) - 1) if ribsL[i + 1] - ribsL[i] < 0.45]
    midR = [(ribsR[i] + ribsR[i + 1]) / 2 for i in range(len(ribsR) - 1) if ribsR[i + 1] - ribsR[i] < 0.45]

    def near(lst, x):
        return min(lst, key=lambda t: abs(t - x))
    alig_symbol(PL, (near(midL, 1.2), (vmin + faceN["N-3"][0]) / 2), False, L=0.9)
    alig_symbol(PL, (near(midL, 2.4), (faceN["N-3"][1] + ch["L"]["v0"]) / 2), False, L=0.9)
    alig_symbol(PL, (near(midL, 7.3), (faceN["N-3"][1] + ch["L"]["v0"]) / 2), False, L=0.9)
    alig_symbol(PL, (near(midR, 1.2), (ch["R"]["v1"] + faceN["N-1"][0]) / 2), False, L=0.9)
    alig_symbol(PL, (near(midR, 8.9), (ch["R"]["v1"] + faceN["N-1"][0]) / 2), False, L=0.9)

    # -------- acero representativo, franjas dir. X
    def bars_idx(r, k):
        return [b for b in byb[r] if idx(b["role"]) == k]

    for strip in (stripA, stripB):
        kinf, ktop = strip[0], strip[-1]
        vinf, vtop = vigX[kinf], vigX[ktop]
        # inferior corrido (piezas reales, con traslape)
        pieces = sorted(bars_idx("VIG_INF", kinf), key=lambda b: geo(b)[2])
        for b in pieces:
            plan_bar(PL, b)
        (_, _, a0, a1), (_, _, b0, b1) = geo(pieces[0]), geo(pieces[1])
        lab_u = [(bays[0][0] + bays[0][1]) / 2 + 0.7, (bays[2][0] + bays[2][1]) / 2 - 0.3]
        for b, uu in zip(pieces, lab_u):
            PL.text(f'1{dtxt(b["d"])} inf. L={b["L"]:.2f}', (uu, vinf + 0.9 * m), 1.7, "E-ACERO-TXT", "BOTTOM_CENTER")
        # traslape
        o0, o1 = max(a0, b0), min(a1, b1)
        PL.dim((o0, vinf), (o1, vinf), (o0, vinf + 3.2 * m), 0, text=f"trasl. {o1 - o0:.2f}")
        # superiores: volado, bastones interiores y extremo
        tops = bars_idx("VIG_VOL", ktop) + bars_idx("VIG_BAS12_", ktop) + bars_idx("VIG_BAS38_", ktop)
        for b in tops:
            plan_bar(PL, b)
            _, _, x0, x1 = geo(b)
            PL.text(f'1{dtxt(b["d"])} L={b["L"]:.2f}', ((x0 + x1) / 2, vtop - 0.9 * m), 1.7, "E-ACERO-TXT", "TOP_CENTER")
            # cotas desde la cara de apoyo
            xs = [x0]
            for k_, (f0, f1) in faceA.items():
                if x0 - 0.01 < f0 and f1 < x1 + 0.01:
                    xs += [f0, f1]
                elif f0 < x1 < f1 + 0.05 and x0 < f0:
                    xs += [f0]
                elif f0 - 0.05 < x0 < f1 and x1 > f1:
                    xs = [x0, f1] if x0 < f1 - 0.005 else [x0]
            xs = sorted(set(round(x, 4) for x in xs + [x1]))
            xs = [x for i, x in enumerate(xs) if i == 0 or x - xs[i - 1] > 0.02]
            PL.hdim_chain(xs, vtop, vtop + 3.8 * m)
        PL.text(f"(ídem en las {len(strip)} viguetas, {sp(vigX[strip[1]] - vigX[strip[0]])})",
                ((bays[1][0] + bays[1][1]) / 2 - 0.35, vinf + 0.9 * m), 1.5, "E-ACERO-TXT", "BOTTOM_CENTER")

    # -------- acero representativo, franjas dir. Y (volado N-4 / lado escalera / borde N-1)
    def lat(r, k):
        bl = [b for b in byb[r] if idx(b["role"]) == k]
        return bl[0] if bl else None

    def lat_near(r, u, d=None):
        bl = [b for b in byb[r] if d is None or b["d"] == d]
        return min(bl, key=lambda b: abs(geo(b)[1] - u))

    reps = [("LAT_SUPL", 4.75, "1/2", "LAT_INFL", 5.134, 4.55),
            ("LAT_SUPL", 8.35, "3/8", "LAT_INFL", 7.95, 8.82),
            ("LAT_SUPR", 4.75, None, "LAT_INFR", 5.134, 4.55)]
    for rs, us, dd, ri, ui, udim in reps:
        bs_ = lat_near(rs, us, dd)
        bi_ = lat_near(ri, ui)
        plan_bar(PL, bs_)
        plan_bar(PL, bi_)
        _, us_, s0, s1 = geo(bs_)
        _, ui_, i0, i1 = geo(bi_)
        PL.text(f'1{dtxt(bs_["d"])} sup. L={bs_["L"]:.2f}', (us_ + 0.9 * m, (s0 + s1) / 2), 1.7, "E-ACERO-TXT", "TOP_CENTER", rot=90)
        PL.text(f'1{dtxt(bi_["d"])} inf. L={bi_["L"]:.2f}', (ui_ + 0.9 * m, (i0 + i1) / 2), 1.7, "E-ACERO-TXT", "TOP_CENTER", rot=90)
        # cotas: borde / cara de viga N / cara de VCH / extremo
        side = "L" if rs.endswith("L") else "R"
        c = VCH[side]
        ys = [s0, s1]
        for k_, (f0, f1) in faceN.items():
            for f in (f0, f1):
                if s0 + 0.02 < f < s1 - 0.02:
                    ys.append(f)
        for f in (c["v0"], c["v1"]):
            if s0 + 0.02 < f < s1 - 0.02:
                ys.append(f)
        ys = sorted(set(round(y, 4) for y in ys))
        PL.vdim_chain(ys, us_, udim)

    # -------- vigas chatas: barras inferiores reales (con traslape) + rotulo
    for side in ("L", "R"):
        c = VCH[side]
        pcs = sorted([b for b in byb["CHATA_INF" + side] if idx(b["role"]) == 1], key=lambda b: geo(b)[2])
        for b in pcs:
            plan_bar(PL, b)
        (_, va_, a0, a1), (_, vb_, b0, b1) = geo(pcs[0]), geo(pcs[1])
        o0, o1 = max(a0, b0), min(a1, b1)
        vm = (c["v0"] + c["v1"]) / 2
        nsup = len({idx(b["role"]) for b in byb["CHATA_SUP" + side]})
        ninf = len({idx(b["role"]) for b in byb["CHATA_INF" + side]})
        ylab = (c["v1"] + vigX[stripA[0]] - RIB / 2) / 2 if side == "L" else c["v1"] + 0.10
        PL.text(f'VCH-{side} 0.30x{H:.2f}: {nsup}{dtxt("1/2")} sup.+{ninf}{dtxt("1/2")} inf., '
                f'Est. {dtxt("1/4")} {sp(c["s"])} - det. 5-5',
                (2.7 if side == "L" else 7.3, ylab), 1.5, "E-ACERO-TXT", "MIDDLE_CENTER")
        PL.text(f"trasl. VCH {o1 - o0:.2f}", ((o0 + o1) / 2, ylab if side == "L" else ylab), 1.5, "E-ACERO-TXT", "MIDDLE_CENTER")

    # -------- malla de temperatura (muestra real en un recuadro)
    tb = box(6.95, ch["R"]["v1"] + 0.22, 8.55, faceN["N-1"][0] - 0.25)
    for r in ("TEMP_V", "TEMP_U"):
        for b in byb[r]:
            q = LineString(P(b)[:, :2]).intersection(tb)
            if q.geom_type == "LineString" and q.length > 0.05:
                PL.pline(list(q.coords), "E-ACERO")
    PL.pline(list(tb.exterior.coords), "E-TEXTO")
    PL.text(f'Malla temp. {dtxt("1/4")} {sp(tsep["TEMP_V"][1])} c/s', ((tb.bounds[0] + tb.bounds[2]) / 2, tb.bounds[3] + 0.6 * m),
            1.6, "E-ACERO-TXT", "BOTTOM_CENTER")

    # -------- escalera / abertura
    stair = [e for e in E.values() if e["cat"] == "escalera" and e.get("tipo") and e["bbox"][0][2] <= zt + 0.05 and e["bbox"][1][2] >= zt - 0.25]
    for e in stair:
        try:
            g = footprint(e)
        except Exception:
            continue
        PL.pline(list(g.exterior.coords), "E-PROYECCION")
    hole = box(GU["A-2"] - 0.3, 0.15, 10.15, faceN["N-3"][0]).difference(fp)
    hb = hole.bounds
    PL.text("ABERTURA / ESCALERA", ((hb[0] + hb[2]) / 2 + 0.5, (hb[1] + hb[3]) / 2 + 0.25), 2.0, "E-TEXTO")
    PL.text("(ver lámina de escalera)", ((hb[0] + hb[2]) / 2 + 0.5, (hb[1] + hb[3]) / 2 - 0.05), 1.6, "E-TEXTO")

    # -------- cotas generales
    us = sorted(GU.values())
    PL.hdim_chain([umin] + us + [umax], vmax, 10.75)
    PL.dim((umin, vmax), (umax, vmax), (umin, 11.05), 0)
    vs = sorted(GV.values())
    PL.vdim_chain([vs[0], vmin] + vs[1:] + [vmax], umin, -1.45)
    PL.dim((umin, vmin), (umin, vmax), (-1.80, vmin), 90)
    # volados
    top_edge = [p for p in fp.exterior.coords if abs(p[1] - vmax) < 1e-3]
    u_edge_top = min(p[0] for p in top_edge)
    PL.dim((u_edge_top, vmax), (faceA["A-1"][0], vmax), (u_edge_top, vmax + 0.30), 0)
    bot_edge = [p for p in fp.exterior.coords if abs(p[1] - vmin) < 1e-3]
    u_edge_bot = min(p[0] for p in bot_edge)
    ang = math.degrees(math.atan2(vmax - vmin, u_edge_top - u_edge_bot))
    vv = 3.6
    ue = u_edge_bot + (u_edge_top - u_edge_bot) * (vv - vmin) / (vmax - vmin)
    PL.text(f"BORDE INCLINADO: VOLADO VARIABLE {abs(faceA['A-1'][0] - u_edge_bot):.2f} A {faceA['A-1'][0] - u_edge_top:.2f} DESDE LA CARA DE VIGA A-1",
            (ue - 1.0 * m, vv), 1.5, "E-TEXTO", "BOTTOM_CENTER", rot=ang)
    PL.vdim_chain([vmin, faceN["N-3"][0]], -0.15, -0.75)
    PL.text("VOLADO", (-0.95, (vmin + faceN["N-3"][0]) / 2), 1.5, "E-TEXTO", "BOTTOM_CENTER", rot=90)
    # abertura / frente
    bot = [p[0] for p in fp.exterior.coords if abs(p[1] - vmin) < 1e-3]
    notch_u = max(bot)
    PL.hdim_chain([min(bot), GU["A-1"], GU["A-4"], notch_u, GU["A-2"], GU["A-3"], umax], vmin, -0.45)
    # niveles
    PL.level(1.6, 0.25, f"NPT {npt}", left=False)
    PL.text(f"Fondo de losa +{zb:.2f}", (1.6 + 2.6 * m, 0.25 - 1.2 * m), 1.5, "E-NIVEL", "TOP_LEFT")

    # -------- marcas de corte
    U1 = 8.95
    section_mark(PL, (U1, ch["L"]["v0"] - 0.30), (U1, faceN["N-2"][1] + 0.30), "1")
    section_mark(PL, (4.75, vmin - 0.30), (4.75, ch["L"]["v1"] + 0.02), "2")
    section_mark(PL, (4.75, ch["R"]["v0"] - 0.02), (4.75, vmax + 0.15), "3")
    vig_long = vigX[stripA[-1]]
    section_mark(PL, (umin - 0.35, vig_long), (umax + 0.35, vig_long), "4", flip=True)
    U5 = min(VCH["L"]["pos"], key=lambda x: abs(x - 0.65))
    section_mark(PL, (U5, ch["L"]["v0"] - 0.22), (U5, ch["L"]["v1"] + 0.22), "5")

    # ============================================================ 2. CORTE 4-4 (longitudinal vigueta) 1:25
    S4 = View(doc, 25, (0, 30 - zb))
    m4 = S4.m
    win4 = (umin - 0.30, zt - 0.56, umax + 0.10, zt + 0.06)
    polys = union_cut([SL] + list(beams.values()), 1, vig_long, win4)
    draw_cut(S4, polys, win4)
    ktop = stripA[-1]
    vb = [b for b in LB if base(b["role"]) in ("VIG_INF", "VIG_BAS12_", "VIG_BAS38_", "VIG_VOL") and idx(b["role"]) == ktop]
    inf_p = sorted([b for b in vb if base(b["role"]) == "VIG_INF"], key=lambda b: geo(b)[2])
    for i, b in enumerate(vb):
        pl = P(b)
        dz = 0.015 if (b is inf_p[-1]) else 0.0
        S4.pline([(p[0], p[2] + dz) for p in pl], "E-ACERO")
    tU = [b for b in byb["TEMP_U"]]
    draw_bars_section(S4, tU, 1, vig_long, win4, par_tol=0.0)
    bcut = [b for b in bbars if abs(np.ptp(P(b)[:, 1])) > 0.3 or b["role"].startswith("ESTRIBO")]
    hostsA = [t for t, g in beamfp.items() if g.intersects(LineString([(umin - 1, vig_long), (umax + 1, vig_long)]))]
    draw_bars_section(S4, [b for b in bbars if b["host"] in hostsA], 1, vig_long, win4, par_tol=0.0)
    # ejes
    for k, u in GU.items():
        S4.line((u, zt - 0.80), (u, zt + 0.02), "E-EJES", linetype=S4.lt("EJE"))
        S4.grid_bubble((u, zt - 0.80 - 4 * m4), k, 4)
    # cotas: luces libres (abajo)
    xs = [min(x for x, y in LineString([(umin - 1, vig_long), (umax + 1, vig_long)]).intersection(fp).coords)]
    for k in ("A-1", "A-4", "A-2", "A-3"):
        xs += list(faceA[k])
    S4.hdim_chain(xs, zt - 0.5, zt - 0.5 - 4.5 * m4)
    # cotas: bastones desde la cara (arriba)
    ztop = zt + 5.5 * m4
    for b in vb:
        if base(b["role"]) == "VIG_INF":
            continue
        _, _, x0, x1 = geo(b)
        xx = [x0]
        for k, (f0, f1) in faceA.items():
            for f in (f0, f1):
                if x0 + 0.02 < f < x1 - 0.02:
                    xx.append(f)
        xx = sorted(xx + [x1])
        S4.hdim_chain(xx, zt, ztop)
        S4.text(f'1{dtxt(b["d"])} L={b["L"]:.2f}', ((x0 + x1) / 2, ztop + 4.2 * m4), 1.8, "E-ACERO-TXT", "BOTTOM_CENTER")
    # inferior y traslape
    (_, _, a0, a1), (_, _, b0, b1) = geo(inf_p[0]), geo(inf_p[1])
    o0, o1 = max(a0, b0), min(a1, b1)
    S4.leader(((a0 + 2.0), zb + 0.031), (a0 + 2.3, zt - 0.40),
              f'1{dtxt("1/2")} inf. corrido: L={inf_p[0]["L"]:.2f} + {inf_p[1]["L"]:.2f}', 1.8, side=1)
    S4.leader(((o0 + o1) / 2, zb + 0.036), (o1 + 0.5, zt - 0.40), f"trasl. {o1 - o0:.2f} sobre eje A-2 (según modelo)", 1.8, side=1)
    S4.leader((8.15, zt - 0.02), (7.95, zt + 0.30), f'malla {dtxt("1/4")} {sp(tsep["TEMP_U"][1])}', 1.6, side=-1)
    edge4 = min(x for x, y in LineString([(umin - 1, vig_long), (umax + 1, vig_long)]).intersection(fp).coords)
    S4.dim((edge4, zb), (edge4, zt), (edge4 - 0.20, zb), 90)
    S4.level(8.45, zt, f"NPT {npt}", left=True)

    # ============================================================ 3. CORTE 1-1 (transversal aligerado) 1:20
    S1 = View(doc, 20, (30, 0 - zb))
    m1 = S1.m
    win1 = (ch["L"]["v0"] - 0.28, zt - 0.56, faceN["N-2"][1] + 0.26, zt + 0.06)
    ribs1 = [v for v in vigX.values() if win1[0] < v < win1[2]]
    sol1 = [(v - RIB / 2, v + RIB / 2) for v in ribs1] + [(ch["L"]["v0"], ch["L"]["v1"]), faceN["N-2"]]
    bpol = union_cut([beams[t] for t in beams], 0, U1, win1)
    cas1 = alig_section(S1, win1, zb, zt, sol1, bpol)
    sel = byb["VIG_INF"] + byb["TEMP_V"] + byb["TEMP_U"] + byb["CHATA_SUPL"] + byb["CHATA_INFL"]
    draw_bars_section(S1, sel, 0, U1, win1, par_tol=0.13)
    draw_bars_section(S1, byb["CHATA_ESTL"], 0, U1, win1, par_tol=0.11)
    hostsN = [t for t, g in beamfp.items() if g.intersects(LineString([(U1, win1[0]), (U1, win1[2])]))]
    draw_bars_section(S1, [b for b in bbars if b["host"] in hostsN], 0, U1, win1, par_tol=0.0)
    S1.line((GV["N-2"], zt - 0.75), (GV["N-2"], zt + 0.05), "E-EJES", linetype=S1.lt("EJE"))
    S1.grid_bubble((GV["N-2"], zt - 0.75 - 4 * m1), "N-2", 4)
    # cotas
    r0 = ribs1[0]
    xs = [ch["L"]["v0"], ch["L"]["v1"], r0 - RIB / 2, r0 + RIB / 2, ribs1[1] - RIB / 2]
    S1.hdim_chain(xs[:3], zb, zb - 4 * m1)
    S1.hdim_chain(xs[3:], zb, zb - 4 * m1)
    S1.dim((r0 - RIB / 2, zb), (r0 + RIB / 2, zb), (r0 - RIB / 2, zb - 9 * m1), 0)
    xs2 = [ribs1[-1] + RIB / 2, faceN["N-2"][0]]
    S1.hdim_chain(xs2, zb, zb - 4 * m1)
    S1.dim((win1[2], zb), (win1[2], zt), (win1[2] + 10 * m1, zb), 90)
    S1.leader((ribs1[1], zb + 0.07), (ribs1[1] + 0.12, zb - 0.26), f"vigueta {RIB:.2f}", 1.7, side=1, layer="E-TEXTO")
    cm_ = [(a + b) / 2 for a, b in cas1 if abs((b - a) - 0.30) < 0.02][0]
    S1.leader((cm_ + 0.05, zb + 0.05), (cm_ + 0.25, zt + 0.30), f"casetón poliestireno 0.30x{CAS_H:.2f}", 1.7, side=1, layer="E-TEXTO")
    S1.text("(NO MODELADO)", (cm_ + 0.25 + 3 * m1, zt + 0.30 - 3.2 * m1), 1.6, "E-TEXTO", "MIDDLE_LEFT")
    S1.leader((ch["L"]["v0"] - 0.15, zt - 0.025), (ch["L"]["v0"] - 0.12, zt + 0.22), f"losita {LOSITA:.2f}", 1.7, side=-1, layer="E-TEXTO")
    S1.leader((ribs1[0], zb + 0.031), (ribs1[0] - 0.05, zb - 0.26), f'1{dtxt("1/2")} inf. (V1)', 1.7, side=-1)
    S1.leader(((ch["L"]["v0"] + ch["L"]["v1"]) / 2, zt - 0.10), ((ch["L"]["v0"] + ch["L"]["v1"]) / 2 + 0.05, zt + 0.12),
              "VCH (det. 5-5)", 1.7, side=1)
    S1.level(win1[0] + 0.02, zt, f"NPT {npt}", left=False)

    # ============================================================ 4. CORTE 2-2 (volado N-4 + VCH) 1:20
    U2 = 4.75
    S2 = View(doc, 20, (60, 0 - zb))
    m2 = S2.m
    win2 = (vmin - 0.25, zt - 0.56, vigX[stripA[0]] + 0.13, zt + 0.06)
    sol2 = [(vmin, ch["L"]["v1"]), (vigX[stripA[0]] - RIB / 2, vigX[stripA[0]] + RIB / 2)]
    bpol = union_cut([beams[t] for t in beams], 0, U2, win2)
    alig_section(S2, win2, zb, zt, sol2, bpol, ext=(vmin, 99))
    ls_ = lat_near("LAT_SUPL", U2, "1/2")
    li_ = lat_near("LAT_INFL", U2)
    for b in (ls_, li_):
        S2.pline([(p[1], p[2]) for p in P(b)], "E-ACERO")
    draw_bars_section(S2, byb["TEMP_V"] + byb["CHATA_SUPL"] + byb["CHATA_INFL"] + byb["VIG_INF"], 0, U2, win2, par_tol=0.0)
    draw_bars_section(S2, byb["CHATA_ESTL"], 0, U2, win2, par_tol=0.11)
    hostsN = [t for t, g in beamfp.items() if g.intersects(LineString([(U2, win2[0]), (U2, win2[2])]))]
    draw_bars_section(S2, [b for b in bbars if b["host"] in hostsN], 0, U2, win2, par_tol=0.0)
    S2.line((GV["N-3"], zt - 0.75), (GV["N-3"], zt + 0.05), "E-EJES", linetype=S2.lt("EJE"))
    S2.grid_bubble((GV["N-3"], zt - 0.75 - 4 * m2), "N-3", 4)
    S2.hdim_chain([vmin, faceN["N-3"][0], faceN["N-3"][1], ch["L"]["v0"], ch["L"]["v1"]], zb, zb - 5 * m2)
    _, _, s0, s1 = geo(ls_)
    S2.hdim_chain([s0, s1], zt, zt + 5 * m2)
    hk = [s for s in ls_["segs"] if s][0]
    S2.leader(((s0 + faceN["N-3"][0]) / 2, zt - 0.03), ((s0 + faceN["N-3"][0]) / 2 + 0.1, zt + 0.40),
              f'1{dtxt(ls_["d"])} sup. L={ls_["L"]:.2f} (ganchos {hk:.2f} en ambos extremos)', 1.7, side=1)
    S2.leader((faceN["N-3"][1] + 0.6, zb + 0.03), (faceN["N-3"][1] + 0.75, zb - 0.30),
              f'1{dtxt(li_["d"])} inf. L={li_["L"]:.2f}', 1.7, side=1)
    S2.leader((vmin + 0.35, zt - 0.025), (vmin + 0.15, zt + 0.22), f'malla {dtxt("1/4")} {sp(tsep["TEMP_V"][1])}', 1.6, side=-1)
    S2.text("VOLADO", ((vmin + faceN["N-3"][0]) / 2, zb - 10.5 * m2), 1.7, "E-TEXTO", "TOP_CENTER")
    S2.text("ANCLAJE EN VCH", ((faceN["N-3"][1] + ch["L"]["v0"]) / 2, zb - 10.5 * m2), 1.7, "E-TEXTO", "TOP_CENTER")
    S2.level(vmin + 0.35, zt, f"NPT {npt}", left=False)
    S2.dim((vmin, zb), (vmin, zt), (vmin - 0.12, zb), 90)

    # ============================================================ 5. CORTE 3-3 (borde N-1 + VCH) 1:20
    S3 = View(doc, 20, (90, 0 - zb))
    m3 = S3.m
    win3 = (vigX[stripB[-1]] - 0.13, zt - 0.56, vmax + 0.25, zt + 0.06)
    sol3 = [(ch["R"]["v0"], vmax), (vigX[stripB[-1]] - RIB / 2, vigX[stripB[-1]] + RIB / 2)]
    bpol = union_cut([beams[t] for t in beams], 0, U2, win3)
    alig_section(S3, win3, zb, zt, sol3, bpol, ext=(-99, vmax))
    rs_ = lat_near("LAT_SUPR", U2)
    ri_ = lat_near("LAT_INFR", U2)
    for b in (rs_, ri_):
        S3.pline([(p[1], p[2]) for p in P(b)], "E-ACERO")
    draw_bars_section(S3, byb["TEMP_V"] + byb["CHATA_SUPR"] + byb["CHATA_INFR"] + byb["VIG_INF"], 0, U2, win3, par_tol=0.0)
    draw_bars_section(S3, byb["CHATA_ESTR"], 0, U2, win3, par_tol=0.11)
    hostsN = [t for t, g in beamfp.items() if g.intersects(LineString([(U2, win3[0]), (U2, win3[2])]))]
    draw_bars_section(S3, [b for b in bbars if b["host"] in hostsN], 0, U2, win3, par_tol=0.0)
    S3.line((GV["N-1"], zt - 0.75), (GV["N-1"], zt + 0.05), "E-EJES", linetype=S3.lt("EJE"))
    S3.grid_bubble((GV["N-1"], zt - 0.75 - 4 * m3), "N-1", 4)
    S3.hdim_chain([ch["R"]["v0"], ch["R"]["v1"], faceN["N-1"][0], vmax], zb, zb - 5 * m3)
    _, _, s0, s1 = geo(rs_)
    S3.hdim_chain([s0, s1], zt, zt + 5 * m3)
    S3.leader(((s0 + s1) / 2, zt - 0.03), ((s0 + s1) / 2 - 0.3, zt + 0.40),
              f'1{dtxt(rs_["d"])} sup. L={rs_["L"]:.2f} (ganchos)', 1.7, side=-1)
    S3.leader(((s0 + s1) / 2 + 0.3, zb + 0.03), ((s0 + s1) / 2 + 0.1, zb - 0.30), f'1{dtxt(ri_["d"])} inf. L={ri_["L"]:.2f}', 1.7, side=-1)
    S3.level(vmax + 0.05, zt, f"NPT {npt}", left=False)

    # ============================================================ 6. DETALLE 5-5 VIGA CHATA 1:10
    S5 = View(doc, 10, (120, 0 - zb))
    m5 = S5.m
    c = VCH["L"]
    win5 = (c["v0"] - 0.17, zt - 0.23, c["v1"] + 0.17, zt + 0.03)
    alig_section(S5, win5, zb, zt, [(c["v0"], c["v1"])], [])
    draw_bars_section(S5, byb["CHATA_SUPL"] + byb["CHATA_INFL"] + byb["TEMP_V"], 0, U5, win5, par_tol=0.0, dot_min_mm=0.3)
    draw_bars_section(S5, byb["CHATA_ESTL"] + byb["TEMP_U"], 0, U5, win5, par_tol=0.03)
    es = min(byb["CHATA_ESTL"], key=lambda b: abs(P(b)[:, 0].mean() - U5))
    pe = P(es)
    S5.hdim_chain([c["v0"], c["v1"]], zb, zb - 9 * m5)
    S5.hdim_chain([pe[:, 1].min(), pe[:, 1].max()], zb, zb - 4.5 * m5)
    S5.vdim_chain([zb, zt], c["v1"], c["v1"] + 0.17)
    S5.vdim_chain([pe[:, 2].min(), pe[:, 2].max()], c["v1"], c["v1"] + 0.06)
    sup = [b for b in byb["CHATA_SUPL"] if geo(b)[2] <= U5 <= geo(b)[3]]
    inf = [b for b in byb["CHATA_INFL"] if geo(b)[2] <= U5 <= geo(b)[3]]
    zs = P(sup[0])[:, 2].mean()
    zi = P(inf[0])[:, 2].mean()
    S5.leader((geo(sup[0])[1], zs), (c["v0"] - 0.05, zt + 0.015), f'{len(sup)}{dtxt("1/2")} sup. (a {zt - zs:.3f} de la cara sup.)', 1.7, side=-1)
    S5.leader((geo(inf[0])[1], zi), (c["v0"] - 0.05, zb - 0.030), f'{len(inf)}{dtxt("1/2")} inf. (a {zi - zb:.3f} del fondo)', 1.7, side=-1)
    S5.leader((pe[:, 1].max(), (pe[:, 2].min() + pe[:, 2].max()) / 2), (c["v1"] + 0.03, zt + 0.015),
              f'Est. {dtxt("1/4")} {sp(c["s"])}  ({c["n"]} und.)', 1.7, side=1)

    # ============================================================ HOJA
    ps = new_sheet(doc, code)
    # planta
    ext_u = (-2.85, 11.85)
    ext_v = (-1.55, 11.85)
    pw = (ext_u[1] - ext_u[0]) * 20
    ph = (ext_v[1] - ext_v[0]) * 20
    pcx, pcy = 30 + pw / 2, 584 - 4 - ph / 2
    add_vp(ps, pcx, pcy, pw, ph, ((ext_u[0] + ext_u[1]) / 2, (ext_v[0] + ext_v[1]) / 2), 50)
    view_title(ps, pcx, pcy - ph / 2 - 7, f"PLANTA DE LOSA ALIGERADA - {level.upper()}  (NPT {npt})", "ESC. 1:50", w=150)

    xr0 = 30 + pw + 12                     # inicio de la zona derecha
    # corte 4-4
    w4 = (win4[2] - win4[0] + 0.30) * 40
    wz0, wz1 = zt - 1.05, zt + 0.50
    h4 = (wz1 - wz0) * 40
    c4x = (831 - 4 + xr0) / 2
    c4y = 584 - 4 - h4 / 2
    add_vp(ps, c4x, c4y, w4, h4, S4.P((win4[0] + win4[2]) / 2 - 0.12, (wz0 + wz1) / 2), 25)
    view_title(ps, c4x, c4y - h4 / 2 - 6, "CORTE 4-4  LONGITUDINAL DE VIGUETA (dir. X)",
               f"ESC. 1:25  (vigueta en eje de {vig_long:.3f} m; cotas de bastones desde la cara de apoyo)", w=140)
    def place(S, win, k, el_, er_, zlo, zhi, xl, ytop, ttl, sub):
        w = (win[2] - win[0] + el_ + er_) * 1000 / k
        h = (zhi - zlo) * 1000 / k
        cx, cy = xl + w / 2, ytop - h / 2
        add_vp(ps, cx, cy, w, h, S.P((win[0] - el_ + win[2] + er_) / 2, (zlo + zhi) / 2), k)
        view_title(ps, cx, cy - h / 2 - 6, ttl, sub, w=min(w - 4, 110))
        return w, h

    # fila 2: 2-2 y 1-1
    y2 = c4y - h4 / 2 - 30
    w, h = place(S2, win2, 20, 0.30, 0.05, zt - 0.95, zt + 0.55, xr0, y2, "CORTE 2-2  VOLADO LADO N-4 Y VCH", "ESC. 1:20")
    place(S1, win1, 20, 0.40, 0.60, zt - 0.95, zt + 0.55, xr0 + w + 10, y2, "CORTE 1-1  ALIGERADO TÍPICO", "ESC. 1:20")
    # fila 3: 3-3 y 5-5
    y3 = y2 - h - 32
    w3, h3 = place(S3, win3, 20, 0.55, 0.35, zt - 0.95, zt + 0.55, xr0, y3, "CORTE 3-3  BORDE N-1 Y VCH", "ESC. 1:20")
    place(S5, win5, 10, 0.50, 0.55, zt - 0.36, zt + 0.10, xr0 + w3 + 14, y3 - 10, "DETALLE 5-5  VIGA CHATA VCH", "ESC. 1:10")
    c3y = y3 - h3 / 2
    row4 = c3y - h3 / 2 - 32

    # leyenda
    lx, ly = 640, row4 - 80
    ptext(ps, "LEYENDA", (lx, ly), 3.0, "E-TITULO")
    items = [("col", "Columna bajo el nivel (achurado)"),
             ("oculto", "Viga bajo la losa / viga chata VCH (línea oculta)"),
             ("vig", "Vigueta 0.10 (nervio) - casetones entre viguetas"),
             ("arrow", "Dirección de viguetas, aligerado h = 0.20"),
             ("acero", "Acero de refuerzo (rep.); trazo corto = gancho 90°"),
             ("borde", "Borde de losa")]
    for i, (kind, s) in enumerate(items):
        yy = ly - 7 - i * 5.6
        if kind == "col":
            h_ = ps.add_hatch(color=252, dxfattribs={"layer": "E-COLUMNA-ACH"})
            h_.paths.add_polyline_path([(lx, yy - 1.5), (lx + 8, yy - 1.5), (lx + 8, yy + 1.5), (lx, yy + 1.5)], is_closed=True)
            ps.add_lwpolyline([(lx, yy - 1.5), (lx + 8, yy - 1.5), (lx + 8, yy + 1.5), (lx, yy + 1.5)], close=True, dxfattribs={"layer": "E-COLUMNA"})
        elif kind == "oculto":
            for dy in (-1.2, 1.2):
                for x in (0, 3.2, 6.4):
                    ps.add_line((lx + x, yy + dy), (lx + min(x + 2.0, 8), yy + dy), dxfattribs={"layer": "E-OCULTO"})
        elif kind == "vig":
            for dy in (-1.0, 1.0):
                ps.add_line((lx, yy + dy), (lx + 8, yy + dy), dxfattribs={"layer": "E-PROYECCION"})
        elif kind == "arrow":
            ps.add_line((lx, yy), (lx + 8, yy), dxfattribs={"layer": "E-TEXTO"})
            for p, sg in (((lx, yy), 1), ((lx + 8, yy), -1)):
                h_ = ps.add_hatch(color=7, dxfattribs={"layer": "E-TEXTO"})
                h_.paths.add_polyline_path([p, (p[0] + sg * 2.2, p[1] + 0.7), (p[0] + sg * 2.2, p[1] - 0.7)], is_closed=True)
        elif kind == "acero":
            ps.add_line((lx, yy), (lx + 8, yy), dxfattribs={"layer": "E-ACERO"})
            ps.add_line((lx + 8, yy - 1.3), (lx + 8, yy + 1.3), dxfattribs={"layer": "E-ACERO"})
        elif kind == "borde":
            ps.add_line((lx, yy), (lx + 8, yy), dxfattribs={"layer": "E-CORTE"})
        ptext(ps, s, (lx + 11, yy), 2.0, "E-TEXTO", "MIDDLE_LEFT")

    # cuadro de acero (debajo de la planta)
    rows, tot = steel_table(LB)
    hdr = [["MARCA", "DESCRIPCIÓN", "Ø", "CANT.", "L UNIT. (m)", "L TOTAL (m)", "PESO (kg)"]]
    tot_rows = [["", f"TOTAL {dtxt(d)}  ({KG[d]:.3f} kg/m)", "", "", "", "", f"{tot[d]:.1f}"] for d in ("1/4", "3/8", "1/2") if d in tot]
    tot_rows.append(["", "TOTAL ACERO DE LOSA DEL NIVEL", "", "", "", "", f"{sum(tot.values()):.1f}"])
    area = fp.area
    tot_rows.append(["", f"Área de losa (modelo) {area:.2f} m²  ->  cuantía", "", "", "", "", f"{sum(tot.values()) / area:.2f} kg/m²"])
    tx0 = 30
    ty0 = pcy - ph / 2 - 22
    cw = [13, 110, 12, 13, 25, 22, 20]
    Wt, Ht = table(ps, tx0, ty0, cw, hdr + rows + tot_rows, row_h=4.6, h_txt=1.85,
                   aligns=["C", "L", "C", "C", "C", "C", "C"])
    ptext(ps, f"CUADRO DE ACERO DE LA LOSA - {level.upper()} (medido del modelo, grupo {GRP})", (tx0, ty0 + 2), 2.8, "E-TITULO")

    # notas
    nx = tx0
    ny = ty0 - Ht - 12
    cargas = "piso terminado 100, tabiquería equivalente 210, s/c 200 kg/m²; muro de ladrillo de 10 cm en contorno y volados 516 kg/m"
    notas = [
        "NOTAS - LOSA ALIGERADA",
        "1. CONCRETO f'c = 210 kg/cm².  ACERO ASTM A615 Grado 60, fy = 4200 kg/cm².",
        f"2. ALIGERADO h = {H:.2f} en una dirección: viguetas 0.10 @ 0.40, losita {LOSITA:.2f}, casetones de poliestireno",
        "    0.30 x 0.15. Los CASETONES NO ESTÁN MODELADOS: el modelo representa la losa como piso macizo de 0.20",
        "    (tipo PISO_ESTRUCTURAL_MACIZO_200mm_VOLADO); ubicarlos según la posición de viguetas de esta planta.",
        f"3. RECUBRIMIENTO libre 2 cm (medido: inferior {cov_inf * 100:.1f} cm, superior {cov_sup * 100:.1f} cm).",
        "4. Viguetas de los paños en dir. X (paralelas a ejes N) apoyadas en las vigas de los ejes A. En las franjas",
        "    laterales (volado lado N-4 y borde N-1) viguetas en dir. Y ancladas 1.50 m en la viga chata VCH 0.30x0.20.",
        "5. Bastones: longitudes medidas desde la cara de apoyo. Barras > 9 m traslapadas 0.60 sobre la viga interior.",
        "    Ganchos a 90° de 0.12 en bordes libres y apoyos extremos.",
        f'6. Malla de temperatura {dtxt("1/4")} en ambos sentidos en toda la losita ({tsep["TEMP_V"][0]} + {tsep["TEMP_U"][0]} líneas, sep. medida',
        f'    {tsep["TEMP_V"][1]:.3f} / {tsep["TEMP_U"][1]:.3f} m).',
        f"7. Cargas de diseño (nodo Dynamo 14, Anexo A): {cargas}.",
        "8. Acero dibujado en planta: una vigueta representativa por franja (ídem en todas las de la franja).",
        "9. Plano generado del modelo IFC 'Proyect sj.ifc' (Revit 2027); cotas y niveles en metros.",
    ]
    notes(ps, nx, ny, notas, h=1.9, lead=3.9, title_h=2.4)

    # cuadro de bastones / tramos medidos
    def chain_txt(b, faces):
        ax, _, x0, x1 = geo(b)
        pts = [(x0, None)]
        for f0, f1, nm in faces:
            if x0 + 0.02 < f1 and f0 < x1 - 0.02:
                pts += [(max(f0, x0), nm), (min(f1, x1), None)]
        pts.append((x1, None))
        pts = sorted(pts, key=lambda p: p[0])
        out = []
        for (a, nm), (b_, _) in zip(pts, pts[1:]):
            if b_ - a < 0.005:
                continue
            out.append(f"[{nm} {b_ - a:.2f}]" if nm else f"{b_ - a:.2f}")
        pl = P(b)
        zmed = np.median(pl[:, 2])
        nh = sum(1 for zz in (pl[0, 2], pl[-1, 2]) if abs(zz - zmed) > 0.05)
        return " + ".join(out), nh
    fA = [(f0, f1, k) for k, (f0, f1) in faceA.items()]
    fN = [(f0, f1, k) for k, (f0, f1) in faceN.items()] + [(c["v0"], c["v1"], "VCH") for c in VCH.values()]
    brow = [["MARCA", "Ø", "UBICACIÓN", "TRAMOS MEDIDOS (m): libre + [apoyo] + libre", "GANCHOS", "CANT."]]
    groups = collections.OrderedDict()
    for b in LB:
        mk = mark(b)
        if mk not in ("B1", "B2", "B3", "L1", "L2", "L3"):
            continue
        ch_, nh = chain_txt(b, fA if mk.startswith("B") else fN)
        key = (mk, b["d"], re.sub(r"[\d.]+", "#", re.sub(r"\[(\S+) [\d.]+\]", r"[\1]", ch_)))
        groups.setdefault(key, []).append((ch_, nh, b))
    UBI = {"B1": "vigueta X, sobre apoyo interior", "B2": "vigueta X, apoyo extremo A-3", "B3": "vigueta X, volado A-1",
           "L1": "vigueta Y, volado N-4", "L2": "vigueta Y, lado escalera", "L3": "vigueta Y, borde N-1"}
    for (mk, d, pat), lst in sorted(groups.items(), key=lambda kv: (ORDER.index(kv[0][0]), kv[0][2])):
        chs = sorted({c for c, _, _ in lst}, key=lambda c: float(c.split(" ")[0].strip("[")) if c[0] != "[" else 0)
        txt = chs[0] if len(chs) == 1 else f"{chs[0]}  ...  {chs[-1]}"
        hk = min(x for x in lst[0][2]["segs"] if x) if lst[0][1] else 0
        brow.append([mk, dtxt(d), UBI[mk], txt, f"{lst[0][1]} x {hk:.2f}" if lst[0][1] else "-", str(len(lst))])
    bx0, by0 = xr0, row4
    Wb, Hb = table(ps, bx0, by0, [11, 11, 48, 142, 18, 12], brow, row_h=4.6, h_txt=1.8, aligns=["C", "C", "L", "L", "C", "C"])
    ptext(ps, "CUADRO DE BASTONES Y ACERO SUPERIOR (tramos medidos del modelo, desde el extremo de la barra)", (bx0, by0 + 2), 2.6, "E-TITULO")
    ptext(ps, "Varias barras de un grupo: se indican la menor y la mayor (bordes inclinados). Apoyo = viga (eje) o viga chata VCH.",
          (bx0, by0 - Hb - 3.5), 1.7)

    title_block(ps, code, [f"LOSA ALIGERADA - {level.upper()} (NPT {npt})", "PLANTA, CORTES, DETALLE VCH Y CUADRO DE ACERO"])
    save_and_render_lt(doc, ps, basename)
    info = dict(level=level, code=code, zt=zt, area=area, tot=dict(tot), total=sum(tot.values()),
                n_vigX=len(vigX), vigX=vigX, n_ribY={s: len(v) for s, v in ribY.items()},
                cov_inf=cov_inf, cov_sup=cov_sup, tsep=tsep, VCH={s: (c["v0"], c["v1"], c["n"], c["s"]) for s, c in VCH.items()},
                rows=rows)
    return info


if __name__ == "__main__":
    want = sys.argv[1:] or [s[0] for s in SHEETS]
    for lv, code, bn in SHEETS:
        if lv in want:
            inf = build(lv, code, bn)
            print(code, lv, f"acero {inf['total']:.1f} kg", {k: round(v, 1) for k, v in inf["tot"].items()},
                  "vigX", inf["n_vigX"], "ribY", inf["n_ribY"], "cov", round(inf["cov_inf"], 4), round(inf["cov_sup"], 4))
            for r in inf["rows"]:
                print("   ", r)
