# Status — ATLAS 0.5.0 — 2026-11-25

ATLAS renders approved acquired environments and source-rig animation through the existing JSON and Blender pipeline. Two official providers supplied real assets for four verified previews. V0.4 speech, audio and facial workflows remain integrated.

## Verified baseline

Commit 48112b2 already contained V0.4. A fresh baseline with Blender, FFmpeg, Rhubarb and actual Turbo inference passed 211 tests with one skip in 266.71 seconds. The earlier V0.3 status was stale. V0.4 independently generated 4.27 seconds of Turbo speech on this Intel CPU, rendered an existing orbit scene with narration, and saved an editable shape-key talking character. The model load and two segment inferences took 34.84 seconds.

## V0.5 implemented and verified

- KayKit pinned starter archive and Poly Haven live HDRI/texture adapters. A local SQLite catalog contains 1,878 records (12 KayKit, 1,866 Poly Haven). Offline search supports metadata terms, style/category filters, pagination and deterministic seed ranking.
- Bounded HTTPS downloads, SHA256-addressed originals, cache validation and safe ZIP member import. Media versions pin channel hashes. The local production registry keeps its existing immutable IDs, approvals, provenance and static preflight.
- 10 acquired static environment GLBs, 2 acquired rigged humanoid GLBs, 5 three-channel material sets and 2 HDRIs. All 12 GLBs inspected ready, all 7 media sets decoded in Blender, 19 acquired assets total. The final starter has zero rejected assets. Seven zero-duration pose entries per rig do not count as playable clips.
- Knight and Mage each have 41 bones and 69 playable source clips, with the same inspected rest-skeleton hash. There are 69 distinct names and 138 source-bound clip records. Original action slots, skin deformation, exact integer timeline boundaries and a rigid hand attachment were verified after reopening a saved scene.
- Schema 1.3 provides pinned humanoids, sequential clip events, speed, loops, hand equipment, environment media and reusable environment placements. The archive originals are preserved while static glTF resources are embedded into production GLBs. Both imported humanoids lack facial controls. The original Atlas character performs the measured Turbo/Rhubarb dialogue in two V0.5 demos.
- The cache stores 26,160,115 bytes of original source blobs. Registered GLBs total 7,758,180 bytes. Measured render times range from 43.79 to 80.21 seconds for these previews. See PERFORMANCE and the evidence JSON for actual details.

## Demonstrations

| Preview | Result | Runtime |
|---|---|---:|
| Acquired assets | outputs/medieval-asset-showcase-b733ddd366a04f89adc66474ad88122e/video.mp4 | 4.00 s |
| Rig and clips | outputs/source-rig-showcase-989dcb340456453b8ee545c0d860ca0c/video.mp4 | 4.00 s |
| Talking character | outputs/atlas-talking-head-790ada2f6a3f4c3a956b1a9762aa82f1/video.mp4 | 4.83 s |
| Medieval courtyard | outputs/medieval-courtyard-d82aefec350d42ec823ebb38f76a6606/video.mp4 | 6.00 s |

The configured renders use the normal pipeline and retain scene.blend, input snapshots, video hashes, measured timings and attribution. Representative frames were visually inspected. The showcase and courtyard reuse the exact same static collection. Reopened scenes confirm packed environment media and editable body/facial animation plus the checked audio strip. Instructions are in V05_DEMOS.

## Verification

Full available suite with ATLAS_INTEGRATION=1, ATLAS_VOICE_INTEGRATION=1 and ATLAS_ACQUIRED_INTEGRATION=1: 227 passed, 1 skipped in 169.52 seconds. The skip was Windows file-symlink privilege. The isolated wheel also rendered a rigged MP4 from outside the checkout. The final targeted suite passed 16 tests, including the saved-scene check after the last NLA endpoint fix. The four demonstration job manifests retain their source hashes from before that small fix. Independent review verified the boundary behavior and identified animation key and repeat limits and pinned media replay, now addressed. See docs/evidence/2026-11-25-v05.json and outputs/v05-final-tests.xml.

## Limits and next milestone

Supported formats are strict static GLB, single-skin embedded rigged GLB with transform clips, and bounded one-BIN glTF packing with same-folder JPEG/PNG dependencies. The two character imports share a rig family. Cross-file animation reuse, arbitrary retargeting, external rigged facial controls, advanced animation blending, FBX/OBJ/BLEND/USD, fitted clothing, source root-motion processing and foot placement remain open.

The provider catalog covers the two implemented sources and selected capabilities. Wider providers, compatibility-based automatic replacement, partial-transfer recovery and managed cache eviction are future work. Models are source-licensed stylized assets, and the videos are technical previews. The next milestone is controlled character movement, navigation and semantic interactions with validated transitions, starting from the inspected humanoid family.
