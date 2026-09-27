"""Lamina E-03 - COLUMNAS: secciones, elevaciones y cuadro de columnas (del modelo IFC)."""
import re
from sheetcommon import *

M = load_model()
E, B, GU, GV = M["elements"], M["bars"], M["GU"], M["GV"]
LEVELS = ["Cimentacion", "Nivel 1", "Nivel 2", "Nivel 3", "Nivel 4", "Nivel 5"]
LZ = M["levels"]
bars_by_host = collections.defaultdict(list)
for b in B:
    bars_by_host[b["host"]].append(b)


def mark(el):
    return el["com"].split("|")[1]


cols = {t: e for t, e in E.items() if e["cat"] == "columna"}


def col_at(mk, lvl):
    for t, e in cols.items():
        if mark(e) == mk and e["level"] == lvl:
            return t, e


def col_stack(mk):
    return [col_at(mk, l) for l in LEVELS[:-1] if col_at(mk, l)]


# ------------------------------------------------------------------ utilidades de corte horizontal
def draw_zcut(v, tag, zc, win):
    el = E[tag]
    segs = slice_mesh(np.asarray(el["v"], float), el["f"], 2, zc)
    polys = list(polygonize(unary_union(segs)))
    draw_cut(v, [unary_union(polys)], win)
    bl = bars_by_host[tag]
    # longitudinales -> puntos
    dots = []
    for b in bl:
        if b["role"] != "LONG":
            continue
        pl = np.asarray(b["pl"], float)
        for i in range(len(pl) - 1):
            a, c = pl[i], pl[i + 1]
            if (a[2] - zc) * (c[2] - zc) <= 0 and abs(c[2] - a[2]) > 0.05:
                s = (zc - a[2]) / (c[2] - a[2])
                P = a + s * (c - a)
                dots.append((P[0], P[1], b))
                v.circle((P[0], P[1]), RAD[b["d"]], "E-ACERO", fill=True)
                break
    # estribos del juego mas cercano a zc (proyectados)
    est = [b for b in bl if b["role"] == "ESTRIBO"]
    zs = sorted({round(float(np.asarray(b["pl"])[:, 2].mean()), 2) for b in est if "GRAPA" not in b["rest"][0]},
                key=lambda z: abs(z - zc))
    z0 = zs[0]
    b0 = min([b for b in est if "GRAPA" not in b["rest"][0]], key=lambda b: abs(np.asarray(b["pl"])[:, 2].mean() - z0))
    zone = b0["rest"][0][:-2]
    same = sorted([b for b in est if b["rest"][0] == b0["rest"][0]], key=lambda b: np.asarray(b["pl"])[:, 2].mean())
    k = [id(x) for x in same].index(id(b0))
    juego = []
    for nm in sorted({b["rest"][0] for b in est if b["rest"][0][:-2].replace("GRAPA_", "") == zone}):
        l = sorted([b for b in est if b["rest"][0] == nm], key=lambda b: np.asarray(b["pl"])[:, 2].mean())
        if k < len(l):
            juego.append(l[k])
    for b in juego:
        pl = np.asarray(b["pl"], float)
        v.pline([tuple(p[:2]) for p in pl], "E-ACERO", const_width=0.0075)
    return dots, juego


def zones(tag):
    """zonas de estribos (nombre -> (n, s, zmin, zmax)) de una columna."""
    est = [b for b in bars_by_host[tag] if b["role"] == "ESTRIBO" and "GRAPA" not in b["rest"][0]
           and b["rest"][0].endswith("_1")]
    zz = collections.defaultdict(list)
    for b in est:
        name = b["rest"][0][:-2]
        zz[name].append(float(np.asarray(b["pl"])[:, 2].mean()))
    out = {}
    for k, l in zz.items():
        l.sort()
        s = re.findall(r"_(\d+)(?:_B)?$", k)
        out[k] = (len(l), l[0], l[-1])
    return out


def zone_text(tag):
    z = zones(tag)
    if any(k.startswith("TODO") for k in z):
        n = sum(v[0] for k, v in z.items())
        return "todo @ .10"
    parts = []
    for k, lbl in (("CONF_INF_5", "1@.05"), ("CONF_INF_10", "@.10"), ("CONF_INF_15", "@.15")):
        if k in z:
            parts.append(f"{z[k][0]}{lbl[lbl.index('@'):]}" if k != "CONF_INF_5" else "1@.05")
    return ", ".join(parts) + ", rto. @.20 c/ext.; @.10 en traslape"


doc = new_doc()
add_layers(doc)
ps = new_sheet(doc, "E-03")

# ============================================================ SECCIONES 1:10
SEC = {}
for i, (key, mk, zc) in enumerate((("C-1", "N-1-A-2", 5.0), ("C-2", "N-1-A-1", 5.0))):
    tag, el = col_at(mk, "Nivel 2")
    v0, v1 = np.array(el["bbox"][0]), np.array(el["bbox"][1])
    V = View(doc, 5, (200 + 10 * i - v0[0], 0 - v0[1]))
    win = (v0[0] - 0.12, v0[1] - 0.12, v1[0] + 0.12, v1[1] + 0.12)
    dots, juego = draw_zcut(V, tag, zc, win)
    # cotas
    fp = footprint(el)
    xs = sorted({round(x, 4) for x, _ in fp.exterior.coords})
    ys = sorted({round(y, 4) for _, y in fp.exterior.coords})
    V.hdim_chain(xs, v0[1], v0[1] - 6 * V.m)
    if len(xs) > 2:
        V.dim((xs[0], v0[1]), (xs[-1], v0[1]), (xs[0], v0[1] - 11 * V.m), 0)
    V.vdim_chain(ys, v0[0], v0[0] - 6 * V.m)
    if len(ys) > 2:
        V.dim((v0[0], ys[0]), (v0[0], ys[-1]), (v0[0] - 11 * V.m, ys[0]), 90)
    # ejes
    ua, va = GU["A-" + mk.split("-A-")[1]], GV[mk.split("-A-")[0]]
    V.line((ua, v0[1] - 0.10), (ua, v1[1] + 0.10), "E-EJES", linetype=V.lt("EJE"))
    V.line((v0[0] - 0.10, va), (v1[0] + 0.10, va), "E-EJES", linetype=V.lt("EJE"))
    # rotulos de acero
    cnt = collections.Counter(b["d"] for _, _, b in dots)
    txt = " + ".join(f"{n} {dstr(d)}" for d, n in sorted(cnt.items(), key=lambda x: -KG[x[0]]))
    SEC[key] = {"view": V, "win": win, "tag": tag, "txt": txt, "n_est": len(juego), "dots": dots, "el": el, "juego": juego}
    # llamadas
    far = max(dots, key=lambda d: d[0] + d[1])
    V.leader((far[0], far[1]), (v1[0] + 0.05, v1[1] + 0.05), txt, 2.0, side=1)
    ng = sum(1 for b in juego if "GRAPA" in b["rest"][0])
    ne = len(juego) - ng
    e1 = [b for b in juego if "GRAPA" not in b["rest"][0]][0]
    p1 = np.asarray(e1["pl"])[3]
    V.leader((p1[0], p1[1]), (v1[0] + 0.05, v0[1] + 0.02), f"{ne} estribos + {ng} grapa{'s' if ng > 1 else ''} {dstr('3/8')}", 2.0, side=1)
    V.text("r = 0.04", ((v0[0] + v1[0]) / 2, v0[1] + 0.02), 1.6, "E-ACERO-TXT")
    SEC.setdefault("_", 0)

# ============================================================ ELEVACIONES 1:50
ELEV = {}
for i, (key, mk) in enumerate((("C-1", "N-2-A-2"), ("C-2", "N-1-A-1"))):
    st = col_stack(mk)
    t0, e0 = st[0]
    va = GV[mk.split("-A-")[0]]
    ua = GU["A-" + mk.split("-A-")[1]]
    # plano v = eje N de la columna (se ve el ancho en u)
    V = View(doc, 40, (300 + 20 * i, 0))
    bb0 = np.min([np.array(e["bbox"][0]) for _, e in st], 0)
    bb1 = np.max([np.array(e["bbox"][1]) for _, e in st], 0)
    win = (bb0[0] - 0.75, -2.08, bb1[0] + 2.25, 12.15)
    cut_elements(V, E, 1, va, win, cats=("zapata", "columna", "viga", "losa", "falsopiso"))
    hb = [b for t, _ in st for b in bars_by_host[t]]
    draw_bars_section(V, hb, 1, va, win, par_tol=0.45)
    V.line((ua, -2.3), (ua, 11.7), "E-EJES", linetype=V.lt("EJE"))
    V.grid_bubble((ua, 11.7 + 4 * V.m), "A-" + mk.split("-A-")[1], 4)
    for lv in LEVELS:
        z = LZ[lv]
        lab = ("NFZ " if lv == "Cimentacion" else "NPT ") + (f"{z:+.2f}" if z else "±0.00")
        V.level(bb1[0] + 0.62, z, lab + ("" if lv == "Cimentacion" else f"  {lv.upper()}"), left=False)
    # traslapes medidos (piezas P1..P4)
    xL = bb1[0] + 0.28
    for t, e in st[1:]:
        lb = [b for b in bars_by_host[t] if b["role"] == "LONG"]
        pl = np.asarray(lb[0]["pl"], float)
        zs, zl = pl[0, 2], pl[1, 2]
        V.dim((bb1[0], zs), (bb1[0], zl), (xL, zs), 90, text=f"{zl - zs:.2f}")
        V.text("trasl.", (xL + 1.5 * V.m, (zs + zl) / 2), 1.5, "E-ACERO-TXT", "MIDDLE_LEFT")
    # zonas de estribos (cadena de cotas a la izquierda) por tramo
    xZ = bb0[0] - 0.30
    for t, e in st[1:]:
        z = zones(t)
        z0_, z1_ = e["bbox"][0][2], e["bbox"][1][2]
        inf_end = max(z[k][2] for k in z if k.startswith("CONF_INF"))
        sup_ini = min(z[k][1] for k in z if k.startswith("CONF_SUP"))
        V.vdim_chain([z0_, inf_end, sup_ini, z1_], bb0[0], xZ, texts=[f"{inf_end - z0_:.2f}", "@.20", f"{z1_ - sup_ini:.2f}"])
    ELEV[key] = {"view": V, "win": win, "mk": mk}

# ============================================================ DETALLE DE TRASLAPE (1:10)
tagT, elT = col_at("N-2-A-2", "Nivel 1")
b1 = [b for b in bars_by_host[tagT] if b["role"] == "LONG" and b["d"] == "5/8"][0]
seg = [x for x in b1["segs"] if x]
VT = View(doc, 20, (500, 0))
lap, bay = seg[0], seg[1]
# barra inferior (continua) y barra superior con bayoneta 1:6
db = 0.015875
VT.pline([(0, 0), (0, 1.9)], "E-ACERO", const_width=db)
VT.pline([(db, 0.35), (db, 0.35 + lap), (0.0, 0.35 + lap + bay), (0.0, 2.3)], "E-ACERO", const_width=db)
VT.dim((0.0, 0.35), (0.0, 0.35 + lap), (-0.12, 0.35), 90, text=f"{lap:.2f}")
VT.dim((0.0, 0.35 + lap), (0.0, 0.35 + lap + bay), (-0.12, 0.35 + lap), 90, text=f"{bay:.2f}")
VT.leader((db, 0.35 + lap + bay / 2), (0.12, 0.35 + lap + bay / 2 + 0.05), "bayoneta 1:6", 2.0, side=1)
VT.leader((db, 0.35 + lap / 2), (0.12, 0.35 + lap / 2), f"traslape clase B {dstr('5/8')}", 2.0, side=1)
VT.text(f"({dstr('1/2')}: 0.60)", (0.12 + 0.05, 0.35 + lap / 2 - 0.06), 1.7, "E-ACERO-TXT", "MIDDLE_LEFT")
VT.text("a media altura libre del piso, estribos @.10 en todo el traslape", (0.0, -0.08), 1.7, "E-TEXTO", "TOP_CENTER")


# ============================================================ DETALLE DE ESTRIBOS Y GRAPAS (1:10)
DETS = []
VE_ = View(doc, 10, (600, 0))
xoff = 0.0
for key in ("C-1", "C-2"):
    for b in sorted(SEC[key]["juego"], key=lambda b: b["rest"][0]):
        pl = np.asarray(b["pl"], float)
        p2 = pl[:, :2] - pl[:, :2].min(0)
        w_, h_ = np.ptp(pl[:, 0]), np.ptp(pl[:, 1])
        pts = [(xoff + x, y) for x, y in p2]
        VE_.pline(pts, "E-ACERO", const_width=0.0095)
        VE_.dim((xoff, 0), (xoff + w_, 0), (xoff, -0.06), 0)
        if h_ > 0.05:
            VE_.dim((xoff + w_, 0), (xoff + w_, h_), (xoff + w_ + 0.06, 0), 90)
        nm = ("GRAPA" if "GRAPA" in b["rest"][0] else "ESTRIBO")
        hook = [x for x in b["segs"] if x]
        VE_.text(f"{key} {nm}", (xoff + w_ / 2, max(h_, 0.02) + 0.07), 2.0, "E-TITULO")
        VE_.text(f"L = {b['L']:.2f}  gancho {hook[-1]:.2f}", (xoff + w_ / 2, max(h_, 0.02) + 0.035), 1.6, "E-ACERO-TXT")
        xoff += w_ + 0.16
        DETS.append(b)
DET_W = xoff

# ============================================================ HOJA
W_, H_ = 841, 594
# secciones
for i, key in enumerate(("C-1", "C-2")):
    d = SEC[key]
    V, win = d["view"], d["win"]
    w = (win[2] - win[0]) * 200 + 75
    h = (win[3] - win[1]) * 200 + 30
    cx = [120, 290][i]
    cy = 575 - h / 2
    add_vp(ps, cx, cy, w, h, V.P((win[0] + win[2]) / 2 + 0.14, (win[1] + win[3]) / 2 - 0.04), 5)
    view_title(ps, cx - 15, cy - h / 2 - 6, f"SECCIÓN {key}", "ESC. 1:5  (corte en zona central)")

# cuadro de columnas
rows = [["TRAMO", "C-1  0.60 x 0.30 (10 + 2 escalera)", "C-2  L 0.60 x 0.60 x 0.30 (4)"]]
for lv0, lv1 in zip(LEVELS[:-1], LEVELS[1:]):
    t1, _ = col_at("N-1-A-2", lv0)
    t2, _ = col_at("N-1-A-1", lv0)
    rows.append([f"{lv0.replace('Cimentacion', 'Cimentación')} - {lv1}", zone_text(t1), zone_text(t2)])
rows.append(["LONGITUDINAL", SEC["C-1"]["txt"], SEC["C-2"]["txt"]])
def juego_txt(key):
    j = SEC[key]["juego"]
    ng = sum(1 for b in j if "GRAPA" in b["rest"][0])
    return f"{len(j) - ng} estribos + {ng} grapa{'s' if ng > 1 else ''} Ø3/8\" por juego"
rows.append(["ESTRIBOS", juego_txt("C-1"), juego_txt("C-2")])
Wt, Ht = table(ps, 30, 330, [40, 112, 112], rows, row_h=6.8, h_txt=2.1, aligns=["L", "L", "L"])
ptext(ps, "CUADRO DE COLUMNAS (medido del modelo)", (30, 332.5), 3.2, "E-TITULO")

# elevaciones
for i, key in enumerate(("C-1", "C-2")):
    d = ELEV[key]
    V, win = d["view"], d["win"]
    w = (win[2] - win[0]) * 25
    h = (win[3] - win[1]) * 25
    cx, cy = 430 + 125 * i, 575 - h / 2
    add_vp(ps, cx, cy, w, h, V.P((win[0] + win[2]) / 2, (win[1] + win[3]) / 2), 40)
    view_title(ps, cx, cy - h / 2 - 6, f"ELEVACIÓN {key} (eje {d['mk']})", "ESC. 1:40")

# detalle de traslape
add_vp(ps, 740, 450, 150, 140, VT.P(0.45, 1.05), 20)
view_title(ps, 740, 373, "DETALLE DE TRASLAPE", "ESC. 1:20")


_wd = DET_W * 100 + 20
add_vp(ps, 32 + _wd / 2, 145, _wd, 95, VE_.P(DET_W / 2 - 0.11, 0.25), 10)
view_title(ps, 32 + _wd / 2, 90, "DETALLE DE ESTRIBOS Y GRAPAS (juego típico, medidas exteriores del modelo)", "ESC. 1:10", w=190)

nts = ["NOTAS - COLUMNAS",
       "1. CONCRETO f'c = 210 kg/cm². ACERO ASTM A615 Gr. 60, fy = 4200 kg/cm².",
       "2. RECUBRIMIENTO libre al estribo 4 cm.",
       "3. Estribos cerrados con ganchos de 135° y extensión 6 db (≥ 7.5 cm); grapas con 135°/90° alternados.",
       "4. Traslapes clase B a media altura libre: Ø5/8\" 0.75 m, Ø1/2\" 0.60 m, con bayoneta 1:6.",
       "5. Arranques: ver E-01 (pata 12 db sobre la parrilla). Remate en el techo: doblez 90° hacia el núcleo.",
       "6. Distribución de estribos tomada de los conjuntos del modelo (zonas CONF / CENTRAL / TRASLAPE).",
       "7. Columnas de escalera (ESQUINA_A2, ESQUINA_A3) armadas como C-1."]
notes(ps, 30, 250, nts, h=2.1)

title_block(ps, "E-03", ["COLUMNAS: SECCIONES, ELEVACIONES", "Y CUADRO DE COLUMNAS"])
save_and_render(doc, ps, "E-03_Columnas")
print("ok", SEC["C-1"]["txt"], "|", SEC["C-2"]["txt"])
for r in rows:
    print(r)
