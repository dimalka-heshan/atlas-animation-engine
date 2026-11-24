"""Lip-sync command registration independent of the production CLI."""
from pathlib import Path

from engine.lipsync import LipSyncTimeline, align_wav
from engine.lipsync.rhubarb import doctor


def add_lipsync_commands(subparsers):
    root = subparsers.add_parser('lipsync', help='measured audio-driven English mouth cues')
    commands = root.add_subparsers(dest='lipsync_command', required=True)
    health = commands.add_parser('doctor', help='verify optional Rhubarb runtime')
    health.add_argument('--executable', type=Path)
    align = commands.add_parser('align', help='align a PCM WAV using Rhubarb 1.14.0')
    align.add_argument('audio', type=Path)
    text = align.add_mutually_exclusive_group(required=True)
    text.add_argument('--transcript')
    text.add_argument('--transcript-file', type=Path)
    align.add_argument('--output', type=Path, required=True)
    align.add_argument('--executable', type=Path)
    check = commands.add_parser('validate', help='validate a saved cue timeline')
    check.add_argument('timeline', type=Path)


def run_lipsync_command(args) -> dict:
    if args.lipsync_command == 'doctor':
        return doctor(args.executable)
    if args.lipsync_command == 'align':
        transcript = args.transcript if args.transcript is not None else args.transcript_file.read_text(encoding='utf-8-sig')
        timeline = align_wav(args.audio, transcript, args.output, args.executable)
        return {'timeline': str(args.output.resolve()), **timeline.model_dump()}
    if args.lipsync_command == 'validate':
        return LipSyncTimeline.model_validate_json(args.timeline.read_text(encoding='utf-8-sig')).model_dump()
    raise ValueError('Unknown lip-sync command')
