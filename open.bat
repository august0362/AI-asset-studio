@echo off
rem AI Asset Studio: start the backend and the UI in the background (no windows), then open the browser.
rem   open.bat          -> Kaggle mode (real Kaggle, profile from .env AAS_ACTIVE_PROFILE)
rem   open.bat mock     -> mock mode (no Kaggle, no quota)
rem Logs: %TEMP%\ai-asset-studio\backend.log and frontend.log. Stop everything with stop.bat.
setlocal
cd /d "%~dp0"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=kaggle"
if /i not "%MODE%"=="kaggle" if /i not "%MODE%"=="mock" (
  echo Unknown mode "%MODE%". Use: open.bat  or  open.bat mock
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [error] .venv not found. Create it first: python -m venv .venv ^&^& .venv\Scripts\pip install -e .[dev]
  pause
  exit /b 1
)

netstat -ano | findstr /R /C:"127.0.0.1:8000 .*LISTENING" >nul && (
  echo [error] Port 8000 is already in use. Run stop.bat first.
  pause
  exit /b 1
)
netstat -ano | findstr /R /C:"127.0.0.1:5173 .*LISTENING" >nul && (
  echo [error] Port 5173 is already in use. Run stop.bat first.
  pause
  exit /b 1
)

if not exist "interface\frontend\node_modules" (
  echo Installing UI packages, first run only...
  pushd interface\frontend
  call npm install
  popd
)

set "LOGDIR=%TEMP%\ai-asset-studio"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo Starting backend (%MODE% mode) and UI in the background...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath cmd.exe -WorkingDirectory '%CD%' -ArgumentList '/c set AAS_COMPUTE_MODE=%MODE%&& .venv\Scripts\python.exe -m aas_backend > \"%LOGDIR%\backend.log\" 2>&1'"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath cmd.exe -WorkingDirectory '%CD%\interface\frontend' -ArgumentList '/c set VITE_API_MODE=http&& set VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1&& npm run dev > \"%LOGDIR%\frontend.log\" 2>&1'"

rem Wait up to ~40 s for both ports.
set /a TRIES=0
:wait
set /a TRIES+=1
ping -n 3 127.0.0.1 >nul
set "UP=1"
netstat -ano | findstr /R /C:"127.0.0.1:8000 .*LISTENING" >nul || set "UP=0"
netstat -ano | findstr /R /C:"127.0.0.1:5173 .*LISTENING" >nul || set "UP=0"
if "%UP%"=="1" goto ready
if %TRIES% lss 20 goto wait

echo [error] The app did not start. Last lines of the logs:
echo ----- backend.log -----
powershell -NoProfile -Command "Get-Content -Tail 15 '%LOGDIR%\backend.log' -ErrorAction SilentlyContinue"
echo ----- frontend.log -----
powershell -NoProfile -Command "Get-Content -Tail 15 '%LOGDIR%\frontend.log' -ErrorAction SilentlyContinue"
call "%~dp0stop.bat" >nul
pause
exit /b 1

:ready
echo Running: backend http://127.0.0.1:8000 (%MODE% mode), UI http://127.0.0.1:5173
echo Logs: %LOGDIR%
if not defined AAS_NO_BROWSER start "" "http://127.0.0.1:5173"
echo Run stop.bat to stop. This window closes in 5 seconds.
ping -n 6 127.0.0.1 >nul
endlocal
