"""Voice CLI; optional runtime never affects silent project commands."""
import json
from pathlib import Path

from engine.voice.library import VoiceLibrary
from engine.voice.provider import ChatterboxProvider


def add_voice_commands(subparsers):
    group = subparsers.add_parser("voice", help="local Chatterbox-Turbo profiles and speech")
    commands = group.add_subparsers(dest="voice_command", required=True)
    parsers = {}
    for command in ("doctor", "create", "list", "history", "delete", "generate", "preview"):
        parser = commands.add_parser(command)
        parser.add_argument("--library", type=Path, default=Path("assets/voices"))
        parsers[command] = parser
    for name in ("create", "history", "delete", "generate", "preview"):
        parsers[name].add_argument("id")
    for name in ("doctor", "generate", "preview"):
        parser = parsers[name]
        parser.add_argument("--runtime-python", type=Path, default=Path("outputs/voice-runtime/Scripts/python.exe"))
        parser.add_argument("--model-cache", type=Path, default=Path("outputs/voice-models"))
        parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
        parser.add_argument("--timeout", type=int, default=1800)
    parsers["doctor"].add_argument("--download-model", action="store_true")
    parsers["create"].add_argument("--reference", type=Path)
    parsers["create"].add_argument("--consent", type=Path, help="JSON with approved, owner, allowed_usage and evidence")
    parsers["create"].add_argument("--name")
    for name in ("generate", "preview"):
        parsers[name].add_argument("--text", required=name == "generate", default="Hello. Welcome to ATLAS.")
        parsers[name].add_argument("--settings", type=Path)
        parsers[name].add_argument("--force", action="store_true", help="regenerate into a new retained take")


def _read(path):
    if path is None:
        return None
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Voice JSON exceeds 1 MiB")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_voice_command(args) -> dict:
    library = VoiceLibrary(args.library)
    command = args.voice_command
    if command == "list":
        return {"profiles": library.list_profiles()}
    if command == "create":
        return library.create_profile(args.id, reference=args.reference, consent=_read(args.consent), name=args.name)
    if command == "history":
        return {"history": library.history(args.id)}
    if command == "delete":
        return library.delete_profile(args.id)
    provider = ChatterboxProvider(args.runtime_python, device=args.device, model_cache=args.model_cache, timeout=args.timeout)
    if command == "doctor":
        return provider.download_models() if args.download_model else provider.doctor()
    return library.generate(args.text, args.id, provider, _read(args.settings), force=args.force)
