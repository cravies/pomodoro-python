@echo off
rem Double-click to build Pomo.exe in this folder (needs uv: https://docs.astral.sh/uv/).
rem Pomo.exe keeps using the pomo.db next to it, so your history carries over.
cd /d "%~dp0"

set UV=uv
where uv >nul 2>nul || set UV=%USERPROFILE%\.local\bin\uv.exe
if not exist "%UV%" where uv >nul 2>nul || (
  echo Could not find uv. Install it from https://docs.astral.sh/uv/ and run this again.
  pause & exit /b 1
)

rem a running Pomo.exe can't be overwritten
taskkill /im Pomo.exe /f >nul 2>nul

echo Building Pomo.exe - this takes a minute or two the first time...
"%UV%" run --no-project --python 3.13 --with flask --with pywebview --with pyinstaller ^
  pyinstaller --noconfirm --onefile --windowed --name Pomo ^
  --icon "%~dp0pomo.ico" ^
  --add-data "%~dp0templates;templates" --add-data "%~dp0static;static" ^
  --distpath "%~dp0." --workpath "%~dp0build" --specpath "%~dp0build" ^
  pomo_app.py
if errorlevel 1 (
  echo.
  echo Build failed - see the messages above.
  pause & exit /b 1
)
rmdir /s /q build

rem Start menu shortcut, so Pomo shows up when you search for it
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs') + '\Pomo.lnk'); $s.TargetPath = '%~dp0Pomo.exe'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0Pomo.exe,0'; $s.Save()"

echo.
echo Done. Pomo is opening now - right-click its icon in the taskbar and choose "Pin to taskbar".
start "" "%~dp0Pomo.exe"
timeout /t 8
