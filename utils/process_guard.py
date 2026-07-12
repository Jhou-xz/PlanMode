import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

PROJECT_ROOT = "/root/plan-mode-project"


def _process_cwd(pid: int) -> str | None:
    """Return the current working directory of a process, or None if unavailable."""
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except (OSError, FileNotFoundError):
        return None


def _get_processes() -> list[dict]:
    """Return other processes running main.py from the project root.

    Excludes the current process and its parent (e.g. the bash wrapper that
    started this process) so that we do not kill our own launcher.
    """
    current_pid = os.getpid()
    parent_pid = os.getppid()
    processes: list[dict] = []
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,ppid,args"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.strip().splitlines()
        if not lines:
            return processes
        for line in lines[1:]:
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            pid_str, ppid_str, args = parts
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid in (current_pid, parent_pid):
                continue
            if "main.py" not in args:
                continue
            # If the project root isn't in args, check the process cwd.
            if PROJECT_ROOT not in args:
                cwd = _process_cwd(pid)
                if cwd != PROJECT_ROOT:
                    continue
            # Exclude shell wrappers that are launching this process.
            if args.lstrip().startswith(("/bin/bash", "/usr/bin/bash", "bash ", "sh ")):
                continue
            processes.append(
                {"pid": pid, "ppid": int(ppid_str), "args": args}
            )
    except Exception as exc:
        logger.warning("Failed to enumerate running processes: %s", exc)
    return processes


def ensure_single_instance() -> list[int]:
    """Kill any other plan-mode-project main.py instances.

    Returns the list of PIDs that were terminated.
    """
    others = _get_processes()
    killed: list[int] = []
    if not others:
        logger.info("No other main.py instances found; starting cleanly.")
        return killed

    for proc in others:
        pid = proc["pid"]
        try:
            os.kill(pid, 9)
            killed.append(pid)
            logger.warning(
                "Killed duplicate main.py process pid=%s ppid=%s args=%s",
                pid,
                proc["ppid"],
                proc["args"],
            )
        except ProcessLookupError:
            logger.info("Duplicate main.py process pid=%s already exited", pid)
        except PermissionError:
            logger.warning(
                "Permission denied killing duplicate main.py process pid=%s", pid
            )

    if killed:
        logger.info(
            "Killed %d duplicate main.py process(es): %s", len(killed), killed
        )
        # Give the OS a moment to release sockets/log files before continuing startup.
        time.sleep(1)
    return killed
