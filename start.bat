@echo off
chcp 65001 >nul
rem Веб-консоль JAWL. Открывает браузер сама.
rem Пока это окно открыто, в нём видно состояние агента.
rem Закроете окно - агент, запущенный отсюда, тоже остановится.
title JAWL - консоль
cd /d "%~dp0"

set "VENV_PY=venv\Scripts\python.exe"
if exist "%VENV_PY%" goto :run

rem ---------------------------------------------------------------- первый запуск
rem Окружения нет. Готовить его сами не будем: у JAWL есть штатный загрузчик
rem jawl.py - он создаёт venv, ставит зависимости и умеет откатиться на uv,
rem если сборка пакетов не удалась. Ключ --version проходит весь этот путь,
rem проверяет, что всё импортируется, и выходит без интерактивного меню.

if not exist "jawl.py" (
    echo.
    echo Не найден jawl.py - запускайте start.bat из корня проекта JAWL.
    echo.
    pause
    exit /b 1
)

rem Чем запустить загрузчик. py.exe лежит в C:\Windows и есть почти всегда,
rem а python в PATH попадает не при всякой установке.
set "BOOT="
where py >nul 2>&1
if %errorlevel%==0 set "BOOT=py"
if defined BOOT goto :boot
where python >nul 2>&1
if %errorlevel%==0 set "BOOT=python"

:boot
if not defined BOOT (
    echo.
    echo Python не найден. Установите Python 3.11 с python.org
    echo и при установке отметьте "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo.
echo Первый запуск: подготавливаю окружение штатным загрузчиком JAWL.
echo Скачиваются зависимости - это займёт несколько минут.
echo.

"%BOOT%" jawl.py --version
if errorlevel 1 goto :bootfail
if not exist "%VENV_PY%" goto :bootfail

echo.
echo Окружение готово. Запускаю консоль.
echo.

rem ---------------------------------------------------------------- запуск
:run
"%VENV_PY%" -m src.web %*

if errorlevel 1 (
    echo.
    echo Консоль завершилась с ошибкой. Строки выше подскажут причину.
    pause
)
exit /b 0

:bootfail
echo.
echo Не удалось подготовить окружение. Запустите загрузчик вручную:
echo     py jawl.py
echo и посмотрите, на чём он остановился.
echo.
pause
exit /b 1
