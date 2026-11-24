"""Capture isolated worker output without inherited-pipe hangs on Windows."""
import os
import signal
import subprocess
import tempfile


def run_worker(command, payload: str, *, timeout: float, env: dict):
    if not 0 < timeout <= 7200:
        raise ValueError("Voice timeout must be greater than zero and at most 7200 seconds")
    with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        stdin.write(payload.encode("utf-8")); stdin.seek(0)
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen(command, stdin=stdin, stdout=stdout, stderr=stderr, env=env, **options)
        try:
            process.wait(timeout=timeout)
        except BaseException:
            if os.name == "nt":
                # A Windows venv launcher can own a second Python process. Kill its tree.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            raise
        stdout.seek(0)
        output = stdout.read(2 * 1024 * 1024 + 1)
        if len(output) > 2 * 1024 * 1024:
            raise ValueError("Voice worker response exceeds 2 MiB")
        stderr.seek(0, 2)
        stderr.seek(max(0, stderr.tell() - 64000))
        errors = stderr.read().decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(command, process.returncode, output.decode("utf-8", errors="replace"), errors)
