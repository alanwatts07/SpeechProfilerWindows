@echo off
echo ============================================
echo Building Speech Profiler for Windows
echo ============================================
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run build script
python build.py

echo.
echo Done! Check dist\SpeechProfiler\ folder
pause
