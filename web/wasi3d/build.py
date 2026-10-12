#!/usr/bin/env python3
"""Build de seguridad para la landing Wasi 3D.

Ejecutar después de cualquier cambio en index.html:

    python3 web/wasi3d/build.py [--artifact RUTA]

- Calcula el hash SHA-256 de cada <script> en línea y escribe una
  Content-Security-Policy estricta (sin 'unsafe-inline' para scripts)
  en la etiqueta <meta> de index.html.
- Genera _headers (Netlify / Cloudflare Pages) con la misma CSP y las
  cabeceras que una <meta> no puede fijar (HSTS, frame-ancestors, etc.).
- Con --artifact, escribe una copia sin el esqueleto <html>/<head> ni la
  CSP en <meta>, para publicarla como Artifact de Claude.
"""
import argparse
import base64
import hashlib
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
INDEX = HERE / "index.html"

SCRIPT_HOSTS = ["https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net"]


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
    ap.add_argument("--artifact", help="ruta de salida para la copia publicable como Artifact")
    args = ap.parse_args()

    html = INDEX.read_text(encoding="utf-8")
    hashes = inline_script_hashes(html)
    html = re.sub(
        r'(<meta http-equiv="Content-Security-Policy" content=")[^"]*(">)',
        lambda m: m.group(1) + csp(hashes, False) + m.group(2),
        html,
        count=1,
    )
    INDEX.write_text(html, encoding="utf-8")

    headers = "\n".join([
        "/*",
        "  Content-Security-Policy: " + csp(hashes, True),
        "  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload",
        "  X-Content-Type-Options: nosniff",
        "  X-Frame-Options: DENY",
        "  Referrer-Policy: strict-origin-when-cross-origin",
        "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
        "  Cross-Origin-Opener-Policy: same-origin",
        "",
    ])
    (HERE / "_headers").write_text(headers, encoding="utf-8")

    if args.artifact:
        skeleton = re.compile(
            r'^(<!doctype html>|<html lang="es">|<head>|<meta charset="utf-8">|<meta name="viewport".*'
            r'|<meta http-equiv="Content-Security-Policy".*|<meta name="referrer".*|<link rel="icon".*|</head>|<body>|</body>|</html>)$'
        )
        lines = [l for l in html.splitlines() if not skeleton.match(l)]
        pathlib.Path(args.artifact).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"CSP con {len(hashes)} hashes de scripts en línea. _headers actualizado.")


if __name__ == "__main__":
    main()
