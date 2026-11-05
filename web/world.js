// Phase 1 웹 설정 (브라우저·node 공용 ES 모듈): ruleset 번들 목록, 국가 표기, 워프 아크 스타일.
// 번들은 pipeline/06_build_web_data.py가 만든다 (한국만 = kr_<rs>.json, 한국+타이베이 = world_<rs>.json).

export const RULESETS = [
  { key: "strict", file: "kr_strict.json", label: "한국만 · T1", note: "" },
  { key: "tw_t1", file: "world_tw_t1.json", label: "한국+타이베이 · T1", note: "공식명만" },
  { key: "tw_t12", file: "world_tw_t12.json", label: "한국+타이베이 · T1+T2", note: "공식명만" },
  { key: "tw_t123", file: "world_tw_t123.json", label: "한국+타이베이 · T1+T2+T3", note: "공식명만" },
  { key: "tw_t12_label", file: "world_tw_t12_label.json", label: "참고 · T1+T2 (타이베이 위키데이터 라벨)", note: "공식명 아님" },
  { key: "tw_t123_label", file: "world_tw_t123_label.json", label: "참고 · T1+T2+T3 (타이베이 위키데이터 라벨)", note: "공식명 아님" },
];

export const COUNTRY_KO = { KR: "한국", TW: "대만" };

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
  const dash = { T1: "4 6", T2: "2 4", T3: "1 5" }[portal.tier] || "4 6";
  return { color: warpColor, weight: 1.6, opacity: 0.55, dashArray: dash };
}

export function tierLabel(tier) {
  return { T1: "T1 같은 이름", T2: "T2 한자 이체자", T3: "T3 영문명" }[tier] || tier;
}
