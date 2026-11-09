// 5차 R4: 도식 라벨 품질을 실제 브라우저 글꼴로 잰다 (DOM 기준, 버전 무관).
// 라벨 = .sch-stations text의 getBBox() 네 모서리를 getCTM으로 SVG 좌표로 옮긴 사각형(회전 포함),
// 선분 = .sch-edges line. 지표: 노선 선분이 라벨 안을 2px(화면) 넘게 지나는 라벨 수, 서로 겹치는 라벨 쌍(외접 사각형 0.5px 초과).
// 사용: node scripts/e2e_labels_dom.cjs <base URL> <이름> [출력 폴더]   (예: http://localhost:8766 4차)
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const [base, tag, out = '.'] = process.argv.slice(2);
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  const pg = await ctx.newPage();
  await pg.goto(`${base}/schematic.html`);
  await pg.waitForSelector('#sch-svg circle');
  await pg.waitForTimeout(800);
  const res = {};
  for (const r of ['seoul', 'busan', 'daegu']) {
    await pg.click(`#sch-tabs button[data-r="${r}"]`);
    await pg.waitForTimeout(700);
    res[r] = await pg.evaluate(() => {
      const svg = document.getElementById('sch-svg');
      const k = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;   // SVG 단위 → 화면 px
      const segs = [...svg.querySelectorAll('.sch-edges line')].map((l) => ['x1', 'y1', 'x2', 'y2'].map((a) => +l.getAttribute(a)));
      const labs = [...svg.querySelectorAll('.sch-stations text')].filter((t) => !t.classList.contains('sch-icon') && t.textContent.trim());
      const rects = labs.map((t) => {
        const bb = t.getBBox(), m = t.getCTM(), sm = svg.getCTM().inverse();
        const M = sm.multiply(m);
        const P = (x, y) => [M.a * x + M.c * y + M.e, M.b * x + M.d * y + M.f];
        return [P(bb.x, bb.y), P(bb.x + bb.width, bb.y), P(bb.x + bb.width, bb.y + bb.height), P(bb.x, bb.y + bb.height)];
      });
      // 선분이 볼록 사각형 안을 지나는 길이 (Cyrus–Beck)
      const inside = (q, s) => {
        let t0 = 0, t1 = 1;
        const d = [s[2] - s[0], s[3] - s[1]];
        for (let i = 0; i < 4; i++) {
          const a = q[i], c = q[(i + 1) % 4];
          // 사각형 안쪽 법선 (꼭짓점 순서와 무관하게 중심 쪽)
          let n = [-(c[1] - a[1]), c[0] - a[0]];
          const cx = (q[0][0] + q[2][0]) / 2, cy = (q[0][1] + q[2][1]) / 2;
          if (n[0] * (cx - a[0]) + n[1] * (cy - a[1]) < 0) n = [-n[0], -n[1]];
          const num = n[0] * (s[0] - a[0]) + n[1] * (s[1] - a[1]);
          const den = n[0] * d[0] + n[1] * d[1];
          if (Math.abs(den) < 1e-12) { if (num < 0) return 0; continue; }
          const t = -num / den;
          if (den > 0) t0 = Math.max(t0, t); else t1 = Math.min(t1, t);
          if (t0 > t1) return 0;
        }
        return (t1 - t0) * Math.hypot(d[0], d[1]);
      };
      let onLine = 0;
      for (const q of rects) if (segs.some((s) => inside(q, s) * k > 2)) onLine++;
      const box = rects.map((q) => [Math.min(...q.map((p) => p[0])), Math.min(...q.map((p) => p[1])), Math.max(...q.map((p) => p[0])), Math.max(...q.map((p) => p[1]))]);
      let pairs = 0;
      for (let i = 0; i < box.length; i++) for (let j = i + 1; j < box.length; j++) {
        const a = box[i], c = box[j];
        if ((Math.min(a[2], c[2]) - Math.max(a[0], c[0])) * k > 0.5 && (Math.min(a[3], c[3]) - Math.max(a[1], c[1])) * k > 0.5) pairs++;
      }
      return { labels: labs.length, on_line: onLine, overlap_pairs: pairs };
    });
    if (r === 'seoul') await pg.screenshot({ path: `${out}/r4_labels_dom_${tag}.png` });
  }
  console.log(JSON.stringify({ tag, ...res }));
  await b.close();
})();
