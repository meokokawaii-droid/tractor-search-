@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Leeway Parts 邮件发送服务
echo ============================================
echo.
echo 启动邮件服务器...
echo 浏览器将自动打开 http://localhost:5010
echo.

:: Try tractor-demo venv first
if exist "%LocalAppData%\..\..\ProgramData\WorkBuddy\users\d2ea318\.workbuddy\binaries\python\envs\tractor-demo\Scripts\python.exe" (
    start "LeewayParts-Outreach" "%LocalAppData%\..\..\ProgramData\WorkBuddy\users\d2ea318\.workbuddy\binaries\python\envs\tractor-demo\Scripts\python.exe" server.py
) else (
    :: Fall back to python in PATH
    start "LeewayParts-Outreach" python server.py
)

timeout /t 3 /nobreak >nul
start "" http://localhost:5010
echo 完成！关闭此窗口即可。
pause >nul
