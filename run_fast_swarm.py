#!/usr/bin/env python3
"""Convenience launcher forwarding to Option A subfolder implementation."""
import os
import sys

TARGET = os.path.join(
    os.path.dirname(__file__),
    "Option A: Production-Grade GCP Terraform Module Scaffolding & Validation",
    "run_fast_swarm.py",
)

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, TARGET] + sys.argv[1:])
