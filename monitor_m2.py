import psutil
import subprocess
import curses
import time
import re
import sys

def get_gpu_metrics():
    """
    Queries Apple Silicon GPU utilization and memory allocation directly
    from the macOS IOKit accelerator registry. Requires ZERO sudo.
    """
    try:
        out = subprocess.check_output(
            ["ioreg", "-r", "-c", "IOAccelerator"],
            text=True,
            timeout=1
        )
        match_util = re.search(r'"Device Utilization %"\s*=\s*(\d+)', out)
        match_mem = re.search(r'"Alloc system memory"\s*=\s*(\d+)', out)

        util = float(match_util.group(1)) if match_util else 0.0
        mem_gb = float(match_mem.group(1)) / (1024**3) if match_mem else 0.0
        return util, mem_gb
    except Exception:
        return None, None

def draw_table(stdscr, cpu_usage, ram_usage, gpu_util, gpu_mem):
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    # Header
    header = "--- Apple Silicon System Monitor (M2 Pro) ---"
    try:
        stdscr.addstr(0, max(0, (width - len(header)) // 2), header, curses.A_BOLD)
    except curses.error:
        pass

    # CPU Row
    cpu_str = f"CPU Usage:      {cpu_usage:6.2f}%"
    try:
        stdscr.addstr(2, 2, cpu_str)
    except curses.error:
        pass

    # RAM Row
    mem = psutil.virtual_memory()
    ram_str = f"RAM Usage:      {mem.percent:6.2f}% ({mem.used / 1024**3:.2f} / {mem.total / 1024**3:.2f} GB)"
    try:
        stdscr.addstr(3, 2, ram_str)
    except curses.error:
        pass

    # GPU Utilization Row
    if gpu_util is not None:
        gpu_str = f"GPU Usage:      {gpu_util:6.2f}%"
    else:
        gpu_str = "GPU Usage:      N/A"
    try:
        stdscr.addstr(4, 2, gpu_str)
    except curses.error:
        pass

    # GPU Memory Row
    if gpu_mem is not None and gpu_mem > 0:
        gpu_mem_str = f"GPU Allocated:  {gpu_mem:6.2f} GB"
        try:
            stdscr.addstr(5, 2, gpu_mem_str)
        except curses.error:
            pass

    # Status / Info
    try:
        stdscr.addstr(7, 2, "Status: Monitoring local LiteRT & Gemma 4 on Apple Metal GPU", curses.A_DIM)
    except curses.error:
        pass

    # Footer
    footer = "Press 'q' to quit"
    try:
        stdscr.addstr(height - 2, 2, footer, curses.A_STANDOUT)
    except curses.error:
        pass
    
    stdscr.refresh()

def main(stdscr):
    # Curses setup
    curses.curs_set(0)
    stdscr.nodelay(True)

    while True:
        try:
            cpu = psutil.cpu_percent()
            ram_usage = psutil.virtual_memory().percent
            gpu_util, gpu_mem = get_gpu_metrics()
            
            draw_table(stdscr, cpu, ram_usage, gpu_util, gpu_mem)
            
            # Check for input
            key = stdscr.getch()
            if key == ord('q'):
                break
                
            time.sleep(1)
        except curses.error:
            pass
        except Exception as e:
            try:
                stdscr.addstr(9, 2, f"Error: {e}")
                stdscr.refresh()
            except:
                pass
            time.sleep(2)

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
