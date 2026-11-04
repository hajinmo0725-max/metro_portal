# web/ — 정적 MVP

- `index.html`, `app.js`, `style.css`: 지도(Leaflet) 위 역·노선·워프 아크, 출발·도착 선택 시 경로 표시
- `route.js`: 길찾기 로직 (브라우저·node 공용). `npm test`로 Python 결과와 대조
- `data/kr_strict.json`: `python3 pipeline/06_build_web_data.py`로 생성
- `vendor/leaflet/`: Leaflet 1.9.4 (BSD-2-Clause, npm registry tarball)

로컬 실행: `cd web && python3 -m http.server 8000` → http://localhost:8000

URL 해시로 경로 공유: `#from=강남&to=부산 동래&warp=1`
