#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "==================================================="
echo "  E-commerce Support Copilot - Quick Start"
echo "==================================================="

if [[ ! -f .env ]]; then
    echo "[.env] File .env chưa tồn tại. Đang tạo từ .env.example..."
    cp .env.example .env
    echo "[.env] Đã tạo file .env mặc định. Bạn có thể cập nhật API Key vào .env."
else
    echo "[.env] Tìm thấy file .env."
fi

echo "[Docker] Đang khởi chạy các services bằng Docker Compose..."
docker compose up -d --build

echo ""
echo "==================================================="
echo "  TẤT CẢ SERVICES ĐÃ KHỞI CHẠY THÀNH CÔNG!"
echo "==================================================="
echo "- Web CSKH Workbench:    http://localhost:8501"
echo "- API Gateway (Swagger): http://localhost:8000/docs"
echo "==================================================="

