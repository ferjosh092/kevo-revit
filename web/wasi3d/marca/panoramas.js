// Genera los panoramas 360° de ejemplo (equirectangulares 2:1) y el plano del creador de recorridos,
// fotografiando la maqueta 3D de la landing desde cada ambiente.
//   python3 -m http.server 8765 --directory web/wasi3d   (en otra terminal)
//   node web/wasi3d/marca/panoramas.js
// Las librerías se sirven desde node_modules si el CDN no está disponible (variable LIBS).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'demo');
const URL = process.env.WASI_URL || 'http://localhost:8765/index.html#panoramas';
const LIBS = process.env.LIBS ? JSON.parse(process.env.LIBS) : null;
const TOMAS = [
  { id: 'sala', x: 2.4, z: 2.3 },
  { id: 'cocina', x: 7.0, z: 1.9 },
  { id: 'dormitorio', x: 2.3, z: 5.5 },
  { id: 'bano', x: 4.65, z: 5.3 },
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  if (LIBS) await page.route(/\.min\.js$/, (r) => {
    const f = r.request().url().split('/').pop();
    return LIBS[f] ? r.fulfill({ path: LIBS[f], contentType: 'application/javascript', headers: { 'access-control-allow-origin': '*' } }) : r.continue();
  });
  await page.goto(URL);
  await page.waitForFunction(() => window.__wasiEscena && window.__wasiViewer, null, { timeout: 30000 });
  await page.evaluate(() => window.__wasiViewer.setBuild(1));
  await page.waitForTimeout(1500);

  const fotos = await page.evaluate((tomas) => {
    const { scene, renderer, ceiling, pano, rings, W, D } = window.__wasiEscena;
    ceiling.visible = true; pano.visible = true; rings.forEach((r) => { r.visible = false; });
    renderer.shadowMap.needsUpdate = true;
    const cubeRT = new THREE.WebGLCubeRenderTarget(1024, { generateMipmaps: false });
    cubeRT.texture.encoding = THREE.sRGBEncoding;
    const cubo = new THREE.CubeCamera(0.05, 200, cubeRT);
    scene.add(cubo);
    // Cubo -> equirectangular: el centro de la imagen mira al norte (-z) y crece hacia la derecha (+x)
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
      uniforms: { env: { value: cubeRT.texture } },
      vertexShader: 'varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}',
      fragmentShader: 'uniform samplerCube env;varying vec2 vUv;void main(){float lon=(vUv.x-.5)*6.2831853;float lat=(vUv.y-.5)*3.1415927;vec3 d=vec3(cos(lat)*sin(lon),sin(lat),-cos(lat)*cos(lon));gl_FragColor=textureCube(env,d);}',
      depthTest: false, depthWrite: false,
    }));
    const escenaQuad = new THREE.Scene(); escenaQuad.add(quad);
    const camQuad = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const tam = new THREE.Vector2(); renderer.getSize(tam);
    const pr = renderer.getPixelRatio();
    renderer.setPixelRatio(1);
    const out = {};
    for (const t of tomas) {
      cubo.position.set(t.x, 1.5, t.z);
      cubo.update(renderer, scene);
      renderer.setSize(2048, 1024, false);
      renderer.render(escenaQuad, camQuad);
      out[t.id] = renderer.domElement.toDataURL('image/jpeg', 0.84);
    }
    // Plano visto desde arriba, sin techo, para el minimapa del recorrido
    ceiling.visible = false; pano.visible = false;
    const m = 0.4;
    const orto = new THREE.OrthographicCamera(-m, W + m, -m, -(D + m), 0.1, 60);
    orto.position.set(0, 30, 0); orto.up.set(0, 0, -1); orto.lookAt(0, 0, 0);
    orto.left = -m; orto.right = W + m; orto.top = D + m; orto.bottom = -m;
    orto.position.set(0, 30, 0); orto.lookAt(0, 0, 0);
    // Cámara cenital: x del mundo a la derecha, z del mundo hacia abajo de la imagen
    const cen = new THREE.OrthographicCamera(-(W / 2 + m), W / 2 + m, D / 2 + m, -(D / 2 + m), 0.1, 60);
    cen.position.set(W / 2, 30, D / 2); cen.up.set(0, 0, -1); cen.lookAt(W / 2, 0, D / 2);
    renderer.setSize(1200, Math.round(1200 * (D + 2 * m) / (W + 2 * m)), false);
    renderer.setClearColor(0xf2efe8, 1);
    renderer.render(scene, cen);
    out.plano = renderer.domElement.toDataURL('image/png');
    out.margen = m;
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(pr); renderer.setSize(tam.x, tam.y, false);
    return out;
  }, TOMAS);

  for (const t of TOMAS) {
    fs.writeFileSync(path.join(OUT, `${t.id}.jpg`), Buffer.from(fotos[t.id].split(',')[1], 'base64'));
    console.log('panorama', t.id);
  }
  fs.writeFileSync(path.join(OUT, 'plano.png'), Buffer.from(fotos.plano.split(',')[1], 'base64'));
  console.log('plano listo; margen', fotos.margen, 'm');
  await browser.close();
})();
