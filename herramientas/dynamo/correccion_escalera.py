# -*- coding: utf-8 -*-
"""
SAN JERONIMO - CORRECCION ACERO DE ESCALERA (R1) - NODO INDEPENDIENTE
Mueve en VERTICAL 11 barras SJ_ACERO_ESCALERA_R1. No crea, no borra y no cambia
parametros, comentarios, tipos ni ningun otro elemento.
  - T1 de LOSA_T1 en N2-N3, N3-N4 y N4-N5: +20 mm (pasa a la capa 2, encima de la L,
    como indica el NODO 13; recubrimiento 15.8 -> 25 mm).
  - T2..T9 de LOSA_T2 en N1-N2: +1.5 a +6 mm (elimina el cruce con las L).
IN[0] = RUN: False = previsualizar (no toca nada); True = mover.
Seguridad: todo en una sola transaccion; si alguna barra no queda donde debe,
se deshace todo. Si ya se corrigio antes, no hace nada.
"""
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (BuiltInParameter, ElementTransformUtils,
                               FilteredElementCollector, Transaction, XYZ)
from Autodesk.Revit.DB.Structure import MultiplanarOption, Rebar
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

doc = DocumentManager.Instance.CurrentDBDocument
RUN = bool(IN[0]) if len(IN) > 0 else False
MK = "SJ_ACERO_ESCALERA_R1|"
FT = 304.8          # mm por pie
TOL = 0.1           # mm

MOVES = [
    (MK + "231185|T1", 20.0), (MK + "231228|T1", 20.0), (MK + "231271|T1", 20.0),
    (MK + "231152|T2", 1.5), (MK + "231152|T3", 2.0), (MK + "231152|T4", 2.5),
    (MK + "231152|T5", 3.0), (MK + "231152|T6", 4.0), (MK + "231152|T7", 4.5),
    (MK + "231152|T8", 5.5), (MK + "231152|T9", 6.0),
]
REF_T, REF_L = MK + "231185|T1", MK + "231185|L1"   # control de "ya corregido"


def get_comment(el):
    try:
        p = el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        return (p.AsString() or "") if p is not None else ""
    except Exception:
        return ""


def min_z(rb):
    for args in ((False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, 0),
                 (False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, 0, False)):
        try:
            curves = rb.GetCenterlineCurves(*args)
        except Exception:
            continue
        return min(min(c.GetEndPoint(0).Z, c.GetEndPoint(1).Z) for c in curves)
    raise ValueError("No se pudo leer la geometria de la barra id {}".format(rb.Id))


# --- buscar solo las barras necesarias
needed = set(t for t, _ in MOVES) | {REF_L}
found, dup = {}, []
for r in FilteredElementCollector(doc).OfClass(Rebar):
    c = get_comment(r)
    if c in needed:
        if c in found:
            dup.append(c)
        found[c] = r

faltan = sorted(needed - set(found))
log = []

if faltan or dup:
    OUT = {"estado": "DETENIDO - no se modifico nada",
           "no_encontradas": faltan, "duplicadas": sorted(set(dup))}
else:
    z0 = dict((t, min_z(found[t]) * FT) for t in needed)
    ya = z0[REF_T] > z0[REF_L]      # original: T1 9.7 mm por debajo de L1
    plan = ["{}  z={:.1f} mm  ->  +{:.1f} mm".format(t.split("|", 1)[1], z0[t], mm) for t, mm in MOVES]

    if ya:
        OUT = {"estado": "YA ESTABA CORREGIDO - no se modifico nada", "barras": plan}
    elif not RUN:
        OUT = {"estado": "PREVISUALIZACION - no se modifico nada (poner True para mover)",
               "barras_a_mover": plan}
    else:
        try:
            TransactionManager.Instance.ForceCloseTransaction()
        except Exception:
            pass
        tx = Transaction(doc, "San Jeronimo - correccion acero escalera")
        tx.Start()
        try:
            for t, mm in MOVES:
                ElementTransformUtils.MoveElement(doc, found[t].Id, XYZ(0, 0, mm / FT))
            doc.Regenerate()
            malas = []
            for t, mm in MOVES:
                real = min_z(found[t]) * FT - z0[t]
                log.append("{}  movida +{:.1f} mm".format(t.split("|", 1)[1], real))
                if abs(real - mm) > TOL:
                    malas.append("{} (esperado {:.1f}, real {:.1f})".format(t, mm, real))
            ref_ok = abs(min_z(found[REF_L]) * FT - z0[REF_L]) <= TOL
            if malas or not ref_ok:
                tx.RollBack()
                OUT = {"estado": "DESHECHO - Revit no dejo las barras donde debia; el modelo quedo igual",
                       "detalle": malas, "L1_de_referencia_intacta": ref_ok}
            else:
                tx.Commit()
                OUT = {"estado": "CORREGIDO - 11 barras movidas y verificadas", "barras": log}
        except Exception as ex:
            if tx.HasStarted() and not tx.HasEnded():
                tx.RollBack()
            OUT = {"estado": "ERROR - se deshizo todo, el modelo quedo igual", "error": str(ex)}
