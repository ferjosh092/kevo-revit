# Servidor de IA de Wasi 3D (Claude y ChatGPT)

Cloudflare Worker que conecta los botones de IA del Estudio (`crear.html`):

| Botón | Ruta | Servicio | Clave |
|---|---|---|---|
| **Describir con IA** | `/api/describir` | Claude (Anthropic) | `ANTHROPIC_API_KEY` |
| **Mejorar con IA** | `/api/mejorar` | API de imágenes de OpenAI | `OPENAI_API_KEY` |

Basta con configurar la clave del servicio que vayas a usar.

## Describir con IA (Claude)

Claude mira la foto del ambiente y propone su nombre, un resumen y entre 3 y 8 puntos de
información en español e inglés, cada uno con su posición en la foto. El Estudio los muestra
como propuesta y el anfitrión marca cuáles agregar. Además avisa si ve algo que conviene
difuminar antes de publicar (personas, reflejos, documentos, fotos familiares).

- Modelo: `MODELO_CLAUDE` en `wrangler.toml` (por defecto `claude-sonnet-5-5`). La respuesta
  sale con un esquema JSON fijo (salidas estructuradas), así que siempre se puede leer.
- El Estudio envía la foto reducida a 1568 px en el lado mayor, que es lo que Claude usa.
- Si los filtros de seguridad de Claude rechazan un pedido, la API lo reintenta sola con el
  modelo que Anthropic recomienda (`fallbacks: "default"`). Con Haiku no hay reintento.
- Costo aproximado con Sonnet 5.5: un centavo de dólar por foto. Revisa los precios vigentes en
  platform.claude.com y pon un límite de gasto mensual en tu cuenta.

## Mejorar con IA (ChatGPT)

Tiene dos modos:

- **Ordenar y ambientar:** quita el desorden de una foto real y mejora la luz (virtual staging).
- **Render fotorrealista:** convierte una vista de la maqueta 3D en una foto con aspecto real.

Puede trabajar sobre la **vista actual**, que da una foto para el anuncio, o sobre el
**panorama 360 completo**. El modo panorama es experimental: la API solo acepta 1536×1024, así
que el panorama se estira, se procesa y se devuelve a 2048 px de ancho, uniendo los bordes.

## Desplegar

```bash
npm install -g wrangler           # o usa npx wrangler
cd web/wasi3d/worker
wrangler login
npm install                          # instala el SDK de Anthropic
wrangler secret put ANTHROPIC_API_KEY  # tu clave de platform.claude.com (nunca en el código)
wrangler secret put OPENAI_API_KEY   # tu clave de platform.openai.com (opcional)
wrangler secret put CODIGO_ACCESO    # contraseña que escribirás en el Estudio
# Edita wrangler.toml: dominio en routes y ORIGENES, y el modelo de imágenes vigente
wrangler deploy
```

El Worker atiende `https://TU-DOMINIO/api/describir` y `/api/mejorar`, en el mismo dominio que la
web. Así el Estudio los llama con `fetch('/api/…')` y la CSP (`connect-src 'self'`) no cambia.

## Seguridad

- Las claves de Anthropic y OpenAI son secretos del Worker y nunca llegan al navegador.
- Cada pedido exige el **código de acceso** (`X-Wasi-Codigo`), comparado en tiempo constante.
- Solo acepta JPG, PNG o WebP: hasta 20 MB para mejorar y 5 MB para describir, y los modos conocidos. Las indicaciones extra se
  limitan a 300 caracteres y se limpian.
- Solo responde a los orígenes de `ORIGENES`. Si Claude u OpenAI fallan, no expone el error original.
- Los textos de Claude se limpian y se recortan en el Worker, y el Estudio los inserta con `textContent`.
- Opcional: límite de pedidos por IP con el binding `LIMITE` de Rate Limiting.

## Costos

Cada mejora es una edición de imagen en OpenAI a 1536×1024. Revisa el precio vigente del modelo
que configures en `MODELO` en platform.openai.com/pricing. Para controlar el gasto, pon un límite
mensual en tu cuenta de OpenAI.

## Uso responsable

Las imágenes generadas se marcan en el Estudio como **«Ambientado con IA»**. Airbnb pide que las
fotos representen el espacio real: usa las versiones ambientadas como referencia o avisa en el
anuncio que la foto está ambientada.

## Pruebas

```bash
cd web/wasi3d/worker && npm install && npm test   # 12 pruebas con respuestas simuladas de Claude y OpenAI
```
