#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f backend/app/config.py ]; then cp backend/app/config.example.py backend/app/config.py; fi
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' '请先用 Python 3.11+ 创建 .venv 并安装 backend/requirements.txt（见 README.md）'
  exit 1
fi
if [ ! -f frontend/dist/index.html ]; then npm --prefix frontend ci; npm --prefix frontend run build; fi
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
