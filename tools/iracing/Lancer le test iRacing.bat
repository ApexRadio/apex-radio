@echo off
chcp 65001 >nul
title Apex Radio - test iRacing
set "PY=%LOCALAPPDATA%\Programs\Apex Radio\python\python.exe"
if not exist "%PY%" set "PY=py"
echo Test iRacing - laisse cette fenetre ouverte pendant que tu roules.
echo iRacing test - keep this window open while you drive.
echo.
"%PY%" -X utf8 "%~dp0iracing_probe.py"
echo.
echo Fichier a envoyer / file to send : Documents\Apex Radio\iracing_test\RESULTATS_iRacing.zip
pause
