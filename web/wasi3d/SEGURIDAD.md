# Seguridad y rendimiento de la landing Wasi 3D

## Después de editar `index.html`

```bash
python3 web/wasi3d/build.py
```

Recalcula los hashes de los scripts en línea, actualiza la CSP de la `<meta>` y regenera `_headers`.
Si no se ejecuta, el navegador bloqueará los scripts editados.

## Qué protege la página

| Medida | Dónde | Contra qué |
|---|---|---|
| SRI (`integrity` sha512) en Three.js, GSAP, ScrollTrigger, SplitText y Lenis | `<script>` | Un CDN comprometido que sirva código alterado. Hashes verificados contra los paquetes de npm y la API de cdnjs. |
| Content-Security-Policy sin `'unsafe-inline'` para scripts | `<meta>` y `_headers` | Inyección de scripts (XSS). Solo corren los scripts propios (por hash) y los dos CDN. |
| `frame-ancestors 'none'`, `X-Frame-Options: DENY` | `_headers` | Clickjacking (meter la página en un iframe ajeno). |
| HSTS, `nosniff`, `Referrer-Policy`, `Permissions-Policy` | `_headers` | Degradación a HTTP, MIME sniffing, fuga de URL, uso de cámara o ubicación. |
| `rel="noopener noreferrer"` en enlaces externos | HTML | Que la pestaña abierta controle la página. |
| Formulario: largo máximo, limpieza de caracteres, validación de WhatsApp y m², listas cerradas, trampa anti-bots y espera de 8 s | JS | Spam y texto malicioso en el mensaje. Todo se escribe con `textContent`, nunca como HTML. |

`_headers` sirve tal cual en Netlify y Cloudflare Pages. En otro hosting, copia esas cabeceras a su configuración.

## Rendimiento

- Scripts con `defer`. El código propio corre en `DOMContentLoaded`.
- El 3D se dibuja solo cuando algo cambia. Las sombras se calculan una vez.
- Modo ligero automático en GPU por software o equipos con 2 GB de RAM o menos: sin sombras, resolución 1×, sin giro automático.

Lighthouse local (13.5.0, móvil simulado): accesibilidad 100, buenas prácticas 100, SEO 100.
El puntaje de rendimiento local no es representativo, porque el contenedor no tiene GPU ni acceso a Google Fonts.
Mídelo en el sitio publicado con PageSpeed Insights o con el MCP de Chrome DevTools (`.mcp.json`).

## Creador de recorridos (`crear.html`)

- Las fotos se procesan en el navegador: se reducen al tamaño máximo de textura del equipo y nunca salen de él.
- El recorrido se guarda en IndexedDB del navegador del anfitrión. Para compartir un enlace público hace falta un servidor (por ejemplo Cloudflare R2 + Workers).
- Solo acepta JPG, PNG y WebP (60 MB por foto, 40 ambientes). Los textos del usuario se limpian y se insertan con `textContent`.
- `marca/panoramas.js` regenera los panoramas de ejemplo de `demo/` a partir de la maqueta de la landing.
