"""Extraccion completa del IFC en coordenadas locales de ejes (origen A-1/N-4, X a lo largo de los ejes N).
Salida model_all.pkl:
  grids, levels, theta_deg
  elements: {tag: {cls, cat, tipo, com, level, psets(resumen), v (Nx3), f (Mx3), bbox}}
  bars: [{id, grp, host, role, rest, d, db, tipo, L, segs, shape, spacing, nset, pl (Nx3)}]
  property: polilineas
"""
import math, pickle, collections
import numpy as np
import ifcopenshell, ifcopenshell.geom as G, ifcopenshell.util.element as ue
import ifcopenshell.util.placement as up

f = ifcopenshell.open("src/Proyect sj.ifc")
st = G.settings(); st.set("use-world-coords", True)

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


def cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def inter(a, b):
    p, r = a[0], a[1] - a[0]
    q, t = b[0], b[1] - b[0]
    return p + cross2(q - p, t) / cross2(r, t) * r


O = inter(axes["A-1"], axes["N-4"])


def L3(v):
    q = (R @ (v[:, :2] - O).T).T
    return np.column_stack([q, v[:, 2]])


grids = {}
for k, P in axes.items():
    Q = (R @ (P - O).T).T
    grids[k] = {"dir": "v", "pos": float(Q[:, 0].mean())} if k.startswith("A") else {"dir": "u", "pos": float(Q[:, 1].mean())}

levels = {s_.Name: float(s_.Elevation) for s_ in f.by_type("IfcBuildingStorey")}


def summ(ps):
    keep = {}
    for grp, props in ps.items():
        if grp.startswith("Pset_EnvironmentalImpact") or grp in ("Parámetros IFC", "Proceso por fases", "Gráficos"):
            continue
        d = {k: v for k, v in props.items() if k != "id" and v not in (None, "")}
        if d:
            keep[grp] = d
    return keep


elements = {}
CATS = {"IfcColumn": "columna", "IfcBeam": "viga", "IfcSlab": "losa", "IfcBuildingElementProxy": "generico"}
for cls, cat in CATS.items():
    for e in f.by_type(cls):
        ps = ue.get_psets(e)
        com = ps.get("Datos de identidad", {}).get("Comentarios") or ""
        tipo = ps.get("Otros", {}).get("Tipo") or ""
        cat2 = cat
        if cls == "IfcSlab":
            if tipo.startswith("ZR_") or tipo.startswith("CIM_ESC"):
                cat2 = "zapata"
            elif "ESCALERA" in com:
                cat2 = "escalera"
            elif "FALSO_PISO" in com:
                cat2 = "falsopiso"
        if cls == "IfcBuildingElementProxy":
            if "ESCALERA" in com:
                cat2 = "escalera"
            elif "Propiedad" in (e.Name or ""):
                continue
        try:
            sh = G.create_shape(st, e)
        except Exception as ex:
            print("sin geometria", e.Tag, ex)
            continue
        v = L3(np.array(sh.geometry.verts).reshape(-1, 3))
        fa = np.array(sh.geometry.faces).reshape(-1, 3)
        lvl = ps.get("Restricciones", {}).get("Nivel base") or ps.get("Restricciones", {}).get("Nivel de referencia") \
            or ps.get("Restricciones", {}).get("Nivel")
        elements[e.Tag] = {"cls": cls, "cat": cat2, "tipo": tipo, "com": com, "name": e.Name, "level": lvl,
                           "guid": e.GlobalId, "psets": summ(ps), "v": v.astype(np.float32), "f": fa.astype(np.int32),
                           "bbox": (v.min(0).tolist(), v.max(0).tolist())}

bars = []
for r in f.by_type("IfcReinforcingBar"):
    ps = ue.get_psets(r)
    com = ps["Datos de identidad"].get("Comentarios") or ""
    p = com.split("|")
    it = r.Representation.Representations[0].Items[0]
    Mr = up.get_local_placement(r.ObjectPlacement)
    W = np.array([(Mr @ np.array([*q, 1]))[:3] for q in it.Directrix.Points.CoordList])
    tipo = ps["Otros"]["Tipo"]
    q = ps["Conjunto de armaduras"].get("Cantidad") or 1
    bars.append({"id": r.Tag, "grp": p[0], "host": p[1] if len(p) > 1 else "", "role": p[2] if len(p) > 2 else "",
                 "rest": p[3:], "tipo": tipo, "d": tipo.split("_")[1].replace("in", ""), "db": float(it.Radius) * 2,
                 "L": ps["Cotas"]["Longitud total de barra"] / q,
                 "segs": [ps["Cotas"].get(f"Longitud {i}") for i in range(1, 7)],
                 "shape": ps["Construcción"].get("Nombre de la forma"),
                 "spacing": ps["Conjunto de armaduras"].get("Espaciado"), "nset": q,
                 "pl": L3(W).astype(np.float32)})

e = [x for x in f.by_type("IfcBuildingElementProxy") if "Propiedad" in (x.Name or "")][0]
Mp = up.get_local_placement(e.ObjectPlacement)
prop = []
for el in e.Representation.Representations[0].Items[0].Elements:
    pts = np.array([list(p.Coordinates) for p in el.Points]) if el.is_a("IfcPolyline") else np.array(el.Points.CoordList)
    W = np.array([(Mp @ np.array([q[0], q[1], 0, 1]))[:3] for q in pts])
    prop.append(L3(W)[:, :2].tolist())

pickle.dump({"grids": grids, "levels": levels, "theta_deg": math.degrees(th), "elements": elements, "bars": bars,
             "property": prop}, open("model_all.pkl", "wb"))
print(len(elements), len(bars), collections.Counter(x["cat"] for x in elements.values()))
