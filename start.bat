@echo off
rem Lance le bot dans cette fenetre : il y affiche son journal. Ctrl+C pour l'arreter.
rem Les options de run.py passent telles quelles : start.bat --check, start.bat --demo, start.bat --demo --format portrait.
title Launch video maker
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Premiere installation : creation de l'environnement Python...
    py -3 -m venv venv || python -m venv venv || goto :error
    venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto :error
)
if not exist ".env" copy /y ".env.example" ".env" >nul

venv\Scripts\python.exe run.py %*
goto :end

:error
echo.
echo L'installation a echoue. Verifie que Python 3.11 ou plus recent est installe.

:end
pause
