"""Approved recording/speech imports for versioned production timelines."""
from pathlib import Path

from engine.audio.library import AudioLibrary, AudioProvenance
from engine.storage.jobs import contained_path


def add_audio_commands(subparsers):
    group = subparsers.add_parser("audio", help="register approved WAV clips for narration/dialogue")
    commands = group.add_subparsers(dest="audio_command", required=True)
    register = commands.add_parser("import", help="snapshot an approved PCM16 WAV and provenance")
    register.add_argument("source", type=Path)
    register.add_argument("--id", required=True)
    register.add_argument("--provenance", type=Path, required=True)
    listing = commands.add_parser("list", help="list latest audio versions")
    show = commands.add_parser("show", help="verify and show a pinned audio version")
    show.add_argument("id")
    show.add_argument("--version", type=int, required=True)
    for cmd in (register, listing, show):
        cmd.add_argument("--library", type=Path, default=Path("assets/audio"))


def run_audio_command(args):
    if args.audio_command != "import" and not contained_path(args.library, "audio.sqlite3").is_file():
        if args.audio_command == "list":
            return []
        raise ValueError(f"Audio library does not exist: {args.library}")
    if args.audio_command == "import":
        if args.provenance.stat().st_size > 500000:
            raise ValueError("Audio provenance exceeds 500 KB")
        meta = AudioProvenance.model_validate_json(args.provenance.read_text(encoding="utf-8-sig"))
        return AudioLibrary(args.library).register(args.source, args.id, meta)
    lib = AudioLibrary(args.library)
    if args.audio_command == "list":
        return lib.list()
    result = lib.resolve(args.id, args.version)
    return result | {"path": str(result["path"])}
