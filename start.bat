@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   E-commerce Support Copilot - Quick Start
echo ===================================================

if not exist .env (
    echo [.env] File .env chua ton tai. Dang tao tu .env.example...
    copy .env.example .env >nul
    echo [.env] Da tao file .env mac dinh. Ban co the them API Key vao .env sau.
) else (
    echo [.env] Tim thay file .env.
)

echo [Docker] Dang khoi chay cac services bang Docker Compose...
docker compose up -d --build

if %ERRORLEVEL% equ 0 (
    echo.
    echo ===================================================
    echo   TAT CA SERVICES DA KHOI CHAY THANH CONG!
    echo ===================================================
    echo - Web CSKH Workbench:    http://localhost:8501
    echo - API Gateway (Swagger): http://localhost:8000/docs
    echo ===================================================
) else (
    echo.
    echo [ERROR] Co loi xay ra khi khoi chay Docker Compose.
)
pause

