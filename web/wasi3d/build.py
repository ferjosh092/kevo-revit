#!/usr/bin/env python3
"""Build de seguridad para las páginas de Wasi 3D.

Ejecutar después de cualquier cambio en index.html o crear.html:

    python3 web/wasi3d/build.py [--artifact RUTA] [--artifact-dir CARPETA]

- Calcula el hash SHA-256 de cada <script> en línea de cada página y escribe una
  Content-Security-Policy estricta (sin 'unsafe-inline' para scripts) en su <meta>.
- Genera _headers (Netlify / Cloudflare Pages) con una CSP por página y las
  cabeceras que una <meta> no puede fijar (HSTS, frame-ancestors, etc.).
- --artifact escribe la landing sin el esqueleto <html>/<head> para publicarla
  como Artifact de Claude; --artifact-dir hace lo mismo con todas las páginas.
"""
import argparse
import base64
import hashlib
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
PAGINAS = ["index.html", "crear.html"]
SCRIPT_HOSTS = ["https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net"]
ESQUELETO = re.compile(
    r'^(<!doctype html>|<html lang="es">|<head>|<meta charset="utf-8">|<meta name="viewport".*'
    r'|<meta http-equiv="Content-Security-Policy".*|<meta name="referrer".*|<link rel="icon".*|</head>|<body>|</body>|</html>)$'
)


def inline_script_hashes(html: str) -> list[str]:
    hashes = []
    for m in re.finditer(r"<script>(.*?)</script>", html, re.S):
        digest = hashlib.sha256(m.group(1).encode("utf-8")).digest()
        hashes.append("'sha256-" + base64.b64encode(digest).decode() + "'")
    return hashes


def csp(hashes: list[str], for_header: bool) -> str:
    parts = [
        "default-src 'self'",
        "script-src 'self' " + " ".join(hashes + SCRIPT_HOSTS),
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ]
    if for_header:
        parts += ["frame-ancestors 'none'", "upgrade-insecure-requests"]
    return "; ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", help="copia de la landing publicable como Artifact")
    ap.add_argument("--artifact-dir", help="carpeta para copias publicables de todas las páginas")
    args = ap.parse_args()

    comunes = [
        "  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload",
        "  X-Content-Type-Options: nosniff",
        "  X-Frame-Options: DENY",
        "  Referrer-Policy: strict-origin-when-cross-origin",
        "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
        "  Cross-Origin-Opener-Policy: same-origin",
    ]
    headers = ["/*"] + comunes + [""]
    for nombre in PAGINAS:
        ruta = HERE / nombre
        html = ruta.read_text(encoding="utf-8")
        hashes = inline_script_hashes(html)
        html = re.sub(
            r'(<meta http-equiv="Content-Security-Policy" content=")[^"]*(">)',
            lambda m: m.group(1) + csp(hashes, False) + m.group(2),
            html,
            count=1,
        )
        ruta.write_text(html, encoding="utf-8")
        rutas = ["/", "/index.html"] if nombre == "index.html" else ["/" + nombre, "/" + nombre[:-5]]
        for r in rutas:
            headers += [r, "  Content-Security-Policy: " + csp(hashes, True), ""]
        limpio = "\n".join(l for l in html.splitlines() if not ESQUELETO.match(l)) + "\n"
        if args.artifact and nombre == "index.html":
            pathlib.Path(args.artifact).write_text(limpio, encoding="utf-8")
        if args.artifact_dir:
            d = pathlib.Path(args.artifact_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / nombre).write_text(limpio, encoding="utf-8")
        print(f"{nombre}: CSP con {len(hashes)} hashes de scripts en línea.")
    (HERE / "_headers").write_text("\n".join(headers), encoding="utf-8")
    print("_headers actualizado.")


if __name__ == "__main__":
    main()
