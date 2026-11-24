"""Persistent approved voice profiles and measured, content-addressed speech."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import wave
import uuid

from engine.audio.validation import verify_wav
from engine.storage.jobs import atomic_json, contained_path, utc_now
from engine.voice.provider import MODEL_REVISION, SOURCE_REVISION
from engine.voice.profiles import VoiceProfile

TAGS = {"laugh", "chuckle", "cough", "clear throat", "sigh", "gasp", "sniff", "groan", "shush"}
DEFAULTS = {"seed": 0, "temperature": 0.8, "top_p": 0.95, "top_k": 1000,
            "repetition_penalty": 1.2, "segment_chars": 250, "pause_ms": 150,
            "paragraph_pause_ms": 300}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def generation_settings(value=None):
    value = value or {}
    if set(value) - DEFAULTS.keys():
        raise ValueError(f"Unsupported Turbo settings: {sorted(set(value) - DEFAULTS.keys())}")
    result = DEFAULTS | value
    limits = {"seed": (0, 2**32 - 1), "temperature": (0.05, 2), "top_p": (0.01, 1),
              "top_k": (1, 1000), "repetition_penalty": (1, 3), "segment_chars": (8, 500),
              "pause_ms": (0, 5000), "paragraph_pause_ms": (0, 5000)}
    for key, (lower, upper) in limits.items():
        item = result[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or not lower <= item <= upper:
            raise ValueError(f"Invalid {key}: expected {lower}–{upper}")
        if key in {"seed", "top_k", "segment_chars", "pause_ms", "paragraph_pause_ms"} and not isinstance(item, int):
            raise ValueError(f"{key} must be an integer")
    return result


def segment_text(text: str, max_chars=250) -> list[dict]:
    if not isinstance(text, str) or not text.strip() or len(text) > 100000:
        raise ValueError("Speech text must contain 1–100000 characters")
    if not isinstance(max_chars, int) or not 8 <= max_chars <= 500:
        raise ValueError("Segment size must be 8–500 characters")
    for tag in re.findall(r"\[([^\]]*)\]", text):
        if tag not in TAGS:
            raise ValueError(f"Unsupported paralinguistic tag: [{tag}]")
    if "[" in re.sub(r"\[[^\]]*\]", "", text) or "]" in re.sub(r"\[[^\]]*\]", "", text):
        raise ValueError("Malformed paralinguistic tag")
    parts = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(paragraph.split())):
            current = ""
            for word in re.findall(r"\[[^\]]*\]|\S+", sentence):
                if len(word) > max_chars:
                    raise ValueError("Speech word/tag exceeds segment limit")
                if current and len(current) + len(word) + 1 > max_chars:
                    parts.append({"text": current, "paragraph_end": False})
                    current = ""
                current = f"{current} {word}".strip()
            if current:
                parts.append({"text": current, "paragraph_end": False})
        if parts:
            parts[-1]["paragraph_end"] = True
    return parts


class VoiceLibrary:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _profile_dir(self, voice_id):
        if not isinstance(voice_id, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", voice_id):
            raise ValueError("Voice ID must be 1–64 letters, digits, underscores or hyphens")
        return contained_path(self.root, f"profiles/{voice_id}")

    def create_profile(self, voice_id, *, reference=None, consent=None, name=None, settings=None, tags=None):
        directory = self._profile_dir(voice_id)
        if directory.exists():
            raise FileExistsError(f"Voice profile already exists: {voice_id}; profiles are immutable")
        settings = generation_settings(settings)
        metadata = None
        if reference is not None:
            if not isinstance(consent, dict) or consent.get("approved") is not True or any(
                not isinstance(consent.get(key), str) or not consent[key].strip()
                for key in ("owner", "allowed_usage", "evidence")
            ):
                raise ValueError("Reference consent requires approved=true, owner, allowed_usage and evidence")
            metadata = verify_wav(Path(reference))
            if not 5 < metadata["duration_seconds"] <= 30:
                raise ValueError("Turbo reference audio must be longer than 5 seconds and at most 30 seconds")
        profile = {"schema_version": 1, "id": voice_id, "name": name or voice_id,
                   "provider": "chatterbox-turbo", "source_revision": SOURCE_REVISION,
                   "model_revision": MODEL_REVISION, "language": "en", "settings": settings,
                   "tags": tags or [], "created_at": utc_now(), "consent": consent,
                   "voice_kind": "approved-reference" if reference else "model-bundled-conditioning",
                   "reference": None}
        directory.mkdir(parents=True, exist_ok=False)
        try:
            if reference is not None:
                destination = contained_path(directory, "reference.wav")
                shutil.copyfile(reference, destination)
                if verify_wav(destination)["sha256"] != metadata["sha256"]:
                    raise ValueError("Reference changed while being copied")
                profile["reference"] = {"path": str(destination), **metadata}
            profile = VoiceProfile.model_validate(profile).model_dump(mode="json")
            atomic_json(directory / "profile.json", profile)
        except BaseException:
            shutil.rmtree(directory)
            raise
        return profile

    def get_profile(self, voice_id):
        directory = self._profile_dir(voice_id)
        path = contained_path(directory, "profile.json")
        if not path.is_file():
            raise ValueError(f"Unknown voice profile: {voice_id}")
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Voice profile exceeds 1 MiB")
        profile = VoiceProfile.model_validate_json(path.read_text(encoding="utf-8")).model_dump(mode="json")
        generation_settings(profile["settings"])
        if profile.get("id") != voice_id or profile.get("source_revision") != SOURCE_REVISION or profile.get("model_revision") != MODEL_REVISION:
            raise ValueError("Voice profile identity/runtime pin mismatch")
        if profile.get("reference"):
            ref = contained_path(directory, "reference.wav")
            if profile["reference"]["path"] != str(ref) or verify_wav(ref)["sha256"] != profile["reference"]["sha256"]:
                raise ValueError("Pinned voice reference has changed")
            consent = profile.get("consent") or {}
            if consent.get("approved") is not True or not all(consent.get(k) for k in ("owner", "allowed_usage", "evidence")):
                raise ValueError("Voice reference consent is missing")
        return profile

    def list_profiles(self):
        base = contained_path(self.root, "profiles")
        return [self.get_profile(path.parent.name) for path in sorted(base.glob("*/profile.json"))]

    def history(self, voice_id):
        self.get_profile(voice_id)
        base = contained_path(self._profile_dir(voice_id), "cache")
        result = []
        for path in sorted(base.glob("*/manifest.json")):
            path = contained_path(base, str(path.relative_to(base)))
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Voice manifest exceeds 2 MiB")
            result.append(json.loads(path.read_text(encoding="utf-8")))
        return result

    def delete_profile(self, voice_id):
        directory = self._profile_dir(voice_id)
        if not directory.is_dir():
            raise ValueError(f"Unknown voice profile: {voice_id}")
        shutil.rmtree(directory)
        return {"deleted": voice_id, "note": "Profile, private reference and local cache deleted; exported audio is retained."}

    def generate(self, text, profile_id, provider, settings=None, *, force=False):
        profile = self.get_profile(profile_id)
        settings = generation_settings(profile["settings"] | (settings or {}))
        segments = segment_text(text, settings["segment_chars"])
        identity = provider.identity
        provenance = {"profile": profile, "provider": identity, "settings": settings,
                      "text": text, "assembly_version": 1}
        if force:
            provenance["take_id"] = uuid.uuid4().hex
        key = _digest(provenance)
        base = contained_path(self._profile_dir(profile_id), f"cache/{key}")
        output = contained_path(base, "speech.wav")
        manifest = contained_path(base, "manifest.json")
        if manifest.is_file() and output.is_file():
            try:
                saved = json.loads(manifest.read_text(encoding="utf-8"))
                if saved["metadata"]["sha256"] == verify_wav(output)["sha256"] and saved["cache_key"] == key:
                    return saved | {"cache_hit": True, "wav_path": str(output)}
            except (ValueError, OSError, KeyError):
                pass
        base.mkdir(parents=True, exist_ok=True)
        chunk_base = contained_path(self._profile_dir(profile_id), "segments")
        chunk_base.mkdir(parents=True, exist_ok=True)
        chunk_paths, missing_text, missing_paths = [], [], []
        with tempfile.TemporaryDirectory(prefix="generation-", dir=base) as temporary:
            temporary = Path(temporary)
            for index, segment in enumerate(segments):
                chunk_key = _digest({"text": segment["text"], "profile": profile, "provider": identity,
                                     "settings": settings, "segment_version": 1, "take_id": provenance.get("take_id")})
                chunk = contained_path(chunk_base, f"{chunk_key}.wav")
                stamp = contained_path(chunk_base, f"{chunk_key}.json")
                valid = False
                try:
                    valid = verify_wav(chunk)["sha256"] == json.loads(stamp.read_text())["sha256"]
                except (ValueError, OSError, KeyError):
                    pass
                chunk_paths.append((chunk, stamp))
                if not valid:
                    missing_text.append(segment["text"])
                    missing_paths.append(temporary / f"{index}.wav")
            inference = {}
            if missing_text:
                reference = Path(profile["reference"]["path"]) if profile["reference"] else None
                inference = provider.generate(missing_text, missing_paths, reference, settings)
                for stage in missing_paths:
                    metadata = verify_wav(stage)
                    chunk, stamp = chunk_paths[int(stage.stem)]
                    os.replace(stage, chunk)
                    atomic_json(stamp, metadata)
            stage = temporary / "combined.wav"
            cursor, result_segments = 0, []
            format_info = None
            with wave.open(str(stage), "wb") as combined:
                for index, (chunk, _) in enumerate(chunk_paths):
                    metadata = verify_wav(chunk)
                    with wave.open(str(chunk), "rb") as source:
                        params = (source.getnchannels(), source.getsampwidth(), source.getframerate())
                        if format_info is None:
                            format_info = params
                            combined.setparams((*params, 0, "NONE", "not compressed"))
                        if params != format_info:
                            raise ValueError("Provider returned inconsistent segment audio formats")
                        result_segments.append({**segments[index], "start_seconds": cursor / params[2],
                                                "duration_seconds": metadata["duration_seconds"],
                                                "sha256": metadata["sha256"]})
                        combined.writeframes(source.readframes(source.getnframes()))
                        cursor += source.getnframes()
                        if index < len(chunk_paths) - 1:
                            pause_ms = settings["paragraph_pause_ms"] if segments[index]["paragraph_end"] else settings["pause_ms"]
                            pause_frames = round(pause_ms * params[2] / 1000)
                            combined.writeframes(b"\x00" * pause_frames * params[0] * params[1])
                            cursor += pause_frames
            metadata = verify_wav(stage)
            os.replace(stage, output)
        result = {"wav_path": str(output), "metadata": metadata, "provenance": provenance,
                  "segments": result_segments, "cache_key": key, "cache_hit": False,
                  "inference": inference, "created_at": utc_now()}
        atomic_json(manifest, result)
        return result
