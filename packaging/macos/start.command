#!/bin/bash
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
RESOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DATA="$HOME/Library/Application Support/AI Dev Director"
mkdir -p "$APP_DATA"
fail() { printf '\n%s\n' "$1"; read -r -p '엔터를 누르면 종료합니다.' ignored; exit 1; }
printf '\nAI DEV DIRECTOR · macOS Preview\n최초 실행 시 Python 의존성을 다운로드합니다.\n'
DIRECTOR_PYTHON=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3,9)' >/dev/null 2>&1; then
        DIRECTOR_PYTHON="$candidate"; break
    fi
done
[ -n "$DIRECTOR_PYTHON" ] || fail 'Python 3.9 이상이 필요합니다. https://www.python.org/downloads/macos/ 에서 설치한 뒤 다시 실행하세요.'
command -v git >/dev/null 2>&1 && git --version >/dev/null 2>&1 || fail 'Git이 필요합니다. 터미널에서 xcode-select --install 실행 후 다시 시작하세요.'
exec "$DIRECTOR_PYTHON" "$RESOURCE_DIR/mac_bootstrap.py" "$RESOURCE_DIR" "$APP_DATA"
