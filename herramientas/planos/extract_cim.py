"""Extrae del IFC todo lo que necesita la lamina E-01 (cimentacion) en coordenadas locales
alineadas a los ejes: u a lo largo de los ejes N (hacia A-3), v a lo largo de los ejes A (hacia N-1).
Origen en la interseccion A-1 / N-4."""
import json, math
import numpy as np
import ifcopenshell, ifcopenshell.geom as G, ifcopenshell.util.element as ue
import ifcopenshell.util.placement as up
from shapely.geometry import Polygon
from shapely.ops import unary_union

f = ifcopenshell.open("src/Proyect sj.ifc")
st = G.settings(); st.set("use-world-coords", True)

# ---------- ejes ----------
g = f.by_type("IfcGrid")[0]
M = up.get_local_placement(g.ObjectPlacement)
axes = {}
for ax in g.UAxes + g.VAxes:
    pts = np.array(ax.AxisCurve.Points.CoordList)
    P = np.array([(M @ np.array([p[0], p[1], 0, 1]))[:2] for p in pts])
    axes[ax.AxisTag] = P
dN = axes["N-1"][1] - axes["N-1"][0]
th = math.atan2(dN[1], dN[0])
c, s = math.cos(-th), math.sin(-th)
R = np.array([[c, -s], [s, c]])


def inter(a, b):
    p, r = a[0], a[1] - a[0]
    q, t = b[0], b[1] - b[0]
    k = np.cross(q - p, t) / np.cross(r, t)
    return p + k * r


O = inter(axes["A-1"], axes["N-4"])


def L2(xy):
    return (R @ (np.asarray(xy)[..., :2] - O).T).T


grids = {}
for k, P in axes.items():
    Q = L2(P)
    if k.startswith("A"):
        grids[k] = {"dir": "v", "pos": float(Q[:, 0].mean())}
    else:
        grids[k] = {"dir": "u", "pos": float(Q[:, 1].mean())}


def mesh(e):
    sh = G.create_shape(st, e)
    v = np.array(sh.geometry.verts).reshape(-1, 3)
    fa = np.array(sh.geometry.faces).reshape(-1, 3)
    return v, fa


def footprint(e):
    v, fa = mesh(e)
    q = L2(v)
    polys = []
    for t in fa:
        p = Polygon(q[t])
        if p.area > 1e-8:
            polys.append(p.buffer(1e-5))
    u = unary_union(polys).buffer(-1e-5).simplify(0.002)
    if u.geom_type != "Polygon":
        u = max(u.geoms, key=lambda x: x.area)
    return [list(map(float, p)) for p in u.exterior.coords[:-1]], float(v[:, 2].min()), float(v[:, 2].max())


def P(e):
    return ue.get_psets(e)


def cm(e):
    return P(e).get("Datos de identidad", {}).get("Comentarios") or ""


out = {"grids": grids, "theta_deg": math.degrees(th), "footings": [], "columns": [], "beams": [],
       "bars": [], "stair": [], "property": None, "levels": {}}
for s_ in f.by_type("IfcBuildingStorey"):
    out["levels"][s_.Name] = float(s_.Elevation)

for e in f.by_type("IfcSlab"):
    p = P(e)
    tipo = p["Otros"]["Tipo"]
    c_ = cm(e)
    if tipo.startswith("ZR_") or tipo.startswith("CIM_ESCALERA"):
        fp, z0, z1 = footprint(e)
        out["footings"].append({"id": e.Tag, "tipo": tipo, "com": c_, "poly": fp, "z0": z0, "z1": z1,
                                "B": p["Cotas"].get("Anchura"), "L": p["Cotas"].get("Longitud"),
                                "h": p["Cotas"].get("Grosor de cimentación")})
    elif "N1-N2|LOSA_T1" in c_:
        fp, z0, z1 = footprint(e)
        out["stair"].append({"id": e.Tag, "com": c_, "poly": fp, "z0": z0, "z1": z1})

for e in f.by_type("IfcColumn"):
    p = P(e)
    if p["Restricciones"]["Nivel base"] != "Cimentacion":
        continue
    fp, z0, z1 = footprint(e)
    out["columns"].append({"id": e.Tag, "tipo": p["Otros"]["Tipo"], "mark": c_.split("|")[1] if (c_ := cm(e)) else "",
                           "com": c_, "poly": fp, "z0": z0, "z1": z1})

for e in f.by_type("IfcBeam"):
    p = P(e)
    if p["Restricciones"].get("Nivel de referencia") != "Cimentacion":
        continue
    fp, z0, z1 = footprint(e)
    out["beams"].append({"id": e.Tag, "tipo": p["Otros"]["Tipo"], "com": cm(e), "poly": fp, "z0": z0, "z1": z1,
                         "b": p["Cotas"]["b"], "h": p["Cotas"]["h"], "Lc": p["Cotas"]["Longitud de corte"]})

for e in f.by_type("IfcBuildingElementProxy"):
    if "Propiedad" in (e.Name or ""):
        try:
            fp, z0, z1 = footprint(e)
            out["property"] = fp
        except Exception as ex:
            print("prop", ex)

host_ids = {x["id"] for x in out["footings"]} | {x["id"] for x in out["columns"]} | {x["id"] for x in out["beams"]}


def centerline(r):
    it = r.Representation.Representations[0].Items[0]
    Mr = up.get_local_placement(r.ObjectPlacement)
    pts = np.array(it.Directrix.Points.CoordList)
    W = np.array([(Mr @ np.array([*p, 1]))[:3] for p in pts])
    q = L2(W)
    return [[float(a), float(b), float(z)] for (a, b), z in zip(q, W[:, 2])], float(it.Radius)


for r in f.by_type("IfcReinforcingBar"):
    p = P(r)
    c_ = cm(r)
    parts = c_.split("|")
    if len(parts) < 3 or parts[1] not in host_ids and "MECHA" not in c_:
        continue
    pl, rad = centerline(r)
    out["bars"].append({"grp": parts[0], "host": parts[1], "role": parts[2], "rest": parts[3:],
                        "tipo": p["Otros"]["Tipo"], "d": p["Otros"]["Tipo"].split("_")[1].replace("in", ""),
                        "L": p["Cotas"]["Longitud total de barra"] / (p["Conjunto de armaduras"].get("Cantidad") or 1),
                        "segs": [p["Cotas"].get(f"Longitud {i}") for i in range(1, 7)],
                        "spacing": p["Conjunto de armaduras"].get("Espaciado"),
                        "nset": p["Conjunto de armaduras"].get("Cantidad"),
                        "shape": p["Construcción"].get("Nombre de la forma"),
                        "pl": pl})

json.dump(out, open("cim.json", "w"), indent=0)
print("theta", out["theta_deg"])
print({k: round(v["pos"], 3) for k, v in grids.items()})
print(len(out["footings"]), len(out["columns"]), len(out["beams"]), len(out["bars"]), out["property"] is not None)
import collections
print(collections.Counter((b["grp"], b["role"]) for b in out["bars"]))
