#!/usr/bin/env bash
# SessionStart hook: Claude Code 클라우드 세션에서만 의존성 설치.
# 로컬 세션에서는 아무것도 하지 않는다.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"

python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
echo "[install_pkgs] python deps installed"
