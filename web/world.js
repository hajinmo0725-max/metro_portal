// Phase 1 웹 설정 (브라우저·node 공용 ES 모듈): ruleset 번들 목록, 국가 표기, 워프 아크 스타일.
// 번들은 pipeline/06_build_web_data.py가 만든다 (한국만 = kr_<rs>.json, 한국+타이베이(+도쿄) = world_<rs>.json).

export const RULESETS = [
  { key: "strict", file: "kr_strict.json", label: "한국만 · T1 (기본)", note: "" },
  { key: "tw_t1", file: "world_tw_t1.json", label: "한국+타이베이 · T1", note: "현지어 라벨 포함" },
  { key: "tw_t12", file: "world_tw_t12.json", label: "한국+타이베이 · T1+T2", note: "현지어 라벨 포함" },
  { key: "tw_t123", file: "world_tw_t123.json", label: "한국+타이베이 · T1+T2+T3a", note: "현지어 라벨 포함" },
  { key: "tw_t12_official", file: "world_tw_t12_official.json", label: "참고 · T1+T2 공식명만", note: "공식명만" },
  { key: "tw_t123b", file: "world_tw_t123b.json", label: "참고 · T1+T2+T3a+T3b (로마자 우연 일치)", note: "T3b 포함" },
  // 5차 T3: Phase 1b 한국+타이베이+도쿄 (기존 규칙 + 일본어 라벨, config/rulesets/ktj_*.yaml)
  { key: "ktj_t1", file: "world_ktj_t1.json", label: "한국+타이베이+도쿄 · T1", note: "현지어 라벨 포함" },
  { key: "ktj_t12", file: "world_ktj_t12.json", label: "한국+타이베이+도쿄 · T1+T2", note: "현지어 라벨 포함" },
  { key: "ktj_t123", file: "world_ktj_t123.json", label: "한국+타이베이+도쿄 · T1+T2+T3a", note: "현지어 라벨 포함" },
];

export const COUNTRY_KO = { KR: "한국", TW: "대만", JP: "일본" };

export function rulesetByKey(key) {
  return RULESETS.find((r) => r.key === key) || RULESETS[0];
}

// 클러스터의 나라 (단일 국가 번들은 co가 없어서 KR)
export function clusterCountry(c) {
  return c.co || "KR";
}

// 워프 아크 스타일: 국가 간 포탈은 굵은 주황 실선, 같은 나라는 기존 보라 점선. T2·T3는 점선 간격으로 구분
export const CROSS_COLOR = "#ff6a00";
export function warpStyle(portal, warpColor) {
  if (portal.x) return { color: CROSS_COLOR, weight: 2.6, opacity: 0.85, dashArray: portal.tier === "T1" ? null : "10 4" };
  const dash = { T1: "4 6", T2: "2 4", T3a: "1 5", T3b: "1 8" }[portal.tier] || "4 6";
  return { color: warpColor, weight: 1.6, opacity: 0.55, dashArray: dash };
}

export function tierLabel(tier) {
  return { T1: "T1 같은 이름", T2: "T2 한자 이체자", T3a: "T3a 영어 번역명", T3b: "T3b 로마자 우연 일치" }[tier] || tier;
}

// 4차 Q6-1: 포탈 신뢰도 (이름 출처 등급 중 가장 낮은 것). high = 공식명, medium = 현지어 라벨, low = 외국어 라벨
export function confidenceLabel(conf) {
  return { high: "공식명", medium: "현지어 라벨(준공식)", low: "외국어 라벨(신뢰도 낮음)" }[conf] || "";
}

// 4차 Q5: 워프 아크 곡률. 같은 도시 쌍(예: 수도권–부산)을 잇는 아크가 여러 개면 곡률을 번갈아(좌우) 키워 겹치지 않게 하고,
// 짧은 아크(shortKm 미만, 예: 부산 동래 1.4km)는 short = true로 표시해서 굵게 그린다.
// key = `${portal.id}|${i}|${j}` (p.c의 인덱스 i < j). 반환 Map(key → {bend, short})
export function arcBends(data, ll, distM, { base = 0.16, step = 0.09, shortKm = 5, shortBend = 0.5 } = {}) {
  const groups = new Map();
  for (const p of data.portals) {
    for (let i = 0; i < p.c.length; i++) for (let j = i + 1; j < p.c.length; j++) {
      const a = data.clusters[p.c[i]], b = data.clusters[p.c[j]];
      const g = [a.city, b.city].sort().join("–");
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push({ key: `${p.id}|${i}|${j}`, d: distM(ll(p.c[i]), ll(p.c[j])), cross: !!p.x });
    }
  }
  const out = new Map();
  for (const [, arcs] of [...groups.entries()].sort()) {
    arcs.sort((x, y) => (x.key < y.key ? -1 : 1));
    arcs.forEach((x, k) => {
      const short = x.d < shortKm * 1000;
      const sign = k % 2 === 0 ? 1 : -1;
      const bend = short ? shortBend * sign : (x.cross ? 0.18 : base + step * Math.floor(k / 2)) * sign;
      out.set(x.key, { bend, short });
    });
  }
  return out;
}
