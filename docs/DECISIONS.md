# Decisions

2026-11-23 foundation cycle:

1. Implement Phases 0/1 as one coherent backend slice. The immediate assignment explicitly prioritizes real configuration-driven videos over all advanced modules.
2. Use Python stdlib orchestration plus Pydantic 2. No FastAPI/React until a useful backend exists; no AI runtime dependency.
3. Use the installed Blender 5.2.3 LTS after launching it and testing both render engines. Do not replace installed software. Blender command safety follows the [official CLI documentation](https://docs.blender.org/manual/en/5.0/advanced/command_line/arguments.html); actual installed behavior is integration-tested.
4. Run Blender out of process. This isolates crashes, keeps bpy out of the core IR, and avoids installing Pydantic inside Blender.
5. CPU Cycles is the default portable profile. Examples choose tested Eevee for fast previews. Switching engines is explicit and recorded; no silent quality-changing fallback.
6. Start with seven procedural primitive types and deterministic scatter. No third-party downloads or licensing assumptions.
7. Use integer frames/fps, linear RGB, meters and Euler degrees. No unconstrained natural-language input.
8. Preserve every render in a unique job directory. No destructive overwrite, premature caching or implicit reuse. SQLite plus atomic JSON records provide inspection; automatic crash resumption is Phase 6.
9. Verify H.264/yuv420p, dimensions, exact decoded frame count, fps, duration, and complete FFmpeg decode before success. Visual quality still needs human review.
10. The supplied directory was empty and had no parent repository. Initialize a dedicated `atlas-foundation` branch in place; no unrelated work needs isolation.
11. Authorize routine choices from the user's detailed brief; do not introduce repeated design-approval pauses. Keep status and handoff documents honest about limitations.
