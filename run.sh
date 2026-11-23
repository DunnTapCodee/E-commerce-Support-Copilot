#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON="python3.11"
else
  PYTHON="python3"
fi

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Không tìm thấy $PYTHON. Cài Python 3.11 hoặc đặt PYTHON_BIN=/path/to/python3." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Tạo môi trường ảo .venv bằng $PYTHON ..."
  "$PYTHON" -m venv .venv
fi

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
PIP_ARGS=(
  -r requirements.txt
  -r services/gateway/requirements.txt
  -r services/intent_service/requirements.txt
  -r services/rag_service/requirements.txt
  -r services/telemetry_service/requirements.txt
  -r services/ui_service/requirements.txt
)

PIP_TIMEOUT="${PIP_TIMEOUT:-120}"
PIP_RETRIES="${PIP_RETRIES:-5}"
echo "Cài/cập nhật dependencies (timeout ${PIP_TIMEOUT}s, tối đa ${PIP_RETRIES} lần thử) ..."
"$VENV_PYTHON" -m pip install \
  --disable-pip-version-check \
  --prefer-binary \
  --timeout "$PIP_TIMEOUT" \
  --retries "$PIP_RETRIES" \
  "${PIP_ARGS[@]}"

if [[ ! -f artifacts/models/intent/router/meta.json || ! -f artifacts/models/intent/vi/meta.json || ! -f artifacts/models/intent/en/meta.json ]]; then
  echo "CẢNH BÁO: Chưa có model NLU đã huấn luyện. intent_service sẽ báo degraded; xem services/intent_service/README_MODULE1.md."
fi

echo "Khởi động Copilot. Mở http://127.0.0.1:8501 — nhấn Ctrl+C để dừng."
exec "$VENV_PYTHON" run_dev.py
