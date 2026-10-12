// Wasi 3D · servidor de IA para el Estudio (Cloudflare Worker).
//
// /api/mejorar   Envía una imagen a la API de imágenes de OpenAI (ChatGPT) para ordenarla y ambientarla,
//                o para convertir una maqueta 3D en un render fotorrealista.
// /api/describir Envía la foto de un ambiente a Claude (Anthropic), que propone su nombre y los puntos
//                de información en español e inglés (ver describir.js).
// Las claves viven solo aquí, como secretos del Worker: nunca llegan al navegador.
//
// Secretos:  OPENAI_API_KEY, ANTHROPIC_API_KEY, CODIGO_ACCESO   (wrangler secret put …)
//            Basta con la clave del servicio que uses.
// Variables: MODELO, CALIDAD, FIDELIDAD, MODELO_CLAUDE, ESFUERZO_CLAUDE, ORIGENES   (wrangler.toml)
// Opcional:  LIMITE  (binding de Rate Limiting de Cloudflare)

import { describir } from "./describir.js";

const MAX_BYTES = 20 * 1024 * 1024;
const TIPOS = new Set(["image/jpeg", "image/png", "image/webp"]);

export const PROMPTS = {
  ordenar:
    "Photorealistic real-estate photograph of exactly the same room. Keep the architecture identical: walls, " +
    "columns, ceiling, windows, curtains, doors, floor tiles, camera position, perspective and proportions. " +
    "Remove clutter: clothes, plastic covers on the furniture, boxes, bags, cables, toys and loose objects. Keep " +
    "the main furniture in place but clean and tidy. Bright natural daylight, balanced exposure, true-to-life " +
    "colors, sharp details. No people, no text, no watermarks.",
  render:
    "Turn this 3D model render into a photorealistic interior photograph of the same room in an apartment in " +
    "Cusco, Peru. Keep exactly the same layout, furniture placement, camera position, window positions and " +
    "proportions. Realistic materials: wooden floor planks, plastered walls, eucalyptus ceiling beams, Andean " +
    "woven textiles, soft natural daylight from the windows and subtle shadows. No people, no text, no watermarks.",
};

export const PANORAMA =
  "This image is a 360-degree equirectangular panorama that was stretched to fit the canvas. Preserve the " +
  "equirectangular projection, the curved horizon and every object position. The left and right edges must " +
  "continue seamlessly into each other.";

const json = (cuerpo, estado, extra = {}) =>
  new Response(JSON.stringify(cuerpo), {
    status: estado,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...extra },
  });

// Comparación en tiempo constante del código de acceso
async function igual(a, b) {
  const enc = new TextEncoder();
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(String(a))),
    crypto.subtle.digest("SHA-256", enc.encode(String(b))),
  ]);
  const x = new Uint8Array(ha), y = new Uint8Array(hb);
  let d = 0;
  for (let i = 0; i < x.length; i++) d |= x[i] ^ y[i];
  return d === 0;
}

function base64ABytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origen = req.headers.get("Origin") || "";
    const permitidos = String(env.ORIGENES || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = permitidos.includes(origen) ? { "Access-Control-Allow-Origin": origen, Vary: "Origin" } : {};

    const ruta = { "/api/mejorar": "OPENAI_API_KEY", "/api/describir": "ANTHROPIC_API_KEY" }[url.pathname];
    if (!ruta) return json({ error: "No encontrado." }, 404, cors);
    if (req.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: { ...cors, "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type, X-Wasi-Codigo", "Access-Control-Max-Age": "86400" },
      });
    }
    if (req.method !== "POST") return json({ error: "Usa POST." }, 405, cors);
    if (origen && !permitidos.includes(origen) && origen !== url.origin) return json({ error: "Origen no permitido." }, 403, cors);
    if (!env[ruta] || !env.CODIGO_ACCESO) return json({ error: "El servidor de IA no está configurado." }, 500, cors);
    if (!(await igual(req.headers.get("X-Wasi-Codigo") || "", env.CODIGO_ACCESO))) return json({ error: "Código de acceso incorrecto." }, 401, cors);
    if (env.LIMITE) {
      const { success } = await env.LIMITE.limit({ key: req.headers.get("CF-Connecting-IP") || "anon" });
      if (!success) return json({ error: "Demasiadas solicitudes. Espera un minuto." }, 429, cors);
    }
    if (+(req.headers.get("Content-Length") || 0) > MAX_BYTES + 64 * 1024) return json({ error: "La imagen pesa más de 20 MB." }, 413, cors);

    let form;
    try { form = await req.formData(); } catch { return json({ error: "Solicitud no válida." }, 400, cors); }
    const imagen = form.get("imagen");
    if (!imagen || typeof imagen === "string" || !TIPOS.has(imagen.type)) return json({ error: "Envía una imagen JPG, PNG o WebP." }, 400, cors);
    if (imagen.size > MAX_BYTES) return json({ error: "La imagen pesa más de 20 MB." }, 413, cors);
    if (url.pathname === "/api/describir") return describir(form, env, (cuerpo, estado) => json(cuerpo, estado, cors));
    const modo = String(form.get("modo") || "");
    if (!PROMPTS[modo]) return json({ error: "Modo no válido." }, 400, cors);
    const panorama = form.get("alcance") === "panorama";
    const extra = String(form.get("extra") || "").replace(/[\u0000-\u001F\u007F]/g, " ").trim().slice(0, 300);
    const prompt = [panorama ? PANORAMA : "", PROMPTS[modo], extra ? `Additional request from the host: ${extra}` : ""].filter(Boolean).join("\n\n");

    const modelo = env.MODELO || "gpt-image-1";
    const fd = new FormData();
    fd.append("model", modelo);
    fd.append("image", imagen, imagen.name || "imagen.jpg");
    fd.append("prompt", prompt);
    fd.append("size", "1536x1024");
    fd.append("quality", env.CALIDAD || "high");
    if (env.FIDELIDAD) fd.append("input_fidelity", env.FIDELIDAD);

    let r, j;
    try {
      r = await fetch("https://api.openai.com/v1/images/edits", { method: "POST", headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}` }, body: fd });
      j = await r.json().catch(() => ({}));
    } catch {
      return json({ error: "No se pudo contactar al servicio de IA. Intenta otra vez." }, 502, cors);
    }
    if (!r.ok) {
      console.log("openai", r.status, j && j.error && j.error.message);
      const msg = r.status === 400 ? "OpenAI rechazó la imagen o las instrucciones." : r.status === 429 ? "Se alcanzó el límite de uso de OpenAI. Intenta más tarde." : "El servicio de IA no respondió. Intenta otra vez.";
      return json({ error: msg }, 502, cors);
    }
    const b64 = j && j.data && j.data[0] && j.data[0].b64_json;
    if (!b64) return json({ error: "El servicio de IA no devolvió una imagen." }, 502, cors);
    return new Response(base64ABytes(b64), {
      headers: { ...cors, "Content-Type": "image/png", "Cache-Control": "no-store", "X-Wasi-Modelo": modelo },
    });
  },
};
