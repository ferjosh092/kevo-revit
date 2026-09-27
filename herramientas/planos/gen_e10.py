"""Lamina E-10 - PLANILLA DE ACERO, METRADOS, ESPECIFICACIONES GENERALES Y OBSERVACIONES DEL MODELO."""
import re
from sheetcommon import *

M = load_model()
E, B = M["elements"], M["bars"]

ELEM = {"COLUMNAS": "Columnas", "VIGAS": "Vigas", "ZAPATAS": "Zapatas", "LOSAS": "Losas", "ESCALERA": "Escalera"}
ROLE = {
    ("COLUMNAS", "LONG"): "Longitudinal (arranque y pisos)",
    ("COLUMNAS", "ESTRIBO"): "Estribos y grapas",
    ("VIGAS", "SUP"): "Superior corrido",
    ("VIGAS", "INF"): "Inferior corrido",
    ("VIGAS", "ESTRIBOS"): "Estribos",
    ("ZAPATAS", "PARRILLA_CAPA"): "Parrilla inferior (2 capas)",
    ("LOSAS", "VIG_INF"): "Vigueta: inferior corrido",
    ("LOSAS", "VIG_BAS12_"): "Vigueta: bastón sobre apoyo",
    ("LOSAS", "VIG_BAS38_"): "Vigueta: bastón apoyo extremo",
    ("LOSAS", "VIG_VOL"): "Vigueta: volado",
    ("LOSAS", "LAT_SUPL"): "Viguetas laterales: superior (N-4)",
    ("LOSAS", "LAT_SUPR"): "Viguetas laterales: superior (N-1)",
    ("LOSAS", "LAT_INFL"): "Viguetas laterales: inferior (N-4)",
    ("LOSAS", "LAT_INFR"): "Viguetas laterales: inferior (N-1)",
    ("LOSAS", "CHATA_SUPL"): "Viga chata: superior",
    ("LOSAS", "CHATA_SUPR"): "Viga chata: superior",
    ("LOSAS", "CHATA_INFL"): "Viga chata: inferior",
    ("LOSAS", "CHATA_INFR"): "Viga chata: inferior",
    ("LOSAS", "CHATA_ESTL"): "Viga chata: estribos",
    ("LOSAS", "CHATA_ESTR"): "Viga chata: estribos",
    ("LOSAS", "TEMP_U"): "Malla de temperatura dir. X",
    ("LOSAS", "TEMP_V"): "Malla de temperatura dir. Y",
    ("ESCALERA", "L"): "Longitudinal de tramos",
    ("ESCALERA", "T"): "Transversal",
    ("ESCALERA", "S"): "Superior de tramos",
    ("ESCALERA", "MECHA_SUP"): "Mechas del cimiento",
}


def fam(b):
    g = b["grp"].replace("SJ_ACERO_", "").replace("_R1", "")
    r = re.sub(r"\d+$", "", b["role"])
    r = re.sub(r"_\d+$", "", r)
    return g, r


grp = collections.defaultdict(list)
for b in B:
    g, r = fam(b)
    lab = ROLE.get((g, r), r)
    grp[(g, lab, b["d"])].append(b)

order = ["ZAPATAS", "COLUMNAS", "VIGAS", "LOSAS", "ESCALERA"]
rows = [["ELEMENTO", "FUNCIÓN", "Ø", "N° BARRAS", "LONG. UNIT. (m)", "LONG. TOTAL (m)", "PESO (kg)"]]
tot = collections.defaultdict(float)
by_el_d = collections.defaultdict(float)
for key in sorted(grp, key=lambda k: (order.index(k[0]), k[1], -KG[k[2]])):
    g, lab, d = key
    bl = grp[key]
    L = [b["L"] for b in bl]
    Lt = sum(L)
    w = Lt * KG[d]
    tot[d] += w
    by_el_d[(g, d)] += w
    lu = f"{min(L):.2f}" if max(L) - min(L) < 0.005 else f"{min(L):.2f} - {max(L):.2f}"
    rows.append([ELEM[g], lab, dstr(d), str(len(bl)), lu, f"{Lt:,.1f}", f"{w:,.1f}"])

doc = new_doc()
add_layers(doc)
ps = new_sheet(doc, "E-10")

# planilla en dos columnas
half = (len(rows) + 1) // 2
cw = [28, 78, 16, 24, 38, 32, 26]
W1, H1 = table(ps, 30, 572, cw, rows[: half + 1], row_h=7.6, h_txt=2.5, aligns=["L", "L", "C", "C", "C", "C", "C"])
table(ps, 30 + sum(cw) + 14, 572, cw, [rows[0]] + rows[half + 1:], row_h=7.6, h_txt=2.5, aligns=["L", "L", "C", "C", "C", "C", "C"])
ptext(ps, "PLANILLA DE ACERO (medida del modelo IFC: cada barra con su longitud real; pesos nominales kg/m)", (30, 575), 3.6, "E-TITULO")

# resumen por elemento y diametro
ds = sorted({d for (_, d) in by_el_d}, key=lambda d: KG[d])
rs = [["ELEMENTO"] + [dstr(d) for d in ds] + ["TOTAL (kg)"]]
for g in order:
    rr = [ELEM[g]] + [f"{by_el_d.get((g, d), 0):,.1f}" if by_el_d.get((g, d), 0) else "—" for d in ds]
    rr.append(f"{sum(by_el_d.get((g, d), 0) for d in ds):,.1f}")
    rs.append(rr)
rs.append(["TOTAL"] + [f"{tot[d]:,.1f}" for d in ds] + [f"{sum(tot.values()):,.1f}"])
rs.append(["kg/m"] + [f"{KG[d]:.3f}" for d in ds] + [""])
y0 = 575 - H1 - 18
Wr, Hr = table(ps, 30, y0, [40] + [32] * len(ds) + [34], rs, row_h=7.2, h_txt=2.4, aligns=["L"] + ["C"] * (len(ds) + 1))
ptext(ps, "RESUMEN DE ACERO POR ELEMENTO Y DIÁMETRO (kg)", (30, y0 + 2), 3.0, "E-TITULO")

# metrado de concreto
vol = collections.defaultdict(float)
for t, e in E.items():
    ps_ = e["psets"]
    v = ps_.get("Cotas", {}).get("Volumen") or ps_.get("Qto_BuildingElementProxyQuantities", {}).get("NetVolume")
    if v is None:
        continue
    cat = {"zapata": "Zapatas y cimiento de escalera", "columna": "Columnas", "viga": "Vigas (cimentación y entrepiso)",
           "losa": "Losas (modelo macizo h=0.20)", "escalera": "Escalera", "falsopiso": "Falso piso"}.get(e["cat"], e["cat"])
    vol[cat] += v
area_losas = sum(e["psets"].get("Cotas", {}).get("Área", 0) for e in E.values() if e["cat"] == "losa")
rv = [["ELEMENTO", "CONCRETO (m³)"]]
for k in ["Zapatas y cimiento de escalera", "Columnas", "Vigas (cimentación y entrepiso)", "Losas (modelo macizo h=0.20)", "Escalera", "Falso piso"]:
    rv.append([k, f"{vol[k]:.2f}"])
alig = area_losas * (0.05 + 0.15 * 0.10 / 0.40)
rv.append([f"Losa aligerada real (estimado: {area_losas:.1f} m² x 0.0875)", f"{alig:.2f}"])
tot_c = sum(v for k, v in vol.items() if not k.startswith("Losas")) + alig
rv.append(["TOTAL (con losa aligerada)", f"{tot_c:.2f}"])
y1 = y0 - Hr - 16
table(ps, 30, y1, [120, 36], rv, row_h=7.2, h_txt=2.4, aligns=["L", "C"])
ptext(ps, "METRADO DE CONCRETO (volúmenes del modelo)", (30, y1 + 2), 3.0, "E-TITULO")
ptext(ps, f"Cuantía global: {sum(tot.values()) / tot_c:.0f} kg de acero por m³ de concreto (con losa aligerada).", (30, y1 - 7.2 * len(rv) - 5), 2.3)
# acero por nivel
def lvl_of(b):
    el = E.get(b["host"])
    if el is None:
        return "?"
    if el["cat"] == "zapata":
        return "Cimentacion"
    if el["cat"] == "escalera":
        m_ = re.search(r"\|N(\d)-N(\d)\|", el["com"])
        return f"Nivel {m_.group(1)}" if m_ else (el["level"] or "?")
    return el["level"] or "?"
pl_ = collections.defaultdict(float)
for b in B:
    pl_[(lvl_of(b), fam(b)[0])] += b["L"] * KG[b["d"]]
LVS = ["Cimentacion", "Nivel 1", "Nivel 2", "Nivel 3", "Nivel 4", "Nivel 5"]
rl = [["NIVEL (tramo que nace en él)"] + [ELEM[g] for g in order] + ["TOTAL"]]
for l in LVS:
    vals = [pl_.get((l, g), 0) for g in order]
    rl.append([l.replace("Cimentacion", "Cimentación")] + [f"{v:,.1f}" if v else "—" for v in vals] + [f"{sum(vals):,.1f}"])
y2 = y0
table(ps, 300, y2, [52, 26, 26, 26, 26, 26, 28], rl, row_h=7.2, h_txt=2.4, aligns=["L"] + ["C"] * 6)
ptext(ps, "ACERO POR NIVEL Y ELEMENTO (kg)", (300, y2 + 2), 3.0, "E-TITULO")
ptext(ps, "Columnas y escalera se asignan al nivel donde nacen; vigas y losas al nivel que soportan.", (300, y2 - 7.2 * len(rl) - 5), 2.1)

# especificaciones generales
esp = ["ESPECIFICACIONES TÉCNICAS GENERALES",
       "1. NORMAS: E.020 Cargas, E.030 Diseño Sismorresistente, E.050 Suelos y Cimentaciones, E.060 Concreto Armado.",
       "2. CONCRETO: f'c = 210 kg/cm² en columnas, vigas, zapatas, losas y escalera; f'c = 175 kg/cm² en falso piso;",
       "    f'c = 100 kg/cm² en solados.",
       "3. ACERO: corrugado ASTM A615 Grado 60, fy = 4200 kg/cm².",
       "4. RECUBRIMIENTOS LIBRES: zapatas 7.5 cm; vigas y columnas 4 cm; losas y escalera 2 cm (medido 2.5 cm).",
       "5. SUELO: qadm = 1.22 - 1.31 kg/cm² a Df = 2.00 m (EMS). Cimiento de escalera a -1.00 m: confirmar.",
       "6. SOBRECARGAS (nodo 14): piso terminado 100, tabiquería equivalente 210, s/c 200 kg/m².",
       "7. GANCHOS: estándar 90° (12 db) en anclajes; estribos y grapas 135° con extensión 6 db ≥ 7.5 cm.",
       "8. TRASLAPES clase B: Ø3/4\" sup. 1.15 / inf. 0.90; Ø5/8\" 0.75; Ø1/2\" 0.60 m. Fuera de nudos y zonas de confinamiento.",
       "9. Cotas en metros. Niveles: NFZ -2.00, N1 ±0.00, N2 +3.20, N3 +5.80, N4 +8.40, N5 +11.00.",
       "10. Láminas generadas del modelo IFC 'Proyect sj.ifc' (Revit 2027); cantidades según el modelo."]
yE = notes(ps, 30, 175, esp, h=2.3, lead=4.8, title_h=2.8)

obs = ["OBSERVACIONES DEL MODELO (revisión automática del IFC)",
       "A. VIGAS: el nodo 12 desplazó capas de acero longitudinal hacia el interior para evitar choques: 1ra capa",
       "   2-3.5 cm; capas siguientes hasta 25 cm (sup. de vigas de entrepiso a media altura). En E-01 y E-08 se",
       "   dibujan en su posición de diseño. Corregir el nodo 12 (no desplazar la capa entera; resolver cruces en el nudo).",
       "B. LOSAS: modeladas macizas (casetones no modelados). Viguetas paralelas a los ejes N (el docstring del",
       "   nodo 14 dice ejes A). Malla Ø1/4\" a la misma cota que bastones: ~5 mm de interferencia en cruces.",
       "C. VIGA CHATA: barras superiores 3.3 cm bajo la esquina del estribo; una barra cruza la rama del estribo.",
       "D. LÍMITE DE PROPIEDAD: zapatas y columnas del eje N-4 lo sobrepasan hasta 0.60 m (verificar levantamiento).",
       "E. Revit exporta el peso del acero en 0: los pesos de esta lámina se calculan con longitudes y kg/m nominales."]
notes(ps, 300, 175, obs, h=2.3, lead=4.6, title_h=2.8)

title_block(ps, "E-10", ["PLANILLA DE ACERO, METRADOS,", "ESPECIFICACIONES Y OBSERVACIONES"])
save_and_render(doc, ps, "E-10_Planilla_Acero")
print("ok", len(rows) - 1, "filas", {d: round(w, 1) for d, w in tot.items()}, round(sum(tot.values()), 1), round(tot_c, 2))
