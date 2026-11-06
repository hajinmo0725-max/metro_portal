// SVG 파일들을 PNG로 렌더 (Playwright). 사용: node scripts/svg2png.cjs in1.svg out1.png [in2.svg out2.png ...]
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage({ deviceScaleFactor: 1 });
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i += 2) {
    const svg = fs.readFileSync(args[i], 'utf8');
    const m = svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
    const w = Math.ceil(+m[1]), h = Math.ceil(+m[2]);
    await pg.setViewportSize({ width: w, height: h });
    await pg.setContent(`<html><body style="margin:0">${svg.replace('<svg ', `<svg width="${w}" height="${h}" `)}</body></html>`);
    await pg.screenshot({ path: args[i + 1] });
  }
  await b.close();
})();
