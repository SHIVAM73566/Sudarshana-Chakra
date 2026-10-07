@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Sudarshana Chakra - Launcher
cd /d "%~dp0"

color 0E

echo ==========================================================================
echo                S U D A R S H A N A   C H A K R A
echo          AUTONOMOUS SELF-EVOLUTION COGNITIVE ENGINE
echo     [Skill Forge // Crucible Sandbox // 180 FPS HoloCore]
echo ==========================================================================
echo.
echo Launching automated bootstrap sequence...

powershell.exe -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"

if %errorlevel% neq 0 (
  echo ERROR: Bootstrap failed.
  pause
  exit /b %errorlevel%
)
exit /b 0