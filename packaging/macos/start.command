#!/bin/bash
set -uo pipefail
RESOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DATA="$HOME/Library/Application Support/AI Dev Director"
BACKGROUND=""
[ "${1:-}" = "--background" ] && BACKGROUND=1
mkdir -p "$APP_DATA"
# Apps opened from Finder get a bare PATH. Borrow the login shell's PATH so CLIs installed via npm, Homebrew or
# ~/.local/bin (claude, codex, agy, grok) are found exactly as in Terminal. Bounded so a slow profile cannot hang.
LOGIN_PATH="$( ( "${SHELL:-/bin/zsh}" -ilc 'printf "__PATH__%s" "$PATH"' 2>/dev/null & pid=$!; ( sleep 8; kill $pid 2>/dev/null ) & wait $pid ) | sed -n 's/.*__PATH__//p' | tail -1)"
export PATH="${LOGIN_PATH:+$LOGIN_PATH:}$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
fail() {
    if [ -n "${AI_DEV_DIRECTOR_APP:-}" ]; then
        # 0.4.1: started by the app window, which shows the failure itself. No second dialog.
        printf '\n%s\n' "$1"
    elif [ -n "$BACKGROUND" ]; then
        /usr/bin/osascript -e 'on run argv' -e 'display dialog (item 1 of argv) with title "AI DEV DIRECTOR" buttons {"확인"} default button 1 with icon caution' -e 'end run' "$1" >/dev/null 2>&1
    else
        printf '\n%s\n' "$1"; read -r -p '엔터를 누르면 종료합니다.' ignored
    fi
    exit 1
}
printf '\nAI DEV DIRECTOR · macOS Preview\n최초 실행 시 Python 의존성을 다운로드합니다.\n'
DIRECTOR_PYTHON=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3,9)' >/dev/null 2>&1; then
        DIRECTOR_PYTHON="$candidate"; break
    fi
done
[ -n "$DIRECTOR_PYTHON" ] || fail 'Python 3.9 이상이 필요합니다. https://www.python.org/downloads/macos/ 에서 설치한 뒤 다시 실행하세요.'
command -v git >/dev/null 2>&1 && git --version >/dev/null 2>&1 || fail 'Git이 필요합니다. 터미널에서 xcode-select --install 실행 후 다시 시작하세요.'
"$DIRECTOR_PYTHON" "$RESOURCE_DIR/mac_bootstrap.py" "$RESOURCE_DIR" "$APP_DATA"
code=$?
[ $code -eq 0 ] || fail "실행에 실패했습니다. 기록: $APP_DATA/launcher.log"
exit 0
