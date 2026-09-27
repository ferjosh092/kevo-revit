"""Funciones comunes para todas las laminas (cortes, acero en corte, membrete, hoja, render PDF).
Uso tipico:
    from sheetcommon import *
    M = load_model()                      # model_all.pkl + acero de vigas en posicion de diseno
    doc = new_doc(); add_layers(doc)
    ps = new_sheet(doc, "E-0X")           # hoja A1 841x594 con marco
    ... View(doc, k, offset) para dibujar en modelo (metros), add_vp(...) para ubicar en la hoja ...
    title_block(ps, "E-0X", ["LINEA 1 DEL TITULO", "LINEA 2"])
    save_and_render(doc, ps, "E-0X_Nombre")
"""
import math, pickle, collections
import numpy as np
from shapely.geometry import Polygon, LineString, box, Point
from shapely.ops import unary_union, polygonize
from sheetlib import (new_doc, add_layers, View, section_mark, frame_and_title, ptext, view_title, add_vp, table)

KG = {"1/4": 0.250, "3/8": 0.560, "1/2": 0.994, "5/8": 1.552, "3/4": 2.235}
RAD = {"1/4": 0.00318, "3/8": 0.00476, "1/2": 0.00635, "5/8": 0.00794, "3/4": 0.00953}
W_, H_ = 841, 594


def dstr(d):
    return f'Ø{d}"'


def load_model(path="model_all.pkl", design=True):
    M = pickle.load(open(path, "rb"))
    M["bars_model"] = M["bars"]
    if design:
        from beamdesign import corrected_bars
        M["bars"], M["design_pos"] = corrected_bars(M)
    GU = {k: g["pos"] for k, g in M["grids"].items() if g["dir"] == "v"}
    GV = {k: g["pos"] for k, g in M["grids"].items() if g["dir"] == "u"}
    M["GU"], M["GV"] = GU, GV
    return M


def footprint(el):
    """huella en planta (u,v) de un elemento (poligono shapely)"""
    v, fa = el["v"], el["f"]
    polys = []
    for t in fa:
        p = Polygon(v[t][:, :2])
        if p.area > 1e-8:
            polys.append(p.buffer(1e-5))
    u = unary_union(polys).buffer(-1e-5).simplify(0.002)
    if u.geom_type != "Polygon":
        u = max(u.geoms, key=lambda x: x.area)
    return u


# ------------------------------------------------------------------ cortes
def slice_mesh(V, F, axis, val):
    """Segmentos de la interseccion de una malla con el plano coord[axis]=val.
    axis 0 -> plano u=val, devuelve (v,z); axis 1 -> plano v=val, devuelve (u,z); axis 2 -> plano z=val, devuelve (u,v)."""
    oth = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[axis]
    d = V[:, axis] - val
    segs = []
    for t in F:
        dd = d[t]
        if dd.max() < -1e-9 or dd.min() > 1e-9:
            continue
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = dd[i], dd[j]
            if (a < 0 < b) or (b < 0 < a):
                s = a / (a - b)
                P = V[t[i]] + s * (V[t[j]] - V[t[i]])
                pts.append((P[oth[0]], P[oth[1]]))
            elif abs(a) <= 1e-9:
                pts.append((V[t[i]][oth[0]], V[t[i]][oth[1]]))
        pts = list(dict.fromkeys([(round(float(x), 6), round(float(y), 6)) for x, y in pts]))
        if len(pts) >= 2:
            segs.append(LineString(pts[:2]))
    return segs


def cut_polys(el, axis, val):
    segs = slice_mesh(np.asarray(el["v"], float), el["f"], axis, val)
    if not segs:
        return []
    u = unary_union(list(polygonize(unary_union(segs))))
    if u.is_empty:
        return []
    return [u] if u.geom_type == "Polygon" else [g for g in u.geoms if g.geom_type == "Polygon"]


def draw_cut(v, polys, win, fill=True, layer="E-CORTE", hatch_layer="E-CORTE-ACH", breaks=True):
    W = box(*win)
    edge = W.exterior.buffer(1e-4)
    for p in polys:
        q = p.intersection(W)
        if q.is_empty:
            continue
        for g in ([q] if q.geom_type == "Polygon" else [g for g in getattr(q, "geoms", []) if g.geom_type == "Polygon"]):
            pts = list(g.exterior.coords)[:-1]
            if fill:
                h = v.hatch(pts, hatch_layer)
                for hole in g.interiors:
                    h.paths.add_polyline_path([v.P(*c) for c in list(hole.coords)[:-1]], is_closed=True)
            ring = LineString(list(g.exterior.coords))
            vis = ring.difference(edge)
            for ls in (vis.geoms if hasattr(vis, "geoms") else [vis]):
                if ls.length > 1e-4:
                    v.pline(list(ls.coords), layer)
            for hole in g.interiors:
                v.pline(list(hole.coords), layer)
            if breaks:
                brk = ring.intersection(edge)
                for ls in (brk.geoms if hasattr(brk, "geoms") else [brk]):
                    if ls.geom_type == "LineString" and ls.length > 0.05:
                        c = list(ls.coords)
                        v.break_line(c[0], c[-1])


def cut_elements(v, elements, axis, val, win, cats=None, zmax=None, zmin=None, fill=True):
    """corta todos los elementos (de las categorias dadas) que cruzan el plano y caen en la ventana."""
    lo = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[axis]
    for tag, el in elements.items():
        if cats and el["cat"] not in cats:
            continue
        bb0, bb1 = el["bbox"]
        if not (bb0[axis] - 1e-6 <= val <= bb1[axis] + 1e-6):
            continue
        if bb1[lo[0]] < win[0] or bb0[lo[0]] > win[2] or bb1[lo[1]] < win[1] or bb0[lo[1]] > win[3]:
            continue
        draw_cut(v, cut_polys(el, axis, val), win, fill=fill)


def draw_bars_section(v, blist, axis, val, win, dot_min_mm=0.45, par_tol=0.35, force_dots=False, layer="E-ACERO"):
    """Acero en un corte por el plano coord[axis]=val (axis 0 o 1). Barras que cruzan -> punto;
    casi paralelas al plano (a menos de par_tol) -> proyeccion; estribos -> proyeccion."""
    other = 0 if axis == 1 else 1
    W = box(*win)
    dots = []
    for b in blist:
        pl = np.asarray(b["pl"], float)
        r = RAD.get(b["d"], 0.005)
        if b.get("role", "").startswith("ESTRIBO") and not force_dots:
            if abs(pl[:, axis].mean() - val) < 0.9:
                q = LineString(pl[:, [other, 2]]).intersection(W)
                for g in (q.geoms if hasattr(q, "geoms") else [q]):
                    if g.geom_type == "LineString" and g.length > 1e-4:
                        v.pline(list(g.coords), layer)
            continue
        crossed = False
        for i in range(len(pl) - 1):
            a, c = pl[i], pl[i + 1]
            da, dc = a[axis] - val, c[axis] - val
            seg = c - a
            L = np.linalg.norm(seg)
            if L < 1e-6:
                continue
            if (da <= 0 <= dc or dc <= 0 <= da) and abs(seg[axis]) / L > 0.7:
                s = da / (da - dc) if da != dc else 0
                P = a + s * seg
                pt = (P[other], P[2])
                if W.contains(Point(pt)):
                    dots.append((pt, max(r, dot_min_mm * v.m), b))
                crossed = True
        if crossed:
            continue
        if np.ptp(pl[:, axis]) < 0.08 and abs(pl[:, axis].mean() - val) < par_tol:
            q = LineString(pl[:, [other, 2]]).intersection(W)
            for g in (q.geoms if hasattr(q, "geoms") else [q]):
                if g.geom_type == "LineString" and g.length > 1e-4:
                    v.pline(list(g.coords), layer)
    seen = []
    for pt, r, b in dots:
        if any(abs(pt[0] - s[0]) < 0.004 and abs(pt[1] - s[1]) < 0.004 for s in seen):
            continue
        seen.append(pt)
        v.circle(pt, r, layer, fill=True)
    return dots


def draw_bars_plan(v, blist, layer="E-ACERO", zmin=-1e9, zmax=1e9):
    """proyeccion en planta (u,v) de barras."""
    for b in blist:
        pl = np.asarray(b["pl"], float)
        if pl[:, 2].max() < zmin or pl[:, 2].min() > zmax:
            continue
        v.pline([tuple(p[:2]) for p in pl], layer)


# ------------------------------------------------------------------ hoja
def new_sheet(doc, name):
    ps = doc.layouts.new(name)
    ps.page_setup(size=(W_, H_), margins=(0, 0, 0, 0), units="mm")
    mv = ps.main_viewport()
    if mv is not None:
        mv.dxf.center = (W_ / 2, H_ / 2, 0)
        mv.dxf.width = W_
        mv.dxf.height = H_
        mv.dxf.view_center_point = (W_ / 2, H_ / 2)
        mv.dxf.view_height = H_
    frame_and_title(ps, W_, H_)
    return ps


def title_block(ps, code, title_lines, scale="INDICADA"):
    mx0, my0_, mw, mh = W_ - 10 - 200, 10, 200, 62
    ps.add_lwpolyline([(mx0, my0_), (mx0 + mw, my0_), (mx0 + mw, my0_ + mh), (mx0, my0_ + mh)], close=True,
                      dxfattribs={"layer": "E-MARCO", "lineweight": 50})
    for yy in (my0_ + 44, my0_ + 30, my0_ + 18):
        ps.add_line((mx0, yy), (mx0 + mw, yy), dxfattribs={"layer": "E-MARCO", "lineweight": 25})
    ps.add_line((mx0 + 150, my0_), (mx0 + 150, my0_ + 30), dxfattribs={"layer": "E-MARCO", "lineweight": 25})
    ps.add_line((mx0 + 75, my0_), (mx0 + 75, my0_ + 18), dxfattribs={"layer": "E-MARCO", "lineweight": 25})
    ptext(ps, "PROYECTO:", (mx0 + 2, my0_ + 58), 1.8)
    ptext(ps, "CASA SAN JERÓNIMO - REDISEÑO ESTRUCTURAL 4 x 3", (mx0 + 2, my0_ + 51), 3.6, "E-TITULO")
    ptext(ps, "5 niveles (Cimentación -2.00, N1 ±0.00 ... N5 +11.00)", (mx0 + 2, my0_ + 46), 2.0)
    ptext(ps, "ESPECIALIDAD: ESTRUCTURAS", (mx0 + 2, my0_ + 39.5), 2.2)
    for i, t in enumerate(title_lines[:2]):
        ptext(ps, t, (mx0 + 2, my0_ + 35 - i * 3.5), 2.6, "E-TITULO")
    ptext(ps, "LÁMINA", (mx0 + 175, my0_ + 26), 2.0, "E-TEXTO", "BOTTOM_CENTER")
    ptext(ps, code, (mx0 + 175, my0_ + 10), 11, "E-TITULO", "BOTTOM_CENTER")
    ptext(ps, f"ESCALA: {scale}", (mx0 + 2, my0_ + 24), 2.0)
    ptext(ps, "FECHA: SET. 2026", (mx0 + 2, my0_ + 20), 2.0)
    ptext(ps, "FUENTE: modelo IFC 'Proyect sj.ifc'", (mx0 + 77, my0_ + 24), 2.0)
    ptext(ps, "(Revit 2027, IFC4, 26-09-2026)", (mx0 + 77, my0_ + 20), 2.0)
    ptext(ps, "PROFESIONAL RESPONSABLE:", (mx0 + 2, my0_ + 13), 1.8)
    ptext(ps, "_______________________  CIP ______", (mx0 + 2, my0_ + 4), 2.0)
    ptext(ps, "REVISÓ:", (mx0 + 77, my0_ + 13), 1.8)
    ptext(ps, "_______________________", (mx0 + 77, my0_ + 4), 2.0)
    return (mx0, my0_, mw, mh)


def notes(ps, x, y, lines, h=2.05, lead=4.3, title_h=2.4):
    for i, s in enumerate(lines):
        ptext(ps, s, (x, y - i * lead), title_h if i == 0 else h, "E-TITULO" if i == 0 else "E-TEXTO")
    return y - len(lines) * lead


def save_and_render(doc, ps, basename, dpi=110):
    doc.set_modelspace_vport(height=20, center=(5, 5))
    doc.saveas(basename + ".dxf")
    # el addon de dibujo de ezdxf escala los patrones de linea del modelo (en metros) como si fueran mm al verlos
    # por una ventana: solo para el render se compensa con ltscale (el DXF ya quedo guardado sin esto)
    for e in doc.modelspace():
        if e.dxf.hasattr("linetype") and e.dxf.linetype.upper() not in ("BYLAYER", "CONTINUOUS", "BYBLOCK"):
            e.dxf.ltscale = e.dxf.get("ltscale", 1.0) * 1000.0
    from ezdxf.addons.drawing import Frontend, RenderContext, pymupdf, layout, config
    ctx = RenderContext(doc)
    be = pymupdf.PyMuPdfBackend()
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                               color_policy=config.ColorPolicy.COLOR,
                               lineweight_policy=config.LineweightPolicy.ABSOLUTE,
                               lineweight_scaling=1.0, min_lineweight=0.09,
                               hatch_policy=config.HatchPolicy.NORMAL,
                               line_policy=config.LinePolicy.ACCURATE)
    Frontend(ctx, be, config=cfg).draw_layout(ps, filter_func=lambda e: e.dxf.layer != "E-VPORT" or e.dxftype() == "VIEWPORT")
    page = layout.Page(W_, H_, layout.Units.mm, margins=layout.Margins.all(0))
    st_ = layout.Settings(fit_page=True)
    open(basename + ".pdf", "wb").write(be.get_pdf_bytes(page, settings=st_))
    open(basename + "_preview.png", "wb").write(be.get_pixmap_bytes(page, fmt="png", dpi=dpi, settings=st_))


def crop_preview(basename, name, x0, y0, x1, y1):
    """recorte del preview en mm de hoja (origen abajo-izquierda) para revisar visualmente."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(basename + "_preview.png")
    f = im.size[0] / W_
    im.crop((int(x0 * f), int((H_ - y1) * f), int(x1 * f), int((H_ - y0) * f))).save(name)
