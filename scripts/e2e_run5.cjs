// 5차 R1·R2·R4 브라우저 E2E (Playwright). 사용: (cd web && python3 -m http.server 8765 &) ; node scripts/e2e_run5.cjs docs/reports/evidence
// R1: 주말 한국+타이베이 퍼즐 날짜·평일 날짜를 최적 경로로 풀어 100점, 번들(ruleset) 확인
// R2: 길찾기 입력 '서울' → 화면 '서울역', 부산 동래 두 역 표기
// R4: 도식 수도권 기본 확대에서 라벨 지표 (선 위 라벨, 겹침 쌍)
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const out = process.argv[2] || '.';
  const b = await chromium.launch();
  const errors = [];
  const log = [];
  const say = (...a) => { const s = a.join(' '); log.push(s); console.log(s); };
  const pz = JSON.parse(fs.readFileSync('web/data/puzzles.json', 'utf8'));
  const day = (d) => new Date(Date.parse(pz.daily_epoch + 'T00:00:00Z') + d * 86400000).toISOString().slice(0, 10);
  const byId = new Map(pz.puzzles.map((p) => [p.id, p]));
  const twDay = pz.daily_order.findIndex((id) => byId.get(id).ruleset !== 'strict');
  const krDay = pz.daily_order.findIndex((id, i) => byId.get(id).ruleset === 'strict' && new Date(Date.parse(day(i))).getUTCDay() === 3);
  const cases = [['tw_weekend', day(twDay)], ['kr_weekday', day(krDay)]];
  for (const [name, date] of cases) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push(name + ' pageerror ' + e.message));
    pg.on('console', (m) => { if (m.type() === 'error' && !/tile\.openstreetmap|ERR_|Failed to load resource/.test(m.text())) errors.push(name + ' console ' + m.text()); });
    await pg.goto(`http://localhost:8765/daily.html#d=${date}`);
    await pg.waitForSelector('#pz-moves button');
    const info = await pg.evaluate(() => ({ ruleset: window.__daily.ruleset, number: window.__daily.number, from: window.__daily.labels[window.__daily.game.from], to: window.__daily.labels[window.__daily.game.to] }));
    const chips = (await pg.textContent('#pz-chips')).replace(/\s+/g, ' ').trim();
    say(name, date, 'ruleset', info.ruleset, '#' + info.number, info.from, '→', info.to, '| chips:', chips);
    const opt = await pg.evaluate(async () => {
      const P = await import('./puzzle.js');
      const d = window.__daily;
      const moves = P.buildMoves(d.data);
      return P.optimalPath(moves, d.game.from, d.game.to).path;
    });
    for (const c of opt.slice(1)) await pg.click(`#pz-moves button[data-to="${c}"]`);
    await pg.waitForSelector('#pz-result:not([hidden])');
    say(name, 'SHARE', (await pg.textContent('#pz-share')).split('\n').slice(0, 2).join(' / '));
    say(name, 'OPT', (await pg.textContent('#pz-optimal')).replace(/\s+/g, ' ').trim().slice(0, 220));
    await pg.waitForTimeout(800);
    await pg.screenshot({ path: `${out}/r1_daily_${name}.png` });
    await ctx.close();
  }
  // R2: 길찾기
  {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push('index pageerror ' + e.message));
    await pg.goto('http://localhost:8765/index.html');
    await pg.waitForFunction(() => document.querySelector('#from'));
    await pg.fill('#from', '서울');
    await pg.fill('#to', '부산 동래');
    await pg.click('#route-form button[type=submit]');
    await pg.waitForTimeout(800);
    const res = (await pg.textContent('#result')).replace(/\s+/g, ' ').trim();
    say('R2 route 서울 → 부산 동래:', res.slice(0, 300));
    await pg.screenshot({ path: `${out}/r2_route_seoul.png` });
    await ctx.close();
  }
  // R4: 도식 라벨 지표 (수도권 기본 확대 3배)
  {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push('schematic pageerror ' + e.message));
    await pg.goto('http://localhost:8765/schematic.html');
    await pg.waitForSelector('#sch-svg circle');
    await pg.waitForTimeout(600);
    for (const r of ['seoul', 'busan', 'taipei']) {
      await pg.click(`#sch-tabs button[data-r="${r}"]`);
      await pg.waitForTimeout(400);
      const st = await pg.evaluate(() => window.__schLabelStats());
      say('R4 labels', r, JSON.stringify(st));
      if (r === 'seoul') await pg.screenshot({ path: `${out}/r4_schematic_seoul.png` });
    }
    await ctx.close();
  }
  await b.close();
  say('ERRORS', errors.length ? errors.join('\n') : 'none');
  fs.writeFileSync(`${out}/run5_browser.txt`, log.join('\n') + '\n');
  process.exit(errors.length ? 1 : 0);
})();
