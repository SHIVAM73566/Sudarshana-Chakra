# actions/cmd_control.py
"""
Command Control for Sudarshana AI.

Allows the AI to open files, launch applications, and run system commands.
This restores the `cmd_control` tool referenced by the planner and executor.
"""

import os
import platform
import shlex
import subprocess


def _open_with_default_app(path: str, player=None) -> str:
    if not os.path.exists(path):
        return f"Path not found: {path}"
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        if player:
            player.write_log(f"[cmd_control] Opened: {path}")
        return f"Opened: {path}"
    except Exception as e:
        return f"Failed to open {path}: {e}"


def _run_command(command: str, player=None) -> str:
    if not command or not command.strip():
        return "No command provided."
    try:
        if platform.system() == "Windows":
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        else:
            proc = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=60,
            )
        if player:
            player.write_log(f"[cmd_control] Ran: {command}")
        output = (proc.stdout or "").strip()[:2000]
        if proc.returncode == 0:
            return f"Command executed successfully.\n{output}" if output else "Command executed successfully."
        return f"Command exited with code {proc.returncode}.\n{output}\n{proc.stderr or ''}".strip()
    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds."
    except Exception as e:
        return f"Failed to run command: {e}"


def cmd_control(parameters=None, player=None, session_memory=None) -> str:
    """
    Open files, launch apps, or run system commands.

    Supported parameter keys:
      - command / cmd       : shell command to execute
      - path / file / file_path : file or folder to open with the default app
      - app_name / app      : application to launch (delegates to open_app)
    """
    parameters = parameters or {}
    command = parameters.get("command") or parameters.get("cmd")
    path = parameters.get("path") or parameters.get("file") or parameters.get("file_path")
    app_name = parameters.get("app_name") or parameters.get("app")

    if command:
        return _run_command(command, player=player)
    if path:
        return _open_with_default_app(str(path), player=player)
    if app_name:
        from actions.open_app import open_app
        return open_app(parameters={"app_name": app_name}, player=player)
    return "Please specify a command, a file path, or an app to open, sir."