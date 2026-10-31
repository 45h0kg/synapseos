"""SynapseOS status dashboard. Press q to leave, r to refresh."""
import curses
import os
import shutil
import subprocess
import sys
import time

CLASS_NET = "/sys/class/net"


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def interfaces():
    rows = []
    if not os.path.isdir(CLASS_NET):
        return rows
    for name in sorted(os.listdir(CLASS_NET)):
        try:
            with open(f"{CLASS_NET}/{name}/operstate") as f:
                state = f.read().strip()
        except OSError:
            state = "unknown"
        rows.append((name, state))
    return rows


def unit_state(unit):
    return run("systemctl", "is-active", unit) or "unknown"


def lines():
    rows = ["SynapseOS", time.strftime("%Y-%m-%d %H:%M:%S"), ""]
    rows.append(f"air gap      {unit_state('airgap.target')}")
    rows.append(f"ebpf monitor {unit_state('synapse-ebpf-monitor.service')}")
    rows.append("")
    rows.append("interfaces")
    rows += [f"  {name:<14}{state}" for name, state in interfaces()]
    rows.append("")
    rows.append("tools")
    for tool in ("garak", "inspect", "synapse-sandbox", "synapse-triage", "tshark", "nmap"):
        rows.append(f"  {tool:<18}{'ok' if shutil.which(tool) else 'missing'}")
    rows += ["", "enter air gap: sudo systemctl start airgap.target (reboot to leave)"]
    return rows


def draw(screen):
    curses.curs_set(0)
    screen.timeout(2000)
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        for y, row in enumerate(lines()[: height - 1]):
            screen.addnstr(y, 0, row, width - 1)
        screen.addnstr(height - 1, 0, "q quit  r refresh", width - 1)
        screen.refresh()
        if screen.getch() == ord("q"):
            return


def main():
    if "--once" in sys.argv or not sys.stdout.isatty():
        print("\n".join(lines()))
    else:
        curses.wrapper(draw)


if __name__ == "__main__":
    main()
