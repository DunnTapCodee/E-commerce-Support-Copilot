"""Local multi-process launcher for all 5 services without Docker."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

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
    print("=" * 65)
    print("🚀 KHỞI ĐỘNG HỆ THỐNG PHÂN TÁN MICROSERVICES (LOCAL DEV)")
    print("=" * 65)

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
        # Start backend services first
        for item in COMMANDS[:3]:
            print(f"Khởi chạy {item['name']}...")
            p = subprocess.Popen(item["cmd"], cwd=ROOT_DIR, env=env)
            processes.append((p, item["name"]))
            time.sleep(1.5)

        # Start Gateway
        print(f"Khởi chạy {COMMANDS[3]['name']}...")
        p_gw = subprocess.Popen(COMMANDS[3]["cmd"], cwd=ROOT_DIR, env=env)
        processes.append((p_gw, COMMANDS[3]["name"]))
        time.sleep(1.5)

        # Start UI
        print(f"Khởi chạy {COMMANDS[4]['name']}...")
        p_ui = subprocess.Popen(COMMANDS[4]["cmd"], cwd=ROOT_DIR, env=env)
        processes.append((p_ui, COMMANDS[4]["name"]))

        print("\n" + "=" * 65)
        print("✨ TẤT CẢ DỊCH VỤ ĐÃ SẴN SÀNG:")
        print("  - Gateway API:         http://127.0.0.1:8000/docs")
        print("  - Intent Service:      http://127.0.0.1:8005/docs")
        print("  - RAG Service:         http://127.0.0.1:8002/docs")
        print("  - Telemetry Service:   http://127.0.0.1:8003/docs")
        print("  - Streamlit UI:        http://127.0.0.1:8501")
        print("=" * 65)
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
