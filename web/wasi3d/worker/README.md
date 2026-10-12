# Servidor de IA de Wasi 3D (ChatGPT)

Cloudflare Worker que conecta el botón **Mejorar con IA** del Estudio (`crear.html`) con la API
de imágenes de OpenAI. Tiene dos modos:

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
wrangler secret put OPENAI_API_KEY   # tu clave de platform.openai.com (nunca en el código)
wrangler secret put CODIGO_ACCESO    # contraseña que escribirás en el Estudio
# Edita wrangler.toml: dominio en routes y ORIGENES, y el modelo de imágenes vigente
wrangler deploy
```

El Worker atiende `https://TU-DOMINIO/api/mejorar`, en el mismo dominio que la web. Así el
Estudio lo llama con `fetch('/api/mejorar')` y la CSP (`connect-src 'self'`) no cambia.

## Seguridad

- La clave de OpenAI es un secreto del Worker y nunca llega al navegador.
- Cada pedido exige el **código de acceso** (`X-Wasi-Codigo`), comparado en tiempo constante.
- Solo acepta JPG, PNG o WebP de hasta 20 MB y los modos conocidos. Las indicaciones extra se
  limitan a 300 caracteres y se limpian.
- Solo responde a los orígenes de `ORIGENES`. Si OpenAI falla, no expone el error original.
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
cd web/wasi3d/worker && npm test    # 7 pruebas con una respuesta simulada de OpenAI
```
