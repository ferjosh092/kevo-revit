"""Lamina E-08 - VIGAS DE ENTREPISO: elevaciones tipicas por eje, secciones tipo y cuadro de vigas."""
from sheetcommon import *
from beamdesign import runs, line_of
from details import beam_section

M = load_model()
E, B, GU, GV, LZ = M["elements"], M["bars"], M["GU"], M["GV"], M["levels"]
R = runs(M)
bh = collections.defaultdict(list)
for b in B:
    bh[b["host"]].append(b)
LV = ["Nivel 2", "Nivel 3", "Nivel 4", "Nivel 5"]
cols = [e for e in E.values() if e["cat"] == "columna"]


def run_tags(lvl, ln):
    for (l, n, t), tags in R.items():
        if l == lvl and n == ln:
            return tags
    return []


def nsup(lvl, ln):
    tags = run_tags(lvl, ln)
    return len({b["rest"][1] for t in tags for b in bh[t] if b["role"] == "SUP"}), \
        len({b["rest"][1] for t in tags for b in bh[t] if b["role"] == "INF"})


def rle(vals):
    out = []
    for g in vals:
        g = round(g, 2)
        if out and abs(out[-1][1] - g) < 0.011:
            out[-1][0] += 1
        else:
            out.append([1, g])
    return out


def elevation(lvl, ln, offset, k=50):
    horiz = ln.startswith("N")
    axis = 1 if horiz else 0          # plano v=cte (ejes N) o u=cte (ejes A)
    other = 0 if horiz else 1
    val = GV[ln] if horiz else GU[ln]
    tags = run_tags(lvl, ln)
    V = View(doc, k, offset)
    zt = LZ[lvl]
    lo = min(E[t]["bbox"][0][other] for t in tags) - 0.55
    hi = max(E[t]["bbox"][1][other] for t in tags) + 0.55
    win = (lo, zt - 1.25, hi, zt + 0.55)
    cut_elements(V, E, axis, val, win, cats=("columna", "viga", "losa"))
    bl = [b for t in tags for b in bh[t]]
    draw_bars_section(V, bl, axis, val, win, par_tol=0.2)
    # ejes
    tagsA = sorted({t for t in (GU if horiz else GV)}, key=lambda t: (GU if horiz else GV)[t])
    for tg in tagsA:
        p = (GU if horiz else GV)[tg]
        if lo < p < hi:
            V.line((p, zt - 1.45), (p, zt + 0.45), "E-EJES", linetype=V.lt("EJE"))
            V.grid_bubble((p, zt - 1.45 - 4 * V.m), tg, 4)
    # caras de columnas sobre el eje, al nivel de la viga
    line = LineString([(lo, val), (hi, val)]) if horiz else LineString([(val, lo), (val, hi)])
    faces = []
    for c in cols:
        if not (c["bbox"][0][2] < zt - 0.3 < c["bbox"][1][2]):
            continue
        cp = footprint(c)
        if cp.intersects(line):
            q = np.array(cp.intersection(line).coords)[:, other]
            faces.append((q.min(), q.max()))
    faces.sort()
    zb = zt - 0.50
    # luces libres y volados (abajo)
    bmin = min(E[t]["bbox"][0][other] for t in tags)
    bmax = max(E[t]["bbox"][1][other] for t in tags)
    xs = []
    if bmin < faces[0][0] - 0.05:
        xs.append(bmin)
    for f in faces:
        xs += [f[0], f[1]]
    if bmax > faces[-1][1] + 0.05:
        xs.append(bmax)
    V.hdim_chain(xs, zb, zb - 5 * V.m)
    # zonas de estribos por tramo (arriba) medidas del modelo
    ztop = zt
    for t in tags:
        pos = sorted(float(np.asarray(x["pl"])[:, other].mean()) for x in bh[t] if x["role"] == "ESTRIBOS")
        if len(pos) < 3:
            continue
        f0 = max([f[1] for f in faces if f[1] <= pos[0] + 0.01], default=None)
        f1 = min([f[0] for f in faces if f[0] >= pos[-1] - 0.01], default=None)
        g = np.diff(pos)
        mid = max(round(x, 2) for x in g)
        dense = [x for x in g if x < mid - 0.011]
        if f0 is None or f1 is None:        # voladizo: estribado uniforme
            e0 = f0 if f0 is not None else pos[0]
            e1 = f1 if f1 is not None else pos[-1]
            V.hdim_chain([min(e0, e1), max(e0, e1)], ztop, ztop + 6 * V.m, texts=[f"@{min(g):.2f}".replace("0.", ".")])
            continue
        i0 = next((i for i, x in enumerate(g) if x > mid - 0.011), 0)
        i1 = len(g) - 1 - next((i for i, x in enumerate(g[::-1]) if x > mid - 0.011), 0)
        a, bnd = pos[i0], pos[i1 + 1]
        V.hdim_chain([f0, a, bnd, f1], ztop, ztop + 6 * V.m,
                     texts=[f"{a - f0:.2f}", f"@{mid:.2f}".replace("0.", "."), f"{f1 - bnd:.2f}"])
    # traslapes medidos
    grp = collections.defaultdict(dict)
    for x in bl:
        if x["role"] in ("SUP", "INF") and len(x["rest"]) >= 3 and x["rest"][2].startswith("PZA"):
            pl = np.asarray(x["pl"], float)
            grp[(x["role"], x["rest"][1])][x["rest"][2]] = (pl[:, other].min(), pl[:, other].max())
    seen = set()
    for (role, bi), d in grp.items():
        if "PZA_A" in d and "PZA_B" in d:
            o0, o1 = max(d["PZA_A"][0], d["PZA_B"][0]), min(d["PZA_A"][1], d["PZA_B"][1])
            key = (role, round(o0, 1), round(o1, 1))
            if o1 - o0 < 0.1 or key in seen:
                continue
            seen.add(key)
            if role == "SUP":
                V.dim((o0, zt - 0.06), (o1, zt - 0.06), (o0, zt + 2.3 * V.m), 0, text=f"trasl. {o1 - o0:.2f}")
            else:
                V.dim((o0, zb + 0.06), (o1, zb + 0.06), (o0, zb - 11 * V.m), 0, text=f"trasl. {o1 - o0:.2f}")
    return V, win


doc = new_doc()
add_layers(doc)
ps = new_sheet(doc, "E-08")

LINES_L = ["N-1", "N-2", "N-3"]
LINES_R = ["A-1", "A-4", "A-2", "A-3"]
ELV = {}
for i, ln in enumerate(LINES_L + LINES_R):
    ELV[ln] = elevation("Nivel 2", ln, (100 + 20 * i, 0), k=40)
# collarin
coll = run_tags("Nivel 2", "COLL-Nivel 2")

# ------------------------------------------------------------ secciones tipo (1:10)
TYPES = {}
for ln in LINES_L + LINES_R:
    for lvl in LV:
        ns, ni = nsup(lvl, ln)
        TYPES.setdefault((ns, ni), []).append((ln, lvl))
tnames = {}
for i, (ns, ni) in enumerate(sorted(TYPES)):
    tnames[(ns, ni)] = f"VE-{ns}"
SECV = {}
for i, key in enumerate(sorted(TYPES)):
    V = View(doc, 10, (400 + 3 * i, 0))
    beam_section(V, 0.30, 0.50, key[0], key[1], "3/4", "3/8", lab_side=1, label_h=2.0)
    SECV[key] = V
Vc = View(doc, 10, (430, 0))
nsc = len({b["rest"][1] for t in coll for b in bh[t] if b["role"] == "SUP"})
nic = len({b["rest"][1] for t in coll for b in bh[t] if b["role"] == "INF"})
beam_section(Vc, 0.30, 0.50, nsc, nic, "5/8", "3/8", lab_side=1, label_h=2.0)

# distribucion de estribos tipica (del modelo, tramo interior del eje N-2)
t_rep = sorted(run_tags("Nivel 2", "N-2"), key=lambda t: E[t]["bbox"][0][0])[1]
pos = sorted(float(np.asarray(x["pl"])[:, 0].mean()) for x in bh[t_rep] if x["role"] == "ESTRIBOS")
g = np.diff(pos)
mid = max(round(x, 2) for x in g)
dense = rle([x for x in g[: len(g) // 2] if x < mid - 0.011])
dist_txt = "1@.05, " + ", ".join(f"{n}@{s:.2f}".replace("0.", ".") for n, s in dense) + f", rto. @{mid:.2f} c/ext.".replace("0.", ".")
pc = sorted(float(np.asarray(x["pl"])[:, 0].mean()) for t in coll for x in bh[t] if x["role"] == "ESTRIBOS")
gc = round(float(np.median(np.diff(pc))), 2)

# ============================================================ HOJA
def place_elev(ln, x0, ytop, width):
    V, win = ELV[ln]
    w = (win[2] - win[0]) * 25
    h = (win[3] - win[1]) * 25 + 26
    cx = x0 + width / 2
    cy = ytop - h / 2
    add_vp(ps, cx, cy, w, h, V.P((win[0] + win[2]) / 2, (win[1] + win[3]) / 2 - 0.18), 40)
    sup = "/".join(str(nsup(l, ln)[0]) for l in LV)
    view_title(ps, cx, cy - h / 2 - 3, f"VIGA EJE {ln}  (N2 a N5: sup. {sup} Ø3/4\", inf. 4 Ø3/4\")", "ESC. 1:40  - típica en todos los niveles; ver cuadro", w=150)
    return cy - h / 2 - 13


y = 580
for ln in LINES_L:
    y = place_elev(ln, 30, y, 380)
yl_end = y
y = 580
for ln in LINES_R:
    y = place_elev(ln, 420, y, 405)

# secciones
xs0 = 30
ys = 175
for i, key in enumerate(sorted(TYPES)):
    V = SECV[key]
    cx = xs0 + 40 + i * 78
    add_vp(ps, cx + 14, ys, 76, 78, V.P(0.36, 0.22), 10)
    view_title(ps, cx, ys - 44, f"{tnames[key]}  0.30 x 0.50", "ESC. 1:10")
cx = xs0 + 40 + len(TYPES) * 78
add_vp(ps, cx + 14, ys, 76, 78, Vc.P(0.36, 0.22), 10)
view_title(ps, cx, ys - 44, "COLLARÍN VCO 0.30 x 0.50", "ESC. 1:10")
ptext(ps, f'Estribos VE {dstr("3/8")}: {dist_txt} (medido del modelo)', (30, 115), 2.2)
ptext(ps, f'Estribos collarín {dstr("3/8")}: @ {gc:.2f}'.replace("0.", ".") + "  —  Acero de vigas dibujado en su posición de diseño (E.060): ver nota 5.", (30, 110), 2.2)

# cuadro de vigas
rows = [["EJE"] + [l.upper() for l in LV]]
for ln in LINES_L + LINES_R:
    rows.append([ln] + [tnames[nsup(l, ln)] for l in LV])
rows.append(["COLLARÍN (N-4)"] + ["VCO"] * 4)
Wt, Ht = table(ps, 40, yl_end - 8, [34, 24, 24, 24, 24], rows, row_h=6.0, h_txt=2.1)
ptext(ps, "CUADRO DE VIGAS POR NIVEL", (40, yl_end - 6), 3.0, "E-TITULO")

nts = ["NOTAS - VIGAS",
       "1. CONCRETO f'c = ____ kg/cm² (COMPLETAR). ACERO ASTM A615 Gr. 60, fy = 4200 kg/cm².",
       "2. RECUBRIMIENTO libre al estribo 4 cm. Estribos cerrados con gancho 135°.",
       "3. Barras corridas por eje; gancho estándar 90° en columnas extremas y en el extremo del volado.",
       "4. Traslapes fuera de nudos: sup. 1.15 m al centro del vano, inf. 0.90 m a 2h de la cara, alternados.",
       "5. En el modelo Revit (nodo 12) varias capas quedaron desplazadas hasta 25 cm hacia el interior",
       "   para evitar choques. Aquí se dibujan en su posición de diseño; corregir el modelo antes del metrado fino.",
       "6. En los nudos, las barras de los ejes A pasan por dentro de las de los ejes N."]
notes(ps, 185, yl_end - 8, nts, h=2.0, lead=4.1)

title_block(ps, "E-08", ["VIGAS DE ENTREPISO: ELEVACIONES,", "SECCIONES TIPO Y CUADRO DE VIGAS"])
save_and_render(doc, ps, "E-08_Vigas")
print("ok", {tnames[k]: v[:2] for k, v in TYPES.items()}, dist_txt, gc)
