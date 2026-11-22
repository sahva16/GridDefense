#!/bin/sh
# GridDefense Console — builds on first run, then starts everything at http://localhost:8000
cd "$(dirname "$0")" || exit 1
command -v python3 >/dev/null || { echo "Python 3.10-3.13 is needed (python.org)"; exit 1; }

if [ ! -f frontend/dist/index.html ]; then
  command -v npm >/dev/null || { echo "The app is not built yet and Node.js LTS is needed (nodejs.org)"; exit 1; }
  echo "Building the 3D app (first run only, takes a few minutes)..."
  (cd frontend && npm install && npm run build) || { echo "Build failed - see above"; exit 1; }
fi

cd backend || exit 1
if [ ! -d .venv ]; then
  echo "Setting up Python (first run only, takes a few minutes)..."
  python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt || { echo "Setup failed - see above"; exit 1; }
else
  . .venv/bin/activate
fi

echo ""
echo "GridDefense console is starting at http://localhost:8000 - keep this window open (Ctrl+C stops it)."
( sleep 10; (open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null) ) &
uvicorn app.main:app --port 8000
