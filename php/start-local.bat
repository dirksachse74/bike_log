@echo off
rem Bike Log (PHP) on this PC, for testing. Double-click this file.
rem Needs XAMPP in C:\xampp with MySQL started in the XAMPP Control Panel. See LOCAL_TEST_WINDOWS.md.
rem Close this window to stop Bike Log.
setlocal
set "PHP=C:\xampp\php\php.exe"
set "PORT=8080"
if not exist "%PHP%" (
  echo PHP from XAMPP was not found at %PHP%.
  echo If XAMPP is somewhere else, open this file in Notepad and change the PHP line.
  pause
  exit /b 1
)
if not exist "%~dp0config\config.php" (
  echo config\config.php is missing. Copy config\config.local-sample.php to config\config.php first.
  pause
  exit /b 1
)
echo Bike Log runs at http://127.0.0.1:%PORT%/  -  close this window to stop it.
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:%PORT%/"
"%PHP%" -S 127.0.0.1:%PORT% -t "%~dp0public"
pause
