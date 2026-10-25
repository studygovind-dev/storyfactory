@echo off
title Story Factory - First Time Setup
echo.
echo ===== STEP 1: Installing ffmpeg (video tool) =====
where ffmpeg >nul 2>nul
if %errorlevel%==0 (
  echo ffmpeg is already installed. Good.
) else (
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  echo.
  echo If ffmpeg was just installed, CLOSE this window and double-click SETUP_FIRST.bat again.
)
echo.
echo ===== STEP 2: Installing Python helper =====
python -m pip install requests
echo.
echo ===== STEP 3: Your keys =====
if exist .env (
  echo .env file already exists - skipping. Delete it to enter keys again.
  goto done
)
echo Paste each key and press Enter. Leave blank if you do not have it yet.
echo.
set /p GEM=Gemini API key: 
set /p KA=Kling Access Key: 
set /p KS=Kling Secret Key: 
set /p EL=ElevenLabs API key: 
set /p VM=ElevenLabs MALE voice ID: 
set /p VF=ElevenLabs FEMALE voice ID: 
set /p VC=ElevenLabs CHILD voice ID: 
set /p TT=Telegram bot token: 
set /p TC=Telegram chat ID: 
(
echo GEMINI_API_KEY=%GEM%
echo KLING_ACCESS_KEY=%KA%
echo KLING_SECRET_KEY=%KS%
echo ELEVEN_API_KEY=%EL%
echo VOICE_MALE=%VM%
echo VOICE_FEMALE=%VF%
echo VOICE_CHILD=%VC%
echo TELEGRAM_BOT_TOKEN=%TT%
echo TELEGRAM_CHAT_ID=%TC%
) > .env
:done
echo.
echo Setup finished. Now double-click TEST_FREE.bat to check everything works.
pause
