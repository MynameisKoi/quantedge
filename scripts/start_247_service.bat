@echo off
title QuantEdge AI - 24/7 Live Trading Engine
cd /d "%~dp0\.."

echo ======================================================================
echo          QuantEdge AI - 24/7 Exness MT4 Production Launcher
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    echo Please install dependencies first.
    pause
    exit /b 1
)

echo [1/3] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [2/3] Checking MT4 FileBridge link...
.venv\Scripts\python.exe run_live_bot.py --check-bridge
if %ERRORLEVEL% neq 0 (
    echo.
    echo [WARNING] MT4 EA heartbeat was not detected!
    echo Please ensure:
    echo   1. Exness MetaTrader 4 is running.
    echo   2. QuantEdgeBridge.mq4 is attached to any active chart.
    echo   3. 'Allow live trading' and 'Allow DLL imports' are checked in MT4.
    echo.
    echo The bot will continue and wait for MT4 to connect automatically.
    echo.
)

echo [3/3] Launching QuantEdge 24/7 Supervisor Watchdog...
:WATCHDOG_LOOP
echo [%DATE% %TIME%] Starting QuantEdge live engine...
.venv\Scripts\python.exe run_live_bot.py

echo.
echo [%DATE% %TIME%] Process exited with code %ERRORLEVEL%.
echo Restarting QuantEdge in 5 seconds (Press Ctrl+C to terminate)...
timeout /t 5 /nobreak >nul
goto WATCHDOG_LOOP
