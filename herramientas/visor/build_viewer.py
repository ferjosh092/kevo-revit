"""Genera los datos del visor BIM web (viewer/model.json + viewer/model.bin) a partir de model_all.pkl.

Coordenadas del visor (three.js, Y arriba): x = u, y = z, z = -v   (metros; en el binario en mm Int16).

model.bin (little-endian, cada bloque alineado a 4 bytes; offsets/longitudes en model.json["bin"]):
  ev   Int16  vertices de concreto (x,y,z mm), todos los elementos concatenados
  ei   Uint16 indices de triangulos locales a cada elemento
  bp   Int16  puntos de las polilineas del acero (x,y,z mm)
  bo   Uint32 offset (en puntos) de inicio de cada barra, n_barras+1
  bh   Uint16 indice del elemento anfitrion de cada barra
  bd   Uint8  indice de diametro de cada barra
  bg   Uint8  indice de grupo de cada barra
"""
import json, re, math, collections, os
import numpy as np
from sheetcommon import load_model

OUT = "viewer"
KG = {"1/4": 0.250, "3/8": 0.560, "1/2": 0.994, "5/8": 1.552, "3/4": 2.235}
DIAMS = ["1/4", "3/8", "1/2", "5/8", "3/4"]
GROUPS = [  # (clave Dynamo, clave corta, etiqueta)
    ("SJ_ACERO_COLUMNAS_R1", "col", "Columnas"),
    ("SJ_ACERO_VIGAS_R1", "vig", "Vigas"),
    ("SJ_ACERO_ZAPATAS_R1", "zap", "Zapatas"),
    ("SJ_ACERO_LOSAS_R1", "los", "Losas"),
    ("SJ_ACERO_ESCALERA_R1", "esc", "Escalera"),
]
CATS = [  # clave, etiqueta, plural
    ("zapata", "Zapata", "Zapatas"),
    ("columna", "Columna", "Columnas"),
    ("viga", "Viga", "Vigas"),
    ("losa", "Losa", "Losas"),
    ("escalera", "Escalera", "Escalera"),
    ("falsopiso", "Falso piso", "Falso piso"),
]
LEVELS = [("CIM", "Cimentacion", "Cimentación"), ("N1", "Nivel 1", "Nivel 1"), ("N2", "Nivel 2", "Nivel 2"),
          ("N3", "Nivel 3", "Nivel 3"), ("N4", "Nivel 4", "Nivel 4"), ("N5", "Nivel 5", "Nivel 5")]
LV_BY_NAME = {n: i for i, (_, n, _) in enumerate(LEVELS)}


def to3(p):
    p = np.asarray(p, dtype=float)
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1)


def q16(p):
    a = np.round(p * 1000.0)
    assert a.min() > -32768 and a.max() < 32767
    return a.astype("<i2")


def mesh_volume(v, f):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0))


def fmt(val):
    if isinstance(val, bool):
        return "Sí" if val else "No"
    if isinstance(val, (float, np.floating)):
        x = float(val)
        if abs(x) < 5e-7:
            x = 0.0
        return f"{x:.3f}".rstrip("0").rstrip(".") if abs(x) < 1e4 else f"{x:.0f}"
    if isinstance(val, (int, np.integer)):
        return str(int(val))
    return str(val)


def level_group(e):
    if e["cat"] == "zapata" or e["level"] == "Cimentacion":
        return 0
    if e["level"] in LV_BY_NAME:
        return LV_BY_NAME[e["level"]]
    m = re.search(r"\|N(\d)-N\d\|", e["com"] or "")
    if m:
        return int(m.group(1))
    z = e["bbox"][0][2]
    return max(i for i, (_, n, _) in enumerate(LEVELS) if i == 0 or M["levels"][n] <= z + 0.3)


M = load_model()
E = M["elements"]
B = M["bars"]
tags = list(E.keys())
tag_idx = {t: i for i, t in enumerate(tags)}

# ------------------------------------------------------------------ acero por anfitrion
steel = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0.0]))  # host -> d -> [n, L, kg]
roles = collections.defaultdict(collections.Counter)
grp_kg = collections.defaultdict(float)
grp_d_kg = collections.defaultdict(lambda: collections.defaultdict(float))
grp_n = collections.Counter()
lvl_kg = collections.defaultdict(float)
for b in B:
    w = b["L"] * KG[b["d"]]
    s = steel[b["host"]][b["d"]]
    s[0] += 1; s[1] += b["L"]; s[2] += w
    roles[b["host"]][b["role"]] += 1
    grp_kg[b["grp"]] += w
    grp_d_kg[b["grp"]][b["d"]] += w
    grp_n[b["grp"]] += 1

# ------------------------------------------------------------------ elementos
ev, ei, els = [], [], []
voff = ioff = 0
cat_vol = collections.defaultdict(float)
cat_n = collections.Counter()
lvl_vol = collections.defaultdict(float)
for t in tags:
    e = E[t]
    v = np.asarray(e["v"], float)
    f = np.asarray(e["f"], np.int64)
    V3 = to3(v)
    ev.append(q16(V3))
    ei.append(f.astype("<u2"))
    vol = mesh_volume(v, f)
    lg = level_group(e)
    ps = e["psets"] or {}
    cot = ps.get("Cotas", {})
    pvol = cot.get("Volumen") or ps.get("Qto_BuildingElementProxyQuantities", {}).get("NetVolume")
    volume = float(pvol) if pvol else vol
    cat_vol[e["cat"]] += volume
    cat_n[e["cat"]] += 1
    lvl_vol[lg] += volume
    com = (e["com"] or "").split("|")
    bb0, bb1 = np.array(e["bbox"][0]), np.array(e["bbox"][1])
    dims = bb1 - bb0
    # resumen de cotas
    q = []
    if "b" in cot: q.append(["b", f'{cot["b"]:.2f} m'])
    if "h" in cot: q.append(["h", f'{cot["h"]:.2f} m'])
    if "Anchura" in cot: q.append(["Ancho", f'{cot["Anchura"]:.2f} m'])
    if "Longitud" in cot: q.append(["Largo", f'{cot["Longitud"]:.2f} m'])
    if "Grosor de cimentación" in cot: q.append(["Peralte", f'{cot["Grosor de cimentación"]:.2f} m'])
    if "Grosor" in cot: q.append(["Espesor", f'{cot["Grosor"]:.2f} m'])
    if "Longitud del sistema" in cot: q.append(["Longitud", f'{cot["Longitud del sistema"]:.2f} m'])
    if "Longitud de corte" in cot: q.append(["Long. de corte", f'{cot["Longitud de corte"]:.2f} m'])
    if "Área" in cot: q.append(["Área", f'{cot["Área"]:.2f} m²'])
    if "Elevación en parte inferior" in cot: q.append(["Elev. inferior", f'{cot["Elevación en parte inferior"]:+.2f} m'])
    if "Elevación en parte superior" in cot: q.append(["Elev. superior", f'{cot["Elevación en parte superior"]:+.2f} m'])
    if e["cat"] == "columna":
        r = ps.get("Restricciones", {})
        if r.get("Nivel base"): q.append(["Nivel base", r["Nivel base"]])
        if r.get("Nivel superior"): q.append(["Nivel superior", r["Nivel superior"]])
    if not q or e["cat"] == "escalera":
        q.append(["Caja (u×v×z)", f"{dims[0]:.2f} × {dims[1]:.2f} × {dims[2]:.2f} m"])
    q.append(["Volumen", f"{volume:.3f} m³"])
    mat = ps.get("Materiales y acabados", {}).get("Material estructural")
    if mat: q.append(["Material", mat])
    rec = ps.get("Estructura", {})
    rc = rec.get("Recubrimiento de armadura - Otras caras") or rec.get("Recubrimiento de armadura")
    if rc:
        m = re.search(r"<(.+?)>", rc)
        q.append(["Recubrimiento", m.group(1) if m else rc])

    st = steel.get(t, {})
    sd = [[d, st[d][0], round(st[d][1], 2), round(st[d][2], 2)] for d in DIAMS if d in st]
    psets = {s: [[k, fmt(v_)] for k, v_ in d.items()] for s, d in ps.items() if d}
    els.append({
        "t": t, "c": e["cat"], "ty": e["tipo"] or "", "com": e["com"] or "", "cls": e["cls"], "g": e.get("guid", ""),
        "lv": e["level"] or LEVELS[lg][1], "lg": lg,
        "mk": com[0] if com else "", "loc": com[1] if len(com) > 1 else "", "role": "|".join(com[2:]),
        "vo": voff, "vn": len(v), "io": ioff, "in": len(f) * 3,
        "bb": [round(float(x), 3) for x in list(to3(bb0[None])[0]) + list(to3(bb1[None])[0])],
        "vol": round(volume, 4), "q": q, "st": sd, "rl": sorted(roles[t].items(), key=lambda x: -x[1]), "ps": psets,
    })
    voff += len(v); ioff += len(f) * 3

# ------------------------------------------------------------------ acero
bp, bo, bh, bd, bg = [], [0], [], [], []
gidx = {g: i for i, (g, _, _) in enumerate(GROUPS)}
npts = 0
for b in B:
    pl = to3(b["pl"])
    bp.append(q16(pl))
    npts += len(pl)
    bo.append(npts)
    bh.append(tag_idx[b["host"]])
    bd.append(DIAMS.index(b["d"]))
    bg.append(gidx[b["grp"]])
    lvl_kg[els[tag_idx[b["host"]]]["lg"]] += b["L"] * KG[b["d"]]

blocks = [
    ("ev", np.concatenate(ev).ravel()), ("ei", np.concatenate(ei).ravel()),
    ("bp", np.concatenate(bp).ravel()), ("bo", np.asarray(bo, "<u4")),
    ("bh", np.asarray(bh, "<u2")), ("bd", np.asarray(bd, "u1")), ("bg", np.asarray(bg, "u1")),
]
os.makedirs(OUT, exist_ok=True)
binmeta = {}
buf = bytearray()
for name, arr in blocks:
    while len(buf) % 4:
        buf.append(0)
    binmeta[name] = [len(buf), int(arr.size), arr.dtype.str]
    buf += arr.tobytes()
open(f"{OUT}/model.bin", "wb").write(buf)

# ------------------------------------------------------------------ cantidades
tot_vol = sum(cat_vol.values())
tot_kg = sum(grp_kg.values())
d_tot = collections.defaultdict(float)
for g in grp_d_kg:
    for d, w in grp_d_kg[g].items():
        d_tot[d] += w
summary = {
    "concrete": [[c, lab, cat_n[c], round(cat_vol[c], 3)] for c, _, lab in CATS if cat_n[c]],
    "concrete_total": round(tot_vol, 3),
    "steel": [[k, lab, grp_n[g], round(grp_kg[g], 1), [[d, round(grp_d_kg[g][d], 1)] for d in DIAMS if d in grp_d_kg[g]]]
              for g, k, lab in GROUPS],
    "steel_total": round(tot_kg, 1),
    "steel_by_d": [[d, round(d_tot[d], 1)] for d in DIAMS if d in d_tot],
    "n_bars": len(B), "n_elements": len(tags),
    "by_level": [[LEVELS[i][2], round(lvl_vol[i], 3), round(lvl_kg[i], 1)] for i in range(len(LEVELS))],
    "ratio": round(tot_kg / tot_vol, 1),
}

grids = []
for k, g in M["grids"].items():
    grids.append({"n": k, "axis": "u" if g["dir"] == "v" else "v", "p": round(g["pos"], 4)})
grids.sort(key=lambda g: (g["axis"], g["p"]))

meta = {
    "title": "Casa San Jerónimo",
    "project": "SJ_REDISENO_4X3_R1",
    "units": "m",
    "levels": [{"k": k, "n": n, "lab": lab, "z": round(M["levels"][n], 3)} for k, n, lab in LEVELS],
    "grids": grids,
    "property": [[[round(a[0], 3), round(a[1], 3)], [round(b_[0], 3), round(b_[1], 3)]] for a, b_ in M["property"]],
    "cats": [[c, lab, pl] for c, lab, pl in CATS],
    "groups": [[k, lab] for _, k, lab in GROUPS],
    "diams": DIAMS, "kgm": KG,
    "bin": binmeta,
    "elements": els,
    "summary": summary,
}
json.dump(meta, open(f"{OUT}/model.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("model.bin", len(buf), "bytes; model.json", os.path.getsize(f"{OUT}/model.json"), "bytes")
print(json.dumps(summary, ensure_ascii=False, indent=1)[:2500])
print(collections.Counter((e["c"], e["lg"]) for e in els))
