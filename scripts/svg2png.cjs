// SVG 파일들을 PNG로 렌더 (Playwright). 사용: node scripts/svg2png.cjs [--max 1400] in1.svg out1.png [in2.svg out2.png ...]
// --max: 긴 변을 이 픽셀로 줄인다 (5차: LOOM transitmap SVG는 수만 픽셀 크기라서)
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage({ deviceScaleFactor: 1 });
  let args = process.argv.slice(2);
  let max = Infinity;
  if (args[0] === '--max') { max = +args[1]; args = args.slice(2); }
  for (let i = 0; i < args.length; i += 2) {
    const svg = fs.readFileSync(args[i], 'utf8');
    const m = svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
    const W = +m[1], H = +m[2], k = Math.min(1, max / Math.max(W, H));
    const w = Math.ceil(W * k), h = Math.ceil(H * k);
    await pg.setViewportSize({ width: w, height: h });
    const body = svg.replace(/^<\?xml[^>]*>\s*/, '').replace(/<!DOCTYPE[^>]*>\s*/, '')
      .replace(/<svg ([^>]*?)\bwidth="[^"]*"/, '<svg $1').replace(/<svg ([^>]*?)\bheight="[^"]*"/, '<svg $1')
      .replace('<svg ', `<svg width="${w}" height="${h}" `);
    await pg.setContent(`<html><body style="margin:0;background:#fff">${body}</body></html>`);
    await pg.screenshot({ path: args[i + 1] });
  }
  await b.close();
})();
