@echo off
title Story Factory - Make Episode
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
echo Making the video. This takes 10-25 minutes. Do not close this window.
python pipeline\make_episode.py %F%
echo.
echo Finished. The video is also in the output folder.
pause
