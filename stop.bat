@echo off
rem AI Asset Studio: stop the backend (port 8000) and the UI (port 5173) started by open.bat.
setlocal

for %%P in (8000 5173) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /R /C:"127.0.0.1:%%P .*LISTENING"') do (
    echo Stopping process %%I on port %%P
    taskkill /PID %%I /T /F >nul 2>&1
  )
)

rem Close the two console windows opened by open.bat.
taskkill /FI "WINDOWTITLE eq AAS Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AAS Frontend*" /T /F >nul 2>&1

echo Stopped.
endlocal
