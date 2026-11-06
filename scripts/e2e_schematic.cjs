// 4차 S4 도식 노선도 브라우저 확인 (Playwright). 사용: (cd web && python3 -m http.server 8765 &) ; node scripts/e2e_schematic.cjs docs/reports/evidence
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'docs/reports/evidence';
const BASE = 'http://localhost:8765';
const log = [];
const checks = [];
const say = (s) => { log.push(s); console.log(s); };
const check = (name, ok, detail = '') => { checks.push({ name, ok }); say(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`); };

(async () => {
  const b = await chromium.launch();
  const errors = [];
  for (const [name, opts] of [['desktop', { viewport: { width: 1280, height: 900 } }], ['mobile', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }]]) {
    say(`\n=== ${name} ===`);
    const ctx = await b.newContext({ ...opts, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push(`${name} pageerror ${e.message}`));
    pg.on('console', (m) => { if (m.type() === 'error' && !/ERR_|Failed to load resource/.test(m.text())) errors.push(`${name} console ${m.text()}`); });
    await pg.goto(`${BASE}/schematic.html`);
    await pg.waitForFunction(() => window.__sch && document.querySelectorAll('#sch-svg line').length > 50);
    const tabs = await pg.$$eval('#sch-tabs button', (bs) => bs.map((x) => x.textContent));
    check(`[${name}] 권역 패널 6개`, tabs.length === 6, tabs.join(', '));
    const sw = await pg.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    check(`[${name}] 가로 넘침 없음`, sw[0] <= sw[1], `${sw[0]} / ${sw[1]}`);
    // 지리 ↔ 도식 전환: 같은 역 원의 좌표가 바뀐다
    const c0 = await pg.$eval('.sch-st circle', (c) => [c.getAttribute('cx'), c.getAttribute('cy')]);
    await pg.click('[data-view="geo"]');
    await pg.waitForTimeout(700);
    const c1 = await pg.$eval('.sch-st circle', (c) => [c.getAttribute('cx'), c.getAttribute('cy')]);
    check(`[${name}] 지리 ↔ 도식 전환 토글`, c0.join() !== c1.join(), `${c0} → ${c1}`);
    if (name === 'desktop') await pg.screenshot({ path: `${OUT}/s_seoul_geo_desktop.png` });
    await pg.click('[data-view="schematic"]');
    await pg.waitForTimeout(700);
    if (name === 'desktop') await pg.screenshot({ path: `${OUT}/s_seoul_schematic_desktop.png` });
    // 같은 권역 포탈 점선 (양평·신촌 등)
    const same = await pg.$$eval('.sch-same line', (ls) => ls.length);
    check(`[${name}] 같은 권역 포탈 점선`, same >= 2, `${same}개`);
    // 포탈 아이콘 클릭 → 목적지 → 패널 이동 (수도권 교대 → 부산)
    const gy = await pg.evaluate(() => window.__sch.data.clusters.findIndex((c) => c.n === '교대' && c.city === '수도권'));
    await pg.$eval(`.sch-st[data-c="${gy}"]`, (g) => g.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 300, clientY: 300 })));
    await pg.waitForSelector('#sch-pop:not([hidden]) button');
    const opts2 = await pg.$$eval('#sch-pop button', (bs) => bs.map((x) => x.textContent.replace(/\s+/g, ' ').trim()));
    const bi = opts2.findIndex((t) => t.includes('부산'));
    await pg.click(`#sch-pop button >> nth=${bi}`);
    await pg.waitForFunction(() => window.__sch.state.region === 'busan');
    check(`[${name}] 포탈 아이콘 → 목적지 권역 패널로 이동`, true, opts2.join(' / '));
    if (name === 'desktop') await pg.screenshot({ path: `${OUT}/s_busan_desktop.png` });
    // 길찾기: 목동 → 부산 동래
    await pg.fill('#sch-from', '목동');
    await pg.fill('#sch-to', '부산 동래');
    await pg.click('#sch-form button[type=submit]');
    await pg.waitForSelector('#sch-route .steps');
    const sum = (await pg.textContent('#sch-route .summary')).replace(/\s+/g, ' ');
    const go = await pg.$$eval('#sch-route .sch-go', (bs) => bs.map((x) => x.textContent));
    const hl = await pg.$$eval('.sch-route line', (ls) => ls.length);
    check(`[${name}] 경로 하이라이트 + 워프는 패널 이동 단계`, sum.includes('수도권 → 대전 → 부산') && go.length === 2 && hl > 0, `${sum} · 이동 버튼 ${go.join(', ')} · 하이라이트 ${hl}`);
    const onRoute = await pg.$$eval('#sch-tabs button.on-route', (bs) => bs.map((x) => x.textContent));
    check(`[${name}] 경로가 지나는 권역 탭 표시`, onRoute.join() === '수도권,부산,대전' || onRoute.length === 3, onRoute.join(', '));
    await pg.click('#sch-route .sch-go >> nth=0');
    await pg.waitForFunction(() => window.__sch.state.region === 'daejeon');
    check(`[${name}] 패널 이동 버튼 → 대전 패널`, true);
    if (name === 'desktop') await pg.screenshot({ path: `${OUT}/s_route_daejeon_desktop.png` });
    if (name === 'mobile') await pg.screenshot({ path: `${OUT}/s_route_mobile.png`, fullPage: true });
    // 국가 간 번들: 판교 → 타이베이 板橋
    await pg.selectOption('#sch-rs', 'tw_t12');
    await pg.waitForFunction(() => window.__sch.data.meta.ruleset === 'tw_t12');
    await pg.fill('#sch-from', '판교');
    await pg.fill('#sch-to', '타이베이 板橋');
    await pg.click('#sch-form button[type=submit]');
    await pg.waitForFunction(() => document.querySelector('#sch-route .summary')?.textContent.includes('타이베이'));
    await pg.click('#sch-route .sch-go >> nth=0');
    await pg.waitForFunction(() => window.__sch.state.region === 'taipei');
    check(`[${name}] 국가 간 워프 → 타이베이 패널`, true, (await pg.textContent('#sch-route .summary')).replace(/\s+/g, ' '));
    if (name === 'desktop') await pg.screenshot({ path: `${OUT}/s_taipei_desktop.png` });
    await ctx.close();
  }
  check('콘솔 에러 0건', errors.length === 0, JSON.stringify(errors));
  const nf = checks.filter((c) => !c.ok).length;
  say(`\n요약: ${checks.length - nf}/${checks.length} 통과`);
  fs.writeFileSync(`${OUT}/s_browser.txt`, log.join('\n') + '\n');
  await b.close();
  process.exit(nf ? 1 : 0);
})();
