REM run python file 'open_browser_cmd' from within pyopenlab and pass the file location
call conda.bat activate base
cd C:\Users\Hera\Documents\GitHub\pyopenlab\
python -m pyopenlab.ui.open_browser_cmd %1

cmd /k 