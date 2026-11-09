"""환승 클러스터, 포탈, 라우팅 그래프 (DESIGN 4·5장). 룰 값은 전부 ruleset에서 받는다."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .geo import haversine_m
from .normalize import normalize_name, parenthetical_aliases, script_ok


class UnionFind:
    def __init__(self, items):
        self.p = {x: x for x in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # 결정성: 사전순 작은 쪽을 대표로
            if rb < ra:
                ra, rb = rb, ra
            self.p[rb] = ra


def tier_normalize(tier_cfg: dict, norm: dict) -> dict:
    """등급별 정규화: 공통 normalize 위에 tier의 normalize를 덮어쓴다 (T2 '站' 접미사, T3 대소문자 접기 등)."""
    if not tier_cfg.get("normalize"):
        return norm
    from .ruleset import deep_merge
    return deep_merge(norm, tier_cfg["normalize"])


_WORD = re.compile(r"[a-z0-9']+")


def english_type(key: str, tier_cfg: dict) -> str:
    """4차 Q6-6: 정규화된 영어명 키가 번역형(translation, 예: city hall)인지 로마자형(romanization, 예: seongnam)인지.
    ruleset의 translation_words에 든 영단어가 하나라도 있으면 번역형."""
    words = set(tier_cfg.get("translation_words") or [])
    return "translation" if any(w in words for w in _WORD.findall(key.casefold())) else "romanization"


def station_match_names(st: dict, tier_cfg: dict, norm: dict, folder=None, with_text: bool = False, detail: bool = False):
    """포탈 매칭에 쓰는 정규화 이름 집합 (ruleset의 언어·문자·종류·출처 등급·현지어·official·출처 조건).
    folder: T2 이체자 접기 (variants.VariantFolder). with_text면 {키: 원문 집합},
    detail이면 {키: {"texts": 원문 집합, "grades": 출처 등급 집합}}을 돌려준다."""
    from .names import grade_of, is_native
    out: dict[str, dict] = {}
    tnorm = tier_normalize(tier_cfg, norm)
    ignore = set(tnorm.get("ignore_texts") or [])
    country = st.get("country", "KR")
    for n in st.get("names", []):
        if n["lang"] not in tier_cfg["langs"]:
            continue
        if tier_cfg.get("scripts") and n["script"] not in tier_cfg["scripts"]:
            continue
        if tier_cfg.get("kinds") and n.get("kind", "primary") not in tier_cfg["kinds"]:
            continue
        if tier_cfg.get("official_only") and not n.get("official"):
            continue
        if tier_cfg.get("sources") and n.get("source") not in tier_cfg["sources"]:
            continue
        g = grade_of(n, country)
        # 4차 Q6-1: 출처 등급 허용 목록, 현지어 이름만 (한국 역의 중국어 번역명 등 제외)
        if tier_cfg.get("grades") and g not in tier_cfg["grades"]:
            continue
        if tier_cfg.get("native_only") and not is_native(n, country):
            continue
        if n["text"].strip() in ignore:
            continue
        k = normalize_name(n["text"], tnorm)
        # 5차 T2: script_check_as — 이름의 문자 체계를 다른 체계로 검사 (일본어 Jpan 이름을 T2에서는 한자만(Hani)인지 본다: 가나 섞인 이름 제외)
        chk = (tier_cfg.get("script_check_as") or {}).get(n["script"], n["script"])
        if tier_cfg.get("script_check") and not script_ok(k, chk):
            continue  # 표기 오류 (한자 칸의 한글 등)
        if folder is not None:
            k = folder.fold(k)
        if k and tier_cfg.get("en_type") and english_type(k, tier_cfg) != tier_cfg["en_type"]:
            continue  # T3a(번역형)·T3b(로마자형) 분리
        # 5차 T2: separate_langs — T1은 '같은 언어·같은 문자' 정의대로 언어마다 따로 맞춘다 (zh '板橋'와 ja '板橋'는 T1이 아니라 T2).
        # 첫 번째 언어는 키 그대로(기존 id 유지), 나머지 언어는 키 뒤에 '@언어'를 붙인다 (포탈 표시 이름은 '@' 앞)
        if k and tier_cfg.get("separate_langs") and n["lang"] != tier_cfg["langs"][0]:
            k = f"{k}@{n['lang']}"
        if k:
            d = out.setdefault(k, {"texts": set(), "grades": set()})
            d["texts"].add(n["text"])
            d["grades"].add(g)
    if detail:
        return out
    if with_text:
        return {k: v["texts"] for k, v in out.items()}
    return set(out)


def transfer_decision(a: dict, b: dict, d: float, ccfg: dict, official) -> tuple[bool, str]:
    """같은 이름(또는 별칭)인 두 역 레코드를 환승(같은 클러스터)으로 묶을지. (묶음 여부, 근거)
    transfer_rule = distance: 거리 D 이하면 묶는다 (2차까지의 규칙).
    transfer_rule = official_first (3차 A3): 공식 환승 정보 우선. yes면 묶고 (official_max_distance_m 이내),
      no면 거리와 무관하게 안 묶고, 정보가 없거나(unknown) 같은 노선 패밀리(same_line)면 거리 D로 판정."""
    D = ccfg["transfer_distance_m"]
    if ccfg.get("transfer_rule", "distance") == "distance" or official is None:
        return d <= D, "distance"
    rel = official.relation(a, b)
    if rel == "yes":
        return d <= ccfg.get("official_max_distance_m", float("inf")), "official_yes"
    if rel == "no":
        return False, "official_no"
    return d <= D, f"distance({rel})"


def build_clusters(stations: list[dict], rs: dict, official=None, audit: list | None = None) -> list[dict]:
    """정규화 이름이 같은 역을 환승 판정(transfer_decision)으로 묶는다. 옵션: 괄호 부역명·데이터 별칭도 같은 판정으로 묶는다.
    official: transfer.OfficialTransfers. ruleset이 official_first인데 None이면 역 데이터로 만든다.
    audit: 리스트를 주면 같은 이름 쌍마다 판정 근거를 넣어 준다 (보고서용)."""
    norm, ccfg = rs["normalize"], rs["cluster"]
    if official is None and ccfg.get("transfer_rule", "distance") == "official_first":
        from .transfer import OfficialTransfers
        official = OfficialTransfers(stations)
    # 4차 Q6-3: 역외 환승 수동 목록 (config/kr_offsite_transfers.yaml). 공식 정보가 '일반역'이어도 묶는다
    offsite = {}
    if ccfg.get("offsite_transfers"):
        from .transfer import load_offsite
        offsite = load_offsite(ccfg["offsite_transfers"])
    st = sorted(stations, key=lambda s: s["id"])
    key = {s["id"]: normalize_name(s["name_ko"], norm) for s in st}
    by_name = defaultdict(list)
    for s in st:
        by_name[key[s["id"]]].append(s)
    uf = UnionFind([s["id"] for s in st])
    reasons = []
    for name, group in sorted(by_name.items()):
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
                ok, why = transfer_decision(a, b, d, ccfg, official)
                if not ok and frozenset((a["id"], b["id"])) in offsite:
                    ok, why = d <= ccfg.get("official_max_distance_m", float("inf")), "offsite_manual"
                if ok:
                    uf.union(a["id"], b["id"])
                if audit is not None:
                    audit.append({"name": name, "a": a["id"], "b": b["id"], "distance_m": round(d, 1), "merged": ok, "basis": why})
    if ccfg.get("use_parenthetical_alias") or ccfg.get("use_data_aliases"):
        for a in st:
            als = []
            if ccfg.get("use_parenthetical_alias"):
                als += parenthetical_aliases(a["name_ko"], norm)
            if ccfg.get("use_data_aliases"):
                als += [normalize_name(x, norm) for x in a.get("aliases", [])]
            for alias in sorted(set(als)):
                for b in by_name.get(alias, []):
                    if b["id"] == a["id"]:
                        continue
                    d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
                    ok, why = transfer_decision(a, b, d, ccfg, official)
                    if audit is not None:
                        audit.append({"name": alias, "a": a["id"], "b": b["id"], "distance_m": round(d, 1), "merged": ok,
                                      "basis": why, "via_alias": True})
                    if ok:
                        uf.union(a["id"], b["id"])
                        reasons.append((a["id"], b["id"], alias, round(d, 1)))
    members = defaultdict(list)
    for s in st:
        members[uf.find(s["id"])].append(s)
    raw = []
    for mem in members.values():
        names = Counter(key[s["id"]] for s in mem)
        primary = sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        lat = sum(s["lat"] for s in mem) / len(mem)
        lon = sum(s["lon"] for s in mem) / len(mem)
        raw.append({"name": primary, "names": sorted(names), "station_ids": sorted(s["id"] for s in mem),
                    "lat": round(lat, 6), "lon": round(lon, 6),
                    "regions": sorted({s.get("region", "") for s in mem}),
                    "lines": sorted({s.get("line_group", "") for s in mem})})
    # 결정적 id: 대표 이름 + 같은 이름 클러스터 내 (위도, 경도) 순번
    raw.sort(key=lambda c: (c["name"], c["lat"], c["lon"]))
    cnt = Counter()
    for c in raw:
        cnt[c["name"]] += 1
        c["id"] = f"{c['name']}#{cnt[c['name']]}"
    alias_links = [{"a": a, "b": b, "alias": al, "distance_m": d} for a, b, al, d in reasons]
    for c in raw:
        c["alias_links"] = [x for x in alias_links if x["a"] in c["station_ids"]]
    return raw


def build_portals(stations: list[dict], clusters: list[dict], rs: dict) -> tuple[list[dict], list[dict]]:
    """이름 노드(포탈). 같은 매칭 이름을 가진 클러스터가 2개 이상이면 포탈 하나. (포탈, 상한 초과로 버린 것)"""
    norm = rs["normalize"]
    cap = rs["portals"].get("hub_degree_cap")
    cluster_of = {sid: c["id"] for c in clusters for sid in c["station_ids"]}
    portals, capped = [], []
    # 등급 키는 T로 시작하는 것만 (hub_degree_cap, dedupe_subsumed 같은 옵션 제외). 비용 순 → 이름 순
    tiers = sorted((k for k in rs["portals"] if k.startswith("T")), key=lambda k: (rs["portals"][k]["cost"], k))
    for tier in tiers:
        tcfg = rs["portals"][tier]
        if not tcfg.get("enabled"):
            continue
        folder = None
        if tcfg.get("variant_fold"):
            from .variants import folder_for
            folder = folder_for(tcfg["variant_fold"])
        from .names import confidence
        by_name = defaultdict(lambda: defaultdict(list))
        texts = defaultdict(set)
        grades = defaultdict(set)
        for s in sorted(stations, key=lambda s: s["id"]):
            for nm, dt in station_match_names(s, tcfg, norm, folder, detail=True).items():
                by_name[nm][cluster_of[s["id"]]].append(s["id"])
                texts[nm] |= dt["texts"]
                grades[nm] |= dt["grades"]
        for nm in sorted(by_name):
            cl = by_name[nm]
            if len(cl) < 2:
                continue
            p = {"id": f"P:{tier}:{nm}", "tier": tier, "name": nm.split("@")[0], "cost": tcfg["cost"],
                 "cluster_ids": sorted(cl), "station_ids": sorted(sid for v in cl.values() for sid in v),
                 "degree": len(cl), "texts": sorted(texts[nm]),
                 # 4차 Q6-1: 매칭에 쓰인 이름의 출처 등급과 그에 따른 신뢰도 (가장 낮은 등급 기준)
                 "grades": sorted(grades[nm]), "confidence": confidence(grades[nm])}
            if cap is not None and p["degree"] > cap:
                capped.append(p)
                continue
            # 더 싼(먼저 만든) 등급 포탈이 이미 같은 클러스터들을 다 잇고 있으면 중복 (예: T1 '시청'과 T3 'city hall')
            if rs["portals"].get("dedupe_subsumed") and any(
                    q["tier"] != tier and set(p["cluster_ids"]) <= set(q["cluster_ids"]) for q in portals):
                p["subsumed"] = True
                capped.append(p)
                continue
            portals.append(p)
    return portals, capped


def build_graph(stations: list[dict], ride_edges: list[dict], clusters: list[dict], portals: list[dict], rs: dict) -> dict:
    """방향 그래프 인접 리스트. 노드 = 역(노선별) + 포탈. 엣지 = (to, cost, kind, meta)."""
    c_ride, c_transfer = rs["costs"]["ride"], rs["costs"]["transfer"]
    adj: dict[str, list] = {s["id"]: [] for s in stations}
    for e in ride_edges:
        adj[e["a"]].append((e["b"], c_ride, "ride", e["line"]))
        if not e.get("directed"):  # 유향 엣지(단방향 운행 구간)는 a → b만
            adj[e["b"]].append((e["a"], c_ride, "ride", e["line"]))
    for c in clusters:
        ids = c["station_ids"]
        for a in ids:
            for b in ids:
                if a != b:
                    adj[a].append((b, c_transfer, "transfer", c["id"]))
    for p in portals:
        adj[p["id"]] = []
        for sid in p["station_ids"]:
            adj[sid].append((p["id"], p["cost"], "warp_in", p["tier"]))
            adj[p["id"]].append((sid, 0, "warp_out", p["tier"]))
    for k in adj:
        adj[k].sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return adj
