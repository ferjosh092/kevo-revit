// Pruebas del Worker sin llamar a OpenAI: se reemplaza fetch por una respuesta simulada.
//   node --test web/wasi3d/worker/test/worker.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { PROMPTS, PANORAMA } from "../src/index.js";

const ENV = { OPENAI_API_KEY: "sk-prueba", CODIGO_ACCESO: "andes-2026", ORIGENES: "https://wasi3d.pe", MODELO: "gpt-image-1" };
const PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

function pedido({ codigo = "andes-2026", modo = "ordenar", alcance = "vista", tipo = "image/jpeg", bytes = 1000, extra = "", origen = "https://wasi3d.pe" } = {}) {
  const fd = new FormData();
  fd.append("imagen", new File([new Uint8Array(bytes)], "sala.jpg", { type: tipo }));
  fd.append("modo", modo);
  fd.append("alcance", alcance);
  if (extra) fd.append("extra", extra);
  return new Request("https://wasi3d.pe/api/mejorar", { method: "POST", headers: { "X-Wasi-Codigo": codigo, Origin: origen }, body: fd });
}

function simularOpenAI(estado = 200) {
  const llamadas = [];
  globalThis.fetch = async (url, init) => {
    llamadas.push({ url, init });
    if (estado !== 200) return new Response(JSON.stringify({ error: { message: "fallo" } }), { status: estado });
    return new Response(JSON.stringify({ data: [{ b64_json: PNG_1PX }] }), { status: 200 });
  };
  return llamadas;
}

test("rechaza un código de acceso incorrecto", async () => {
  simularOpenAI();
  const r = await worker.fetch(pedido({ codigo: "otro" }), ENV);
  assert.equal(r.status, 401);
});

test("rechaza un origen no autorizado", async () => {
  simularOpenAI();
  const r = await worker.fetch(pedido({ origen: "https://otro-sitio.com" }), ENV);
  assert.equal(r.status, 403);
});

test("rechaza formatos que no son imagen y modos desconocidos", async () => {
  simularOpenAI();
  assert.equal((await worker.fetch(pedido({ tipo: "application/pdf" }), ENV)).status, 400);
  assert.equal((await worker.fetch(pedido({ modo: "borrar" }), ENV)).status, 400);
});

test("rechaza imágenes de más de 20 MB", async () => {
  simularOpenAI();
  const r = await worker.fetch(pedido({ bytes: 21 * 1024 * 1024 }), ENV);
  assert.equal(r.status, 413);
});

test("envía la imagen y el prompt a OpenAI y devuelve un PNG", async () => {
  const llamadas = simularOpenAI();
  const r = await worker.fetch(pedido({ alcance: "panorama", extra: "sofás grises\u0007" }), ENV);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Content-Type"), "image/png");
  assert.equal(r.headers.get("Access-Control-Allow-Origin"), "https://wasi3d.pe");
  const bytes = new Uint8Array(await r.arrayBuffer());
  assert.deepEqual([...bytes.slice(1, 4)], [80, 78, 71]); // "PNG"
  assert.equal(llamadas.length, 1);
  const { url, init } = llamadas[0];
  assert.equal(url, "https://api.openai.com/v1/images/edits");
  assert.equal(init.headers.Authorization, "Bearer sk-prueba");
  const prompt = init.body.get("prompt");
  assert.ok(prompt.startsWith(PANORAMA));
  assert.ok(prompt.includes(PROMPTS.ordenar));
  assert.ok(prompt.includes("sofás grises"));
  assert.ok(!prompt.includes("\u0007"), "limpia caracteres de control");
  assert.equal(init.body.get("model"), "gpt-image-1");
  assert.equal(init.body.get("size"), "1536x1024");
});

test("no expone detalles de OpenAI cuando falla", async () => {
  simularOpenAI(500);
  const r = await worker.fetch(pedido(), ENV);
  assert.equal(r.status, 502);
  const j = await r.json();
  assert.ok(!JSON.stringify(j).includes("sk-prueba"));
});

test("sin clave configurada responde 500 sin llamar a OpenAI", async () => {
  const llamadas = simularOpenAI();
  const r = await worker.fetch(pedido(), { ...ENV, OPENAI_API_KEY: "" });
  assert.equal(r.status, 500);
  assert.equal(llamadas.length, 0);
});
