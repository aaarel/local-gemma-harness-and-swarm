#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Directly invoke the virtual environment's Python 3.11 binary (has psutil installed)
exec .venv/bin/python monitor_m2.py "$@"
