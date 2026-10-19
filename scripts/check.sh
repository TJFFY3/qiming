#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f backend/app/config.py ]; then cp backend/app/config.example.py backend/app/config.py; fi
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m unittest discover -s vendor/chemistry/tests -q
npm --prefix frontend test
npm --prefix frontend run build
