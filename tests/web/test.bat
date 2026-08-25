@echo off
chcp 65001 >nul
rem Тесты веб-консоли. Лежит рядом с ними, а запускается из корня проекта:
rem pytest и импорты рассчитывают на него.
cd /d "%~dp0..\.."

if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" -m pytest tests/web %*
pause
