# -*- coding: utf-8 -*-
"""
SAN JERONIMO - NODO 18 - REDISENO: ESCALERA (caja A-2/A-3 con columnas 0.60x0.30, N-4 en 10.015)
Configuracion aprobada (medidas desde A-1 / desde N-1):
  - Tramos de 1.10 pegados (sin ojo): tramo 1 (sube) en la franja junto a N-4 (b 8.765-9.865),
    tramo 2 (baja hacia el piso siguiente) junto a N-3 (b 7.65-8.75).
  - TODO dentro de la caja de 4.05 x 2.22 (de la cara exterior de A-2, 6.10, a la cara exterior de
    A-3, 10.15). Nada en voladizo. Espesor 0.15.
  - Reparto de la caja: plataforma de llegada PLAT (1.20) en todos los pisos; descanso intermedio de
    1.25 en el primer piso (DESC1) y de 1.10 en los altos (2.30 - PLAT). Rectangulos completos de una
    pieza. Pisos de 2.60: 16 contrapasos (8 + 8) de 16.25 con pasos de 0.25, tramos de 7.30 a 9.05.
    Primer piso: 19 contrapasos de 16.8; el tramo 1 arranca en la cara exterior de A-2 (6.10) con 11
    pasos de 0.255 (llega a 8.90) y el tramo 2 baja con 6 pasos de 0.267 hasta 7.30.
  - Si los tramos llegaran a distinta distancia, la plataforma se construye en dos franjas.
  - Peldanos y nudos prismaticos como modelos genericos (DirectShape), igual que el modelo anterior.
QUE HACE: borra las piezas SJ_ESCALERA_CONCRETO (pisos y modelos genericos) y crea las nuevas con el
mismo tipo de piso (Generico 150 mm) y marcador SJ_ESCALERA_CONCRETO_4X3_R1. Despues: nodo 9B
(cimiento de arranque) y nodo 13 (acero).
IN[0] = RUN: False = previsualizar; True = ejecutar
"""
import clr, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, CurveLoop, DirectShape, ElementId, FamilyInstance,
    FamilySymbol, FilteredElementCollector, Floor, GeometryCreationUtilities, Grid, Level, Line, LocationPoint,
    Options, Solid, StorageType, Transaction, UnitTypeId, UnitUtils, XYZ)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
clr.AddReference("System")
from System.Collections.Generic import List
doc = DocumentManager.Instance.CurrentDBDocument

MARKER = "SJ_ESCALERA_CONCRETO_4X3_R1"
PREFIJO_VIEJO = "SJ_ESCALERA_CONCRETO"
A_PLAT = 6.10           # cara exterior de A-2: inicio de la caja (plataforma de llegada al piso, dentro de la caja)
A_INI = 7.15            # arranque de los tramos en los pisos altos (la plataforma 6.10-7.15 va antes)
A_FIN = 10.15           # cara exterior de A-3: fin del descanso intermedio (caja de 4.05 entre caras exteriores)
B_T2 = (7.65, 8.75)     # franja del tramo 2 (junto a N-3)
B_T1 = (8.765, 9.865)   # franja del tramo 1 (junto a N-4)
B_DESC = (7.65, 9.865)
J1 = (6.10, 7.15, 7.65, 9.865)   # plataforma de llegada al piso, DENTRO de la caja, sobre el collarin de A-2: a0, a1, b0, b1
PASO = 0.25            # (valor por defecto; el paso real de cada piso esta en NIVELES)
ESP = 0.15
NUDO_ANCHO = 0.30
# Configuracion por piso: (nivel base, nivel tope, contrapasos T1, contrapasos T2, paso T1, paso T2,
#                          arranque T1 (a), llegada T2 (a))
#  PLAT define el reparto: plataforma de llegada = PLAT (1.20), descanso de los pisos altos = 2.30 - PLAT (1.10);
#  DESC1 = descanso del primer piso (1.25). Pisos de 2.60: 16 cp (8 + 8) de 16.25 con pasos de 0.25,
#  ambos tramos de 1.75. 1er piso (3.20): 19 cp de 16.8; T1 desde la cara de A-2 (6.10) con 11 pasos de 0.25
#  y descanso DESC1 (1.30); T2 con 6 pasos hasta la plataforma del Nivel 2.
PLAT = 1.20                     # plataforma de llegada (6.10 -> 6.10 + PLAT); descanso de los pisos altos = 2.30 - PLAT (1.10)
A_TR = 6.10 + PLAT              # arranque / llegada de los tramos en los pisos altos
DESC1 = 1.25                    # descanso intermedio del PRIMER piso (max. 1.30 con pasos de 0.25 en el tramo 1)
NIVELES = [("Nivel 1", "Nivel 2", 12, 7, (10.15 - DESC1 - 6.10) / 11.0, (10.15 - DESC1 - A_TR) / 6.0, 6.10, A_TR),
           ("Nivel 2", "Nivel 3", 8, 8, 0.25, 0.25, A_TR, A_TR),
           ("Nivel 3", "Nivel 4", 8, 8, 0.25, 0.25, A_TR, A_TR),
           ("Nivel 4", "Nivel 5", 8, 8, 0.25, 0.25, A_TR, A_TR)]

def unwrap(value):
    try:
        return UnwrapElement(value)
    except Exception:
        return value


def m(value):
    return UnitUtils.ConvertToInternalUnits(float(value), UnitTypeId.Meters)


def internal_to_m(value):
    return UnitUtils.ConvertFromInternalUnits(float(value), UnitTypeId.Meters)


def id_value(element_id):
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def element_name(element):
    try:
        return element.Name
    except Exception:
        return "<sin nombre>"


def ensure_family_symbol(value, label):
    item = unwrap(value)
    if not isinstance(item, FamilySymbol):
        raise ValueError("{} debe ser un Tipo de familia de Revit.".format(label))
    return item


def writable_double_parameters(element):
    names = []
    for parameter in element.Parameters:
        if parameter.StorageType == StorageType.Double and not parameter.IsReadOnly:
            names.append(parameter.Definition.Name)
    return sorted(set(names))


def set_dimension(element, candidate_names, value_m, label):
    for name in candidate_names:
        parameter = element.LookupParameter(name)
        if (parameter is not None and not parameter.IsReadOnly and
                parameter.StorageType == StorageType.Double):
            parameter.Set(m(value_m))
            return name
    raise ValueError(
        "No se encontro parametro editable para {} en '{}'. Disponibles: {}".format(
            label, element_name(element), ", ".join(writable_double_parameters(element))))


def duplicate_or_get(base_symbol, target_name):
    for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if symbol.Family.Id == base_symbol.Family.Id and element_name(symbol) == target_name:
            return symbol
    return base_symbol.Duplicate(target_name)


def configure_footing_type(base, data):
    symbol = duplicate_or_get(base, data["name"])
    set_dimension(symbol, ("Width", "Foundation Width", "Ancho", "Anchura", "B", "b"), data["b"], "ancho")
    set_dimension(symbol, ("Length", "Foundation Length", "Largo", "Longitud", "L", "l"), data["l"], "largo")
    set_dimension(symbol, (
        "Thickness", "Foundation Thickness", "Espesor",
        "Grosor de cimentación", "Grosor de cimentacion", "t", "T", "h", "H"),
        data["t"], "espesor")
    return symbol


def activate(symbol):
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()


def set_comment(instance, value):
    parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if parameter is not None and not parameter.IsReadOnly:
        parameter.Set(value)


def instance_point(instance):
    location = instance.Location
    if isinstance(location, LocationPoint):
        return location.Point
    return None


def xy_distance(a, b):
    return math.sqrt((a.X - b.X) ** 2 + (a.Y - b.Y) ** 2)


def move_point_instance_xy(instance, target):
    current = instance_point(instance)
    if current is None:
        return
    vector = XYZ(target.X - current.X, target.Y - current.Y, 0.0)
    if vector.GetLength() > 1e-8:
        ElementTransformUtils.MoveElement(doc, instance.Id, vector)


def normalize_radians(angle):
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def rotate_point_instance(instance, target_angle, center):
    """Gira la instancia hasta target_angle alrededor de un eje vertical
    que pasa por 'center' (el punto DESTINO explicito). NUNCA se usa
    Location.Point como centro: en un elemento recien creado y sin
    regenerar vale (0,0,0) y el giro ocurre alrededor del origen."""
    location = instance.Location
    if not isinstance(location, LocationPoint):
        return
    delta = normalize_radians(target_angle - location.Rotation)
    if abs(delta) <= 1e-7:
        return
    axis = Line.CreateBound(
        XYZ(center.X, center.Y, center.Z - m(1.0)),
        XYZ(center.X, center.Y, center.Z + m(1.0)))
    ElementTransformUtils.RotateElement(doc, instance.Id, axis, delta)


def set_column_constraints(column, low_level, high_level, base_offset_ft):
    values = (
        (BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, low_level.Id),
        (BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, high_level.Id),
        (BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM, base_offset_ft),
        (BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM, 0.0),
    )
    for built_in, value in values:
        parameter = column.get_Parameter(built_in)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(value)





def get_comment(el):
    try:
        p = el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        return (p.AsString() or "") if p is not None else ""
    except Exception:
        return ""

def center_xy(el):
    bb = el.get_BoundingBox(None)
    return ((bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0)

try:
    run = bool(IN[0])
    grids = dict((g.Name.strip(), g) for g in FilteredElementCollector(doc).OfClass(Grid))
    gN = grids["N-1"].Curve; d = gN.GetEndPoint(1) - gN.GetEndPoint(0)
    L = math.hypot(d.X, d.Y); u = (d.X / L, d.Y / L)
    if u[0] < 0: u = (-u[0], -u[1])
    n = (-u[1], u[0])
    cols = [c for c in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType() if isinstance(c, FamilyInstance)]
    # origen = interseccion real de los ejes A-1 y N-1 (no depende de ninguna columna)
    gA = grids["A-1"].Curve
    ra = gA.GetEndPoint(0); da = gA.GetEndPoint(1) - ra
    rn = gN.GetEndPoint(0); dn = gN.GetEndPoint(1) - rn
    den = da.X * dn.Y - da.Y * dn.X
    if abs(den) < 1e-9:
        raise ValueError("los ejes A-1 y N-1 no se cruzan")
    tpar = ((rn.X - ra.X) * dn.Y - (rn.Y - ra.Y) * dn.X) / den
    O = (ra.X + tpar * da.X, ra.Y + tpar * da.Y)
    def P(a, b, z):
        return XYZ(O[0] + m(a) * u[0] - m(b) * n[0], O[1] + m(a) * u[1] - m(b) * n[1], m(z))
    levels = dict((l.Name, l) for l in FilteredElementCollector(doc).OfClass(Level))
    viejos_pisos = [f for f in FilteredElementCollector(doc).OfClass(Floor) if get_comment(f).startswith(PREFIJO_VIEJO)]
    viejos_gen = [g for g in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_GenericModel).WhereElementIsNotElementType() if get_comment(g).startswith(PREFIJO_VIEJO)]
    if not viejos_pisos:
        raise ValueError("no se encontraron las piezas actuales de escalera (marcador " + PREFIJO_VIEJO + ")")
    tipo_id = viejos_pisos[0].GetTypeId()
    tipo_nombre = element_name(doc.GetElement(tipo_id))
    cat_gen = ElementId(BuiltInCategory.OST_GenericModel)

    def rect_loop(a0, a1, b0, b1, z):
        pts = [P(a0, b0, z), P(a1, b0, z), P(a1, b1, z), P(a0, b1, z)]
        lp = CurveLoop()
        for i in range(4):
            lp.Append(Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        return lp

    def prism(profile_ab_z, b0, b1, tag):
        """profile: lista de (a, z) en el plano vertical; se extruye de b0 a b1"""
        pts = [P(a, b0, z) for a, z in profile_ab_z]
        lp = CurveLoop()
        for i in range(len(pts)):
            lp.Append(Line.CreateBound(pts[i], pts[(i + 1) % len(pts)]))
        loops = List[CurveLoop](); loops.Add(lp)
        vec = XYZ(-n[0], -n[1], 0.0)                        # +b va hacia N-3 -> direccion -n
        sol = GeometryCreationUtilities.CreateExtrusionGeometry(loops, vec, m(b1 - b0))
        ds = DirectShape.CreateElement(doc, cat_gen)
        ds.SetShape([sol])
        set_comment(ds, "{}|{}".format(MARKER, tag))
        return ds

    plan = []
    for (lo, hi, n1, n2, paso1, paso2, a_ini1, a_ini2) in NIVELES:
        z0 = internal_to_m(levels[lo].Elevation); z1 = internal_to_m(levels[hi].Elevation)
        nc = n1 + n2; r = (z1 - z0) / nc
        a_end1 = a_ini1 + (n1 - 1) * paso1        # fin del tramo 1 (inner corner del ultimo peldano)
        a_L2 = a_ini2 + (n2 - 1) * paso2          # arranque del tramo 2 (borde del descanso)
        zL = z0 + n1 * r                          # tope del descanso intermedio
        nm = "{}-{}".format(lo.replace("Nivel ", "N"), hi.replace("Nivel ", "N"))
        plan.append({"nivel": nm, "z0": z0, "z1": z1, "r": r, "n1": n1, "n2": n2, "a_ini1": a_ini1, "a_ini2": a_ini2,
                     "a_end1": a_end1, "a_L2": a_L2, "zL": zL, "paso1": paso1, "paso2": paso2,
                     "descanso_m": round(A_FIN - max(a_end1, a_L2), 2), "lo": lo, "hi": hi})

    if not run:
        OUT = {"estado": "PREVISUALIZACION - no se modifico el modelo", "tipo_de_piso": tipo_nombre,
               "piezas_a_borrar": {"pisos": len(viejos_pisos), "modelos_genericos": len(viejos_gen)},
               "tramos": [{"nivel": p["nivel"], "contrapasos": "{} = {} + {}".format(p["n1"] + p["n2"], p["n1"], p["n2"]),
                           "contrapaso_cm": round(p["r"] * 100, 1), "pasos_cm (T1 / T2)": (p["paso1"] * 100, p["paso2"] * 100),
                           "tramo_1_m": "{:.2f} a {:.2f}".format(p["a_ini1"], p["a_end1"]), "tramo_2_m": "{:.2f} a {:.2f}".format(p["a_L2"], p["a_ini2"]),
                           "descanso_intermedio_m": p["descanso_m"], "cota_descanso_m": round(p["zL"], 3)} for p in plan],
               "plataforma_de_llegada": [{"nivel": p["nivel"], "franja_tramo_1_m": "6.10 a {:.2f}".format(plan[i + 1]["a_ini1"] if i + 1 < len(plan) else p["a_ini1"]),
                                          "franja_tramo_2_m": "6.10 a {:.2f}".format(p["a_ini2"])} for i, p in enumerate(plan)],
               "accion": "IN[0]=True para ejecutar."}
    else:
        tx = Transaction(doc, "San Jeronimo - rediseno 4x3: escalera"); tx.Start()
        try:
            for e in viejos_pisos + viejos_gen: doc.Delete(e.Id)
            doc.Regenerate()
            hechas = []
            def floor_flat(a0, a1, b0, b1, z_top, level, tag):
                loops = List[CurveLoop](); loops.Add(rect_loop(a0, a1, b0, b1, z_top))
                f = Floor.Create(doc, loops, tipo_id, level.Id, True, None, 0.0)
                doc.Regenerate()
                po = f.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
                if po is not None and not po.IsReadOnly:
                    po.Set(m(z_top) - level.Elevation)
                set_comment(f, "{}|{}".format(MARKER, tag))
                doc.Regenerate()
                bb = f.get_BoundingBox(None)
                hechas.append({"pieza": tag, "id": id_value(f.Id), "z_min_max_m": (round(internal_to_m(bb.Min.Z), 3), round(internal_to_m(bb.Max.Z), 3))})
                return f
            def floor_slope(a_lo, a_hi, b0, b1, z_lo, z_hi, level, tag):
                """losa inclinada: cara superior de (a_lo, z_lo) a (a_hi, z_hi); cola de la flecha en a_lo"""
                loops = List[CurveLoop](); loops.Add(rect_loop(min(a_lo, a_hi), max(a_lo, a_hi), b0, b1, z_lo))
                bm = (b0 + b1) / 2.0
                arrow = Line.CreateBound(P(a_lo, bm, z_lo), P(a_hi, bm, z_lo))
                slope = (z_hi - z_lo) / abs(a_hi - a_lo)
                f = Floor.Create(doc, loops, tipo_id, level.Id, True, arrow, slope)
                doc.Regenerate()
                po = f.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
                if po is not None and not po.IsReadOnly:
                    po.Set(m(z_lo) - level.Elevation)
                set_comment(f, "{}|{}".format(MARKER, tag))
                doc.Regenerate()
                bb = f.get_BoundingBox(None)
                hechas.append({"pieza": tag, "id": id_value(f.Id), "z_min_max_m": (round(internal_to_m(bb.Min.Z), 3), round(internal_to_m(bb.Max.Z), 3)),
                               "esperado_top_m": (round(z_lo, 3), round(z_hi, 3))})
                return f
            for p in plan:
                lvl0, lvl1 = levels[p["lo"]], levels[p["hi"]]
                z0, z1, r, n1, n2 = p["z0"], p["z1"], p["r"], p["n1"], p["n2"]
                zL = p["zL"]; nm = p["nivel"]; paso1, paso2 = p["paso1"], p["paso2"]
                a_ini1, a_ini2, a_end1, a_L2 = p["a_ini1"], p["a_ini2"], p["a_end1"], p["a_L2"]
                tv1 = ESP / math.cos(math.atan2(r, paso1)); tv2 = ESP / math.cos(math.atan2(r, paso2))
                # tramo 1: sube de (a_ini1, z0) a (a_end1, z0 + (n1-1) r)
                floor_slope(a_ini1, a_end1, B_T1[0], B_T1[1], z0, z0 + (n1 - 1) * r, lvl0, "{}|LOSA_T1".format(nm))
                # tramo 2: sube del descanso (a_L2, zL) a (a_ini2, z1 - r)
                floor_slope(a_L2, a_ini2, B_T2[0], B_T2[1], zL, z1 - r, lvl0, "{}|LOSA_T2".format(nm))
                # descanso intermedio
                floor_flat(max(a_end1, a_L2), A_FIN, B_DESC[0], B_DESC[1], zL, lvl0, "{}|DESCANSO_J2".format(nm))
                # plataforma de llegada al nivel superior, dentro de la caja, en dos franjas:
                #   franja del tramo 1: de 6.10 al arranque del tramo 1 del piso siguiente (o el propio si es el ultimo)
                #   franja del tramo 2: de 6.10 a la llegada del tramo 2 de este piso
                k_ = plan.index(p)
                a_sig = plan[k_ + 1]["a_ini1"] if k_ + 1 < len(plan) else a_ini1
                if abs(a_sig - a_ini2) < 0.005:
                    floor_flat(J1[0], a_ini2, B_DESC[0], B_DESC[1], z1, lvl1, "{}|EXTENSION_PLATAFORMA_J1".format(nm))
                else:
                    floor_flat(J1[0], a_sig, B_T1[0], B_T1[1], z1, lvl1, "{}|EXTENSION_PLATAFORMA_J1".format(nm))
                    floor_flat(J1[0], a_ini2, B_T2[0], B_T2[1], z1, lvl1, "{}|EXTENSION_PLATAFORMA_J1B".format(nm))
                # peldanos tramo 1
                EPS = 0.02
                prof = [(a_ini1, z0 - EPS), (a_ini1, z0)]
                for i in range(1, n1):
                    a_i = a_ini1 + (i - 1) * paso1
                    prof += [(a_i, z0 + i * r), (a_i + paso1, z0 + i * r)]
                prof.append((a_end1, z0 + (n1 - 1) * r - EPS))
                prism(prof, B_T1[0], B_T1[1], "{}|PELDANOS_T1".format(nm))
                # peldanos tramo 2 (desde el descanso hacia a_ini2)
                prof = [(a_L2, zL - EPS), (a_L2, zL)]
                for i in range(1, n2):
                    a_i = a_L2 - (i - 1) * paso2
                    prof += [(a_i, zL + i * r), (a_i - paso2, zL + i * r)]
                prof.append((a_ini2, zL + (n2 - 1) * r - EPS))
                prism(prof, B_T2[0], B_T2[1], "{}|PELDANOS_T2".format(nm))
                # nudos prismaticos
                z_fondo_t1 = z0 + (n1 - 1) * r - tv1
                prism([(a_end1, z_fondo_t1), (a_end1 + NUDO_ANCHO, z_fondo_t1), (a_end1 + NUDO_ANCHO, zL), (a_end1, zL)], B_T1[0], B_T1[1], "{}|NUDO_PRISMATICO_J2".format(nm))
                z_fondo_t2 = zL - tv2
                prism([(a_L2, z_fondo_t2), (a_L2 + NUDO_ANCHO, z_fondo_t2), (a_L2 + NUDO_ANCHO, zL), (a_L2, zL)], B_T2[0], B_T2[1], "{}|NUDO_PRISMATICO_J2B".format(nm))
                z_fondo_ll = z1 - r - tv2
                prism([(a_ini2 - NUDO_ANCHO, z_fondo_ll), (a_ini2, z_fondo_ll), (a_ini2, z1 - ESP), (a_ini2 - NUDO_ANCHO, z1 - ESP)], B_T2[0], B_T2[1], "{}|NUDO_PRISMATICO_J1".format(nm))   # hasta el fondo de la plataforma (sin hueco)
                hechas.append({"pieza": "{}|peldanos y nudos".format(nm), "modelos_genericos": 5})
            tx.Commit()
            OUT = {"estado": "ESCALERA CREADA", "borrados": {"pisos": len(viejos_pisos), "modelos_genericos": len(viejos_gen)},
                   "piezas": hechas, "siguiente": "Revisar en 3D (tramos, descansos y plataformas); luego nodo 9B y nodo 13."}
        except Exception:
            if tx.HasStarted(): tx.RollBack()
            raise
except Exception as error:
    OUT = {"estado": "ERROR - no se completo la operacion", "detalle": str(error)}
