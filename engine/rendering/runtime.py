"""Discover executables and run argument lists without invoking a shell."""
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path


def find_tool(name: str, explicit: Path | str | None = None) -> Path:
    override = explicit or os.environ.get(f"ATLAS_{name.upper()}")
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(f"{name} executable not found: {candidate}")
        return candidate.resolve()
    found = shutil.which(name)
    if found:
        return Path(found).resolve()
    if name == "blender":
        roots = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Blender Foundation",
                 Path("/Applications/Blender.app/Contents/MacOS")]
        candidates = [p for root in roots if root.exists()
                      for p in root.glob("**/blender.exe" if os.name == "nt" else "blender")]
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime).resolve()
    raise FileNotFoundError(f"{name} not found. Install it or set ATLAS_{name.upper()} to its executable path.")


def capture(command: list[str], timeout: float = 30) -> str:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} exited {result.returncode}: {result.stderr[-2000:]}")
    return result.stdout


def run_logged(command: list[str], log: Path, timeout: float) -> float:
    """Run a tool, retaining full diagnostics and reaping it on timeout/cancel."""
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"command": command}) + "\n")
        handle.flush()
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, shell=False)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise RuntimeError(f"{Path(command[0]).name} timed out; diagnostics: {log}") from exc
        except BaseException:
            process.kill()
            process.wait()
            raise
    if code:
        raise RuntimeError(f"{Path(command[0]).name} exited {code}; diagnostics: {log}")
    return time.perf_counter() - started


def doctor() -> dict:
    report = {"os": platform.platform(), "python": platform.python_version(),
              "logical_cpus": os.cpu_count(), "tools": {}}
    for name in ("blender", "ffmpeg", "ffprobe"):
        try:
            executable = find_tool(name)
            version = capture([str(executable), "--version" if name == "blender" else "-version"])
            report["tools"][name] = {"path": str(executable), "version": version.splitlines()[0]}
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            report["tools"][name] = {"error": str(exc)}
    if os.name == "nt":
        try:
            report["hardware"] = json.loads(capture(["powershell", "-NoProfile", "-Command",
                "@{cpu=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfLogicalProcessors);"
                "memory=(Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize;"
                "gpu=(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM)} | ConvertTo-Json -Depth 4"]))
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            report["hardware_error"] = str(exc)
    return report
