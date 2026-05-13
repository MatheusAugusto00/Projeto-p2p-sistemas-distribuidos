#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
START_DELAY="${SPRINT3_START_DELAY:-1}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Este script abre janelas no app Terminal do macOS."
  echo "Execute manualmente os comandos abaixo em 5 terminais:"
  echo
  echo "1) MASTER_UUID=Master_A MASTER_HOST=127.0.0.1 MASTER_PORT=8000 INITIAL_TASK_COUNT=50 CAPACITY=5 RELEASE_THRESHOLD=2 PEER_MASTERS=Master_B@127.0.0.1:8001 ${PYTHON_BIN} server.py"
  echo "2) MASTER_UUID=Master_B MASTER_HOST=127.0.0.1 MASTER_PORT=8001 INITIAL_TASK_COUNT=0 CAPACITY=100 RELEASE_THRESHOLD=60 PEER_MASTERS=Master_A@127.0.0.1:8000 ${PYTHON_BIN} server.py"
  echo "3) WORKER_ID=B1 MASTER_HOST=127.0.0.1 MASTER_PORT=8001 RECONNECT_DELAY=2 ${PYTHON_BIN} client.py"
  echo "4) WORKER_ID=B2 MASTER_HOST=127.0.0.1 MASTER_PORT=8001 RECONNECT_DELAY=2 ${PYTHON_BIN} client.py"
  echo "5) WORKER_ID=A1 MASTER_HOST=127.0.0.1 MASTER_PORT=8000 RECONNECT_DELAY=2 ${PYTHON_BIN} client.py"
  exit 1
fi

open_terminal() {
  local title="$1"
  local command="$2"

  /usr/bin/osascript - "$PROJECT_DIR" "$title" "$command" <<'APPLESCRIPT'
on run argv
  set projectDir to item 1 of argv
  set titleText to item 2 of argv
  set commandText to item 3 of argv

  tell application "Terminal"
    activate
    do script "cd " & quoted form of projectDir & " && printf '\\033]0;" & titleText & "\\007' && " & commandText
  end tell
end run
APPLESCRIPT
}

echo "Abrindo 5 terminais para testar a Sprint 3..."

open_terminal "Sprint3 Master A" "MASTER_UUID=Master_A MASTER_HOST=127.0.0.1 MASTER_PORT=8000 INITIAL_TASK_COUNT=50 CAPACITY=5 RELEASE_THRESHOLD=2 PEER_MASTERS=Master_B@127.0.0.1:8001 ${PYTHON_BIN} server.py"
sleep "$START_DELAY"

open_terminal "Sprint3 Master B" "MASTER_UUID=Master_B MASTER_HOST=127.0.0.1 MASTER_PORT=8001 INITIAL_TASK_COUNT=0 CAPACITY=100 RELEASE_THRESHOLD=60 PEER_MASTERS=Master_A@127.0.0.1:8000 ${PYTHON_BIN} server.py"
sleep "$START_DELAY"

open_terminal "Sprint3 Worker B1" "WORKER_ID=B1 MASTER_HOST=127.0.0.1 MASTER_PORT=8001 RECONNECT_DELAY=2 ${PYTHON_BIN} client.py"
sleep "$START_DELAY"

open_terminal "Sprint3 Worker B2" "WORKER_ID=B2 MASTER_HOST=127.0.0.1 MASTER_PORT=8001 RECONNECT_DELAY=2 ${PYTHON_BIN} client.py"
sleep "$START_DELAY"

open_terminal "Sprint3 Worker A1" "WORKER_ID=A1 MASTER_HOST=127.0.0.1 MASTER_PORT=8000 RECONNECT_DELAY=2 ${PYTHON_BIN} client.py"

echo "Terminais abertos."
echo "Para parar a demo, use Ctrl+C em cada terminal aberto."
