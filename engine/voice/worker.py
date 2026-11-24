"""Run by the isolated interpreter, including from installed ATLAS wheels.

Only stdout is protocol JSON; upstream logs are redirected to stderr.
"""
import contextlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

try:
    from .model_integrity import MODEL_FILES, verify_model_files
except ImportError:  # Direct package-owned worker execution in isolated Python.
    from model_integrity import MODEL_FILES, verify_model_files



def handle(request):
    if request.get("protocol") != 1 or request.get("command") not in {"doctor", "download", "generate"}:
        raise ValueError("Unsupported voice protocol/command")
    import torch
    from huggingface_hub import snapshot_download
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    distribution = importlib.metadata.distribution("chatterbox-tts")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    revision = direct.get("vcs_info", {}).get("commit_id")
    if revision != request["source_revision"]:
        raise ValueError(f"Installed Chatterbox source revision {revision!r} does not match pinned {request['source_revision']}")
    runtime = {"python": platform.python_version(), "packages": dict(sorted(
        (dist.metadata["Name"], dist.version) for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]))}
    device = request["device"]
    available = device == "cpu" or (device == "cuda" and torch.cuda.is_available())
    gpu = [{"name": torch.cuda.get_device_name(i), "memory_bytes": torch.cuda.get_device_properties(i).total_memory}
           for i in range(torch.cuda.device_count())]
    cache = Path(request["model_cache"])
    cache.mkdir(parents=True, exist_ok=True)
    snapshot = cache / ("models--" + request["model_repo"].replace("/", "--")) / "snapshots" / request["model_revision"]
    missing = [name for name in MODEL_FILES if not (snapshot / name).is_file()]
    if request["command"] == "download":
        snapshot_download(repo_id=request["model_repo"], revision=request["model_revision"],
                          cache_dir=str(cache), allow_patterns=list(MODEL_FILES), max_workers=2)
        missing = [name for name in MODEL_FILES if not (snapshot / name).is_file()]
    ready = available and not missing
    if not missing:
        verify_model_files(snapshot)
    diagnostic = {"ready": ready, "runtime": runtime, "source_revision": revision,
                  "model_revision": request["model_revision"], "model_directory": str(snapshot),
                  "missing_model_files": missing, "device": device, "cuda_available": torch.cuda.is_available(),
                  "gpus": gpu, "cpu_count": os.cpu_count(), "disk_free_bytes": shutil.disk_usage(cache).free,
                  "required_model_bytes": sum(value[0] for value in MODEL_FILES.values()),
                  "inference_verified": False}
    if not ready:
        diagnostic["error"] = "Requested CUDA device is unavailable" if not available else "Model files missing; run voice doctor --download-model"
    if request["command"] != "generate":
        return diagnostic
    if not ready:
        raise RuntimeError(diagnostic["error"])
    if not request.get("segments") or len(request["segments"]) != len(request.get("outputs", [])):
        raise ValueError("Speech segments and output paths must have equal nonzero length")
    import numpy as np
    import soundfile as sf
    import random
    torch.set_num_threads(min(8, os.cpu_count() or 1))
    started = time.perf_counter()
    # from_pretrained has no revision argument; from_local prevents floating weights.
    model = ChatterboxTurboTTS.from_local(snapshot, device=device, nano=False)
    load_seconds = time.perf_counter() - started
    settings = request.get("settings", {})
    inference = []
    for text, output in zip(request["segments"], request["outputs"], strict=True):
        seed = settings.get("seed", 0)
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        start = time.perf_counter()
        controls = {key: settings[key] for key in ("temperature", "top_p", "top_k", "repetition_penalty") if key in settings}
        with torch.inference_mode():
            wav = model.generate(text, audio_prompt_path=request.get("reference"), **controls)
        samples = wav.detach().cpu().numpy().reshape(-1)
        if not np.isfinite(samples).all() or not samples.size:
            raise ValueError("Turbo produced empty or nonfinite audio")
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), samples, model.sr, subtype="PCM_16")
        inference.append({"seconds": time.perf_counter() - start, "sample_rate": model.sr,
                          "frames": samples.size, "duration_seconds": samples.size / model.sr})
    return {"runtime": runtime, "source_revision": revision, "model_revision": request["model_revision"],
            "device": device, "load_seconds": load_seconds, "segments": inference,
            "total_seconds": time.perf_counter() - started, "inference_verified": True}


def main():
    try:
        raw = sys.stdin.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Voice request exceeds 2 MiB")
        with contextlib.redirect_stdout(sys.stderr):
            result = handle(json.loads(raw))
        response = {"protocol": 1, "ok": True, "result": result}
        status = 0
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        response = {"protocol": 1, "ok": False, "error": f"{type(error).__name__}: {error}"}
        status = 1
    print(json.dumps(response, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
