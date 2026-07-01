@echo off
where python >nul 2>&1
if errorlevel 1 (
    echo [statusline] python not found -- install Python 3.8+ to enable the status line
    exit /b 0
)
python -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>&1
if errorlevel 1 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
    echo [statusline] Python 3.8+ required, found %PYVER%
    exit /b 0
)
python "%USERPROFILE%\.claude\statusline.py"
