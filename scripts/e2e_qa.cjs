// 4차 QA 반영 브라우저 확인 (Playwright). Q1·Q3·Q4·Q5·Q6-5 항목을 수치로 검사하고 캡처를 남긴다.
// 사용: (cd web && python3 -m http.server 8765 &) ; node scripts/e2e_qa.cjs docs/reports/evidence
// 결과: <out>/q_browser.txt (검사 로그), <out>/q_*.png (캡처). 지도 타일(tile.openstreetmap.org)은 세션 네트워크에서 막힐 수 있어 회색 배경일 수 있다.
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || 'docs/reports/evidence';
const BASE = 'http://localhost:8765';
const log = [];
const checks = [];
const say = (s) => { log.push(s); console.log(s); };
const check = (name, ok, detail = '') => { checks.push({ name, ok }); say(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`); };
const shot = async (pg, file, full = false) => pg.screenshot({ path: `${OUT}/${file}`, fullPage: full });

async function dailyPage(ctx, hash, errors, tag) {
  const pg = await ctx.newPage();
  pg.on('pageerror', (e) => errors.push(`${tag} pageerror ${e.message}`));
  pg.on('console', (m) => { if (m.type() === 'error' && !/tile\.openstreetmap|ERR_|Failed to load resource/.test(m.text())) errors.push(`${tag} console ${m.text()}`); });
  await pg.goto(`${BASE}/daily.html${hash}`);
  await pg.waitForFunction(() => window.__daily && document.querySelector('#pz-moves button'));
  return pg;
}

async function optimal(pg) {
  return pg.evaluate(async () => {
    const P = await import('./puzzle.js');
    const { game, data } = window.__daily;
    const moves = P.buildMoves(data);
    return P.optimalPath(moves, game.from, game.to).path;
  });
}

(async () => {
  const b = await chromium.launch();
  const errors = [];
  // 가장 긴 노선 태그가 붙는 출발역을 가진 날짜 (세로 줄바꿈 버그 재현용)
  const pz = JSON.parse(fs.readFileSync('web/data/puzzles.json', 'utf8'));
  const data = JSON.parse(fs.readFileSync('web/data/kr_strict.json', 'utf8'));
  const P = await import('../web/puzzle.js');
  const moves = P.buildMoves(data);
  const cix = new Map(data.clusters.map((c, i) => [c.id, i]));
  let longest = { len: 0 };
  pz.daily_order.forEach((pid, d) => {
    const p = pz.puzzles.find((x) => x.id === pid);
    for (const m of moves[cix.get(p.from)]) {
      if (m.type !== 'ride') continue;
      const len = m.lines.map((i) => data.lines[i].name).join(' · ').length;
      if (len > longest.len) longest = { len, d, date: new Date(Date.parse(pz.daily_epoch + 'T00:00:00Z') + d * 864e5).toISOString().slice(0, 10) };
    }
  });

  for (const [name, opts] of [['desktop', { viewport: { width: 1280, height: 800 } }], ['mobile', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }]]) {
    say(`\n=== ${name} ===`);
    const ctx = await b.newContext({ ...opts, deviceScaleFactor: 1 });

    // Q1-1 해시 변경
    let pg = await dailyPage(ctx, '#d=2026-11-05', errors, name);
    const n1 = await pg.evaluate(() => [window.__daily.number, window.__daily.game.puzzle.id]);
    await Promise.all([pg.waitForEvent('load'), pg.evaluate(() => { location.hash = '#d=2026-11-06'; })]);
    await pg.waitForFunction(() => window.__daily && window.__daily.dateStr === '2026-11-06');
    const n2 = await pg.evaluate(() => [window.__daily.number, window.__daily.game.puzzle.id, document.querySelector('#pz-no').textContent]);
    check(`[${name}] Q1 해시만 바꿔도 퍼즐이 바뀐다`, n1[0] === 1 && n2[0] === 2 && n1[1] !== n2[1] && n2[2] === '#2', `${n1[1]} → ${n2[1]} (${n2[2]})`);

    // Q1-3 출시 전 날짜
    for (const d of ['2026-11-04', '2020-01-01']) {
      await Promise.all([pg.waitForEvent('load'), pg.evaluate((h) => { location.hash = h; }, `#d=${d}`)]);
      await pg.waitForFunction(() => window.__daily && document.querySelector('#pz-no').textContent);
      const no = await pg.textContent('#pz-no');
      const warn = await pg.$('.chip.warn');
      check(`[${name}] Q1 출시 전 날짜 ${d} → #1 + 안내`, no === '#1' && !!warn, no);
    }
    await pg.close();

    // Q1-2 세로 줄바꿈: 노선 태그가 가장 긴 날
    pg = await dailyPage(ctx, `#d=${longest.date}`, errors, name);
    const wrap = await pg.$$eval('#pz-moves button', (bs) => bs.map((x) => {
      const nm = x.querySelector('.nm'); const lh = parseFloat(getComputedStyle(nm).lineHeight) || 22;
      return { t: nm.textContent, h: nm.getBoundingClientRect().height, lh, bh: x.getBoundingClientRect().height, tag: x.querySelector('.tag').textContent };
    }));
    const bad = wrap.filter((w) => w.h > w.lh * 1.4);
    check(`[${name}] Q1 역 이름 세로 줄바꿈 없음 (태그 최장 ${longest.len}자, ${longest.date})`, bad.length === 0,
      wrap.map((w) => `${w.t}(${Math.round(w.h)}px)`).join(', '));
    // Q4 이동 버튼 높이 ≥ 44px
    const minH = Math.min(...wrap.map((w) => w.bh));
    check(`[${name}] Q4 이동 버튼 높이 ≥ 44px`, minH >= 44, `최소 ${minH.toFixed(1)}px`);
    // Q3 방면 표시와 고정 정렬
    const dirs = await pg.$$eval('#pz-moves button.ride .dir', (xs) => xs.map((x) => x.textContent));
    check(`[${name}] Q3 승차 후보에 '○○ 방면' 표시`, dirs.length > 0 && dirs.every((t) => t.endsWith('방면')), dirs.join(' / '));
    // Q4 되돌리기·포기 버튼이 첫 화면 안
    const vh = opts.viewport.height;
    const rects = await pg.evaluate(() => ['#pz-undo', '#pz-giveup'].map((s) => document.querySelector(s).getBoundingClientRect().bottom));
    check(`[${name}] Q4 되돌리기·포기 버튼이 첫 화면 안`, rects.every((y) => y <= vh), rects.map((y) => Math.round(y)).join(', ') + ` / ${vh}`);
    const sw = await pg.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    check(`[${name}] Q4 가로 넘침 없음 (문서 폭 ≤ 화면 폭)`, sw[0] <= sw[1], `${sw[0]} / ${sw[1]}`);
    await shot(pg, `q_daily_start_${name}.png`);
    await pg.close();

    // Q3 완료 화면: 되돌리기 횟수, 범례, Q4 전체 경로 범위, 도착 라벨 잘림
    pg = await dailyPage(ctx, '#d=2026-11-06', errors, name);
    const opt = await optimal(pg);
    const first = await pg.$$eval('#pz-moves button', (bs) => bs.map((x) => Number(x.dataset.to)));
    const wrong = first.find((t) => t !== opt[1]);
    await pg.click(`#pz-moves button[data-to="${wrong}"]`);
    await pg.click('#pz-undo');
    for (const c of opt.slice(1)) await pg.click(`#pz-moves button[data-to="${c}"]`);
    await pg.waitForSelector('#pz-result:not([hidden])');
    await pg.waitForTimeout(800);
    const share = await pg.textContent('#pz-share');
    check(`[${name}] Q3 공유 문구에 되돌리기 횟수`, share.includes('되돌리기 1회'), share.replace(/\n/g, ' | '));
    check(`[${name}] Q3 완료 화면 범례`, await pg.isVisible('#pz-legend'));
    const inView = await pg.evaluate((path) => {
      const { map, data } = window.__daily;
      const bd = map.getBounds();
      return path.filter((c) => !bd.contains([data.clusters[c].la, data.clusters[c].lo])).length;
    }, opt);
    check(`[${name}] Q4 완료 상태에서 최적 경로 전체가 지도 안`, inView === 0, `밖 ${inView}개 / ${opt.length}`);
    // 새로 고침(저장 상태) 후에도
    await pg.reload();
    await pg.waitForFunction(() => window.__daily && window.__daily.game.done);
    await pg.waitForTimeout(800);
    const inView2 = await pg.evaluate((path) => {
      const { map, data } = window.__daily;
      const bd = map.getBounds();
      return path.filter((c) => !bd.contains([data.clusters[c].la, data.clusters[c].lo])).length;
    }, opt);
    check(`[${name}] Q4 저장된 완료 상태를 다시 열어도 전체 경로가 지도 안`, inView2 === 0, `밖 ${inView2}개`);
    const clip = await pg.evaluate(() => {
      const m = document.querySelector('#map').getBoundingClientRect();
      return [...document.querySelectorAll('.leaflet-tooltip-pane .leaflet-tooltip')].map((t) => {
        const r = t.getBoundingClientRect();
        return { t: t.textContent, ok: r.left >= m.left - 1 && r.right <= m.right + 1 && r.top >= m.top - 1 && r.bottom <= m.bottom + 1 };
      });
    });
    check(`[${name}] Q4 도착역 라벨이 지도 밖으로 안 잘림`, clip.length > 0 && clip.every((x) => x.ok), clip.map((x) => `${x.t}:${x.ok ? 'ok' : '잘림'}`).join(', '));
    await shot(pg, `q_daily_done_${name}.png`, name === 'mobile');
    await pg.close();

    // ---- 메인 ----
    pg = await ctx.newPage();
    pg.on('pageerror', (e) => errors.push(`${name} index pageerror ${e.message}`));
    pg.on('console', (m) => { if (m.type() === 'error' && !/tile\.openstreetmap|ERR_|Failed to load resource/.test(m.text())) errors.push(`${name} index console ${m.text()}`); });
    await pg.goto(`${BASE}/index.html`);
    await pg.waitForFunction(() => window.__app && window.__app.data);
    if (name === 'desktop') {
      for (const f of ['favicon.svg', 'favicon.ico']) {
        const r = await pg.request.get(`${BASE}/${f}`);
        check(`Q5 ${f} 200`, r.status() === 200, String(r.status()));
      }
      const icon = await pg.$eval('link[rel=icon]', (l) => l.getAttribute('href'));
      check('Q5 <link rel="icon">', icon === 'favicon.svg');
      // 낮은 줌에서 일반 역 마커 숨김
      const z7 = await pg.evaluate(() => [window.__app.map.getZoom(), window.__app.map.hasLayer(window.__app.plainStationLayer)]);
      await pg.evaluate(() => { window.__app.map.setView([37.55, 126.98], 12); });
      await pg.waitForTimeout(300);
      const z12 = await pg.evaluate(() => [window.__app.map.getZoom(), window.__app.map.hasLayer(window.__app.plainStationLayer)]);
      check('Q5 낮은 줌(7)에서 일반 역 숨김, 줌 12에서 표시', z7[1] === false && z12[1] === true, `z${z7[0]}:${z7[1]} z${z12[0]}:${z12[1]}`);
      // 아크 클릭 팝업: 부산 동래 아크 중간 지점 클릭
      await pg.evaluate(() => { window.__app.map.setView([35.205, 129.083], 14); });
      await pg.waitForTimeout(400);
      const pt = await pg.evaluate(() => {
        const { map, warpLayer } = window.__app;
        let target = null;
        warpLayer.eachLayer((l) => { if (!target && l.getTooltip() && /\[동래\]/.test(l.getTooltip().getContent())) target = l; });
        const ll = target.getLatLngs(); const mid = ll[Math.floor(ll.length / 2)];
        const p = map.latLngToContainerPoint(mid); const r = document.querySelector('#map').getBoundingClientRect();
        return { x: r.left + p.x, y: r.top + p.y, w: target.options.weight };
      });
      await pg.mouse.click(pt.x, pt.y);
      await pg.waitForTimeout(400);
      const popup = await pg.$('.leaflet-popup-content .arc-pop');
      const ptxt = popup ? (await popup.textContent()).replace(/\s+/g, ' ') : '';
      check('Q5 아크 클릭(탭)으로 정보 팝업, 짧은 동래 아크는 굵게', !!popup && ptxt.includes('동래') && pt.w >= 3, `굵기 ${pt.w} · ${ptxt.slice(0, 80)}`);
      await shot(pg, 'q_index_arc_popup_desktop.png');
      // 서울–부산 아크 곡률 분산
      const bends = await pg.evaluate(async () => {
        const W = await import('./world.js');
        const { data } = window.__app;
        const m = W.arcBends(data, (ci) => [data.clusters[ci].la, data.clusters[ci].lo], (a, b) => window.L.latLng(a).distanceTo(b));
        const out = [];
        for (const p of data.portals) p.c.forEach((ci, i) => p.c.forEach((cj, j) => {
          if (i < j && [data.clusters[ci].city, data.clusters[cj].city].sort().join('–') === '부산–수도권') out.push(m.get(`${p.id}|${i}|${j}`).bend);
        }));
        return out;
      });
      check('Q5 수도권–부산 아크 곡률이 서로 다르다', bends.length >= 2 && new Set(bends.map((x) => x.toFixed(3))).size === bends.length, bends.map((x) => x.toFixed(2)).join(', '));
      await pg.evaluate(() => { window.__app.map.setView([36.0, 128.2], 8); });
      await pg.waitForTimeout(400);
      await shot(pg, 'q_index_arcs_z8_desktop.png');
    }
    // 길찾기: 목동 → 부산 동래 (동명역 병기, '역' 접미사, 모바일 결과 위치)
    await pg.fill('#from', '목동');
    await pg.fill('#to', '부산 동래');
    await pg.click('#route-form button[type=submit]');
    await pg.waitForSelector('#result .summary');
    await pg.waitForTimeout(900);
    const steps = (await pg.textContent('#result .steps')).replace(/\s+/g, ' ');
    check(`[${name}] Q5 같은 이름 역 워프에 노선 병기`, /양평 \(5호선\) ⇢ 수도권 양평 \(경의·중앙선\)/.test(steps), steps.match(/워프 T1 \[양평\][^⇢]*⇢[^)]*\)/)?.[0] || steps.slice(0, 120));
    check(`[${name}] Q5 '역' 접미사 통일 (양평역·용문역 표기 없음)`, !/양평역|용문역/.test(steps));
    if (name === 'mobile') {
      const r = await pg.evaluate(() => ({ res: document.querySelector('#result').getBoundingClientRect().top, map: document.querySelector('#map').getBoundingClientRect() }));
      check('[mobile] Q4 길찾기 후 결과가 첫 화면에 보이고 지도도 함께 보인다', r.res < vh * 0.8 && r.map.top <= 1 && r.map.bottom > 150,
        `결과 top ${Math.round(r.res)}px, 지도 ${Math.round(r.map.top)}~${Math.round(r.map.bottom)}px / ${vh}`);
    }
    const sw2 = await pg.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    check(`[${name}] Q4 메인 가로 넘침 없음`, sw2[0] <= sw2[1], `${sw2[0]} / ${sw2[1]}`);
    await shot(pg, `q_index_route_${name}.png`);
    // Q6-5 해외 경유 표시 (tw_t12: 판교 → 중화가 타이베이를 거친다)
    await pg.selectOption('#ruleset-select', 'tw_t12');
    await pg.waitForFunction(() => window.__app.data.meta.ruleset === 'tw_t12');
    await pg.fill('#from', '판교');
    await pg.fill('#to', '중화');
    await pg.click('#route-form button[type=submit]');
    await pg.waitForSelector('#result .summary');
    const sum = (await pg.textContent('#result .summary')).replace(/\s+/g, ' ');
    const ab = await pg.$$eval('#result .steps .abroad', (xs) => xs.map((x) => x.textContent));
    check(`[${name}] Q6-5 국가 간 ruleset 경로에 해외 경유 구간 표시`, sum.includes('해외 경유') && ab.length >= 1, `${sum} · ${ab.join(', ')}`);
    if (name === 'desktop') await shot(pg, 'q_index_abroad_desktop.png');
    const def = await pg.evaluate(async () => (await import('./world.js')).RULESETS[0].key);
    check(`[${name}] Q6-5 길찾기 기본 ruleset = 한국 T1 (strict)`, def === 'strict');
    await ctx.close();
  }
  check('콘솔 에러 0건 (타일 로드 실패 제외)', errors.length === 0, JSON.stringify(errors));
  const nf = checks.filter((c) => !c.ok).length;
  say(`\n요약: ${checks.length - nf}/${checks.length} 통과`);
  fs.writeFileSync(`${OUT}/q_browser.txt`, log.join('\n') + '\n');
  await b.close();
  process.exit(nf ? 1 : 0);
})();
