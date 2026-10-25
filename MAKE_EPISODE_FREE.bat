@echo off
title Story Factory - Free Episode ($0)
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
echo Making a FREE video: free pictures + free voices + slow zoom.
echo The free picture server is often busy, so this can take 5-30 minutes.
py pipeline\make_episode.py %F% --free
echo.
echo If you see "Done:" above, the video is in the output folder (folder name ends with _free).
pause
