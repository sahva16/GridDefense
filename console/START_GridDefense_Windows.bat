@echo off
setlocal EnableDelayedExpansion
title GridDefense Console
cd /d "%~dp0"
echo ============================================================
echo   GridDefense Console
echo ============================================================
echo.

rem ---- 0. Must be run from an extracted folder, not from inside the zip ----
if not exist "backend\app\main.py" (
  echo [X] Cannot find backend\app\main.py next to this file.
  echo     Extract the whole zip first ^(right-click the zip ^> Extract All^),
  echo     then double-click this file inside the extracted folder.
  goto :fail
)
if not exist "backend\bundle\griddefense_model.joblib" (
  echo [X] The model bundle is missing from backend\bundle.
  echo     Copy the contents of your app_bundle folder into backend\bundle.
  goto :fail
)

rem ---- 1. Find a Python the models can run on (3.10 to 3.13) ----
rem scikit-learn 1.6.1 (the version that trained the models) has no installer for Python 3.14+.
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [X] No suitable Python found. GridDefense needs Python 3.10, 3.11, 3.12 or 3.13.
  echo     Python 3.14 is too new for scikit-learn 1.6.1, which trained the models.
  echo     Install Python 3.13 from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^),
  echo     then run this file again.
  python --version 2>nul && echo     ^(The python on this PC is the version shown above.^)
  goto :fail
)
echo [OK] Found a suitable Python:
!PY! --version

rem ---- 2. The 3D app (already built inside the zip) ----
if not exist frontend\dist\index.html (
  where npm >nul 2>nul || (echo [X] The app is not built and Node.js is missing. Get the LTS version from nodejs.org. & goto :fail)
  echo Building the 3D app - first run only, takes a few minutes...
  pushd frontend
  call npm install || (popd & goto :fail)
  call npm run build || (popd & goto :fail)
  popd
)

rem ---- 3. Python environment: (re)build it if it is missing or broken ----
cd backend
if exist .venv\Scripts\uvicorn.exe (
  .venv\Scripts\python -c "import sklearn, fastapi, pypower; assert sklearn.__version__ == '1.6.1'" >nul 2>nul || (
    echo [!] The Python environment is incomplete - rebuilding it.
    rmdir /s /q .venv
  )
) else (
  if exist .venv (
    echo [!] The Python environment from an earlier attempt is incomplete - rebuilding it.
    rmdir /s /q .venv
  )
)
if not exist .venv (
  echo Setting up Python - first run only, takes 3 to 10 minutes. Please wait...
  !PY! -m venv .venv || goto :fail
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt || (rmdir /s /q .venv & goto :fail)
)
echo [OK] Python environment ready

rem ---- 4. Start ----
echo.
echo GridDefense is starting. Loading the models and checking them against the notebook
echo (about 10-20 seconds). The browser opens http://localhost:8000 by itself.
echo Keep this window open. Close it to stop GridDefense.
echo TIP: if this window seems frozen, press Enter once (clicking inside it pauses it).
echo.
start "" cmd /c "timeout /t 15 >nul & start http://localhost:8000"
.venv\Scripts\python -m uvicorn app.main:app --port 8000
echo.
echo GridDefense stopped. If you did not close it yourself, read the messages above.
goto :fail_noheader

:fail
echo.
echo Something went wrong - read the messages above.
:fail_noheader
echo.
pause
