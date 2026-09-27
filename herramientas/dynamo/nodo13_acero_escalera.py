# -*- coding: utf-8 -*-
"""
SAN JERONIMO - NODO 13 - ACERO DE LA ESCALERA (Revit 2027) - R1
Memoria seccion 5: losa de 15 cm, gobierna el minimo -> malla fi 3/8" @ 25 cm en
ambos sentidos. Recubrimiento 2 cm (losas, E.060 7.7.1).

Se arman los 16 pisos estructurales marcados SJ_ESCALERA_CONCRETO:
  4 x LOSA_T1 y 4 x LOSA_T2 (tramos inclinados), 4 x DESCANSO_J2, 4 x EXTENSION_PLATAFORMA_J1.
  - Malla INFERIOR en los dos sentidos, recortada al contorno REAL de cada pieza
    (se mide la cara inferior; separacion <= 25 cm; 2.5 cm a los bordes).
  - Capa 1 (abajo): barras en el sentido de la escalera. Capa 2: transversales.
  - ANCLAJE de las barras longitudinales de cada tramo inclinado (E.060 12 / detalle
    clasico de escaleras): en el extremo BAJO doblan y entran 50 cm horizontales en el
    descanso/plataforma; en el extremo ALTO entran al nudo de encuentro, suben hasta la
    capa superior del descanso/plataforma y doblan 40 cm horizontales ARRIBA (nunca
    siguiendo el quiebre por abajo: la traccion empujaria el recubrimiento).
  - ACERO SUPERIOR de los tramos: fi 3/8" @ 25 corrido (luces < 3 m), anclado en cada extremo.
  - ARRANQUE DEL PRIMER TRAMO sobre el cimiento (nodo 9B), como en la fig. 107 del Manual del
    Maestro Constructor (Aceros Arequipa): el acero INFERIOR llega recto hasta el arranque, que
    queda embebido en el bloque (mas de 15 cm dentro del apoyo); el acero SUPERIOR es el que
    BAJA al cimiento, vertical junto a su cara posterior casi hasta el fondo. Como el bloque se
    vacia antes que la escalera, esa barra es una MECHA que sale del cimiento y traslapa 45 cm
    con la barra superior del tramo.
  - AUTOVERIFICACION contra el acero ya colocado (columnas, zapatas, vigas) y entre si.

IN[0] = RUN: False = previsualizar; True = crear
IN[1] = (opcional) PRUEBA: numero de piezas. Orden: un tramo T1, un T2, un descanso, una
        plataforma, resto. 0 o vacio = todas.
"""

import clr
import math

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Curve, ElementId, FilteredElementCollector, Floor,
    GeometryInstance, Line, Options, PlanarFace, Solid, Transaction, XYZ,
)
from Autodesk.Revit.DB.Structure import (
    BarTerminationsData, MultiplanarOption, Rebar, RebarBarType,
    RebarHookType, RebarHostData, RebarStyle, RebarTerminationOrientation,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

clr.AddReference("System")
from System.Collections.Generic import List

doc = DocumentManager.Instance.CurrentDBDocument

# ------------------------------ DATOS ------------------------------
MARKER = "SJ_ACERO_ESCALERA_R1"
PREFIJO_PISOS = "SJ_ESCALERA_CONCRETO"
M = 1.0 / 0.3048
D38 = 0.009525 * M
D34 = 0.01905 * M
BAR_NAMES = {"3/8": ("SJ_3/8in_G60", D38)}
COVER = 0.025 * M                 # recubrimiento de losa (2.5 cm, revision de planos)
BORDE = 0.025 * M                 # a los bordes de la pieza
SEP = 0.25 * M                    # malla @ 25 cm
PATA_BAJA = 0.50 * M              # entrada horizontal en el descanso inferior
PATA_ALTA = 0.40 * M              # doblez horizontal arriba en el descanso superior
TRASLAPE_38 = 0.45 * M            # traslape clase B de fi 3/8" (1.3 x 35.3 db = 44 cm)
MECHA_EMPOTRE = 0.50 * M          # tramo vertical de la mecha dentro del cimiento
MECHA_GANCHO = 0.20 * M           # gancho de 90 de la mecha (12 db + radio), hacia el interior del bloque
CIMIENTOS = []                    # se llena en MAIN con los cimientos de escalera medidos
MECHAS_INFERIORES = False         # fig. 107: el acero inferior NO baja al cimiento
ACERO_SUPERIOR = True             # acero superior corrido en los tramos inclinados (False = solo la malla de la memoria)
# -------------------------------------------------------------------


def id_value(eid):
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def bar_diameter(bt):
    for attr in ("BarNominalDiameter", "BarModelDiameter", "BarDiameter"):
        try:
            return getattr(bt, attr)
        except Exception:
            pass
    return None


def find_bar_type(diam_ft, nombre=None):
    """1) el tipo propio del proyecto por NOMBRE (SJ_...); 2) cualquier tipo con
    diametro EXACTO (0.05 mm). Un tipo generico de diametro parecido (p.ej. 13 mm
    por 1/2") NO se acepta: se crea el tipo SJ con el diametro y doblados correctos."""
    candidatos = list(FilteredElementCollector(doc).OfClass(RebarBarType))
    if nombre:
        for bt in candidatos:
            try:
                if bt.Name == nombre:
                    d = bar_diameter(bt)
                    if d is not None and abs(d - diam_ft) <= 0.0006 * M:
                        return bt
            except Exception:
                pass
    if nombre:
        # con nombre propio definido NO se aceptan tipos ajenos aunque el diametro
        # coincida: no se conocen sus diametros de doblado. Se creara el tipo SJ.
        return None
    for bt in candidatos:
        d = bar_diameter(bt)
        if d is not None and abs(d - diam_ft) <= 0.00005 * M:
            return bt
    return None


def create_bar_type(name, diam_ft):
    """Solo dentro de transaccion activa."""
    bt = RebarBarType.Create(doc)
    for attr in ("BarNominalDiameter", "BarModelDiameter", "BarDiameter"):
        try:
            setattr(bt, attr, diam_ft)
        except Exception:
            pass
    # Diametros de doblado E.060 (7.2): 6 db barras hasta 1"; 4 db estribos hasta 5/8".
    # Cada uno en su try: si Revit rechaza un valor, conserva el que trae por defecto.
    for attr, factor in (("StandardBendDiameter", 6.0),
                         ("StandardHookBendDiameter", 6.0),
                         ("StirrupTieBendDiameter", 4.0)):
        try:
            setattr(bt, attr, factor * diam_ft)
        except Exception:
            pass
    try:
        bt.Name = name
    except Exception:
        pass
    d = bar_diameter(bt)
    if d is None or abs(d - diam_ft) > 0.0006 * M:
        raise ValueError("no se pudo fijar el diametro del tipo de barra {} "
                         "(quedo en {}). No se creo ninguna armadura.".format(name, d))
    return bt


def find_hook_135():
    best = None
    for h in FilteredElementCollector(doc).OfClass(RebarHookType):
        try:
            if h.Style != RebarStyle.StirrupTie:
                continue
            if abs(h.HookAngle - math.radians(135.0)) > 0.02:
                continue
        except Exception:
            continue
        name = (h.Name or "").lower()
        if best is None or "ism" in name:       # Seismic / Sismico
            best = h
    return best


def create_hook_135():
    h = RebarHookType.Create(doc, math.radians(135.0), 8.0)   # E.060: 8 db
    try:
        h.Style = RebarStyle.StirrupTie
    except Exception:
        pass
    try:
        h.Name = "SJ_Estribo_Sismico_135"
    except Exception:
        pass
    if h.Style != RebarStyle.StirrupTie:
        raise ValueError("no se pudo asignar estilo Estribo al gancho de 135. "
                         "No se creo ninguna armadura.")
    return h


def terminations(hook_id=None, o_start=None, o_end=None):
    try:
        t = BarTerminationsData(doc)
    except TypeError:
        t = BarTerminationsData()
    if hook_id is not None:
        t.HookTypeIdAtStart = hook_id
        t.HookTypeIdAtEnd = hook_id
        t.TerminationOrientationAtStart = o_start
        t.TerminationOrientationAtEnd = o_end
    return t


def set_comment(el, text):
    p = el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is not None and not p.IsReadOnly:
        p.Set(text)


def get_comment(el):
    try:
        if not el.IsValidObject:
            return ""
        p = el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        return (p.AsString() or "") if p is not None else ""
    except Exception:
        return ""



def make_curves(points):
    lst = List[Curve]()
    for a, b in zip(points[:-1], points[1:]):
        lst.Add(Line.CreateBound(a, b))
    return lst




def _seg_dist(p1, q1, p2, q2):
    """Distancia minima entre dos segmentos 3D (tuplas)."""
    def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    def clamp(x): return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
    d1, d2, r = sub(q1, p1), sub(q2, p2), sub(p1, p2)
    a, e, f_ = dot(d1, d1), dot(d2, d2), dot(d2, r)
    if a < 1e-12 and e < 1e-12:
        s_, t_ = 0.0, 0.0
    elif a < 1e-12:
        s_, t_ = 0.0, clamp(f_ / e)
    else:
        c = dot(d1, r)
        if e < 1e-12:
            t_, s_ = 0.0, clamp(-c / a)
        else:
            b_ = dot(d1, d2)
            den = a * e - b_ * b_
            s_ = clamp((b_ * f_ - c * e) / den) if den > 1e-12 else 0.0
            t_ = (b_ * s_ + f_) / e
            if t_ < 0.0:
                t_, s_ = 0.0, clamp(-c / a)
            elif t_ > 1.0:
                t_, s_ = 1.0, clamp((b_ - c) / a)
    w = (p1[0] + d1[0] * s_ - p2[0] - d2[0] * t_,
         p1[1] + d1[1] * s_ - p2[1] - d2[1] * t_,
         p1[2] + d1[2] * s_ - p2[2] - d2[2] * t_)
    return math.sqrt(dot(w, w))




# ======================= geometria medida =======================
def v3(p):
    return (p.X, p.Y, p.Z)


class Registry(object):
    def __init__(self):
        self.segs = []          # (p, q, radio, lo, hi)

    def add(self, p, q, r, src=""):
        lo = (min(p[0], q[0]) - r, min(p[1], q[1]) - r, min(p[2], q[2]) - r)
        hi = (max(p[0], q[0]) + r, max(p[1], q[1]) + r, max(p[2], q[2]) + r)
        self.segs.append((p, q, r, lo, hi, src))

    def add_poly(self, pts, r, src=""):
        for a, b in zip(pts[:-1], pts[1:]):
            self.add(a, b, r, src)

    def local(self, lo, hi):
        """sub-registro con lo que toca la caja [lo, hi] (para probar muchos candidatos rapido)."""
        sub = Registry()
        for it in self.segs:
            lo2, hi2 = it[3], it[4]
            if lo[0] > hi2[0] or hi[0] < lo2[0] or lo[1] > hi2[1] or hi[1] < lo2[1] or lo[2] > hi2[2] or hi[2] < lo2[2]:
                continue
            sub.segs.append(it)
        return sub

    def worst(self, pts, r, tol):
        """mayor penetracion de la polilinea contra lo registrado (<=0 = libre)."""
        peor, quien = -1e9, ""
        for a, b in zip(pts[:-1], pts[1:]):
            lo = (min(a[0], b[0]) - r - tol, min(a[1], b[1]) - r - tol, min(a[2], b[2]) - r - tol)
            hi = (max(a[0], b[0]) + r + tol, max(a[1], b[1]) + r + tol, max(a[2], b[2]) + r + tol)
            for (p, q, r2, lo2, hi2, src) in self.segs:
                if lo[0] > hi2[0] or hi[0] < lo2[0] or lo[1] > hi2[1] or hi[1] < lo2[1] or lo[2] > hi2[2] or hi[2] < lo2[2]:
                    continue
                pen = (r + r2 + tol) - _seg_dist(a, b, p, q)
                if pen > peor:
                    peor, quien = pen, src
        return peor, quien



def _solids_inst(el):
    out = []
    geo = el.get_Geometry(Options())
    if geo is None:
        return out
    for g in geo:
        if isinstance(g, Solid):
            if g.Volume > 1e-9:
                out.append(g)
        elif isinstance(g, GeometryInstance):
            for s in g.GetInstanceGeometry():
                if isinstance(s, Solid) and s.Volume > 1e-9:
                    out.append(s)
    return out


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def unit(a):
    n = math.sqrt(dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def piece_frame(f):
    """Mide la pieza: cara inferior (poligono 3D), normal hacia arriba y espesor."""
    sup, inf = None, None
    for s in _solids_inst(f):
        for face in s.Faces:
            if not isinstance(face, PlanarFace):
                continue
            nz = face.FaceNormal.Z
            if nz > 0.3 and (sup is None or face.Area > sup.Area):
                sup = face
            if nz < -0.3 and (inf is None or face.Area > inf.Area):
                inf = face
    if sup is None or inf is None:
        raise ValueError("no se encontraron las caras superior e inferior")
    n = unit(v3(sup.FaceNormal))
    poly = []
    loops = list(inf.GetEdgesAsCurveLoops())
    loop = max(loops, key=lambda lp: sum(1 for _ in lp))
    for c in loop:
        poly.append(v3(c.GetEndPoint(0)))
    psup = None
    for lp in sup.GetEdgesAsCurveLoops():
        for c in lp:
            psup = v3(c.GetEndPoint(0))
            break
        break
    esp = abs(dot(add(psup, poly[0], -1.0), n))
    inclinada = n[2] < 0.995
    return {"el": f, "n": n, "poly": poly, "esp": esp, "inclinada": inclinada,
            "zmin": min(p[2] for p in poly), "zmax": max(p[2] for p in poly) + esp}


def set_axes(fr, run_h):
    """e1 = sentido de la escalera dentro del plano de la pieza (hacia arriba si es inclinada)."""
    n = fr["n"]
    if fr["inclinada"]:
        h = unit((-n[0], -n[1], 0.0))
        c, s = n[2], math.sqrt(max(0.0, 1.0 - n[2] * n[2]))
        e1 = (h[0] * c, h[1] * c, s)
        fr["h"] = h
    else:
        e1 = unit((run_h[0], run_h[1], 0.0))
        fr["h"] = e1
    e2 = unit(cross(n, e1))
    fr["e1"], fr["e2"], fr["P0"] = e1, e2, fr["poly"][0]
    fr["uv"] = [(dot(add(p, fr["P0"], -1.0), e1), dot(add(p, fr["P0"], -1.0), e2)) for p in fr["poly"]]


def P(fr, u, v, w):
    return add(add(add(fr["P0"], fr["e1"], u), fr["e2"], v), fr["n"], w)


def intervals(uv, along_u, c):
    """intersecciones de la recta (v=c si along_u; u=c si no) con el poligono -> [(a0,a1)]"""
    xs = []
    n = len(uv)
    for i in range(n):
        a, b = uv[i], uv[(i + 1) % n]
        if along_u:
            ca, cb, va, vb = a[1], b[1], a[0], b[0]
        else:
            ca, cb, va, vb = a[0], b[0], a[1], b[1]
        if (ca - c) * (cb - c) < 0 or (abs(ca - c) < 1e-12 and abs(cb - c) > 1e-12 and cb > c) or \
                (abs(cb - c) < 1e-12 and abs(ca - c) > 1e-12 and ca > c):
            t = (c - ca) / (cb - ca)
            xs.append(va + t * (vb - va))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def inside_uv(uv, u, v):
    ins = False
    n = len(uv)
    for i in range(n):
        a, b = uv[i], uv[(i + 1) % n]
        if (a[1] > v) != (b[1] > v):
            if u < a[0] + (v - a[1]) / (b[1] - a[1]) * (b[0] - a[0]):
                ins = not ins
    return ins


def flat_piece_at(frames, pt, z_ref):
    """pieza HORIZONTAL cuya planta contiene pt (x,y) y cuya cota es cercana a z_ref"""
    for g in frames:
        if g["inclinada"]:
            continue
        if abs(g["poly"][0][2] - z_ref) > 0.25 * M:
            continue
        w = add((pt[0], pt[1], g["P0"][2]), g["P0"], -1.0)
        if inside_uv(g["uv"], dot(w, g["e1"]), dot(w, g["e2"])):
            return g
    return None


def plan_piece(fr, frames):
    """Devuelve la lista de barras de la pieza: [(tag, [puntos 3D], anfitrion o None)] sin crear nada."""
    bars = []
    extras = []
    d = D38
    us = [p[0] for p in fr["uv"]]
    vs = [p[1] for p in fr["uv"]]
    w1 = COVER + d / 2.0
    w2 = COVER + d + d / 2.0
    # ---- capa 1: barras en el sentido de la escalera (a lo largo de e1) ----
    W = (max(vs) - min(vs)) - 2 * BORDE
    n1 = max(2, int(math.ceil(W / SEP - 1e-6)) + 1)
    sp1 = W / float(n1 - 1)
    for i in range(n1):
        v = min(vs) + BORDE + i * sp1
        for (a0, a1) in intervals(fr["uv"], True, v):
            if a1 - a0 < 0.30 * M:
                continue
            pts = [P(fr, a0 + BORDE, v, w1), P(fr, a1 - BORDE, v, w1)]
            if fr["inclinada"]:
                h = fr["h"]
                sin_t = fr["e1"][2]
                # extremo BAJO: entra horizontal en la pieza inferior, a la cota de SU capa 1
                lo = pts[0]
                g = flat_piece_at(frames, add(lo, h, -0.20 * M), lo[2])
                if g is not None and sin_t > 1e-6:
                    z_t = g["poly"][0][2] + COVER + d / 2.0
                    du = (z_t - lo[2]) / sin_t
                    if 0.0 <= du < 0.90 * M:
                        k = P(fr, a0 + BORDE + du, v, w1)
                        pts = [add(k, h, -PATA_BAJA), k] + pts[1:]
                elif g is None and MECHAS_INFERIORES:
                    # (OPCIONAL, APAGADO: en la fig. 107 el acero INFERIOR no baja al cimiento; llega recto al arranque,
                    # que ya esta embebido en el bloque mas de 15 cm, E.060 12.11.1)
                    # El cimiento se vacia ANTES que la escalera, asi que
                    # el acero del tramo no puede "bajar" dentro de el: del cimiento deben salir MECHAS
                    # (Manual del Maestro Constructor, Aceros Arequipa, 15.3 / fig. 111) ancladas con gancho de
                    # 90 en el bloque, que suben y TRASLAPAN con las barras del fondo del tramo.
                    for cz in CIMIENTOS:
                        wx, wy = lo[0] - cz["O"][0], lo[1] - cz["O"][1]
                        fx = wx * cz["bx"][0] + wy * cz["bx"][1]
                        fy = wx * cz["by"][0] + wy * cz["by"][1]
                        c_ = 0.070 * M
                        if (cz["x0"] + c_ <= fx <= cz["x1"] - c_ and cz["y0"] + c_ <= fy <= cz["y1"] - c_
                                and cz["z1"] > lo[2] - 0.15 * M and cz["z0"] < lo[2] - MECHA_EMPOTRE - 0.075 * M):
                            lado = 1.0 if v < (min(vs) + max(vs)) / 2.0 else -1.0
                            k = add(lo, fr["e2"], lado * (d + 0.002 * M))      # al costado de la barra del tramo
                            c0 = (k[0], k[1], k[2] - MECHA_EMPOTRE)
                            mecha = [add(c0, h, MECHA_GANCHO), c0, k, add(k, fr["e1"], TRASLAPE_38)]
                            extras.append(("MECHA{}".format(i + 1), mecha, cz["el"]))
                            break
                # extremo ALTO. El descanso de arriba tiene su cara inferior MAS ALTA que el fondo del
                # tramo (encuentro tipo contrapaso, cerrado por el nudo prismatico). Seguir la pendiente
                # dejaria la barra en el aire bajo el descanso; por eso: avanza 6 cm dentro del nudo,
                # SUBE VERTICAL hasta la capa superior del descanso y dobla horizontal ARRIBA.
                hi = pts[-1]
                g = flat_piece_at(frames, add(hi, h, 0.20 * M), hi[2])
                if g is not None and sin_t > 1e-6:
                    z_t = g["poly"][0][2] + g["esp"] - COVER - d / 2.0
                    cos_t = math.sqrt(max(1e-12, 1.0 - sin_t * sin_t))
                    k1 = P(fr, a1 + 0.06 * M / cos_t, v, w1)          # 6 cm (en planta) pasado el borde del tramo
                    if 0.05 * M < z_t - k1[2] < 0.60 * M:
                        k2 = (k1[0], k1[1], z_t)
                        pts = pts[:-1] + [k1, k2, add(k2, h, PATA_ALTA)]
            bars.append(("L{}".format(i + 1), pts, None))
    # ---- ACERO SUPERIOR de los tramos inclinados (negativo en los apoyos) ----
    # Practica y guias de diseno de escaleras: As(-) = As(+)/3 a As(+)/2 en los apoyos; en luces menores
    # de 3 m se corre en toda la longitud. Aqui As(+) ya es el minimo, asi que arriba va tambien fi 3/8" @ 25,
    # corrido, anclado en cada extremo:
    #   - extremo ALTO : entra al nudo, sube a la capa superior del descanso y dobla 40 cm (como el inferior).
    #   - extremo BAJO sobre descanso/plataforma: CRUZA al fondo de esa pieza (sigue la pendiente hacia abajo)
    #     y dobla 35 cm horizontales; nunca sigue el quiebre por arriba (reventaria el recubrimiento).
    #   - extremo BAJO sobre el CIMIENTO: mecha superior que sale del bloque (gancho + 50 cm) y traslapa 45 cm.
    if fr["inclinada"] and ACERO_SUPERIOR:
        h = fr["h"]
        sin_t = fr["e1"][2]
        cos_t = math.sqrt(max(1e-12, 1.0 - sin_t * sin_t))
        w_t = fr["esp"] - COVER - d / 2.0
        for i in range(n1):
            v0 = min(vs) + BORDE + i * sp1
            v = v0 + 0.04 * M if v0 + 0.04 * M <= max(vs) - BORDE else v0 - 0.04 * M
            for (a0, a1) in intervals(fr["uv"], True, v):
                if a1 - a0 < 0.30 * M:
                    continue
                # Las caras extremas del tramo son VERTICALES: al subir a la capa superior (a lo largo de
                # la normal) el punto se corre hacia atras w*sen(t). Se compensa para que el arranque de la
                # barra quede dentro de la losa, a BORDE de la cara extrema.
                tan_t = sin_t / cos_t
                lo = P(fr, a0 + BORDE + w_t * tan_t, v, w_t)
                hi = P(fr, a1 - BORDE, v, w_t)
                pts = [lo, hi]
                g = flat_piece_at(frames, add(hi, h, 0.20 * M), hi[2])
                if g is not None:
                    z_t = g["poly"][0][2] + g["esp"] - COVER - d / 2.0
                    # subida dentro del nudo, a 10 cm EN PLANTA pasado el borde del tramo
                    k1 = P(fr, a1 + (0.10 * M + w_t * sin_t) / cos_t, v, w_t)
                    if 0.03 * M < z_t - k1[2] < 0.60 * M:
                        k2 = (k1[0], k1[1], z_t)
                        pts = [lo, k1, k2, add(k2, h, PATA_ALTA)]
                g = flat_piece_at(frames, add(lo, h, -0.20 * M), lo[2])
                if g is not None:
                    z_b = g["poly"][0][2] + COVER + 2 * d + d / 2.0
                    du = (lo[2] - z_b) / sin_t if sin_t > 1e-6 else -1.0
                    if 0.0 < du < 0.50 * M:
                        k = P(fr, a0 + BORDE + w_t * tan_t - du, v, w_t)
                        pts = [add(k, h, -0.35 * M), k] + pts[1:]
                else:
                    # ARRANQUE SOBRE EL CIMIENTO (nodo 9B), como en la fig. 107 del Manual del Maestro Constructor:
                    # el acero SUPERIOR es el que baja al cimiento. Como el bloque se vacia antes, es una MECHA:
                    # nace casi en el fondo del bloque, sube vertical junto a su cara posterior (7.5 cm de
                    # recubrimiento), dobla siguiendo la capa superior del tramo y traslapa 45 cm con la barra superior.
                    for cz in CIMIENTOS:
                        wx, wy = lo[0] - cz["O"][0], lo[1] - cz["O"][1]
                        fx = wx * cz["bx"][0] + wy * cz["bx"][1]
                        fy = wx * cz["by"][0] + wy * cz["by"][1]
                        if not (cz["x0"] <= fx <= cz["x1"] and cz["y0"] <= fy <= cz["y1"]):
                            continue
                        hx = h[0] * cz["bx"][0] + h[1] * cz["bx"][1]
                        hy = h[0] * cz["by"][0] + h[1] * cz["by"][1]
                        if abs(hx) >= abs(hy):
                            atras = (fx - cz["x0"]) if hx > 0 else (cz["x1"] - fx)
                        else:
                            atras = (fy - cz["y0"]) if hy > 0 else (cz["y1"] - fy)
                        retro = atras - (0.16 * M + d / 2.0)             # rama vertical a 16 cm de la cara posterior (bajo el arranque del tramo)
                        if retro < 0:
                            continue
                        # recubrimiento LATERAL de la mecha en el bloque: >= 5 cm; si no, esa barra no baja como mecha
                        if abs(hx) >= abs(hy):
                            lat = min(fy - cz["y0"], cz["y1"] - fy)
                        else:
                            lat = min(fx - cz["x0"], cz["x1"] - fx)
                        if lat < 0.05 * M + d / 2.0:
                            continue
                        lado = -1.0 if v < (min(vs) + max(vs)) / 2.0 else 1.0
                        off = lado * (d + 0.002 * M)
                        lo_m = add(lo, fr["e2"], off)
                        k = add(lo_m, fr["e1"], -retro / cos_t)          # sigue la capa superior hacia atras y abajo
                        z_bajo = cz["z0"] + 0.10 * M
                        if k[2] > cz["z1"] - 0.015 * M or k[2] - z_bajo < 0.30 * M:
                            continue
                        extras.append(("MECHA_SUP{}".format(i + 1),
                                       [(k[0], k[1], z_bajo), k, add(lo_m, fr["e1"], TRASLAPE_38)], cz["el"]))
                        break
                bars.append(("S{}".format(i + 1), pts, None))
    # ---- capa 2: transversales (a lo largo de e2) ----
    Wu = (max(us) - min(us)) - 2 * BORDE
    n2 = max(2, int(math.ceil(Wu / SEP - 1e-6)) + 1)
    sp2 = Wu / float(n2 - 1)
    for i in range(n2):
        u = min(us) + BORDE + i * sp2
        for (a0, a1) in intervals(fr["uv"], False, u):
            if a1 - a0 < 0.30 * M:
                continue
            bars.append(("T{}".format(i + 1), [P(fr, u, a0 + BORDE, w2), P(fr, u, a1 - BORDE, w2)], None))
    return bars + extras, (n1, sp1, n2, sp2)


def existing_segments():
    out = []
    for r in FilteredElementCollector(doc).OfClass(Rebar):
        com = get_comment(r)
        if not com.startswith("SJ_ACERO_") or com.startswith(MARKER):
            continue
        d = None
        try:
            d = bar_diameter(doc.GetElement(r.GetTypeId()))
        except Exception:
            pass
        d = d or D34
        base = None
        for args in ((False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, 0),
                     (False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, 0, False)):
            try:
                curves = r.GetCenterlineCurves(*args)
            except Exception:
                continue
            base = []
            for c in curves:
                t = list(c.Tessellate())
                if len(t) > 4:
                    n_ = len(t) - 1
                    t = [t[0], t[n_ // 3], t[(2 * n_) // 3], t[n_]]
                for p, q in zip(t[:-1], t[1:]):
                    base.append((p, q))
            break
        if base is None:
            continue
        n = 1
        try:
            n = int(r.NumberOfBarPositions)
        except Exception:
            n = 1
        if n <= 1:
            for p, q in base:
                out.append((v3(p), v3(q), d / 2.0, com.split("|", 2)[-1]))
            continue
        try:
            acc = r.GetShapeDrivenAccessor()
            for i in range(n):
                T = acc.GetBarPositionTransform(i)
                for p, q in base:
                    out.append((v3(T.OfPoint(p)), v3(T.OfPoint(q)), d / 2.0, com.split("|", 2)[-1]))
        except Exception:
            for p, q in base:
                out.append((v3(p), v3(q), d / 2.0, com.split("|", 2)[-1]))
    return out


def make_bar(host, pts, bar_type, tag):
    PX = [XYZ(p[0], p[1], p[2]) for p in pts]
    normal = None
    d1 = add(pts[1], pts[0], -1.0)
    for a, b in zip(pts[:-1], pts[1:]):
        cx = cross(d1, add(b, a, -1.0))
        nn = math.sqrt(dot(cx, cx))
        if nn > 1e-9:
            normal = XYZ(cx[0] / nn, cx[1] / nn, cx[2] / nn)
            break
    if normal is None:
        aux = (0.0, 0.0, 1.0) if abs(unit(d1)[2]) < 0.9 else (1.0, 0.0, 0.0)
        cx = unit(cross(d1, aux))
        normal = XYZ(cx[0], cx[1], cx[2])
    rb = Rebar.CreateFromCurves(doc, RebarStyle.Standard, bar_type, host, normal,
                                make_curves(PX), terminations(), True, True)
    if rb is None:
        raise ValueError("CreateFromCurves devolvio None ({})".format(tag))
    set_comment(rb, "{}|{}|{}".format(MARKER, id_value(host.Id), tag))
    return rb


# ============================== MAIN ==============================
try:
    run = bool(IN[0])
    limite = 0
    try:
        if len(IN) > 1 and IN[1] is not None:
            limite = int(IN[1])
    except Exception:
        limite = 0

    frames, problemas = [], []
    for f in FilteredElementCollector(doc).OfClass(Floor):
        com = get_comment(f)
        if not com.startswith(PREFIJO_PISOS):
            continue
        try:
            if not RebarHostData.GetRebarHostData(f).IsValidHost():
                raise ValueError("no acepta armadura (debe ser piso ESTRUCTURAL de hormigon)")
            fr = piece_frame(f)
            fr["com"] = com
            fr["clase"] = com.split("|")[-1]
            frames.append(fr)
        except Exception as ex:
            problemas.append("piso id {} [{}]: {}".format(id_value(f.Id), com, ex))

    for cz in (FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFoundation)
               .WhereElementIsNotElementType()):
        if not get_comment(cz).startswith("SJ_CIMIENTO_ESCALERA"):
            continue
        try:
            xs, ys = [], []
            for g_ in cz.GetOriginalGeometry(Options()):
                if isinstance(g_, Solid) and g_.Volume > 1e-9:
                    for e_ in g_.Edges:
                        for p_ in e_.Tessellate():
                            xs.append(p_.X); ys.append(p_.Y)
            T_ = cz.GetTransform()
            bb_ = cz.get_BoundingBox(None)
            CIMIENTOS.append({"el": cz, "O": (T_.Origin.X, T_.Origin.Y), "bx": (T_.BasisX.X, T_.BasisX.Y),
                              "by": (T_.BasisY.X, T_.BasisY.Y), "x0": min(xs), "x1": max(xs),
                              "y0": min(ys), "y1": max(ys), "z0": bb_.Min.Z, "z1": bb_.Max.Z})
        except Exception as ex:
            problemas.append("cimiento de escalera id {}: {}".format(id_value(cz.Id), ex))

    run_h = (1.0, 0.0, 0.0)
    for fr in frames:
        if fr["inclinada"]:
            n = fr["n"]
            run_h = unit((abs(n[0]), abs(n[1]) * (1 if n[0] * n[1] >= 0 else -1), 0.0))
            break
    for fr in frames:
        set_axes(fr, run_h)

    orden = {"LOSA_T1": 0, "LOSA_T2": 1, "DESCANSO_J2": 2, "EXTENSION_PLATAFORMA_J1": 3}
    frames.sort(key=lambda t: (t["com"]))
    cabeza, vistos = [], set()
    # para la prueba: T1 y T2 de un tramo que SI tenga descanso abajo (no el arranque en terreno)
    for fr in sorted(frames, key=lambda t: (orden.get(t["clase"], 9), -t["zmin"] if False else t["zmin"])):
        if fr["clase"] not in vistos and (fr["clase"] != "LOSA_T1" or fr["zmin"] > 1.0 * M):
            vistos.add(fr["clase"])
            cabeza.append(fr)
    frames_ord = cabeza + [fr for fr in frames if fr not in cabeza]

    planes = {}
    resumen = []
    for fr in frames_ord:
        bars, (n1, sp1, n2, sp2) = plan_piece(fr, frames)
        planes[id_value(fr["el"].Id)] = bars
        con_pata = sum(1 for t, p, hst in bars if t.startswith("L") and len(p) > 2)
        n_mechas = sum(1 for t, p, hst in bars if t.startswith("MECHA"))
        n_sup = sum(1 for t, p, hst in bars if t.startswith("S"))
        resumen.append({"id": id_value(fr["el"].Id), "pieza": fr["com"].split("|", 1)[-1],
                        "espesor_m": round(fr["esp"] / M, 3),
                        "pendiente_grados": round(math.degrees(math.acos(min(1.0, fr["n"][2]))), 1),
                        "longitudinales": "{} @ {:.1f} cm".format(n1, sp1 / M * 100),
                        "transversales": "{} @ {:.1f} cm".format(n2, sp2 / M * 100),
                        "longitudinales_con_anclaje_doblado": con_pata,
                        "superiores_corridas": n_sup,
                        "mechas_desde_el_cimiento": n_mechas})

    existentes = list(FilteredElementCollector(doc).OfClass(Rebar))
    propias = [r for r in existentes if get_comment(r).startswith(MARKER)]
    tipos = dict((k, find_bar_type(v[1], v[0])) for k, v in BAR_NAMES.items())
    segs = existing_segments()
    conteo = {}
    for fr in frames:
        conteo[fr["clase"]] = conteo.get(fr["clase"], 0) + 1

    if not run:
        OUT = {
            "estado": "PREVISUALIZACION - no se modifico el modelo",
            "piezas (esperado 4 de cada clase, 16 en total)": conteo,
            "barras_previstas": sum(len(b) for b in planes.values()),
            "acero_existente_leido (segmentos)": len(segs),
            "cimiento_de_arranque_detectado (nodo 9B)": len(CIMIENTOS),
            "piezas_detalle": resumen,
            "problemas": problemas,
            "tipos_de_barra": dict((k, (tipos[k].Name if tipos[k] else "NO EXISTE -> se creara")) for k in tipos),
            "armaduras_de_este_nodo_ya_en_modelo (se reemplazan)": len(propias),
            "accion": "IN[0]=True con IN[1]=4 (una pieza de cada clase); revisar en 3D; luego IN[1]=0.",
        }
    else:
        try:
            TransactionManager.Instance.ForceCloseTransaction()
        except Exception:
            pass
        tx = Transaction(doc, "San Jeronimo - acero de escalera")
        tx.Start()
        try:
            import uuid
            from Autodesk.Revit.DB import IFailuresPreprocessor, FailureProcessingResult

            class _SinAdvertencias(IFailuresPreprocessor):
                __namespace__ = "SJ_" + uuid.uuid4().hex

                def PreprocessFailures(self, accessor):
                    accessor.DeleteAllWarnings()
                    return FailureProcessingResult.Continue

            opts = tx.GetFailureHandlingOptions()
            opts.SetFailuresPreprocessor(_SinAdvertencias())
            tx.SetFailureHandlingOptions(opts)
        except Exception:
            pass
        try:
            for k in tipos:
                if tipos[k] is None:
                    tipos[k] = create_bar_type(*BAR_NAMES[k])
            doc.Regenerate()
            borradas = 0
            for r in propias:
                doc.Delete(r.Id)
                borradas += 1
            doc.Regenerate()

            # solo interesa el acero que esta en el volumen de la escalera (el modelo completo
            # tiene decenas de miles de segmentos: se filtra una sola vez)
            xs_ = [p[0] for fr in frames for p in fr["poly"]]
            ys_ = [p[1] for fr in frames for p in fr["poly"]]
            zs_ = [p[2] for fr in frames for p in fr["poly"]]
            caja_lo = (min(xs_) - 0.8 * M, min(ys_) - 0.8 * M, min(zs_) - 0.5 * M)
            caja_hi = (max(xs_) + 0.8 * M, max(ys_) + 0.8 * M, max(zs_) + 0.8 * M)
            reg = Registry()
            for (a, b, rad, src) in segs:
                if (max(a[0], b[0]) < caja_lo[0] or min(a[0], b[0]) > caja_hi[0] or
                        max(a[1], b[1]) < caja_lo[1] or min(a[1], b[1]) > caja_hi[1] or
                        max(a[2], b[2]) < caja_lo[2] or min(a[2], b[2]) > caja_hi[2]):
                    continue
                reg.add(a, b, rad, src)
            import time
            t_ini = time.time()
            avisos = set()
            trabajo = frames_ord[:limite] if limite > 0 else frames_ord
            total, errores, hechas = 0, [], []
            for fr in trabajo:
                fid = id_value(fr["el"].Id)
                try:
                    c = 0
                    for tag, pts, hst in planes[fid]:
                        # comprobacion contra el acero existente y el ya creado; correccion lateral pequena
                        lo = (min(p[0] for p in pts) - 0.1 * M, min(p[1] for p in pts) - 0.1 * M, min(p[2] for p in pts) - 0.1 * M)
                        hi = (max(p[0] for p in pts) + 0.1 * M, max(p[1] for p in pts) + 0.1 * M, max(p[2] for p in pts) + 0.1 * M)
                        loc = reg.local(lo, hi)
                        lat = fr["e2"] if (tag.startswith("L") or tag.startswith("S") or tag.startswith("MECHA")) else fr["e1"]
                        mejor = None
                        for dl in (0.0, 0.010 * M, -0.010 * M, 0.020 * M, -0.020 * M, 0.030 * M, -0.030 * M):
                            cand = [add(p, lat, dl) for p in pts]
                            pen, quien = loc.worst(cand, D38 / 2.0, 0.0)
                            if mejor is None or pen < mejor[0]:
                                mejor = (pen, quien, cand)
                            if pen <= 0.001 * M:
                                break
                        if mejor[0] > 0.0015 * M:
                            avisos.add("pieza {} barra {}: cruce de {:.1f} mm con [{}]; ajustar en obra".format(
                                fid, tag, mejor[0] / M * 1000, mejor[1]))
                        anfitrion = fr["el"]
                        if hst is not None:
                            try:
                                if RebarHostData.GetRebarHostData(hst).IsValidHost():
                                    anfitrion = hst             # la mecha pertenece al cimiento
                            except Exception:
                                pass
                        make_bar(anfitrion, mejor[2], tipos["3/8"], tag)
                        reg.add_poly(mejor[2], D38 / 2.0, "escalera {} {}".format(fid, tag))
                        c += 1
                    total += c
                    hechas.append("{} (id {}): {} barras".format(fr["com"].split("|", 1)[-1], fid, c))
                except Exception as ex:
                    errores.append("pieza id {}: {}".format(fid, ex))
            resultado_commit = str(tx.Commit())
            OUT = {
                "estado": "ACERO DE ESCALERA COLOCADO" if not errores else "COLOCADO CON ERRORES - ver 'errores'",
                "commit": resultado_commit,
                "segundos": int(time.time() - t_ini),
                "acero_cercano_considerado (segmentos)": len(reg.segs),
                "piezas_procesadas": "{} de {}".format(len(trabajo), len(frames)),
                "barras_totales": total,
                "detalle": hechas,
                "armaduras_previas_de_este_nodo_borradas": borradas,
                "avisos": sorted(avisos),
                "errores": errores,
                "problemas_previos": problemas,
                "pendiente_ingeniero": [
                    "Sobrecarga real de la escalera (200 vs 400-500 kg/m2): si sube, la malla minima puede no bastar.",
                    "Acero SUPERIOR de los tramos: la memoria no lo calculo. Se coloco fi 3/8 @ 25 corrido (As- = As+ por ser ambos el minimo; luces < 3 m), anclado en descansos, plataformas y cimiento. Confirmar cuantia; se desactiva con ACERO_SUPERIOR = False.",
                    "Descansos y plataformas: solo llevan la malla inferior de la memoria; confirmar si requieren acero superior propio.",
                    ("Primer tramo (fig. 107 del Manual del Maestro Constructor): el acero superior baja al cimiento como 5 mechas fi 3/8 verticales junto a la cara posterior del bloque, traslapadas 45 cm; el inferior llega recto al arranque embebido." if CIMIENTOS else
                     "Primer tramo (Nivel 1): no se encontro el cimiento de arranque; correr el nodo 9B y repetir este nodo."),
                ],
            }
        except Exception:
            if tx.HasStarted():
                tx.RollBack()
            raise
except Exception as error:
    OUT = {"estado": "ERROR - no se completo la operacion", "detalle": str(error)}
