@echo off
title Story Factory - Cheap Episode (no Kling)
echo.
echo   1 = The Quiet Man (one-man army)
echo   2 = Cover Name (undercover agent)
echo   3 = The Nanny and the Boss
echo.
set /p C=Choose 1, 2 or 3: 
if "%C%"=="1" set F=series\quiet_man_ep01.json
if "%C%"=="2" set F=series\cover_name_ep01.json
if "%C%"=="3" set F=series\nanny_ep01.json
if not defined F (echo Wrong choice & pause & exit /b)
echo.
echo Making real pictures + real voice. Takes about 3-5 minutes.
py pipeline\make_episode.py %F% --no-kling
echo.
echo Finished. Look in the output folder (folder name ends with _zoom).
pause
