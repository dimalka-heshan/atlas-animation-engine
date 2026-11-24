"""Resolve measured audio before rendering; mix only checked job-local snapshots."""
import shutil
from pathlib import Path

from engine.assets.registry import file_hash
from engine.audio.library import AudioLibrary
from engine.audio.validation import verify_wav
from engine.core.models import Project
from engine.rendering.runtime import run_logged
from engine.storage.jobs import atomic_json, contained_path


def resolve_audio(project: Project, library: Path) -> list[dict]:
    if not project.audio:
        return []
    if not contained_path(library, "audio.sqlite3").is_file():
        raise ValueError(f"Audio library does not exist: {library}")
    registry = AudioLibrary(library)
    duration = project.render.frames / project.render.fps
    entries = []
    for event in project.audio:
        entry = registry.resolve(event.clip.id, event.clip.version)
        end = event.start_seconds + entry["metadata"]["duration_seconds"]
        if end > duration + 1 / 48000:
            raise ValueError(f"Audio event {event.id} ends at {end:.3f}s beyond video {duration:.3f}s; extend render.frames or move the event")
        entries.append(entry | {"event": event.model_dump(mode="json")})
    by_event = {entry["event"]["id"]: entry for entry in entries}
    for performance in project.performances:
        entry = by_event[performance.audio_event_id]
        if performance.timeline.audio_sha256 != entry["sha256"]:
            raise ValueError("Lip-sync timeline audio hash does not match its assigned clip")
        if abs(performance.timeline.duration_seconds - entry["metadata"]["duration_seconds"]) > 1 / entry["metadata"]["sample_rate"]:
            raise ValueError("Lip-sync duration does not match measured audio")
    return entries


def snapshot_audio(entries: list[dict], directory: Path) -> list[dict]:
    results = []
    if not entries:
        return results
    (directory / "audio").mkdir()
    for entry in entries:
        relative = f"audio/{entry['sha256']}.wav"
        target = contained_path(directory, relative)
        if not target.exists():
            shutil.copyfile(entry["path"], target)
        if file_hash(target) != entry["sha256"]:
            raise ValueError("Audio source changed while snapshotting")
        verify_wav(target)
        results.append({key: value for key, value in entry.items() if key != "path"} | {"source_file": relative})
    atomic_json(directory / "audio-manifest.json", results)
    (directory / "audio-attributions.txt").write_text("\n\n".join(
        f"{e['id']} v{e['version']}: {e['provenance']['creator']}\n{e['provenance']['source_url']}\n"
        f"{e['provenance']['license_id']}\n{e['provenance']['attribution']}" for e in results), encoding="utf-8")
    return results


def mix_audio(entries: list[dict], directory: Path, duration: float, ffmpeg: Path, timeout: float) -> dict:
    if not entries:
        raise ValueError("Cannot mix an empty audio timeline")
    command = [str(ffmpeg), "-nostdin", "-v", "warning", "-y"]
    filters, labels = [], []
    for index, entry in enumerate(entries):
        source = contained_path(directory, entry["source_file"])
        if file_hash(source) != entry["sha256"]:
            raise ValueError("Audio snapshot hash mismatch before mixing")
        command.extend(["-i", str(source)])
        event = entry["event"]
        # Nearest sample (half up) on the common 48 kHz clock, not milliseconds.
        delay = int(event["start_seconds"] * 48000 + .5)
        label = f"a{index}"
        filters.append(f"[{index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                       f"volume={event['gain']:.9f},adelay={delay}S:all=1[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"amix=inputs={len(entries)}:normalize=0:dropout_transition=0,"
                   f"apad,atrim=duration={duration:.9f}[mix]")
    target = directory / "audio-mix.wav"
    elapsed = run_logged(command + ["-filter_complex", ";".join(filters), "-map", "[mix]", "-ar", "48000",
        "-ac", "2", "-c:a", "pcm_s16le", str(target)], directory / "audio-mix.log", timeout)
    metadata = verify_wav(target)
    if abs(metadata["duration_seconds"] - duration) > 1 / 48000:
        raise ValueError("Mixed audio duration drift")
    if metadata["clipped_samples"]:
        raise ValueError("Audio mix clips; lower event gain before rendering")
    return metadata | {"file": "audio-mix.wav", "mix_seconds": elapsed}


def mux_audio(directory: Path, duration: float, ffmpeg: Path, timeout: float) -> float:
    target = directory / "video.audio.partial.mp4"
    elapsed = run_logged([str(ffmpeg), "-nostdin", "-v", "warning", "-y", "-i", str(directory / "video.partial.mp4"),
        "-i", str(directory / "audio-mix.wav"), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{duration:.9f}",
        "-movflags", "+faststart", str(target)], directory / "audio-mux.log", timeout)
    target.replace(directory / "video.partial.mp4")
    return elapsed
