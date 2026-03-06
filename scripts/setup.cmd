@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0.."

echo.
echo izTeamSlots setup
echo =================
echo.

:: ── Python ──────────────────────────────────────────────
echo Checking Python...
set "PYTHON="
where python >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    set "PYTHON=python"
)
if "%PYTHON%"=="" (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do set "PYVER=%%v"
        set "PYTHON=python3"
    )
)
if "%PYTHON%"=="" (
    echo   [x] Python 3.11+ not found. Install: https://python.org
    exit /b 1
)
echo   [v] Python: %PYVER%

:: ── uv ──────────────────────────────────────────────────
echo Checking uv...
where uv >nul 2>&1
if errorlevel 1 (
    echo   [!] uv not found. Installing...
    powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>&1
if errorlevel 1 (
    echo   [x] uv install failed. Install manually: https://docs.astral.sh/uv
    exit /b 1
)
for /f "tokens=*" %%v in ('uv --version') do echo   [v] %%v

:: ── Python venv + deps ──────────────────────────────────
set "VENV=%ROOT%\.venv"
echo Setting up Python venv...
if not exist "%VENV%\Scripts\python.exe" (
    uv venv "%VENV%" --python %PYTHON% -q
)
echo   [v] venv: %VENV%

echo Installing Python dependencies...
uv pip install -q --python "%VENV%\Scripts\python.exe" -r "%ROOT%\requirements.txt"
echo   [v] Python deps installed

:: ── Bun ─────────────────────────────────────────────────
echo Checking Bun...
where bun >nul 2>&1
if errorlevel 1 (
    echo   [!] Bun not found. Installing...
    powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://bun.sh/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.bun\bin;%PATH%"
)
where bun >nul 2>&1
if errorlevel 1 (
    echo   [x] Bun install failed. Install manually: https://bun.sh
    exit /b 1
)
for /f "tokens=*" %%v in ('bun --version') do echo   [v] Bun: %%v

:: ── UI deps ─────────────────────────────────────────────
echo Installing UI dependencies...
pushd "%ROOT%\ui"
bun install --frozen-lockfile 2>nul || bun install
popd
echo   [v] UI deps installed

:: ── .env ────────────────────────────────────────────────
if not exist "%ROOT%\.env" (
    if exist "%ROOT%\.env.example" (
        copy "%ROOT%\.env.example" "%ROOT%\.env" >nul
        echo   [!] .env created from .env.example — edit it with your API keys
    )
)

:: ── Done ────────────────────────────────────────────────
echo.
echo Setup complete!
echo.
echo   Start:  npm start
echo   Or:     izteamslots
echo.
