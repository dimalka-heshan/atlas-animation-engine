# Asset licensing and provenance

This milestone uses only generated Blender primitive geometry and numeric material configurations. It includes no downloaded models, textures, fonts, audio or asset packs. Manifests therefore record an empty external asset list. Primitive examples require no external attribution data to execute.

ATLAS does not yet import, index, approve, normalize or redistribute third-party assets. Do not interpret absence of an asset registry as permission to use arbitrary files. Phase 2 must record creator, source URL, exact license/license text, attribution, redistribution restrictions, source hash, version and import status. Unknown or incompatible usage must be flagged or rejected before production.

Free download does not mean CC0. Evaluate Kenney, Quaternius, Poly Haven, KayKit and other packs individually. Unity Asset Store conversion must respect the actual asset license. Automated scraping and library redistribution are outside the current workflow.

Runtime dependencies keep their own licenses: Python (PSF), Pydantic (MIT), pytest (MIT), setuptools (MIT), Blender (GPL), and FFmpeg according to build options. The installed FFmpeg reports GPL and version3 enabled. The project neither bundles nor relicenses those executables. Select a repository software license before distributing ATLAS; this development cycle does not make that ownership decision for the user.
