// Wasi 3D · «Describir con IA»: Claude mira la foto de un ambiente y propone su nombre,
// un resumen y puntos de información en español e inglés, con su ubicación en la imagen.
// También avisa si ve algo que conviene ocultar antes de publicar (personas, documentos…).
// La clave de Anthropic vive solo aquí, como secreto del Worker (ANTHROPIC_API_KEY).

import Anthropic from "@anthropic-ai/sdk";

export const MAX_BYTES_CLAUDE = 5 * 1024 * 1024; // límite de la API por imagen
export const MODELO_CLAUDE = "claude-sonnet-5-5";
const MAX_PUNTOS = 8;

export const SISTEMA =
  "Eres el asistente de Wasi 3D, un servicio de recorridos virtuales para alojamientos turísticos en Cusco, Perú. " +
  "Recibes la foto de un ambiente y preparas los textos que verá el huésped dentro del recorrido.\n\n" +
  "Reglas:\n" +
  "- Describe solo lo que se ve en la foto. No inventes servicios, medidas, marcas ni vistas que no aparezcan: el anuncio debe ser fiel al espacio real.\n" +
  "- Escribe en español neutro y claro, en segunda persona («aquí puedes…»), sin exagerar. Cada texto en inglés es la traducción natural del español.\n" +
  "- Elige entre 3 y 8 puntos de información útiles para un huésped: zonas (estar, comedor, trabajo), equipamiento (cama, cocina, terma, calefacción, televisor, escritorio), ventanas y luz natural. No marques objetos decorativos sin interés.\n" +
  "- Para cada punto da su posición en la imagen: x es la fracción horizontal (0 = borde izquierdo, 1 = borde derecho) e y la vertical (0 = arriba, 1 = abajo), en el centro del objeto.\n" +
  "- En «privacidad» anota lo que el anfitrión debería ocultar o difuminar antes de publicar: personas o rostros, reflejos de personas, documentos, pantallas con datos, fotos familiares, placas de auto. Si no hay nada, deja la lista vacía.\n" +
  "- Nunca describas a las personas que aparezcan; solo avisa en «privacidad» que hay que difuminarlas.";

export const ESQUEMA = {
  type: "object",
  properties: {
    nombre: { type: "string", description: "Nombre corto del ambiente en español, por ejemplo «Sala principal»" },
    nombre_en: { type: "string" },
    resumen: { type: "string", description: "Una o dos frases para presentar el ambiente al huésped" },
    resumen_en: { type: "string" },
    puntos: {
      type: "array",
      items: {
        type: "object",
        properties: {
          titulo: { type: "string" },
          titulo_en: { type: "string" },
          texto: { type: "string", description: "Una o dos frases útiles para el huésped" },
          texto_en: { type: "string" },
          x: { type: "number" },
          y: { type: "number" },
        },
        required: ["titulo", "titulo_en", "texto", "texto_en", "x", "y"],
        additionalProperties: false,
      },
    },
    privacidad: { type: "array", items: { type: "string" } },
  },
  required: ["nombre", "nombre_en", "resumen", "resumen_en", "puntos", "privacidad"],
  additionalProperties: false,
};

const TIPOS_FOTO = {
  "360": "La imagen es un panorama 360° equirectangular: el borde izquierdo y el derecho son el mismo punto, y los objetos cerca de arriba y abajo se ven deformados.",
  parcial: "La imagen es un panorama 360° horizontal tomado con celular: cubre toda la vuelta, pero no el techo ni el piso completos.",
  foto: "La imagen es una foto normal del ambiente.",
};

const limpio = (s, n) => String(s ?? "").replace(/[\u0000-\u001F\u007F<>]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
const fraccion = (v) => Math.min(1, Math.max(0, Number.isFinite(+v) ? +v : 0.5));

function aBase64(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

// Deja la respuesta del modelo dentro de los límites que el Estudio espera
export function normalizar(d) {
  const puntos = (Array.isArray(d.puntos) ? d.puntos : []).slice(0, MAX_PUNTOS).map((p) => ({
    titulo: limpio(p.titulo, 60), titulo_en: limpio(p.titulo_en, 60),
    texto: limpio(p.texto, 280), texto_en: limpio(p.texto_en, 280),
    x: fraccion(p.x), y: fraccion(p.y),
  })).filter((p) => p.titulo);
  return {
    nombre: limpio(d.nombre, 40), nombre_en: limpio(d.nombre_en, 40),
    resumen: limpio(d.resumen, 280), resumen_en: limpio(d.resumen_en, 280),
    puntos,
    privacidad: (Array.isArray(d.privacidad) ? d.privacidad : []).slice(0, 6).map((s) => limpio(s, 160)).filter(Boolean),
  };
}

export async function describir(form, env, json) {
  const imagen = form.get("imagen");
  if (imagen.size > MAX_BYTES_CLAUDE) return json({ error: "Para describir, la imagen debe pesar menos de 5 MB." }, 413);
  const tipo = TIPOS_FOTO[String(form.get("tipo") || "")] ? String(form.get("tipo")) : "foto";
  const lugar = limpio(form.get("lugar"), 80);
  const actual = limpio(form.get("nombre"), 40);

  const modelo = env.MODELO_CLAUDE || MODELO_CLAUDE;
  const pedido = {
    model: modelo,
    max_tokens: 16000,
    system: SISTEMA,
    output_config: { effort: env.ESFUERZO_CLAUDE || "medium", format: { type: "json_schema", schema: ESQUEMA } },
    messages: [{
      role: "user",
      content: [
        { type: "image", source: { type: "base64", media_type: imagen.type, data: aBase64(new Uint8Array(await imagen.arrayBuffer())) } },
        { type: "text", text: [TIPOS_FOTO[tipo], lugar ? `Alojamiento: ${lugar}.` : "", actual ? `El anfitrión llamó a este ambiente «${actual}».` : "", "Prepara los textos del ambiente."].filter(Boolean).join("\n") },
      ],
    }],
  };
  // Si los filtros de seguridad rechazan el pedido, la API lo reintenta sola con el modelo que recomienda.
  // Haiku no tiene este reintento, así que ahí no se pide.
  if (!/haiku/.test(modelo)) Object.assign(pedido, { betas: ["server-side-fallback-2026-07-01"], fallbacks: "default" });

  const cliente = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 90_000 });
  let r;
  try {
    r = await cliente.beta.messages.create(pedido);
  } catch (e) {
    if (e instanceof Anthropic.RateLimitError) return json({ error: "Se alcanzó el límite de uso de Claude. Intenta en un minuto." }, 429);
    if (e instanceof Anthropic.BadRequestError) { console.log("claude 400", e.message); return json({ error: "Claude no pudo leer esta imagen." }, 502); }
    if (e instanceof Anthropic.AuthenticationError) { console.log("claude 401"); return json({ error: "El servidor de IA no está configurado." }, 500); }
    if (e instanceof Anthropic.APIError) { console.log("claude", e.status, e.message); return json({ error: "Claude no respondió. Intenta otra vez." }, 502); }
    return json({ error: "No se pudo contactar a Claude. Intenta otra vez." }, 502);
  }
  if (r.stop_reason === "refusal") return json({ error: "Claude no describió esta imagen. Prueba con otra foto del ambiente." }, 422);
  if (r.stop_reason === "max_tokens") return json({ error: "La respuesta de Claude quedó incompleta. Intenta otra vez." }, 502);
  const texto = r.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  let datos;
  try { datos = normalizar(JSON.parse(texto)); } catch { return json({ error: "Claude devolvió una respuesta que no se pudo leer." }, 502); }
  return json({ ...datos, modelo: r.model }, 200);
}
