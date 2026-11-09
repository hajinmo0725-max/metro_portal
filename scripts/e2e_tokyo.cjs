// 5차 T3 브라우저 E2E (Playwright). 사용: (cd web && python3 -m http.server 8765 &) ; node scripts/e2e_tokyo.cjs docs/reports/evidence
// 길찾기 ruleset 선택에 '한국+타이베이+도쿄'가 있고, 예시 버튼(판교 → 도쿄 板橋)이 번들을 바꿔 워프 한 번으로 잇는지 본다
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const out = process.argv[2] || '.';
  const b = await chromium.launch();
  const errors = [], log = [];
  const say = (...a) => { const s = a.join(' '); log.push(s); console.log(s); };
  for (const [name, opts] of [['desktop', { viewport: { width: 1280, height: 860 } }], ['mobile', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }]]) {
    const ctx = await b.newContext({ ...opts, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push(name + ' pageerror ' + e.message));
    pg.on('console', (m) => { if (m.type() === 'error' && !/tile\.openstreetmap|ERR_|Failed to load resource/.test(m.text())) errors.push(name + ' console ' + m.text()); });
    await pg.goto('http://localhost:8765/index.html');
    await pg.waitForFunction(() => document.querySelectorAll('#ruleset-select option').length > 0 && window.__app);
    const opts2 = await pg.$$eval('#ruleset-select option', (os) => os.map((o) => o.value + '=' + o.textContent));
    say(name, 'ruleset options:', opts2.filter((x) => x.startsWith('ktj')).join(' | '));
    await pg.click('.examples button[data-rs="ktj_t12"]');
    await pg.waitForFunction(() => /총비용/.test(document.querySelector('#result').textContent), null, { timeout: 15000 });
    const res = (await pg.textContent('#result')).replace(/\s+/g, ' ').trim();
    say(name, 'route 판교 → 도쿄권 板橋 @', await pg.$eval('#ruleset-select', (s) => s.value), ':', res.slice(0, 260));
    const stats = await pg.evaluate(() => ({ clusters: window.__app.data.clusters.length, jp: window.__app.data.clusters.filter((c) => (c.co || '').includes('JP')).length, portals: window.__app.data.portals.length }));
    say(name, 'bundle', JSON.stringify(stats));
    await pg.waitForTimeout(900);
    await pg.screenshot({ path: `${out}/t3_route_tokyo_${name}.png` });
    if (name === 'desktop') {
      // 도쿄 지도 보기 + 3국 공통 포탈 아크
      await pg.goto('http://localhost:8765/index.html#from=新宿&to=판교&rs=ktj_t12');
      await pg.reload();
      await pg.waitForFunction(() => /총비용|연결 안 됨|여러 역/.test(document.querySelector('#result').textContent), null, { timeout: 15000 });
      say(name, 'route 新宿 → 판교:', (await pg.textContent('#result')).replace(/\s+/g, ' ').trim().slice(0, 260));
      await pg.click('[data-view="jp"]');
      await pg.waitForTimeout(800);
      await pg.screenshot({ path: `${out}/t3_tokyo_map_desktop.png` });
    }
    await ctx.close();
  }
  await b.close();
  say('ERRORS', errors.length ? errors.join('\n') : 'none');
  fs.writeFileSync(`${out}/t3_browser.txt`, log.join('\n') + '\n');
  process.exit(errors.length ? 1 : 0);
})();
