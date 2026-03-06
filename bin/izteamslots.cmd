@echo off
setlocal

set "ROOT=%~dp0.."

:: Resolve Python from venv
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_BIN=%ROOT%\.venv\Scripts\python.exe"
)

:: Find bun
where bun >nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.bun\bin\bun.exe" (
        set "PATH=%USERPROFILE%\.bun\bin;%PATH%"
    ) else (
        echo Bun not found. Run: npm run setup 1>&2
        exit /b 1
    )
)

bun run --cwd "%ROOT%\ui" src/main.ts %*
