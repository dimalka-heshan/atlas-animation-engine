# Director and production service

The director supplies creative intent. ATLAS validates requirements and resolves typed production requests. Blender executes the resulting scenes through package-owned entry points. Portable plans and projects contain data, including any dialogue or production notes.

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m apps.cli capabilities
& $python -m apps.cli director schema
& $python -m apps.cli director validate outputs/director-intent.json
& $python -m apps.cli validate examples/01_orbit_studio.json
& $python -m apps.cli production preview outputs/director-preview.json
```

`capabilities` exposes the operation version, status, JSON input and output schemas, execution command, preconditions, known limits and artifacts. Unavailable entries have no execution contract. The Python host uses `engine.production` for preflight, action compilation and bounded previews. The ordinary render pipeline and CLI share the scene preparation function.

`props.transfer` uses `atlas production handoff` with a schema 1.6 project and a required handoff definition. The result includes the verified video, manifest and contact report. [Handoff example](V062_DEMOS.md)

The version 1.0 creative intake accepts intent and requested capability names. For example, `{"schema_version":"1.0","title":"The archive","summary":"A curator introduces the collection.","required_capabilities":["render.preview"]}`. Its review reports capability gaps. A ready result means the named capabilities are available. The executable Blender input is a separate ATLAS project. Automated story compilation, HTTP and MCP are later phases.

Trusted host arguments select output, libraries and executable paths. Preview accepts at most 960 by 540 pixels in either orientation, 240 frames, 32 samples and 16 threads. Existing ordinary renders retain their original project limits. No credentials are needed to use the local services with approved assets already installed.
