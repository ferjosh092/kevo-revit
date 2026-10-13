#!/usr/bin/env python3
"""Genera la identidad visual de Wasi 3D en SVG, todo desde código.

    pip install fonttools brotli
    python3 web/wasi3d/marca/generar.py          # escribe web/wasi3d/marca/svg/*.svg
    node web/wasi3d/marca/render.js              # opcional: PNG de cada SVG

El isotipo es un cubo isométrico (la maqueta 3D) con una puerta trapezoidal,
la forma de vano de la arquitectura inca de Cusco. Los textos se convierten a
trazos con fontTools, así los SVG se ven igual sin tener las fuentes instaladas.
"""
import math
import pathlib

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "svg"
FONTS = HERE / "fuentes"

C = {
    "carmin": "#A3123F",
    "carmin_claro": "#D7476F",
    "carmin_oscuro": "#6A0A28",
    "tinta": "#18201C",
    "piedra": "#EEF0EB",
    "papel": "#F8F9F5",
    "tinta_noche": "#111513",
    "maiz": "#C98F12",
}

COS30 = math.cos(math.radians(30))


# ---------- Isotipo ----------

def cubo(cx, cy, s, top, left, right, door, stroke=None):
    """Cubo isométrico de lado s centrado en (cx, cy) con puerta trapezoidal en la cara izquierda."""
    P = {
        "T": (cx, cy - s), "UR": (cx + s * COS30, cy - s / 2), "LR": (cx + s * COS30, cy + s / 2),
        "B": (cx, cy + s), "LL": (cx - s * COS30, cy + s / 2), "UL": (cx - s * COS30, cy - s / 2),
        "C": (cx, cy),
    }

    def poly(*names):
        return " ".join(f"{P[n][0]:.2f},{P[n][1]:.2f}" for n in names)

    # Cara izquierda: origen UL, u hacia el centro, v hacia abajo
    ux, uy = P["C"][0] - P["UL"][0], P["C"][1] - P["UL"][1]

    def L(u, v):
        return (P["UL"][0] + u * ux, P["UL"][1] + u * uy + v * s)

    # Vano inca: más angosto arriba que abajo, con dintel
    door_pts = [L(0.30, 1.0), L(0.37, 0.40), L(0.63, 0.40), L(0.70, 1.0)]
    lintel = [L(0.33, 0.36), L(0.67, 0.36), L(0.67, 0.31), L(0.33, 0.31)]
    dp = " ".join(f"{x:.2f},{y:.2f}" for x, y in door_pts)
    lp = " ".join(f"{x:.2f},{y:.2f}" for x, y in lintel)
    st = f' stroke="{stroke}" stroke-width="{s * 0.035:.2f}" stroke-linejoin="round"' if stroke else ""
    return (
        f'<polygon points="{poly("T", "UR", "C", "UL")}" fill="{top}"{st}/>'
        f'<polygon points="{poly("UL", "C", "B", "LL")}" fill="{left}"{st}/>'
        f'<polygon points="{poly("C", "UR", "LR", "B")}" fill="{right}"{st}/>'
        f'<polygon points="{dp}" fill="{door}"/>'
        f'<polygon points="{lp}" fill="{door}" opacity=".55"/>'
    )


# ---------- Texto a trazos ----------

class Fuente:
    def __init__(self, archivo):
        self.font = TTFont(FONTS / archivo)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]

    def ancho(self, texto, size, tracking=0.0):
        w = 0
        for ch in texto:
            g = self.cmap.get(ord(ch))
            w += self.hmtx[g][0] if g else self.upm * 0.3
            w += tracking * self.upm
        return w * size / self.upm

    def ajustar(self, texto, size, max_ancho, tracking=0.0):
        """Reduce el tamaño hasta que el texto quepa en max_ancho."""
        return min(size, size * max_ancho / max(1e-6, self.ancho(texto, size, tracking)))

    def trazo(self, texto, x, y, size, tracking=0.0):
        """Devuelve el atributo d de un path con el texto, línea base en y."""
        k = size / self.upm
        d = []
        pen_x = 0
        for ch in texto:
            g = self.cmap.get(ord(ch))
            if g is None:
                pen_x += self.upm * 0.3 + tracking * self.upm
                continue
            pen = SVGPathPen(self.glyphs)
            # y invertido: las fuentes crecen hacia arriba, el SVG hacia abajo
            self.glyphs[g].draw(TransformPen(pen, (k, 0, 0, -k, x + pen_x * k, y)))
            d.append(pen.getCommands())
            pen_x += self.hmtx[g][0] + tracking * self.upm
        return " ".join(d)


def svg(w, h, body, titulo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{titulo}"><title>{titulo}</title>{body}</svg>\n')


def main():
    OUT.mkdir(exist_ok=True)
    syne = Fuente("syne-latin-800-normal.woff")
    fig = Fuente("figtree-latin-600-normal.woff")
    archivos = {}

    colores = dict(top=C["carmin_claro"], left=C["carmin"], right=C["carmin_oscuro"], door=C["tinta"])
    colores_osc = dict(top="#E8577F", left="#C21F52", right="#7E0F33", door=C["tinta_noche"])

    # 1. Isotipo solo
    archivos["isotipo.svg"] = svg(256, 256, cubo(128, 128, 112, **colores), "Wasi 3D")

    # 2. Isotipo monocromo (una tinta, caras por opacidad): sellos, grabado láser, fax
    archivos["isotipo-mono.svg"] = svg(256, 256,
        cubo(128, 128, 112, top="#18201C66", left=C["tinta"], right="#18201CB3", door=C["papel"]), "Wasi 3D")

    # 3. Logo horizontal (fondo claro y fondo oscuro)
    def horizontal(color_texto, cols, fondo=None):
        h, size = 160, 84
        texto = "Wasi 3D"
        tw = syne.ancho(texto, size, -0.02)
        w = int(160 + 24 + tw + 24)
        bg = f'<rect width="{w}" height="{h}" fill="{fondo}"/>' if fondo else ""
        return svg(w, h, bg + cubo(80, 80, 66, **cols) +
                   f'<path d="{syne.trazo(texto, 172, 108, size, -0.02)}" fill="{color_texto}"/>', "Wasi 3D")

    archivos["logo-horizontal.svg"] = horizontal(C["tinta"], colores)
    archivos["logo-horizontal-oscuro.svg"] = horizontal("#E7EBE5", colores_osc, C["tinta_noche"])

    # 4. Logo vertical con lema
    lema = "TOURS 3D · CUSCO"
    w, h = 520, 520
    t1 = syne.ancho("Wasi 3D", 92, -0.02)
    t2 = fig.ancho(lema, 26, 0.14)
    archivos["logo-vertical.svg"] = svg(w, h,
        cubo(w / 2, 170, 118, **colores) +
        f'<path d="{syne.trazo("Wasi 3D", (w - t1) / 2, 400, 92, -0.02)}" fill="{C["tinta"]}"/>' +
        f'<path d="{fig.trazo(lema, (w - t2) / 2, 452, 26, 0.14)}" fill="{C["carmin"]}"/>', "Wasi 3D, tours 3D en Cusco")

    # 5. Ícono de app (PWA / WhatsApp Business / Instagram): zona segura del 80 %
    archivos["icono-app.svg"] = svg(512, 512,
        f'<rect width="512" height="512" rx="0" fill="{C["piedra"]}"/>' + cubo(256, 256, 150, **colores), "Wasi 3D")
    archivos["icono-app-redondo.svg"] = svg(512, 512,
        f'<rect width="512" height="512" rx="112" fill="{C["carmin"]}"/>' +
        cubo(256, 256, 150, top="#F4DCE3", left="#FFFFFF", right="#E7B3C2", door=C["carmin_oscuro"]), "Wasi 3D")

    # 6. Favicon (simplificado: sin dintel para que se lea a 16 px)
    fav = cubo(32, 32, 29, **colores)
    fav = fav[:fav.rfind("<polygon")]
    archivos["favicon.svg"] = svg(64, 64, fav, "Wasi 3D")

    # 7. Imagen para compartir en redes (Open Graph 1200×630)
    w, h = 1200, 630
    lineas = ["Que tus huéspedes caminen", "tu espacio antes de reservar."]
    body = f'<rect width="{w}" height="{h}" fill="{C["piedra"]}"/>'
    # Retícula isométrica tenue: el lenguaje del plano
    for i in range(-12, 30):
        x = i * 60
        body += f'<path d="M{x} {h} L{x + h / math.tan(math.radians(30))} 0" stroke="{C["tinta"]}" stroke-opacity=".05" stroke-width="1.5"/>'
        body += f'<path d="M{x} 0 L{x + h / math.tan(math.radians(30))} {h}" stroke="{C["tinta"]}" stroke-opacity=".05" stroke-width="1.5"/>'
    body += cubo(930, 315, 190, **colores)
    body += f'<path d="{syne.trazo("Wasi 3D", 80, 170, 96, -0.02)}" fill="{C["tinta"]}"/>'
    for n, linea in enumerate(lineas):
        body += f'<path d="{fig.trazo(linea, 82, 300 + n * 62, 46, -0.005)}" fill="{C["tinta"]}"/>'
    body += f'<rect x="80" y="420" width="64" height="6" fill="{C["carmin"]}"/>'
    body += f'<path d="{fig.trazo("Recorrido 3D · maqueta · plano con medidas · fotos HDR", 82, 492, 26, 0.01)}" fill="#58635D"/>'
    body += f'<path d="{fig.trazo("Listo en 48 horas · desde S/ 390", 82, 540, 26, 0.01)}" fill="{C["carmin"]}"/>'
    archivos["og-imagen.svg"] = svg(w, h, body, "Wasi 3D: tours 3D para alojamientos en Cusco")

    # 8. Tarjeta de métodos de pago (para WhatsApp e Instagram, 1080×1350).
    #    Solo texto con los nombres de los medios: los logotipos de Yape, Plin, Visa, etc.
    #    son marcas de terceros y se colocan con los archivos oficiales que entrega cada pasarela.
    w, h = 1080, 1350
    body = f'<rect width="{w}" height="{h}" fill="{C["papel"]}"/>'
    body += f'<rect width="{w}" height="300" fill="{C["carmin"]}"/>'
    body += cubo(150, 150, 82, top="#F4DCE3", left="#FFFFFF", right="#E7B3C2", door=C["carmin_oscuro"])
    ts = syne.ajustar("Formas de pago", 72, 740, -0.02)
    body += f'<path d="{syne.trazo("Formas de pago", 270, 130, ts, -0.02)}" fill="#FFFFFF"/>'
    body += f'<path d="{fig.trazo("Reserva tu escaneo con el 50 % de adelanto", 272, 196, 32)}" fill="#F4DCE3"/>'
    medios = [
        ("Yape o Plin", "Al instante, desde tu celular", "Perú"),
        ("Tarjeta de crédito o débito", "Visa, Mastercard, Amex, Diners", "Perú y extranjero"),
        ("PayPal", "Para anfitriones en el extranjero", "Extranjero"),
        ("Transferencia bancaria", "BCP, Interbank, BBVA, Scotiabank", "Perú"),
        ("PagoEfectivo", "Agentes y banca por internet", "Perú"),
    ]
    y = 380
    for nombre, detalle, zona in medios:
        body += f'<rect x="72" y="{y}" width="936" height="150" rx="18" fill="#FFFFFF" stroke="#D2D7CF" stroke-width="2"/>'
        body += f'<rect x="72" y="{y}" width="12" height="150" rx="6" fill="{C["carmin"]}"/>'
        zw = fig.ancho(zona, 24, 0.04)
        ns = fig.ajustar(nombre, 40, 972 - zw - 60 - 120)
        body += f'<path d="{fig.trazo(nombre, 120, y + 68, ns, -0.01)}" fill="{C["tinta"]}"/>'
        body += f'<path d="{fig.trazo(detalle, 122, y + 114, 28)}" fill="#58635D"/>'
        body += f'<rect x="{972 - zw - 40:.1f}" y="{y + 36}" width="{zw + 40:.1f}" height="44" rx="22" fill="#F4DCE3"/>'
        body += f'<path d="{fig.trazo(zona, 972 - zw - 20, y + 66, 24, 0.04)}" fill="{C["carmin"]}"/>'
        y += 172
    body += f'<path d="{fig.trazo("Te enviamos boleta o factura electrónica.", 74, 1290, 30)}" fill="{C["tinta"]}"/>'
    archivos["formas-de-pago.svg"] = svg(w, h, body, "Formas de pago de Wasi 3D")

    for nombre, contenido in archivos.items():
        (OUT / nombre).write_text(contenido, encoding="utf-8")
    print("Generados:", ", ".join(sorted(archivos)))


if __name__ == "__main__":
    main()
