"""Detalles tipicos dibujados por reglas de armado (E.060) sobre una View de sheetlib."""
import math
import numpy as np
from beamdesign import layer_split, lateral_positions, COVER, D38, SEG_CAPA

DB = {"1/4": 0.00635, "3/8": 0.009525, "1/2": 0.0127, "5/8": 0.015875, "3/4": 0.01905}


def dstr(d):
    return f'Ø{d}"'


def rounded_rect(x0, y0, x1, y1, r, n=6):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def stirrup(v, x0, y0, x1, y1, ds, hook_corner="TL", ext=None, layer="E-ACERO"):
    """Estribo cerrado (eje de la barra) con ganchos de 135 grados en la esquina indicada."""
    r = 2.0 * ds
    v.pline(rounded_rect(x0, y0, x1, y1, r), layer, close=True, const_width=ds * 0.9)
    ext = ext or max(6 * ds, 0.075)
    cx, cy = (x0 + r, y1 - r) if hook_corner == "TL" else (x1 - r, y1 - r)
    sx = 1 if hook_corner == "TL" else -1
    # dos ganchos: salen de la esquina y entran al nucleo a 45 grados
    for (px, py) in ((x0 if sx > 0 else x1, y1 - r), (cx, y1)):
        d = np.array([sx, -1.0]) / math.sqrt(2)
        q = (px + d[0] * ext, py + d[1] * ext)
        v.pline([(px, py), q], layer, const_width=ds * 0.9)


def beam_section(v, b, h, n_sup, n_inf, d_long="3/4", d_est="3/8", title_txt=None, dist_txt=None,
                 lab_side=1, show_dims=True, label_h=2.2):
    """Seccion transversal tipica de viga, origen en la esquina inferior izquierda."""
    db, ds = DB[d_long], DB[d_est]
    m = v.m
    v.hatch([(0, 0), (b, 0), (b, h), (0, h)], "E-CORTE-ACH")
    v.pline([(0, 0), (b, 0), (b, h), (0, h)], "E-CORTE", close=True)
    e0 = COVER + ds / 2
    stirrup(v, e0, e0, b - e0, h - e0, ds, "TL")
    inner = b - 2 * (COVER + ds) - db
    half = inner / 2
    xc = b / 2
    lay = {}
    for role, n in (("SUP", n_sup), ("INF", n_inf)):
        capas = layer_split(n, inner, db)
        z1 = (h - COVER - ds - db / 2) if role == "SUP" else (COVER + ds + db / 2)
        sg = -1 if role == "SUP" else 1
        lay[role] = []
        for ic, nl in enumerate(capas):
            ts = lateral_positions(nl, capas[0], half)
            z = z1 + sg * ic * SEG_CAPA
            for t in ts:
                v.circle((xc + t, z), db / 2, "E-ACERO", fill=True)
            lay[role].append((nl, z, ts))
    # rotulos
    xl = b + 0.03 if lab_side > 0 else -0.03
    for role in ("SUP", "INF"):
        for ic, (nl, z, ts) in enumerate(lay[role]):
            tx = xc + (max(ts) if lab_side > 0 else min(ts))
            ytxt = z + (0.02 if role == "SUP" else -0.02) * (1 if ic == 0 else -1)
            capa = f" ({ic + 1}ra capa)" if len(lay[role]) > 1 and ic == 0 else (f" ({ic + 1}da capa)" if len(lay[role]) > 1 else "")
            v.leader((tx, z), (xl + (0.04 if lab_side > 0 else -0.04), ytxt), f"{nl} {dstr(d_long)}{capa}", label_h,
                     side=lab_side)
    v.leader((b - e0, h * 0.55), (xl + 0.04 * lab_side, h * 0.55), f"Estribo {dstr(d_est)}", label_h, side=lab_side)
    if show_dims:
        v.dim((0, 0), (b, 0), (0, -7 * m), 0)
        v.dim((0, 0), (0, h), (-7 * m, 0), 90)
        # recubrimiento y separacion de capas
        v.text("r = 0.04", (b / 2, (e0 - ds / 2) / 2), 1.4, "E-ACERO-TXT")
        for role in ("SUP", "INF"):
            if len(lay[role]) > 1:
                z0_, z1_ = lay[role][0][1], lay[role][1][1]
                x_ = xc + lay[role][0][2][0]
                v.dim((x_, min(z0_, z1_)), (x_, max(z0_, z1_)), (-3.0 * m, min(z0_, z1_)), 90,
                      text=f"{abs(z1_ - z0_):.3f}".replace("0.", "."), dec=3)
    v.text("gancho 135°", (e0 + 0.02, h + 2.2 * m), 1.6, "E-ACERO-TXT", "BOTTOM_LEFT")
    return lay
