@echo off
title Story Factory - Free Test
echo Making a free test video (no keys, no cost)...
py pipeline\make_episode.py series\quiet_man_ep01.json --dry-run
echo.
echo If you see "Done:" above, open the folder output\the_quiet_man_ep01_dry and play final.mp4
pause
