@echo off
setlocal

:: Get current date and time
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do (
    set month=%%a
    set day=%%b
    set year=%%c
)
for /f "tokens=1-2 delims=:." %%a in ("%time%") do (
    set hour=%%a
    set minute=%%b
)

:: Pad with zero if necessary
if %hour% LSS 10 set hour=0%hour%
if %minute% LSS 10 set minute=0%minute%

:: Generate commit message
set msg=Auto-commit on %year%-%month%-%day% at %hour%:%minute%

:: Run git commands
echo Adding changes...
git add .

echo Committing with message: %msg%
git commit -m "%msg%"

echo Pushing to origin/main...
git push origin main

endlocal
pause
