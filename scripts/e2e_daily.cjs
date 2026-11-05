// 데일리 퍼즐 브라우저 E2E (Playwright). 사용: (cd web && python3 -m http.server 8765 &) ; node scripts/e2e_daily.cjs docs/reports/evidence
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const errors = [];
  for (const [name, opts] of [['desktop', { viewport: { width: 1280, height: 800 } }], ['mobile', { viewport: { width: 390, height: 844 }, isMobile: true }]]) {
    const ctx = await b.newContext({ ...opts, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push(name + ' pageerror ' + e.message));
    pg.on('console', (m) => { if (m.type() === 'error' && !/tile\.openstreetmap|ERR_|Failed to load resource/.test(m.text())) errors.push(name + ' console ' + m.text()); });
    await pg.goto('http://localhost:8765/daily.html#d=2026-11-05');
    await pg.waitForSelector('#pz-moves button');
    const head = await pg.textContent('#pz-head');
    console.log(name, 'HEAD', head.replace(/\s+/g, ' ').trim());
    // 최적 경로를 퍼즐 로직으로 계산해서 버튼 클릭
    const opt = await pg.evaluate(async () => {
      const P = await import('./puzzle.js');
      const data = await (await fetch('data/kr_strict.json')).json();
      const pz = await (await fetch('data/puzzles.json')).json();
      const moves = P.buildMoves(data);
      const { puzzle } = P.dailyPick(pz, '2026-11-05');
      const idx = new Map(data.clusters.map((c, i) => [c.id, i]));
      return P.optimalPath(moves, idx.get(puzzle.from), idx.get(puzzle.to)).path;
    });
    if (name === 'desktop') {
      // 한 번 헛걸음 + 되돌리기 테스트
      const first = await pg.$$eval('#pz-moves button', (bs) => bs.map((x) => Number(x.dataset.to)));
      const wrong = first.find((t) => t !== opt[1]);
      await pg.click(`#pz-moves button[data-to="${wrong}"]`);
      await pg.click('#pz-undo');
      await pg.screenshot({ path: process.argv[2] + '/daily_start_' + name + '.png' });
    }
    for (const c of opt.slice(1)) await pg.click(`#pz-moves button[data-to="${c}"]`);
    await pg.waitForSelector('#pz-result:not([hidden])');
    console.log(name, 'SHARE\n' + await pg.textContent('#pz-share'));
    console.log(name, 'OPT', (await pg.textContent('#pz-optimal')).replace(/\s+/g, ' ').trim());
    await pg.waitForTimeout(1200);
    await pg.screenshot({ path: process.argv[2] + '/daily_done_' + name + '.png', fullPage: name === 'mobile' });
    // 새로고침해도 결과 유지
    await pg.reload(); await pg.waitForSelector('#pz-result:not([hidden])', { timeout: 5000 });
    console.log(name, 'persisted OK');
    await ctx.close();
  }
  // 다른 날짜 + 포기
  const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } });
  const pg = await ctx.newPage();
  pg.on('pageerror', (e) => errors.push('giveup pageerror ' + e.message));
  await pg.goto('http://localhost:8765/daily.html#d=2026-11-09');
  await pg.waitForSelector('#pz-moves button');
  await pg.click('#pz-giveup');
  console.log('GIVEUP\n' + await pg.textContent('#pz-share'));
  // 메인 페이지도 여전히 동작
  await pg.goto('http://localhost:8765/index.html#from=강남&to=부산 동래');
  await pg.waitForSelector('.summary');
  console.log('INDEX', (await pg.textContent('.summary')).replace(/\s+/g, ' '));
  console.log('ERRORS', JSON.stringify(errors));
  await b.close();
})();
