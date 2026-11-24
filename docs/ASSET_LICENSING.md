# Asset licensing and provenance

The primitive examples use generated geometry and numeric materials. Version 0.2 also includes an original locally generated GLB lantern and its provenance sidecar, with no downloaded models, textures, fonts, audio or asset packs. Asset-backed manifests record its source hash, pinned version, declared rights and inspection evidence; primitive-only manifests retain an empty asset list.

The local registry now records creator, meaningful source URL/URN, license ID/text, attribution, restrictions, explicit approval/render/redistribution permissions, SHA-256, immutable version and inspection status. Unknown or incompatible declared usage is rejected before Blender inspection or production. Approval is operator-supplied and is never inferred or automatically granted. See ASSETS for the deliberately narrow supported policy and static GLB profile. No third-party pack has yet been imported in the acceptance demonstrations.

Free download does not mean CC0. Evaluate Kenney, Quaternius, Poly Haven, KayKit and other packs individually. Automated scraping and library redistribution are outside the current workflow. A stored approval is a declaration, not independent legal verification. Registering a newer version does not revoke an older version's approval; global revocation workflows remain unimplemented.

Runtime dependencies keep their own licenses: Python (PSF), Pydantic (MIT), pytest (MIT), setuptools (MIT), Blender (GPL), and FFmpeg according to build options. The installed FFmpeg reports GPL and version3 enabled. The project neither bundles nor relicenses those executables. Select a repository software license before distributing ATLAS; this development cycle does not make that ownership decision for the user.

Version 0.3 adds original locally generated beacon/crate acceptance geometry from `tools/create_batch_fixture.py`, including duplicate, corrupt and unreviewed test cases. Batch plans default to no selection, and batch registration requires explicit approved rendering permission. Scanned names/tags/license labels are informational; the hashed sidecar is revalidated at apply time. Thumbnail generation uses the same rights gate as rendering and grants no additional redistribution permission. No external asset pack has been downloaded or approved during this release.

## Approved upstream assets (0.5)

Kay Lousberg's two pinned KayKit releases declare CC0 for their asset content. ATLAS stores the license text from the official archive and the original archive SHA256 with each registered asset. Poly Haven's HDRIs and textures are CC0. Its live API has separate terms and requires identifiable requests and visible source credit. The catalog shows Powered by Poly Haven and the ATLAS client identifies itself in the user agent. The model and media originals remain in the local ignored acquisition cache.

Acquisition does not infer rights for arbitrary ZIPs. Manual import requires the existing explicit approved provenance and stores the archive hash and member path. Renders preserve attribution and licensing evidence for the versions used. The courtyard's speech remains the V0.4 model-bundled Chatterbox output with no imported human voice sample.
