# web/ — 정적 MVP

- `index.html`, `app.js`, `style.css`: 지도(Leaflet) 위 역·노선·워프 아크, 출발·도착 선택 시 경로 표시
- `route.js`: 길찾기 로직 (브라우저·node 공용). `npm test`로 Python 결과와 대조
- `daily.html` + `daily.js` + `puzzle.js`: 데일리 퍼즐. 서울 시간 날짜로 `data/puzzles.json`의 `daily_order`를 순환해 퍼즐을 고른다.
  한 수 = 인접역 승차 1개 또는 워프 1번(환승은 공짜). 점수 = 최적 비용 / 내 비용 × 100, 결과는 🚇/🌀 이모지로 복사.
  진행 상황은 localStorage에 날짜별로 저장(막혀 있으면 생략). 다른 날 퍼즐: `daily.html#d=YYYY-MM-DD`
- `data/puzzles.json`: `python3 pipeline/10_build_game_data.py`로 생성 (퍼즐 후보·데일리 순서)
- 브라우저 E2E: `scripts/e2e_daily.cjs` (Playwright, 로컬 서버 필요)
- `data/kr_strict.json`: `python3 pipeline/06_build_web_data.py`로 생성
- `vendor/leaflet/`: Leaflet 1.9.4 (BSD-2-Clause, npm registry tarball)

로컬 실행: `cd web && python3 -m http.server 8000` → http://localhost:8000

URL 해시로 경로 공유: `#from=강남&to=부산 동래&warp=1`
