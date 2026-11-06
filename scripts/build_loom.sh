#!/usr/bin/env bash
# S2. LOOM(github.com/ad-freiburg/loom, GPL-3.0)을 받아 빌드한다. 외부 CLI로만 쓰고 레포에는 코드를 복사하지 않는다.
# 산출물: data/raw/tools/loom/build/{topo,loom,octi,transitmap} (data/raw는 gitignore)
# 사용: scripts/build_loom.sh   (이미 빌드돼 있으면 건너뛴다. --force로 다시 빌드)
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_URL="https://github.com/ad-freiburg/loom"
# 재현성을 위해 커밋을 고정한다 (2026-11-06 세션에서 확인한 master HEAD)
COMMIT="1e4757838104d1e4d22186c9b77d5fc4b98681a0"
DEST="data/raw/tools/loom"
BIN="$DEST/build"

if [ "${1:-}" != "--force" ] && [ -x "$BIN/transitmap" ] && [ -x "$BIN/octi" ]; then
  echo "[loom] already built: $BIN"
  exit 0
fi

mkdir -p "$(dirname "$DEST")"
if [ ! -d "$DEST/.git" ]; then
  git clone --quiet "$REPO_URL" "$DEST"
fi
git -C "$DEST" fetch --quiet origin
git -C "$DEST" checkout --quiet "$COMMIT"
git -C "$DEST" submodule update --init --recursive --quiet

mkdir -p "$BIN"
( cd "$BIN" && cmake .. -DCMAKE_BUILD_TYPE=Release > cmake.log 2>&1 && make -j"$(nproc)" > make.log 2>&1 )
ls -la "$BIN"/{topo,loom,octi,transitmap,gtfs2graph} 2>/dev/null || true
echo "[loom] built at $(git -C "$DEST" rev-parse HEAD)"
