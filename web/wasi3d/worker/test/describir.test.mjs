// Pruebas de /api/describir sin llamar a Claude: se reemplaza fetch por una respuesta simulada.
//   node --test web/wasi3d/worker/test/describir.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { SISTEMA, ESQUEMA, MODELO_CLAUDE } from "../src/describir.js";

const ENV = { ANTHROPIC_API_KEY: "sk-ant-prueba", CODIGO_ACCESO: "andes-2026", ORIGENES: "https://wasi3d.pe" };

function pedido({ codigo = "andes-2026", tipo = "image/jpeg", bytes = 1000, tipoFoto = "360", nombre = "IMG 2041", lugar = "Departamento en San Blas" } = {}) {
  const fd = new FormData();
  fd.append("imagen", new File([new Uint8Array(bytes).fill(7)], "sala.jpg", { type: tipo }));
  fd.append("tipo", tipoFoto);
  fd.append("nombre", nombre);
  fd.append("lugar", lugar);
  return new Request("https://wasi3d.pe/api/describir", { method: "POST", headers: { "X-Wasi-Codigo": codigo, Origin: "https://wasi3d.pe" }, body: fd });
}

const RESPUESTA = {
  nombre: "Sala principal", nombre_en: "Living room",
  resumen: "Una sala amplia con luz natural.", resumen_en: "A spacious living room with natural light.",
  puntos: [
    { titulo: "Ventanales", titulo_en: "Windows", texto: "Entra luz toda la mañana.", texto_en: "Morning light all day.", x: 0.31, y: 0.42 },
    { titulo: "Zona de estar <b>", titulo_en: "Lounge", texto: "Sofás frente al televisor.", texto_en: "Sofas facing the TV.", x: 1.7, y: -2 },
    { titulo: "", titulo_en: "", texto: "", texto_en: "", x: 0.5, y: 0.5 },
  ],
  privacidad: ["Hay una persona reflejada en el televisor"],
};

function simularClaude({ estado = 200, stop = "end_turn", texto = JSON.stringify(RESPUESTA) } = {}) {
  const llamadas = [];
  globalThis.fetch = async (url, init) => {
    llamadas.push({ url: String(url), init });
    const h = { "content-type": "application/json", "request-id": "req_prueba" };
    if (estado !== 200) return new Response(JSON.stringify({ type: "error", error: { type: "api_error", message: "fallo interno sk-ant-prueba" } }), { status: estado, headers: h });
    return new Response(JSON.stringify({
      id: "msg_prueba", type: "message", role: "assistant", model: MODELO_CLAUDE, stop_reason: stop, stop_sequence: null,
      content: stop === "refusal" ? [] : [{ type: "text", text: texto }],
      usage: { input_tokens: 2100, output_tokens: 600 },
    }), { status: 200, headers: h });
  };
  return llamadas;
}

test("envía la foto a Claude con el esquema y devuelve propuestas limpias", async () => {
  const llamadas = simularClaude();
  const r = await worker.fetch(pedido(), ENV);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Access-Control-Allow-Origin"), "https://wasi3d.pe");
  const j = await r.json();
  assert.equal(j.nombre, "Sala principal");
  assert.equal(j.puntos.length, 2, "descarta puntos sin título");
  assert.ok(!/[<>]/.test(j.puntos[1].titulo), "quita < y >");
  assert.deepEqual([j.puntos[1].x, j.puntos[1].y], [1, 0], "limita la posición a la imagen");
  assert.deepEqual(j.privacidad, ["Hay una persona reflejada en el televisor"]);

  assert.equal(llamadas.length, 1);
  const { url, init } = llamadas[0];
  assert.ok(url.startsWith("https://api.anthropic.com/v1/messages"));
  const h = new Headers(init.headers);
  assert.equal(h.get("x-api-key"), "sk-ant-prueba");
  assert.ok(h.get("anthropic-beta").includes("server-side-fallback-2026-07-01"));
  const body = JSON.parse(init.body);
  assert.equal(body.model, MODELO_CLAUDE);
  assert.equal(body.system, SISTEMA);
  assert.equal(body.fallbacks, "default");
  assert.deepEqual(body.output_config.format, { type: "json_schema", schema: ESQUEMA });
  assert.equal(body.output_config.effort, "medium");
  const [img, txt] = body.messages[0].content;
  assert.equal(img.source.media_type, "image/jpeg");
  assert.equal(Buffer.from(img.source.data, "base64").length, 1000);
  assert.ok(txt.text.includes("equirectangular"));
  assert.ok(txt.text.includes("San Blas"));
});

test("con Haiku no pide reintento con otro modelo", async () => {
  const llamadas = simularClaude();
  const r = await worker.fetch(pedido(), { ...ENV, MODELO_CLAUDE: "claude-haiku-5-5" });
  assert.equal(r.status, 200);
  const body = JSON.parse(llamadas[0].init.body);
  assert.equal(body.model, "claude-haiku-5-5");
  assert.equal(body.fallbacks, undefined);
});

test("rechaza imágenes de más de 5 MB sin llamar a Claude", async () => {
  const llamadas = simularClaude();
  const r = await worker.fetch(pedido({ bytes: 6 * 1024 * 1024 }), ENV);
  assert.equal(r.status, 413);
  assert.equal(llamadas.length, 0);
});

test("pide código de acceso y clave configurada", async () => {
  const llamadas = simularClaude();
  assert.equal((await worker.fetch(pedido({ codigo: "x" }), ENV)).status, 401);
  assert.equal((await worker.fetch(pedido(), { ...ENV, ANTHROPIC_API_KEY: "" })).status, 500);
  assert.equal(llamadas.length, 0);
});

test("maneja rechazo, respuesta ilegible y errores sin exponer detalles", async () => {
  simularClaude({ stop: "refusal" });
  assert.equal((await worker.fetch(pedido(), ENV)).status, 422);
  simularClaude({ texto: "no es json" });
  assert.equal((await worker.fetch(pedido(), ENV)).status, 502);
  simularClaude({ estado: 500 });
  const r = await worker.fetch(pedido(), ENV);
  assert.equal(r.status, 502);
  assert.ok(!JSON.stringify(await r.json()).includes("sk-ant"));
});
