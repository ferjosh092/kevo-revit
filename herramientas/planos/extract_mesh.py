"""Mallas 3D (coordenadas locales de ejes) de los elementos que aparecen en los cortes de E-01,
y acero del primer tramo de escalera. Complementa cim.json."""
import json, math, pickle
import numpy as np
import ifcopenshell, ifcopenshell.geom as G, ifcopenshell.util.element as ue
import ifcopenshell.util.placement as up

f = ifcopenshell.open("src/Proyect sj.ifc")
st = G.settings(); st.set("use-world-coords", True)
cim = json.load(open("cim.json"))

g = f.by_type("IfcGrid")[0]
M = up.get_local_placement(g.ObjectPlacement)
axes = {}
for ax in g.UAxes + g.VAxes:
    pts = np.array(ax.AxisCurve.Points.CoordList)
    axes[ax.AxisTag] = np.array([(M @ np.array([p[0], p[1], 0, 1]))[:2] for p in pts])
dN = axes["N-1"][1] - axes["N-1"][0]
th = math.atan2(dN[1], dN[0])
c, s = math.cos(-th), math.sin(-th)
R = np.array([[c, -s], [s, c]])


def inter(a, b):
    p, r = a[0], a[1] - a[0]
    q, t = b[0], b[1] - b[0]
    k = (np.cross(np.append(q - p, 0), np.append(t, 0))[2]) / (np.cross(np.append(r, 0), np.append(t, 0))[2])
    return p + k * r


O = inter(axes["A-1"], axes["N-4"])


def L3(v):
    q = (R @ (v[:, :2] - O).T).T
    return np.column_stack([q, v[:, 2]])


def cm(e):
    return ue.get_psets(e).get("Datos de identidad", {}).get("Comentarios") or ""


meshes = {}
want = set()
for e in f.by_type("IfcSlab"):
    t = ue.get_psets(e)["Otros"]["Tipo"]
    c_ = cm(e)
    if t.startswith("ZR_") or t.startswith("CIM_ESC"):
        want.add((e, "zapata"))
    elif "FALSO_PISO" in c_:
        want.add((e, "falsopiso"))
    elif "N1-N2|LOSA_T1" in c_ or "N1-N2|DESCANSO" in c_:
        want.add((e, "escalera"))
for e in f.by_type("IfcColumn"):
    if ue.get_psets(e)["Restricciones"]["Nivel base"] in ("Cimentacion", "Nivel 1"):
        want.add((e, "columna"))
for e in f.by_type("IfcBeam"):
    if ue.get_psets(e)["Restricciones"].get("Nivel de referencia") in ("Cimentacion", "Nivel 2"):
        want.add((e, "viga"))
for e in f.by_type("IfcBuildingElementProxy"):
    if "N1-N2|PELDANOS_T1" in cm(e):
        want.add((e, "peldanos"))

for e, cat in want:
    sh = G.create_shape(st, e)
    v = np.array(sh.geometry.verts).reshape(-1, 3)
    fa = np.array(sh.geometry.faces).reshape(-1, 3)
    meshes[e.Tag] = {"cat": cat, "com": cm(e), "v": L3(v), "f": fa, "name": e.Name}

# acero de la escalera (primer tramo y descanso) para el detalle del cimiento
stair_hosts = {k for k, m in meshes.items() if m["cat"] == "escalera"}
sbars = []
for r in f.by_type("IfcReinforcingBar"):
    c_ = cm(r)
    p = c_.split("|")
    if len(p) >= 3 and p[1] in stair_hosts:
        it = r.Representation.Representations[0].Items[0]
        Mr = up.get_local_placement(r.ObjectPlacement)
        pts = np.array(it.Directrix.Points.CoordList)
        W = np.array([(Mr @ np.array([*q, 1]))[:3] for q in pts])
        ps = ue.get_psets(r)
        sbars.append({"host": p[1], "role": p[2], "rest": p[3:], "d": ps["Otros"]["Tipo"].split("_")[1].replace("in", ""),
                      "pl": L3(W).tolist(), "r": float(it.Radius)})

# limite de propiedad
e = [x for x in f.by_type("IfcBuildingElementProxy") if "Propiedad" in (x.Name or "")][0]
Mp = up.get_local_placement(e.ObjectPlacement)
prop = []
for el in e.Representation.Representations[0].Items[0].Elements:
    pts = np.array([list(p.Coordinates) for p in el.Points]) if el.is_a("IfcPolyline") else np.array(el.Points.CoordList)
    W = np.array([(Mp @ np.array([q[0], q[1], 0, 1]))[:3] for q in pts])
    prop.append(L3(W)[:, :2].tolist())

pickle.dump({"meshes": meshes, "stair_bars": sbars, "property": prop}, open("mesh.pkl", "wb"))
import collections
print(collections.Counter(m["cat"] for m in meshes.values()), len(sbars))
print("prop", np.round(prop, 3).tolist())
for k, m in meshes.items():
    if m["cat"] in ("falsopiso", "escalera", "peldanos"):
        print(m["cat"], m["com"], np.round(m["v"].min(0), 3), np.round(m["v"].max(0), 3))
print(collections.Counter((b["host"], b["role"], b["d"]) for b in sbars))
