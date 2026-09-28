#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Directly invoke the virtual environment's Python 3.11 binary
exec .venv/bin/python harness_tui.py "$@"
