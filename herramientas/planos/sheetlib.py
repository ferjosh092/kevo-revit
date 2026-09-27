"""Utilidades de dibujo para laminas estructurales en DXF (ezdxf).
Modelo en metros reales; hoja en espacio papel (mm) con ventanas a escala."""
import math
import numpy as np
import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec2

FONT = "ARIAL"

LAYERS = {
    # nombre: (color ACI, grosor 1/100 mm, tipo de linea)
    "E-EJES": (1, 18, "EJE"),
    "E-EJES-ID": (7, 25, None),
    "E-ZAPATA": (7, 40, None),
    "E-COLUMNA": (7, 50, None),
    "E-COLUMNA-ACH": (252, 0, None),
    "E-VIGA": (7, 30, None),
    "E-OCULTO": (8, 18, "OCULTA"),
    "E-CORTE": (7, 50, None),
    "E-CORTE-ACH": (254, 0, None),
    "E-PROYECCION": (8, 18, None),
    "E-ACERO": (1, 35, None),
    "E-ACERO-TXT": (7, 18, None),
    "E-COTA": (7, 13, None),
    "E-TEXTO": (7, 18, None),
    "E-TITULO": (7, 35, None),
    "E-NIVEL": (7, 18, None),
    "E-LIMITE": (94, 25, "LIMITE"),
    "E-TERRENO": (8, 13, None),
    "E-SECCION": (7, 35, None),
    "E-TABLA": (7, 18, None),
    "E-MARCO": (7, 50, None),
    "E-VPORT": (7, 13, None),
    "E-HOJA": (7, 0, None),
}


def new_doc():
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 1.0
    doc.header["$PSLTSCALE"] = 0
    doc.header["$LUPREC"] = 3
    if FONT not in doc.styles:
        doc.styles.add(FONT, font="arial.ttf")
    return doc


def add_linetypes(doc, k):
    """Tipos de linea dimensionados para una escala 1:k (patrones en metros de modelo)."""
    m = k / 1000.0
    defs = {
        f"EJE{k}": [12, -2, 1.5, -2],
        f"OCULTA{k}": [3, -1.5],
        f"LIMITE{k}": [15, -2, 1.5, -2, 1.5, -2],
    }
    for name, pat in defs.items():
        if name in doc.linetypes:
            continue
        pm = [x * m for x in pat]
        doc.linetypes.add(name, pattern=[sum(abs(x) for x in pm)] + pm, description=name)


def add_layers(doc):
    for name, (color, lw, lt) in LAYERS.items():
        if name in doc.layers:
            continue
        ly = doc.layers.add(name, color=color)
        ly.dxf.lineweight = lw if lw else 0
        if name == "E-VPORT":
            ly.dxf.plot = 0


class View:
    """Una vista dibujada en espacio modelo a escala 1:k, con origen desplazado."""

    def __init__(self, doc, k, offset=(0.0, 0.0)):
        self.doc = doc
        self.msp = doc.modelspace()
        self.k = k
        self.m = k / 1000.0          # metros de modelo por mm de papel
        self.off = np.array(offset, float)
        self.ltk = max(k, 20)          # patrones muy cortos (1:5, 1:10) cuelgan el render de ezdxf
        add_linetypes(doc, self.ltk)
        self._dimstyle()

    # --- transformacion ---
    def P(self, x, y):
        return (float(x + self.off[0]), float(y + self.off[1]))

    def mm(self, v):
        return v * self.m

    def lt(self, base):
        return f"{base}{self.ltk}"

    def _dimstyle(self):
        name = f"COTA{self.k}"
        self.dimstyle = name
        if name in self.doc.dimstyles:
            return
        ds = self.doc.dimstyles.new(name)
        m = self.m
        ds.dxf.dimtxt = 1.8 * m
        ds.dxf.dimasz = 1.2 * m
        ds.dxf.dimtsz = 1.0 * m          # trazo oblicuo (tick)
        ds.dxf.dimexe = 1.2 * m
        ds.dxf.dimexo = 0.8 * m
        ds.dxf.dimgap = 0.6 * m
        ds.dxf.dimdec = 2
        ds.dxf.dimtad = 1
        ds.dxf.dimtih = 0
        ds.dxf.dimtoh = 0
        ds.dxf.dimtxsty = FONT
        ds.dxf.dimclrd = 7
        ds.dxf.dimclre = 7
        ds.dxf.dimclrt = 7
        ds.dxf.dimlwd = 13
        ds.dxf.dimlwe = 13
        ds.dxf.dimdsep = ord(".")
        ds.dxf.dimzin = 0
        ds.dxf.dimatfit = 3
        ds.dxf.dimtmove = 2

    # --- primitivas ---
    def line(self, a, b, layer, **kw):
        at = {"layer": layer}
        at.update(kw)
        return self.msp.add_line(self.P(*a), self.P(*b), dxfattribs=at)

    def pline(self, pts, layer, close=False, **kw):
        at = {"layer": layer}
        at.update(kw)
        return self.msp.add_lwpolyline([self.P(*p) for p in pts], close=close, dxfattribs=at)

    def hatch(self, pts, layer, color=None):
        h = self.msp.add_hatch(color=color if color is not None else 256, dxfattribs={"layer": layer})
        h.paths.add_polyline_path([self.P(*p) for p in pts], is_closed=True)
        return h

    def circle(self, c, r, layer, fill=False):
        e = self.msp.add_circle(self.P(*c), r, dxfattribs={"layer": layer})
        if fill:
            h = self.msp.add_hatch(color=256, dxfattribs={"layer": layer})
            ep = h.paths.add_edge_path()
            ep.add_arc(self.P(*c), r, 0, 360)
        return e

    def text(self, s, p, h_mm=2.2, layer="E-TEXTO", align="MIDDLE_CENTER", rot=0.0, width=0.9):
        t = self.msp.add_text(s, height=h_mm * self.m, rotation=rot,
                              dxfattribs={"layer": layer, "style": FONT, "width": width})
        t.set_placement(self.P(*p), align=TextEntityAlignment[align])
        return t

    def mtext(self, s, p, h_mm=2.0, layer="E-TEXTO", width_mm=60, attach=1):
        mt = self.msp.add_mtext(s, dxfattribs={"layer": layer, "style": FONT, "char_height": h_mm * self.m,
                                                "width": width_mm * self.m, "attachment_point": attach})
        mt.set_location(self.P(*p))
        return mt

    def dim(self, p1, p2, base, angle=0, text=None, dec=2, layer="E-COTA"):
        ov = {"dimdec": dec}
        d = self.msp.add_linear_dim(base=self.P(*base), p1=self.P(*p1), p2=self.P(*p2), angle=angle,
                                    dimstyle=self.dimstyle, override=ov, text=text if text else "<>",
                                    dxfattribs={"layer": layer})
        d.render()
        return d

    def hdim_chain(self, xs, y_ref, y_dim, dec=2, texts=None):
        for i in range(len(xs) - 1):
            t = texts[i] if texts else None
            self.dim((xs[i], y_ref), (xs[i + 1], y_ref), (xs[i], y_dim), 0, text=t, dec=dec)

    def vdim_chain(self, ys, x_ref, x_dim, dec=2, texts=None):
        for i in range(len(ys) - 1):
            t = texts[i] if texts else None
            self.dim((x_ref, ys[i]), (x_ref, ys[i + 1]), (x_dim, ys[i]), 90, text=t, dec=dec)

    def leader(self, a, b, s, h_mm=2.0, side=None, layer="E-ACERO-TXT", dot=True, shelf_mm=2.0):
        """Linea de llamada desde a (en el elemento) hasta b, con texto a continuacion."""
        side = side if side is not None else (1 if b[0] >= a[0] else -1)
        c = (b[0] + side * shelf_mm * self.m, b[1])
        self.pline([a, b, c], layer)
        if dot:
            self.circle(a, 0.5 * self.m, layer, fill=True)
        self.text(s, (c[0] + side * 0.8 * self.m, c[1]), h_mm, layer,
                  align="MIDDLE_LEFT" if side > 0 else "MIDDLE_RIGHT")

    def level(self, x, y, label, left=True, h_mm=2.0):
        """Simbolo de nivel (triangulo) con texto."""
        m = self.m
        s = 1.6 * m
        tri = [(x, y), (x - s, y + 1.6 * s), (x + s, y + 1.6 * s)]
        self.pline(tri, "E-NIVEL", close=True)
        self.hatch([(x, y), (x - s, y + 1.6 * s), (x, y + 1.6 * s)], "E-NIVEL", color=7)
        L = 11 * m
        x0, x1 = (x - L, x + s) if left else (x - s, x + L)
        self.line((x0, y + 1.6 * s), (x1, y + 1.6 * s), "E-NIVEL")
        self.text(label, ((x0 + 0.5 * m) if left else (x + 2 * s), y + 1.6 * s + 0.8 * m), h_mm, "E-NIVEL",
                  align="BOTTOM_LEFT")

    def grid_bubble(self, c, tag, r_mm=5.0):
        self.circle(c, r_mm * self.m, "E-EJES-ID")
        self.text(tag, c, 3.0, "E-EJES-ID", width=0.8)

    def break_line(self, a, b):
        """Linea de corte (zigzag) entre a y b."""
        a = np.array(a, float)
        b = np.array(b, float)
        d = b - a
        L = np.linalg.norm(d)
        u = d / L
        n = np.array([-u[1], u[0]])
        z = 1.5 * self.m
        mid = a + d / 2
        pts = [a, mid - u * z, mid - u * z * 0.3 + n * z * 1.5, mid + u * z * 0.3 - n * z * 1.5, mid + u * z, b]
        self.pline([tuple(p) for p in pts], "E-CORTE")


def section_mark(v: View, a, b, tag, flip=False):
    """Marca de corte en planta: linea gruesa corta en los extremos y circulo con numero."""
    a = np.array(a, float)
    b = np.array(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]]) * (-1 if flip else 1)
    m = v.m
    for p, sgn in ((a, 1), (b, -1)):
        q = p + d * sgn * 6 * m
        v.pline([tuple(p), tuple(q)], "E-SECCION", const_width=0.7 * m)
        # flecha de direccion de vista
        t = p + n * 4 * m
        v.pline([tuple(p + d * sgn * 1 * m), tuple(t), tuple(p + d * sgn * 3.5 * m)], "E-SECCION")
        c = p - d * sgn * 3.5 * m
        v.circle(tuple(c), 3.0 * m, "E-SECCION")
        v.text(tag, tuple(c), 2.6, "E-SECCION")


def frame_and_title(ps, W, H):
    ps.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H)], close=True, dxfattribs={"layer": "E-HOJA", "lineweight": 0})
    ps.add_lwpolyline([(25, 10), (W - 10, 10), (W - 10, H - 10), (25, H - 10)], close=True,
                      dxfattribs={"layer": "E-MARCO", "lineweight": 70})


def ptext(ps, s, p, h, layer="E-TEXTO", align="BOTTOM_LEFT", width=0.9):
    t = ps.add_text(s, height=h, dxfattribs={"layer": layer, "style": FONT, "width": width})
    t.set_placement(p, align=TextEntityAlignment[align])
    return t


def view_title(ps, x, y, title, scale_txt, w=None):
    ptext(ps, title, (x, y + 1.5), 4.0, "E-TITULO", "BOTTOM_CENTER")
    tw = w or len(title) * 3.3
    ps.add_line((x - tw / 2, y), (x + tw / 2, y), dxfattribs={"layer": "E-TITULO", "lineweight": 50})
    ps.add_line((x - tw / 2, y - 1.0), (x + tw / 2, y - 1.0), dxfattribs={"layer": "E-TITULO", "lineweight": 18})
    ptext(ps, scale_txt, (x, y - 2.5), 2.5, "E-TEXTO", "TOP_CENTER")


def add_vp(ps, cx, cy, w, h, model_center, k):
    vp = ps.add_viewport(center=(cx, cy), size=(w, h), view_center_point=model_center, view_height=h * k / 1000.0,
                         dxfattribs={"layer": "E-VPORT"})
    return vp


def table(ps, x, y, col_w, rows, row_h=6.0, h_txt=2.2, header_rows=1, aligns=None):
    """Tabla en espacio papel. rows: lista de listas de texto; x,y esquina superior izquierda."""
    W = sum(col_w)
    n = len(rows)
    for i in range(n + 1):
        lw = 50 if i in (0, header_rows, n) else 18
        ps.add_line((x, y - i * row_h), (x + W, y - i * row_h), dxfattribs={"layer": "E-TABLA", "lineweight": lw})
    xx = x
    for j, w in enumerate(col_w + [0]):
        lw = 50 if j in (0, len(col_w)) else 18
        ps.add_line((xx, y), (xx, y - n * row_h), dxfattribs={"layer": "E-TABLA", "lineweight": lw})
        xx += w
    for i, r in enumerate(rows):
        xx = x
        for j, (w, s) in enumerate(zip(col_w, r)):
            al = (aligns[j] if aligns else "C") if i >= header_rows else "C"
            if al == "L":
                ptext(ps, s, (xx + 1.5, y - (i + 0.5) * row_h), h_txt, "E-TABLA", "MIDDLE_LEFT", 0.85)
            else:
                ptext(ps, s, (xx + w / 2, y - (i + 0.5) * row_h), h_txt, "E-TABLA", "MIDDLE_CENTER", 0.85)
            xx += w
    return W, n * row_h
