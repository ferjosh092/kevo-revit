"""Lamina E-02 - PLANTA DE COLUMNAS (REPLANTEO) Y CORTES GENERALES."""
from sheetcommon import *

M = load_model()
E, GU, GV, LZ = M["elements"], M["GU"], M["GV"], M["levels"]
cols = [e for e in E.values() if e["cat"] == "columna" and e["level"] == "Nivel 1"]
for c in cols:
    c["fp"] = footprint(c)
    c["mk"] = c["com"].split("|")[1]
    c["CT"] = "C-2" if c["tipo"].startswith("L_") else "C-1"

doc = new_doc()
add_layers(doc)
ps = new_sheet(doc, "E-02")

# ============================================================ PLANTA 1:50
PL = View(doc, 50, (0, 0))
m = PL.m
for k, u in GU.items():
    PL.line((u, -1.35), (u, 11.35), "E-EJES", linetype=PL.lt("EJE"))
    PL.grid_bubble((u, 11.35 + 5 * m), k)
    PL.grid_bubble((u, -1.35 - 5 * m), k)
for k, vv in GV.items():
    PL.line((-1.35, vv), (11.35, vv), "E-EJES", linetype=PL.lt("EJE"))
    PL.grid_bubble((-1.35 - 5 * m, vv), k)
    PL.grid_bubble((11.35 + 5 * m, vv), k)
for seg in M["property"]:
    PL.pline(seg, "E-LIMITE", linetype=PL.lt("LIMITE"))
# losa de Nivel 2 como referencia (proyeccion)
losa = [e for e in E.values() if e["cat"] == "losa" and e["level"] == "Nivel 2"][0]
PL.pline(list(footprint(losa).exterior.coords), "E-PROYECCION", linetype=PL.lt("OCULTA"))
PL.text("contorno de losa N2 (proyección)", (4.8, 11.0), 1.6, "E-TEXTO")
for c in cols:
    pts = list(c["fp"].exterior.coords)[:-1]
    PL.hatch(pts, "E-COLUMNA-ACH")
    PL.pline(pts, "E-COLUMNA", close=True)
# cotas generales
U0, U1 = min(c["fp"].bounds[0] for c in cols), max(c["fp"].bounds[2] for c in cols)
V0, V1 = min(c["fp"].bounds[1] for c in cols), max(c["fp"].bounds[3] for c in cols)
us = [U0] + sorted(GU.values()) + [U1]
PL.hdim_chain(us, V1, 10.75)
PL.dim((U0, V1), (U1, V1), (U0, 11.05), 0)
vs = [V0] + sorted(GV.values()) + [V1]
PL.vdim_chain(vs, U0, -1.05, texts=[(f"{b_ - a_:.3f}" if abs(round((b_ - a_) * 100) - (b_ - a_) * 100) > 0.01 else f"{b_ - a_:.2f}") for a_, b_ in zip(vs, vs[1:])])
PL.dim((U0, V0), (U0, V1), (-1.35, V0), 90, dec=3)
# replanteo: cada columna acotada a sus ejes (en X abajo, en Y a la derecha) + rotulo
for c in cols:
    x0, y0, x1, y1 = c["fp"].bounds
    ua = GU["A-" + c["mk"].split("-A-")[1]] if "-A-" in c["mk"] else None
    na = c["mk"].split("-A-")[0] if "-A-" in c["mk"] else None
    if ua is None:
        # columnas de escalera: eje mas cercano
        ua = min(GU.values(), key=lambda u: abs(u - (x0 + x1) / 2))
        va = min(GV.values(), key=lambda v: abs(v - (y0 + y1) / 2))
    else:
        va = GV[na]
    c["rep"] = (ua, va, x0, x1, y0, y1)
    c["eje"] = (min(GU, key=lambda k: abs(GU[k] - ua)), min(GV, key=lambda k: abs(GV[k] - va)))
    PL.text(f'{c["CT"]}', (x0 - 0.05, y1 + 0.06), 2.2, "E-TITULO", "BOTTOM_RIGHT")

# ============================================================ CORTES GENERALES 1:100
def general_section(axis, val, offset, lo, hi):
    V = View(doc, 100, offset)
    win = (lo, -2.25, hi, 12.0)
    cut_elements(V, E, axis, val, win, cats=("zapata", "columna", "viga", "losa", "falsopiso", "escalera"))
    tags = sorted(GU if axis == 1 else GV, key=lambda t: (GU if axis == 1 else GV)[t])
    for tg in tags:
        p = (GU if axis == 1 else GV)[tg]
        V.line((p, -2.4), (p, 11.9), "E-EJES", linetype=V.lt("EJE"))
        V.grid_bubble((p, -2.4 - 4 * V.m), tg, 4)
    zs = [LZ[l] for l in ("Cimentacion", "Nivel 1", "Nivel 2", "Nivel 3", "Nivel 4", "Nivel 5")]
    V.vdim_chain(zs, hi - 0.4, hi - 0.4 + 6 * V.m)
    for l, z in LZ.items():
        lab = ("NFZ " if l == "Cimentacion" else "NPT ") + (f"{z:+.2f}" if z else "±0.00")
        V.level(lo + 1.3, z, lab + ("" if l == "Cimentacion" else "  " + l.upper()), left=True)
    return V, win


SN, winN = general_section(1, GV["N-2"], (200, 0), -2.1, 11.9)
SA, winA = general_section(0, GU["A-2"], (230, 0), -2.1, 11.7)

# ============================================================ HOJA
add_vp(ps, 25 + 8 + 150, 594 - 14 - 150, 300, 300, (5.0, 5.2), 50)
view_title(ps, 183, 594 - 14 - 300 - 8, "PLANTA DE COLUMNAS Y REPLANTEO (N1 a N5)", "ESC. 1:50", w=160)
for i, (V, win, t) in enumerate(((SN, winN, "CORTE GENERAL EJE N-2"), (SA, winA, "CORTE GENERAL EJE A-2"))):
    w = (win[2] - win[0]) * 10 + 6
    h = (win[3] - win[1]) * 10 + 14
    cx = 440 + i * 170
    cy = 580 - h / 2
    add_vp(ps, cx, cy, w, h, V.P((win[0] + win[2]) / 2, (win[1] + win[3]) / 2 - 0.45), 100)
    view_title(ps, cx, cy - h / 2 - 5, t, "ESC. 1:100")

# cuadro de columnas por tipo y ubicacion
rows = [["TIPO", "SECCIÓN", "CANT./NIVEL", "UBICACIÓN"]]
for ct, sec in (("C-1", "0.60 x 0.30 (0.30 x 0.60 girada)"), ("C-2", "L 0.60 x 0.60, alas 0.30")):
    cc = [c for c in cols if c["CT"] == ct]
    rows.append([ct, sec, str(len(cc)), ", ".join(sorted(c["mk"].replace("-A-", "/A-") for c in cc))[:95]])
table(ps, 30, 250, [14, 52, 22, 175], rows, row_h=6.5, h_txt=2.0, aligns=["C", "L", "C", "L"])
ptext(ps, "CUADRO DE COLUMNAS POR TIPO (armado: ver E-03)", (30, 252), 3.0, "E-TITULO")
rows2 = [["NIVEL", "COTA (m)", "ALTURA ENTREPISO (m)"]]
names = ["Cimentacion", "Nivel 1", "Nivel 2", "Nivel 3", "Nivel 4", "Nivel 5"]
for i, l in enumerate(names):
    rows2.append([l.replace("Cimentacion", "Fondo de cimentación"), f"{LZ[l]:+.2f}", f"{LZ[names[i + 1]] - LZ[l]:.2f}" if i + 1 < len(names) else "—"])
table(ps, 30, 205, [45, 25, 40], rows2, row_h=6.0, h_txt=2.0)
ptext(ps, "CUADRO DE NIVELES", (30, 207), 3.0, "E-TITULO")
rr = [["COLUMNA", "TIPO", "EJES", "IZQ. (-X)", "DER. (+X)", "ABAJO (-Y)", "ARRIBA (+Y)"]]
for c in sorted(cols, key=lambda c: (-c["rep"][1], c["rep"][0])):
    ua, va, x0, x1, y0, y1 = c["rep"]
    rr.append([c["mk"].replace("-A-", "/A-"), c["CT"], f'{c["eje"][0]} / {c["eje"][1]}',
               f"{ua - x0:.2f}", f"{x1 - ua:.2f}", f"{va - y0:.2f}", f"{y1 - va:.2f}"])
table(ps, 400, 322, [30, 14, 26, 20, 20, 20, 20], rr, row_h=6.0, h_txt=2.0)
ptext(ps, "CUADRO DE REPLANTEO: distancia de cada cara al eje (m)", (400, 324), 3.0, "E-TITULO")
ptext(ps, "X a lo largo de los ejes N (hacia A-3); Y a lo largo de los ejes A (hacia N-1).", (400, 322 - 6.0 * len(rr) - 4), 1.9)
nts = ["NOTAS",
       "1. Replanteo según cuadro (caras de cada columna a sus ejes, en metros). Columnas iguales en todos los niveles.",
       "2. Ejes según modelo: el orden en planta es A-1, A-4, A-2, A-3 (no correlativo).",
       "3. Columnas de escalera (eje N-4) sobre zapatas Z-1: ver E-01 y E-09.",
       "4. Límite de propiedad según modelo; las zapatas y columnas de N-4 lo sobrepasan: verificar con el levantamiento."]
notes(ps, 180, 205, nts, h=2.0, lead=4.2)
title_block(ps, "E-02", ["PLANTA DE COLUMNAS (REPLANTEO)", "Y CORTES GENERALES"])
save_and_render(doc, ps, "E-02_Columnas_Replanteo")
print("ok")
