"""Local multi-process launcher for all microservices without Docker."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Fix Vietnamese/emoji output on Windows consoles with cp1252 encoding
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent

# Ensure Python knows about the project root
env = os.environ.copy()
env["PYTHONPATH"] = str(ROOT_DIR)
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"

# Read .env if present
env_file = ROOT_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

# Deployment-generated calibrated threshold takes precedence over demo defaults.
deployment_env = ROOT_DIR / "artifacts/models/intent/deployment.env"
if deployment_env.exists():
    for line in deployment_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()

COMMANDS = [
    {
        "name": "intent_service (8005)",
        "cmd": [sys.executable, "-m", "uvicorn", "services.intent_service.src.main:app", "--port", "8005", "--host", "127.0.0.1"],
    },
    {
        "name": "rag_service (8002)",
        "cmd": [sys.executable, "-m", "uvicorn", "services.rag_service.src.main:app", "--port", "8002", "--host", "127.0.0.1"],
    },
    {
        "name": "telemetry_service (8003)",
        "cmd": [sys.executable, "-m", "uvicorn", "services.telemetry_service.src.main:app", "--port", "8003", "--host", "127.0.0.1"],
    },
    {
        "name": "document_service (8004)",
        "cmd": [sys.executable, "-m", "uvicorn", "services.document_service.src.main:app", "--port", "8004", "--host", "127.0.0.1"],
    },
    {
        "name": "conversation_service (8006)",
        "cmd": [sys.executable, "-m", "uvicorn", "services.conversation_service.src.main:app", "--port", "8006", "--host", "127.0.0.1"],
    },
    {
        "name": "gateway (8000)",
        "cmd": [sys.executable, "-m", "uvicorn", "services.gateway.src.main:app", "--port", "8000", "--host", "127.0.0.1"],
    },
    {
        "name": "ui_service (8501)",
        "cmd": [sys.executable, "-m", "streamlit", "run", "services/ui_service/src/app.py", "--server.port=8501", "--server.address=127.0.0.1", "--server.headless=true"],
    },
]


def main():
    processes = []
    print("=" * 68)
    print("🚀 KHỞI ĐỘNG HỆ THỐNG TOÀN DIỆN E-COMMERCE COPILOT (LOCAL DEV)")
    print("=" * 68)

    def signal_handler(sig, frame):
        print("\n[Ctrl+C] Đang dừng tất cả các tiến trình con...")
        for proc, name in processes:
            print(f"  -> Dừng {name} (PID: {proc.pid})")
            try:
                proc.terminate()
            except Exception:
                pass
        time.sleep(1)
        for proc, name in processes:
            try:
                proc.kill()
            except Exception:
                pass
        print("Đã dọn dẹp sạch toàn bộ tiến trình. Tạm biệt!")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start all services sequentially
        for item in COMMANDS:
            print(f"Khởi chạy {item['name']}...")
            p = subprocess.Popen(item["cmd"], cwd=ROOT_DIR, env=env)
            processes.append((p, item["name"]))
            time.sleep(1.2)

        print("\n" + "=" * 68)
        print("✨ TẤT CẢ DỊCH VỤ ĐÃ SẴN SÀNG:")
        print("  1. Gateway API:            http://127.0.0.1:8000/docs")
        print("  2. Conversation Service:   http://127.0.0.1:8006/docs")
        print("  3. Document Service:       http://127.0.0.1:8004/docs")
        print("  4. RAG Service:            http://127.0.0.1:8002/docs")
        print("  5. Intent Service:         http://127.0.0.1:8005/docs")
        print("  6. Telemetry Service:      http://127.0.0.1:8003/docs")
        print("  -------------------------------------------------------------")
        print("  📱 Giao diện Streamlit:    http://127.0.0.1:8501")
        print("  ⚡ Giao diện React TSX:     http://localhost:5173 (chạy 'cd frontend; npm run dev')")
        print("=" * 68)
        print("Bấm Ctrl + C để dừng toàn bộ hệ thống bất kỳ lúc nào.\n")

        while True:
            time.sleep(1)
            for p, name in processes:
                if p.poll() is not None:
                    print(f"⚠️ Cảnh báo: Tiến trình {name} đã thoát với mã {p.returncode}")

    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
