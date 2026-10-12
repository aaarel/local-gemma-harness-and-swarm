#!/usr/bin/env python3
"""Convenience launcher forwarding to Option B subfolder implementation."""
import os
import sys

TARGET = os.path.join(
    os.path.dirname(__file__),
    "Option B: Kubernetes & GKE Production Hardening & Kustomize Migration",
    "run_gke_swarm.py",
)

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, TARGET] + sys.argv[1:])
