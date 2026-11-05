// Phase 1 지도·ruleset 토글 브라우저 E2E (Playwright). 사용: (cd web && python3 -m http.server 8765 &) ; node scripts/e2e_world.cjs docs/reports/evidence
const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2] || '.';
  const b = await chromium.launch();
  const errors = [];
  const log = [];
  for (const [name, opts] of [['desktop', { viewport: { width: 1280, height: 800 } }], ['mobile', { viewport: { width: 390, height: 844 }, isMobile: true }]]) {
    const ctx = await b.newContext({ ...opts, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push(name + ' pageerror ' + e.message));
    pg.on('console', (m) => { if (m.type() === 'error' && !/tile\.openstreetmap|ERR_|Failed to load resource/.test(m.text())) errors.push(name + ' console ' + m.text()); });
    await pg.goto('http://localhost:8765/index.html');
    await pg.waitForFunction(() => document.querySelector('#stats').textContent.includes('포탈'));
    log.push(`${name} 처음: ${await pg.textContent('#stats')} | ${await pg.textContent('#ruleset')}`);
    // 공식명만 (tw_t12) → 판교 → 타이베이 板橋 연결 안 됨
    await pg.selectOption('#ruleset-select', 'tw_t12');
    await pg.waitForFunction(() => document.querySelector('#ruleset').textContent.startsWith('tw_t12 '));
    await pg.fill('#from', '판교');
    await pg.fill('#to', '타이베이 板橋');
    await pg.click('button.primary');
    log.push(`${name} tw_t12: ${(await pg.textContent('#result')).replace(/\s+/g, ' ').trim()} | 안내: ${await pg.textContent('#ruleset-note')}`);
    // 참고 번들 → 국가 간 T2 워프
    await pg.selectOption('#ruleset-select', 'tw_t12_label');
    await pg.waitForFunction(() => document.querySelector('#ruleset').textContent.startsWith('tw_t12_label'));
    await pg.waitForSelector('#result .summary');
    const res = (await pg.textContent('#result')).replace(/\s+/g, ' ').trim();
    log.push(`${name} tw_t12_label: ${res} | ${await pg.textContent('#stats')}`);
    if (!/국가 간 워프 T2/.test(res)) errors.push(name + ' 국가 간 워프가 결과에 없음');
    await pg.screenshot({ path: `${out}/b4_world_${name}.png` });
    // 강남 → 타이베이 台北車站 (해시 복원 경로). 해시만 바뀌면 새로 안 읽으므로 빈 페이지를 거친다
    await pg.goto('about:blank');
    await pg.goto('http://localhost:8765/index.html#from=강남&to=타이베이 台北車站&warp=1&rs=tw_t123_label');
    await pg.waitForSelector('#result .summary');
    log.push(`${name} 해시 복원 tw_t123_label 강남→台北車站: ${(await pg.textContent('#result .summary')).replace(/\s+/g, ' ').trim()}`);
    await ctx.close();
  }
  await b.close();
  console.log(log.join('\n'));
  console.log('ERRORS', errors.length, errors);
  process.exit(errors.length ? 1 : 0);
})();
