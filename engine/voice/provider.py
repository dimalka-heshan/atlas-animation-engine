"""Versioned JSON subprocess boundary for the optional official Turbo runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from engine.voice.process import run_worker

SOURCE_REVISION = "ab55923c27757c90cfcc407baa57dc25a7d25217"
MODEL_REVISION = "749d1c1a46eb10492095d68fbcf55691ccf137cd"
MODEL_REPO = "ResembleAI/chatterbox-turbo"


class ChatterboxProvider:
    def __init__(self, runtime_python: Path, *, device="cpu", model_cache=None, timeout=1800):
        self.runtime_python = Path(runtime_python).resolve()
        if device not in {"cpu", "cuda"}:
            raise ValueError("Supported Turbo devices are cpu and cuda")
        self.device = device
        self.model_cache = Path(model_cache or "outputs/voice-models").resolve()
        self.timeout = timeout
        self._identity = None

    def _run(self, command, **payload):
        if not self.runtime_python.is_file():
            raise RuntimeError(f"Voice runtime Python missing: {self.runtime_python}. Run tools/install_voice_runtime.py")
        worker = Path(__file__).with_name("worker.py")
        request = {"protocol": 1, "command": command, "device": self.device,
                   "model_cache": str(self.model_cache), "source_revision": SOURCE_REVISION,
                   "model_revision": MODEL_REVISION, "model_repo": MODEL_REPO, **payload}
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["HF_HUB_DISABLE_TELEMETRY"] = "1"
        env["HF_HUB_DISABLE_XET"] = "1"
        try:
            process = run_worker([str(self.runtime_python), str(worker)],
                json.dumps(request, allow_nan=False), timeout=self.timeout, env=env)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Turbo runtime timed out after {self.timeout}s; no completed speech was published") from error
        except OSError as error:
            raise RuntimeError(f"Cannot start voice runtime: {error}") from error
        try:
            result = json.loads(process.stdout)
        except ValueError as error:
            raise RuntimeError(f"Voice runtime returned invalid JSON: {process.stderr[-2000:]}") from error
        if process.returncode or result.get("protocol") != 1 or result.get("ok") is not True:
            raise RuntimeError(f"Turbo runtime failed: {result.get('error', process.stderr[-2000:])}")
        return result["result"]

    @property
    def identity(self):
        if self._identity is None:
            diagnostic = self.doctor()
            if not diagnostic["ready"]:
                raise RuntimeError(f"Turbo runtime not ready: {diagnostic.get('error', diagnostic)}")
            worker_hash = hashlib.sha256(Path(__file__).with_name("worker.py").read_bytes()).hexdigest()
            self._identity = {"provider": "chatterbox-turbo", "source_revision": SOURCE_REVISION,
                              "model_revision": MODEL_REVISION, "device": self.device,
                              "runtime": diagnostic["runtime"], "worker_sha256": worker_hash}
        return self._identity

    def doctor(self):
        try:
            return self._run("doctor")
        except RuntimeError as error:
            return {"ready": False, "runtime_python": str(self.runtime_python), "error": str(error),
                    "source_revision": SOURCE_REVISION, "model_revision": MODEL_REVISION}

    def download_models(self):
        return self._run("download")

    def generate(self, segments, outputs, reference, settings):
        return self._run("generate", segments=segments, outputs=[str(Path(p).resolve()) for p in outputs],
                         reference=str(reference) if reference else None, settings=settings)
