"""Bounded official-model range download for connections that stall on large responses.

Run from repository root: python -m tools.download_voice_model
Existing complete pinned files are verified and reused; partial files are never ready.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import threading
import time
import urllib.request

from engine.voice.model_integrity import MODEL_FILES, verify_model_files
from engine.voice.provider import MODEL_REPO, MODEL_REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("outputs/voice-models"))
    args = parser.parse_args()
    snapshot = args.cache.resolve() / f"models--{MODEL_REPO.replace('/', '--')}" / "snapshots" / MODEL_REVISION
    snapshot.mkdir(parents=True, exist_ok=True)
    for name, identity in MODEL_FILES.items():
        try:
            verify_model_files(snapshot, {name: identity})
            print(f"Verified existing {name}", flush=True)
            continue
        except ValueError:
            pass
        size = identity[0]
        path = snapshot / name
        partial = snapshot / (name + ".atlas-partial")
        lock = threading.Lock()
        chunk_size = 16 * 1024 * 1024
        with partial.open("w+b") as output:
            output.truncate(size)
            def fetch(start):
                end = min(start + chunk_size, size) - 1
                # A distinct cache key avoids intermediaries serving a previous byte range.
                url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}?atlas_range={start}"
                for attempt in range(3):
                    try:
                        request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}", "User-Agent": "ATLAS-model-installer"})
                        with urllib.request.urlopen(request, timeout=45) as response:
                            if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                                raise ValueError(f"Unexpected range response for {name} at {start}")
                            data = response.read(end - start + 2)
                        if len(data) != end - start + 1:
                            raise ValueError(f"Truncated range for {name}")
                        with lock:
                            output.seek(start)
                            output.write(data)
                        return len(data)
                    except (OSError, ValueError):
                        if attempt == 2:
                            raise
                        time.sleep(attempt + 1)
            total = 0
            with ThreadPoolExecutor(max_workers=4) as pool:
                for count in pool.map(fetch, range(0, size, chunk_size)):
                    total += count
                    print(f"{name}: {total}/{size} bytes", flush=True)
            output.flush()
        # Verify the exact final file identity before atomic publication.
        verify_model_files(snapshot, {partial.name: identity})
        partial.replace(path)
        print(f"Published verified {name}", flush=True)
    verify_model_files(snapshot)
    print(f"Complete verified model: {snapshot}", flush=True)


if __name__ == "__main__":
    main()
