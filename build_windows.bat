@echo off
echo Building HardLock Windows executable...
pip install -r requirements.txt pyinstaller pywin32
pyinstaller --onefile --windowed --name "HardLock" --icon=icon.png -m hardlock
echo.
echo Done. Look in the dist\ folder for HardLock.exe
pause
