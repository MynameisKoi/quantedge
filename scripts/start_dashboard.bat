@echo off
title QuantEdge AI - Analytics Dashboard Server
cd /d "%~dp0\.."

echo ======================================================================
echo           QuantEdge AI - Institutional Analytics Dashboard
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    pause
    exit /b 1
)

echo [1/2] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [2/2] Launching FastAPI Dashboard Server on http://localhost:8000 ...
echo Press Ctrl+C to stop the dashboard server.
echo.

.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
