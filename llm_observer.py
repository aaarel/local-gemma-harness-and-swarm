import subprocess
import re
import time
import sys
from datetime import datetime

def get_gpu_metrics():
    """Queries Apple Silicon GPU metrics via ioreg."""
    try:
        out = subprocess.check_output(["ioreg", "-r", "-c", "IOAccelerator"], text=True, timeout=1)
        match_util = re.search(r'"Device Utilization %"\s*=\s*(\d+)', out)
        match_mem = re.search(r'"Alloc system memory"\s*=\s*(\d+)', out)
        
        util = float(match_util.group(1)) if match_util else 0.0
        mem_gb = float(match_mem.group(1)) / (1024**3) if match_mem else 0.0
        return util, mem_gb
    except Exception:
        return 0.0, 0.0

def get_cpu_usage():
    """Gets CPU usage via top command on macOS."""
    try:
        out = subprocess.check_output(["top", "-l", "1", "-n", "0"], text=True)
        cpu_match = re.search(r'CPU usage: ([\d.]+)%', out)
        return float(cpu_match.group(1)) if cpu_match else 0.0
    except Exception:
        return 0.0

def print_report():
    cpu = get_cpu_usage()
    gpu_util, gpu_mem = get_gpu_metrics()
    
    # ANSI Escape Sequences for a "live" terminal experience
    # \033[H -> Move cursor to top-left
    # \033[J -> Clear screen from cursor to end
    sys.stdout.write("\033[H\033[J")
    
    print("="*50)
    print(f" SYSTEM HEALTH MONITOR | {datetime.now().strftime('%H:%M:%S')}")
    print("="*50)
    print(f" [CPU]    Usage: {cpu:>6.1f}%")
    print(f" [GPU]    Util: {gpu_util:>6.1f}% | Mem: {gpu_mem:>6.2f} GB")
    print("-" * 50)
    print(f" Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(" Press Ctrl+C to exit")
    print("="*50)

if __name__ == "__main__":
    try:
        while True:
            print_report()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
        sys.exit(0)
