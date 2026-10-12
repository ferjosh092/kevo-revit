// Convierte cada SVG de marca/svg a PNG (y el ícono de app a varios tamaños).
//   npm i -D playwright   (o usa uno global)
//   node web/wasi3d/marca/render.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SVG = path.join(__dirname, 'svg');
const PNG = path.join(__dirname, 'png');
const EXTRA = { 'icono-app.svg': [192, 512], 'icono-app-redondo.svg': [180, 512], 'favicon.svg': [32, 48] };

(async () => {
  fs.mkdirSync(PNG, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const file of fs.readdirSync(SVG).filter((f) => f.endsWith('.svg'))) {
    const src = fs.readFileSync(path.join(SVG, file), 'utf8');
    const [, w, h] = src.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/).map(Number);
    const sizes = EXTRA[file] || [null];
    for (const size of sizes) {
      const scale = size ? size / w : (w < 600 ? 2 : 1);
      const W = Math.round(w * scale), H = Math.round(h * scale);
      await page.setViewportSize({ width: W, height: H });
      await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${W}px;height:${H}px}</style>${src}`);
      const out = path.join(PNG, file.replace('.svg', size ? `-${size}.png` : '.png'));
      await page.screenshot({ path: out, omitBackground: true });
      console.log('PNG', path.basename(out), `${W}×${H}`);
    }
  }
  await browser.close();
})();
