#!/bin/bash
# Double-click this file in Finder to open Cassiopeia.
# If Cassiopeia is already running in the background, this only opens its window.
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
exec "$PY" -m cassiopeia
